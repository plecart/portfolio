/**
 * La table, ses cartes et la forme des liens de l'auteur, partagées par les scénarios.
 *
 * La table a ses propres cellules — ses cadres de chargement, puis ses cartes — ; pour éprouver la
 * mesure sur des largeurs quelconques, le scénario en pose de factices, au sens du contrat
 * « cellule de la table » — l'attribut `data-table-cell` sur la boîte de grille —, et rien n'entre
 * dans l'application pour cela. Il les pose sur la table servie vide (le `test` d'`api.ts`), que
 * plus rien ne réécrit une fois la liste arrivée.
 */
import type { Locator, Page } from '@playwright/test'
import { expect, serveProjects } from './api.ts'
import { settle } from './css.ts'
import { buildProject, buildTechnology, ONGOING, type Project } from './projects.ts'
import { scrollThrough } from './scroll.ts'

/** La largeur de référence du bureau : la table sans cellule y laisse la colonne (spec §3.4). */
export const COLUMN_VIEWPORT = { width: 1280, height: 800 }

/** Un téléphone plus étroit que le projet mobile (400 px) : les tailles mobiles de §6.1. */
export const NARROW_VIEWPORT = { ...COLUMN_VIEWPORT, width: 375 }

/**
 * La forme des liens, lue sur leur boîte : fixe en colonne, dans le flux en pied de page. Aussi
 * sous une fiche ouverte, qui les cache des technologies d'assistance.
 */
export async function expectPlacement(page: Page, placement: 'column' | 'footer') {
  await expect(page.getByRole('contentinfo', { includeHidden: true })).toHaveCSS(
    'position',
    placement === 'column' ? 'fixed' : 'relative',
  )
}

/**
 * Compte, dès le chargement, les lectures de boîte des cellules de la table (`data-table-cell`) ;
 * la mesure des liens de l'auteur en fait une par cellule à chaque relecture
 * (`useAuthorLinksPlacement`).
 *
 * @returns De quoi lire le compte.
 */
export async function countCellReads(page: Page) {
  await page.addInitScript(() => {
    const read = Element.prototype.getBoundingClientRect
    let cellReads = 0
    Element.prototype.getBoundingClientRect = function (this: Element) {
      if (this.matches('[data-table-cell]')) cellReads += 1
      return read.call(this)
    }
    Object.defineProperty(window, 'cellReads', { get: () => cellReads })
  })
  return () => page.evaluate(() => (window as unknown as { cellReads: number }).cellReads)
}

/** Les cartes de la table, dans son ordre : ses liens. */
export const cards = (page: Page) => page.getByRole('main').getByRole('link')

/** Les couches d'une carte qui bougent, et son bandeau de résumé. */
export const entry = (card: Locator) => card.locator('.card-entry')
export const pose = (card: Locator) => card.locator('.card-pose')
export const face = (card: Locator) => card.locator('.card-face')
export const summary = (card: Locator) => card.locator('.card-summary')

/** Les trois technologies qu'une carte montre au plus (spec §1.4), une par type. */
const THREE_TECHNOLOGIES = (['language', 'framework', 'infrastructure'] as const).map((kind) =>
  buildTechnology(kind, kind),
)

/** Une carte aux trois technologies et aux deux états : sous 600 px, ses rubans vont à la ligne. */
export const FULL_CARD = buildProject({
  ...ONGOING,
  slug: 'pleine',
  demo_url: 'https://demo.test/pleine',
  technologies: THREE_TECHNOLOGIES,
})

/**
 * Une carte aux trois technologies, en ligne : sur la carte simple, ses rubans tiennent sur une
 * rangée au bureau, à 2 px près, et en prennent deux à 375 px (spec §4.1).
 */
export const LIVE_CARD = buildProject({
  slug: 'en-ligne',
  demo_url: 'https://demo.test/en-ligne',
  technologies: THREE_TECHNOLOGIES,
})

/** Deux cartes sur une rangée : la carte pleine, en cours donc en tête, et sa voisine. */
export const TWO_CARDS = [FULL_CARD, buildProject({ slug: 'voisine' })]

/** Les tailles de tout ruban, de carte ou de fiche (spec §4.1, §4.3), lues par `ribbonSizes`. */
export const RIBBON_SIZES = { ribbons: ['32px 13px'], icons: ['24px 24px'] }

