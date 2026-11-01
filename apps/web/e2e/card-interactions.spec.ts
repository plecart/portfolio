/**
 * Les interactions d'une carte (spec §1.3, §1.7, §2.7, §3.1, §4.1, §6.1-6.3 ; issue #168), sur la
 * page servie, l'API et les fichiers interceptés par les gestes d'`api.ts`.
 */
import { AxeBuilder } from '@axe-core/playwright'
import type { Locator, Page } from '@playwright/test'
import { expect, holdProjects, serving, test } from './api.ts'
import { resolveAll } from './css.ts'
import { buildProject, FILES_ORIGIN, PROJECT_SETS } from './projects.ts'
import { scrollThrough } from './scroll.ts'
import {
  cards,
  COLUMN_VIEWPORT,
  enterCards,
  expectPlacement,
  openTable,
  serveUnderCsp,
  settle,
} from './table.ts'

/** Les couches d'une carte qui bougent, et son bandeau de résumé. */
const entry = (card: Locator) => card.locator('.card-entry')
const pose = (card: Locator) => card.locator('.card-pose')
const face = (card: Locator) => card.locator('.card-face')
const summary = (card: Locator) => card.locator('.card-summary')

/** Le soulèvement (−6 px, ×1,02) et la pression (×0,985) de spec §2.7, en transformation calculée. */
const LIFTED = 'matrix(1.02, 0, 0, 1.02, 0, -6)'
const PRESSED = 'matrix(0.985, 0, 0, 0.985, 0, 0)'

/** Focalise une carte au clavier : une touche d'abord, pour que `:focus-visible` s'applique. */
async function focusByKeyboard(card: Locator) {
  await card.page().keyboard.press('Tab')
  await card.focus()
}

/** Attend l'ombre soulevée et le bandeau, apparus ou effacés. */
async function expectRevealed(card: Locator, revealed: boolean) {
  const opacity = revealed ? '1' : '0'
  await expect(face(card)).toHaveCSS('opacity', opacity, { pseudo: 'after' })
  await expect(summary(card)).toHaveCSS('opacity', opacity)
}

/** Les deux gestes d'une intention, sur un appareil à survol (spec §4.1). */
const INTENTS: [string, (card: Locator) => Promise<void>][] = [
  ['au survol', (card) => card.hover()],
  ['au focus clavier', focusByKeyboard],
]

/** Une carte aux trois technologies et aux deux états : sous 600 px, ses rubans vont à la ligne. */
const FULL_CARD = buildProject({
  slug: 'pleine',
  status: 'ongoing',
  finished_on: null,
  demo_url: 'https://demo.test/pleine',
  technologies: (['language', 'framework', 'infrastructure'] as const).map((kind) => ({
    name: kind,
    kind,
    icon: `${FILES_ORIGIN}/icones/${kind}.svg`,
  })),
})

/** Deux cartes sur une rangée : la carte pleine, en cours donc en tête, et sa voisine. */
const TWO_CARDS = [FULL_CARD, buildProject({ slug: 'voisine' })]

test('à 15 % de sa surface dans l’écran, une carte entre : 8 px de montée et un fondu de 240 ms', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  const box = (await card.boundingBox())!
  const { height } = page.viewportSize()!
  const [duration, curve] = await resolveAll(page, [
    ['transition-duration', 'var(--dur)'],
    ['transition-timing-function', 'var(--ease-out)'],
  ])

  await expect(entry(card)).toHaveCSS('opacity', '0')
  await expect(entry(card)).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 8)')
  await expect(entry(card)).toHaveCSS('transition-property', 'opacity, transform')
  await expect(entry(card)).toHaveCSS('transition-duration', `${duration}, ${duration}`)
  await expect(entry(card)).toHaveCSS('transition-timing-function', `${curve}, ${curve}`)

  await scrollThrough(page, box.y + box.height * 0.1 - height)
  await expect(card).not.toHaveAttribute('data-entered')

  await scrollThrough(page, box.y + box.height * 0.2 - height)
  await expect(entry(card)).toHaveCSS('opacity', '1')
  await expect(entry(card)).toHaveCSS('transform', 'none')
})

