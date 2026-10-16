/**
 * Le chargement de la liste et les états qui précèdent la table (spec §1.3, §1.15, §3.1, §4.5,
 * §5.1-5.3, §6.3 ; brief de #19), sur la page servie, l'API interceptée par les gestes d'`api.ts`.
 */
import { AxeBuilder } from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { API_ORIGIN, expect, FAILURES, holdProjects, serving, test, type Answer } from './api.ts'
import { resolveAll } from './css.ts'
import { PROJECT_SETS } from './projects.ts'
import { COLUMN_VIEWPORT, expectPlacement } from './table.ts'

/** Les cellules de la table : pendant le chargement, ses trois cadres. */
const cells = (page: Page) => page.locator('[data-table-cell]')

/** Ouvre la page sur la requête de la liste tenue en attente : l'état chargement. */
async function openLoading(page: Page) {
  const release = await holdProjects(page)
  await page.goto('/')
  await expect(cells(page)).toHaveCount(3)
  return release
}

/** Ouvre la page sur une réponse, et attend qu'elle ait quitté l'état chargement. */
async function openAnswered(page: Page, answer: Answer) {
  const release = await holdProjects(page)
  await page.goto('/')
  await expect(page.getByRole('main')).toHaveAttribute('aria-busy', 'true')
  await release(answer)
  await expect(page.getByRole('main')).not.toHaveAttribute('aria-busy')
}

test("au démarrage, une seule requête : la liste, sur l'origine de l'API, servie par l'interception", async ({
  page,
}) => {
  const requested: string[] = []
  page.on('request', (request) => {
    if (new URL(request.url()).origin === API_ORIGIN) requested.push(request.url())
  })
  const served = page.waitForResponse('**/api/projets', { timeout: 5000 })

  // Le mode strict de React double les effets en développement seulement : la version compilée
  // n'en joue qu'un (décision 6).
  await page.goto('/', { waitUntil: 'networkidle' })

  expect(requested).toEqual([`${API_ORIGIN}/api/projets`])
  // Le `[]` du `test` d'`api.ts`, et non une réponse de l'API réelle : sans l'interception par
  // défaut, chaque scénario joindrait la production en restant vert.
  expect(await (await served).json()).toEqual([])
})

for (const [name, answer] of Object.entries({ 'liste vide': serving([]), ...FAILURES })) {
  test(`la table est occupée pendant le chargement, libérée par la réponse — ${name}`, async ({
    page,
  }) => {
    await openAnswered(page, answer)
  })
}

test('chargement : trois cadres aux dimensions des cartes, la vitrine en tête (spec §4.1, §5.5)', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
  await openLoading(page)

  const boxes = await Promise.all((await cells(page).all()).map((cell) => cell.boundingBox()))
  const [showcase, first, second] = boxes.map((box) => [box!.x, box!.y, box!.width, box!.height])

  if (isMobile) {
    // 400 px : la vitrine sur la première rangée entière, les deux simples dessous ; 16 px de
    // marge et de gouttière.
    expect(showcase).toEqual([16, showcase[1], 368, 412])
    expect([first, second]).toEqual([
      [16, showcase[1] + 412 + 16, 176, 214],
      [208, showcase[1] + 412 + 16, 176, 214],
    ])
  } else {
    // 1280 px : quatre colonnes, un bloc de 1044 px centré, 118 px de marge de chaque côté.
    expect(showcase).toEqual([118, showcase[1], 508, 558])
    expect([first, second]).toEqual([
      [118 + 508 + 28, showcase[1], 240, 282],
      [118 + 508 + 28 + 240 + 28, showcase[1], 240, 282],
    ])
  }
})

test('chargement : les cadres sont cachés et inertes, sans post-it ni ruban', async ({ page }) => {
  await openLoading(page)

  for (const cell of await cells(page).all()) {
    await expect(cell).toHaveAttribute('aria-hidden', 'true')
    await expect(cell).toHaveAttribute('inert')
  }
  // Rien de focalisable, rien de nommé : ni lien, ni bouton, ni texte.
  await expect(page.getByRole('main')).toHaveText('')
})

