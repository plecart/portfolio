/**
 * Accès des tests aux fichiers de l'application, par des chemins ancrés sur ce module plutôt que
 * sur le dossier courant.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Racine de l'application : le dossier qui contient `package.json`. */
export const APP_ROOT = fileURLToPath(new URL('..', import.meta.url))

/**
 * Lit un fichier JSON strict de l'application — pas un `tsconfig`, que TypeScript lit en JSONC.
 *
 * @param fileName Chemin relatif à la racine de l'application, par exemple `package.json`.
 * @returns Le contenu analysé. Le type est une promesse de l'appelant, que rien ne vérifie : ne
 *   lire que les champs dont le test a besoin, et traiter leur absence.
 * @throws Si le fichier est introuvable ou n'est pas du JSON valide.
 */
export function readAppJson<T>(fileName: string): T {
  return JSON.parse(readFileSync(join(APP_ROOT, fileName), 'utf8')) as T
}
