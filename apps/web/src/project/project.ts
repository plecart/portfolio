/** L'adresse d'une fiche (spec §3.2), en logique pure. */

/** Le chemin d'une fiche, avec ou sans barre finale : un seul segment après `/projets/`. */
const PROJECT_PATH = /^\/projets\/([^/]+)\/?$/

/**
 * Le chemin de la fiche d'un projet.
 *
 * @param slug Le slug du projet.
 * @returns `/projets/<slug>`, l'adresse de la fiche et le `href` de sa carte.
 */
export function projectPath(slug: string): string {
  return `/projets/${slug}`
}

/**
 * Le slug que désigne un chemin.
 *
 * @param pathname Un chemin d'adresse (`location.pathname`).
 * @returns Le slug de `/projets/<slug>` ; `null` pour tout autre chemin.
 */
export function slugFromPath(pathname: string): string | null {
  return PROJECT_PATH.exec(pathname)?.[1] ?? null
}