test('chargement : la face pulse en 1,8 s, courbe --ease-in-out, sans fin (spec §2.7, §5.1)', async ({
  page,
}) => {
  await openLoading(page)
  const [duration, curve] = await resolveAll(page, [
    ['animation-duration', 'var(--dur-pulse)'],
    ['animation-timing-function', 'var(--ease-in-out)'],
  ])

  // La pulsation est sur la face, jamais sur la cellule : la mesure des liens lit la cellule
  // (contrat de `TABLE_CELL_SELECTOR`).
  for (const cell of await cells(page).all()) {
    const [own, face] = await cell.evaluate((element) =>
      [element, element.firstElementChild!].map((node) => {
        const style = getComputedStyle(node)
        return [
          style.animationName,
          style.animationDuration,
          style.animationTimingFunction,
          style.animationIterationCount,
        ]
      }),
    )
    expect(own[0]).toBe('none')
    expect(face).toEqual(['frame-pulse', duration, curve, 'infinite'])
  }
  expect(duration).toBe('1.8s')
})

test('chargement en mouvement réduit : aucune pulsation (spec §6.3)', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await openLoading(page)

  for (const cell of await cells(page).all()) {
    expect(await cell.evaluate((element) => getComputedStyle(element.firstElementChild!).animationName)).toBe(
      'none',
    )
  }
})

test("chargement : les cadres sont des cellules — liens de l'auteur en pied de page à 1100 px, en colonne à 1280", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'largeurs de bureau : le projet desktop les porte')
  await page.setViewportSize({ width: 1100, height: 800 })
  await openLoading(page)

  // Quatre colonnes : un bloc de 1044 px, 28 px de marge (spec §3.4).
  await expectPlacement(page, 'footer')
  await page.setViewportSize(COLUMN_VIEWPORT)
  await expectPlacement(page, 'column')
})

for (const [failure, answer] of Object.entries(FAILURES)) {
  test(`erreur : le message et « Réessayer », aucun cadre — ${failure}`, async ({ page }) => {
    await openAnswered(page, answer)
    const status = page.getByRole('status')

    await expect(status).toHaveText('Les projets ne se chargent pas. Réessayer')
    await expect(status.getByRole('button')).toHaveAccessibleName('Réessayer')
    await expect(cells(page)).toHaveCount(0)
  })
}

test('erreur : « Réessayer » est un lien à la ligne, centré, souligné à 3 px, à l’accent (spec §4.5)', async ({
  page,
}) => {
  await openAnswered(page, FAILURES['statut 500'])
  const status = page.getByRole('status')
  const retry = status.getByRole('button')
  const [accent] = await resolveAll(page, [['color', 'var(--accent)']])

  await expect(retry).toHaveCSS('color', accent)
  await expect(retry).toHaveCSS('text-decoration-line', 'underline')
  await expect(retry).toHaveCSS('text-underline-offset', '3px')
  // Deux lignes de 24 px : le texte, puis le lien seul, centré comme lui.
  const [paragraph, button] = [(await status.boundingBox())!, (await retry.boundingBox())!]
  expect([paragraph.height, button.height, button.y - paragraph.y]).toEqual([48, 24, 24])
  expect(Math.round(button.x + button.width / 2)).toBe(Math.round(paragraph.x + paragraph.width / 2))
})

