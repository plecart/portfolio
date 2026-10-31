/**
 * La table et la forme des liens de l'auteur, partagées par les scénarios.
 *
 * La table a ses propres cellules — ses cadres de chargement, puis ses cartes — ;
 * pour éprouver la mesure sur des largeurs quelconques, le scénario en pose de factices, au sens du
 * contrat « cellule de la table » — l'attribut `data-table-cell` sur la boîte de grille —, et rien
 * n'entre dans l'application pour cela. Il les pose sur la table servie vide (le `test` d'`api.ts`),
 * que plus rien ne réécrit une fois la liste arrivée.
 */
import { expect, type Page } from '@playwright/test'

/** La largeur de référence du bureau : la table sans cellule y laisse la colonne (spec §3.4). */
export const COLUMN_VIEWPORT = { width: 1280, height: 800 }

/** La forme des liens, lue sur leur boîte : fixe en colonne, dans le flux en pied de page. */
export async function expectPlacement(page: Page, placement: 'column' | 'footer') {
  await expect(page.getByRole('contentinfo')).toHaveCSS(
    'position',
    placement === 'column' ? 'fixed' : 'relative',
  )
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
