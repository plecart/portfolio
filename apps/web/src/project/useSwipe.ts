import { type MouseEvent, type PointerEvent, useRef } from 'react'
import { swipeStep } from './project.ts'
import type { Point } from './zoom.ts'

/**
 * Le balayage d'un élément (spec §4.4), en événements de pointeur natifs : ni suivi du doigt, ni
 * souris, qui ne glisse pas (§1.10). `pointercancel`, émis quand le navigateur prend la main pour
 * défiler, oublie le geste.
 *
 * @param onStep Reçoit le pas d'un balayage franc : `1` vers la gauche, `-1` vers la droite.
 * @returns Les gestionnaires à poser sur l'élément.
 */
export function useSwipe(onStep: (step: number) => void) {
  const start = useRef<Point | null>(null)

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

/**
 * Le clic d'un élément qu'on balaie (spec §4.4) : un geste qui a la forme d'un balayage n'en est
 * pas un, quel que soit le pointeur. Au doigt, Chromium n'émet pas de clic après un balayage ; un
 * stylet qui balaie, une souris qui glisse, si (Chromium 156, mesuré le 2026-11-08).
 *
 * @param onClick Reçoit un clic qui n'est pas un balayage, y compris un clic sans appui suivi,
 *   comme celui d'un script.
 * @returns Les gestionnaires à poser sur l'élément.
 */
export function useClickWithoutSwipe(onClick: () => void) {
  const start = useRef<Point | null>(null)

  return {
    onPointerDown: ({ clientX: x, clientY: y }: PointerEvent) => {
      start.current = { x, y }
    },
    onClick: ({ clientX, clientY }: MouseEvent) => {
      const from = start.current
      start.current = null
      if (from && swipeStep(clientX - from.x, clientY - from.y) !== 0) return
      onClick()
    },
  }
}
