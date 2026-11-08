/**
 * La chorégraphie de la fiche (spec §2.7, §4.6 ; issue #22) : ouverte depuis sa carte, elle en part
 * et y revient.
 *
 * Les animations se lisent par `getAnimations()`, jamais au chronomètre : la page figée
 * (`freezeAnimations`), une animation se place à l'instant voulu par son `currentTime`, et ses
 * durées, ses retards et sa courbe se comparent aux jetons résolus. Seules comptent celles de la
 * Web Animations API — ni les transitions ni les animations CSS de la page.
 */
import type { Locator, Page } from '@playwright/test'
import { expect, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  clickOutsideOverCard,
  CLOSINGS,
  closeButton,
  expectClosed,
  ficheProject,
  freezeAnimations,
  LINKS,
  nextImage,
  NO_OUTSIDE,
  openProject,
  OUTSIDE,
  panel,
  readingColumn,
  watchAnimations,
} from './project.ts'
import { buildImage, ONGOING, PROJECT_SETS } from './projects.ts'
import {
  cards,
  COLUMN_VIEWPORT,
  countCellReads,
  enterCards,
  expectPlacement,
  face,
  focusByKeyboard,
  openTable,
} from './table.ts'

/** Trois projets ; la première carte, celle d'un projet en cours, à une seule image. */
const PROJECTS = PROJECT_SETS.threeWithoutShowcase
const FIRST_PATH = '/projets/projet-02'

/** Une fiche à deux images et deux liens : tout son contenu apparaît à la pose. */
const FULL_FICHE = ficheProject({
  ...LINKS,
  gallery: [buildImage('fiche', 'Une'), buildImage('fiche', 'Deux')],
})

/** Une boîte, par ses quatre nombres. */
type Box = { left: number; top: number; width: number; height: number }

/** Les durées et la courbe de §2.7, résolues : millisecondes et courbe sérialisée par le navigateur. */
async function motion(page: Page) {
  const [open, content, fast, reduced, ribbon, easing] = await resolveAll(page, [
    ['transition-duration', 'var(--dur-open)'],
    ['transition-duration', 'var(--dur-content)'],
    ['transition-duration', 'var(--dur-fast)'],
    ['transition-duration', 'var(--dur-reduced)'],
    ['transition-delay', 'var(--delay-ribbon)'],
    ['transition-timing-function', 'var(--ease-out)'],
  ])
  const ms = (seconds: string) => Math.round(parseFloat(seconds) * 1000)
  return {
    open: ms(open),
    content: ms(content),
    fast: ms(fast),
    reduced: ms(reduced),
    ribbon: ms(ribbon),
    easing,
  }
}

/** La boîte d'un élément à l'écran. */
const boxOf = (element: Locator): Promise<Box> =>
  element.evaluate((node) => node.getBoundingClientRect().toJSON())

/** Deux boîtes égales au demi-pixel. */
function expectSameBox(actual: Box, expected: Box) {
  for (const key of ['left', 'top', 'width', 'height'] as const) {
    expect(actual[key], key).toBeCloseTo(expected[key], 0)
  }
}

/**
 * Une translation lue sur une image clé : Chromium écrit `48px` pour `48px 0px`, et `0px` au repos
 * (Chromium 156, `getKeyframes()` sondé le 2026-11-03).
 */
function offsetOf(translate: unknown) {
  const [x, y = 0] = String(translate).split(' ').map(parseFloat)
  return { x, y }
}

/**
 * Ouvre la table, ses cartes entrées et leurs transitions finies : une transition partie pendant que
 * la page est figée ne finit jamais après sa relance (Chromium 156, mesuré le 2026-11-03).
 */
async function openEnteredTable(page: Page, projects: Parameters<typeof openTable>[1]) {
  await openTable(page, projects)
  await enterCards(page)
}

/**
 * La carte d'un projet, par son adresse : la fiche ouverte, Radix cache les cartes des technologies
 * d'assistance, et `cards` ne les trouve plus.
 */
const cardAt = (page: Page, path: string) => page.locator(`.card[href="${path}"]`)

/**
 * Ouvre, page figée, la fiche d'une carte par son activation seule, comme une technologie
 * d'assistance : la chorégraphie reste à son premier instant. Entrée lui donnerait le focus au même
 * instant : levée d'un coup sous `[data-origin]` pour la mesure du vol, elle retomberait dès que le
 * panneau le prend.
 */
async function openFrozen(page: Page, path: string) {
  const resume = await freezeAnimations(page)
  await cardAt(page, path).dispatchEvent('click', { detail: 0 })
  await expect(panel(page)).toBeVisible()
  return resume
}

/** Dans la page : place chaque animation de la Web Animations API à `time` ms de son début. */
function seekAnimations(time: number) {
  for (const animation of document.getAnimations()) {
    if (animation.constructor === Animation) animation.currentTime = time
  }
}

/** Dans la page : annule les animations de la Web Animations API, comme un tiers qui les retire. */
function cancelAnimations() {
  for (const animation of document.getAnimations()) {
    if (animation.constructor === Animation) animation.cancel()
  }
}

/**
 * Page figée, achève les animations de la page : le contenu de la fiche, effacé, laisse partir le
 * retour à la carte, qui reste à son premier instant. Une lecture de ce que tient un remplissage
 * achève dans sa propre fonction de page (`readFlights`) : Playwright n'envoie à la page que le texte
 * de la fonction, et la fiche tire la suite au microtâche suivant.
 */
async function finishAnimations(page: Page) {
  await page.evaluate(() => {
    for (const animation of document.getAnimations()) {
      if (animation.constructor === Animation) animation.finish()
    }
  })
}

