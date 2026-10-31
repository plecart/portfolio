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

test('la collecte mesure la table à douze cartes, images comprises', async ({ page }) => {
  await page.route(`${API_ORIGIN}/**`, (route) => route.abort())

  await page.goto(lighthouse.ci.collect.url[0])

  const table = page.getByRole('main')
  await expect(table.getByRole('link')).toHaveCount(12)
  const cover = table.locator('img[srcset]').first()
  await expect(cover).toHaveJSProperty('complete', true)
  expect(await cover.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0)
})
