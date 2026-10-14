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

// Règle des chaînes : aucun texte d'interface en dur dans un composant — il vient du catalogue
// `src/strings.ts` (spec §6.2). Visé : un texte qui contient une lettre, là où l'interface le rend
// (enfant JSX) ou l'annonce (attribut ci-dessous). Lettres en classe entre crochets, pour la même
// raison que les motifs des valeurs. Formes couvertes et hors portée : tests/string-rule.test.ts.
const LETTER = '/[a-zà-öø-ÿœæ]/i'
const ANNOUNCED_ATTRIBUTES = [
  'aria-label',
  'aria-description',
  'aria-roledescription',
  'aria-braillelabel',
  'aria-brailleroledescription',
  'aria-valuetext',
  'aria-placeholder',
  'title',
  'alt',
  'abbr',
  'placeholder',
  'label',
  // Rendu en texte par React, comme un enfant JSX.
  'children',
]
const ANNOUNCED = `JSXAttribute[name.name=/^(${ANNOUNCED_ATTRIBUTES.join('|')})$/]`
const IN_BRACES = `:matches(JSXElement, JSXFragment, ${ANNOUNCED}) > JSXExpressionContainer`
const stringSelectors = [
  `JSXText[value=${LETTER}]`,
  `${IN_BRACES} > Literal[value=${LETTER}]`,
  `${IN_BRACES} > TemplateLiteral > TemplateElement[value.raw=${LETTER}]`,
  `${ANNOUNCED} > Literal[value=${LETTER}]`,
].map((selector) => ({
  selector,
  message: "Texte d'interface en dur : passer par le catalogue src/strings.ts (spec §6.2).",
}))

export default tseslint.config(
  { ignores: ['dist'] },
  js.configs.recommended,
  // L'analyseur et les règles TypeScript sur les seuls fichiers TypeScript : appliqués partout, ils
  // liraient aussi les scripts classiques de `public/` en modules, sans y refuser un `export`.
  { files: ['**/*.{ts,tsx,mts,cts}'], extends: [tseslint.configs.recommended] },
  // `configs.flat['recommended-latest']`, et non `configs['recommended-latest']` : dans
  // `eslint-plugin-react-hooks` 7.1.1, l'entrée de premier niveau est encore au format
  // `.eslintrc` (sa clé `plugins` est un tableau de chaînes) et ESLint 9 la refuse.
  reactHooks.configs.flat['recommended-latest'],
  jsxA11y.flatConfigs.recommended,
  // Une seule entrée `no-restricted-syntax` par fichier : d'un bloc à l'autre, ESLint remplace
  // les options d'une règle au lieu de les cumuler. Valeurs et chaînes partagent donc cette entrée,
  // et toute autre liste de sélecteurs sur `src/` s'y ajoute.
  {
    files: ['src/**/*.{js,jsx,mjs,cjs,ts,tsx,mts,cts}'],
    rules: { 'no-restricted-syntax': ['error', ...valueSelectors, ...stringSelectors] },
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
    // Rendue par typescript-eslint aux seuls fichiers TypeScript : une comparaison tapée pour une
    // affectation passerait sinon.
    rules: { 'no-unused-expressions': 'error' },
  },
)
