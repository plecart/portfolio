// Configuration ESLint de l'application web.
//
// Écrite à la main : le gabarit `create-vite` ne fournit plus de configuration ESLint depuis sa
// version 9 (il livre `oxlint`, retiré ici — deux linters pour une seule règle d'accessibilité
// seraient un doublon). La décision ESLint + `jsx-a11y` vient de l'ADR 0008.
//
// ESLint est épinglé sur la ligne 9 tant que `eslint-plugin-jsx-a11y` ne déclare pas la 10 comme
// pair : la faire tourner demanderait de forcer un pair non déclaré — sur le plugin même dont on
// dépend pour l'accessibilité. Le refus, et le test qui le fait expirer :
// docs/frontend-outillage.md §2.4.
import js from '@eslint/js'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'
import forbiddenValues from './forbidden-values.json' with { type: 'json' }

// Règle des valeurs : aucune couleur, durée ou courbe en dur dans un composant — elles viennent
// des jetons de `src/tokens.css` (spec §2). Chaque motif de `forbidden-values.json`, que le
// balayage des feuilles CSS lit aussi, vise les chaînes et les gabarits : classes et styles.
// Insensibles à la casse, comme CSS l'est pour ses fonctions et ses unités. esquery ne garde pas
// les antislashs d'une expression régulière de sélecteur, d'où des motifs faits de classes entre
// crochets. Formes couvertes et hors portée : tests/value-rule.test.ts.
const valueSelectors = forbiddenValues.flatMap(({ name, pattern }) => {
  const message = `Valeur en dur (${name}) : passer par un jeton de src/tokens.css (spec §2).`
  return [
    { selector: `Literal[value=/${pattern}/i]`, message },
    { selector: `TemplateElement[value.raw=/${pattern}/i]`, message },
  ]
})

export default tseslint.config(
  { ignores: ['dist'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  // `configs.flat['recommended-latest']`, et non `configs['recommended-latest']` : dans
  // `eslint-plugin-react-hooks` 7.1.1, l'entrée de premier niveau est encore au format
  // `.eslintrc` (sa clé `plugins` est un tableau de chaînes) et ESLint 9 la refuse.
  reactHooks.configs.flat['recommended-latest'],
  jsxA11y.flatConfigs.recommended,
  // Une seule entrée `no-restricted-syntax` par fichier : d'un bloc à l'autre, ESLint remplace
  // les options d'une règle au lieu de les cumuler. Toute autre liste de sélecteurs sur `src/`
  // s'ajoute donc à celle-ci.
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: { 'no-restricted-syntax': ['error', ...valueSelectors] },
  },
  // `public/` est copié tel quel par Vite et chargé en script classique, hors de toute
  // compilation : ni module, ni Node — seulement les globales du navigateur qu'il lit, déclarées
  // une à une plutôt que par un paquet de globales qui n'apporterait que cela.
  {
    files: ['public/**/*.js'],
    languageOptions: {
      sourceType: 'script',
      globals: { document: 'readonly', localStorage: 'readonly' },
    },
  },
)
