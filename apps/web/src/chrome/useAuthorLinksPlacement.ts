import { useLayoutEffect, useState, type RefObject } from 'react'
import {
  authorLinksPlacement,
  nearestCellMargin,
  TABLE_CELL_SELECTOR,
  type AuthorLinksPlacement,
} from './author-links-placement.ts'

/**
 * La forme des liens de l'auteur, mesurée sur la table (spec §3.4 ; brief de #18, décision 1).
 *
 * Mesure avant la première peinture — les liens ne sautent pas du pied de page à la colonne au
 * chargement —, puis de nouveau au redimensionnement de la fenêtre, à chaque ajout ou retrait
 * d'élément dans la table et à chaque attribut qui fait, défait ou redimensionne une cellule
 * (contrat et portée : `TABLE_CELL_SELECTOR`). Le calcul est `nearestCellMargin` puis
 * `authorLinksPlacement`, en logique pure.
 *
 * @param table La table, l'élément qui porte les cellules.
 * @returns `column` ou `footer` ; React ne met à jour le DOM des liens qu'à un changement de forme.
 */
export function useAuthorLinksPlacement(
  table: RefObject<HTMLElement | null>,
): AuthorLinksPlacement {
  const [placement, setPlacement] = useState<AuthorLinksPlacement>('footer')

  useLayoutEffect(() => {
    const root = table.current
    if (!root) return
    const update = () => {
      const cells = [...root.querySelectorAll(TABLE_CELL_SELECTOR)].map((cell) =>
        cell.getBoundingClientRect(),
      )
      const windowWidth = window.innerWidth
      const viewportWidth = document.documentElement.clientWidth
      const margin = nearestCellMargin(cells, { windowWidth, viewportWidth })
      setPlacement(authorLinksPlacement(windowWidth, margin))
    }

    update()
    const cellsChanged = new MutationObserver(update)
    cellsChanged.observe(root, {
      childList: true,
      subtree: true,
      attributeFilter: ['data-table-cell', 'hidden', 'style', 'class'],
    })
    window.addEventListener('resize', update)
    return () => {
      cellsChanged.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [table])

  return placement
}
