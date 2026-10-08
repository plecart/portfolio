/**
 * Accès des tests aux fichiers de l'application, par des chemins ancrés sur ce module plutôt que
 * sur le dossier courant ; lecture, dans le verrou npm, d'un paquet installé ; et lecture d'un
 * texte par la configuration ESLint du projet.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ESLint } from 'eslint'

/** Racine de l'application : le dossier qui contient `package.json`. */
export const APP_ROOT = fileURLToPath(new URL('..', import.meta.url))

/** ESLint tel que la porte `npm run lint` le lance : configuration du projet, depuis sa racine. */
const ESLINT = new ESLint({ cwd: APP_ROOT })

/**
 * Les règles qu'ESLint lève sur un texte, lu comme s'il était le fichier donné.
 *
 * @param filePath Chemin relatif à la racine de l'application, par exemple `src/App.tsx` : c'est
 *   lui qui décide des blocs de configuration appliqués. Le fichier n'a pas à exister.
 * @param text Le contenu à analyser.
 * @returns L'identifiant de règle de chaque message, dans l'ordre d'ESLint ; `null` pour une
 *   erreur d'analyse, et un message sans règle aussi pour un fichier ignoré — un texte que la
 *   porte ne lirait pas ne rend donc jamais une liste vide.
 */
export async function lintRuleIds(filePath: string, text: string): Promise<(string | null)[]> {
  return (await lint(filePath, text)).map((message) => message.ruleId)
}

/**
 * Les messages qu'ESLint lève sur une expression, exportée depuis un composant de `src/`.
 *
 * Des messages, pas des identifiants : la règle des valeurs et celle des chaînes partagent
 * `no-restricted-syntax`, et seul le message dit laquelle a refusé.
 *
 * @param expression Une expression TypeScript ou JSX, par exemple `<p className="flex" />`.
 * @returns Le texte de chaque message, dans l'ordre d'ESLint.
 */
export async function lintComponent(expression: string): Promise<string[]> {
  const messages = await lint('src/probe.tsx', `export const probe = ${expression}`)

  return messages.map((message) => message.message)
}

/** Les messages qu'ESLint lève sur un texte, lu comme s'il était le fichier donné. */
async function lint(filePath: string, text: string): Promise<ESLint.LintResult['messages']> {
  const [result] = await ESLINT.lintText(text, { filePath: join(APP_ROOT, filePath) })

  return result.messages
}

/**
 * Délai accordé au premier passage d'ESLint d'un fichier de test : configuration, analyseur
 * TypeScript et extensions se chargent alors, au-delà des 5 s par défaut de Vitest à froid, juste
 * après `npm ci` (mesuré une fois sur six à la relecture de #18).
 */
export const LINT_WARM_UP_MS = 60_000

/** Premier passage d'ESLint, à lancer en `beforeAll` avec `LINT_WARM_UP_MS` : les tests gardent
 *  ensuite le délai par défaut. */
export async function warmUpLint(): Promise<void> {
  await lintRuleIds('src/warm-up.ts', '')
}

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