/**
 * Trois éléments du contenu qui apparaît à la pose (spec §4.6) : le bouton Fermer, la barre de la
 * galerie, la colonne de lecture.
 */
const contentSample = (page: Page) => [
  closeButton(page),
  panel(page).locator('.project-gallery-bar'),
  readingColumn(page),
]

/** La fiche revenue à sa carte : panneau retiré, défilement rendu, la carte montrée et focalisée. */
async function expectLanded(page: Page, card: Locator) {
  await expectClosed(page)
  await expect(page.locator('html')).not.toHaveAttribute('data-project-open')
  await expect(card.locator('.card-photo')).toHaveCSS('opacity', '1')
  await expect(card).toBeFocused()
}

/**
 * Dans la page : chaque élément volant de la fiche — la feuille, la photo, le post-it, puis chaque
 * ruban — et son homologue sur la carte : sa boîte à l'instant, et sa seule animation, lue à son
 * premier et à son dernier instant, puis rendue au sien.
 *
 * @param finish Achève d'abord les animations de la page et lit aussitôt, avant que la fiche n'en
 *   tire la suite au microtâche suivant : ce que tient leur remplissage.
 */
function readFlights({ path, finish = false }: { path: string; finish?: boolean }) {
  if (finish) {
    for (const animation of document.getAnimations()) {
      if (animation.constructor === Animation) animation.finish()
    }
  }
  const card = document.querySelector(`.card[href="${path}"]`)!
  const dialog = document.querySelector('[role="dialog"]')!
  const box = (element: Element) => {
    const { left, top, width, height } = element.getBoundingClientRect()
    return { left, top, width, height }
  }
  const homologues = card.querySelectorAll('.card-band .card-ribbon')
  const pairs = [
    [dialog.querySelector('.project-sheet')!, card.querySelector('.card-face')!],
    [dialog.querySelector('.project-gallery-frame')!, card.querySelector('.card-photo')!],
    [dialog.querySelector('.project-title')!, card.querySelector('.card-postit')!],
    ...[...dialog.querySelectorAll('.project-head .card-ribbon')].map((ribbon, index) => [
      ribbon,
      homologues[index],
    ]),
  ]
  return pairs.map(([element, homologue]) => {
    const now = box(element)
    const flights = element.getAnimations().filter((animation) => animation.constructor === Animation)
    const [flight] = flights
    const at = flight.currentTime
    flight.currentTime = 0
    const start = box(element)
    flight.currentTime = flight.effect!.getComputedTiming().endTime as number
    const end = box(element)
    flight.currentTime = at
    const { duration, delay, easing } = flight.effect!.getTiming()
    return { count: flights.length, now, start, end, homologue: box(homologue), duration, delay, easing }
  })
}

test('la feuille, la photo, le post-it et les rubans partent de leur homologue sur la carte, en `--dur-open`, `--ease-out`', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open, ribbon, easing } = await motion(page)
  await openFrozen(page, FIRST_PATH)

  const flights = await page.evaluate(readFlights, { path: FIRST_PATH })
  const panelBox = await boxOf(panel(page))

  expect(flights.length).toBeGreaterThan(3)
  for (const [index, flight] of flights.entries()) {
    expect(flight.count).toBe(1)
    expectSameBox(flight.start, flight.homologue)
    expect(flight.duration).toBe(open)
    expect(flight.easing).toBe(easing)
    expect(flight.delay).toBe(Math.max(0, index - 3) * ribbon)
  }
  expectSameBox(flights[0].end, panelBox)
})

test('les rubans passent par 35 % d’opacité entre 30 % et 70 % du trajet', async ({ page }) => {
  await openEnteredTable(page, PROJECTS)
  await openFrozen(page, FIRST_PATH)

  const keyframes = await panel(page)
    .locator('.project-head .card-ribbon')
    .first()
    .evaluate((ribbon) =>
      (ribbon.getAnimations()[0].effect as KeyframeEffect)
        .getKeyframes()
        .map(({ computedOffset, opacity }) => [computedOffset, Number(opacity)]),
    )

  expect(keyframes).toEqual([
    [0, 1],
    [0.3, 0.35],
    [0.7, 0.35],
    [1, 1],
  ])
})

test('la carte se cache d’un coup, sauf son trombone, qui monte de 14 px en s’effaçant, et sa pose revient à 0°', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open, content, fast } = await motion(page)
  const card = cardAt(page, FIRST_PATH)
  await freezeAnimations(page)

  await card.dispatchEvent('click', { detail: 0 })
  await expect(panel(page)).toBeVisible()

  for (const part of ['.card-photo', '.card-postit', '.card-band']) {
    await expect(card.locator(part)).toHaveCSS('opacity', '0')
  }
  await expect(face(card)).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await expect(face(card)).toHaveCSS('box-shadow', 'none')
  const transitions = await card.evaluate((cell) =>
    ['.card-clip', '.card-pose'].flatMap((layer) =>
      cell
        .querySelector(layer)!
        .getAnimations()
        .map((transition) => ({
          layer,
          property: (transition as CSSTransition).transitionProperty,
          duration: transition.effect!.getTiming().duration,
          end: (transition.effect as KeyframeEffect).getKeyframes().at(-1)!,
        })),
    ),
  )
  expect(transitions).toHaveLength(3)
  expect(transitions).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ layer: '.card-clip', property: 'opacity', duration: fast }),
      expect.objectContaining({
        layer: '.card-clip',
        property: 'translate',
        duration: content,
        end: expect.objectContaining({ translate: '0px -14px' }),
      }),
      expect.objectContaining({
        layer: '.card-pose',
        property: 'transform',
        duration: open,
        end: expect.objectContaining({ transform: 'none' }),
      }),
    ]),
  )
})