test('une carte n’entre qu’une fois : la revoir ne rejoue rien', async ({ page }) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  await enterCards(page)
  const replays = await page.evaluateHandle(() => {
    const seen: string[] = []
    addEventListener('transitionrun', ({ target, propertyName }) => {
      if ((target as Element).matches('.card-entry')) seen.push(propertyName)
    })
    return seen
  })
  const bottom = await page.evaluate(() => document.documentElement.scrollHeight)

  await scrollThrough(page, bottom, 0, bottom)

  expect(await replays.jsonValue()).toEqual([])
})

test('toute la table n’a qu’un observateur, qui lâche chaque carte entrée', async ({ page }) => {
  await page.addInitScript(() => {
    const calls = { created: 0, unobserved: 0 }
    Object.assign(window, { observerCalls: calls })
    const Native = window.IntersectionObserver
    window.IntersectionObserver = class extends Native {
      constructor(...args: ConstructorParameters<typeof Native>) {
        super(...args)
        calls.created += 1
      }

      unobserve(target: Element) {
        calls.unobserved += 1
        super.unobserve(target)
      }
    }
  })
  await openTable(page, PROJECT_SETS.threeWithShowcase)
  await expect(page.locator('.card[data-entered]')).toHaveCount(3)

  const calls = await page.evaluate(() => Reflect.get(window, 'observerCalls'))

  expect(calls).toEqual({ created: 1, unobserved: 3 })
})

test('le retard vaut 40 ms par colonne mesurée, et se relit au redimensionnement', async ({ page }) => {
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const columns = () =>
    cards(page).evaluateAll((links) =>
      links.map((link) => {
        const { transitionDelay } = getComputedStyle(link.querySelector('.card-entry')!)
        return Math.round(parseFloat(transitionDelay) * 1000) / 40
      }),
    )

  expect(await columns()).toEqual([0, 2, 3, 2, 3, 0, 1, 2, 3, 0, 1, 2])

  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 1000 })
  await expect.poll(columns).toEqual([0, 2, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2])

  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 400 })
  await expect.poll(columns).toEqual([0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
})

test('en mouvement réduit, une carte entre par un fondu de 150 ms, sans montée, retard conservé', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  const [duration] = await resolveAll(page, [['transition-duration', 'var(--dur-fast)']])

  await expect(entry(card)).toHaveCSS('opacity', '0')
  await expect(entry(card)).toHaveCSS('transform', 'none')
  await expect(entry(card)).toHaveCSS('transition-property', 'opacity')
  await expect(entry(card)).toHaveCSS('transition-duration', duration)
  // La dernière des douze cartes, en troisième colonne à 1280 px.
  await expect(entry(card)).toHaveCSS('transition-delay', '0.08s')

  await card.scrollIntoViewIfNeeded()
  await expect(entry(card)).toHaveCSS('opacity', '1')
})

test('les cartes remplacent les cadres en entrant, sans changer la forme des liens de l’auteur', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'largeurs de bureau : le projet desktop les porte')
  // À 1200 px, 78 px de marge pour une garde de 76 : une mesure qui suivrait l'entrée basculerait.
  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 1200 })
  const release = await holdProjects(page)
  await page.goto('/')
  await expectPlacement(page, 'column')
  const watched = await page.evaluateHandle(() => {
    const seen = { forms: 0, moved: [] as string[] }
    new MutationObserver(() => (seen.forms += 1)).observe(document.querySelector('footer')!, {
      attributeFilter: ['data-docked'],
    })
    addEventListener('transitionrun', ({ target }) => seen.moved.push((target as Element).className))
    return seen
  })

  await release(serving(PROJECT_SETS.twelveWithShowcase))
  await expect(page.locator('.card[data-entered]')).not.toHaveCount(0)
  await settle(page)

  const { forms, moved } = await watched.jsonValue()
  expect(forms).toBe(0)
  await expectPlacement(page, 'column')
  // Rien ne bouge que la couche d'entrée : ni la cellule, que les liens mesurent, ni ses voisines.
  expect(moved.length).toBeGreaterThan(0)
  expect([...new Set(moved)]).toEqual(['card-entry'])
})

