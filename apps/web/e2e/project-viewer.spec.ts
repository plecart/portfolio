/**
 * La couche plein écran de la galerie (issue #243) : son ouverture, son clavier, ses fermetures, sa
 * palette sombre et son fondu, aux deux largeurs ; ses gestes ont leurs scénarios
 * (`project-viewer-gestures.spec.ts`). Les images des scénarios sont carrées : à ×1, l'image a pour
 * côté le plus petit de la zone d'image — sa hauteur au bureau, sa largeur sur téléphone.
 */
import type { Page } from '@playwright/test'
import { expect, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  arriveAt,
  boundsAt,
  CAPTIONS,
  closeImageButton,
  expandButton,
  expectClosed,
  expectNoViolations,
  ficheProject,
  FIT,
  freezeAnimations,
  gallery,
  openFromTable,
  openViewer,
  outlastOpening,
  panel,
  THREE_IMAGES,
  transformOf,
  viewer,
  viewerButton,
  viewerCounter,
  viewerImage,
  viewerZone,
  watchAnimations,
  watchCspViolations,
} from './project.ts'
import { buildImage } from './projects.ts'
import { cards, serveUnderCsp, watchTransitions } from './table.ts'

const ONE_IMAGE = [buildImage('fiche', CAPTIONS[0])]

/** La barre de la couche, sa légende, et le compteur de la galerie. */
const viewerBar = (page: Page) => page.locator('.image-viewer-bar')
const viewerCaption = (page: Page) => viewer(page).locator('.project-gallery-caption')
const galleryCounter = (page: Page) => gallery(page).locator('.project-gallery-counter')

test.describe('l’ouverture', () => {
  for (const [name, open] of [
    ['« Agrandir l’image »', (page: Page) => expandButton(page).click()],
    ['un clic sur l’image', (page: Page) => gallery(page).getByRole('img').click()],
  ] as const) {
    test(`${name} ouvre la couche sur l’image courante, le focus à « Fermer l’image »`, async ({
      page,
    }) => {
      const warnings: string[] = []
      page.on('console', (message) => {
        if (['warning', 'error'].includes(message.type())) warnings.push(message.text())
      })
      await arriveAt(page, { gallery: THREE_IMAGES })

      await open(page)

      await expect(viewer(page)).toBeVisible()
      await expect(viewer(page)).toHaveAttribute('aria-modal', 'true')
      await expect(closeImageButton(page)).toBeFocused()
      await expect(viewerImage(page)).toHaveAccessibleName(CAPTIONS[0])
      await expect(viewerImage(page)).toHaveAttribute('sizes', '100vw')
      await expect(viewerImage(page)).toHaveAttribute('srcset', /960w/)
      await expect(viewerCaption(page)).toHaveText(CAPTIONS[0])
      await expect(viewerCounter(page)).toHaveText('1 / 3')
      await expect(viewerCounter(page)).toHaveAttribute('aria-live', 'polite')
      expect(warnings).toEqual([])
    })
  }

  test('la couche couvre la fenêtre ; l’image entière se centre dans la zone au-dessus de la barre', async ({
    page,
  }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })
    await openViewer(page)
    const { width, height } = page.viewportSize()!
    const bar = (await viewerBar(page).boundingBox())!
    const zone = { width, height: height - bar.height }
    const side = Math.min(zone.width, zone.height)

    expect(await viewer(page).boundingBox()).toEqual({ x: 0, y: 0, width, height })
    expect(await viewerZone(page)).toEqual({ x: 0, y: 0, ...zone })
    expect(bar).toMatchObject({ x: 0, y: zone.height, width })
    // La barre, à 8 px de chaque bord (spec §4.4) : la légende, puis le compteur.
    await expect(viewerBar(page)).toHaveCSS('padding', '8px')
    expect(await viewerImage(page).boundingBox()).toEqual({
      x: (zone.width - side) / 2,
      y: (zone.height - side) / 2,
      width: side,
      height: side,
    })
    expect(await closeImageButton(page).boundingBox()).toEqual({
      x: width - 44,
      y: 8,
      width: 36,
      height: 36,
    })
    // Les flèches de §4.4 : à 8 px des bords de la fenêtre, centrées dans la zone d'image.
    const middle = zone.height / 2 - 18
    expect(await viewerButton(page, 'Image précédente').boundingBox()).toEqual({
      x: 8,
      y: middle,
      width: 36,
      height: 36,
    })
    expect(await viewerButton(page, 'Image suivante').boundingBox()).toEqual({
      x: width - 44,
      y: middle,
      width: 36,
      height: 36,
    })
  })
})