/**
 * Dans le cadre de la galerie : la couche noir et blanc — l'image grise posée sur la première —,
 * sa boîte et celle de l'image, et son fondu.
 */
function readGreyLayer(frame: Element) {
  const [image, ...others] = frame.querySelectorAll('img')
  const grey = others.find((other) => getComputedStyle(other).filter === 'grayscale(1)')!
  const [fade] = grey.getAnimations()
  return {
    same: grey.src === image.src,
    box: grey.getBoundingClientRect().toJSON(),
    image: image.getBoundingClientRect().toJSON(),
    hidden: grey.getAttribute('aria-hidden'),
    duration: fade.effect!.getTiming().duration,
    opacities: (fade.effect as KeyframeEffect).getKeyframes().map(({ opacity }) => Number(opacity)),
  }
}

test('un projet en cours : la couche noir et blanc couvre la première image et s’efface pendant le vol', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open } = await motion(page)
  const resume = await openFrozen(page, FIRST_PATH)
  const images = panel(page).locator('.project-gallery-frame img')

  const layer = await panel(page).locator('.project-gallery-frame').evaluate(readGreyLayer)

  expect(layer).toMatchObject({ same: true, hidden: 'true', duration: open, opacities: [1, 0] })
  expectSameBox(layer.box, layer.image)

  await resume()
  await settle(page)

  await expect(images).toHaveCount(1)
})

test('fermée depuis sa deuxième image, la galerie revient d’un coup à la première, celle de la carte, et la couche noir et blanc s’y pose', async ({
  page,
}) => {
  await openEnteredTable(page, [
    ficheProject({ ...ONGOING, gallery: [buildImage('fiche', 'Une'), buildImage('fiche', 'Deux')] }),
  ])
  await openProject(cardAt(page, '/projets/fiche'))
  await nextImage(page).click()
  await settle(page)
  await freezeAnimations(page)
  const frame = panel(page).locator('.project-gallery-frame')
  const track = panel(page).locator('.project-gallery-track')

  await page.keyboard.press('Escape')

  expect(await track.evaluate((element) => element.getAnimations().length)).toBe(0)
  expectSameBox(await boxOf(frame.locator('img').first()), await boxOf(frame))
  await finishAnimations(page)
  const grey = await frame.evaluate(readGreyLayer)
  expectSameBox(grey.box, await boxOf(frame))
})

test('les autres cartes de l’écran reculent de 48 px à l’opposé de la carte ouverte et s’effacent ; hors de l’écran, rien ne bouge', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECT_SETS.twelveWithShowcase)
  const { open, easing } = await motion(page)
  const path = await cards(page).nth(2).getAttribute('href')
  await openFrozen(page, path!)

  const others = await page.evaluate((opened) => {
    const center = (element: Element) => {
      const { left, top, width, height } = element.getBoundingClientRect()
      return { x: left + width / 2, y: top + height / 2 }
    }
    const origin = center(document.querySelector(`.card[href="${opened}"]`)!)
    return [...document.querySelectorAll(`.card:not([href="${opened}"])`)].map((cell) => {
      const { top, bottom } = cell.getBoundingClientRect()
      const { x, y } = center(cell)
      const [fade] = cell.querySelector('.card-entry')!.getAnimations()
      const keyframes = (fade.effect as KeyframeEffect).getKeyframes()
      return {
        onScreen: bottom > 0 && top < innerHeight,
        direction: { x: x - origin.x, y: y - origin.y },
        moves: keyframes.some((keyframe) => 'translate' in keyframe),
        end: keyframes.at(-1)!,
        timing: fade.effect!.getTiming(),
      }
    })
  }, path!)

  expect(others.filter(({ onScreen }) => onScreen).length).toBeGreaterThan(0)
  expect(others.filter(({ onScreen }) => !onScreen).length).toBeGreaterThan(0)
  for (const { onScreen, direction, moves, end, timing } of others) {
    expect(Number(end.opacity)).toBe(0)
    expect(timing).toMatchObject({ duration: open, easing })
    expect(moves).toBe(onScreen)
    if (!onScreen) continue
    const { x, y } = offsetOf(end.translate)
    const length = Math.hypot(direction.x, direction.y)
    expect(Math.hypot(x, y)).toBeCloseTo(48, 3)
    expect(x).toBeCloseTo((direction.x / length) * 48, 3)
    expect(y).toBeCloseTo((direction.y / length) * 48, 3)
  }
})

test('pendant le vol, ni une cellule de la table ni sa grille ne se transforment', async ({ page }) => {
  await openEnteredTable(page, PROJECT_SETS.twelveWithShowcase)
  await openFrozen(page, (await cards(page).nth(2).getAttribute('href'))!)

  const transformed = await page.evaluate(() => {
    for (const animation of document.getAnimations()) {
      animation.currentTime = (animation.effect!.getComputedTiming().endTime as number) / 2
    }
    const grid = document.querySelector('[data-table-cell]')!.parentElement!
    return [grid, ...document.querySelectorAll('[data-table-cell]')].filter((element) => {
      const style = getComputedStyle(element)
      return [style.transform, style.translate, style.scale, style.rotate].some((value) => value !== 'none')
    }).length
  })

  expect(transformed).toBe(0)
})

/**
 * Dans la page : les ancêtres du panneau, lui compris, qui portent une transformation, et la place
 * du bouton Fermer, sa propre montée de 8 px retirée (spec §4.6).
 */
