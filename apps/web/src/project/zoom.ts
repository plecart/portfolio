/**
 * Le zoom de la couche plein écran (issue #243), en logique pure : le facteur, borné de ×1 à ×4, et
 * la translation, bornée à l'image. Sans DOM : la couche mesure sa zone d'image et lit la taille
 * naturelle de l'image, puis écrit la vue rendue en `transform`.
 *
 * À ×1, l'image tient entière dans la zone et y est centrée (`containedSize`). Une vue la translate
 * depuis cette position, puis l'agrandit autour de son centre : `translate(x, y) scale(facteur)`,
 * origine au centre de l'image.
 */

/** Une largeur et une hauteur, en px. */
export type Size = { width: number; height: number }

/**
 * Un point ou un déplacement, en px ; un point du zoom se compte depuis le coin haut gauche de la
 * zone d'image.
 */
export type Point = { x: number; y: number }

/** Une vue : le facteur, et la translation de l'image depuis sa position centrée, en px. */
export type View = { scale: number; x: number; y: number }

/** La zone d'image, et la taille naturelle de l'image qu'elle montre — seul son format compte. */
export type Stage = { zone: Size; natural: Size }

/** Les bornes du facteur, fixes sur toute image et tout écran (issue #243, décision 3). */
export const MIN_SCALE = 1
export const MAX_SCALE = 4

/** L'image entière, centrée : la vue d'ouverture, et celle de toute image montrée. */
export const FIT: View = { scale: MIN_SCALE, x: 0, y: 0 }

/** `value` ramenée entre `min` et `max`. */
function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

/**
 * La taille de l'image à ×1 : entière dans la zone, comme `object-fit: contain` — agrandie si elle
 * est plus petite que la zone.
 *
 * @param zone La zone d'image.
 * @param natural La taille naturelle de l'image, ou toute taille au même format.
 * @returns La taille affichée, au même format, qui touche la zone sur au moins un axe.
 */
export function containedSize(zone: Size, natural: Size): Size {
  const ratio = Math.min(zone.width / natural.width, zone.height / natural.height)
  return { width: natural.width * ratio, height: natural.height * ratio }
}

/**
 * La translation d'une vue ramenée dans ses bornes : sur chaque axe, aucun bord de l'image agrandie
 * ne s'écarte du bord de la zone qu'il dépasse, et la translation est nulle sur un axe où l'image
 * tient. Sert aussi quand la zone change de taille sous une vue.
 *
 * @param view La vue, son facteur déjà dans les bornes.
 * @param stage La zone et l'image.
 * @returns La même vue, sa translation bornée ; jamais −0, que la vue d'ouverture n'égalerait pas.
 */
export function clampView({ scale, x, y }: View, stage: Stage): View {
  const shown = containedSize(stage.zone, stage.natural)
  // Le débord de l'image agrandie, de part et d'autre de la zone ; `+ 0` change −0 en 0.
  const limit = (value: number, side: keyof Size) => {
    const bound = Math.max(0, (shown[side] * scale - stage.zone[side]) / 2)
    return clamp(value, -bound, bound) + 0
  }
  return { scale, x: limit(x, 'width'), y: limit(y, 'height') }
}

/**
 * Le zoom vers un facteur, au point visé : le point de l'image sous ce point y reste, puis la
 * translation est bornée (`clampView`), ce qui peut l'en écarter près d'un bord.
 *
 * @param view La vue en place.
 * @param scale Le facteur demandé, ramené de ×1 à ×4 : à sa borne, la vue ne change pas.
 * @param point Le point visé, dans la zone ; son centre pour un zoom à la touche.
 * @param stage La zone et l'image.
 * @returns La nouvelle vue.
 */
export function zoomAt(view: View, scale: number, point: Point, stage: Stage): View {
  const next = clamp(scale, MIN_SCALE, MAX_SCALE)
  const ratio = next / view.scale
  // Le point visé, depuis le centre de la zone : la translation y garde le même point de l'image.
  const dx = point.x - stage.zone.width / 2
  const dy = point.y - stage.zone.height / 2
  return clampView(
    { scale: next, x: dx - ratio * (dx - view.x), y: dy - ratio * (dy - view.y) },
    stage,
  )
}

/**
 * Le déplacement de l'image, borné (`clampView`) : à ×1, elle ne bouge pas.
 *
 * @param view La vue en place.
 * @param delta Le déplacement demandé, en px, positif vers la droite et vers le bas.
 * @param stage La zone et l'image.
 * @returns La nouvelle vue, au même facteur.
 */
export function panBy(view: View, delta: Point, stage: Stage): View {
  return clampView({ ...view, x: view.x + delta.x, y: view.y + delta.y }, stage)
}
