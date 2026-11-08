import { useEffect, useState } from 'react'
import { clampView, containedSize, FIT, type Size, type Stage, type View } from './zoom.ts'

/**
 * La taille d'un élément, suivie à chaque redimensionnement.
 *
 * @returns `null` avant la première mesure.
 */
function useSize(element: HTMLElement | null): Size | null {
  const [size, setSize] = useState<Size | null>(null)

  useEffect(() => {
    if (!element) return
    const observer = new ResizeObserver(([{ contentRect }]) =>
      setSize({ width: contentRect.width, height: contentRect.height }),
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [element])

  return size
}

/**
 * La vue de la couche plein écran (issue #243) : son facteur et sa translation, bornés à la zone
 * d'image telle qu'elle est mesurée, la fenêtre pouvant changer de taille sous une vue. Elle part de
 * ×1, l'image entière.
 *
 * @param zone La zone d'image, `null` avant son montage.
 * @param natural La taille naturelle de l'image montrée, ou toute taille au même format.
 * @returns `shown`, la vue à rendre ; `box`, la taille de l'image à ×1, `null` avant la première
 *   mesure ; `glide`, la vue vient d'un pas — touche, double clic — qui glisse (spec §4.4), et non
 *   d'un geste que l'image suit ni d'un redimensionnement qui la borne ; `change`, `hold` et
 *   `reset`, qui la changent.
 */
export function useZoomView(zone: HTMLElement | null, natural: Size) {
  const size = useSize(zone)
  // `glide` : la zone mesurée quand un pas qui glisse a changé la vue ; un redimensionnement la
  // remplace, et la vue qu'il ramène dans ses bornes ne glisse pas.
  const [{ view, glide }, setState] = useState<{ view: View; held: View; glide: Size | null }>({
    view: FIT,
    held: FIT,
    glide: null,
  })
  const stage: Stage | null = size && { zone: size, natural }

  return {
    shown: stage ? clampView(view, stage) : FIT,
    box: stage && containedSize(stage.zone, natural),
    glide: glide !== null && glide === size,
    /**
     * Change la vue ; sans effet avant la première mesure. Chaque changement part du précédent,
     * même pas encore rendu : plusieurs pointeurs peuvent bouger entre deux rendus. Un `next` qui
     * rend la vue reçue telle quelle (`snapToFit` au-dessus de ×1,05) ne touche à rien : la fin
     * d'une molette ne coupe pas le glissement d'une touche pressée juste après.
     *
     * @param next La nouvelle vue, de la vue en place, de la zone et de la vue retenue (`hold`).
     * @param glides Un pas qui glisse ; par défaut, l'image suit sans retard.
     */
    change(next: (view: View, stage: Stage, held: View) => View, glides = false) {
      if (!stage) return
      setState((state) => {
        const current = clampView(state.view, stage)
        const view = next(current, stage, state.held)
        return view === current ? state : { ...state, view, glide: glides ? stage.zone : null }
      })
    },
    /**
     * Retient la vue en place : un pincement part d'elle à chacun de ses pas, sans cumuler les
     * bornes de ses pas précédents.
     */
    hold() {
      if (stage) setState((state) => ({ ...state, held: clampView(state.view, stage) }))
    },
    /** Remet l'image entière, d'un coup : changer d'image la remplace à ×1 (décision 7). */
    reset: () => setState({ view: FIT, held: FIT, glide: null }),
  }
}