function readClosePlace() {
  const transformed: string[] = []
  let node: Element | null = document.querySelector('.project-panel')
  for (; node; node = node.parentElement) {
    const { transform, translate, scale, rotate } = getComputedStyle(node)
    if ([transform, translate, scale, rotate].some((value) => value !== 'none')) {
      transformed.push(node.tagName)
    }
  }
  const button = document.querySelector('.project-close')!
  const rise = getComputedStyle(button).translate.split(' ')
  const [x = 0, y = 0] = rise.map((value) => parseFloat(value) || 0)
  const { left, top, width, height } = button.getBoundingClientRect()
  return { transformed, place: { left: left - x, top: top - y, width, height } }
}

test('sous 600 px, pendant le vol, ni le panneau ni ses ancêtres ne se transforment : le bouton Fermer reste à sa place', async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, 'le bouton Fermer est fixe sous 600 px')
  await openEnteredTable(page, PROJECTS)
  const { open } = await motion(page)
  const resume = await openFrozen(page, FIRST_PATH)
  const instants = []

  for (const time of [0, open / 4, open / 2, (open * 3) / 4]) {
    await page.evaluate(seekAnimations, time)
    instants.push(await page.evaluate(readClosePlace))
  }
  await resume()
  await settle(page)
  const posed = await page.evaluate(readClosePlace)

  for (const { transformed, place } of instants) {
    expect(transformed).toEqual([])
    expectSameBox(place, posed.place)
  }
})

test('de l’ouverture à la fin du retour, la mesure des liens de l’auteur n’est pas relue, et, relue de force, rend la même forme', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'la colonne demande la largeur du bureau')
  const cellReads = await countCellReads(page)
  // 118 px de marge à 1280 px (spec §3.1) : un recul de 48 px posé sur une cellule la passerait
  // sous les 76 px qui admettent la colonne (§3.4).
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openEnteredTable(page, PROJECT_SETS.twelveWithShowcase)
  const { open } = await motion(page)
  await expectPlacement(page, 'column')
  await openFrozen(page, (await cards(page).nth(2).getAttribute('href'))!)
  const instants: [string, () => Promise<unknown>][] = [
    ['en plein vol', () => page.evaluate(seekAnimations, open / 2)],
    ['à la pose', () => page.evaluate(seekAnimations, open)],
    ['à la demande de fermeture', () => page.keyboard.press('Escape')],
    ['au départ du retour', () => finishAnimations(page)],
    ['en plein retour', () => page.evaluate(seekAnimations, open / 2)],
  ]

  for (const [instant, reach] of instants) {
    const before = await cellReads()
    await reach()
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)))
    expect(await cellReads(), instant).toBe(before)
    await page.evaluate(() => dispatchEvent(new Event('resize')))
    expect(await cellReads(), instant).toBeGreaterThan(before)
    await expectPlacement(page, 'column')
  }
})

test('à la pose, le contenu monte de 8 px en `--dur-content`, puis « Fermer la fiche » prend le focus, que le panneau tient sans anneau d’ici là', async ({
  page,
}) => {
  await openEnteredTable(page, [FULL_FICHE])
  const { open, content, easing } = await motion(page)
  const resume = await openFrozen(page, '/projets/fiche')
  const appearing = [
    closeButton(page),
    panel(page).getByRole('button', { name: 'Image précédente' }),
    panel(page).getByRole('button', { name: 'Image suivante' }),
    panel(page).locator('.project-gallery-bar'),
    panel(page).getByRole('link', { name: 'Voir le site' }),
    panel(page).getByRole('link', { name: 'Voir le dépôt' }),
    readingColumn(page),
  ]

  await expect(panel(page)).toBeFocused()
  await expect(panel(page)).toHaveCSS('outline-style', 'none')
  for (const element of appearing) {
    await expect(element).toHaveCSS('opacity', '0')
    const entrance = await element.evaluate((node) => {
      const [animation] = node.getAnimations().filter((candidate) => candidate.constructor === Animation)
      const [first, last] = (animation.effect as KeyframeEffect).getKeyframes()
      return { timing: animation.effect!.getTiming(), first, last }
    })
    expect(entrance.timing).toMatchObject({ duration: content, delay: open, easing })
    expect(entrance.first).toMatchObject({ opacity: '0', translate: '0px 8px' })
    expect(entrance.last).toMatchObject({ opacity: '1' })
    expect(offsetOf(entrance.last.translate)).toEqual({ x: 0, y: 0 })
  }

  await resume()

  await expect(closeButton(page)).toBeFocused()
  const [paper] = await resolveAll(page, [['background-color', 'var(--paper)']])
  await expect(panel(page)).toHaveCSS('background-color', paper)
})

for (const reducedMotion of ['no-preference', 'reduce'] as const) {
  test(`(${reducedMotion}) rien dans la fiche ne réagit au pointeur avant qu’elle soit active, ni une fois sa fermeture demandée`, async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion })
    await openEnteredTable(page, PROJECTS)
    const resume = await openFrozen(page, FIRST_PATH)
    // Le panneau réagit, une fois que Radix l'a écrit sur lui : ses enfants, non.
    await expect(panel(page)).toHaveCSS('pointer-events', 'auto')

    await expect(closeButton(page)).toHaveCSS('pointer-events', 'none')
    await resume()
    await expect(closeButton(page)).toBeFocused()
    await expect(closeButton(page)).toHaveCSS('pointer-events', 'auto')
    await freezeAnimations(page)
    await page.keyboard.press('Escape')
    await expect(closeButton(page)).toHaveCSS('pointer-events', 'none')
  })
}

