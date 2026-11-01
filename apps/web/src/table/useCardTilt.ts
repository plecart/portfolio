import { useRef, type PointerEvent } from 'react'
import { cardTilt } from './cards.ts'

/** Un pointeur fin, qui survole, hors mouvement réduit (spec §4.1, §6.1, §6.3). */
const TILTING_DEVICE =
  '(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)'

/**
 * L'inclinaison d'une carte sous la souris (spec §4.1) : les gestes se posent sur la cellule,
 * immobile, et l'inclinaison s'écrit sur sa couche par le CSSOM — la CSP de production bloquerait un
 * attribut `style` analysé. La feuille assure le retour en 240 ms à la sortie, et ne transite pas
 * pendant le déplacement.
 *
 * Seul le déplacement incline, jamais l'entrée : sous un stylet, Chromium rejoue un survol de type
 * `mouse`, sans `pointermove`, alors qu'une souris qui entre émet les deux à la fois (Chromium 156,
 * stylet simulé par CDP, mesuré le 2026-11-01). Une carte qui arrive sous une souris immobile
 * attend donc qu'elle bouge.
 *
 * @returns La couche d'inclinaison et les gestes de la cellule.
 */
export function useCardTilt() {
  const layer = useRef<HTMLDivElement>(null)

  const follow = (event: PointerEvent<HTMLElement>) => {
    if (event.pointerType !== 'mouse' || !matchMedia(TILTING_DEVICE).matches) return
    const { rotateX, rotateY } = cardTilt(event, event.currentTarget.getBoundingClientRect())
    layer.current?.style.setProperty('transform', `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`)
  }

  const settle = () => {
    layer.current?.style.removeProperty('transform')
  }

  return { layer, onPointerMove: follow, onPointerLeave: settle }
}
