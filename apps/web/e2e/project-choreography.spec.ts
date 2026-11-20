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
  LONG_DESCRIPTION,
  nextImage,
  NO_OUTSIDE,
  openProject,
  OUTSIDE,
  panel,
  readingColumn,
  watchAnimations,
} from './project.ts'
import { buildImage, buildTechnology, ONGOING, PROJECT_SETS } from './projects.ts'
import {
  cards,
  COLUMN_VIEWPORT,
  countCellReads,
  enterCards,
  expectPlacement,
  face,
  focusByKeyboard,
  inkedIcons,
  openTable,
  ribbonIcons,
  RIBBON_SIZES,
  ribbonSizes,
  serveUnderCsp,
  straighten,
  strap,
  strapPixels,
  watchPoseAnimations,
} from './table.ts'

/** Trois projets ; la première carte, celle d'un projet en cours, à une seule image. */
const PROJECTS = PROJECT_SETS.threeWithoutShowcase
const FIRST_PATH = '/projets/projet-02'

/** Le chemin de toute fiche de `ficheProject`. */
const FICHE_PATH = '/projets/fiche'

/** Une fiche à deux images et deux liens : tout son contenu apparaît à la pose. */
const FULL_FICHE = ficheProject({
  ...LINKS,
  gallery: [buildImage('fiche', 'Une'), buildImage('fiche', 'Deux')],
})

/** Une boîte, par ses quatre nombres. */
type Box = { left: number; top: number; width: number; height: number }