test('à la fermeture, le contenu s’efface en `--dur-fast`, puis la feuille, la photo, le post-it et les rubans repartent vers la carte en `--dur-open`, et la couche noir et blanc revient', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open, fast, ribbon, easing } = await motion(page)
  await openProject(cardAt(page, FIRST_PATH))
  const panelBox = await boxOf(panel(page))
  const [paper] = await resolveAll(page, [['background-color', 'var(--paper)']])
  await freezeAnimations(page)

  await page.keyboard.press('Escape')

  for (const element of contentSample(page)) {
    const fade = await element.evaluate((node) => {
      const [animation] = node.getAnimations().filter((candidate) => candidate.constructor === Animation)
      return {
        timing: animation.effect!.getTiming(),
        end: (animation.effect as KeyframeEffect).getKeyframes().at(-1)!.opacity,
      }
    })
    expect(fade).toEqual({ timing: expect.objectContaining({ duration: fast, easing }), end: '0' })
  }
  await expect(panel(page)).toHaveCSS('background-color', paper)

  await finishAnimations(page)

  await expect(panel(page)).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  const flights = await page.evaluate(readFlights, { path: FIRST_PATH })
  expect(flights.length).toBeGreaterThan(3)
  for (const [index, flight] of flights.entries()) {
    expect(flight.count).toBe(1)
    expectSameBox(flight.end, flight.homologue)
    expect(flight.duration).toBe(open)
    expect(flight.easing).toBe(easing)
    expect(flight.delay).toBe(Math.max(0, index - 3) * ribbon)
  }
  expectSameBox(flights[0].start, panelBox)
  const grey = await panel(page).locator('.project-gallery-frame').evaluate(readGreyLayer)
  expect(grey).toMatchObject({ same: true, duration: open, opacities: [0, 1] })
  expectSameBox(grey.box, grey.image)
})

test('à la fermeture, les autres cartes reviennent à leur place en réapparaissant, en `--dur-open`', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECT_SETS.twelveWithShowcase)
  const { open, easing } = await motion(page)
  const path = (await cards(page).nth(2).getAttribute('href'))!
  await openProject(cardAt(page, path))
  await freezeAnimations(page)

  await page.keyboard.press('Escape')
  await finishAnimations(page)

  const returns = await page.evaluate((opened) => {
    return [...document.querySelectorAll(`.card:not([href="${opened}"]) .card-entry`)].map((entry) => {
      const animations = entry.getAnimations()
      const keyframes = (animations[0].effect as KeyframeEffect).getKeyframes()
      return {
        count: animations.length,
        timing: animations[0].effect!.getTiming(),
        first: keyframes[0],
        last: keyframes.at(-1)!,
      }
    })
  }, path)

  expect(returns.filter(({ first }) => 'translate' in first).length).toBeGreaterThan(0)
  for (const { count, timing, first, last } of returns) {
    expect(count).toBe(1)
    expect(timing).toMatchObject({ duration: open, easing })
    expect([first.opacity, last.opacity]).toEqual(['0', '1'])
    if (!('translate' in first)) continue
    expect(Math.hypot(...Object.values(offsetOf(first.translate)))).toBeCloseTo(48, 3)
    expect(offsetOf(last.translate)).toEqual({ x: 0, y: 0 })
  }
})

/*
 * Ce que tient le remplissage (`fill`) de chaque animation de `useChoreography`, dénombré dans sa
 * source le 2026-11-03 : onze animations, une par sens de chaque mouvement.
 *
 * - tiennent quelque chose, sept : le vol à l'aller (`backwards`, un ruban qui attend son retard
 *   reste sur son homologue : test « … partent de leur homologue », lu au temps 0) ; le vol au retour
 *   (`both` : sur la carte jusqu'au retrait, et, pendant son retard, là où le ruban était : test
 *   « … en plein vol … », lu au temps 0) ; l'effacement des cartes à l'aller (`forwards`, tant
 *   que la fiche est ouverte) ; l'apparition du contenu (`backwards`, caché jusqu'à la pose : test
 *   « à la pose, le contenu monte… », lu au temps 0) ; son effacement (`forwards`) ; en mouvement
 *   réduit, l'effacement des enfants du panneau puis du panneau (`forwards`, jusqu'au retrait) ;
 * - ne tiennent rien, leur fin étant leur repos, quatre : le retour des cartes, les deux fondus de la
 *   couche noir et blanc — retirée à l'aller, opaque au retour —, l'apparition du panneau en
 *   mouvement réduit.
 *
 * Les cinq qui tiennent jusqu'au retrait ou tant que la fiche est ouverte sont épinglés ici ; chacun
 * des sept rougit son test quand son remplissage est retiré (mutations du 2026-11-03).
 */

/** Dans la page : la couche d'entrée des cartes autres que `opened`, dans l'écran ou non, et sa pose. */
function readEntries(opened: string) {
  return [...document.querySelectorAll(`.card:not([href="${opened}"])`)].map((cell) => {
    const { top, bottom } = cell.getBoundingClientRect()
    const { opacity, translate } = getComputedStyle(cell.querySelector('.card-entry')!)
    return { onScreen: bottom > 0 && top < innerHeight, opacity, translate }
  })
}

test('au bout du retour, jusqu’au retrait du panneau, la feuille, la photo, le post-it et les rubans restent sur la carte, le contenu effacé', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  await openProject(cardAt(page, FIRST_PATH))
  await freezeAnimations(page)

  await page.keyboard.press('Escape')
  await finishAnimations(page)

  for (const element of contentSample(page)) {
    await expect(element).toHaveCSS('opacity', '0')
  }
  const held = await page.evaluate(readFlights, { path: FIRST_PATH, finish: true })
  expect(held.length).toBeGreaterThan(3)
  for (const { now, homologue } of held) expectSameBox(now, homologue)
})

test('tant que la fiche est ouverte, les autres cartes restent effacées, et reculées dans l’écran', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECT_SETS.twelveWithShowcase)
  const path = (await cards(page).nth(2).getAttribute('href'))!
  await openProject(cardAt(page, path))

  const others = await page.evaluate(readEntries, path)

  expect(others.filter(({ onScreen }) => onScreen).length).toBeGreaterThan(0)
  for (const { onScreen, opacity, translate } of others) {
    expect(opacity).toBe('0')
    expect(translate === 'none').toBe(!onScreen)
  }
})