for (const width of [1280, 400]) {
  for (const [gesture, act] of INTENTS) {
    test(`${gesture} à ${width} px, la carte se redresse, se soulève, l'ombre s'élargit, le bandeau se révèle`, async ({
      page,
      isMobile,
    }) => {
      test.skip(isMobile, 'appareil sans survol : la révélation au toucher a ses scénarios')
      await page.setViewportSize({ ...COLUMN_VIEWPORT, width })
      await openTable(page, PROJECT_SETS.threeWithShowcase)
      await settle(page)
      const card = cards(page).first()

      await expectRevealed(card, false)
      await expect(summary(card)).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 6)')

      await act(card)

      await expect(pose(card)).toHaveCSS('transform', 'none')
      await expect(face(card)).toHaveCSS('transform', LIFTED)
      await expectRevealed(card, true)
      await expect(summary(card)).toHaveCSS('transform', 'none')
    })
  }
}

test('les mouvements d’une carte suivent le tableau de spec §2.7', async ({ page }) => {
  await openTable(page, PROJECT_SETS.one)
  const card = cards(page)
  const [fast, base, out, spring] = await resolveAll(page, [
    ['transition-duration', 'var(--dur-fast)'],
    ['transition-duration', 'var(--dur)'],
    ['transition-timing-function', 'var(--ease-out)'],
    ['transition-timing-function', 'var(--ease-spring)'],
  ])
  const expectMotion = async (layer: Locator, name: string, duration: string, curve: string) => {
    await expect(layer).toHaveCSS('transition-property', name)
    await expect(layer).toHaveCSS('transition-duration', duration)
    await expect(layer).toHaveCSS('transition-timing-function', curve)
  }

  await expectMotion(pose(card), 'transform', base, out)
  await expectMotion(face(card), 'transform', base, spring)
  await expectMotion(summary(card), 'opacity, transform', `${fast}, ${base}`, `${out}, ${out}`)
  await expect(face(card)).toHaveCSS('transition-property', 'opacity', { pseudo: 'after' })
  await expect(face(card)).toHaveCSS('transition-duration', base, { pseudo: 'after' })
  await expect(face(card)).toHaveCSS('transition-timing-function', out, { pseudo: 'after' })
})

test('le bandeau de résumé : absolu en bas de la photo, `--paper` à 94 %, 13 px, `--ink` (spec §4.1)', async ({
  page,
}) => {
  await openTable(page, [buildProject({ summary: 'Un résumé.' })])
  const card = cards(page)
  const [paper, ink] = await resolveAll(page, [
    ['background-color', 'color-mix(in srgb, var(--paper) 94%, transparent)'],
    ['color', 'var(--ink)'],
  ])

  await expect(summary(card)).toHaveText('Un résumé.')
  await expect(summary(card)).toHaveAttribute('aria-hidden', 'true')
  await expect(summary(card)).toHaveCSS('background-color', paper)
  await expect(summary(card)).toHaveCSS('color', ink)
  await expect(summary(card)).toHaveCSS('font-size', '13px')
  await expect(summary(card)).toHaveCSS('padding', '12px')
  const gap = await summary(card).evaluate(
    (band) =>
      band.parentElement!.getBoundingClientRect().bottom - band.getBoundingClientRect().bottom,
  )
  // Caché, le bandeau est 6 px plus bas que sa place.
  expect(Math.round(gap)).toBe(-6)
})

