/**
 * Les projets que les scénarios servent à la place de l'API, typés depuis son schéma OpenAPI
 * (`src/api/schema.ts`, `make web-openapi`) : un champ renommé dans le contrat casse leur
 * compilation (brief de #19, décision 10).
 */
import type { components } from '../src/api/schema.ts'

/** Un projet tel que l'API le sert. */
export type Project = components['schemas']['ProjectOut']
