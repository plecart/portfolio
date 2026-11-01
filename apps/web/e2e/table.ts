/**
 * La table et la forme des liens de l'auteur, partagées par les scénarios.
 *
 * La table a ses propres cellules — ses cadres de chargement, puis ses cartes — ;
 * pour éprouver la mesure sur des largeurs quelconques, le scénario en pose de factices, au sens du
 * contrat « cellule de la table » — l'attribut `data-table-cell` sur la boîte de grille —, et rien
 * n'entre dans l'application pour cela. Il les pose sur la table servie vide (le `test` d'`api.ts`),
 * que plus rien ne réécrit une fois la liste arrivée.
 */
import type { Page } from '@playwright/test'
import { expect, serveProjects } from './api.ts'
import type { Project } from './projects.ts'
import { scrollThrough } from './scroll.ts'

/** La largeur de référence du bureau : la table sans cellule y laisse la colonne (spec §3.4). */
export const COLUMN_VIEWPORT = { width: 1280, height: 800 }

/** La forme des liens, lue sur leur boîte : fixe en colonne, dans le flux en pied de page. */
export async function expectPlacement(page: Page, placement: 'column' | 'footer') {
  await expect(page.getByRole('contentinfo')).toHaveCSS(
    'position',
    placement === 'column' ? 'fixed' : 'relative',
  )
}

/** Les cartes de la table, dans son ordre : ses liens. */
export const cards = (page: Page) => page.getByRole('main').getByRole('link')

/** Ouvre la table sur un jeu de projets, ses cartes rendues. */
export async function openTable(page: Page, projects: Project[]) {
  await serveProjects(page, projects)
  await page.goto('/')
  await expect(cards(page)).toHaveCount(projects.length)
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

/** Attend la fin des transitions en cours : ce qu'on lit ensuite les trouve arrivées. */
export async function settle(page: Page) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)))
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