/** Le canal vert d'une capture PNG, colonne par colonne, décodé par la page. */
const greenColumns = (page: Page, png: Buffer) =>
  page.evaluate(async (url) => {
    const bitmap = await createImageBitmap(await (await fetch(url)).blob())
    const { width, height } = bitmap
    const context = new OffscreenCanvas(width, height).getContext('2d')!
    context.drawImage(bitmap, 0, 0)
    const { data } = context.getImageData(0, 0, width, height)
    return Array.from({ length: width }, (_, x) =>
      Array.from({ length: height }, (_, y) => data[4 * (y * width + x) + 1]),
    )
  }, `data:image/png;base64,${png.toString('base64')}`)

test('à mi-transition, aucun filet de l’image ne longe le bandeau', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans survol : le filet se mesure sous la carte inclinée')
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.threeWithoutShowcase)
  await enterCards(page)
  const card = cards(page).first()
  const { x, y, width, height } = (await card.boundingBox())!

  await page.mouse.move(x + width / 2, y + height * 0.8)
  await expect.poll(() => summary(card).evaluate((band) => band.getAnimations().length)).toBe(2)
  await page.evaluate(() => {
    for (const motion of document.getAnimations()) {
      motion.pause()
      motion.currentTime = 75
    }
  })

  // Une bande à cheval sur le bord bas : du bandeau au papier, rien de plus sombre que les deux.
  const band = (await summary(card).boundingBox())!
  const edge = Math.floor(band.y + band.height)
  const clip = { x: Math.ceil(band.x) + 2, y: edge - 12, width: Math.floor(band.width) - 4, height: 24 }
  const columns = await greenColumns(page, await page.screenshot({ clip }))

  expect(columns[0][0]).toBeLessThan(columns[0].at(-1)!)
  const dips = columns.map((column) => Math.min(column[0], column.at(-1)!) - Math.min(...column))
  expect(Math.max(...dips)).toBeLessThanOrEqual(2)
})

/** Le résumé le plus long de spec §7, 120 caractères, et son voisin : deux cartes simples. */
const LONGEST_SUMMARY = [
  buildProject({
    slug: 'a',
    summary:
      'Une application de suivi des livraisons pour les artisans du bâtiment, avec planning partagé et alertes par messageries.',
  }),
  buildProject({ slug: 'b' }),
]

test('un résumé de 120 caractères tient en sept lignes sur la carte simple mobile (spec §7)', async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, 'la carte simple de 176 px, la plus étroite de spec §7')
  expect(LONGEST_SUMMARY[0].summary).toHaveLength(120)
  await openTable(page, LONGEST_SUMMARY)

  const { text, lineHeight, photo } = await summary(cards(page).first()).evaluate(
    (band: HTMLElement) => ({
      text: band.offsetHeight - 2 * 12,
      lineHeight: parseFloat(getComputedStyle(band).lineHeight),
      photo: band.parentElement!.offsetHeight,
    }),
  )

  expect(Math.round(text / lineHeight)).toBeLessThanOrEqual(7)
  expect(text + 2 * 12).toBeLessThanOrEqual(photo)
})

for (const [width, maxLines] of [
  [320, 4],
  [340, 5],
  [380, 6],
] as const) {
  test(`à ${width} px, le bandeau s'arrête à ${maxLines} lignes : le haut du texte reste sous le post-it`, async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'des cartes simples plus étroites que celle de spec §7')
    await page.setViewportSize({ ...COLUMN_VIEWPORT, width })
    await openTable(page, LONGEST_SUMMARY)

    const band = await summary(cards(page).first()).evaluate((element: HTMLElement) => {
      const { lineHeight, paddingBottom, paddingTop } = getComputedStyle(element)
      const inset = parseFloat(paddingTop) + parseFloat(paddingBottom)
      const postit = element.closest('.card-tilt')!.querySelector<HTMLElement>('.card-postit')!
      return {
        textTop: element.offsetTop + parseFloat(paddingTop),
        postitBottom: postit.offsetTop + postit.offsetHeight,
        lines: Math.round((element.offsetHeight - inset) / parseFloat(lineHeight)),
        overflow: element.scrollHeight - element.clientHeight,
      }
    })

    expect(band.textTop).toBeGreaterThanOrEqual(band.postitBottom)
    expect(band.lines).toBe(maxLines)
    // Les lignes cachées ne reparaissent pas dans la marge basse du bandeau.
    expect(band.overflow).toBe(0)
  })
}

