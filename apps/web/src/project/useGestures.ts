import { type PointerEvent, useEffect, useEffectEvent, useRef } from 'react'
import { swipeStep } from './project.ts'
import type { Point } from './zoom.ts'

/**
 * Ce qu'un appui peut parcourir et rester un toucher, en px : la `tapDistance` par défaut de
 * d3-zoom (doc de d3-zoom, lue par context7 le 2026-11-08). Au-delà, c'est un glisser.
 */
const TAP_SLOP = 10

/**
 * Le double toucher, une seule voie pour la souris, le stylet et le doigt : un second toucher qui
 * commence au plus 500 ms après la fin du premier, à 20 px de lui au plus. 20 px : la tolérance du
 * double tape de Chromium 156 (`dblclick` émis à 20 px d'écart, pas à 25) ; 500 ms : au-delà de son
 * délai au doigt (350 ms passent, 400 non), pour une souris réglée lentement — mesuré le
 * 2026-11-08, Pixel 5 émulé, `touch-action: none`.
 */
const DOUBLE_TAP = { delay: 500, distance: 20 }

/**
 * La fin d'un zoom à la molette : aucun cran depuis 150 ms, le délai de d3-zoom (doc de d3-zoom,
 * « Zoom events », note 7, lue par context7 le 2026-11-08).
 */
const WHEEL_END_DELAY = 150

/**
 * Le zoom d'une molette, par unité de `deltaMode` (pixel, ligne, page) : le facteur vaut 2 puissance
 * (−`deltaY` × ce taux), un cran de 100 px zoomant de 15 % — le `wheelDelta` par défaut de d3-zoom
 * (même lecture). Le pincement d'un pavé tactile arrive en molette, Ctrl enfoncé (MDN,
 * `MouseEvent.ctrlKey`, lu par context7 le 2026-11-08), à pas fins : d3-zoom en décuple le taux.
 */
const WHEEL_RATES = [0.002, 0.05, 1]
const PINCH_WHEEL_BOOST = 10

/** Le facteur de zoom d'une molette. */
function wheelFactor({ deltaY, deltaMode, ctrlKey }: WheelEvent): number {
  return 2 ** (-deltaY * WHEEL_RATES[deltaMode] * (ctrlKey ? PINCH_WHEEL_BOOST : 1))
}

const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y)
const middle = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 })
const minus = (a: Point, b: Point): Point => ({ x: a.x - b.x, y: a.y - b.y })

/** Le point d'un événement de pointeur ou de molette, dans la fenêtre. */
const clientPoint = ({ clientX, clientY }: { clientX: number; clientY: number }): Point => ({
  x: clientX,
  y: clientY,
})

/** Un point de la fenêtre, rapporté au coin haut gauche d'un élément. */
function localPoint(element: Element, { x, y }: Point): Point {
  const { left, top } = element.getBoundingClientRect()
  return { x: x - left, y: y - top }
}

/** Ce que les gestes demandent ; un point s'y compte depuis le coin haut gauche de l'élément. */
export type GestureHandlers = {
  /** Un pointeur seul glisse de ce déplacement, en px. */
  onDrag: (delta: Point) => void
  /** Une molette zoome de ce facteur, à ce point. */
  onZoom: (factor: number, point: Point) => void
  /** Un pincement commence : ses pas partiront de la vue en place. */
  onPinchStart: () => void
  /**
   * Un pas du pincement, depuis son début : ses deux pointeurs se sont écartés de ce facteur, et
   * leur milieu est passé de `from` à `to`.
   */
  onPinch: (factor: number, from: Point, to: Point) => void
  /** Un zoom s'achève : le geste qui a pincé finit, ou la molette se tait (`WHEEL_END_DELAY`). */
  onZoomEnd: () => void
  /** Un double toucher, à ce point. */
  onDoubleTap: (point: Point) => void
  /** Un balayage franc d'un doigt ou d'un stylet, de ce pas (`swipeStep`). */
  onSwipe: (step: number) => void
  /**
   * Un toucher sur le fond : l'élément lui-même, hors de ses enfants. Un toucher commencé moins de
   * `DOUBLE_TAP.delay` après l'apparition de l'élément n'en est pas un : c'est le second temps du
   * double clic qui l'a fait paraître dès le premier.
   */
  onBackgroundTap: () => void
}

