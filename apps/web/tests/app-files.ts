/**
 * Accès des tests aux fichiers de l'application, par des chemins ancrés sur ce module plutôt que
 * sur le dossier courant ; et lecture, dans le verrou npm, d'un paquet installé.
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

/** Ce que les tests lisent d'une entrée du verrou npm. */
export type LockedPackage = { version: string; peerDependencies?: Record<string, string> }

/** Le verrou npm, format 3 : les paquets installés, indexés par chemin, racine `""` exclue. */
export type Lockfile = { packages: Record<`node_modules/${string}`, LockedPackage> }

/**
 * L'entrée d'un paquet installé à la racine d'un verrou.
 *
 * @param lockfile Le verrou, par exemple `readAppJson<Lockfile>('package-lock.json')`.
 * @param name Paquet, par exemple `@types/node` ; une dépendance directe est toujours à la racine,
 *   `node_modules/<nom>`.
 * @returns L'entrée : version installée, pairs déclarés.
 * @throws Si le paquet n'est plus installé : un test qui lirait une entrée absente ne mesurerait
 *   rien.
 */
export function installedPackage(lockfile: Lockfile, name: string): LockedPackage {
  const entry = lockfile.packages[`node_modules/${name}`]
  if (entry === undefined) throw new Error(`${name} n'est plus installé`)

  return entry
}