test('focus clavier : un anneau de 2 px `--accent` à 4 px de la face, aucun sur la cellule', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.threeWithShowcase)
  const card = cards(page).first()
  const [accent] = await resolveAll(page, [['outline-color', 'var(--accent)']])

  await focusByKeyboard(card)

  await expect(card).toHaveCSS('outline-style', 'none')
  await expect(face(card)).toHaveCSS('outline-style', 'solid')
  await expect(face(card)).toHaveCSS('outline-width', '2px')
  await expect(face(card)).toHaveCSS('outline-offset', '4px')
  await expect(face(card)).toHaveCSS('outline-color', accent)
})

/** Le nombre d'écouteurs de `pointerdown` sur le document, lu par le débogueur du navigateur. */
async function documentPointerListeners(page: Page): Promise<number> {
  const client = await page.context().newCDPSession(page)
  const { result } = await client.send('Runtime.evaluate', { expression: 'document' })
  const { listeners } = await client.send('DOMDebugger.getEventListeners', {
    objectId: result.objectId!,
  })
  await client.detach()
  return listeners.filter(({ type }) => type === 'pointerdown').length
}

test.describe('au toucher', () => {
  test.skip(({ isMobile }) => !isMobile, 'un appareil sans survol : le projet mobile')

  /** « Ouvrir », visible sur la page. */
  const open = (page: Page) => page.getByText('Ouvrir').filter({ visible: true })

  for (const width of [400, 1280]) {
    test(`à ${width} px, premier toucher : redressement, ombre et bandeau, sans soulèvement ; second : le lien`, async ({
      page,
    }) => {
      await page.setViewportSize({ ...COLUMN_VIEWPORT, width })
      await openTable(page, TWO_CARDS)
      await settle(page)
      const card = cards(page).first()

      await card.tap()

      await expect(page).toHaveURL('/')
      await expect(pose(card)).toHaveCSS('transform', 'none')
      await expectRevealed(card, true)
      await expect(face(card)).toHaveCSS('transform', 'none')
      await expect(open(page)).toHaveCount(1)
      await expect(card.locator('.card-ribbons').first()).toBeHidden()

      await card.tap()

      await expect(page).toHaveURL('/projets/pleine')
    })
  }

  test('« Ouvrir » suit le lien : il ne remplace les rubans que pendant la révélation', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    await settle(page)
    const card = cards(page).first()
    await expect(open(page)).toHaveCount(0)

    await card.tap()
    await open(page).tap()

    await expect(page).toHaveURL('/projets/pleine')
  })

  test('« Ouvrir » : 30 px de haut, marge 0 12 px, bordure 1 px `--ink`, `--paper`, rayon 6 px, 13 / 600', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    await settle(page)
    await cards(page).first().tap()
    const [ink, paper] = await resolveAll(page, [
      ['border-top-color', 'var(--ink)'],
      ['background-color', 'var(--paper)'],
    ])

    const button = open(page)
    await expect(button).toHaveCSS('height', '30px')
    await expect(button).toHaveCSS('padding', '0px 12px')
    await expect(button).toHaveCSS('border-top-width', '1px')
    await expect(button).toHaveCSS('border-top-color', ink)
    await expect(button).toHaveCSS('background-color', paper)
    await expect(button).toHaveCSS('border-top-left-radius', '6px')
    await expect(button).toHaveCSS('font-size', '13px')
    await expect(button).toHaveCSS('font-weight', '600')
  })

  for (const [band, project] of [
    ['d’une ligne', buildProject({ slug: 'pleine' })],
    ['de deux lignes', FULL_CARD],
  ] as const) {
    test(`la hauteur de la carte ne change pas quand « Ouvrir » remplace une bande ${band}`, async ({
      page,
    }) => {
      await openTable(page, [buildProject({ slug: 'voisine' }), project])
      await settle(page)
      const card = cards(page).first()
      const height = () => face(card).evaluate((element: HTMLElement) => element.offsetHeight)
      const before = await height()

      await card.tap()
      await expect(open(page)).toHaveCount(1)

      expect(await height()).toBe(before)
    })
  }

  test('une seule carte révélée : toucher une autre carte déplace la révélation', async ({ page }) => {
    await openTable(page, TWO_CARDS)
    await settle(page)
    const [first, second] = [cards(page).first(), cards(page).last()]

    await first.tap()
    await expectRevealed(first, true)
    await second.tap()

    await expectRevealed(first, false)
    await expectRevealed(second, true)
    await expect(open(page)).toHaveCount(1)
    await expect(page).toHaveURL('/')
  })

  test('toucher hors des cartes referme, et l’écoute du document cesse avec la révélation', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    await settle(page)
    const card = cards(page).first()
    const box = (await card.boundingBox())!
    expect(await documentPointerListeners(page)).toBe(0)

    await card.tap()
    await expect(open(page)).toHaveCount(1)
    expect(await documentPointerListeners(page)).toBe(1)

    // Loin sous la table : le navigateur ajuste vers un lien proche le toucher qui le frôle.
    await page.touchscreen.tap(box.x + box.width, box.y + box.height + 100)

    await expect(open(page)).toHaveCount(0)
    await expectRevealed(card, false)
    await expect.poll(() => documentPointerListeners(page)).toBe(0)
    await expect(page).toHaveURL('/')
  })

  test('un `pointerdown` seul referme : iOS n’émet aucun `click` hors d’un élément cliquable', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    await settle(page)
    await cards(page).first().tap()
    await expect(open(page)).toHaveCount(1)

    await page.evaluate(() =>
      document.querySelector('main')!.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })),
    )

    await expect(open(page)).toHaveCount(0)
  })

  test('Entrée ouvre directement la carte focalisée, sans révélation (spec §6.2)', async ({ page }) => {
    await openTable(page, TWO_CARDS)
    await settle(page)
    await cards(page).first().focus()

    await page.keyboard.press('Enter')

    await expect(page).toHaveURL('/projets/pleine')
  })

  test('un toucher enfonce la carte en 80 ms (spec §1.6, §4.1)', async ({ page }) => {
    await openTable(page, TWO_CARDS)
    await settle(page)
    const [press] = await resolveAll(page, [['transition-duration', 'var(--dur-press)']])
    // Un contact tenu par le protocole ne rend jamais `:active` : Chromium ne le pose qu'à la
    // relève, le temps du toucher (mesuré le 2026-11-01). On lit donc la transition qui part.
    const pressed = await page.evaluateHandle(() => {
      const durations: string[] = []
      addEventListener('transitionrun', ({ target, propertyName }) => {
        const layer = target as Element
        if (layer.matches('.card-face') && propertyName === 'transform') {
          durations.push(getComputedStyle(layer).transitionDuration)
        }
      })
      return durations
    })

    await cards(page).first().tap()

    await expect.poll(async () => (await pressed.jsonValue())[0]).toBe(press)
  })
})