/**
 * Les tailles calculées des rubans sous un élément, chacune une fois : hauteur et police des
 * rubans, largeur et hauteur de leurs icônes. Une seule de chaque quand tous ont la même ; aucune
 * sans ruban.
 */
export const ribbonSizes = (container: Locator) =>
  container.locator('.card-ribbon').evaluateAll((ribbons) => {
    const distinct = (values: string[]) => [...new Set(values)]
    const style = (element: Element) => getComputedStyle(element)
    const icons = ribbons.flatMap((ribbon) => [...ribbon.querySelectorAll('img')])
    return {
      ribbons: distinct(
        ribbons.map((ribbon) => `${style(ribbon).height} ${style(ribbon).fontSize}`),
      ),
      icons: distinct(icons.map((icon) => `${style(icon).width} ${style(icon).height}`)),
    }
  })

/**
 * Ouvre la table sur un jeu de projets, ses cartes rendues et sa police arrivée : `font-display:
 * swap` laisse sinon mesurer le texte dans la police de repli, plus étroite.
 */
export async function openTable(page: Page, projects: Project[]) {
  await serveProjects(page, projects)
  await page.goto('/')
  await expect(cards(page)).toHaveCount(projects.length)
  await page.evaluate(async () => void (await document.fonts.ready))
}

/**
 * Sert la page sous une CSP sans `style-src 'unsafe-inline'`, comme celle de Caddy, qu'aucun scénario
 * ne traverse : elle bloque un attribut `style` analysé, jamais le CSSOM.
 */
export async function serveUnderCsp(page: Page) {
  await page.route('/', async (route) => {
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: { ...response.headers(), 'content-security-policy': "style-src 'self'" },
    })
  })
}

/**
 * Consigne les transitions qui partent à partir de maintenant, sur toute la page : elles se lisent
 * après coup, là où une lecture de `getAnimations()` manquerait une transition déjà finie.
 *
 * @returns De quoi lire celles parties, sur une couche (sa classe) ou partout.
 */
export async function watchTransitions(page: Page) {
  const runs = await page.evaluateHandle(() => {
    const seen: { layer: string; property: string; duration: string }[] = []
    addEventListener('transitionrun', ({ target, propertyName: property }) => {
      const element = target as Element
      const { transitionDuration: duration } = getComputedStyle(element)
      seen.push({ layer: element.className, property, duration })
    })
    return seen
  })
  return async (layer?: string) => {
    const seen = await runs.jsonValue()
    return layer ? seen.filter((run) => run.layer === layer) : seen
  }
}

/** Focalise une carte au clavier : une touche d'abord, pour que `:focus-visible` s'applique. */
export async function focusByKeyboard(card: Locator) {
  await card.page().keyboard.press('Tab')
  await card.focus()
}

/**
 * Fait entrer toutes les cartes : la page défilée écran par écran, puis ramenée en haut. Une carte
 * qui n'est pas entrée reste à opacité 0, et un contrôle d'accessibilité ne la lirait pas.
 */
export async function enterCards(page: Page) {
  const { clientHeight, scrollHeight } = await page.evaluate(() => {
    const { clientHeight, scrollHeight } = document.documentElement
    return { clientHeight, scrollHeight }
  })
  for (let top = 0; top < scrollHeight; top += clientHeight) await scrollThrough(page, top)
  await scrollThrough(page, 0)
  await expect(page.locator('.card:not([data-entered])')).toHaveCount(0)
  await settle(page)
}

/**
 * Pose des cellules dans la table, centrées comme la grille les centre ; elles remplacent celles
 * qui y étaient.
 *
 * @param widths La largeur de chaque cellule, en px ; aucune vide la table.
 * @param height Leur hauteur, en px : de quoi allonger la page sans autre élément.
 */
export async function placeCells(page: Page, widths: number[], height = 10) {
  await page.evaluate(
    ([cellWidths, cellHeight]) => {
      document.querySelector('main')?.replaceChildren(
        ...cellWidths.map((width) => {
          const cell = document.createElement('div')
          cell.setAttribute('data-table-cell', '')
          cell.style.cssText = `width: ${width}px; height: ${cellHeight}px; margin: 0 auto`
          return cell
        }),
      )
    },
    [widths, height] as const,
  )
}
