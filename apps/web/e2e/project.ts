/** La fiche et ses gestes, partagés par les scénarios. */
import { AxeBuilder } from '@axe-core/playwright'
import type { Locator, Page } from '@playwright/test'
import type { Point } from '../src/project/zoom.ts'
import { expect, serveProjects } from './api.ts'
import { settle } from './css.ts'
import { buildProject, type Project } from './projects.ts'
import { cards, openTable } from './table.ts'

/** Le panneau de la fiche. */
export const panel = (page: Page) => page.getByRole('dialog')

/** Le bouton « Fermer la fiche ». */
export const closeButton = (page: Page) => page.getByRole('button', { name: 'Fermer la fiche' })

/** Le clic hors du panneau, au coin de la fenêtre : une fermeture dès 600 px seulement (spec §3.2). */
export const OUTSIDE = 'un clic hors du panneau'

/** Sous 600 px, le panneau est la fenêtre (spec §3.2) : rien n'est hors de lui. */
export const NO_OUTSIDE = 'sous 600 px, le panneau est la fenêtre'

/** Les quatre fermetures (spec §3.2), dont `OUTSIDE`, dès 600 px. */
export const CLOSINGS: [string, (page: Page) => Promise<unknown>][] = [
  ['le bouton', (page) => closeButton(page).click()],
  ['Échap', (page) => page.keyboard.press('Escape')],
  ['le retour du navigateur', (page) => page.goBack()],
  [OUTSIDE, (page) => page.mouse.click(4, 4)],
]

/** L'appui d'un clic à la main, en millisecondes : la page a le temps de réagir avant le relâché. */
const PRESS = 100

/**
 * Clique hors du panneau, sous sa marge basse, sur une carte de la table : le clic tomberait sur
 * elle s'il traversait.
 */
export async function clickOutsideOverCard(page: Page) {
  const { x, y } = await page.evaluate(() => {
    const { bottom } = document.querySelector('[role="dialog"]')!.getBoundingClientRect()
    const y = (bottom + innerHeight) / 2
    const card = [...document.querySelectorAll('.card')]
      .map((cell) => cell.getBoundingClientRect())
      .find((box) => box.top < y && y < box.bottom)!
    return { x: card.left + card.width / 2, y }
  })
  await page.mouse.click(x, y, { delay: PRESS })
}

/** La colonne de lecture, arrêt de tabulation de ce qui défile. */
export const readingColumn = (page: Page) => page.getByRole('region', { name: 'Contenu de la fiche' })

/** La galerie de la fiche, et ses deux flèches. */
export const gallery = (page: Page) => page.getByRole('group', { name: 'Images du projet' })
export const previousImage = (page: Page) => page.getByRole('button', { name: 'Image précédente' })
export const nextImage = (page: Page) => page.getByRole('button', { name: 'Image suivante' })

/** « Agrandir l’image », le bouton de la galerie qui ouvre la couche plein écran (issue #243). */
export const expandButton = (page: Page) => page.getByRole('button', { name: 'Agrandir l’image' })

/** La couche plein écran, et son bouton de fermeture. */
export const viewer = (page: Page) => page.getByRole('dialog', { name: 'Image en plein écran' })
export const closeImageButton = (page: Page) => page.getByRole('button', { name: 'Fermer l’image' })

/** L'image de la couche, et son compteur. */
export const viewerImage = (page: Page) => viewer(page).getByRole('img')
export const viewerCounter = (page: Page) => viewer(page).locator('.project-gallery-counter')

/** La boîte de la zone d'image de la couche : la fenêtre moins la barre. */
export const viewerZone = async (page: Page) =>
  (await page.locator('.image-viewer-zone').boundingBox())!

/** La transformation que la couche écrit sur son image : translation et facteur. */
export const transformOf = (page: Page) =>
  viewerImage(page).evaluate((image: HTMLElement) => image.style.transform)

/** La vue d'ouverture de la couche : l'image entière, centrée. */
export const FIT = 'translate(0px, 0px) scale(1)'

/**
 * Attend que la couche soit ouverte depuis plus d'un double toucher (500 ms, spec §4.4) : avant, un
 * toucher du fond est le second temps du double clic qui l'a ouverte, et ne la ferme pas.
 */
export const outlastOpening = (page: Page) => page.waitForTimeout(500)

/**
 * Un stylet glissé d'un point à un autre, en un pas : Playwright n'a que la souris, le clavier et un
 * écran tactile qui ne fait que toucher (doc de Playwright, classe `Touchscreen`, lue par context7 le
 * 2026-11-08) ; le protocole de Chromium simule le stylet.
 */
export async function penDrag(page: Page, from: Point, to: Point) {
  const client = await page.context().newCDPSession(page)
  const pen = (type: 'mouseMoved' | 'mousePressed' | 'mouseReleased', { x, y }: Point) =>
    client.send('Input.dispatchMouseEvent', {
      type,
      x,
      y,
      button: 'left',
      buttons: 1,
      clickCount: 1,
      pointerType: 'pen',
    })

  await pen('mouseMoved', from)
  await pen('mousePressed', from)
  await pen('mouseMoved', to)
  await pen('mouseReleased', to)
  await client.detach()
}

