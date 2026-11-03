/**
 * La géométrie de la chorégraphie d'une fiche (spec §4.6), sans document : des boîtes de
 * `getBoundingClientRect` en entrée, des images clés de la Web Animations API en sortie. La conduite
 * des animations vit dans `useChoreography`.
 */

/** Une boîte à l'écran : ce que `getBoundingClientRect` en donne, ici. */
type Box = { left: number; top: number; width: number; height: number }

/** Un point, ou un écart, en pixels. */
type Point = { x: number; y: number }

/** La partie linéaire d'une transformation, telle que `DOMMatrix` la lit. */
type Linear = { a: number; b: number; c: number; d: number }

/**
 * Une image clé de la Web Animations API — des propriétés CSS et leurs valeurs, `offset` compris —,
 * écrite sans le type du DOM, que les tests de Node ne chargent pas.
 */
export type Frame = Record<string, string | number>

/** Une translation nulle. */
export const NO_SHIFT = '0px 0px'

/** Un élément volant à sa place : ni translation ni échelle de plus que sa feuille ne lui donne. */
export const AT_REST: Frame = { translate: NO_SHIFT, scale: '1 1' }

/** Le creux d'opacité d'un ruban en vol (spec §4.6) : 35 % entre 30 % et 70 % du trajet. */
const RIBBON_DIP = { opacity: 0.35, from: 0.3, to: 0.7 }

/**
 * La durée d'un jeton (`--dur-open: 280ms`, `--dur-pulse: 1.8s`), en millisecondes : la Web
 * Animations API prend des nombres, pas des `var()`.
 */
export function milliseconds(token: string): number {
  const amount = parseFloat(token)
  return token.trim().endsWith('ms') ? amount : amount * 1000
}

/**
 * Le pivot d'un élément — son origine de transformation, que sa rotation laisse en place — mesuré
 * depuis le coin haut gauche de sa boîte englobante. Sans rotation, c'est l'origine elle-même ;
 * tourné, son coin n'est plus celui de la boîte.
 *
 * @param matrix Sa transformation calculée.
 * @param width Sa largeur de mise en page, sans transformation (`offsetWidth`) ; `height` de même.
 * @param origin Son origine de transformation, depuis le coin haut gauche de sa mise en page.
 */
export function pivotIn({ a, b, c, d }: Linear, width: number, height: number, origin: Point): Point {
  const corners = [
    [0, 0],
    [width, 0],
    [0, height],
    [width, height],
  ].map(([x, y]) => [x - origin.x, y - origin.y])
  return {
    x: -Math.min(...corners.map(([x, y]) => a * x + c * y)),
    y: -Math.min(...corners.map(([x, y]) => b * x + d * y)),
  }
}

/**
 * L'image clé qui pose un élément sur son homologue (spec §4.6) : une translation, puis une échelle
 * non uniforme autour de son pivot, par les propriétés `translate` et `scale`, qui s'ajoutent à sa
 * propre transformation sans la remplacer. L'interpolation de l'une et de l'autre fait le même
 * trajet quel que soit le pivot : le haut gauche de la spec n'en est qu'un.
 *
 * @param from La boîte de l'homologue, sur la carte.
 * @param to La boîte de l'élément au repos.
 * @param pivot Son pivot dans cette boîte (`pivotIn`).
 */
export function flightStart(from: Box, to: Box, pivot: Point): Frame {
  const sx = from.width / to.width
  const sy = from.height / to.height
  const x = from.left - to.left + (sx - 1) * pivot.x
  const y = from.top - to.top + (sy - 1) * pivot.y
  return { translate: `${x}px ${y}px`, scale: `${sx} ${sy}` }
}

/**
 * Le recul d'une carte (spec §4.6) : `distance` pixels dans la direction du centre de la carte
 * ouverte au sien. Deux centres confondus n'ont pas de direction : pas de recul, plutôt qu'une
 * direction arbitraire.
 */
export function recoil(opened: Box, card: Box, distance: number): Point {
  const x = card.left + card.width / 2 - (opened.left + opened.width / 2)
  const y = card.top + card.height / 2 - (opened.top + opened.height / 2)
  const length = Math.hypot(x, y)
  return length === 0 ? { x: 0, y: 0 } : { x: (x / length) * distance, y: (y / length) * distance }
}

/**
 * Les images clés d'un ruban en vol de `start` à `end`, à l'aller comme au retour (spec §4.6) :
 * plein aux deux bouts, sauf un départ qui porte son opacité — celle d'un ruban relevé en plein vol.
 */
export function dimmedKeyframes(start: Frame, end: Frame): Frame[] {
  const { opacity, from, to } = RIBBON_DIP
  return [
    { opacity: 1, ...start },
    { offset: from, opacity },
    { offset: to, opacity },
    { ...end, opacity: 1 },
  ]
}