/** Les durées et la courbe de §2.7, résolues : millisecondes et courbe sérialisée par le navigateur. */
async function motion(page: Page) {
  const [open, content, fast, reduced, strap, ribbon, easing] = await resolveAll(page, [
    ['transition-duration', 'var(--dur-open)'],
    ['transition-duration', 'var(--dur-content)'],
    ['transition-duration', 'var(--dur-fast)'],
    ['transition-duration', 'var(--dur-reduced)'],
    ['transition-duration', 'var(--dur-strap)'],
    ['transition-delay', 'var(--delay-ribbon)'],
    ['transition-timing-function', 'var(--ease-out)'],
  ])
  const ms = (seconds: string) => Math.round(parseFloat(seconds) * 1000)
  return {
    open: ms(open),
    content: ms(content),
    fast: ms(fast),
    reduced: ms(reduced),
    strap: ms(strap),
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
 * Attend un élément volant de `readFlights` posé sur son homologue de la carte : sa boîte ; la copie
 * d'un ruban, roulée sous une échelle uniforme, son centre, au demi-pixel — leurs boîtes englobantes
 * ne diffèrent que de leurs inclinaisons, et sa taille est celle de son homologue (test « chaque
 * ruban vole roulé »).
 */
function expectOnHomologue(actual: Box, { name, homologue }: { name: string; homologue: Box }) {
  if (!name) return expectSameBox(actual, homologue)
  const centerOf = ({ left, top, width, height }: Box) => [left + width / 2, top + height / 2]
  const [[x, y], [expectedX, expectedY]] = [centerOf(actual), centerOf(homologue)]
  expect(x, `centre de ${name}`).toBeCloseTo(expectedX, 0)
  expect(y, `centre de ${name}`).toBeCloseTo(expectedY, 0)
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
 * galerie, le résumé, dans la colonne de lecture.
 */
const contentSample = (page: Page) => [
  closeButton(page),
  panel(page).locator('.project-gallery-bar'),
  readingColumn(page).locator('.project-summary'),
]

/** La fiche revenue à sa carte : panneau retiré, défilement rendu, la carte montrée et focalisée. */
async function expectLanded(page: Page, card: Locator) {
  await expectClosed(page)
  await expect(page.locator('html')).not.toHaveAttribute('data-project-open')
  await expect(card.locator('.card-photo')).toHaveCSS('opacity', '1')
  await expect(card).toBeFocused()
}

/**
 * Dans la page : chaque élément volant de la fiche — la feuille, la photo, le post-it, puis la copie
 * volante de chaque ruban (`data-flyer`) — et son homologue sur la carte : sa boîte à l'instant, et
 * sa seule animation, lue à son premier et à son dernier instant, puis rendue au sien ; l'opacité à
 * laquelle il se voit à l'instant (`seenOpacity`) ; la boîte et la visibilité de l'élément de la
 * fiche qu'il fait voler, lui-même ou le ruban d'une copie. Une copie dit aussi le nom de son ruban,
 * le rang de son homologue dans la bande de la carte, et la place du ruban : la stack
 * « Technologies » ou l'en-tête ; un autre élément, ni nom, ni rang, ni place.
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
  const flightOf = (element: Element, homologue: Element, rest = element) => {
    // `seenOpacity`, recopiée : une fonction de page n'emporte pas les autres.
    let opacity = 1
    for (let node: Element | null = element; node; node = node.parentElement) {
      opacity *= Number(getComputedStyle(node).opacity)
    }
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
    const boxes = { now, start, end, homologue: box(homologue), rest: box(rest) }
    const seen = getComputedStyle(rest).visibility
    return { count: flights.length, ...boxes, seen, opacity, duration, delay, easing }
  }
  const travelers = [
    [dialog.querySelector('.project-sheet')!, card.querySelector('.card-face')!],
    [dialog.querySelector('.project-gallery-frame')!, card.querySelector('.card-photo')!],
    [dialog.querySelector('.project-title')!, card.querySelector('.card-postit')!],
  ].map(([element, homologue]) => ({ ...flightOf(element, homologue), name: '', rank: 0, place: '' }))
  const band = [...card.querySelectorAll<HTMLElement>('.card-band [data-ribbon]')]
  const technologies = dialog.querySelector('.project-stack')
  const ribbons = [...dialog.querySelectorAll<HTMLElement>('[data-flyer]')].map((flyer) => {
    const name = flyer.dataset.flyer!
    const rank = band.findIndex((homologue) => homologue.dataset.ribbon === name)
    const ribbon = dialog.querySelector(`[data-ribbon="${name}"]`)!
    const place = technologies?.contains(ribbon)
      ? 'technologies'
      : ribbon.closest('.project-head')
        ? 'head'
        : ''
    return { ...flightOf(flyer, band[rank], ribbon), name, rank, place }
  })
  return [...travelers, ...ribbons.sort((one, other) => one.rank - other.rank)]
}

/**
 * Dans la page : l'opacité à laquelle un élément se voit, la sienne composée de celles de ses
 * ancêtres. Un test qui affirme qu'un élément reste visible pendant que son entourage s'efface le lit
 * ainsi, jamais par sa seule opacité ni par ses seules animations : un ancêtre qui s'efface
 * l'emporte avec lui (relecture de #255).
 */
function seenOpacity(element: Element) {
  let opacity = 1
  for (let node: Element | null = element; node; node = node.parentElement) {
    opacity *= Number(getComputedStyle(node).opacity)
  }
  return opacity
}

/** L'opacité à laquelle se voit chaque élément de `elements` (`seenOpacity`). */
const seenOpacities = async (elements: Locator) =>
  Promise.all((await elements.all()).map((element) => element.evaluate(seenOpacity)))

/** Les vols des rubans parmi ceux de `readFlights`, dans l'ordre de la bande de la carte. */
const ribbonFlights = (flights: ReturnType<typeof readFlights>) => flights.filter(({ name }) => name)

test('la feuille, la photo, le post-it et les rubans partent de leur homologue sur la carte, en `--dur-open`, `--ease-out`, le i-ème ruban de la bande avec 20 × i ms de retard', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open, ribbon, easing } = await motion(page)
  await openFrozen(page, FIRST_PATH)

  const flights = await page.evaluate(readFlights, { path: FIRST_PATH })
  const panelBox = await boxOf(panel(page))

  expect(flights.length).toBeGreaterThan(3)
  for (const flight of flights) {
    expect(flight.count).toBe(1)
    expectOnHomologue(flight.start, flight)
    expect(flight.duration).toBe(open)
    expect(flight.easing).toBe(easing)
    expect(flight.delay).toBe(flight.rank * ribbon)
  }
  expectSameBox(flights[0].end, panelBox)
})

/**
 * Une fiche en cours et en ligne, deux outils intercalés dans l'ordre de l'admin : sa carte montre
 * TypeScript, React et Docker, puis ses deux états ; sa stack « Technologies » commence par les
 * trois mêmes, et Redis et PostgreSQL les suivent. Cinq rubans : la copie d'un ruban, au bout de
 * la liste, n'a pas son rang pair ou impair, ni donc son inclinaison par la feuille.
 */
const RIBBONED_FIELDS = {
  ...ONGOING,
  demo_url: LINKS.demo_url,
  technologies: [
    buildTechnology('Figma', 'tool'),
    buildTechnology('TypeScript', 'language'),
    buildTechnology('React', 'framework'),
    buildTechnology('Git', 'tool'),
    buildTechnology('Docker', 'infrastructure'),
    buildTechnology('Redis', 'infrastructure'),
    buildTechnology('PostgreSQL', 'infrastructure'),
  ],
}

/** Dans la stack « Technologies » de `RIBBONED_FIELDS`, les rubans que visent ceux de la carte. */
const TARGETED = '[data-ribbon]:not([data-ribbon="Redis"], [data-ribbon="PostgreSQL"])'

/** Les rubans de la carte de `RIBBONED_FIELDS`, et la place de leur homologue sur la fiche. */
const RIBBON_PLACES = [
  ['TypeScript', 'technologies'],
  ['React', 'technologies'],
  ['Docker', 'technologies'],
  ['ongoing', 'head'],
  ['live', 'head'],
]

test('chaque ruban de technologie vole vers le ruban de la stack « Technologies » de même nom, chaque état vers le sien dans l’en-tête, et en revient', async ({
  page,
}) => {
  await openEnteredTable(page, [ficheProject(RIBBONED_FIELDS)])
  const resume = await openFrozen(page, FICHE_PATH)

  const opening = ribbonFlights(await page.evaluate(readFlights, { path: FICHE_PATH }))

  expect(opening.map(({ name, place }) => [name, place])).toEqual(RIBBON_PLACES)
  for (const flight of opening) {
    expectOnHomologue(flight.start, flight)
    expectSameBox(flight.end, flight.rest)
  }

  await resume()
  await settle(page)
  await freezeAnimations(page)
  await page.keyboard.press('Escape')
  await finishAnimations(page)

  const closing = ribbonFlights(await page.evaluate(readFlights, { path: FICHE_PATH }))

  expect(closing.map(({ name, place }) => [name, place])).toEqual(RIBBON_PLACES)
  for (const flight of closing) {
    expect(flight.count).toBe(1)
    expectSameBox(flight.start, flight.rest)
    expectOnHomologue(flight.end, flight)
  }
})

/**
 * Dans la page : la copie volante de chaque ruban (`data-flyer`) à la part `at` de son vol, de 0, son
 * début, à 1, sa fin, lue puis rendue à son instant ; sans `at`, à l'instant. Son échelle, sur ses
 * deux axes ; sa largeur et sa marge en ligne, puis celles de son homologue sur la carte et de son
 * ruban sur la fiche ; son débordement, et ce que son contenu dépasse de sa largeur ; l'opacité de
 * son nom, s'il en a un.
 */
function readRolls({ path, at }: { path: string; at?: number }) {
  const card = document.querySelector(`.card[href="${path}"]`)!
  const dialog = document.querySelector('[role="dialog"]')!
  const sizeOf = (element: HTMLElement) => ({
    width: element.offsetWidth,
    padding: getComputedStyle(element).paddingInline,
  })
  return [...dialog.querySelectorAll<HTMLElement>('[data-flyer]')].map((flyer) => {
    const name = flyer.dataset.flyer!
    const [flight] = flyer.getAnimations().filter((animation) => animation.constructor === Animation)
    const now = flight.currentTime
    if (at !== undefined) {
      const { delay, duration } = flight.effect!.getComputedTiming()
      flight.currentTime = delay! + at * (duration as number)
    }
    const style = getComputedStyle(flyer)
    // Un seul nombre vaut pour les deux axes (`scale`).
    const [sx, sy = sx] = style.scale.split(' ').map(Number)
    const label = flyer.querySelector('.card-ribbon-name')
    const read = {
      name,
      scale: [sx, sy],
      ...sizeOf(flyer),
      overflow: style.overflow,
      overflowing: flyer.scrollWidth - flyer.clientWidth,
      label: label && getComputedStyle(label).opacity,
      homologue: sizeOf(card.querySelector<HTMLElement>(`.card-band [data-ribbon="${name}"]`)!),
      ribbon: sizeOf(dialog.querySelector<HTMLElement>(`[data-ribbon="${name}"]`)!),
    }
    flight.currentTime = now
    return read
  })
}

/** Les rubans de technologies de la carte de `RIBBONED_FIELDS` : ceux qui portent un nom. */
const NAMED = RIBBON_PLACES.filter(([, place]) => place === 'technologies').map(([name]) => name)

test('chaque ruban vole roulé : au bout carte, sa copie a la largeur et la marge en ligne de son homologue, sous une échelle uniforme, et coupe ce qui la dépasse, le nom d’une technologie effacé ; au bout fiche, les siennes, son nom entier ; entre les deux, nom et largeur passent par des valeurs intermédiaires — à l’aller comme au retour', async ({
  page,
}) => {
  await openEnteredTable(page, [ficheProject(RIBBONED_FIELDS)])
  const rolls = (at: number) => page.evaluate(readRolls, { path: FICHE_PATH, at })
  const resume = await openFrozen(page, FICHE_PATH)
  const opening = [await rolls(0), await rolls(0.5), await rolls(1)]
  await resume()
  await settle(page)
  await freezeAnimations(page)
  await page.keyboard.press('Escape')
  await finishAnimations(page)
  const closing = [await rolls(1), await rolls(0.5), await rolls(0)]

  // Chaque vol, du bout carte au bout fiche.
  for (const [onCard, halfway, onFiche] of [opening, closing]) {
    expect(onCard).toHaveLength(RIBBON_PLACES.length)
    for (const { name, scale: [sx, sy], width, padding, label, homologue } of onCard) {
      expect(sy, name).toBe(sx)
      expect({ width, padding }, name).toEqual(homologue)
      expect(label, name).toBe(NAMED.includes(name) ? '0' : null)
    }
    // Le nom d'une technologie dépasse de la copie roulée, qui le coupe (`project.css`).
    for (const { name, overflow, overflowing } of onCard.filter(({ label }) => label)) {
      expect(overflow, name).toBe('hidden')
      expect(overflowing, name).toBeGreaterThan(0)
    }
    for (const { name, width, padding, label, ribbon } of onFiche) {
      expect({ width, padding }, name).toEqual(ribbon)
      expect(label, name).toBe(NAMED.includes(name) ? '1' : null)
    }
    // Le nom s'interpole (`card.css`, sa propriété enregistrée), la largeur avec lui.
    const named = halfway.filter(({ label }) => label)
    expect(named).toHaveLength(NAMED.length)
    for (const { name, width, label, homologue, ribbon } of named) {
      expect(Number(label), name).toBeGreaterThan(0)
      expect(Number(label), name).toBeLessThan(1)
      expect(width, name).toBeGreaterThan(homologue.width)
      expect(width, name).toBeLessThan(ribbon.width)
    }
  }
})

test('sous la CSP de production, la copie volante d’un ruban de technologie porte son icône entière, à l’encre du ruban, même roulée au bout carte : rien ne change à l’atterrissage (#271)', async ({
  page,
}) => {
  await serveUnderCsp(page)
  await openEnteredTable(page, [ficheProject(RIBBONED_FIELDS)])
  await openFrozen(page, FICHE_PATH)
  const flown = RIBBONED_FIELDS.technologies.filter(({ name }) => NAMED.includes(name))
  const inked = await inkedIcons(page, flown)
  const targets = readingColumn(page).locator('.project-stack').first().locator(TARGETED)

  expect(await ribbonIcons(panel(page).locator('[data-flyer]'))).toEqual(inked)
  expect(await ribbonIcons(targets)).toEqual(inked)
  // Les copies, roulées à la largeur de leur homologue, comme les rubans de la fiche.
  expect(await ribbonSizes(panel(page))).toEqual(RIBBON_SIZES)
})

/**
 * Dans la page : chaque copie volante d'un ruban, sa visibilité et la part de sa boîte que montre
 * la fenêtre, coupes de ses ancêtres comprises (`IntersectionObserver`) ; la visibilité du ruban de
 * la fiche qu'elle remplace, et si elle a son inclinaison ; enfin, son `aria-hidden`.
 */
function readFlyers() {
  const dialog = document.querySelector('[role="dialog"]')!
  const flyers = [...dialog.querySelectorAll<HTMLElement>('[data-flyer]')]
  const shownPart = (element: Element) =>
    new Promise<number>((resolve) => {
      const observer = new IntersectionObserver(([entry]) => {
        observer.disconnect()
        resolve(entry.intersectionRatio)
      })
      observer.observe(element)
    })
  return Promise.all(
    flyers.map(async (flyer) => {
      const ribbon = dialog.querySelector(`[data-ribbon="${flyer.dataset.flyer}"]`)!
      const [style, ribbonStyle] = [flyer, ribbon].map((element) => getComputedStyle(element))
      return {
        visibility: style.visibility,
        ratio: await shownPart(flyer),
        ribbon: ribbonStyle.visibility,
        tilted: style.transform === ribbonStyle.transform,
        ariaHidden: flyer.ariaHidden,
      }
    }),
  )
}

test('en vol, les rubans visés sont seuls visibles dans la colonne, sans qu’elle coupe leur vol ; posés, ils y prennent leur place, et le reste apparaît autour d’eux', async ({
  page,
}) => {
  await openEnteredTable(page, [ficheProject({ ...RIBBONED_FIELDS, description: LONG_DESCRIPTION })])
  const { open, content } = await motion(page)
  const resume = await openFrozen(page, FICHE_PATH)
  const column = readingColumn(page)
  const flyers = panel(page).locator('[data-flyer]')
  const targets = column.locator('.project-stack').first().locator(TARGETED)
  const rest = [
    column.locator('.project-summary'),
    column.locator('.project-stack-title').first(),
    column.locator('[data-ribbon="Redis"]'),
    column.locator('.project-stack').last(),
  ]

  // Les copies se voient entières, aucun de leurs ancêtres ne s'effaçant avec le reste.
  expect(await seenOpacities(flyers)).toEqual(RIBBON_PLACES.map(() => 1))
  const flying = await page.evaluate(readFlyers)

  expect(flying).toHaveLength(RIBBON_PLACES.length)
  for (const flyer of flying) {
    expect(flyer).toEqual({
      visibility: 'visible',
      ratio: 1,
      ribbon: 'hidden',
      tilted: true,
      ariaHidden: 'true',
    })
  }
  // Sa barre aussi : seule sa boîte reste, qui ne se voit pas.
  const [unseen] = await resolveAll(page, [['scrollbar-color', 'transparent transparent']])
  await expect(column).toHaveCSS('scrollbar-color', unseen)
  await expect(column).toHaveCSS('opacity', '1')
  for (const element of rest) await expect(element).toHaveCSS('opacity', '0')

  // À mi-apparition du reste, les rubans visés, posés, se voient entiers.
  await page.evaluate(seekAnimations, open + content / 4)
  const appearing = await column.locator('.project-summary').evaluate(seenOpacity)
  expect(appearing).toBeGreaterThan(0)
  expect(appearing).toBeLessThan(1)
  expect(await seenOpacities(targets)).toEqual([1, 1, 1])

  await resume()
  await settle(page)

  for (const flyer of await page.evaluate(readFlyers)) {
    expect(flyer).toMatchObject({ visibility: 'hidden', ribbon: 'visible' })
  }
  for (const element of rest) await expect(element).toHaveCSS('opacity', '1')
  await expect(column).not.toHaveCSS('scrollbar-color', unseen)
})

test('à la fermeture, la colonne s’efface d’abord, sauf les rubans visés, qui repartent ensuite vers la carte', async ({
  page,
}) => {
  await openEnteredTable(page, [ficheProject(RIBBONED_FIELDS)])
  const { fast } = await motion(page)
  await openProject(cardAt(page, FICHE_PATH))
  await freezeAnimations(page)
  const column = readingColumn(page)
  const targets = column.locator('.project-stack').first().locator(TARGETED)

  await page.keyboard.press('Escape')

  const animationCount = (element: Locator) =>
    element.evaluate((node) => node.getAnimations().length)
  expect(await animationCount(column.locator('.project-summary'))).toBe(1)
  await expect(targets).toHaveCount(3)
  for (const target of await targets.all()) {
    expect(await animationCount(target)).toBe(0)
    await expect(target).toHaveCSS('visibility', 'visible')
  }
  for (const flyer of await page.evaluate(readFlyers)) expect(flyer.visibility).toBe('hidden')
  // À mi-effacement du reste, les rubans visés se voient entiers.
  await page.evaluate(seekAnimations, fast / 2)
  const fading = await column.locator('.project-summary').evaluate(seenOpacity)
  expect(fading).toBeGreaterThan(0)
  expect(fading).toBeLessThan(1)
  expect(await seenOpacities(targets)).toEqual([1, 1, 1])

  await finishAnimations(page)

  await expect(column.locator('.project-summary')).toHaveCSS('opacity', '0')
  for (const flyer of await page.evaluate(readFlyers)) {
    expect(flyer).toMatchObject({ visibility: 'visible', ribbon: 'hidden' })
  }
  expect(await seenOpacities(panel(page).locator('[data-flyer]'))).toEqual(
    RIBBON_PLACES.map(() => 1),
  )
})

test('fermée sa stack défilée hors de vue, chaque ruban repart de sa vraie place, sans test de visibilité', async ({
  page,
  isMobile,
}) => {
  await openEnteredTable(page, [ficheProject({ ...RIBBONED_FIELDS, description: LONG_DESCRIPTION })])
  await openProject(cardAt(page, FICHE_PATH))
  // Ce qui défile : la colonne au bureau, le panneau sur téléphone (spec §4.3).
  const scroller = isMobile ? panel(page) : readingColumn(page)
  await scroller.evaluate((element) =>
    element.scrollTo({ top: element.scrollHeight, behavior: 'instant' }),
  )
  const { y: scrollerTop } = (await scroller.boundingBox())!
  await freezeAnimations(page)

  await page.keyboard.press('Escape')
  await finishAnimations(page)

  const closing = ribbonFlights(await page.evaluate(readFlights, { path: FICHE_PATH }))
  const technologies = closing.filter(({ place }) => place === 'technologies')
  expect(technologies).toHaveLength(3)
  for (const flight of technologies) {
    expect(flight.rest.top + flight.rest.height).toBeLessThan(scrollerTop)
    expectSameBox(flight.start, flight.rest)
    expectOnHomologue(flight.end, flight)
  }
})

test('un ruban de la carte dont la stack replie l’homologue n’a pas de trajet ; la fiche se pose quand même', async ({
  page,
}) => {
  // Chacun seul sur sa rangée, à 1280 comme à 400 px : le troisième au moins passe dans le repli.
  const technologies = ['Alpha', 'Beta', 'Gamma'].map((name) =>
    buildTechnology(`${name}, une technologie au nom bien long`, 'language'),
  )
  await openEnteredTable(page, [ficheProject({ technologies })])
  const resume = await openFrozen(page, FICHE_PATH)

  const flown = ribbonFlights(await page.evaluate(readFlights, { path: FICHE_PATH }))
  const rendered = await readingColumn(page)
    .locator('[data-ribbon]')
    .evaluateAll((ribbons) => ribbons.map((ribbon) => (ribbon as HTMLElement).dataset.ribbon))

  expect(rendered.length).toBeLessThan(technologies.length)
  expect(flown.map(({ name }) => name)).toEqual(rendered)
  await resume()
  await expect(closeButton(page)).toBeFocused()
})

test('les rubans passent par 35 % d’opacité entre 30 % et 70 % du trajet', async ({ page }) => {
  await openEnteredTable(page, PROJECTS)
  await openFrozen(page, FIRST_PATH)

  const keyframes = await panel(page)
    .locator('[data-flyer]')
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
 * Dans la page : la sangle de la carte, et sa copie volante (`data-strap-flyer`) s'il y en a une, à
 * `at` ms des animations de la copie, à leur fin (`'end'`), ou à l'instant, lues puis rendues à leur
 * instant. De chacune, sa boîte, sa largeur de mise en page, et ce que montre chacune de ses deux
 * bandes, la tranche puis les rayures : sa transformation, sa rotation, sa visibilité, son épaisseur.
 * De la copie, en plus, son `aria-hidden`, son opacité et le temps de chacune de ses animations — ses
 * deux glissements et son effacement ; de la carte, les
 * transitions en cours de ses bandes : propriété, durée, courbe, départ et arrivée, en matrices comme
 * ce que montre une bande — une transition les écrit en liste de fonctions.
 */
function readStrap({ path, at }: { path: string; at?: number | 'end' }) {
  const flyer = document.querySelector('[role="dialog"] [data-strap-flyer]')
  const strap = document.querySelector(`.card[href="${path}"] .card-strap`)!
  const read = (box: Element) => {
    const { left, top, width, height } = box.getBoundingClientRect()
    return {
      box: { left, top, width, height },
      width: parseFloat(getComputedStyle(box).width),
      bands: [box, box.querySelector('.card-strap-stripes')!].map((band) => {
        const style = getComputedStyle(band, '::before')
        const { transform, rotate, visibility } = style
        return { transform, rotate, visibility, thickness: parseFloat(style.height) }
      }),
    }
  }
  const animations = flyer?.getAnimations({ subtree: true }) ?? []
  const times = animations.map(({ currentTime }) => currentTime)
  for (const animation of at === undefined ? [] : animations) {
    const { endTime } = animation.effect!.getComputedTiming()
    animation.currentTime = at === 'end' ? (endTime as number) : (at as number)
  }
  const copy = flyer && {
    ...read(flyer),
    ariaHidden: flyer.ariaHidden,
    opacity: getComputedStyle(flyer).opacity,
    slides: animations.map(({ effect }) => {
      const { duration, delay, easing } = effect!.getTiming()
      return { duration, delay, easing }
    }),
  }
  const card = {
    ...read(strap),
    transitions: strap.getAnimations({ subtree: true }).map((transition) => {
      const { duration, easing } = transition.effect!.getTiming()
      const keyframes = (transition.effect as KeyframeEffect).getKeyframes()
      const matrix = (keyframe: Keyframe) => new DOMMatrix(String(keyframe.transform)).toString()
      return {
        property: (transition as CSSTransition).transitionProperty,
        duration,
        easing,
        from: matrix(keyframes[0]),
        to: matrix(keyframes.at(-1)!),
      }
    }),
  }
  animations.forEach((animation, index) => {
    animation.currentTime = times[index]
  })
  return { copy, card }
}

/** Les six nombres d'une transformation calculée, `matrix(a, b, c, d, e, f)`. */
const matrixOf = (transform: string) => transform.slice('matrix('.length, -1).split(',').map(Number)

/**
 * Attend une bande de la sangle glissée de `shift` px perpendiculairement à son axe depuis `rest`,
 * vers le coin haut-gauche quand il est négatif : sa transformation, que sa rotation précède
 * (`card.css`), ne change que de sa translation verticale.
 */
function expectSlid(transform: string, rest: string, shift: number) {
  const expected = matrixOf(rest).map((value, index) => (index === 5 ? value + shift : value))
  matrixOf(transform).forEach((value, index) => {
    expect(value, `${transform} : ${index}`).toBeCloseTo(expected[index], 1)
  })
}

/**
 * La translation qui met une bande de la sangle juste hors de sa boîte, perpendiculairement à son
 * axe, vers le coin haut-gauche, négative, quelle que soit sa place : de son centre, celui de la
 * photo, au coin, la moitié de la largeur de la boîte × (sin + cos) de son angle sur cet axe, plus la
 * moitié de son épaisseur à son échelle — mince au coin. Depuis le repos, c'est aussi sa course.
 */
function clearOf({ width, bands: [band] }: ReturnType<typeof readStrap>['card']) {
  const angle = (-parseFloat(band.rotate) * Math.PI) / 180
  const [scale] = matrixOf(band.transform)
  return -((width / 2) * (Math.sin(angle) + Math.cos(angle)) + (scale * band.thickness) / 2)
}

/** La face de la copie de la sangle : la boîte de ses rayures (`card.css`). */
const STRAP_COPY_FACE = '[data-strap-flyer] .card-strap-stripes'

/**
 * Les pixels que peint la copie de la sangle dans une boîte du panneau (`strapPixels`) : la sienne
 * par défaut.
 */
async function strapCopyPixels(page: Page, box = '[data-strap-flyer]') {
  const zone = (await panel(page).locator(box).boundingBox())!
  return strapPixels(panel(page), zone, zone)
}

/**
 * Dans la page : au centre de la photo de la carte, l'ordre de peinture de la copie de la sangle, de
 * la photo volante et de la feuille, chacune rendue au pointeur et montrée le temps de la mesure — la
 * boîte de la copie, cachée, ne montre que ses bandes : le test de touche suit l'ordre de peinture.
 * Le rang de chacune, du dessus vers le dessous.
 */
function strapCopyRanks(path: string) {
  const dialog = document.querySelector('[role="dialog"]')!
  const layers = ['[data-strap-flyer]', '.project-gallery-frame', '.project-sheet'].map(
    (selector) => dialog.querySelector<HTMLElement>(selector)!,
  )
  const photo = document.querySelector(`.card[href="${path}"] .card-photo`)!
  const { left, top, width, height } = photo.getBoundingClientRect()
  const shown = { pointerEvents: 'auto', visibility: 'visible' }
  for (const layer of layers) Object.assign(layer.style, shown)
  const hits = document.elementsFromPoint(left + width / 2, top + height / 2)
  for (const layer of layers) Object.assign(layer.style, { pointerEvents: '', visibility: '' })
  return layers.map((layer) => hits.findIndex((hit) => layer.contains(hit)))
}

/**
 * Révèle une carte de la main du test, comme un premier toucher, la fiche ouverte ou non : sa sangle
 * passe au coin, et sa pose se redresse (`card.css`).
 */
async function reveal(card: Locator) {
  await card.evaluate((cell) => cell.setAttribute('data-revealed', ''))
  await settle(card.page())
}

/**
 * La part d'une durée où un mouvement en `--ease-out` a fait à peu près la moitié de sa course : la
 * courbe en fait l'essentiel au début.
 */
const MID_COURSE = 1 / 8

/**
 * La sangle de la carte au départ : au repos, sa pose redressée, pour que sa boîte se mesure au
 * pixel près ; au coin, révélée (`reveal`).
 */
const STRAP_STARTS: [string, (card: Locator) => Promise<unknown>][] = [
  ['au repos', straighten],
  ['au coin', reveal],
]

for (const [state, prepare] of STRAP_STARTS) {
  test(`sangle ${state} : à l’ouverture, la carte l’ôte d’un coup, et une copie \`aria-hidden\`, posée sur elle, au-dessus de la photo volante et de la feuille, glisse perpendiculairement à son axe vers le coin haut-gauche jusqu’à juste quitter sa boîte, en \`--dur-open\`, \`--ease-out\`, sans retard, encore dans la face à mi-course, et s’efface en \`--dur-fast\` en glissant ; posée, la fiche n’en montre rien`, async ({
    page,
  }) => {
    await openEnteredTable(page, PROJECTS)
    const { open, fast, easing } = await motion(page)
    const midway = open * MID_COURSE
    await prepare(cardAt(page, FIRST_PATH))
    const { card: before } = await page.evaluate(readStrap, { path: FIRST_PATH })
    const resume = await openFrozen(page, FIRST_PATH)

    const { copy: start, card: hidden } = await page.evaluate(readStrap, { path: FIRST_PATH, at: 0 })
    const { copy: middle } = await page.evaluate(readStrap, { path: FIRST_PATH, at: midway })
    const { copy: end } = await page.evaluate(readStrap, { path: FIRST_PATH, at: 'end' as const })
    const [copy, photo, sheet] = await page.evaluate(strapCopyRanks, FIRST_PATH)
    const clear = clearOf(before)

    // Elle se voit au départ, encore dans la face à mi-course, et plus du tout au bout.
    expect((await strapCopyPixels(page)).length).toBeGreaterThan(0)
    await page.evaluate(seekAnimations, midway)
    expect((await strapCopyPixels(page, STRAP_COPY_FACE)).length).toBeGreaterThan(0)
    await page.evaluate(seekAnimations, open)
    expect(await strapCopyPixels(page)).toEqual([])
    expect(start!.ariaHidden).toBe('true')
    expectSameBox(start!.box, before.box)
    expect(copy).toBeGreaterThanOrEqual(0)
    expect(photo).toBeGreaterThan(copy)
    expect(sheet).toBeGreaterThan(photo)
    expect(start!.slides).toHaveLength(3)
    expect(start!.slides).toEqual(
      expect.arrayContaining([
        ...[0, 1].map(() => ({ duration: open, delay: 0, easing })),
        { duration: fast, delay: 0, easing },
      ]),
    )
    expect([start!.opacity, end!.opacity]).toEqual(['1', '0'])
    expect(hidden.transitions).toEqual([])
    for (const [index, { transform: rest, rotate }] of before.bands.entries()) {
      // Sa course : d'où elle part, au repos ou au coin, à juste hors de sa boîte.
      const course = clear - matrixOf(rest)[5]
      const halfway = matrixOf(middle!.bands[index].transform)[5] - matrixOf(rest)[5]
      expectSlid(hidden.bands[index].transform, rest, course)
      expect(start!.bands[index]).toMatchObject({ rotate, visibility: 'visible' })
      expectSlid(start!.bands[index].transform, rest, 0)
      expect(halfway).toBeLessThan(0)
      expect(halfway).toBeGreaterThan(course)
      expectSlid(middle!.bands[index].transform, rest, halfway)
      expectSlid(end!.bands[index].transform, rest, course)
    }

    await resume()
    await settle(page)

    expect(await strapCopyPixels(page)).toEqual([])
  })
}

test('ouverte pendant que sa sangle glisse vers le coin, la carte la passe à sa copie telle qu’elle la montre : la copie part de cette bande, entre le repos et le coin', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { strap: glide } = await motion(page)
  const card = cardAt(page, FIRST_PATH)
  // Révélée page figée (`reveal`, sans attendre sa fin), sa sangle arrêtée à mi-course.
  await freezeAnimations(page)
  await card.evaluate((cell) => cell.setAttribute('data-revealed', ''))
  await strap(card).evaluate((box, time) => {
    for (const transition of box.getAnimations({ subtree: true })) transition.currentTime = time
  }, glide * MID_COURSE)
  const { card: sliding } = await page.evaluate(readStrap, { path: FIRST_PATH })
  await openFrozen(page, FIRST_PATH)

  const { copy: start } = await page.evaluate(readStrap, { path: FIRST_PATH, at: 0 })
  expect(sliding.transitions).toHaveLength(2)
  for (const [index, { transform }] of sliding.bands.entries()) {
    const { from: rest, to: corner } = sliding.transitions[index]
    // L'échelle de la bande : 1 au repos, `--strap-thin` au coin.
    const [[now], [atRest], [atCorner]] = [transform, rest, corner].map(matrixOf)
    expect(now).toBeLessThan(atRest)
    expect(now).toBeGreaterThan(atCorner)
    expectSlid(start!.bands[index].transform, transform, 0)
  }
})

test('à la fermeture, la copie de la sangle retirée, la sangle de la carte reste hors de sa boîte ; la carte réapparue, elle y glisse perpendiculairement à son axe depuis le coin haut-gauche jusqu’à sa place au repos, en `--dur-strap`, `--ease-out`', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { strap: glide, easing } = await motion(page)
  const card = cardAt(page, FIRST_PATH)
  // Tenue hors de toute intention, que le focus rendu à la carte lui donnerait : à son repos.
  await strap(card).evaluate((box: HTMLElement) =>
    box.style.setProperty('--strap-cornered', '0', 'important'),
  )
  const { card: before } = await page.evaluate(readStrap, { path: FIRST_PATH })
  await openProject(card)
  const resume = await freezeAnimations(page)
  await page.keyboard.press('Escape')
  await finishAnimations(page)
  const { copy, card: returning } = await page.evaluate(readStrap, { path: FIRST_PATH })
  await finishAnimations(page)
  await expect(card).not.toHaveAttribute('data-origin')
  const { card: appearing } = await page.evaluate(readStrap, { path: FIRST_PATH })
  await resume()
  await expectLanded(page, card)
  await settle(page)
  const { card: landed } = await page.evaluate(readStrap, { path: FIRST_PATH })

  const clear = clearOf(before)
  expect(copy).toBeNull()
  expect(appearing.transitions).toHaveLength(2)
  for (const [index, { transform: rest }] of before.bands.entries()) {
    const { property, duration, easing: curve, from, to } = appearing.transitions[index]
    expectSlid(returning.bands[index].transform, rest, clear)
    expect({ property, duration, curve }).toEqual({
      property: 'transform',
      duration: glide,
      curve: easing,
    })
    expectSlid(from, rest, clear)
    expectSlid(to, rest, 0)
    expectSlid(landed.bands[index].transform, rest, 0)
  }
})

test('fermée en plein vol, la copie de la sangle est retirée, et la sangle de la carte reste hors de sa boîte', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open } = await motion(page)
  const { card: before } = await page.evaluate(readStrap, { path: FIRST_PATH })
  await openFrozen(page, FIRST_PATH)
  await page.evaluate(seekAnimations, open / 2)
  await expect(panel(page).locator('[data-strap-flyer]')).toHaveCount(1)

  await page.keyboard.press('Escape')

  const { copy, card: returning } = await page.evaluate(readStrap, { path: FIRST_PATH })
  expect(copy).toBeNull()
  for (const [index, { transform }] of before.bands.entries()) {
    expectSlid(returning.bands[index].transform, transform, clearOf(before))
  }
})

