/**
 * Invariants de configuration de l'application web.
 *
 * Deux règles qu'aucune autre porte ne couvre : la version de Node vit dans deux fichiers que
 * rien ne relie l'un à l'autre, et `tsc` ne signale jamais l'absence du mode strict — il compile
 * simplement moins, sans rien dire. Ces tests fixent aussi le motif Vitest du dépôt.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import * as ts from 'typescript'
import { expect, test } from 'vitest'
import { APP_ROOT, readAppJson } from './app-files.ts'

/** Hôte minimal de lecture : il remonte en exception ce que `tsc` signalerait sur sa sortie. */
const CONFIG_HOST: ts.ParseConfigFileHost = {
  ...ts.sys,
  onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
    throw new Error(ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'))
  },
}

/**
 * Résout les options d'une configuration TypeScript de l'application.
 *
 * Passe par le compilateur lui-même plutôt que par une lecture du JSON : les fichiers
 * `tsconfig` admettent des commentaires — que `JSON.parse` refuse — et la chaîne d'`extends`
 * doit être suivie, sans quoi le test mesurerait le fichier au lieu de mesurer l'effet.
 *
 * @param configFileName Nom du fichier, relatif à la racine de l'application.
 * @returns Les options effectives, héritage appliqué.
 * @throws Si le fichier est introuvable, illisible, ou refusé par le compilateur.
 */
function resolveCompilerOptions(configFileName: string): ts.CompilerOptions {
  const parsed = ts.getParsedCommandLineOfConfigFile(
    join(APP_ROOT, configFileName),
    undefined,
    CONFIG_HOST,
  )
  if (!parsed) throw new Error(`Configuration TypeScript illisible : ${configFileName}`)

  return parsed.options
}

test('la version de Node est la même dans .nvmrc et dans engines', () => {
  const pinned = readFileSync(join(APP_ROOT, '.nvmrc'), 'utf8').trim()
  const manifest = readAppJson<{ engines?: { node?: string } }>('package.json')

  expect(manifest.engines?.node).toBe(pinned)
})

/**
 * Les configurations TypeScript de l'application, lues depuis les `references` de `tsconfig.json`.
 *
 * Dérivée plutôt que recopiée : une liste écrite à la main devient un échantillon dès qu'une
 * quatrième configuration apparaît, et rien ne le signale. Ici, toute configuration ajoutée au
 * projet racine entre d'office dans la population du test.
 */
function projectConfigFileNames(): string[] {
  const root = readAppJson<{ references: { path: string }[] }>('tsconfig.json')

  return root.references.map((reference) => reference.path.replace(/^\.\//, ''))
}

test('toutes les configurations TypeScript du projet résolvent en mode strict', () => {
  const configFileNames = projectConfigFileNames()

  expect(configFileNames.length).toBeGreaterThan(0)
  expect(
    configFileNames.map((name) => [name, resolveCompilerOptions(name).strict]),
  ).toEqual(configFileNames.map((name) => [name, true]))
})

test('la porte de lint échoue sur un simple avertissement', () => {
  const manifest = readAppJson<{ scripts: { lint: string } }>('package.json')

  // Sur les 114 règles actives, 3 ne sont que des avertissements — dont
  // `react-hooks/exhaustive-deps`. Sans ce drapeau, `eslint` sort 0 devant elles et la porte
  // passe au vert en ayant vu le défaut. C'est une option qui fait la porte, pas une préférence.
  expect(manifest.scripts.lint).toContain('--max-warnings 0')
})
