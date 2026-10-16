/**
 * Le chargement de la liste et les états qui précèdent la table (spec §1.3, §1.15, §5.1-5.3 ; brief
 * de #19), sur la page servie, l'API interceptée par les gestes d'`api.ts`.
 */
import { API_ORIGIN, expect, FAILURES, holdProjects, serving, test } from './api.ts'

test("au démarrage, une seule requête : la liste, sur l'origine de l'API", async ({ page }) => {
  const requested: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/')) requested.push(request.url())
  })

  // Le mode strict de React double les effets en développement seulement : la version compilée
  // n'en joue qu'un (décision 6).
  await page.goto('/', { waitUntil: 'networkidle' })

  expect(requested).toEqual([`${API_ORIGIN}/api/projets`])
})

for (const [name, answer] of Object.entries({ 'liste vide': serving([]), ...FAILURES })) {
  test(`la table est occupée pendant le chargement, libérée par la réponse — ${name}`, async ({
    page,
  }) => {
    const release = await holdProjects(page)
    await page.goto('/')
    const table = page.getByRole('main')

    await expect(table).toHaveAttribute('aria-busy', 'true')
    await release(answer)

    await expect(table).not.toHaveAttribute('aria-busy')
  })
}
