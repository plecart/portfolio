/**
 * La fumée de la pile complète (#26) : le front publié, derrière le vrai Caddyfile, contre la vraie
 * API, son vrai `worker` et son vrai Redis, sur le projet que `seed.py` a semé.
 *
 * Chaque scénario tourne sous la garde ci-dessous : toute requête du navigateur passe par le relais
 * vers la pile (`stack.ts`), toute autre est refusée et fait échouer le scénario ; toute violation
 * de la CSP posée par Caddy aussi. L'épreuve du cache vient en tête, dans l'ordre du fichier : le
 * démarrage global l'a préparée, et aucun appel de la liste ne doit la précéder.
 */
import { test as base, expect, type APIRequestContext } from '@playwright/test'
import {
  compose,
  env,
  inStack,
  origin,
  projectsUrl,
  relay,
  seeded,
  servedCoverState,
} from './stack.ts'

/** Le préfixe des messages de la sonde : un événement `securitypolicyviolation` de la page. */
const PROBE = 'securitypolicyviolation'

const test = base.extend<{ guarded: void }, { stackClient: APIRequestContext }>({
  // Le client du relais vit autant que le worker de Playwright, et non qu'un scénario : celui d'un
  // scénario jette ses réponses à sa fin, quand une requête de la page peut encore attendre la
  // sienne (mesuré : `route.fulfill: Fetch response has been disposed`).
  stackClient: [
    async ({ playwright }, use) => {
      const client = await playwright.request.newContext()
      await use(client)
      await client.dispose()
    },
    { scope: 'worker' },
  ],

  guarded: [
    async ({ context, page, stackClient }, use) => {
      const refused: string[] = []
      await context.route('**/*', async (route) => {
        const sent = route.request()
        if (!inStack(sent.url())) {
          refused.push(sent.url())
          return route.abort('blockedbyclient')
        }
        const response = await relay(stackClient, sent.url(), {
          method: sent.method(),
          headers: await sent.allHeaders(),
          data: sent.postDataBuffer() ?? undefined,
        })
        await route.fulfill({ response })
      })

      // Deux voies, chacune la sienne : l'événement de la page, que la sonde rapporte, et le
      // message que Chromium écrit de lui-même sur la console.
      const events: string[] = []
      const messages: string[] = []
      page.on('console', (message) => {
        const text = message.text()
        if (text.startsWith(PROBE)) events.push(text)
        else if (text.includes('Content Security Policy')) messages.push(text)
      })
      await page.addInitScript((probe) => {
        addEventListener('securitypolicyviolation', ({ violatedDirective, blockedURI }) =>
          console.error(`${probe} ${violatedDirective} ${blockedURI}`),
        )
      }, PROBE)

      await use()
      expect({ refused, events, messages }, 'la page sort de ses origines ou de sa CSP').toEqual({
        refused: [],
        events: [],
        messages: [],
      })
    },
    { auto: true },
  ],
})

/**
 * La durée de vie restante, en secondes, de chaque entrée de la liste dans le cache de l'API —
 * `-1` sans expiration —, lue dans Redis : ses clés portent `contenu:<génération>:projets:`
 * (`apps/api/content/cache.py`).
 */
function listEntryTtls(): number[] {
  const redis = (...args: string[]) => compose(['exec', '-T', 'redis', 'redis-cli', ...args])
  const keys = redis('--scan', '--pattern', '*contenu:*:projets:*')
    .split('\n')
    .map((key) => key.trim())
    .filter(Boolean)
  return keys.map((key) => Number(redis('TTL', key)))
}

test(
  "la liste vue en attente avant le worker se voit prête à l'appel suivant, sans attendre le TTL",
  async ({ stackClient }) => {
    expect(env('SMOKE_FIRST_STATE')).toBe('pending')
    // L'entrée que le premier appel a rangée vit encore : seule la purge du worker la fait manquer.
    const entries = listEntryTtls()
    expect(entries).toHaveLength(1)
    expect(entries[0]).toBeGreaterThan(0)
    expect(await servedCoverState(stackClient)).toBe('ready')
  },
)

test('après un appel de la liste, sa clé vit dans Redis avec une durée de vie', async ({
  stackClient,
}) => {
  await relay(stackClient, projectsUrl())
  const ttls = listEntryTtls()
  expect(ttls.length).toBeGreaterThan(0)
  expect(ttls.filter((ttl) => ttl <= 0)).toEqual([])
})

test('la table montre une carte, celle du projet semé', async ({ page }) => {
  await page.goto('/')
  const cards = page.getByRole('main').getByRole('link')
  await expect(cards).toHaveCount(1)
  await expect(cards).toContainText(seeded().title)
})

test("la carte s'ouvre en fiche", async ({ page }) => {
  const { slug, title } = seeded()
  await page.goto('/')
  await page.getByRole('main').getByRole('link').click()
  await expect(page).toHaveURL(`/projets/${slug}`)
  await expect(page.getByRole('dialog', { name: title })).toBeVisible()
})

test("la fiche porte ses balises d'aperçu, son image servie par l'hôte des médias", async ({
  page,
  stackClient,
}) => {
  const { slug, title, summary } = seeded()
  await page.goto(`/projets/${slug}`)
  const og = (property: string) => page.locator(`meta[property="og:${property}"]`)
  await expect(og('title')).toHaveAttribute('content', title)
  await expect(og('description')).toHaveAttribute('content', summary)
  const image = (await og('image').getAttribute('content')) ?? ''
  expect(image.startsWith(`${origin('MEDIA_HOST')}/`), image).toBe(true)
  expect((await relay(stackClient, image)).status()).toBe(200)
})

test('un slug inconnu redirige vers la table', async ({ stackClient }) => {
  const response = await relay(stackClient, `${origin('SITE_HOST')}/projets/inconnu`)
  expect(response.status()).toBe(302)
  expect(response.headers().location).toBe('/')
})

test("le site appelle l'API sans cookie, sous son CORS", async ({ page, stackClient }) => {
  const listed = page.waitForRequest(projectsUrl())
  await page.goto('/')
  const sent = await listed.then((request) => request.allHeaders())
  expect(sent).not.toHaveProperty('cookie')
  // La réponse de la pile à cette même requête, rejouée : Chromium ne montre pas le `set-cookie`
  // d'une réponse interceptée (mesuré le 2026-11-05, en-tête ajouté au relais, scénario vert).
  const answered = (await relay(stackClient, projectsUrl(), { headers: sent })).headers()
  expect(answered).not.toHaveProperty('set-cookie')
  expect(answered['access-control-allow-origin']).toBe(origin('SITE_HOST'))
})
