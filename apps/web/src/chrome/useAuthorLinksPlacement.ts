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
 * chargement —, puis de nouveau au redimensionnement de la fenêtre et à chaque ajout ou retrait
 * d'élément dans la table (contrat et portée : `TABLE_CELL_SELECTOR`). Le calcul est
 * `authorLinksPlacement`, en logique pure.
 *
 * @param table La table, l'élément qui porte les cellules.
 * @returns `column` ou `footer` ; React ne rend de nouveau les liens qu'à un changement de forme.
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
      const margin = nearestCellMargin(cells, document.documentElement.clientWidth)
      setPlacement(authorLinksPlacement(window.innerWidth, margin))
    }

    update()
    const cellsChanged = new MutationObserver(update)
    cellsChanged.observe(root, { childList: true, subtree: true })
    // ponytail: une barre de défilement qui apparaît sans redimensionnement (page qui s'allonge)
    // ne relit pas la marge, ni une cellule redimensionnée sans changement du DOM ; un
    // `ResizeObserver` sur `<html>` et sur les cellules les couvrirait, quand #20 fera défiler.
    window.addEventListener('resize', update)
    return () => {
      cellsChanged.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [table])

  return placement
}