test.describe('à trois images', () => {
  test.beforeEach(async ({ page }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })
  })

  test('→ à ×1 change d’image ; zoomé, → déplace l’image ; la galerie garde l’image vue, le focus à « Agrandir l’image »', async ({
    page,
  }) => {
    await openViewer(page)

    await page.keyboard.press('ArrowRight')
    await expect(viewerCounter(page)).toHaveText('2 / 3')
    await expect(viewerImage(page)).toHaveAccessibleName(CAPTIONS[1])

    await page.keyboard.press('+')
    expect(await transformOf(page)).toBe('translate(0px, 0px) scale(2)')

    await page.keyboard.press('ArrowRight')
    // 100 px vers la gauche, ou jusqu'au bord de l'image : l'image carrée, à ×2, dépasse la zone de
    // 44,5 px de chaque côté au bureau (1 369 px pour 1 280), de 200 px sur téléphone.
    const pan = Math.min(100, (await boundsAt(page, 2)).x)
    expect(await transformOf(page)).toBe(`translate(${-pan}px, 0px) scale(2)`)
    await expect(viewerCounter(page)).toHaveText('2 / 3')

    await page.keyboard.press('Escape')
    await expect(viewer(page)).toHaveCount(0)
    await expect(galleryCounter(page)).toHaveText('2 / 3')
    await expect(expandButton(page)).toBeFocused()
  })

  test('la fenêtre redimensionnée ramène la vue dans ses nouvelles bornes', async ({ page }) => {
    await openViewer(page)
    /** La borne de la translation horizontale à ×2. */
    const bound = async () => (await boundsAt(page, 2)).x
    await page.keyboard.press('+')
    for (const key of ['ArrowRight', 'ArrowRight', 'ArrowRight']) await page.keyboard.press(key)
    expect(await transformOf(page)).toBe(`translate(${-(await bound())}px, 0px) scale(2)`)

    // Moins haute, la zone rétrécit l'image : son débord diminue, et la vue le suit.
    await page.setViewportSize({ width: page.viewportSize()!.width, height: 400 })

    const shrunk = `translate(${-(await bound())}px, 0px) scale(2)`
    await expect.poll(() => transformOf(page)).toBe(shrunk)
  })

  test('← à ×1 change d’image en boucle ; ↑ et ↓ ne font rien', async ({ page }) => {
    await openViewer(page)

    await page.keyboard.press('ArrowLeft')
    await expect(viewerCounter(page)).toHaveText('3 / 3')

    await page.keyboard.press('ArrowUp')
    await page.keyboard.press('ArrowDown')
    await expect(viewerCounter(page)).toHaveText('3 / 3')
    expect(await transformOf(page)).toBe(FIT)
  })

  test('les flèches à l’écran changent toujours d’image, en boucle, et remettent ×1', async ({
    page,
  }) => {
    await openViewer(page)
    await page.keyboard.press('+')

    await viewerButton(page, 'Image précédente').click()

    await expect(viewerCounter(page)).toHaveText('3 / 3')
    expect(await transformOf(page)).toBe(FIT)

    await viewerButton(page, 'Image suivante').click()
    await expect(viewerCounter(page)).toHaveText('1 / 3')
  })

  test('+ zoome d’une unité jusqu’à ×4, puis reste sans effet', async ({ page }) => {
    await openViewer(page)

    for (const scale of [2, 3, 4, 4]) {
      await page.keyboard.press('+')
      expect(await transformOf(page)).toBe(`translate(0px, 0px) scale(${scale})`)
    }
  })

  test('− dézoome d’une unité jusqu’à ×1, puis reste sans effet', async ({ page }) => {
    await openViewer(page)
    for (const key of ['+', '+', '+']) await page.keyboard.press(key)

    for (const scale of [3, 2, 1, 1]) {
      await page.keyboard.press('-')
      expect(await transformOf(page)).toBe(`translate(0px, 0px) scale(${scale})`)
    }
  })

  test('aucun bouton de zoom (décision 8) : la fermeture et les flèches, qu’aucun zoom ne désactive', async ({
    page,
  }) => {
    await openViewer(page)
    /** Les contrôles de la couche, seuls éléments qu'un attribut `disabled` désactive. */
    const controls = () =>
      viewer(page)
        .locator('button, input, select, textarea, fieldset')
        .evaluateAll((elements) =>
          elements.map((element) => [element.getAttribute('aria-label'), element.matches(':disabled')]),
        )

    for (const scale of [1, 2, 3, 4]) {
      if (scale > 1) await page.keyboard.press('+')
      expect(await transformOf(page)).toBe(`translate(0px, 0px) scale(${scale})`)
      expect(await controls()).toEqual([
        ['Fermer l’image', false],
        ['Image précédente', false],
        ['Image suivante', false],
      ])
    }
  })

  for (const modifier of ['Control', 'Alt', 'Meta']) {
    test(`${modifier} laisse +, − et les flèches au navigateur, à ×1 comme zoomé`, async ({
      page,
    }) => {
      await openViewer(page)

      for (const key of ['+', '-', 'ArrowRight']) await page.keyboard.press(`${modifier}+${key}`)
      await expect(viewerCounter(page)).toHaveText('1 / 3')
      expect(await transformOf(page)).toBe(FIT)

      await page.keyboard.press('+')
      for (const key of ['+', '-', 'ArrowDown']) await page.keyboard.press(`${modifier}+${key}`)
      expect(await transformOf(page)).toBe('translate(0px, 0px) scale(2)')
    })
  }

  test('Maj zoome avec + et − — le + s’obtient avec Maj sur certains claviers —, et laisse les flèches au navigateur', async ({
    page,
  }) => {
    await openViewer(page)

    await page.keyboard.press('Shift+ArrowRight')
    await expect(viewerCounter(page)).toHaveText('1 / 3')

    await page.keyboard.press('Shift++')
    expect(await transformOf(page)).toBe('translate(0px, 0px) scale(2)')

    await page.keyboard.press('Shift+ArrowDown')
    expect(await transformOf(page)).toBe('translate(0px, 0px) scale(2)')

    await page.keyboard.press('Shift+-')
    expect(await transformOf(page)).toBe(FIT)
  })
})