test('sur un appareil à survol, un clic ouvre d’emblée', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans survol : le premier toucher révèle')
  await openTable(page, TWO_CARDS)
  await settle(page)

  await cards(page).first().click()

  await expect(page).toHaveURL('/projets/pleine')
})

test('pressée au pointeur, la carte s’enfonce à ×0,985 en 80 ms (spec §4.1)', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans pointeur : le toucher a son scénario')
  await openTable(page, PROJECT_SETS.one)
  await settle(page)
  const card = cards(page)
  const [press] = await resolveAll(page, [['transition-duration', 'var(--dur-press)']])
  await card.hover()

  await page.mouse.down()

  await expect(face(card)).toHaveCSS('transform', PRESSED)
  await expect(face(card)).toHaveCSS('transition-duration', press)
})

test.describe('en mouvement réduit', () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
  })

  for (const [gesture, act] of INTENTS) {
    test(`${gesture}, ni redressement ni soulèvement : l'ombre et le fondu du bandeau seulement`, async ({
      page,
      isMobile,
    }) => {
      test.skip(isMobile, 'appareil sans survol : la révélation au toucher a son scénario')
      await openTable(page, PROJECT_SETS.one)
      await settle(page)
      const card = cards(page)
      const rest = await pose(card).evaluate((layer) => getComputedStyle(layer).transform)
      await expect(summary(card)).toHaveCSS('transform', 'none')

      await act(card)

      await expectRevealed(card, true)
      await expect(pose(card)).toHaveCSS('transform', rest)
      await expect(face(card)).toHaveCSS('transform', 'none')
    })
  }

  test('au toucher, ni redressement ni soulèvement : l’ombre et le fondu du bandeau seulement', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'un appareil sans survol : le projet mobile')
    await openTable(page, TWO_CARDS)
    await settle(page)
    const card = cards(page).first()
    const rest = await pose(card).evaluate((layer) => getComputedStyle(layer).transform)

    await card.tap()

    await expectRevealed(card, true)
    await expect(pose(card)).toHaveCSS('transform', rest)
  })

  test('pressée, la carte ne s’enfonce pas', async ({ page, isMobile }) => {
    test.skip(isMobile, 'appareil sans pointeur')
    await openTable(page, PROJECT_SETS.one)
    await settle(page)
    const card = cards(page)
    await card.hover()

    await page.mouse.down()

    await expect(face(card)).toHaveCSS('transform', 'none')
  })
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`une carte révélée : aucune violation d'accessibilité — ${colorScheme}`, async ({
    page,
    isMobile,
  }) => {
    await page.emulateMedia({ colorScheme })
    await openTable(page, TWO_CARDS)
    await enterCards(page)
    const card = cards(page).first()

    await (isMobile ? card.tap() : card.hover())
    await expectRevealed(card, true)
    await settle(page)

    const { violations } = await new AxeBuilder({ page }).analyze()
    expect(violations.map((violation) => violation.id)).toEqual([])
  })
}

