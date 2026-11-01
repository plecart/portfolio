/**
 * La règle des valeurs : aucune couleur, durée ou courbe en dur hors de `src/tokens.css`
 * (spec §2 ; CONTRIBUTING.md, « Valeurs du front »).
 *
 * Trois portes sur une même population. ESLint (`no-restricted-syntax`) lit les littéraux et les
 * gabarits de `src/` — classes et styles ; un balayage lit toute autre feuille CSS de `src/` ; les
 * deux appliquent les motifs de `forbidden-values.json`, sans tenir compte de la casse. Tailwind,
 * enfin, n'a plus ni couleurs, ni ombres, ni animations, ni courbes à lui (`@theme` de
 * `index.css`), sauf le blanc par défaut de `ring-offset-*`, et sa transition par défaut lit les
 * jetons.
 *
 * Dénombrement du 2026-10-04, repris à la seconde relecture : **21 formes** d'une couleur, d'une
 * ombre, d'une durée ou d'une courbe écrite en dur dans ce front, **15 couvertes**. Dans un
 * composant — classe, valeurs arbitraires comprises, où `_` tient lieu d'espace ; style ;
 * gabarit —, 11 : hexadécimal ; fonction de couleur ; classe de palette de Tailwind ; ombre par
 * défaut de Tailwind (`shadow-*`, `inset-shadow-*`, `drop-shadow-*`, `text-shadow-*`) ; durée à
 * unité ; durée numérique de Tailwind ; animation par défaut de Tailwind ; fonction de courbe ;
 * courbe par défaut de Tailwind ; `ease-linear` ; transition par défaut de Tailwind. Dans une
 * feuille CSS, 4 : hexadécimal, fonction de couleur, durée à unité, fonction de courbe.
 * **6 hors portée**, à ne jamais supposer couvertes : couleur nommée (`red`, `white`) dans un
 * composant et dans une feuille CSS ; couleur système (`Canvas`) ; mot-clé de courbe (`ease`,
 * `linear`) dans un composant et dans une feuille CSS ; décalage d'anneau sans couleur
 * (`ring-offset-2` sans `ring-offset-(--jeton)`), que Tailwind peint en `#fff` — la spec trace
 * l'anneau de focus par `outline`. Hors de tout dénombrement, comme pour toute règle qui lit du
 * texte : une valeur assemblée par une expression ou passée par une variable.
 *
 * Pour Tailwind, la population est mesurée, pas supposée : ses 8 568 classes (4.3.3) compilées avec
 * `index.css`, seules portent encore une valeur interdite `duration-N`, `delay-N` et `ease-linear`,
 * qu'ESLint refuse, des valeurs neutres (`#0000` transparent, masques `#fff`) et le `#fff` de
 * `ring-offset-*`. Mesure faite une fois (liste des classes par l'API instable de Tailwind), à
 * refaire à une montée de Tailwind.
 *
 * Faux positifs connus, refusés à tort : une ancre ou un fragment fait de lettres hexadécimales
 * (`#add`, `#face`, `#add_item`) ; un texte « #123 », « 2s », ou un nom de fonction CSS suivi d'une
 * parenthèse, quelle que soit la casse (« Lab( », « COLOR( ») ; une durée dans un nom de fichier
 * (`url(/x_2s.png)`) ; `duration-0`. Les écrire autrement — aucun motif simple ne les distingue
 * d'une valeur.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { compile } from 'tailwindcss'
import { beforeAll, describe, expect, test } from 'vitest'
import {
  APP_ROOT,
  LINT_WARM_UP_MS,
  lintComponent,
  lintRuleIds,
  readAppJson,
  warmUpLint,
} from './app-files.ts'

beforeAll(warmUpLint, LINT_WARM_UP_MS)

/** Une forme interdite : son nom, rendu dans le message d'ESLint, et son motif. */
type ForbiddenValue = { name: string; pattern: string }

const FORBIDDEN_VALUES = readAppJson<ForbiddenValue[]>('forbidden-values.json')

/** Le refus de cette règle, et pas celui de la règle des chaînes, qui partage son identifiant. */
const VALUE_REFUSAL = expect.stringContaining('Valeur en dur')

/** Le seul fichier où un littéral de couleur, de durée ou de courbe a sa place. */
const TOKENS_SHEET = 'tokens.css'

