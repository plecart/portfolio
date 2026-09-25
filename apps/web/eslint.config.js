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

export default tseslint.config(
  { ignores: ['dist'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  // `configs.flat['recommended-latest']`, et non `configs['recommended-latest']` : dans
  // `eslint-plugin-react-hooks` 7.1.1, l'entrée de premier niveau est encore au format
  // `.eslintrc` (sa clé `plugins` est un tableau de chaînes) et ESLint 9 la refuse.
  reactHooks.configs.flat['recommended-latest'],
  jsxA11y.flatConfigs.recommended,
)
