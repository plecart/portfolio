import { useLayoutEffect, useRef, useState } from 'react'
import { stackFold } from './stackFold.ts'

/** La largeur de mise en page d'un élément, fractions comprises, sans sa transformation. */
const widthOf = (element: Element) => parseFloat(getComputedStyle(element).width)

/**
 * Le repli d'une liste de la stack à l'instant (`stackFold`), ses rubans tous rendus et le ruban
 * « +N » au bout : chaque ruban par sa rangée et son bord droit — le centre de sa boîte, que son
 * inclinaison ne déplace pas, plus sa demi-largeur.
 */
function measure(list: HTMLElement): number {
  const { left } = list.getBoundingClientRect()
  const slots = [...list.querySelectorAll<HTMLElement>(':scope > [data-ribbon]')].map((ribbon) => {
    const box = ribbon.getBoundingClientRect()
    return { top: ribbon.offsetTop, right: box.left + (box.width + widthOf(ribbon)) / 2 - left }
  })
  const more = list.querySelector(':scope > .project-more')!
  return stackFold(slots, parseFloat(getComputedStyle(list).columnGap) + widthOf(more), widthOf(list))
}

/**
 * Le repli d'une liste de la stack à deux rangées (spec §4.3), mesuré sur sa mise en page avant la
 * première peinture, puis de nouveau à chaque changement de sa taille repliée : sa largeur suit celle
 * de la colonne, et sa hauteur, une police arrivée après la mesure. Dépliée, elle ne se mesure pas :
 * le compte de son ruban-bouton, et son nom, ne changent pas ; elle se mesure de nouveau repliée.
 *
 * @param expanded La liste est dépliée.
 * @returns La liste, à poser sur son `<ul>`, puis le nombre de rubans à montrer, repliée ;
 *   `undefined` le temps d'une mesure, qui demande de les rendre tous, et le ruban « +N » au bout, à
 *   son compte le plus large.
 */
export function useStackFold(expanded: boolean) {
  const list = useRef<HTMLUListElement>(null)
  const [shown, setShown] = useState<number>()

  useLayoutEffect(() => {
    if (shown === undefined) setShown(measure(list.current!))
  }, [shown])

  useLayoutEffect(() => {
    if (expanded) return
    const observer = new ResizeObserver(() => setShown(undefined))
    observer.observe(list.current!)
    return () => observer.disconnect()
  }, [expanded])

  return [list, shown] as const
}
