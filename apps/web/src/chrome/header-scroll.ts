/**
 * L'entête au défilement (spec §3.3), en logique pure : la position de défilement entre, l'état de
 * l'entête sort. Seuils repris du prototype retenu (`cadre.html`, variante « Retrait »), source de
 * mesure de la spec.
 */

/** Hauteur de l'entête (spec §3.3) : en deçà, elle reste toujours visible. */
const HEADER_HEIGHT = 56

/** Défilement cumulé dans un même sens qui la fait sortir ou revenir ; évite le battement. */
const TRAVEL_THRESHOLD = 8

/**
 * État de l'entête.
 *
 * - `detached` : la page n'est plus en haut — fond papier à 94 % et filet.
 * - `hidden` : sortie par le haut ; le focus clavier la ramène, ce que le CSS décide seul.
 * - `lastY`, `travel` : dernière position lue et défilement cumulé dans le sens courant, en px,
 *   positif vers le bas.
 */
export type HeaderScroll = {
  detached: boolean
  hidden: boolean
  lastY: number
  travel: number
}

/** L'entête en haut de page, avant tout défilement. */
export const headerAtTop: HeaderScroll = { detached: false, hidden: false, lastY: 0, travel: 0 }

/**
 * L'état de l'entête à une nouvelle position de défilement.
 *
 * @param previous L'état à la position précédente (`headerAtTop` au départ).
 * @param y La position lue, en px ; une valeur négative (rebond élastique au-dessus du haut de
 *   page) se lit comme le haut de page.
 * @returns Le nouvel état. À 56 px et moins, l'entête est visible et le cumul repart de zéro ; un
 *   changement de sens repart aussi de zéro ; au-delà de 8 px cumulés, elle sort (vers le bas) ou
 *   revient (vers le haut) ; à 8 px exactement, rien ne change.
 */
export function nextHeaderScroll(previous: HeaderScroll, y: number): HeaderScroll {
  const delta = y - previous.lastY
  const detached = y > 0

  if (y <= HEADER_HEIGHT) return { detached, hidden: false, lastY: y, travel: 0 }

  const travel =
    Math.sign(delta) === Math.sign(previous.travel) ? previous.travel + delta : delta
  const hidden =
    travel > TRAVEL_THRESHOLD ? true : travel < -TRAVEL_THRESHOLD ? false : previous.hidden

  return { detached, hidden, lastY: y, travel }
}