test.describe('les fermetures', () => {
  test.beforeEach(async ({ page }) => {
    await arriveAt(page, { gallery: THREE_IMAGES })
  })

  test('Échap ferme la couche seule ; un second Échap ferme la fiche', async ({ page }) => {
    await openViewer(page)

    await page.keyboard.press('Escape')

    await expect(viewer(page)).toHaveCount(0)
    await expect(panel(page)).toHaveAccessibleName('Fiche')
    await expect(page).toHaveURL('/projets/fiche')

    await page.keyboard.press('Escape')
    await expectClosed(page)
  })

  test('« Fermer l’image » ferme la couche seule et rend le focus à « Agrandir l’image »', async ({
    page,
  }) => {
    await openViewer(page)

    await closeImageButton(page).click()

    await expect(viewer(page)).toHaveCount(0)
    await expect(panel(page)).toHaveAccessibleName('Fiche')
    await expect(expandButton(page)).toBeFocused()
  })

  test('un clic sur le fond ferme la couche et rend le focus à « Agrandir l’image » ; un clic sur l’image la laisse ouverte', async ({
    page,
  }) => {
    await openViewer(page)
    const image = (await viewerImage(page).boundingBox())!
    // Hors de l'image, des flèches et de « Fermer l'image » : le coin haut gauche de la zone.
    const background = { x: 60, y: 60 }
    expect(background.x < image.x || background.y < image.y).toBe(true)

    await viewerImage(page).click()
    await expect(viewer(page)).toHaveAttribute('data-state', 'open')

    await outlastOpening(page)
    await page.mouse.click(background.x, background.y)
    await expect(viewer(page)).toHaveCount(0)
    await expect(panel(page)).toHaveAccessibleName('Fiche')
    await expect(expandButton(page)).toBeFocused()
  })

  test('rouverte, la couche repart de ×1 sur l’image courante', async ({ page }) => {
    await openViewer(page)
    await viewerButton(page, 'Image suivante').click()
    await page.keyboard.press('+')
    await page.keyboard.press('Escape')
    await expect(viewer(page)).toHaveCount(0)

    await openViewer(page)

    await expect(viewerCounter(page)).toHaveText('2 / 3')
    expect(await transformOf(page)).toBe(FIT)
  })
})

