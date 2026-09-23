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

test('la feuille de base de Tailwind est appliquée', async ({ page }) => {
  await page.goto('/')

  const heading = await page.locator('h1').evaluate((element) => {
    const style = getComputedStyle(element)
    return { fontSize: style.fontSize, marginTop: style.marginTop }
  })

  // Mesure la feuille de base plutôt qu'une classe utilitaire posée pour l'occasion : sans
  // Tailwind un `h1` pèse 2em et porte sa propre marge ; avec elle, il hérite et n'en a plus.
  // Le test ne dépend donc d'aucun balisage écrit exprès pour lui.
  expect(heading).toEqual({ fontSize: '16px', marginTop: '0px' })
})

test("l'index compilé porte le bloc d'aperçu une seule fois", async ({ request }) => {
  const html = await (await request.get('/')).text()

  // Les deux marqueurs sont comptés séparément : compter les blocs bien formés laisserait
  // passer un marqueur orphelin, et c'est sur les marqueurs que #14 découpera.
  expect(html.match(/<!--meta:start-->/g)).toHaveLength(1)
  expect(html.match(/<!--meta:end-->/g)).toHaveLength(1)

  const [block] = html.match(/<!--meta:start-->[\s\S]*<!--meta:end-->/) ?? []
  expect(block).toContain('<title>')
  expect(block).toContain('property="og:title"')
  expect(block).toContain('property="og:description"')
})

test('la licence de la police voyage avec la distribution', async ({ request }) => {
  const response = await request.get('/OFL.txt')

  // Le `.woff2` part chez chaque visiteur ; l'OFL 1.1 veut que son texte l'accompagne. Une
  // notice qui renvoie à un chemin du dépôt ne satisfait personne qui reçoit la distribution :
  // c'est ici, sur ce qui est réellement servi, que la condition se vérifie.
  expect(response.status()).toBe(200)
  expect(await response.text()).toContain('SIL OPEN FONT LICENSE Version 1.1')
})

test('les deux descriptions du bloc portent le même texte', async ({ page }) => {
  await page.goto('/')

  const contentOf = (selector: string) => page.locator(selector).getAttribute('content')

  // Le HTML statique ne sait pas factoriser une chaîne : `description` et `og:description` sont
  // écrites deux fois, et #14 les réécrira toutes les deux. L'égalité est donc un invariant du
  // gabarit, pas une coïncidence — sans ce test, rien ne la tiendrait.
  expect(await contentOf('meta[property="og:description"]')).toBe(
    await contentOf('meta[name="description"]'),
  )
})

test("la page ne porte aucune violation d'accessibilité", async ({ page }) => {
  await page.goto('/')

  const { violations } = await new AxeBuilder({ page }).analyze()

  // Les identifiants de règle suffisent au diagnostic et tiennent sur une ligne ; le rapport
  // complet d'axe noierait l'échec sous plusieurs écrans de contexte DOM.
  expect(violations.map((violation) => violation.id)).toEqual([])
})
