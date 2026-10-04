/**
 * La règle des valeurs : aucune couleur, durée ou courbe en dur hors de `src/tokens.css`
 * (spec §2 ; CONTRIBUTING.md, « Valeurs du front »).
 *
 * Trois portes sur une même population. ESLint (`no-restricted-syntax`) lit les littéraux et les
 * gabarits de `src/` — classes et styles ; un balayage lit toute autre feuille CSS de `src/` ; les
 * deux appliquent les motifs de `forbidden-values.json`, sans tenir compte de la casse. Tailwind,
 * enfin, n'a plus ni couleurs, ni ombres, ni animations, ni courbes à lui (`@theme` de
 * `index.css`), et sa transition par défaut lit les jetons.
 *
 * Dénombrement du 2026-10-04, repris à la seconde relecture : **20 formes** d'une couleur, d'une
 * ombre, d'une durée ou d'une courbe écrite en dur dans ce front, **15 couvertes**. Dans un
 * composant — classe, valeurs arbitraires comprises, où `_` tient lieu d'espace ; style ;
 * gabarit —, 11 : hexadécimal ; fonction de couleur ; classe de palette de Tailwind ; ombre par
 * défaut de Tailwind (`shadow-*`, `inset-shadow-*`, `drop-shadow-*`, `text-shadow-*`) ; durée à
 * unité ; durée numérique de Tailwind ; animation par défaut de Tailwind ; fonction de courbe ;
 * courbe par défaut de Tailwind ; `ease-linear` ; transition par défaut de Tailwind. Dans une
 * feuille CSS, 4 : hexadécimal, fonction de couleur, durée à unité, fonction de courbe.
 * **5 hors portée**, à ne jamais supposer couvertes : couleur nommée (`red`, `white`) dans un
 * composant et dans une feuille CSS ; couleur système (`Canvas`) ; mot-clé de courbe (`ease`,
 * `linear`) dans un composant et dans une feuille CSS. Hors de tout dénombrement, comme pour toute
 * règle qui lit du texte : une valeur assemblée par une expression ou passée par une variable.
 *
 * Faux positifs connus, refusés à tort : une ancre ou un fragment fait de lettres hexadécimales
 * (`#add`, `#face`), un texte « #123 » ou « 2s », `duration-0`. Les écrire autrement — aucun motif
 * simple ne les distingue d'une valeur.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { compile } from 'tailwindcss'
import { beforeAll, describe, expect, test } from 'vitest'
import {
  APP_ROOT,
  LINT_WARM_UP_MS,
  lintRuleIds,
  readAppJson,
  warmUpLint,
} from './app-files.ts'

beforeAll(warmUpLint, LINT_WARM_UP_MS)

/** Une forme interdite : son nom, rendu dans le message d'ESLint, et son motif. */
type ForbiddenValue = { name: string; pattern: string }

const FORBIDDEN_VALUES = readAppJson<ForbiddenValue[]>('forbidden-values.json')

/** Le seul fichier où un littéral de couleur, de durée ou de courbe a sa place. */
const TOKENS_SHEET = 'tokens.css'

const SRC = join(APP_ROOT, 'src')

