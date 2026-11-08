/**
 * La galerie de la fiche (spec §3.2, §4.4, §6.2, §6.3 ; issue #170) : ses images, ses commandes et ce
 * qu'elle tient du panneau, aux deux largeurs. Toutes les images d'une fiche partagent leur fichier ;
 * la légende, l'accessibilité et la position disent laquelle est montrée.
 */
import type { Page } from '@playwright/test'
import { expect, serveProjects, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  arriveAt,
  CAPTIONS,
  center,
  closeButton,
  expectNoOverflow,
  expectNoViolations,
  expectPanelBox,
  ficheProject,
  freezeAnimations,
  gallery,
  LONG_DESCRIPTION,
  nextImage,
  panel,
  penDrag,
  previousImage,
  readingColumn,
  THREE_IMAGES,
  viewer,
} from './project.ts'
import { buildImage, FILES_ORIGIN } from './projects.ts'
import { COLUMN_VIEWPORT, watchTransitions } from './table.ts'

const PHONE_VIEWPORT = { width: 400, height: 800 }

const frame = (page: Page) => page.locator('.project-gallery-frame')
const bar = (page: Page) => page.locator('.project-gallery-bar')
const caption = (page: Page) => page.locator('.project-gallery-caption')
const counter = (page: Page) => page.locator('.project-gallery-counter')

/** Attend une image montrée : posée dans le cadre, légendée, comptée, seule exposée. */
async function expectImage(page: Page, position: number, count = CAPTIONS.length) {
  const image = gallery(page).getByRole('img')

  await expect(image).toHaveAccessibleName(CAPTIONS[position])
  await expect(caption(page)).toHaveText(CAPTIONS[position])
  await expect(counter(page)).toHaveText(`${position + 1} / ${count}`)
  await expect(counter(page)).toHaveAttribute('aria-live', 'polite')
  await expect
    .poll(async () => {
      const { x } = (await frame(page).boundingBox())!
      return Math.round((await image.boundingBox())!.x - x)
    })
    .toBe(0)
}

/** Attend le cadre sans commande : ni flèches ni compteur. */
async function expectNoCommands(page: Page) {
  await expect(previousImage(page)).toHaveCount(0)
  await expect(nextImage(page)).toHaveCount(0)
  await expect(counter(page)).toHaveCount(0)
}

/**
 * Consigne les touches à partir de maintenant : l'écouteur de la page, posé avant, a déjà joué.
 *
 * @returns De quoi lire si chacune a été annulée.
 */
async function watchKeys(page: Page) {
  const keys = await page.evaluateHandle(() => {
    const seen: boolean[] = []
    addEventListener('keydown', (event) => seen.push(event.defaultPrevented))
    return seen
  })
  return () => keys.jsonValue()
}

/** Les défilements de tout ce qui peut défiler : la page, le panneau, la colonne. */
const scrollOffsets = (page: Page) =>
  page.evaluate(() =>
    [document.documentElement, ...document.querySelectorAll('.project-panel, .project-scroll')].map(
      ({ scrollLeft, scrollTop }) => [scrollLeft, scrollTop],
    ),
  )

test.beforeEach(async ({ page, isMobile }) => {
  await page.setViewportSize(isMobile ? PHONE_VIEWPORT : COLUMN_VIEWPORT)
})