test.describe('le retour du navigateur, couche ouverte', () => {
  /** La fiche ouverte depuis sa carte, qui a son entrée d'historique, puis sa couche. */
  test.beforeEach(async ({ page }) => {
    await openFromTable(page, [ficheProject({ gallery: THREE_IMAGES })])
    await openViewer(page)
  })

  test('ferme la couche avec la fiche, d’un seul pas : l’adresse est / et la couche déjà sortie, sur l’image vue', async ({
    page,
  }) => {
    await page.keyboard.press('ArrowLeft')
    await expect(viewerCounter(page)).toHaveText('3 / 3')
    await freezeAnimations(page)

    await page.goBack()

    await expect(page).toHaveURL('/')
    const leaving = page.locator('.image-viewer')
    await expect(leaving).toHaveAttribute('data-state', 'closed')
    // La galerie revient à sa première image, la photo de la carte (spec §4.6) ; la couche qui
    // s'efface garde la sienne.
    await expect(leaving.locator('.project-gallery-counter')).toHaveText('3 / 3')
  })

  test('ne laisse ni fiche ni couche, le focus rendu à la carte', async ({ page }) => {
    await page.goBack()

    await expect(viewer(page)).toHaveCount(0)
    await expectClosed(page)
    await expect(cards(page).first()).toBeFocused()
  })
})

test('une image seule : ni flèches ni compteur, le zoom disponible', async ({ page }) => {
  await arriveAt(page, { gallery: ONE_IMAGE })
  await openViewer(page)

  await expect(viewerButton(page, 'Image précédente')).toHaveCount(0)
  await expect(viewerButton(page, 'Image suivante')).toHaveCount(0)
  await expect(viewerCounter(page)).toHaveCount(0)
  await expect(viewerCaption(page)).toHaveText(CAPTIONS[0])

  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('+')

  expect(await transformOf(page)).toBe('translate(0px, 0px) scale(2)')
})

test('un toucher sur l’image ouvre la couche', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'tactile')
  await arriveAt(page, { gallery: THREE_IMAGES })

  await gallery(page).getByRole('img').tap()

  await expect(viewer(page)).toBeVisible()
})

for (const mode of ['light', 'dark'] as const) {
  test(`la couche prend la palette sombre, mode ${mode} forcé, sans violation d’axe`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: mode })
    await arriveAt(page, { gallery: THREE_IMAGES })
    await page.evaluate((forced) => (document.documentElement.dataset.theme = forced), mode)
    await openViewer(page)
    // Les valeurs sombres de §2.1, résolues comme le navigateur les sérialise.
    const [bg, ink, ink2] = await resolveAll(page, [
      ['color', '#1C1A17'],
      ['color', '#EDE6DA'],
      ['color', '#A69C8F'],
    ])

    expect(bg).toBe('rgb(28, 26, 23)')
    await expect(viewer(page)).toHaveCSS('background-color', bg)
    await expect(viewer(page)).toHaveCSS('color-scheme', 'dark')
    await expect(viewerCaption(page)).toHaveCSS('color', ink2)
    await expect(viewerCounter(page)).toHaveCSS('color', ink2)
    await expect(closeImageButton(page)).toHaveCSS('color', ink2)
    await expect(viewerButton(page, 'Image suivante')).toHaveCSS('color', ink)
    await expectNoViolations(page)
  })
}

