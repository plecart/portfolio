/**
 * La forme des liens de l'auteur (spec §3.4, §6.1 ; brief de #18, décision 1), en logique pure :
 * la largeur de la fenêtre et les cellules de la table entrent, colonne fixe ou pied de page sort.
 */

/**
 * Le contrat « cellule de la table », par lequel la table déclare ce que la mesure regarde : un
 * cadre de chargement (#19) ou une carte (#20) porte l'attribut `data-table-cell` sur sa **boîte
 * de grille** — l'élément que la grille place, sans transformation : la pose et l'animation
 * d'entrée vont sur un élément enfant, sinon la mesure suivrait l'inclinaison et la montée.
 *
 * Quatre voies changent la marge ; `useAuthorLinksPlacement` en relit deux — la fenêtre
 * redimensionnée, un élément ajouté ou retiré dans la table. Les deux autres restent à la charge
 * de la table : une cellule redimensionnée sans changement du DOM (la table remplace une cellule
 * plutôt que de la redimensionner), et une barre de défilement qui apparaît ou disparaît sans
 * redimensionnement (voir le `ponytail:` du crochet).
 */
export const TABLE_CELL_SELECTOR = '[data-table-cell]'

/**
 * Le point de rupture unique du site (spec §6.1) : en dessous, toujours le pied de page. Le même
 * que `--breakpoint-sm` d'`index.css`, chacun tenu à 600 par son test.
 */
const BREAKPOINT = 600

/** La marge qui admet la colonne : 36 px de disque, 24 du bord, 16 de garde (spec §3.4). */
const COLUMN_MARGIN = 76

/** Colonne fixe en bas à droite, ou pied de page après la table. */
export type AuthorLinksPlacement = 'column' | 'footer'

/**
 * La marge entre le bord de la fenêtre et la cellule la plus proche (spec §3.4), des deux côtés,
 * comme au prototype retenu (`cadre.html`, variante « Retrait »).
 *
 * @param cells Les bords des cellules, en px depuis le bord gauche de la fenêtre
 *   (`getBoundingClientRect`).
 * @param viewportWidth La largeur visible de la fenêtre, barre de défilement exclue
 *   (`clientWidth`) : c'est depuis son bord que la colonne se pose à 24 px.
 * @returns La plus petite marge, à gauche ou à droite, sur toutes les cellules ; `null` sans
 *   cellule.
 */
export function nearestCellMargin(
  cells: readonly { left: number; right: number }[],
  viewportWidth: number,
): number | null {
  if (cells.length === 0) return null
  return Math.min(...cells.map((cell) => Math.min(cell.left, viewportWidth - cell.right)))
}

/**
 * La forme des liens.
 *
 * @param windowWidth La largeur de la fenêtre comme la lit une requête média (`innerWidth`) : le
 *   même seuil que le point de rupture `sm:` des feuilles.
 * @param margin `nearestCellMargin`, `null` sans cellule — table vide, écran d'erreur.
 * @returns Sous 600 px, `footer` ; à partir de 600 px, `column` sans cellule ou dès 76 px de
 *   marge, `footer` en deçà.
 */
export function authorLinksPlacement(
  windowWidth: number,
  margin: number | null,
): AuthorLinksPlacement {
  if (windowWidth < BREAKPOINT) return 'footer'
  return margin === null || margin >= COLUMN_MARGIN ? 'column' : 'footer'
}
