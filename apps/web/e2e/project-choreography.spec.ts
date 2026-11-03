/**
 * La chorégraphie de la fiche (spec §2.7, §4.6 ; issue #22) : ouverte depuis sa carte, elle en part.
 *
 * Les animations se lisent par `getAnimations()`, jamais au chronomètre : la page figée
 * (`freezeAnimations`), une animation se place à l'instant voulu par son `currentTime`, et ses
 * durées, ses retards et sa courbe se comparent aux jetons résolus. Seules comptent celles de la
 * Web Animations API — ni les transitions ni les animations CSS de la page.
 */
import type { Page } from '@playwright/test'
import { expect, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  closeButton,
  ficheProject,
  freezeAnimations,
  LINKS,
  panel,
  readingColumn,
} from './project.ts'
import { buildImage, PROJECT_SETS } from './projects.ts'
import { cards, enterCards, openTable } from './table.ts'

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
  const [open, content, fast, ribbon, easing] = await resolveAll(page, [
    ['transition-duration', 'var(--dur-open)'],
    ['transition-duration', 'var(--dur-content)'],
    ['transition-duration', 'var(--dur-fast)'],
    ['transition-delay', 'var(--delay-ribbon)'],
    ['transition-timing-function', 'var(--ease-out)'],
  ])
  const ms = (seconds: string) => Math.round(parseFloat(seconds) * 1000)
  return { open: ms(open), content: ms(content), fast: ms(fast), ribbon: ms(ribbon), easing }
}

/** Deux boîtes égales au demi-pixel. */
function expectSameBox(actual: Box, expected: Box) {
  for (const key of ['left', 'top', 'width', 'height'] as const) {
    expect(actual[key], key).toBeCloseTo(expected[key], 0)
  }
}

/** Une translation lue sur une image clé : Chromium écrit `48px` pour `48px 0px`, et `0px` au repos. */
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

/** Ouvre, page figée, la fiche d'une carte par Entrée : la chorégraphie reste à son premier instant. */
async function openFrozen(page: Page, path: string) {
  const resume = await freezeAnimations(page)
  await page.locator(`.card[href="${path}"]`).press('Enter')
  await expect(panel(page)).toBeVisible()
  return resume
}

test('la feuille, la photo, le post-it et les rubans partent de leur homologue sur la carte, en `--dur-open`, `--ease-out`', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open, ribbon, easing } = await motion(page)
  await openFrozen(page, FIRST_PATH)

  const flights = await page.evaluate((path) => {
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
      const flights = element.getAnimations().filter((animation) => animation.constructor === Animation)
      const [flight] = flights
      flight.currentTime = 0
      const start = box(element)
      flight.currentTime = flight.effect!.getComputedTiming().endTime as number
      const end = box(element)
      const { duration, delay, easing } = flight.effect!.getTiming()
      return { count: flights.length, start, end, homologue: box(homologue), duration, delay, easing }
    })
  }, FIRST_PATH)
  const panelBox = await panel(page).evaluate((element) => element.getBoundingClientRect().toJSON())

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
  const card = page.locator(`.card[href="${FIRST_PATH}"]`)
  await freezeAnimations(page)

  await card.dispatchEvent('click', { detail: 0 })
  await expect(panel(page)).toBeVisible()

  for (const part of ['.card-photo', '.card-postit', '.card-band']) {
    await expect(card.locator(part)).toHaveCSS('opacity', '0')
  }
  await expect(card.locator('.card-face')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await expect(card.locator('.card-face')).toHaveCSS('box-shadow', 'none')
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

test('un projet en cours : la couche noir et blanc couvre la première image et s’efface pendant le vol', async ({
  page,
}) => {
  await openEnteredTable(page, PROJECTS)
  const { open } = await motion(page)
  const resume = await openFrozen(page, FIRST_PATH)
  const images = panel(page).locator('.project-gallery-frame img')

  const layer = await panel(page)
    .locator('.project-gallery-frame')
    .evaluate((frame) => {
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
    })

  expect(layer).toMatchObject({ same: true, hidden: 'true', duration: open, opacities: [1, 0] })
  expectSameBox(layer.box, layer.image)

  await resume()
  await settle(page)

  await expect(images).toHaveCount(1)
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

test('à la pose, le contenu monte de 8 px en `--dur-content`, puis « Fermer la fiche » prend le focus', async ({
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
