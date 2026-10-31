/**
 * Ce que la collecte Lighthouse mesure. L'écran d'erreur tient les quatre seuils de la spec §1.16
 * (99, 100, 100, 100, mesuré le 2026-10-31) et `lhci` n'a aucune assertion de minimum — `minScore`,
 * `maxLength` et `maxNumericValue` seulement (`@lhci/utils`, `assertions.js`) : sans ce scénario, un
 * serveur qui ne servirait plus la table rendrait la porte verte sans rien avoir mesuré.
 *
 * Le `test` de Playwright, et non celui d'`api.ts` : rien n'est intercepté, sauf l'API de
 * production, qu'une origine mal remplacée joindrait.
 */
import { expect, test } from '@playwright/test'
import lighthouse from '../lighthouserc.json' with { type: 'json' }
import { API_ORIGIN } from './api.ts'
import { scrollThrough } from './scroll.ts'

/** L'adresse de la collecte : celle du serveur. */
const [SERVER] = lighthouse.ci.collect.url

test('la collecte mesure la table à douze cartes, images comprises', async ({ page }) => {
  await page.route(`${API_ORIGIN}/**`, (route) => route.abort())

  await page.goto(SERVER)

  const table = page.getByRole('main')
  await expect(table.getByRole('link')).toHaveCount(12)
  // `lazy` : une image ne part qu'à l'approche de l'écran.
  await scrollThrough(page, await page.evaluate(() => document.documentElement.scrollHeight))
  const images = table.locator('img')
  // Onze couvertures, leurs quatre copies en cours, vingt icônes : toute la population.
  await expect(images).toHaveCount(11 + 4 + 20)
  // Le repli SPA rend du HTML en 200 pour une route perdue : seule l'image décodée la prouve.
  await expect
    .poll(() =>
      images.evaluateAll((all: HTMLImageElement[]) =>
        all.filter((image) => !image.complete || image.naturalWidth === 0).map((image) => image.src),
      ),
    )
    .toEqual([])
})

test('un fichier absent répond 404, et le serveur reste debout', async ({ request }) => {
  expect((await request.get(new URL('/images/absent/0.webp', SERVER).href)).status()).toBe(404)

  expect((await request.get(SERVER)).ok()).toBe(true)
})