/** Formes interdites présentes dans une feuille CSS, commentaires exclus : leurs noms. */
function forbiddenIn(css: string): string[] {
  const code = css.replace(/\/\*[\s\S]*?\*\//g, '')

  return FORBIDDEN_VALUES.filter(({ pattern }) => new RegExp(pattern, 'i').test(code)).map(
    ({ name }) => name,
  )
}

/** Les règles qu'ESLint lève sur un extrait, lu comme un composant de `src/`. */
const lintComponent = (code: string) => lintRuleIds('src/value-rule-probe.tsx', code)

describe('ESLint refuse une valeur en dur dans un composant', () => {
  test.each([
    ['hexadécimal en classe', '<p className="bg-[#B4471F]" />'],
    ['hexadécimal court en classe', '<p className="text-[#fff]" />'],
    ['rgb() en style', "<p style={{ color: 'rgb(42, 38, 34)' }} />"],
    ['oklch() en classe', '<p className="bg-[oklch(70%_0.1_50)]" />'],
    ['durée à unité en classe', '<p className="duration-[240ms]" />'],
    ['durée numérique de Tailwind', '<p className="duration-200" />'],
    ['délai numérique sous variante', '<p className="md:delay-75" />'],
    ['durée en style', "<p style={{ transition: 'opacity .2s' }} />"],
    ['courbe en gabarit', '`ease-[cubic-bezier(.22,1,.36,1)]`'],
    ['linear() en style', "<p style={{ transitionTimingFunction: 'linear(0, 1)' }} />"],
    ['ease-linear en classe', '<p className="ease-linear" />'],
    ['hexadécimal après une expression de gabarit', '`${base} bg-[#2a2622]`'],
    // Dans une valeur arbitraire, Tailwind lit `_` comme une espace.
    ['fonction de couleur après `_`', '<p className="shadow-[0_1px_rgb(0,0,0)]" />'],
    ['durée entre `_`', '<p className="[transition:opacity_200ms]" />'],
    ['durée d’une animation arbitraire', '<p className="animate-[spin_1s_linear_infinite]" />'],
    ['courbe après `_`', '<p className="[transition:all_var(--dur)_cubic-bezier(.4,0,.2,1)]" />'],
    ['hexadécimal avant `_`', '<p className="shadow-[0_0_0_#fff_inset]" />'],
    // CSS ne tient pas compte de la casse des fonctions ni des unités.
    ['fonction de couleur en capitales', "<p style={{ color: 'RGB(42, 38, 34)' }} />"],
    ['unité en capitale', "<p style={{ transition: 'opacity .2S' }} />"],
  ])('%s', async (_, code) => {
    expect(await lintComponent(`export const probe = ${code}`)).toContain('no-restricted-syntax')
  })

  test.each([
    ['jetons en classe', '<p className="bg-(--paper) text-(--ink) shadow-(--shadow-rest)" />'],
    ['durée et courbe en jetons', '<p className="duration-(--dur) ease-(--ease-out)" />'],
    ['dimensions', '<p className="p-(--s-4) rounded-(--r-card) h-14 w-[76px]" />'],
    // `bac` est hexadécimal : l'ancre ne passe que parce que le motif exige une fin de mot.
    ['ancre de page', '<a href="#bac-a-sable">bac à sable</a>'],
    ['transition par défaut', '<p className="transition-colors" />'],
    ['nombre', '200'],
  ])('%s passe', async (_, code) => {
    expect(await lintComponent(`export const probe = ${code}`)).not.toContain(
      'no-restricted-syntax',
    )
  })

  test('un script JavaScript de src/ est lu aussi', async () => {
    expect(await lintRuleIds('src/value-rule-probe.js', "export const tone = '#ff0000'\n")).toContain(
      'no-restricted-syntax',
    )
  })
})

describe('aucune feuille CSS hors des jetons ne porte de valeur en dur', () => {
  const sheets = readdirSync(SRC, { recursive: true, encoding: 'utf8' }).filter(
    (path) => path.endsWith('.css') && path !== TOKENS_SHEET,
  )

  test('la population balayée est celle du dépôt', () => {
    expect(sheets).toContain('index.css')
  })

  test.each(sheets)('%s', (path) => {
    expect(forbiddenIn(readFileSync(join(SRC, path), 'utf8'))).toEqual([])
  })

  test('le balayage voit chaque famille, et la feuille des jetons en est pleine', () => {
    expect(
      forbiddenIn(
        'a { color: #fff; background: rgb(0 0 0); transition: color .2s cubic-bezier(.4, 0, .2, 1) }',
      ),
    ).toEqual(['couleur hexadécimale', 'fonction de couleur', 'durée à unité', 'fonction de courbe'])
    expect(forbiddenIn(readFileSync(join(SRC, TOKENS_SHEET), 'utf8'))).not.toEqual([])
  })

  test('un commentaire ne compte pas', () => {
    // Un renvoi d'issue à trois chiffres a la forme d'une couleur hexadécimale.
    expect(forbiddenIn('/* voir #164, 2s */ a { color: var(--ink) }')).toEqual([])
  })
})

/**
 * Compile `src/index.css` par Tailwind lui-même, comme le fait son plugin Vite.
 *
 * @returns Le compilateur : `build(classes)` rend la feuille produite pour ces classes.
 */
async function compileIndexCss() {
  const require = createRequire(import.meta.url)
  const loadStylesheet = async (id: string, base: string) => {
    const path = id.startsWith('.') ? resolve(base, id) : require.resolve(`${id}/index.css`)
    return { path, base: dirname(path), content: readFileSync(path, 'utf8') }
  }

  return compile(readFileSync(join(SRC, 'index.css'), 'utf8'), { base: SRC, loadStylesheet })
}

/** Vrai si la classe ajoute quelque chose à la feuille que Tailwind produit sans elle. */
async function generates(className: string): Promise<boolean> {
  const [bare, withClass] = await Promise.all([compileIndexCss(), compileIndexCss()])

  return withClass.build([className]) !== bare.build([])
}

describe("Tailwind n'apporte ni couleur, ni ombre, ni animation, ni courbe à lui", () => {
  test.each([
    'bg-red-500',
    'text-white',
    'border-black',
    'shadow-lg',
    'inset-shadow-sm',
    'drop-shadow-md',
    'text-shadow-md',
    'animate-spin',
    'animate-ping',
    'ease-in',
    'ease-out',
    'ease-in-out',
  ])('%s ne produit rien', async (className) => {
    expect(await generates(className)).toBe(false)
  })

  test('une classe sur un jeton produit sa règle', async () => {
    expect(await generates('bg-(--paper)')).toBe(true)
  })

  test('la transition par défaut prend la durée et la courbe des jetons', async () => {
    const css = (await compileIndexCss()).build(['transition-colors'])

    expect(css).toMatch(/--default-transition-duration:\s*var\(--dur-fast\)/)
    expect(css).toMatch(/--default-transition-timing-function:\s*var\(--ease-out\)/)
  })
})
