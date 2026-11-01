import { useEffect, useState, type MouseEvent } from 'react'
import { TABLE_CELL_SELECTOR } from '../chrome/author-links-placement.ts'

/** Un appareil à survol révèle sans toucher : son clic ouvre d'emblée (spec §6.1). */
const HOVER_DEVICE = '(hover: hover)'

/**
 * La révélation au toucher (spec §1.7, §4.1), une carte à la fois, tenue au niveau de la table. Sur
 * un appareil sans survol, le premier `click` sur une carte la révèle au lieu de suivre le lien ; le
 * suivant le suit. Un `click` clavier, sans contact (`detail` à 0), ouvre directement (§6.2).
 *
 * La révélation s'achève au `pointerdown` hors des cellules, et non au `click`, qu'iOS n'émet pas sur
 * un élément non cliquable. L'écouteur n'existe que pendant une révélation.
 *
 * @returns Le slug de la carte révélée, et le geste à poser sur le `click` d'une carte.
 */
export function useTouchReveal(): {
  revealed: string | null
  revealOnTouch: (event: MouseEvent, slug: string) => void
} {
  const [revealed, setRevealed] = useState<string | null>(null)
  const revealing = revealed !== null

  useEffect(() => {
    if (!revealing) return
    const endOutsideCells = ({ target }: PointerEvent) => {
      if (!(target as Element).closest(TABLE_CELL_SELECTOR)) setRevealed(null)
    }
    document.addEventListener('pointerdown', endOutsideCells)
    return () => document.removeEventListener('pointerdown', endOutsideCells)
  }, [revealing])

  const revealOnTouch = (event: MouseEvent, slug: string) => {
    if (event.detail === 0 || slug === revealed || matchMedia(HOVER_DEVICE).matches) return
    event.preventDefault()
    setRevealed(slug)
  }

  return { revealed, revealOnTouch }
}