test.describe('à trois images', () => {
  test.beforeEach(async ({ page }) => {
    await arriveAt(page, { gallery: THREE_IMAGES, description: LONG_DESCRIPTION })
  })

  test('Fermer reste le premier arrêt, et la première image est montrée', async ({ page }) => {
    await expect(closeButton(page)).toBeFocused()
    await expectImage(page, 0)
  })

  test('les flèches bouclent dans les deux sens', async ({ page }) => {
    await previousImage(page).click()
    await expectImage(page, 2)

    await nextImage(page).click()
    await expectImage(page, 0)

    await nextImage(page).click()
    await expectImage(page, 1)
    await expectNoViolations(page)
  })

  test('une image glisse en 240 ms, par la courbe --ease-out', async ({ page }) => {
    const transitions = await watchTransitions(page)

    await nextImage(page).click()
    await settle(page)

    const [curve] = await resolveAll(page, [['transition-timing-function', 'var(--ease-out)']])
    expect(await transitions('project-gallery-track')).toEqual([
      { layer: 'project-gallery-track', property: 'translate', duration: '0.24s' },
    ])
    await expect(page.locator('.project-gallery-track')).toHaveCSS('transition-timing-function', curve)
  })

  for (const [name, focus] of [
    ['Fermer', (page: Page) => closeButton(page).focus()],
    ['une flèche', (page: Page) => nextImage(page).focus()],
    ['la colonne de lecture', (page: Page) => readingColumn(page).focus()],
  ] as const) {
    test(`← et → depuis ${name} changent d’image, sans autre effet`, async ({ page }) => {
      await focus(page)
      const keys = await watchKeys(page)
      const [url, offsets] = [page.url(), await scrollOffsets(page)]

      await page.keyboard.press('ArrowLeft')
      await expectImage(page, 2)

      await page.keyboard.press('ArrowRight')
      await expectImage(page, 0)

      expect(await keys()).toEqual([true, true])
      expect(page.url()).toBe(url)
      expect(await scrollOffsets(page)).toEqual(offsets)
    })
  }

  for (const modifier of ['Alt', 'Control', 'Meta', 'Shift']) {
    test(`${modifier}+← garde son sens natif`, async ({ page }) => {
      const keys = await watchKeys(page)

      await page.keyboard.press(`${modifier}+ArrowLeft`)

      expect(await keys()).toEqual([false, false])
      await expectImage(page, 0)
    })
  }
})

test('en mouvement réduit, l’image change sans glisser', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await arriveAt(page, { gallery: THREE_IMAGES })
  const transitions = await watchTransitions(page)

  await nextImage(page).click()

  await expectImage(page, 1)
  expect(await transitions('project-gallery-track')).toEqual([])
})

test.describe('le balayage', () => {
  test.use({ hasTouch: true })

  /** Un doigt posé au centre du cadre, déplacé en quatre temps, puis levé ou annulé. */
  async function touch(page: Page, dx: number, dy: number, end: 'touchEnd' | 'touchCancel') {
    const start = await center(frame(page))
    const client = await page.context().newCDPSession(page)
    const send = (type: 'touchStart' | 'touchMove' | 'touchEnd' | 'touchCancel', step: number | null) =>
      client.send('Input.dispatchTouchEvent', {
        type,
        touchPoints:
          step === null ? [] : [{ x: start.x + (dx * step) / 4, y: start.y + (dy * step) / 4 }],
      })

    await send('touchStart', 0)
    for (const step of [1, 2, 3, 4]) await send('touchMove', step)
    await send(end, null)
    await client.detach()
  }

  test.beforeEach(async ({ page }) => {
    await arriveAt(page, { gallery: THREE_IMAGES, description: LONG_DESCRIPTION })
  })

  test('39 px ne change rien, 41 px change d’image, dans les deux sens', async ({ page }) => {
    await touch(page, -39, 0, 'touchEnd')
    await expectImage(page, 0)

    await touch(page, -41, 0, 'touchEnd')
    await expectImage(page, 1)

    await touch(page, 41, 0, 'touchEnd')
    await expectImage(page, 0)
    await expect(viewer(page)).toHaveCount(0)
  })

  test('un frémissement vertical ne change pas d’image, et fait défiler le panneau', async ({
    page,
    isMobile,
  }) => {
    await touch(page, 10, -80, 'touchEnd')

    await expectImage(page, 0)
    if (isMobile) {
      await expect.poll(() => panel(page).evaluate(({ scrollTop }) => scrollTop)).toBeGreaterThan(0)
    }
  })

  test('un geste annulé est oublié : un pointeur qui se lève ensuite ne l’achève pas', async ({
    page,
  }) => {
    await touch(page, -60, 0, 'touchCancel')

    const [outside, inside] = [await center(bar(page)), await center(frame(page))]
    await page.mouse.move(outside.x, outside.y)
    await page.mouse.down()
    await page.mouse.move(inside.x - 60, inside.y)
    await page.mouse.up()

    await expectImage(page, 0)
  })

  test('une souris ne balaie pas', async ({ page }) => {
    const { x, y } = await center(frame(page))

    await page.mouse.move(x, y)
    await page.mouse.down()
    await page.mouse.move(x - 100, y)
    await page.mouse.up()

    await expectImage(page, 0)
    // Un glissé n'est pas un clic : il n'ouvre pas la couche plein écran (#243).
    await expect(viewer(page)).toHaveCount(0)
  })

  test('un stylet balaie', async ({ page }) => {
    const start = await center(frame(page))

    await penDrag(page, start, { x: start.x - 60, y: start.y })

    await expectImage(page, 1)
    await expect(viewer(page)).toHaveCount(0)
  })
})

