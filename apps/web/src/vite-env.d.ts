/** Variables d'environnement que la compilation injecte (`.env.<mode>`, préfixe `VITE_`). */
interface ImportMetaEnv {
  /** L'origine de l'API publique, sans chemin ; `vite.config.ts` refuse de compiler sans elle. */
  readonly VITE_API_URL: string
}
