/**
 * L'API publique dans les scénarios : la requête de la liste est toujours interceptée, jamais
 * envoyée (brief de #19, décision 10).
 *
 * Toute page sert `[]` par défaut — le `test` de ce module, que chaque scénario importe à la place
 * de celui de Playwright : sans lui, la version compilée appellerait l'API de production. Un geste
 * posé par le scénario l'emporte, Playwright jouant les routes dans l'ordre inverse de leur pose.
 * Les gestes visent le chemin de la liste sur toute origine. Leurs réponses ne portent pas
 * d'en-tête CORS : Chromium ne l'exige pas d'une réponse interceptée (mesuré le 2026-10-16, en-tête
 * retiré, scénarios verts) ; la politique CORS réelle de l'API est éprouvée côté back (#10).
 */
import { join } from 'node:path'
import { test as base, type Page, type Route } from '@playwright/test'
import { loadEnv } from 'vite'
import type { Project } from './projects.ts'

export { expect } from '@playwright/test'

/**
 * L'origine de l'API dans la version compilée, lue dans la même source que la compilation : les
 * fichiers de mode de l'application, quel que soit le répertoire d'où les scénarios sont lancés.
 */
export const API_ORIGIN = new URL(loadEnv('production', join(import.meta.dirname, '..')).VITE_API_URL)
  .origin

/** La liste, sur toute origine. */
const PROJECTS_PATH = '**/api/projets'

/** Une réponse à la requête de la liste : un jeu servi, ou une défaillance. */
export type Answer = (route: Route) => Promise<void>

/** La réponse qui sert un jeu de projets. */
export const serving =
  (projects: Project[]): Answer =>
  (route) =>
    route.fulfill({ json: projects })

/** Les trois défaillances que le site traite comme une seule : l'état erreur (décision 6). */
export const FAILURES: Record<string, Answer> = {
  'réseau injoignable': (route) => route.abort(),
  'statut 500': (route) => route.fulfill({ status: 500, json: { detail: 'Erreur' } }),
  'corps non JSON': (route) => route.fulfill({ body: '<!doctype html>' }),
}

/** Sert un jeu de projets à chaque requête de la liste. */
export async function serveProjects(page: Page, projects: Project[]) {
  await page.route(PROJECTS_PATH, serving(projects))
}

/**
 * Tient la prochaine requête de la liste en attente ; les suivantes reviennent aux autres gestes.
 *
 * @returns Le geste qui la relâche avec une réponse, dès la requête arrivée.
 */
export async function holdProjects(page: Page): Promise<(answer: Answer) => Promise<void>> {
  let arrived!: (route: Route) => void
  const held = new Promise<Route>((resolve) => (arrived = resolve))
  await page.route(PROJECTS_PATH, (route) => arrived(route), { times: 1 })
  return async (answer) => answer(await held)
}

export const test = base.extend<{ emptyApi: void }>({
  emptyApi: [
    async ({ page }, use) => {
      await serveProjects(page, [])
      await use()
    },
    { auto: true },
  ],
})