/** Les deux premiers pointeurs d'un pincement, à son début, dans la fenêtre. */
type Pinch = { spread: number; middle: Point }

/** Un geste en cours, du premier appui au dernier relâché. */
type Gesture = {
  /** Le premier appui, dans la fenêtre, et son instant (`timeStamp`). */
  start: Point
  time: number
  /** Il a commencé sur le fond. */
  onBackground: boolean
  /** Un doigt ou un stylet, qui balaie ; une souris ne balaie pas (spec §1.10). */
  swipes: boolean
  /** Sorti de `TAP_SLOP` : ce n'est plus un toucher. */
  moved: boolean
  /** Un second pointeur l'a rejoint : il ne finit ni en toucher ni en balayage. */
  pinched: boolean
  /** Le pincement en cours, tant que deux pointeurs au moins sont posés. */
  pinch: Pinch | null
}

/**
 * Les gestes d'un élément, en événements de pointeur natifs (issue #243, décision 4) : glisser,
 * pincer, double toucher, balayer, toucher le fond — et la molette. Un appui sur un bouton de
 * l'élément lui reste ; tout autre appui capture son pointeur, et un geste sorti de l'élément y
 * finit. Seul un toucher, qui ne glisse pas, compte : un glisser commencé sur l'image et relâché sur
 * le fond n'est pas un toucher du fond, quand le `click` de son relâché partirait de leur ancêtre
 * commun. L'élément porte `touch-action: none` : le navigateur ne prend aucun geste du doigt.
 *
 * Un pincement suit ses deux premiers pointeurs, et chacun de ses pas part de son début : les pas
 * successifs des deux doigts, qui font osciller leur milieu, ne cumulent pas les bornes de la vue.
 *
 * Un double toucher, ce sont deux touchers de suite : tout autre geste entre eux — glisser,
 * balayage, pincement, molette, geste interrompu — le rompt, et ce qui change la vue ou l'image
 * hors des gestes le rompt par `forgetTap`.
 *
 * @param element L'élément, `null` avant son montage : son apparition se date, et sa molette s'y
 *   écoute.
 * @param handlers Ce que chaque geste demande.
 * @returns `listeners`, les gestionnaires de pointeur à poser sur l'élément ; `forgetTap`, qui
 *   rompt un double toucher commencé.
 */
