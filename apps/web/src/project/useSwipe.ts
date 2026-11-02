import { type PointerEvent, useRef } from 'react'
import { swipeStep } from './project.ts'

/**
 * Le balayage d'un élément (spec §4.4), en événements de pointeur natifs : ni suivi du doigt, ni
 * souris, qui ne glisse pas (§1.10). `pointercancel`, émis quand le navigateur prend la main pour
 * défiler, oublie le geste.
 *
 * @param onStep Reçoit le pas d'un balayage franc : `1` vers la gauche, `-1` vers la droite.
 * @returns Les gestionnaires à poser sur l'élément.
 */
export function useSwipe(onStep: (step: number) => void) {
  const start = useRef<{ x: number; y: number } | null>(null)

  return {
    onPointerDown: ({ pointerType, clientX: x, clientY: y }: PointerEvent) => {
      start.current = pointerType === 'mouse' ? null : { x, y }
    },
    onPointerUp: ({ clientX, clientY }: PointerEvent) => {
      if (!start.current) return
      const step = swipeStep(clientX - start.current.x, clientY - start.current.y)
      start.current = null
      if (step !== 0) onStep(step)
    },
    onPointerCancel: () => {
      start.current = null
    },
  }
}
