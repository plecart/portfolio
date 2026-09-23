/**
 * Invariants de configuration de l'application web.
 *
 * Deux règles qu'aucune autre porte ne couvre : la version de Node vit dans deux fichiers que
 * rien ne relie l'un à l'autre, et `tsc` ne signale jamais l'absence du mode strict — il compile
 * simplement moins, sans rien dire. Ces tests fixent aussi le motif Vitest du dépôt.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import * as ts from 'typescript'
import { expect, test } from 'vitest'

const APP_ROOT = fileURLToPath(new URL('..', import.meta.url))

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
  const manifest = JSON.parse(readFileSync(join(APP_ROOT, 'package.json'), 'utf8')) as {
    engines?: { node?: string }
  }

  expect(manifest.engines?.node).toBe(pinned)
})

test.for(['tsconfig.app.json', 'tsconfig.node.json'])(
  '%s résout en mode strict',
  (configFileName) => {
    expect(resolveCompilerOptions(configFileName).strict).toBe(true)
  },
)
