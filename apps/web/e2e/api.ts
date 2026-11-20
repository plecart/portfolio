/**
 * L'API publique et les fichiers dans les scénarios : la requête de la liste et celles des images
 * sont toujours interceptées, jamais envoyées (brief de #19, décision 10).
 *
 * Toute page sert `[]` par défaut — le `test` de ce module, que chaque scénario importe à la place
 * de celui de Playwright : sans lui, la version compilée appellerait l'API de production. Un geste
 * posé par le scénario l'emporte, Playwright jouant les routes dans l'ordre inverse de leur pose.
 * Les gestes visent le chemin de la liste sur toute origine. Leurs réponses, comme celles des
 * fichiers, ne posent aucun en-tête CORS : Playwright ajoute `Access-Control-Allow-Origin` à toute
 * réponse interceptée d'une requête d'une autre origine (`Route.fulfill`, `_maybeAddCorsHeaders`,
 * playwright-core 1.64.1, lu le 2026-11-20) — la liste, et l'icône qu'un masque CSS charge en CORS
 * (#271). La politique CORS réelle de l'API est éprouvée côté back (#10).
 */
import { join } from 'node:path'
import { test as base, type Page, type Route } from '@playwright/test'
import { loadEnv } from 'vite'
import { FILES_ORIGIN, fixturePath, type Project } from './projects.ts'

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

/**
 * Compte les requêtes de la liste à partir de maintenant, servies ou non.
 *
 * @returns De quoi lire le compte.
 */
export function countProjectRequests(page: Page): () => number {
  let count = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/projets')) count += 1
  })
  return () => count
}

/** Sert les images et les icônes des jeux depuis `fixtures/` : leur origine n'est jamais résolue. */
async function serveFiles(page: Page) {
  await page.route(`${FILES_ORIGIN}/**`, (route) =>
    route.fulfill({ path: fixturePath(new URL(route.request().url()).pathname) }),
  )
}

export const test = base.extend<{ isolatedNetwork: void }>({
  isolatedNetwork: [
    async ({ page }, use) => {
      await serveProjects(page, [])
      await serveFiles(page)
      await use()
    },
    { auto: true },
  ],
})
