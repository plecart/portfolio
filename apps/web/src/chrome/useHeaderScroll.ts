import { useEffect, useState } from 'react'
import { headerAtTop, nextHeaderScroll } from './header-scroll.ts'

/**
 * L'état de l'entête au défilement de la fenêtre (spec §3.3).
 *
 * Lit `scrollY` une fois par image au plus — écoute passive de `scroll`, calcul au prochain
 * `requestAnimationFrame` —, et une première fois au montage, la page pouvant s'ouvrir défilée.
 * Lecture prouvée sur une page haute d'emblée (`e2e/table-cards.spec.ts`). La table la met moins à
 * l'épreuve : sa liste arrive après le chargement, et le navigateur ne restaure le défilement que
 * dans la hauteur des cadres — sur douze cartes et les trois cadres d'alors, 0 à 1280 px et 145 px
 * à 400 px (Chromium 156, mesuré le 2026-10-31, issue #168). Le calcul est `nextHeaderScroll`, en
 * logique pure.
 *
 * @returns `detached` (fond et filet) et `hidden` (sortie par le haut). Deux booléens, pour que
 *   React ne rende de nouveau l'entête qu'à un changement d'état, pas à chaque image.
 */
export function useHeaderScroll(): { detached: boolean; hidden: boolean } {
  const [detached, setDetached] = useState(false)
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    let scroll = headerAtTop
    let frame = 0
    const update = () => {
      frame = 0
      scroll = nextHeaderScroll(scroll, window.scrollY)
      setDetached(scroll.detached)
      setHidden(scroll.hidden)
    }
    const onScroll = () => {
      frame ||= requestAnimationFrame(update)
    }

    frame = requestAnimationFrame(update)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(frame)
    }
  }, [])

  return { detached, hidden }
}
