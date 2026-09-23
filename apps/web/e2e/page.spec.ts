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

/**
 * Ce que ce garde couvre, et ce qu'il ne couvre pas.
 *
 * Dénombrement du 2026-09-24 : **23 formes** de requête sortante recensées pour une page web,
 * **17 vues** ici — les 16 que `page.on('request')` rapporte (balises `src`/`href`, `@import`,
 * `url()` CSS, `@font-face`, `fetch`, `XHR`, `import()`, `sendBeacon`, `EventSource`, worker,
 * préchargements, `iframe`, `video`) plus le WebSocket, qui voyage sur un autre évènement.
 *
 * **6 hors portée**, à couvrir par l'issue qui les introduira, jamais à supposer couvertes ici :
 * Service Worker (hors du contexte de page) ; requête différée au-delà de `networkidle` ;
 * `<img loading="lazy">` sous la ligne de flottaison (#18, #20) ; `fetch` derrière une
 * interaction (#19) ; `preconnect` et `dns-prefetch`, qui joignent le tiers en DNS et TLS sans
 * jamais produire de requête HTTP.
 */
test("la page ne fait aucune requête vers un tiers", async ({ page }) => {
  const requested: string[] = []
  page.on('request', (request) => {
    requested.push(request.url())
  })
  // Un WebSocket n'apparaît jamais dans `page.on('request')` : sans cette ligne, c'est le vecteur
  // qui fuirait le plus silencieusement.
  page.on('websocket', (socket) => {
    requested.push(socket.url())
  })

  await page.goto('/', { waitUntil: 'networkidle' })

  // Les schémas `data:` et `blob:` n'ont pas d'origine et ne quittent jamais le document : les
  // compter comme tiers rendrait la mesure fausse. `ws:`/`wss:` en revanche partent bien chez un
  // tiers, et leur origine se compare après normalisation du schéma.
  const own = ownOrigin(page)
  const thirdParty = requested.filter((url) => {
    const { protocol, origin } = new URL(url)
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(protocol)) return false

    return origin.replace(/^wss?:/, (scheme) => (scheme === 'ws:' ? 'http:' : 'https:')) !== own
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
  const faces = await page.evaluate(() =>
    [...document.fonts].map((face) => [face.family, face.weight, face.display]),
  )

  expect(family).toContain('Manrope')
  // Les trois moitiés de la décision de la spec §2.2 — famille, graisses variables 200–800 et
  // `font-display: swap` — sont assenées ensemble. Prises séparément, deux d'entre elles
  // n'étaient tenues que par la lecture du fichier.
  expect(faces).toEqual([['Manrope', '200 800', 'swap']])
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

test('le projet mobile émule un appareil tactile de 400 px', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'contrat du projet mobile seulement')

  await page.goto('/')

  // Contrat repris par #20 et #21 (brief de #3). Sans cette assertion, retirer le descripteur
  // d'appareil de `playwright.config.ts` laissait la suite entièrement verte : un contrat que
  // seule la lecture d'un fichier de configuration garantit n'est pas un contrat.
  expect(
    await page.evaluate(() => ({
      width: window.innerWidth,
      touch: navigator.maxTouchPoints > 0,
    })),
  ).toEqual({ width: 400, touch: true })
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
