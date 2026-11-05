import { defineConfig, devices } from '@playwright/test'
import { origin } from './stack.ts'

/**
 * La configuration de la fumée (#26), à part de celle de `e2e/` : ses scénarios tournent contre la
 * pile complète que `make smoke` a démarrée, jamais contre `vite preview` et une API simulée — d'où
 * aucun `webServer`. Le site sous son origine de production, que le relais sert depuis la pile.
 */
export default defineConfig({
  testDir: '.',
  globalSetup: './global-setup.ts',
  use: { baseURL: origin('SITE_HOST') },
  // Chromium seul (ADR 0008), au seul format desktop (brief de #26, décision 6) : la fumée éprouve
  // la pile, la suite E2E les deux formats.
  projects: [{ name: 'desktop', use: devices['Desktop Chrome'] }],
})