/** Les images du cadre de la galerie, en vol ou posé. */
const frameImages = (page: Page) => panel(page).locator('.project-gallery-frame img')

/** Attend le cadre de la galerie à sa seule image, en couleur. */
async function expectColorFrame(page: Page) {
  await expect(frameImages(page)).toHaveCount(1)
  await expect(frameImages(page)).toHaveCSS('filter', 'none')
}

test('un projet en cours : sa photo vole en couleur, à l’aller comme au retour, la fiche sans sangle', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const card = cardAt(page, FIRST_PATH)
  const resume = await openFrozen(page, FIRST_PATH)

  await expectColorFrame(page)
  // Sa seule sangle est la copie de celle de la carte.
  await expect(panel(page).locator('.card-strap:not([data-strap-flyer])')).toHaveCount(0)
  await resume()
  await settle(page)
  const resumeReturn = await freezeAnimations(page)
  await page.keyboard.press('Escape')
  await finishAnimations(page)

  await expectColorFrame(page)
  await resumeReturn()

  await expectLanded(page, card)
})

/**
 * Dans le cadre de la galerie, la couverture posée en vol — la copie de la première image —, sa
 * boîte et son fondu.
 */
function readCoverLayer(frame: Element) {
  const [image, ...others] = frame.querySelectorAll('img')
  const cover = others.find((other) => other.getAnimations().length > 0)!
  const [fade] = cover.getAnimations()
  return {
    same: cover.src === image.src,
    box: cover.getBoundingClientRect().toJSON(),
    hidden: cover.getAttribute('aria-hidden'),
    duration: fade.effect!.getTiming().duration,
    opacities: (fade.effect as KeyframeEffect).getKeyframes().map(({ opacity }) => Number(opacity)),
  }
}

