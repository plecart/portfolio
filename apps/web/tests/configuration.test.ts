/**
 * Invariants de configuration de l'application web.
 *
 * Des règles qu'aucune autre porte ne couvre : la version de Node vit dans deux fichiers que rien
 * ne relie l'un à l'autre, et ses types dans un troisième ; `tsc` ne signale jamais l'absence du
 * mode strict — il compile simplement moins, sans rien dire ; et `eslint` sort 0 devant un
 * avertissement. Ces tests fixent aussi le motif Vitest du dépôt.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { major } from 'semver'
import * as ts from 'typescript'
import { beforeAll, expect, test, vi } from 'vitest'
import viteConfig from '../vite.config.ts'
import {
  APP_ROOT,
  installedPackage,
  LINT_WARM_UP_MS,
  lintRuleIds,
  readAppJson,
  warmUpLint,
  type Lockfile,
} from './app-files.ts'

beforeAll(warmUpLint, LINT_WARM_UP_MS)

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

/** La version de Node épinglée par `.nvmrc`, par exemple `24.21.0`. */
function pinnedNodeVersion(): string {
  return readFileSync(join(APP_ROOT, '.nvmrc'), 'utf8').trim()
}

test('la version de Node est la même dans .nvmrc et dans engines', () => {
  const manifest = readAppJson<{ engines?: { node?: string } }>('package.json')

  expect(manifest.engines?.node).toBe(pinnedNodeVersion())
})

test('la majeure de @types/node est celle de Node', () => {
  // Des types d'une majeure plus récente décriraient des API absentes du runtime : `tsc` les
  // accepterait, Node les ignorerait à l'exécution. Les deux montent ensemble, à la main.
  const pinned = pinnedNodeVersion()
  const lockfile = readAppJson<Lockfile>('package-lock.json')
  const types = installedPackage(lockfile, '@types/node').version

  expect(major(types), `@types/node ${types} pour Node ${pinned}`).toBe(major(pinned))
})

/**
 * Les configurations TypeScript de l'application, lues depuis les `references` de `tsconfig.json`.
 *
 * Dérivée plutôt que recopiée : une liste écrite à la main devient un échantillon dès qu'une
 * quatrième configuration apparaît, et rien ne le signale. Ici, toute configuration ajoutée au
 * projet racine entre d'office dans la population du test.
 */