/** Ouvre la couche par « Agrandir l’image », fondu d'entrée achevé. */
export async function openViewer(page: Page) {
  await expandButton(page).click()
  await expect(viewer(page)).toBeVisible()
  await settle(page)
}

/** Le projet d'une fiche à un seul slug, ces champs remplacés. */
export const ficheProject = (overrides: Partial<Project> = {}) =>
  buildProject({ slug: 'fiche', title: 'Fiche', ...overrides })

/** Les deux liens d'une fiche. */
export const LINKS = {
  demo_url: 'https://demo.test/fiche',
  repository_url: 'https://depot.test/fiche',
}

/** De quoi faire défiler la colonne comme le panneau. */
export const LONG_DESCRIPTION = Array.from(
  { length: 40 },
  (_, index) => `Paragraphe ${index + 1} de la description.`,
).join('\n\n')

/** Arrive sur la fiche par son adresse. */
export async function arriveAt(page: Page, overrides: Partial<Project> = {}, hash = '') {
  await serveProjects(page, [ficheProject(overrides)])
  await page.goto(`/projets/fiche${hash}`)
  await expect(panel(page)).toBeVisible()
  await page.evaluate(async () => void (await document.fonts.ready))
  await settle(page)
}

/** Attend un élément sans débordement horizontal. */
export async function expectNoOverflow(element: Locator) {
  const { scrollWidth, clientWidth } = await element.evaluate(
    ({ scrollWidth, clientWidth }) => ({ scrollWidth, clientWidth }),
  )

  expect(scrollWidth).toBeLessThanOrEqual(clientWidth)
}

/** Aucune violation d'axe sur ce qui est rendu. */
export async function expectNoViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze()

  expect(violations.map((violation) => violation.id)).toEqual([])
}

/** Ouvre la fiche d'une carte par Entrée, qui ouvre d'emblée sur les deux projets. */
export async function openProject(card: Locator) {
  await card.press('Enter')
  await expect(panel(card.page())).toBeVisible()
  await settle(card.page())
}

/** Ouvre une table sur ces projets, puis la fiche de sa première carte. */
export async function openFromTable(page: Page, projects: Project[]) {
  await openTable(page, projects)
  await openProject(cards(page).first())
}

/** Attend la fiche fermée, panneau retiré au bout de son fondu de sortie, et l'adresse à `/`. */
export async function expectClosed(page: Page) {
  await expect(panel(page)).toHaveCount(0)
  await expect(page).toHaveURL('/')
}

/** Attend le panneau à ses repères (spec §3.2) : la fenêtre sous 600 px, sinon ceux de 1280 × 800. */
export async function expectPanelBox(page: Page) {
  const viewport = page.viewportSize()!

  expect(await panel(page).boundingBox()).toEqual(
    viewport.width < 600
      ? { x: 0, y: 0, ...viewport }
      : { x: 24, y: 79, width: 1232, height: 642 },
  )
}

/**
 * Fige les animations de la page, celles qui partiront comme celles en cours : un panneau qui se
 * ferme reste dans son fondu de sortie.
 *
 * @returns Le geste qui les relance à leur vitesse.
 */
export async function freezeAnimations(page: Page) {
  const client = await page.context().newCDPSession(page)
  await client.send('Animation.enable')
  await client.send('Animation.setPlaybackRate', { playbackRate: 0 })
  return () => client.send('Animation.setPlaybackRate', { playbackRate: 1 })
}

/**
 * Consigne les violations de CSP de la page, telles que Chromium les écrit en console.
 *
 * @returns Les messages, dans un tableau qui se remplit au fil du scénario.
 */
export function watchCspViolations(page: Page): string[] {
  const violations: string[] = []
  page.on('console', (message) => {
    if (message.text().includes('Content Security Policy')) violations.push(message.text())
  })
  return violations
}

/**
 * Consigne les animations CSS qui partent à partir de maintenant, sur toute la page.
 *
 * @returns De quoi lire celles parties : nom, durée et courbe.
 */
export async function watchAnimations(page: Page) {
  const runs = await page.evaluateHandle(() => {
    const seen: { name: string; duration: string; curve: string }[] = []
    addEventListener('animationstart', ({ target, animationName: name }) => {
      const { animationDuration: duration, animationTimingFunction: curve } = getComputedStyle(
        target as Element,
      )
      seen.push({ name, duration, curve })
    })
    return seen
  })
  return () => runs.jsonValue()
}

/**
 * Retient, sans les laisser agir, les clics que la page laisse au navigateur : un onglet ouvert
 * échapperait aux interceptions de la page. Un clic du bouton du milieu est un `auxclick`.
 *
 * @returns De quoi lire le nombre de clics que l'application n'a pas annulés.
 */
export async function holdNativeClicks(page: Page) {
  const clicks = await page.evaluateHandle(() => {
    const held = { count: 0 }
    for (const type of ['click', 'auxclick']) {
      addEventListener(type, (event) => {
        if (!event.defaultPrevented) held.count += 1
        event.preventDefault()
      })
    }
    return held
  })
  return async () => (await clicks.jsonValue()).count
}
