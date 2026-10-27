/**
 * Les cartes de la table, en logique pure : leur ordre (spec §1.9). Les projets entrent tels que
 * l'API les sert, rien n'est lu ailleurs.
 *
 * Typé depuis le schéma, et non par `api/projects.ts` : ce module-là lit `import.meta.env`, que
 * les tests, compilés sans les types de Vite (`tsconfig.node.json`), ne connaissent pas.
 */
import type { components } from '../api/schema.ts'

type Project = components['schemas']['ProjectOut']

/** Compare deux chaînes par unités de code — dates ISO, slugs —, sans dépendre de la locale. */
function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

/**
 * La date qui situe un projet dans son groupe : sa fin, à défaut son début. Un projet en cours n'a
 * pas de fin (contrat de `ProjectOut`) : il se situe par son début.
 */
function datedOn(project: Project): string {
  return project.finished_on ?? project.started_on
}

/**
 * L'ordre de la table (spec §1.9) : la vitrine, puis les projets en cours, puis les autres —
 * terminés et archivés ensemble —, chaque groupe du plus récent au plus ancien, et à date égale
 * par slug croissant. Le slug étant unique, l'ordre est total.
 */
function compareProjects(a: Project, b: Project): number {
  return (
    Number(b.showcase) - Number(a.showcase) ||
    Number(b.status === 'ongoing') - Number(a.status === 'ongoing') ||
    compareText(datedOn(b), datedOn(a)) ||
    compareText(a.slug, b.slug)
  )
}

/**
 * Les projets dans l'ordre de la table.
 *
 * Plusieurs vitrines — que la base refuse — passent toutes en tête, rangées entre elles comme les
 * autres projets.
 *
 * @param projects Les projets, dans l'ordre de l'API ; la liste n'est pas modifiée.
 * @returns Une nouvelle liste, ordonnée.
 */
export function orderProjects(projects: readonly Project[]): Project[] {
  return [...projects].sort(compareProjects)
}