function projectConfigFileNames(): string[] {
  // Lu par le compilateur, comme `tsc` le lit : en JSONC, commentaires admis.
  const { config, error } = ts.readConfigFile(join(APP_ROOT, 'tsconfig.json'), ts.sys.readFile)
  if (error) throw new Error(ts.flattenDiagnosticMessageText(error.messageText, '\n'))
  const root = config as { references: { path: string }[] }

  return root.references.map((reference) => reference.path.replace(/^\.\//, ''))
}

test('toutes les configurations TypeScript du projet résolvent en mode strict', () => {
  const configFileNames = projectConfigFileNames()

  expect(configFileNames.length).toBeGreaterThan(0)
  expect(
    configFileNames.map((name) => [name, resolveCompilerOptions(name).strict]),
  ).toEqual(configFileNames.map((name) => [name, true]))
})

test('la porte de lint lit le script de restauration du mode', async () => {
  // Servi tel quel depuis `public/`, hors de la compilation : `tsc` ne le lit pas (hors de ses
  // `include`). Le lint est la seule porte statique qui le couvre — encore faut-il qu'il le lise
  // en script classique de navigateur, sans quoi ses globales seraient des fautes.
  const filePath = 'public/theme.js'
  const source = readFileSync(join(APP_ROOT, filePath), 'utf8')

  expect(await lintRuleIds(filePath, source)).toEqual([])
  expect(await lintRuleIds(filePath, source.replace('localStorage', 'locaStorage'))).toEqual([
    'no-undef',
  ])
  // Une comparaison tapée pour l'affectation ne pose jamais le mode.
  expect(
    await lintRuleIds(filePath, source.replace('dataset.theme = theme', 'dataset.theme == theme')),
  ).toEqual(['no-unused-expressions'])
  // Une syntaxe de module ferait du script une erreur au chargement — donc pas de restauration :
  // lu en script classique, il ne s'analyse plus (erreur sans règle).
  expect(await lintRuleIds(filePath, `${source}export {}\n`)).toEqual([null])
})

test('la porte de lint échoue sur un simple avertissement', () => {
  const manifest = readAppJson<{ scripts: { lint: string } }>('package.json')

  // Sur les 114 règles actives, 3 ne sont que des avertissements — dont
  // `react-hooks/exhaustive-deps`. Sans ce drapeau, `eslint` sort 0 devant elles et la porte
  // passe au vert en ayant vu le défaut. C'est une option qui fait la porte, pas une préférence.
  expect(manifest.scripts.lint).toContain('--max-warnings 0')
})

test("la compilation échoue sans l'origine de l'API ou sur une adresse mal formée, et passe avec", () => {
  const build = { command: 'build', isSsrBuild: false, isPreview: false } as const
  const compile = (mode: string, value?: string) => {
    // `loadEnv` lit aussi l'environnement du processus, qui l'emporte sur les fichiers : fixée ici,
    // la variable ne dépend pas du poste. Absente du processus, elle vient du fichier du mode.
    const saved = process.env.VITE_API_URL
    if (value === undefined) delete process.env.VITE_API_URL
    else process.env.VITE_API_URL = value
    try {
      viteConfig({ ...build, mode })
    } finally {
      if (saved === undefined) delete process.env.VITE_API_URL
      else process.env.VITE_API_URL = saved
    }
  }

  // Aucun fichier `.env.sans-api` : le mode n'apporte pas `VITE_API_URL`. Sans la garde, Vite
  // remplacerait la variable par `undefined`, et l'adresse de la liste ne se construirait pas.
  expect(() => compile('sans-api')).toThrow('VITE_API_URL')
  expect(() => compile('sans-api', 'api.pacome.dev')).toThrow('VITE_API_URL')
  expect(() => compile('sans-api', 'localhost:8000')).toThrow('VITE_API_URL')
  expect(() => compile('production')).not.toThrow()
})

/**
 * La commande du serveur des scénarios, le premier `webServer` de `playwright.config.ts`, relue
 * sous l'environnement donné : la configuration le lit à son chargement.
 *
 * @param environment `CI` et `GITHUB_ACTIONS`, chacune `undefined` quand elle manque, comme sur
 *   le poste.
 */
async function e2eServerCommand(environment: {
  CI: string | undefined
  GITHUB_ACTIONS: string | undefined
}): Promise<string | undefined> {
  for (const [name, value] of Object.entries(environment)) vi.stubEnv(name, value)
  vi.resetModules()
  try {
    const { default: config } = await import('../playwright.config.ts')

    return [config.webServer].flat()[0]?.command
  } finally {
    vi.unstubAllEnvs()
  }
}

test("sur un runner GitHub, les scénarios jouent le front déjà compilé ; ailleurs, il se compile d'abord", async () => {
  // Sur un runner GitHub, le job qui lance l'e2e a compilé le front au pas précédent
  // (`make web-build`) : le recompiler ne ferait que payer la compilation deux fois (ADR 0031).
  // Ailleurs, `make web-e2e` éprouve le front courant, quel que soit l'état de `dist` — y compris
  // sous `CI=1`, qu'un poste peut poser aussi : lu sur `CI`, le saut servirait un `dist` périmé.
  const preview = 'npm run preview -- --port 4173 --strictPort'
  const build = `npm run build && ${preview}`

  expect(await e2eServerCommand({ CI: 'true', GITHUB_ACTIONS: 'true' })).toBe(preview)
  expect(await e2eServerCommand({ CI: undefined, GITHUB_ACTIONS: 'true' })).toBe(preview)
  expect(await e2eServerCommand({ CI: '1', GITHUB_ACTIONS: undefined })).toBe(build)
  expect(await e2eServerCommand({ CI: undefined, GITHUB_ACTIONS: undefined })).toBe(build)
})
