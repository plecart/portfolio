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
 * La plage qu'un paquet installé à la racine déclare pour l'un de ses pairs, lue dans le verrou.
 *
 * @param name Paquet installé, par exemple `eslint-plugin-jsx-a11y`.
 * @param peer Pair dont on veut la plage, par exemple `eslint`.
 * @returns La plage telle que publiée, par exemple `^3 || … || ^9`.
 * @throws Si le paquet n'est plus à la racine du verrou, ou ne déclare plus ce pair : le refus
 *   a peut-être perdu sa raison, et un test qui lirait une plage absente ne mesurerait rien.
 */
function peerRange(name: string, peer: string): string {
  const lockfile = readAppJson<Lockfile>('package-lock.json')
  const range = lockfile.packages[`node_modules/${name}`]?.peerDependencies?.[peer]
  if (range === undefined) {
    throw new Error(`${name} ne déclare plus de pair ${peer} dans le verrou : le refus tient-il ?`)
  }

  return range
}

test.each(REFUSALS)(
  '%s %s reste refusé tant que %s ne le déclare pas',
  (refused, major, blocker) => {
    const range = peerRange(blocker, refused)

    // `intersects` et non `satisfies` : il suffit qu'une seule version de la majeure soit
    // acceptée pour que le refus tombe, et `satisfies('10', …)` rend `false` en silence — « 10 »
    // n'est pas une version complète.
    expect(
      intersects(range, major),
      `${blocker} accepte ${refused} ${major} (${range}) : lever le refus`,
    ).toBe(false)
  },
)