test('erreur : le message est centré entre l’entête et les liens de l’auteur (spec §4.5)', async ({
  page,
  isMobile,
}) => {
  await openAnswered(page, FAILURES['statut 500'])
  const viewport = page.viewportSize()!
  const message = (await page.getByRole('status').boundingBox())!
  const footer = (await page.getByRole('contentinfo').boundingBox())!
  // En colonne, les liens flottent : l'espace va jusqu'au bas de la fenêtre ; en pied de page, il
  // s'arrête au-dessus d'eux.
  const bottom = isMobile ? footer.y : viewport.height
  // L'espace commence sous l'entête fixe de 56 px (spec §3.3).
  const top = 56

  expect(Math.round(message.x + message.width / 2)).toBe(viewport.width / 2)
  expect(Math.abs(message.y + message.height / 2 - (top + bottom) / 2)).toBeLessThanOrEqual(1)
})

test('erreur : « Réessayer » relance la requête sans recharger la page — cadres, puis table', async ({
  page,
}) => {
  let requests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/projets')) requests += 1
  })
  await openAnswered(page, FAILURES['réseau injoignable'])
  // Un témoin posé dans la page : un rechargement l'effacerait.
  await page.evaluate(() => ((window as unknown as { witness: boolean }).witness = true))
  const release = await holdProjects(page)

  await page.getByRole('button', { name: 'Réessayer' }).click()

  await expect(cells(page)).toHaveCount(3)
  await expect(page.getByRole('status')).toHaveCount(0)
  await release(serving(PROJECT_SETS.threeWithShowcase))
  await expect(page.getByRole('main')).not.toHaveAttribute('aria-busy')
  // La table, vide jusqu'aux cartes de #20 : ni cadre, ni message.
  await expect(cells(page)).toHaveCount(0)
  await expect(page.getByRole('status')).toHaveCount(0)
  expect(requests).toBe(2)
  expect(await page.evaluate(() => (window as unknown as { witness?: boolean }).witness)).toBe(true)
})

test('« Réessayer » relance aussi au clavier, et reprend le focus si la relance échoue', async ({
  page,
}) => {
  let requests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/projets')) requests += 1
  })
  await openAnswered(page, FAILURES['statut 500'])
  // Le premier échec ne suit aucune action du visiteur : rien ne prend le focus.
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true)
  const release = await holdProjects(page)

  await page.getByRole('button', { name: 'Réessayer' }).focus()
  await page.keyboard.press('Enter')

  await expect(cells(page)).toHaveCount(3)
  expect(requests).toBe(2)
  await release(FAILURES['statut 500'])
  // Le bouton activé a disparu avec le message : celui qui revient reprend le focus.
  await expect(page.getByRole('button', { name: 'Réessayer' })).toBeFocused()
})

test('vide : ni cadre, ni message (spec §5.3)', async ({ page }) => {
  await openAnswered(page, serving(PROJECT_SETS.none))

  await expect(cells(page)).toHaveCount(0)
  await expect(page.getByRole('status')).toHaveCount(0)
  await expect(page.getByRole('main')).toHaveText('')
})

for (const [state, answer] of [
  ['erreur', FAILURES['statut 500']],
  ['vide', serving([])],
] as const) {
  test(`${state} : sans cellule, liens de l'auteur en colonne dès 600 px, en pied de page en dessous`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, 'largeurs de bureau : le projet desktop les porte')
    await page.setViewportSize({ width: 600, height: 800 })
    await openAnswered(page, answer)

    await expectPlacement(page, 'column')
    await page.setViewportSize({ width: 599, height: 800 })
    await expectPlacement(page, 'footer')
  })
}

/** Ouvre chaque état ; le chargement reste tenu jusqu'à la fin du scénario. */
const STATES: Record<string, (page: Page) => Promise<unknown>> = {
  chargement: openLoading,
  erreur: (page) => openAnswered(page, FAILURES['statut 500']),
  vide: (page) => openAnswered(page, serving([])),
}

for (const [state, open] of Object.entries(STATES)) {
  for (const colorScheme of ['light', 'dark'] as const) {
    test(`${state} : aucune violation d'accessibilité — ${colorScheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme })
      await open(page)

      const { violations } = await new AxeBuilder({ page }).analyze()

      expect(violations.map((violation) => violation.id)).toEqual([])
    })
  }
}