export function useGestures(element: HTMLElement | null, handlers: GestureHandlers) {
  const pointers = useRef(new Map<number, Point>())
  const gesture = useRef<Gesture | null>(null)
  const lastTap = useRef<{ time: number; point: Point } | null>(null)
  /** L'apparition de l'élément, sur l'horloge des `timeStamp` (`performance.now`). */
  const appearedAt = useRef(0)

  /** Rompt un double toucher commencé : son premier toucher s'oublie. */
  const forgetTap = () => {
    lastTap.current = null
  }

  const onWheel = useEffectEvent((event: WheelEvent) => {
    event.preventDefault()
    forgetTap()
    const point = localPoint(event.currentTarget as Element, clientPoint(event))
    handlers.onZoom(wheelFactor(event), point)
  })
  const onWheelEnd = useEffectEvent(() => handlers.onZoomEnd())

  useEffect(() => {
    if (!element) return
    appearedAt.current = performance.now()
    let wheelEnd: ReturnType<typeof setTimeout> | undefined
    const listener = (event: WheelEvent) => {
      onWheel(event)
      clearTimeout(wheelEnd)
      wheelEnd = setTimeout(() => onWheelEnd(), WHEEL_END_DELAY)
    }
    // React pose `onWheel` en passif (react-dom 19.3.1, `addTrappedEventListener`), où
    // `preventDefault` est sans effet : la page défilerait, ou zoomerait au pincement du pavé tactile.
    element.addEventListener('wheel', listener, { passive: false })
    return () => {
      element.removeEventListener('wheel', listener)
      clearTimeout(wheelEnd)
    }
  }, [element])

  /** Le pincement des deux premiers pointeurs posés, s'il y en a deux ; il commence. */
  const startPinch = (current: Gesture) => {
    const [a, b] = pointers.current.values()
    current.pinch = b ? { spread: distance(a, b), middle: middle(a, b) } : null
    if (current.pinch) handlers.onPinchStart()
  }

  /** Le toucher qui achève un geste : le fond, ou la seconde moitié d'un double toucher. */
  const tap = (event: PointerEvent<HTMLElement>, current: Gesture) => {
    if (current.onBackground) {
      // Plus tôt, c'est le second temps du double clic qui a fait paraître l'élément.
      if (current.time - appearedAt.current > DOUBLE_TAP.delay) handlers.onBackgroundTap()
      return
    }
    const point = clientPoint(event)
    const last = lastTap.current
    const double =
      last !== null &&
      current.time - last.time <= DOUBLE_TAP.delay &&
      distance(point, last.point) <= DOUBLE_TAP.distance
    lastTap.current = double ? null : { time: event.timeStamp, point }
    if (double) handlers.onDoubleTap(localPoint(event.currentTarget, point))
  }

  const listeners = {
    onPointerDown(event: PointerEvent<HTMLElement>) {
      const { target, currentTarget, pointerId, button, pointerType, timeStamp } = event
      if (button !== 0 || (target as Element).closest('button')) return
      currentTarget.setPointerCapture(pointerId)
      const point = clientPoint(event)
      pointers.current.set(pointerId, point)
      const current = gesture.current
      if (!current) {
        gesture.current = {
          start: point,
          time: timeStamp,
          onBackground: target === currentTarget,
          swipes: pointerType !== 'mouse',
          moved: false,
          pinched: false,
          pinch: null,
        }
      } else if (pointers.current.size === 2) {
        current.pinched = true
        startPinch(current)
      }
    },

    onPointerMove(event: PointerEvent<HTMLElement>) {
      const before = pointers.current.get(event.pointerId)
      const current = gesture.current
      if (!before || !current) return
      const point = clientPoint(event)
      pointers.current.set(event.pointerId, point)
      if (distance(point, current.start) > TAP_SLOP) current.moved = true
      const { pinch } = current
      if (!pinch) return handlers.onDrag(minus(point, before))
      if (pinch.spread === 0) return
      const [a, b] = pointers.current.values()
      const local = (at: Point) => localPoint(event.currentTarget, at)
      handlers.onPinch(distance(a, b) / pinch.spread, local(pinch.middle), local(middle(a, b)))
    },

    onPointerUp(event: PointerEvent<HTMLElement>) {
      const current = gesture.current
      if (!pointers.current.delete(event.pointerId) || !current) return
      // Un pointeur levé d'un pincement : les deux premiers qui restent le reprennent, ou le dernier
      // glisse seul.
      if (pointers.current.size > 0) return startPinch(current)
      gesture.current = null
      if (!current.moved && !current.pinched) return tap(event, current)
      forgetTap()
      if (current.pinched) return handlers.onZoomEnd()
      const { x, y } = clientPoint(event)
      const step = current.swipes ? swipeStep(x - current.start.x, y - current.start.y) : 0
      if (step !== 0) handlers.onSwipe(step)
    },

    /** Un geste que le navigateur interrompt est oublié ; s'il pinçait, le zoom s'achève. */
    onPointerCancel() {
      if (gesture.current?.pinched) handlers.onZoomEnd()
      pointers.current.clear()
      gesture.current = null
      forgetTap()
    },
  }

  return { listeners, forgetTap }
}
