import { useLayoutEffect, useState, type RefObject } from 'react'
import {
  authorLinksPlacement,
  nearestCellMargin,
  TABLE_CELL_SELECTOR,
  type AuthorLinksPlacement,
} from './author-links-placement.ts'

/**
 * Une mutation qui peut changer la marge : un élément ajouté ou retiré, l'attribut de cellule posé
 * ou retiré, ou un autre attribut changé sur une cellule ou sur un élément qui en contient (la
 * grille). Jamais un attribut changé **dans** une cellule : sa pose et son animation y vivent
 * (contrat de `TABLE_CELL_SELECTOR`), et les relire forcerait une mise en page à chaque image.
 */
function mayMoveCells(record: MutationRecord): boolean {
  if (record.type === 'childList' || record.attributeName === 'data-table-cell') return true
  const target = record.target as Element
  return target.matches(TABLE_CELL_SELECTOR) || target.querySelector(TABLE_CELL_SELECTOR) !== null
}

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
  // Avant la première mesure, la forme d'une table sans cellule : celle de l'attente à l'adresse
  // d'une fiche (§5.1), que la mesure ne fait donc pas changer sous la page « fiche ouverte ».
  const [placement, setPlacement] = useState(() => authorLinksPlacement(window.innerWidth, null))

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
    const cellsChanged = new MutationObserver((records) => {
      if (records.some(mayMoveCells)) update()
    })
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
