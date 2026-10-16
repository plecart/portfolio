/**
 * Fraîcheur des types de l'API (#19, décision 5) : le module committé est exactement ce que
 * `openapi-typescript` rend du schéma versionné.
 *
 * Même mécanisme que le test de fraîcheur de `apps/api/openapi.json` côté back : un changement du
 * contrat sans `make web-openapi` rougit ici, donc dans `make web-test` et en CI, sans étape de
 * workflow à part.
 */
import { readFileSync } from 'node:fs'
import { expect, test } from 'vitest'
import { renderApiTypes, TYPES_URL } from '../scripts/api-types.ts'

test('le module des types est celui du schéma OpenAPI : sinon, make web-openapi', async () => {
  // La copie de travail d'un poste Windows est en CRLF (`core.autocrlf`) ; le rendu est en LF.
  const committed = readFileSync(TYPES_URL, 'utf8').replaceAll('\r\n', '\n')

  expect(committed).toBe(await renderApiTypes())
})
