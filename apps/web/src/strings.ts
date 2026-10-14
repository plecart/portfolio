/**
 * Catalogue de chaînes du front : tout texte que l'interface rend ou annonce, en français, avec
 * l'apostrophe typographique « ’ » (spec §6.2). Identifiants en anglais, valeurs en français ; un
 * seul catalogue par application (cadrage §2, D52).
 *
 * Un texte écrit en dur dans un composant est refusé par ESLint (CONTRIBUTING.md, « Chaînes du
 * front ») ; formes couvertes et hors portée : tests/string-rule.test.ts.
 */
export const strings = {
  /** Nom de l'auteur : titre de la page et lien vers l'accueil (spec §3.3). */
  siteName: 'Pacôme Bernier',
  /** Bouton de mode : il dit le mode visé, l'autre que celui affiché (spec §3.3). */
  switchToDark: 'Passer en mode sombre',
  switchToLight: 'Passer en mode clair',
} as const
