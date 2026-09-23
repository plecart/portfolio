/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  test: {
    // Borné à `tests/` : le motif par défaut de Vitest ramasserait aussi les scénarios
    // Playwright de `e2e/`, qui ne tournent pas dans le même lanceur.
    include: ['tests/**/*.test.ts'],
  },
})
