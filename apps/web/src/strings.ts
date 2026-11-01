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
  /** Liens de l'auteur, dans leur ordre (spec §3.4). */
  authorGitHub: 'GitHub de Pacôme Bernier',
  authorLinkedIn: 'LinkedIn de Pacôme Bernier',
  /** Message d'erreur de la table, et le lien qui relance le chargement (spec §4.5). */
  loadError: 'Les projets ne se chargent pas.',
  retry: 'Réessayer',
  /** États d'une carte : la phrase de son libellé, puis le texte de son ruban (spec §4.1). */
  stateOngoing: 'En cours',
  stateLive: 'En ligne',
  ribbonOngoing: 'en cours',
  ribbonLive: 'en ligne',
  /** Ce qui remplace les rubans d'une carte révélée au toucher (spec §4.1). */
  openCard: 'Ouvrir',
} as const