for (const [name, close] of CLOSINGS) {
  test(`${name} : à la fin du retour seulement, la carte réapparaît, panneau et feuille partent sans fondu, le défilement et le focus lui reviennent`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile && name === OUTSIDE, NO_OUTSIDE)
    await openEnteredTable(page, PROJECTS)
    const card = cardAt(page, FIRST_PATH)
    await openProject(card)
    const animations = await watchAnimations(page)
    const resume = await freezeAnimations(page)

    await close(page)

    await expect(page.locator('html')).toHaveAttribute('data-project-open')
    await expect(card.locator('.card-photo')).toHaveCSS('opacity', '0')
    await expect(panel(page)).toHaveCount(1)

    await resume()

    await expectLanded(page, card)
    await expect(page.locator('.project-sheet')).toHaveCount(0)
    expect(await animations()).toEqual([])
  })
}

/**
 * Une animation annulée en route — son `finished` rejette, son `finish` ne part pas — n'arrête pas
 * la chorégraphie. Les attentes d'une fin d'animation de `useChoreography`, dénombrées dans sa
 * source avant correctif (2026-11-03) : cinq.
 *
 * - fuyaient : la pose, au `finish` du premier vol (rien sur `cancel`) ; l'effacement du contenu et
 *   le retour à la carte, deux `await` de `Promise.all` ; l'atterrissage, `land().then(onLanded)`,
 *   que ces deux rejets coupent ;
 * - indemne : le retrait de la couche noir et blanc, sur `finish` comme sur `cancel`.
 *
 * Un cas par instant où une attente est en cours ; les deux modes passent par les mêmes attentes.
 */
const CANCELLATIONS: [string, (page: Page) => Promise<unknown>][] = [
  ['pendant que le contenu s’efface', async () => {}],
  ['pendant le retour à la carte', finishAnimations],
]

test('une animation annulée pendant le vol : la fiche se pose quand même, « Fermer la fiche » prend le focus', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const [paper] = await resolveAll(page, [['background-color', 'var(--paper)']])
  const resume = await openFrozen(page, FIRST_PATH)

  await page.evaluate(cancelAnimations)
  await resume()

  await expect(closeButton(page)).toBeFocused()
  await expect(panel(page)).toHaveCSS('background-color', paper)
})

for (const [moment, reach] of CANCELLATIONS) {
  test(`une animation annulée ${moment} : la fermeture va à son terme`, async ({ page }) => {
    await openEnteredTable(page, PROJECTS)
    const card = cardAt(page, FIRST_PATH)
    await openProject(card)
    const resume = await freezeAnimations(page)

    await page.keyboard.press('Escape')
    await reach(page)
    await page.evaluate(cancelAnimations)
    await resume()

    await expectLanded(page, card)
  })
}

/** Les fermetures possibles en plein vol : le bouton n'y réagit pas encore. */
const INTERRUPTIONS = CLOSINGS.filter(([name]) => name !== 'le bouton')

for (const [name, close] of INTERRUPTIONS) {
  test(`${name} en plein vol : chaque élément repart vers la carte d’où il est, en \`--dur-open\`, le contenu reste caché, et la fermeture va à son terme`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile && name === OUTSIDE, NO_OUTSIDE)
    await openEnteredTable(page, PROJECTS)
    const { open, easing } = await motion(page)
    const card = cardAt(page, FIRST_PATH)
    const resume = await openFrozen(page, FIRST_PATH)
    await page.evaluate(seekAnimations, open / 2)
    const flying = await page.evaluate(readFlights, { path: FIRST_PATH })
    const receding = await page.evaluate(readEntries, FIRST_PATH)
    const frame = panel(page).locator('.project-gallery-frame')
    const greyShown = await frame
      .locator('.card-photo-grey')
      .evaluate((layer) => Number(getComputedStyle(layer).opacity))

    await close(page)

    // La pose n'arrive plus : le panneau reste transparent, le focus loin de « Fermer la fiche ».
    await expect(panel(page)).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
    await expect(closeButton(page)).not.toBeFocused()
    const [from, to] = (await frame.evaluate(readGreyLayer)).opacities
    expect(greyShown).toBeGreaterThan(0)
    expect(from).toBeCloseTo(greyShown, 3)
    expect(to).toBe(1)
    const returning = await page.evaluate(readFlights, { path: FIRST_PATH })
    expect(returning).toHaveLength(flying.length)
    for (const [index, flight] of returning.entries()) {
      expect(flight.count).toBe(1)
      expectSameBox(flight.now, flying[index].now)
      expectSameBox(flight.start, flying[index].now)
      expectSameBox(flight.end, flight.homologue)
      expect(flight).toMatchObject({ duration: open, easing })
    }
    expect(await page.evaluate(readEntries, FIRST_PATH)).toEqual(receding)
    for (const element of contentSample(page)) {
      await expect(element).toHaveCSS('opacity', '0')
    }

    await resume()

    await expectLanded(page, card)
  })
}

/*
 * Au décollage, la carte perd ses états d'intention — le focus, que prend le panneau, et le survol,
 * que Radix retire au pointeur —, et ses couches en reviendraient par transition. Les couches d'une
 * carte qui transitent (`card.css`), dénombrées le 2026-11-08 : sept. Déplacent la face, la photo,
 * le post-it ou les rubans, trois : la levée et la pression (`.card-face`), qu'une intention perdue
 * au décollage ferait revenir, coupées sous `[data-origin]` ; la pose (`.card-pose`), voulue : elle
 * revient à 0° en `--dur-open` (§4.6) ; l'entrée (`.card-entry`), qui ne court qu'avant la fin de
 * la montée de la carte. N'en déplacent aucun, quatre : la cellule et l'ombre soulevée, par leur
 * seule opacité ; le bandeau de résumé et le trombone, sans homologue.
 */
