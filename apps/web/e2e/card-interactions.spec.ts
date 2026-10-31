/**
 * Les interactions d'une carte (spec §1.3, §1.7, §2.7, §3.1, §4.1, §6.1-6.3 ; issue #168), sur la
 * page servie, l'API et les fichiers interceptés par les gestes d'`api.ts`.
 */
import type { Locator } from '@playwright/test'
import { expect, holdProjects, serving, test } from './api.ts'
import { resolveAll } from './css.ts'
import { PROJECT_SETS } from './projects.ts'
import { scrollThrough } from './scroll.ts'
import {
  cards,
  COLUMN_VIEWPORT,
  enterCards,
  expectPlacement,
  openTable,
  settle,
} from './table.ts'

/** La couche d'entrée d'une carte. */
const entry = (card: Locator) => card.locator('.card-entry')

test('à 15 % de sa surface dans l’écran, une carte entre : 8 px de montée et un fondu de 240 ms', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  const box = (await card.boundingBox())!
  const { height } = page.viewportSize()!
  const [duration, curve] = await resolveAll(page, [
    ['transition-duration', 'var(--dur)'],
    ['transition-timing-function', 'var(--ease-out)'],
  ])

  await expect(entry(card)).toHaveCSS('opacity', '0')
  await expect(entry(card)).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 8)')
  await expect(entry(card)).toHaveCSS('transition-property', 'opacity, transform')
  await expect(entry(card)).toHaveCSS('transition-duration', `${duration}, ${duration}`)
  await expect(entry(card)).toHaveCSS('transition-timing-function', `${curve}, ${curve}`)

  await scrollThrough(page, box.y + box.height * 0.1 - height)
  await expect(card).not.toHaveAttribute('data-entered')

  await scrollThrough(page, box.y + box.height * 0.2 - height)
  await expect(entry(card)).toHaveCSS('opacity', '1')
  await expect(entry(card)).toHaveCSS('transform', 'none')
})

test('une carte n’entre qu’une fois : la revoir ne rejoue rien', async ({ page }) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  await enterCards(page)
  const replays = await page.evaluateHandle(() => {
    const seen: string[] = []
    addEventListener('transitionrun', ({ target, propertyName }) => {
      if ((target as Element).matches('.card-entry')) seen.push(propertyName)
    })
    return seen
  })
  const bottom = await page.evaluate(() => document.documentElement.scrollHeight)

  await scrollThrough(page, bottom, 0, bottom)

  expect(await replays.jsonValue()).toEqual([])
})

test('toute la table n’a qu’un observateur, qui lâche chaque carte entrée', async ({ page }) => {
  await page.addInitScript(() => {
    const calls = { created: 0, unobserved: 0 }
    Object.assign(window, { observerCalls: calls })
    const Native = window.IntersectionObserver
    window.IntersectionObserver = class extends Native {
      constructor(...args: ConstructorParameters<typeof Native>) {
        super(...args)
        calls.created += 1
      }

      unobserve(target: Element) {
        calls.unobserved += 1
        super.unobserve(target)
      }
    }
  })
  await openTable(page, PROJECT_SETS.threeWithShowcase)
  await expect(page.locator('.card[data-entered]')).toHaveCount(3)

  const calls = await page.evaluate(() => Reflect.get(window, 'observerCalls'))

  expect(calls).toEqual({ created: 1, unobserved: 3 })
})

test('le retard vaut 40 ms par colonne mesurée, et se relit au redimensionnement', async ({ page }) => {
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const columns = () =>
    cards(page).evaluateAll((links) =>
      links.map((link) => {
        const { transitionDelay } = getComputedStyle(link.querySelector('.card-entry')!)
        return Math.round(parseFloat(transitionDelay) * 1000) / 40
      }),
    )

  expect(await columns()).toEqual([0, 2, 3, 2, 3, 0, 1, 2, 3, 0, 1, 2])

  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 1000 })
  await expect.poll(columns).toEqual([0, 2, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2])

  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 400 })
  await expect.poll(columns).toEqual([0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
})

test('en mouvement réduit, une carte entre par un fondu de 150 ms, sans montée, retard conservé', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  const [duration] = await resolveAll(page, [['transition-duration', 'var(--dur-fast)']])

  await expect(entry(card)).toHaveCSS('opacity', '0')
  await expect(entry(card)).toHaveCSS('transform', 'none')
  await expect(entry(card)).toHaveCSS('transition-property', 'opacity')
  await expect(entry(card)).toHaveCSS('transition-duration', duration)
  // La dernière des douze cartes, en troisième colonne à 1280 px.
  await expect(entry(card)).toHaveCSS('transition-delay', '0.08s')

  await card.scrollIntoViewIfNeeded()
  await expect(entry(card)).toHaveCSS('opacity', '1')
})

test('les cartes remplacent les cadres en entrant, sans changer la forme des liens de l’auteur', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'largeurs de bureau : le projet desktop les porte')
  // À 1200 px, 78 px de marge pour une garde de 76 : une mesure qui suivrait l'entrée basculerait.
  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 1200 })
  const release = await holdProjects(page)
  await page.goto('/')
  await expectPlacement(page, 'column')
  const watched = await page.evaluateHandle(() => {
    const seen = { forms: 0, moved: [] as string[] }
    new MutationObserver(() => (seen.forms += 1)).observe(document.querySelector('footer')!, {
      attributeFilter: ['data-docked'],
    })
    addEventListener('transitionrun', ({ target }) => seen.moved.push((target as Element).className))
    return seen
  })

  await release(serving(PROJECT_SETS.twelveWithShowcase))
  await expect(page.locator('.card[data-entered]')).not.toHaveCount(0)
  await settle(page)

  const { forms, moved } = await watched.jsonValue()
  expect(forms).toBe(0)
  await expectPlacement(page, 'column')
  // Rien ne bouge que la couche d'entrée : ni la cellule, que les liens mesurent, ni ses voisines.
  expect(moved.length).toBeGreaterThan(0)
  expect([...new Set(moved)]).toEqual(['card-entry'])
})