const SRC = join(APP_ROOT, 'src')

/** Toute feuille CSS de `src/` autre que celle des jetons. */
const SHEETS = readdirSync(SRC, { recursive: true, encoding: 'utf8' }).filter(
  (path) => path.endsWith('.css') && path !== TOKENS_SHEET,
)

/** Une feuille CSS sans ses commentaires. */
const withoutComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '')

/** Formes interdites présentes dans une feuille CSS, commentaires exclus : leurs noms. */
function forbiddenIn(css: string): string[] {
  const code = withoutComments(css)

  return FORBIDDEN_VALUES.filter(({ pattern }) => new RegExp(pattern, 'i').test(code)).map(
    ({ name }) => name,
  )
}

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
    expect(await lintComponent(code)).toContainEqual(VALUE_REFUSAL)
  })

  test.each([
    ['jetons en classe', '<p className="bg-(--paper) text-(--ink) shadow-(--shadow-rest)" />'],
    ['durée et courbe en jetons', '<p className="duration-(--dur) ease-(--ease-out)" />'],
    ['dimensions', '<p className="p-(--s-4) rounded-(--r-card) h-14 w-[76px]" />'],
    // `bac` est hexadécimal : l'ancre ne passe que parce que le motif exige une fin de mot.
    ['ancre de page', '<a href="#bac-a-sable" />'],
    ['transition par défaut', '<p className="transition-colors" />'],
    ['nombre', '200'],
  ])('%s passe', async (_, code) => {
    expect(await lintComponent(code)).not.toContainEqual(VALUE_REFUSAL)
  })

  test('un script JavaScript de src/ est lu aussi', async () => {
    expect(await lintRuleIds('src/value-rule-probe.js', "export const tone = '#ff0000'\n")).toContain(
      'no-restricted-syntax',
    )
  })
})

describe('aucune feuille CSS hors des jetons ne porte de valeur en dur', () => {
  test('la population balayée est celle du dépôt', () => {
    expect(SHEETS).toContain('index.css')
  })

  test.each(SHEETS)('%s', (path) => {
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
 * Ce que `shadcn init` écrit dans la feuille globale, et que le `dialog` copié sans lui n'apporte
 * pas (issue #170, décision du 2026-10-27). Son `oklch(…)` tombe sous le balayage ci-dessus, et
 * `--accent` n'y figure pas : c'est un jeton de la spec (§2.1).
 */
const SHADCN_FORMS: [string, RegExp][] = [
  [
    'variable de palette',
    /--(background|foreground|card|card-foreground|popover|primary|secondary|muted|destructive|border|input|ring|sidebar|chart-[1-5])\s*:/,
  ],
  ['tw-animate-css', /tw-animate-css/],
  ['couche base', /@apply\s+(border-border|bg-background)/],
]

/** Formes de `shadcn init` présentes dans une feuille CSS, commentaires exclus : leurs noms. */
function shadcnFormsIn(css: string): string[] {
  const code = withoutComments(css)

  return SHADCN_FORMS.filter(([, form]) => form.test(code)).map(([name]) => name)
}

describe('aucune feuille ne porte ce que `shadcn init` y écrirait', () => {
  test.each([...SHEETS, TOKENS_SHEET])('%s', (path) => {
    expect(shadcnFormsIn(readFileSync(join(SRC, path), 'utf8'))).toEqual([])
  })

  test('le balayage voit chaque forme', () => {
    const init = `
      @import "tw-animate-css";
      :root { --background: oklch(1 0 0); }
      @layer base { * { @apply border-border; } }
    `

    expect(shadcnFormsIn(init)).toEqual(SHADCN_FORMS.map(([name]) => name))
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

  test.each(['bg-(--paper)', 'shadow-(--shadow-rest)', 'ease-(--ease-out)'])(
    '%s, une classe sur un jeton, produit sa règle',
    async (className) => {
      expect(await generates(className)).toBe(true)
    },
  )

  test('la transition par défaut prend la durée et la courbe des jetons', async () => {
    const css = (await compileIndexCss()).build(['transition-colors'])

    expect(css).toMatch(/--default-transition-duration:\s*var\(--dur-fast\)/)
    expect(css).toMatch(/--default-transition-timing-function:\s*var\(--ease-out\)/)
  })
})
