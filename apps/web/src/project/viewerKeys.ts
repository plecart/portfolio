/**
 * Le clavier de la couche plein écran (issue #243, décision 6), en logique pure : ce qu'une touche
 * commande à la couche selon son zoom, ou rien — la touche reste alors au navigateur. La couche,
 * qui retient le focus, applique la commande.
 */
import { directionStep } from './project.ts'
import type { Point } from './zoom.ts'

/** Le pas d'un déplacement au clavier, en px (spec §4.4). */
const PAN_STEP = 100

/**
 * Le déplacement de chaque flèche, une fois zoomé : celui du défilement d'une page, qui montre ce
 * qui est plus loin dans le sens de la flèche — l'image part à l'opposé.
 */
const PAN_KEYS = new Map<string, Point>([
  ['ArrowLeft', { x: PAN_STEP, y: 0 }],
  ['ArrowRight', { x: -PAN_STEP, y: 0 }],
  ['ArrowUp', { x: 0, y: PAN_STEP }],
  ['ArrowDown', { x: 0, y: -PAN_STEP }],
])

/** Le pas de zoom de chaque touche, d'une unité (spec §4.4). */
const ZOOM_KEYS = new Map([
  ['+', 1],
  ['-', -1],
])

/** Ce qu'une touche commande : zoomer de ce pas, déplacer l'image de ce vecteur, changer d'image. */
export type KeyCommand = { zoom: number } | { pan: Point } | { step: number }

/** Une touche pressée et ses modificateurs, comme un `KeyboardEvent` les porte. */
type Pressed = {
  key: string
  shiftKey: boolean
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
}

/**
 * La commande d'une touche dans la couche. + et − zooment d'une unité, sans effet à leur borne ; à
 * ×1, ← et → changent d'image ; zoomé, ← → ↑ ↓ déplacent l'image. Ctrl, Cmd et Alt laissent la
 * touche au navigateur ; Maj ne compte que pour les flèches, le + s'obtenant avec Maj sur certains
 * claviers.
 *
 * @param pressed La touche et ses modificateurs.
 * @param state `zoomed`, la couche au-delà de ×1 ; `navigable`, plus d'une image à montrer.
 * @returns `undefined` pour une touche que la couche laisse au navigateur.
 */
export function keyCommand(
  { key, shiftKey, ctrlKey, metaKey, altKey }: Pressed,
  { zoomed, navigable }: { zoomed: boolean; navigable: boolean },
): KeyCommand | undefined {
  if (ctrlKey || metaKey || altKey) return
  const zoom = ZOOM_KEYS.get(key)
  if (zoom !== undefined) return { zoom }
  if (shiftKey) return
  if (zoomed) {
    const pan = PAN_KEYS.get(key)
    return pan && { pan }
  }
  const step = directionStep(key)
  if (navigable && step !== null) return { step }
}
