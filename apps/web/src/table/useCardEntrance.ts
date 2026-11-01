import { useEffect, type RefObject } from 'react'
import { cardColumns } from './cards.ts'

/** La part de la surface d'une cellule qui doit être dans l'écran pour qu'elle entre (spec §3.1). */
const ENTRY_THRESHOLD = 0.15

/**
 * L'entrée des cartes (spec §1.3, §3.1) : un seul `IntersectionObserver`, sur les cellules, immobiles
 * — seule la couche d'entrée qu'elles contiennent bouge. Une cellule à 15 % dans l'écran reçoit
 * `data-entered`, que la feuille lit, et n'est plus observée : une carte n'entre qu'une fois.
 *
 * Le retard vaut l'indice de colonne mesuré × `--delay-column`, et l'indice se relit à chaque
 * redimensionnement.
 *
 * @param grid La grille de la table.
 * @param projects Les projets rendus : les cellules à observer changent avec eux.
 */
export function useCardEntrance(grid: RefObject<HTMLElement | null>, projects: readonly unknown[]) {
  useEffect(() => {
    const table = grid.current
    if (!table || projects.length === 0) return
    const cells = [...table.querySelectorAll<HTMLElement>('.card')]

    const writeColumns = () => {
      const { gridTemplateColumns, columnGap } = getComputedStyle(table)
      const step = parseFloat(gridTemplateColumns) + parseFloat(columnGap)
      const lefts = cells.map((cell) => cell.getBoundingClientRect().left)
      cardColumns(lefts, step).forEach((column, index) => {
        cells[index].style.setProperty('--card-column', String(column))
      })
    }

    const observer = new IntersectionObserver(
      (records) => {
        for (const { isIntersecting, target } of records) {
          if (!isIntersecting) continue
          target.setAttribute('data-entered', '')
          observer.unobserve(target)
        }
      },
      { threshold: ENTRY_THRESHOLD },
    )

    writeColumns()
    cells.forEach((cell) => observer.observe(cell))
    window.addEventListener('resize', writeColumns)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', writeColumns)
    }
  }, [grid, projects])
}