test('levée par le focus, fermée en plein vol : chaque élément revient sur la carte au repos', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'la levée suit un appareil à survol')
  await openEnteredTable(page, PROJECTS)
  const { open } = await motion(page)
  const card = cardAt(page, FIRST_PATH)
  await focusByKeyboard(card)
  await settle(page)
  await expect(face(card)).not.toHaveCSS('transform', 'none')
  await openFrozen(page, FIRST_PATH)
  await page.evaluate(seekAnimations, open / 2)

  await page.keyboard.press('Escape')
  // La carte au repos sous `[data-origin]` : ses transitions achevées.
  await card.evaluate((cell) => {
    for (const transition of cell.getAnimations({ subtree: true })) transition.finish()
  })

  const returning = await page.evaluate(readFlights, { path: FIRST_PATH })
  expect(returning.length).toBeGreaterThan(3)
  for (const { end, homologue } of returning) expectSameBox(end, homologue)
})

/*
 * Une ouverture n'est prise qu'une fois la fermeture finie (décision de #22). Les voies qui ouvrent
 * une fiche, dénombrées dans la source le 2026-11-03 : trois. L'activation d'une carte (`onOpen` de
 * la table : clic, Entrée, second toucher) et l'historique (`popstate`) peuvent arriver pendant un
 * retour ; l'adresse au chargement, jamais. Radix retient le pointeur et le focus tant que la fiche
 * est à l'écran : l'activation d'une carte arrive ici par l'événement lui-même, comme celle d'une
 * technologie d'assistance.
 */

for (const reducedMotion of ['no-preference', 'reduce'] as const) {
  test(`pendant la fermeture (${reducedMotion}), une autre carte activée n’ouvre rien ; la fermeture finie, elle ouvre`, async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion })
    await openEnteredTable(page, PROJECTS)
    const card = cardAt(page, FIRST_PATH)
    const otherPath = (await cards(page).nth(1).getAttribute('href'))!
    const other = cardAt(page, otherPath)
    await openProject(card)
    const resume = await freezeAnimations(page)

    await page.keyboard.press('Escape')
    await other.dispatchEvent('click', { detail: 0 })

    await expect(page).toHaveURL('/')
    await resume()
    await expectClosed(page)
    await expect(card).toBeFocused()

    await other.press('Enter')

    await expect(panel(page)).toBeVisible()
    await expect(page).toHaveURL(otherPath)
  })
}

test('« suivant » de l’historique pendant le retour : la fiche se rouvre une fois la carte rejointe, par le fondu de l’arrivée directe', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const [paper] = await resolveAll(page, [['background-color', 'var(--paper)']])
  await openProject(cardAt(page, FIRST_PATH))
  const resume = await freezeAnimations(page)
  await page.keyboard.press('Escape')
  await expect(page).toHaveURL('/')
  const animations = await watchAnimations(page)

  await page.goForward()
  await resume()
  await expect(page.locator('html')).not.toHaveAttribute('data-choreography')
  await settle(page)

  await expect(page).toHaveURL(FIRST_PATH)
  await expect(closeButton(page)).toBeFocused()
  await expect(panel(page)).toHaveCSS('background-color', paper)
  await expect(closeButton(page)).toHaveCSS('opacity', '1')
  expect((await animations()).map(({ name }) => name)).toEqual(['project-in'])
})

test('« suivant » puis « précédent » pendant le retour : un seul retour, qui va à son terme', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const card = cardAt(page, FIRST_PATH)
  await openProject(card)
  const resume = await freezeAnimations(page)
  await page.keyboard.press('Escape')
  await expect(page).toHaveURL('/')
  await finishAnimations(page)

  await page.goForward()
  await page.goBack()

  for (const flight of await page.evaluate(readFlights, { path: FIRST_PATH })) {
    expect(flight.count).toBe(1)
  }
  await resume()
  await expectClosed(page)
  await expect(card).toBeFocused()
})

test('un clic hors du panneau sur une autre carte ramène la fiche à la sienne, sans ouvrir l’autre', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, NO_OUTSIDE)
  await openEnteredTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cardAt(page, (await cards(page).nth(2).getAttribute('href'))!)
  await openProject(card)

  await clickOutsideOverCard(page)

  await expectClosed(page)
  await settle(page)
  await expect(page).toHaveURL('/')
  await expect(card).toBeFocused()
})

test('sa carte d’origine sortie du document, la fiche se ferme par le fondu de sortie', async ({ page }) => {
  await openEnteredTable(page, PROJECTS)
  const card = cardAt(page, FIRST_PATH)
  await openProject(card)
  await card.evaluate((cell) => cell.remove())
  const animations = await watchAnimations(page)

  await closeButton(page).click()

  await expectClosed(page)
  expect((await animations()).map(({ name }) => name)).toEqual(['project-out'])
})

/**
 * Dans la page : les animations de la Web Animations API, par la classe de leur cible et la carte
 * qui la contient, s'il y en a une, ce qu'elles animent, leurs opacités, leur durée et leur fin.
 */
