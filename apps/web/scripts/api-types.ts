/**
 * Les types de l'API publique, générés depuis son schéma OpenAPI versionné (#19, ADR 0008).
 *
 * Une seule fonction de rendu, pour l'écriture comme pour la vérification : `npm run openapi`
 * (`make web-openapi`) écrit le module, et `tests/api-types.test.ts` compare ce même rendu au module
 * committé. Une génération écrite deux fois — l'outil en ligne de commande d'un côté, son API de
 * l'autre — diffère déjà par la bannière que la première ajoute.
 *
 * Lancé directement (`node scripts/api-types.ts`), le module écrit le fichier ; importé, il n'écrit
 * rien.
 */
import { writeFileSync } from 'node:fs'
import openapiTS, { astToString } from 'openapi-typescript'

/** Le schéma, écrit par `make openapi` côté back : le front le lit, il ne l'écrit jamais. */
const SCHEMA_URL =new URL('../../api/openapi.json', import.meta.url)

/** Le module des types, committé : les composants importent `components['schemas'][…]` d'ici. */
export const TYPES_URL = new URL('../src/api/schema.ts', import.meta.url)

/** En tête du module : il ne s'édite pas, il se régénère. */
const BANNER = `/**
 * Généré depuis apps/api/openapi.json par \`make web-openapi\` : ne pas éditer.
 */

`

/**
 * Rend le module des types depuis le schéma.
 *
 * @returns Le texte du module, en fins de ligne LF, tel que `openapi-typescript` l'imprime
 *   derrière la bannière.
 * @throws Si le schéma n'est pas un document OpenAPI 3, ou porte une référence qui ne se résout
 *   pas : `openapi-typescript` le valide avant de rendre.
 */
export async function renderApiTypes(): Promise<string> {
  return BANNER + astToString(await openapiTS(SCHEMA_URL))
}

if (import.meta.main) writeFileSync(TYPES_URL, await renderApiTypes())
