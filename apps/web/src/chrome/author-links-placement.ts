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
 * Une cellule masquée (`display: none`, `hidden`) ne compte pas. La mesure se relit au
 * redimensionnement de la fenêtre, à chaque élément ajouté ou retiré dans la table et à chaque
 * attribut `data-table-cell`, `hidden`, `style` ou `class` changé (`useAuthorLinksPlacement`).
 * Restent à la charge de la table : une taille changée par une feuille sans mutation du DOM, et
 * une transformation posée sur un **ancêtre** de la cellule, que la mesure suit comme la sienne.
 * Dénombrement des voies : `e2e/author-links.spec.ts`.
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
 * comme au prototype retenu (`cadre.html`, variante « Retrait »), comptée **hors barre de
 * défilement** : la grille, centrée dans la largeur visible, recule de la moitié de la barre, et la
 * lui rendre fait de la marge une grandeur de la seule mise en page. Les repères de §3.4 tiennent
 * avec ou sans barre, et la forme ne dépend pas du chemin — le pied de page dans le flux, qui
 * allonge la page, fait naître la barre (choix du mainteneur, arrêt visuel du lot 3 de #18).
 *
 * @param cells Les bords des cellules, en px depuis le bord gauche de la fenêtre
 *   (`getBoundingClientRect`) ; une cellule de largeur nulle — masquée — est ignorée.
 * @param widths La largeur de la fenêtre (`innerWidth`) et sa largeur visible, barre exclue
 *   (`clientWidth`).
 * @returns La plus petite marge, à gauche ou à droite, sur les cellules visibles ; `null` sans
 *   cellule visible.
 */
export function nearestCellMargin(
  cells: readonly { left: number; right: number }[],
  { windowWidth, viewportWidth }: { windowWidth: number; viewportWidth: number },
): number | null {
  const shown = cells.filter((cell) => cell.right > cell.left)
  if (shown.length === 0) return null
  const scrollbarHalf = (windowWidth - viewportWidth) / 2
  const margins = shown.map((cell) => Math.min(cell.left, viewportWidth - cell.right))
  return Math.min(...margins) + scrollbarHalf
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