test.describe('les images prêtes seules comptent', () => {
  test('trois images dont une en attente : « 1 / 2 », et la boucle ne la voit pas', async ({
    page,
  }) => {
    await arriveAt(page, {
      gallery: [
        buildImage('fiche', CAPTIONS[0]),
        buildImage('fiche', 'En attente', 'pending'),
        buildImage('fiche', CAPTIONS[1]),
      ],
    })

    await expectImage(page, 0, 2)

    await nextImage(page).click()
    await expectImage(page, 1, 2)

    await nextImage(page).click()
    await expectImage(page, 0, 2)
  })

  test('une prête et une en échec : ni flèches ni compteur, la barre garde la légende', async ({
    page,
  }) => {
    await arriveAt(page, {
      gallery: [buildImage('fiche', CAPTIONS[0]), buildImage('fiche', 'Échec', 'failed')],
    })
    const keys = await watchKeys(page)

    await page.keyboard.press('ArrowLeft')

    await expectNoCommands(page)
    await expect(caption(page)).toHaveText(CAPTIONS[0])
    await expect(gallery(page).getByRole('img')).toHaveAccessibleName(CAPTIONS[0])
    expect((await bar(page).boundingBox())!.height).toBe(20)
    expect(await keys()).toEqual([false])
    await expectNoViolations(page)
  })

  for (const [name, images] of [
    ['une galerie vide', []],
    ['deux images en attente', ['Une', 'Deux'].map((text) => buildImage('fiche', text, 'pending'))],
  ] as const) {
    test(`${name} : le carré --line, la barre vide, le panneau tenu`, async ({ page }) => {
      await arriveAt(page, { gallery: [...images] })
      const [line] = await resolveAll(page, [['background-color', 'var(--line)']])
      const { width } = (await frame(page).boundingBox())!

      await expectNoCommands(page)
      await expect(gallery(page).getByRole('img')).toHaveCount(0)
      await expect(frame(page)).toHaveCSS('background-color', line)
      await expect(bar(page)).toHaveText('')
      expect((await frame(page).boundingBox())!.height).toBe(width)
      expect((await bar(page).boundingBox())!.height).toBe(20)
      await expectPanelBox(page)
      await expectNoViolations(page)
    })
  }
})