function readFades() {
  const ignored = new Set(['offset', 'computedOffset', 'easing', 'composite'])
  return document
    .getAnimations()
    .filter((animation) => animation.constructor === Animation)
    .map((animation) => {
      const effect = animation.effect as KeyframeEffect
      const keyframes = effect.getKeyframes()
      const target = effect.target as Element
      return {
        target: target.className,
        card: target.closest('.card')?.getAttribute('href') ?? undefined,
        properties: [...new Set(keyframes.flatMap(Object.keys))].filter((key) => !ignored.has(key)),
        opacities: keyframes.map(({ opacity }) => opacity),
        duration: effect.getTiming().duration,
        end: effect.getComputedTiming().endTime,
      }
    })
}

/** Dans la page : l'opacité des deux couches de chaque carte qu'un fondu efface, l'entrée et la face. */
function readCardOpacities() {
  return [...document.querySelectorAll('.card')].map((cell) =>
    ['.card-entry', '.card-face'].map((layer) => getComputedStyle(cell.querySelector(layer)!).opacity),
  )
}

test.describe('en mouvement réduit (spec §6.3)', () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
  })

  test('la fiche apparaît pendant que toutes les cartes s’effacent, en `--dur-fast`, sans feuille ni vol ; elle est active à `--dur-reduced`', async ({
    page,
  }) => {
    await openEnteredTable(page, PROJECT_SETS.twelveWithShowcase)
    const { fast, reduced } = await motion(page)
    const entered = await page.locator('.card[data-entered]').count()
    const opened = (await cards(page).nth(2).getAttribute('href'))!
    const resume = await openFrozen(page, opened)

    const fades = await page.evaluate(readFades)

    expect(new Set(fades.flatMap(({ properties }) => properties))).toEqual(new Set(['opacity']))
    expect(fades.filter(({ target }) => target === 'project-panel')).toEqual([
      { target: 'project-panel', properties: ['opacity'], opacities: ['0', '1'], duration: fast, end: reduced },
    ])
    // La carte ouverte, par sa face (§6.3) ; les autres, entières.
    const cardFades = fades.filter(({ card }) => card)
    expect(cardFades).toHaveLength(entered)
    for (const fade of cardFades) {
      const target = fade.card === opened ? 'card-face' : 'card-entry'
      expect(fade).toMatchObject({ target, opacities: ['1', '0'], duration: fast })
    }
    await expect(page.locator('.project-sheet')).toBeHidden()
    await expect(panel(page)).toBeFocused()

    await resume()

    await expect(closeButton(page)).toBeFocused()
  })

  test('à la fermeture, le contenu s’efface en `--dur-reduced`, puis la fiche en `--dur-reduced` pendant que les cartes reviennent en `--dur-fast`', async ({
    page,
  }) => {
    await openEnteredTable(page, PROJECTS)
    const { fast, reduced } = await motion(page)
    const card = cardAt(page, FIRST_PATH)
    await openProject(card)
    const resume = await freezeAnimations(page)

    await page.keyboard.press('Escape')

    const content = (await page.evaluate(readFades)).filter(({ card }) => !card)
    expect(content.length).toBeGreaterThan(2)
    for (const fade of content) {
      expect(fade).toMatchObject({ properties: ['opacity'], duration: reduced })
      expect(fade.opacities.at(-1)).toBe('0')
    }

    await finishAnimations(page)

    const fades = await page.evaluate(readFades)
    const [fiche, ...others] = fades.filter(({ target }) => target === 'project-panel')
    expect(others).toEqual([])
    expect(fiche).toMatchObject({ properties: ['opacity'], duration: reduced })
    expect(fiche.opacities.at(-1)).toBe('0')
    const returns = fades.filter(({ card }) => card)
    expect(returns).toHaveLength(PROJECTS.length)
    for (const fade of returns) {
      const target = fade.card === FIRST_PATH ? 'card-face' : 'card-entry'
      expect(fade).toMatchObject({ target, opacities: ['0', '1'], duration: fast })
    }

    await resume()

    await expectClosed(page)
    await expect(page.locator('html')).not.toHaveAttribute('data-project-open')
    await expect(card).toBeFocused()
  })

  test('Échap pendant l’apparition : la fiche s’efface depuis son opacité, en `--dur-reduced`, et les cartes reviennent d’où elles sont', async ({
    page,
  }) => {
    await openEnteredTable(page, PROJECTS)
    const { fast, reduced } = await motion(page)
    const card = cardAt(page, FIRST_PATH)
    const resume = await openFrozen(page, FIRST_PATH)
    await page.evaluate(seekAnimations, fast / 2)
    const appearing = await panel(page).evaluate((element) => getComputedStyle(element).opacity)
    const fading = await page.evaluate(readCardOpacities)

    await page.keyboard.press('Escape')

    const fiche = (await page.evaluate(readFades)).filter(({ target }) => target === 'project-panel')
    expect(fiche).toEqual([
      { target: 'project-panel', properties: ['opacity'], opacities: [appearing, '0'], duration: reduced, end: reduced },
    ])
    expect(await page.evaluate(readCardOpacities)).toEqual(fading)

    await resume()

    await expectClosed(page)
    await expect(card).toBeFocused()
  })

  test('au bout de la fermeture, jusqu’au retrait du panneau, la fiche et son contenu restent effacés', async ({
    page,
  }) => {
    await openEnteredTable(page, PROJECTS)
    await openProject(cardAt(page, FIRST_PATH))
    await freezeAnimations(page)

    await page.keyboard.press('Escape')
    await finishAnimations(page)
    // Achevées et lues dans la même tâche : au microtâche suivant, la fiche quitte le document.
    const opacities = await panel(page).evaluate((element) => {
      for (const animation of document.getAnimations()) {
        if (animation.constructor === Animation) animation.finish()
      }
      return [element, ...element.children].map((node) => getComputedStyle(node).opacity)
    })

    expect(opacities.length).toBeGreaterThan(2)
    expect(new Set(opacities)).toEqual(new Set(['0']))
  })
})
