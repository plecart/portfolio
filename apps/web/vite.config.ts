/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // Tailwind v4 passe par son plugin Vite, jamais par le script CDN `cdn.tailwindcss.com`
  // (ADR 0008) : le CSS est compilé au build, et rien ne s'exécute dans le navigateur.
  plugins: [tailwindcss(), react()],
  test: {
    // Borné à `tests/` : le motif par défaut de Vitest ramasserait aussi les scénarios
    // Playwright de `e2e/`, qui ne tournent pas dans le même lanceur.
    include: ['tests/**/*.test.ts'],
  },
})