test.describe('les repères de §3.2 et §4.4', () => {
  test('le carré, la barre et les marges du panneau', async ({ page, isMobile }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })
    const [side, inset] = isMobile ? [384, 8] : [594, 10]
    const { x: panelX, y: panelY } = (await panel(page).boundingBox())!

    expect(await frame(page).boundingBox()).toEqual({
      x: panelX + inset,
      y: panelY + inset,
      width: side,
      height: side,
    })
    expect(await bar(page).boundingBox()).toEqual({
      x: panelX + inset,
      y: panelY + inset + side + 8,
      width: side,
      height: 20,
    })
  })

  test('l’image tient entière dans le carré', async ({ page }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })

    await expect(gallery(page).getByRole('img')).toHaveCSS('object-fit', 'contain')
    await expect(gallery(page).getByRole('img')).toHaveAttribute('loading', 'lazy')
  })

  test('le cadre laisse le défilement vertical et le pincement au navigateur', async ({ page }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })

    await expect(frame(page)).toHaveCSS('touch-action', 'pan-y pinch-zoom')
  })

  test('les flèches : 36 px, rondes, centrées, à 8 px des bords, --paper à 88 %, --ink', async ({
    page,
  }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })
    const box = (await frame(page).boundingBox())!
    const [paper, ink] = await resolveAll(page, [
      ['background-color', 'color-mix(in srgb, var(--paper) 88%, transparent)'],
      ['color', 'var(--ink)'],
    ])
    const middle = box.y + box.height / 2 - 18

    expect(await previousImage(page).boundingBox()).toEqual({
      x: box.x + 8,
      y: middle,
      width: 36,
      height: 36,
    })
    expect(await nextImage(page).boundingBox()).toEqual({
      x: box.x + box.width - 44,
      y: middle,
      width: 36,
      height: 36,
    })
    for (const arrow of [previousImage(page), nextImage(page)]) {
      await expect(arrow).toHaveCSS('border-radius', '50%')
      await expect(arrow).toHaveCSS('background-color', paper)
      await expect(arrow).toHaveCSS('color', ink)
      await expect(arrow.locator('svg')).toHaveAttribute('aria-hidden', 'true')
      expect(await arrow.locator('svg').boundingBox()).toMatchObject({ width: 18, height: 18 })
    }
  })

  test('la barre : 13 px --ink-2, chiffres tabulaires, légende à gauche, compteur à droite', async ({
    page,
  }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })
    const [ink2] = await resolveAll(page, [['color', 'var(--ink-2)']])
    const box = (await bar(page).boundingBox())!

    await expect(bar(page)).toHaveCSS('color', ink2)
    await expect(bar(page)).toHaveCSS('font-size', '13px')
    await expect(counter(page)).toHaveCSS('font-variant-numeric', 'tabular-nums')
    expect((await caption(page).boundingBox())!.x).toBe(box.x)
    const counterBox = (await counter(page).boundingBox())!
    expect(counterBox.x + counterBox.width).toBe(box.x + box.width)
  })

  /** Une légende de 50 caractères, la borne de §7, sur douze images. */
  const LONGEST_CAPTION = 'Écran de suivi des expéditions, vue par entrepôts.'
  const TWELVE_LONG_CAPTIONS = Array.from({ length: 12 }, () => buildImage('fiche', LONGEST_CAPTION))

  test('une légende de 50 caractères tient sur la barre, compteur à deux chiffres compris', async ({
    page,
  }) => {
    expect(LONGEST_CAPTION).toHaveLength(50)
    await arriveAt(page, { gallery: TWELVE_LONG_CAPTIONS })

    await page.keyboard.press('ArrowLeft')

    await expect(counter(page)).toHaveText('12 / 12')
    await expectNoOverflow(caption(page))
    expect((await bar(page).boundingBox())!.height).toBe(20)
  })

  test('sous 400 px, la légende longue n’élargit ni le carré ni le panneau', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'téléphone')
    await page.setViewportSize({ width: 320, height: 800 })
    await arriveAt(page, { gallery: TWELVE_LONG_CAPTIONS })

    expect((await frame(page).boundingBox())!.width).toBe(304)
    expect((await bar(page).boundingBox())!.height).toBe(20)
    expect((await caption(page).boundingBox())!.height).toBeLessThan(20)
    await expectNoOverflow(panel(page))
  })

  /**
   * Retient les images : ce que le cadre réserve ne doit rien leur devoir.
   *
   * @returns Le geste qui les laisse arriver.
   */
  async function holdImages(page: Page) {
    let release!: () => void
    const released = new Promise<void>((resolve) => (release = resolve))
    await page.route(`${FILES_ORIGIN}/images/**`, async (route) => {
      await released
      await route.fallback()
    })
    return release
  }

  test('le cadre réserve son carré avant toute image, quel que soit le format déclaré', async ({
    page,
  }) => {
    const image = buildImage('fiche', 'Une bannière')
    const banner = {
      ...image,
      height: image.width / 3,
      variants: image.variants.map((variant) => ({ ...variant, height: variant.width / 3 })),
    }
    await holdImages(page)
    await arriveAt(page, { gallery: [banner] })
    const { width, height } = (await frame(page).boundingBox())!

    expect(height).toBe(width)
    expect(width).toBeGreaterThan(0)
  })

  test('sur téléphone, une arrivée sur une ancre défile juste, et l’image arrivée n’y change rien', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'tout défile sur téléphone seulement')
    const release = await holdImages(page)
    await arriveAt(
      page,
      {
        gallery: THREE_IMAGES,
        sections: [{ title: 'Fin', anchor: 'fin', body: LONG_DESCRIPTION }],
      },
      '#s-fin',
    )
    const sectionTop = async () =>
      Math.round((await panel(page).locator('[id="s-fin"]').boundingBox())!.y)

    await expect.poll(sectionTop).toBe(8)

    release()

    await expect
      .poll(() => gallery(page).getByRole('img').evaluate((image: HTMLImageElement) => image.complete))
      .toBe(true)
    expect(await sectionTop()).toBe(8)
  })

  test('sur téléphone, les rangées ne s’étirent pas sur une fiche courte', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'une rangée au bureau')
    await arriveAt(page, { gallery: THREE_IMAGES, description: 'Court.' })

    expect((await gallery(page).boundingBox())!.height).toBe(412)
    expect((await page.locator('.project-reading').boundingBox())!.y).toBe(432)
  })

  test('sizes suit --photo : à 1024 × 768, la variante de 480 px suffit', async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, 'densité de 2,75 : la plus grande variante, à toute largeur')
    await page.setViewportSize({ width: 1024, height: 768 })
    await arriveAt(page, { gallery: THREE_IMAGES })

    await expect
      .poll(() => gallery(page).getByRole('img').evaluate((image: HTMLImageElement) => image.currentSrc))
      .toMatch(/\/480\.webp$/)
  })

  test('sizes reprend mot pour mot la formule de --photo', async ({ page }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })
    const photo = await panel(page).evaluate((element) =>
      getComputedStyle(element).getPropertyValue('--photo'),
    )

    expect(await gallery(page).getByRole('img').getAttribute('sizes')).toContain(`) ${photo},`)
  })
})

test.describe('d’une fiche à l’autre', () => {
  const OTHER = {
    slug: 'autre',
    title: 'Autre',
    gallery: CAPTIONS.slice(0, 2).map((text) => buildImage('autre', text)),
  }

  test('une autre fiche ouverte pendant le fondu de sortie d’une arrivée directe repart de la première image', async ({
    page,
  }) => {
    await serveProjects(page, [ficheProject({ gallery: THREE_IMAGES }), ficheProject(OTHER)])
    await page.goto('/projets/fiche')
    await expect(panel(page)).toBeVisible()
    await nextImage(page).click()
    await nextImage(page).click()
    await expectImage(page, 2)
    await freezeAnimations(page)

    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveAttribute('data-state', 'closed')
    await page.locator('.card', { hasText: 'Autre' }).evaluate((card: HTMLElement) => card.click())

    await expect(panel(page)).toHaveAccessibleName('Autre')
    await expectImage(page, 0, 2)
  })
})
