/**
 * Ce que seule la page réellement servie peut prouver.
 *
 * Ces scénarios tournent contre la version compilée et servie en statique — la même que Caddy
 * publiera. Aucun test unitaire ne peut les remplacer : ils mesurent le HTML final, le trafic
 * réseau du navigateur et l'arbre d'accessibilité rendu.
 */
// Import nommé, pas défaut : le paquet expose `export { AxeBuilder, AxeBuilder as default }`
// (`dist/index.d.ts`), et la forme par défaut n'est pas constructible sans `esModuleInterop`,
// que le projet n'active pas.
import { AxeBuilder } from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

/** L'origine que le site sert lui-même. Tout ce qui n'en vient pas est un tiers. */
function ownOrigin(page: Page): string {
  return new URL(page.url()).origin
}

test("la page déclare le français comme langue du document", async ({ page }) => {
  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('lang', 'fr')
})

test("la page ne fait aucune requête vers un tiers", async ({ page }) => {
  const requested: string[] = []
  page.on('request', (request) => {
    requested.push(request.url())
  })

  await page.goto('/', { waitUntil: 'networkidle' })

  // Les schémas `data:` et `blob:` n'ont pas d'origine et ne quittent jamais le document :
  // les compter comme tiers rendrait la mesure fausse.
  const own = ownOrigin(page)
  const thirdParty = requested.filter((url) => {
    const { protocol, origin } = new URL(url)
    return (protocol === 'http:' || protocol === 'https:') && origin !== own
  })

  expect(thirdParty).toEqual([])
})

test('la page rend son texte en Manrope, servie par le site', async ({ page }) => {
  const fontRequests: string[] = []
  page.on('request', (request) => {
    if (request.url().endsWith('.woff2')) fontRequests.push(request.url())
  })

  await page.goto('/', { waitUntil: 'networkidle' })

  const family = await page
    .locator('h1')
    .evaluate((element) => getComputedStyle(element).fontFamily)

  expect(family).toContain('Manrope')
  // Une seule police, servie par le site lui-même : c'est la condition des 25 Ko de la spec §6.4.
  expect(fontRequests.map((url) => new URL(url).origin)).toEqual([ownOrigin(page)])
})

test("la page ne porte aucune violation d'accessibilité", async ({ page }) => {
  await page.goto('/')

  const { violations } = await new AxeBuilder({ page }).analyze()

  // Les identifiants de règle suffisent au diagnostic et tiennent sur une ligne ; le rapport
  // complet d'axe noierait l'échec sous plusieurs écrans de contexte DOM.
  expect(violations.map((violation) => violation.id)).toEqual([])
})
