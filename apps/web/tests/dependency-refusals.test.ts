/**
 * Les montées majeures refusées, et leur expiration.
 *
 * `.github/dependabot.yml` refuse la majeure suivante d'ESLint — et d'`@eslint/js`, qui va par
 * paire avec lui — et de TypeScript : un plugin qu'on garde ne l'accepte pas encore comme pair, et
 * `npm ci` échouerait en `ERESOLVE` (`docs/frontend-outillage.md` §2.4). Un refus ne doit pas
 * devenir permanent par oubli : chaque cas rougit le jour où la plage `peerDependencies` du plugin,
 * lue dans le verrou, accepte la majeure refusée. Il faut alors lever le refus : la règle `ignore`,
 * son cas dans `apps/api/tests/test_supply_chain.py`, et le cas d'ici.
 *
 * Le verrou ne change que par une PR : le rouge apparaît dans celle qui apporte la nouvelle
 * version du plugin, celles de Dependabot comprises.
 */
import { intersects } from 'semver'
import { expect, test } from 'vitest'
import { readAppJson } from './app-files.ts'

/** Ce que le test lit du verrou npm : les entrées installées, indexées par chemin. */
type Lockfile = {
  packages: Record<string, { peerDependencies?: Record<string, string> }>
}

/** Paquet refusé, majeure refusée, plugin dont la plage de pairs fonde le refus. */
const REFUSALS: [refused: string, major: string, blocker: string][] = [
  ['eslint', '10', 'eslint-plugin-jsx-a11y'],
  ['typescript', '7', 'typescript-eslint'],
]

/**
 * La plage qu'un paquet installé à la racine déclare pour l'un de ses pairs, lue dans un verrou.
 *
 * @param lockfile Le verrou npm, par exemple celui de l'application.
 * @param name Paquet installé, par exemple `eslint-plugin-jsx-a11y` ; une dépendance directe est
 *   toujours à la racine, `node_modules/<nom>`.
 * @param peer Pair dont on veut la plage, par exemple `eslint`.
 * @returns La plage telle que publiée, par exemple `^3 || … || ^9`.
 * @throws Si le paquet n'est plus installé, ou ne déclare plus ce pair : le refus a peut-être
 *   perdu sa raison, et un test qui lirait une plage absente ne mesurerait rien.
 */
function peerRange(lockfile: Lockfile, name: string, peer: string): string {
  const entry = lockfile.packages[`node_modules/${name}`]
  if (entry === undefined) {
    throw new Error(`${name} n'est plus installé : le refus qu'il fondait tient-il encore ?`)
  }
  const range = entry.peerDependencies?.[peer]
  if (range === undefined) {
    throw new Error(`${name} ne déclare plus de pair ${peer} : le refus tient-il encore ?`)
  }

  return range
}

/**
 * Une plage de pairs accepte-t-elle au moins une version d'une majeure ?
 *
 * `intersects` et non `satisfies` : il suffit qu'une seule version de la majeure soit acceptée
 * pour que le refus tombe, et `satisfies('10', …)` rend `false` en silence — « 10 » n'est pas une
 * version complète. Une plage qui n'ouvre que des préversions de la majeure ne compte pas (recueil
 * ci-dessous).
 *
 * @param range Plage publiée par le plugin, par exemple `^3 || … || ^9`.
 * @param major Majeure refusée, par exemple `10`.
 * @returns `true` dès qu'une version stable de la majeure entre dans la plage. `semver` lit une
 *   plage vide ou mal formée comme `^x` en `*` : elle rend `true`, un rouge plutôt qu'un vert muet.
 * @throws Si `semver` ne sait pas lire la plage du tout, par exemple `latest`.
 */
function acceptsMajor(range: string, major: string): boolean {
  return intersects(range, major)
}

/**
 * Plages publiées ou plausibles, avec le verdict attendu pour la majeure donnée : le recueil prouve
 * que la garde sait rougir, ce que le cas réel, vert aujourd'hui, ne montre pas.
 */
const RANGE_FORMS: [range: string, major: string, accepted: boolean][] = [
  ['^3 || ^4 || ^5 || ^6 || ^7 || ^8 || ^9', '10', false],
  ['^3 || ^4 || ^5 || ^6 || ^7 || ^8 || ^9 || ^10', '10', true],
  ['>=4.8.4 <6.1.0', '7', false],
  ['>=4.8.4 <7.1.0', '7', true],
  ['^10.1.0', '10', true],
  ['>=8', '10', true],
  ['*', '10', true],
  ['^9 || 10.0.0-rc.1', '10', false],
  ['10.1.0-rc.1', '10', false],
  ['^9 || ^10.0.0-rc.0', '10', true],
]

test.each(RANGE_FORMS)('la plage « %s » accepte la majeure %s : %s', (range, major, accepted) => {
  expect(acceptsMajor(range, major)).toBe(accepted)
})

test('un plugin désinstallé ou un pair non déclaré est signalé, jamais lu comme une plage', () => {
  const lockfile: Lockfile = { packages: { 'node_modules/plugin': { peerDependencies: {} } } }

  expect(() => peerRange(lockfile, 'absent', 'eslint')).toThrow(`absent n'est plus installé`)
  expect(() => peerRange(lockfile, 'plugin', 'eslint')).toThrow(
    'plugin ne déclare plus de pair eslint',
  )
})

test.each(REFUSALS)(
  '%s %s reste refusé tant que %s ne le déclare pas',
  (refused, major, blocker) => {
    const range = peerRange(readAppJson<Lockfile>('package-lock.json'), blocker, refused)

    expect(
      acceptsMajor(range, major),
      `${blocker} accepte ${refused} ${major} (${range}) : lever le refus`,
    ).toBe(false)
  },
)