test('fermée depuis sa deuxième image, la galerie la garde, flèches du clavier comprises, et la couverture y apparaît en fondu pendant le vol', async ({
  page,
}) => {
  await openEnteredTable(page, [
    ficheProject({ gallery: [buildImage('une', 'Une'), buildImage('deux', 'Deux')] }),
  ])
  const { open } = await motion(page)
  await openProject(cardAt(page, FICHE_PATH))
  await nextImage(page).click()
  await settle(page)
  await freezeAnimations(page)
  const frame = panel(page).locator('.project-gallery-frame')
  const track = panel(page).locator('.project-gallery-track')
  const second = frame.locator('img').nth(1)

  await page.keyboard.press('Escape')
  await page.keyboard.press('ArrowRight')

  expect(await track.evaluate((element) => element.getAnimations().length)).toBe(0)
  expectSameBox(await boxOf(second), await boxOf(frame))
  await finishAnimations(page)
  await expect.poll(() => frame.evaluate((element) => element.getAnimations().length)).toBe(1)
  const cover = await frame.evaluate(readCoverLayer)
  expect(cover).toMatchObject({ same: true, hidden: 'true', duration: open, opacities: [0, 1] })
  expectSameBox(cover.box, await boxOf(second))
  expectSameBox(await boxOf(second), await boxOf(frame))
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
  const resume = await openFrozen(page, FICHE_PATH)
  const appearing = [
    closeButton(page),
    panel(page).getByRole('button', { name: 'Image précédente' }),
    panel(page).getByRole('button', { name: 'Image suivante' }),
    panel(page).locator('.project-gallery-bar'),
    panel(page).getByRole('link', { name: 'Voir le site' }),
    panel(page).getByRole('link', { name: 'Voir le dépôt' }),
    readingColumn(page).locator('.project-summary'),
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

test('à la fermeture, le contenu s’efface en `--dur-fast`, puis la feuille, la photo, le post-it et les rubans repartent vers la carte en `--dur-open`', async ({
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
  for (const flight of flights) {
    expect(flight.count).toBe(1)
    expectOnHomologue(flight.end, flight)
    expect(flight.duration).toBe(open)
    expect(flight.easing).toBe(easing)
    expect(flight.delay).toBe(flight.rank * ribbon)
  }
  expectSameBox(flights[0].start, panelBox)
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
 * Ce que tient le remplissage (`fill`) de chaque animation de `useChoreography`, une par sens de
 * chaque mouvement, les deux bandes de la sangle n'en faisant qu'une.
 *
 * - tiennent quelque chose : le vol à l'aller (`backwards`, la copie d'un ruban qui attend son
 *   retard reste sur son homologue : test « … partent de leur homologue », lu au temps 0) ; le vol
 *   au retour (`both` : sur la carte jusqu'au retrait, et, pendant son retard, là où le ruban était :
 *   test « … en plein vol … », lu au temps 0) ; le ruban caché tant que sa copie vole, à l'aller
 *   (`backwards`, pendant le retard : test « en vol, les rubans visés… », lu au temps 0) et au retour
 *   (`both` : test « à la fermeture, la colonne s’efface d’abord… », lu au temps 0, et jusqu'au
 *   retrait) ; l'effacement des cartes à l'aller (`forwards`, tant que la fiche est ouverte) ;
 *   l'apparition du contenu (`backwards`, caché jusqu'à la pose : test « à la pose, le contenu
 *   monte… », lu au temps 0) ; son effacement (`forwards`) ; en mouvement réduit, l'effacement des
 *   enfants du panneau puis du panneau (`forwards`, jusqu'au retrait) ;
 * - ne tiennent rien, leur fin étant leur repos : le retour des cartes, l'apparition du panneau en
 *   mouvement réduit, le glissement de la copie de la sangle, ôtée hors de ses vols (`project.css`).
 *
 * Ceux qui tiennent jusqu'au retrait ou tant que la fiche est ouverte sont épinglés ici ; chacun de
 * ceux qui tiennent quelque chose rougit son test quand son remplissage est retiré (mutations du
 * 2026-11-03 ; du 2026-11-09 pour le ruban caché).
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
  for (const flight of held) {
    expectOnHomologue(flight.now, flight)
    // Vus entiers sur la carte : aucun de leurs ancêtres ne s'est effacé avec le contenu.
    expect(flight.opacity).toBe(1)
  }
  // Chaque ruban de la fiche, que sa copie a remplacé, reste caché.
  expect(ribbonFlights(held).map(({ seen }) => seen)).toEqual(['hidden', 'hidden', 'hidden'])
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

test('revenue de la fiche, la carte d’origine ne rejoue pas son entrée : sa pose ne tourne plus', async ({
  page,
}) => {
  const turns = await watchPoseAnimations(page)
  await openEnteredTable(page, PROJECTS)
  const entered = await turns()
  const card = cardAt(page, FIRST_PATH)

  await openProject(card)
  await page.keyboard.press('Escape')
  await expectLanded(page, card)
  await settle(page)

  expect(entered.map(({ card: path }) => path)).toContain(FIRST_PATH)
  expect(await turns()).toEqual(entered)
})

/**
 * Une animation annulée en route — son `finished` rejette, son `finish` ne part pas — n'arrête pas
 * la chorégraphie. Les attentes d'une fin d'animation de `useChoreography`, dénombrées dans sa
 * source avant correctif (2026-11-03) : cinq.
 *
 * - fuyaient : la pose, au `finish` du premier vol (rien sur `cancel`) ; l'effacement du contenu et
 *   le retour à la carte, deux `await` de `Promise.all` ; l'atterrissage, `land().then(onLanded)`,
 *   que ces deux rejets coupent ;
 * - indemne : le retrait de la couche noir et blanc, sur `finish` comme sur `cancel`, parti avec
 *   elle (#255).
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
  test(`${name} en plein vol : chaque élément repart vers la carte d’où il est et tel qu’il est — la copie d’un ruban sans saut de largeur, de marge en ligne, de nom ni d’opacité —, en \`--dur-open\`, le contenu reste caché, et la fermeture va à son terme`, async ({
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
    const rolling = await page.evaluate(readRolls, { path: FIRST_PATH })
    const receding = await page.evaluate(readEntries, FIRST_PATH)

    await close(page)

    // La pose n'arrive plus : le panneau reste transparent, le focus loin de « Fermer la fiche ».
    await expect(panel(page)).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
    await expect(closeButton(page)).not.toBeFocused()
    const returning = await page.evaluate(readFlights, { path: FIRST_PATH })
    expect(returning).toHaveLength(flying.length)
    for (const [index, flight] of returning.entries()) {
      expect(flight.count).toBe(1)
      expectSameBox(flight.now, flying[index].now)
      expectSameBox(flight.start, flying[index].now)
      expect(flight.opacity).toBeCloseTo(flying[index].opacity, 2)
      expectOnHomologue(flight.end, flight)
      expect(flight).toMatchObject({ duration: open, easing })
    }
    // Ce que la boîte d'une copie de ruban ne dit pas : sa marge en ligne et son nom.
    const rolled = await page.evaluate(readRolls, { path: FIRST_PATH })
    expect(rolled.map((roll) => roll.name)).toEqual(rolling.map((roll) => roll.name))
    for (const [index, { name: ribbon, padding, label }] of rolled.entries()) {
      expect(parseFloat(padding), ribbon).toBeCloseTo(parseFloat(rolling[index].padding), 2)
      expect(Number(label), ribbon).toBeCloseTo(Number(rolling[index].label), 2)
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
  for (const flight of returning) expectOnHomologue(flight.end, flight)
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

test('sa carte d’origine sortie du document, la fiche se retire sans laisser une copie volante, de ruban ni de sangle', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const card = cardAt(page, FIRST_PATH)
  await openProject(card)
  await card.evaluate((cell) => cell.remove())
  const resume = await freezeAnimations(page)

  await closeButton(page).click()

  // Abandonnée, la fiche part par son fondu de sortie, figé : le panneau est encore là.
  const fiche = page.locator('.project-panel')
  await expect(fiche).toHaveAttribute('data-state', 'closed')
  await expect(fiche.locator('[data-flyer], [data-strap-flyer]')).toHaveCount(0)
  await resume()
  await expectClosed(page)
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
