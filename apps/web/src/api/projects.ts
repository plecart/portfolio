/**
 * La liste des projets publiés, telle que l'API publique la sert (`GET /api/projets`), typée par
 * le module généré depuis son schéma OpenAPI (`make web-openapi`).
 */
import type { components } from './schema.ts'

/** Un projet publié, tel que l'API le sert. */
export type Project = components['schemas']['ProjectOut']

/** L'adresse de la liste, sur l'origine de l'API (fichiers de mode de Vite, `VITE_API_URL`). */
const PROJECTS_URL = new URL('/api/projets', import.meta.env.VITE_API_URL)

/**
 * Charge la liste, en une requête (spec §1.3 : les projets sont chargés d'un coup).
 *
 * Le corps n'est pas validé à l'exécution : le test de contrat du back garantit qu'il suit le
 * schéma dont les types dérivent (brief de #19, décision 6).
 *
 * @param signal Abandonne la requête, au démontage de son appelant.
 * @returns Les projets, dans l'ordre de l'API.
 * @throws Sur toute défaillance — réseau, statut hors 2xx, corps qui n'est pas du JSON — et à
 *   l'abandon : l'appelant ne distingue pas les causes, toutes mènent à l'état erreur.
 */
export async function fetchProjects(signal: AbortSignal): Promise<Project[]> {
  const response = await fetch(PROJECTS_URL, { signal })
  if (!response.ok) throw new Error(`GET ${PROJECTS_URL} : statut ${response.status}`)
  return (await response.json()) as Project[]
}
