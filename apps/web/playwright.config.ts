import { defineConfig, devices } from '@playwright/test'
import lighthouse from './lighthouserc.json' with { type: 'json' }

/**
 * Port du serveur statique de test. Il n'apparaît qu'ici : le script `preview` du manifeste le
 * reçoit en argument, pour qu'une seule valeur commande l'adresse de base et le serveur.
 */
const PORT = 4173
const BASE_URL = `http://localhost:${PORT}`

const PIXEL_5 = devices['Pixel 5']

export default defineConfig({
  testDir: './e2e',

  // Les scénarios s'exécutent contre la **version compilée**, jamais contre le serveur de
  // développement : c'est elle que Caddy sert en production (ADR 0008), et elle seule porte le
  // HTML final — celui où #14 viendra remplacer le bloc d'aperçu.
  //
  // `--strictPort` est indispensable : sans lui Vite glisse sur le port suivant quand 4173 est
  // pris, et les scénarios interrogeraient une application qui n'est pas celle qu'on vient de
  // compiler.
  webServer: [
    {
      command: `npm run build && npm run preview -- --port ${PORT} --strictPort`,
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
    },
    // Le serveur de la collecte Lighthouse, que `lighthouse-server.spec.ts` éprouve. Attendu sur la
    // liste : son index n'existe pas pendant que la compilation d'à côté vide `dist`.
    {
      command: 'node e2e/lighthouse-server.ts',
      url: new URL('/api/projets', lighthouse.ci.collect.url[0]).href,
      reuseExistingServer: !process.env.CI,
    },
  ],

  use: { baseURL: BASE_URL },

  // Chromium seul (ADR 0008 : un seul moteur à maintenir). Les deux projets sont le contrat des
  // scénarios : la largeur desktop de référence, et un appareil tactile réel.
  projects: [
    { name: 'desktop', use: devices['Desktop Chrome'] },
    {
      name: 'mobile',
      use: { ...PIXEL_5, viewport: { ...PIXEL_5.viewport, width: 400 } },
    },
  ],
})
