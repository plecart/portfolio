/**
 * Le repli d'un groupe de la stack de la fiche à deux rangées (spec §4.3 ; issue #255), en logique
 * pure : la mise en page de ses rubans, mesurée tous rendus, en entrée ; combien en montrer, en
 * sortie. La mesure vit dans `useStackFold`.
 */

/**
 * Un ruban de la liste, mesuré : sa rangée, par le haut de sa boîte, et son bord droit, depuis le
 * bord gauche de la liste.
 */
export type Slot = { top: number; right: number }

/**
 * Combien de rubans montrer pour tenir en deux rangées (spec §4.3) : tous s'ils y tiennent ; sinon,
 * ceux des deux premières rangées, moins ceux que le ruban « +N » repousse dans le repli en prenant
 * la dernière place de la deuxième.
 *
 * @param slots Les rubans, dans l'ordre de la liste.
 * @param more La place du ruban « +N » au bout d'une rangée : l'écart qui le précède et sa largeur.
 * @param width La largeur de la liste.
 */
export function stackFold(slots: readonly Slot[], more: number, width: number): number {
  const [, second, third] = [...new Set(slots.map(({ top }) => top))]
  if (third === undefined) return slots.length
  let shown = slots.findIndex(({ top }) => top === third)
  while (slots[shown - 1].top === second && slots[shown - 1].right + more > width) shown -= 1
  return shown
}
