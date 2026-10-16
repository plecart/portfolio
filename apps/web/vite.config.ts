/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ command, mode }) => {
  // L'origine de l'API n'a pas de valeur par défaut (brief de #19, décision 4) : sans elle, Vite
  // remplacerait `import.meta.env.VITE_API_URL` par `undefined`, et le site compilé appellerait
  // une adresse fausse sans que rien ne le signale. À la compilation seulement : Vitest charge la
  // même configuration en mode `test`, sans fichier d'environnement. Lue depuis le répertoire
  // courant, d'où Vite résout sa racine. Une adresse qui n'est pas en `http(s)` est refusée de
  // même : `localhost:8000` se lit comme une URL au schéma `localhost:`, et l'adresse de la liste,
  // construite au chargement du module, empêcherait alors toute la page de se monter.
  const apiUrl = URL.parse(loadEnv(mode, process.cwd()).VITE_API_URL ?? '')
  if (command === 'build' && !['http:', 'https:'].includes(apiUrl?.protocol ?? '')) {
    throw new Error(`VITE_API_URL absente ou mal formée pour le mode « ${mode} » : apps/web/.env.${mode}`)
  }

  return {
    // Tailwind v4 passe par son plugin Vite, jamais par le script CDN `cdn.tailwindcss.com`
    // (ADR 0008) : le CSS est compilé au build, et rien ne s'exécute dans le navigateur.
    plugins: [tailwindcss(), react()],
    test: {
      // Borné à `tests/` : le motif par défaut de Vitest ramasserait aussi les scénarios
      // Playwright de `e2e/`, qui ne tournent pas dans le même lanceur.
      include: ['tests/**/*.test.ts'],
    },
  }
})