test.describe('« Agrandir l’image » et la loupe', () => {
  for (const [count, images] of [
    ['trois images', THREE_IMAGES],
    ['une image', ONE_IMAGE],
  ] as const) {
    test(`à ${count} : 36 px, rond, à 8 px du coin bas droit du cadre, --paper à 88 %, --ink`, async ({
      page,
    }) => {
      await arriveAt(page, { gallery: [...images] })
      const frame = (await page.locator('.project-gallery-frame').boundingBox())!
      const [paper, ink] = await resolveAll(page, [
        ['background-color', 'color-mix(in srgb, var(--paper) 88%, transparent)'],
        ['color', 'var(--ink)'],
      ])

      expect(await expandButton(page).boundingBox()).toEqual({
        x: frame.x + frame.width - 44,
        y: frame.y + frame.height - 44,
        width: 36,
        height: 36,
      })
      await expect(expandButton(page)).toHaveCSS('border-radius', '50%')
      await expect(expandButton(page)).toHaveCSS('background-color', paper)
      await expect(expandButton(page)).toHaveCSS('color', ink)
      await expect(expandButton(page).locator('svg')).toHaveAttribute('aria-hidden', 'true')
      expect(await expandButton(page).locator('svg').boundingBox()).toMatchObject({
        width: 18,
        height: 18,
      })
    })
  }

  test('le curseur est une loupe sur l’image de la galerie', async ({ page, isMobile }) => {
    test.skip(isMobile, 'pas de curseur au doigt')
    await arriveAt(page, { gallery: THREE_IMAGES })

    await expect(gallery(page).getByRole('img')).toHaveCSS('cursor', 'zoom-in')
  })
})

test('le zoom glisse en 240 ms, par la courbe --ease-out ; changer d’image ne glisse pas', async ({
  page,
}) => {
  await arriveAt(page, { gallery: THREE_IMAGES })
  const [curve] = await resolveAll(page, [['transition-timing-function', 'var(--ease-out)']])
  await openViewer(page)
  const transitions = await watchTransitions(page)

  await page.keyboard.press('+')
  await settle(page)

  expect(await transitions('image-viewer-image')).toEqual([
    { layer: 'image-viewer-image', property: 'transform', duration: '0.24s' },
  ])
  await expect(viewerImage(page)).toHaveCSS('transition-timing-function', curve)

  await viewerButton(page, 'Image suivante').click()
  await settle(page)

  expect(await transitions('image-viewer-image')).toHaveLength(1)
  expect(await transformOf(page)).toBe(FIT)
})

test('sous la CSP de production, la couche s’ouvre, zoome et se ferme sans violation', async ({
  page,
}) => {
  const violations = watchCspViolations(page)
  await serveUnderCsp(page)
  await openFromTable(page, [ficheProject({ gallery: THREE_IMAGES })])

  await openViewer(page)
  await page.keyboard.press('+')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Escape')

  await expect(viewer(page)).toHaveCount(0)
  expect(violations).toEqual([])
})

test('ouverture et fermeture par fondu de 240 ms, par la courbe --ease-out', async ({ page }) => {
  await arriveAt(page, { gallery: THREE_IMAGES })
  const [curve] = await resolveAll(page, [['animation-timing-function', 'var(--ease-out)']])
  const animations = await watchAnimations(page)

  await openViewer(page)
  await page.keyboard.press('Escape')
  await expect(viewer(page)).toHaveCount(0)

  expect(await animations()).toEqual([
    { name: 'project-in', duration: '0.24s', curve },
    { name: 'project-out', duration: '0.24s', curve },
  ])
})
