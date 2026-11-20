/**
 * Ce que la collecte Lighthouse mesure. L'écran d'erreur tient les quatre seuils de la spec §1.16
 * (99, 100, 100, 100, mesuré le 2026-10-31) et `lhci` n'a aucune assertion de minimum — `minScore`,
 * `maxLength` et `maxNumericValue` seulement (`@lhci/utils`, `assertions.js`) : sans ces scénarios,
 * un serveur qui ne servirait plus la table, ou la fiche, rendrait la porte verte sans rien avoir
 * mesuré.
 *
 * Le `test` de Playwright, et non celui d'`api.ts` : rien n'est intercepté, sauf l'API de
 * production, qu'une origine mal remplacée joindrait.
 */
import { expect, type Locator, test } from '@playwright/test'
import lighthouse from '../lighthouserc.json' with { type: 'json' }
import { API_ORIGIN } from './api.ts'
import { gallery } from './project.ts'
import { pageBottom, scrollThrough } from './scroll.ts'
import { ribbonIcons } from './table.ts'

/** Les adresses de la collecte : la table, à la racine du serveur, puis la fiche du premier projet. */
const [SERVER, PROJECT_PAGE] = lighthouse.ci.collect.url

/**
 * L'adresse de chaque image de `images` que le navigateur n'a pas décodée. Le repli SPA rend du HTML
 * en 200 pour une route perdue : seule l'image décodée prouve la sienne.
 */
function undecoded(images: Locator): Promise<string[]> {
  return images.evaluateAll((all: HTMLImageElement[]) =>
    all.filter((image) => !image.complete || image.naturalWidth === 0).map((image) => image.src),
  )
}

test('la collecte mesure la table à douze cartes, images et icônes comprises', async ({
  page,
  request,
}) => {
  await page.route(`${API_ORIGIN}/**`, (route) => route.abort())

  await page.goto(SERVER)

  const table = page.getByRole('main')
  await expect(table.getByRole('link')).toHaveCount(12)
  // `lazy` : une image ne part qu'à l'approche de l'écran.
  await scrollThrough(page, await pageBottom(page))
  const images = table.locator('img')
  // Onze couvertures : toute la population.
  await expect(images).toHaveCount(11)
  await expect.poll(() => undecoded(images)).toEqual([])
  // Vingt icônes, des masques (#271) : chacune servie en SVG, et non par le repli SPA.
  const masks = (await ribbonIcons(table)).map(({ mask }) => mask)
  expect(masks).toHaveLength(20)
  for (const mask of new Set(masks)) {
    const icon = mask.slice('url("'.length, -'")'.length)
    expect((await request.get(icon)).headers()['content-type']).toBe('image/svg+xml')
  }
})

test('la collecte mesure la fiche, la première image de sa galerie décodée', async ({ page }) => {
  await page.route(`${API_ORIGIN}/**`, (route) => route.abort())

  await page.goto(PROJECT_PAGE)

  // La première variante de sa première image : la fiche ouverte est celle du premier projet.
  const image = gallery(page).locator('img').first()
  await expect(image).toHaveAttribute('src', new URL('/images/projet-01/480.webp', SERVER).href)
  await expect.poll(() => undecoded(image)).toEqual([])
})

test('un fichier absent répond 404, et le serveur reste debout', async ({ request }) => {
  expect((await request.get(new URL('/images/absent/0.webp', SERVER).href)).status()).toBe(404)

  expect((await request.get(SERVER)).ok()).toBe(true)
})