/** L'inclinaison d'une carte sur chaque axe, au degré, lue sur sa transformation calculée. */
const tiltOf = (card: Locator) =>
  card.locator('.card-tilt').evaluate((layer) => {
    const { m23, m31 } = new DOMMatrix(getComputedStyle(layer).transform)
    return [m23, m31].map((sine) => Math.round((Math.asin(sine) * 180) / Math.PI))
  })

/** La durée des transitions en cours sur la couche d'inclinaison d'une carte, en ms. */
const settling = (card: Locator) =>
  card
    .locator('.card-tilt')
    .evaluate((layer) => layer.getAnimations().map((motion) => motion.effect?.getTiming().duration))

/** Le coin haut droit d'une carte : le point qui l'incline de +6° sur chaque axe. */
async function topRightCorner(card: Locator) {
  const { x, y, width } = (await card.boundingBox())!
  return { x: x + width - 1, y: y + 1 }
}

/** Laisse au navigateur le temps d'une image : ce qu'un geste écrit y est posé. */
const nextFrame = (page: Page) => page.evaluate(() => new Promise(requestAnimationFrame))

for (const [size, index] of [
  ['vitrine', 0],
  ['simple', 1],
] as const) {
  test(`au pointeur, une carte ${size} s'incline : +6° au coin haut droit, 0 au centre, retour en 240 ms`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, 'appareil sans pointeur fin : aucune inclinaison')
    await page.setViewportSize(COLUMN_VIEWPORT)
    await openTable(page, PROJECT_SETS.threeWithShowcase)
    await settle(page)
    const card = cards(page).nth(index)
    const { x, y, width, height } = (await card.boundingBox())!

    const corner = await topRightCorner(card)
    await page.mouse.move(corner.x, corner.y)
    await expect.poll(() => tiltOf(card)).toEqual([6, 6])

    await page.mouse.move(x + width / 2, y + height / 2)
    await expect.poll(() => tiltOf(card)).toEqual([0, 0])

    // Jamais d'inertie : la couche suit le pointeur sans transition.
    await page.mouse.move(x + 1, y + height - 1)
    await expect.poll(() => tiltOf(card)).toEqual([-6, -6])
    expect(await settling(card)).toEqual([])

    await page.mouse.move(0, 0)
    await expect.poll(() => settling(card)).toEqual([240])
    await expect.poll(() => tiltOf(card)).toEqual([0, 0])
  })
}

