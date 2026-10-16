/**
 * Le bouton de mode sur la page servie (spec §1.5, §3.3 ; brief de #18, décision 2) : le site suit
 * le système ; un clic force l'autre mode et le mémorise ; le clic qui ramène au mode du système
 * lui rend la main ; par l'un ou l'autre chemin, la palette bascule sans rien faire glisser
 * (décision 10). La restauration au chargement, avant le premier rendu, est prouvée par
 * `tokens.spec.ts`.
 */
import type { Page } from '@playwright/test'
import { expect, test } from './api.ts'
import { resolveAll } from './css.ts'
import { detachHeader } from './scroll.ts'

type Mode = 'light' | 'dark'

const TO_DARK = 'Passer en mode sombre'
const TO_LIGHT = 'Passer en mode clair'

/** Le bouton de mode, sous l'un ou l'autre de ses libellés. */
const toggle = (page: Page) => page.getByRole('banner').getByRole('button')

/** Le mode forcé sur `<html>` et la valeur mémorisée sous `theme` : `null` quand absents. */
async function forcedAndStored(page: Page) {
  return page.evaluate(() => [
    document.documentElement.getAttribute('data-theme'),
    localStorage.getItem('theme'),
  ])
}

/** Le fond de page attendu dans un mode : `--bg` de la spec §2.1. */
async function background(page: Page, mode: Mode) {
  const [value] = await resolveAll(page, [
    ['background-color', mode === 'dark' ? '#1C1A17' : '#F3EDE4'],
  ])
  return value
}

for (const system of ['light', 'dark'] as const) {
  test(`le bouton suit le mode du système — ${system}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: system })
    await page.goto('/')

    await expect(toggle(page)).toHaveAccessibleName(system === 'dark' ? TO_LIGHT : TO_DARK)
    // Une seule icône rendue : le soleil en mode clair — seul des deux à porter un disque —, la
    // lune en mode sombre ; l'inactive est absente du rendu (spec §3.3, §6.2).
    await expect(toggle(page).locator('svg')).toHaveCount(1)
    await expect(toggle(page).locator('svg circle')).toHaveCount(system === 'light' ? 1 : 0)
    expect(await forcedAndStored(page)).toEqual([null, null])
  })
}

test('un clic force l’autre mode, mémorisé et retrouvé après rechargement', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/')

  await toggle(page).click()

  await expect(toggle(page)).toHaveAccessibleName(TO_LIGHT)
  expect(await forcedAndStored(page)).toEqual(['dark', 'dark'])
  await expect(page.locator('html')).toHaveCSS('background-color', await background(page, 'dark'))

  await page.reload()

  await expect(toggle(page)).toHaveAccessibleName(TO_LIGHT)
  expect(await forcedAndStored(page)).toEqual(['dark', 'dark'])
})

test('le clic qui ramène au mode du système lui rend la main', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/')
  await toggle(page).click()

  await toggle(page).click()

  await expect(toggle(page)).toHaveAccessibleName(TO_DARK)
  expect(await forcedAndStored(page)).toEqual([null, null])

  // Plus rien de forcé : un changement du système est suivi, sans rechargement.
  await page.emulateMedia({ colorScheme: 'dark' })

  await expect(toggle(page)).toHaveAccessibleName(TO_LIGHT)
  await expect(page.locator('html')).toHaveCSS('background-color', await background(page, 'dark'))
})

test('une valeur mémorisée devenue celle du système reste jusqu’au prochain clic', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.addInitScript(() => localStorage.setItem('theme', 'dark'))
  await page.goto('/')

  expect(await forcedAndStored(page)).toEqual(['dark', 'dark'])

  await toggle(page).click()

  // Le clic vise l'autre mode que celui affiché, contraire au système : il est forcé.
  await expect(toggle(page)).toHaveAccessibleName(TO_DARK)
  expect(await forcedAndStored(page)).toEqual(['light', 'light'])
})

/**
 * Les deux chemins qui passent du clair au sombre, chacun rendant les propriétés des transitions
 * CSS lancées par le changement, lues dans la tâche même où l'application l'a appliqué : celle du
 * clic, ou celle de l'événement du système, juste après l'écouteur de l'application (posé au
 * montage, il passe avant). Lues à l'image suivante, elles laisseraient passer un calcul de style
 * — c'est la lecture qui le forcerait — entre le changement du système et son événement, qui
 * arrive parfois une image plus tard.
 */
const SWITCHES_TO_DARK: Record<string, (page: Page) => Promise<string[]>> = {
  'le clic du bouton': (page) =>
    page.evaluate(() => {
      document.querySelector('header button')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      return document.getAnimations().map((a) => (a as CSSTransition).transitionProperty)
    }),
  'le système': async (page) => {
    // Dans un objet : une promesse rendue seule serait attendue ici, avant le changement.
    const pending = await page.evaluateHandle(() => ({
      transitions: new Promise<string[]>((resolve) =>
        matchMedia('(prefers-color-scheme: dark)').addEventListener(
          'change',
          () => resolve(document.getAnimations().map((a) => (a as CSSTransition).transitionProperty)),
          { once: true },
        ),
      ),
    }))
    await page.emulateMedia({ colorScheme: 'dark' })
    return pending.evaluate(({ transitions }) => transitions)
  },
}

for (const [path, switchToDark] of Object.entries(SWITCHES_TO_DARK)) {
  test(`changer de mode ne fait rien glisser — ${path}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'light' })
    await page.goto('/')
    // Entête décollée : son fond et son filet, qui glissent au décollement (spec §2.7), sont de la
    // mesure avec le nom et le bouton, qui glissent au survol.
    await detachHeader(page)

    const transitions = await switchToDark(page)

    await expect(toggle(page)).toHaveAccessibleName(TO_LIGHT)
    // Les transitions sont rendues aussitôt : sans quoi plus rien ne glisserait, survol compris.
    expect([
      transitions,
      await page.evaluate(() => 'switching' in document.documentElement.dataset),
    ]).toEqual([[], false])
  })
}

test('un stockage qui lève une exception n’empêche pas de changer de mode', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.emulateMedia({ colorScheme: 'light' })
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      get() {
        throw new DOMException('Stockage refusé', 'SecurityError')
      },
    })
  })
  await page.goto('/')

  await toggle(page).click()

  await expect(toggle(page)).toHaveAccessibleName(TO_LIGHT)
  expect([errors, await page.evaluate(() => document.documentElement.dataset.theme)]).toEqual([
    [],
    'dark',
  ])
})