test('la perspective de 900 px atteint la couche inclinée : elle est sur son parent direct', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.one)

  const perspective = await cards(page)
    .locator('.card-tilt')
    .evaluate((layer) => getComputedStyle(layer.parentElement!).perspective)

  expect(perspective).toBe('900px')
})

test('aucune inclinaison sur un appareil tactile, ni au doigt ni à la souris', async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, 'un appareil sans survol : le projet mobile')
  await openTable(page, PROJECT_SETS.one)
  await settle(page)
  const card = cards(page)
  const { x, y } = await topRightCorner(card)

  await page.touchscreen.tap(x, y)
  await nextFrame(page)
  expect(await tiltOf(card)).toEqual([0, 0])

  await page.mouse.move(x, y)
  await nextFrame(page)
  expect(await tiltOf(card)).toEqual([0, 0])
})

test('aucune inclinaison en mouvement réduit', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans pointeur fin : aucune inclinaison')
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await openTable(page, PROJECT_SETS.one)
  await settle(page)
  const card = cards(page)
  const { x, y } = await topRightCorner(card)

  await page.mouse.move(x, y)
  await nextFrame(page)

  expect(await tiltOf(card)).toEqual([0, 0])
})

test('un autre pointeur que la souris n’incline rien, sur un appareil à souris', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'un appareil à pointeur fin : le projet desktop')
  await openTable(page, PROJECT_SETS.one)
  await settle(page)
  const card = cards(page)
  const client = await page.context().newCDPSession(page)
  const overs = await page.evaluateHandle(() => {
    const pointerTypes: string[] = []
    addEventListener('pointerover', ({ pointerType }) => pointerTypes.push(pointerType))
    return pointerTypes
  })

  // Un stylet : l'émulation tactile de Chromium change aussi `hover` et `pointer`, pas lui.
  await client.send('Input.dispatchMouseEvent', {
    type: 'mouseMoved',
    pointerType: 'pen',
    ...(await topRightCorner(card)),
  })
  // Sous lui, Chromium rejoue un survol de type `mouse`, sans `pointermove` : on l'attend, sans quoi
  // lire l'inclinaison dépend de l'image où il tombe.
  await expect.poll(() => overs.jsonValue()).toContain('mouse')

  expect(await tiltOf(card)).toEqual([0, 0])
})

test('sous la CSP de production, inclinaison et retard s’écrivent : rien par un attribut analysé', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'appareil sans pointeur fin : aucune inclinaison')
  await serveUnderCsp(page)
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, TWO_CARDS)
  await settle(page)
  const card = cards(page).first()
  const { x, y } = await topRightCorner(card)

  await page.mouse.move(x, y)

  await expect.poll(() => tiltOf(card)).toEqual([6, 6])
  await expect(entry(cards(page).last())).toHaveCSS('transition-delay', '0.04s, 0.04s')
})
