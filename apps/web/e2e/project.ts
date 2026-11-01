/** La fiche et ses gestes, partagés par les scénarios. */
import type { Locator, Page } from '@playwright/test'
import { expect } from './api.ts'
import { settle } from './css.ts'

/** Le panneau de la fiche. */
export const panel = (page: Page) => page.getByRole('dialog')

/** Le bouton « Fermer la fiche ». */
export const closeButton = (page: Page) => page.getByRole('button', { name: 'Fermer la fiche' })

/** La colonne de lecture, arrêt de tabulation de ce qui défile. */
export const readingColumn = (page: Page) => page.getByRole('region', { name: 'Contenu de la fiche' })

/** Ouvre la fiche d'une carte par Entrée, qui ouvre d'emblée sur les deux projets. */
export async function openProject(card: Locator) {
  await card.press('Enter')
  await expect(panel(card.page())).toBeVisible()
  await settle(card.page())
}

/** Attend la fiche fermée, panneau retiré au bout de son fondu de sortie. */
export async function expectClosed(page: Page) {
  await expect(panel(page)).toHaveCount(0)
}

/**
 * Consigne les violations de CSP de la page, telles que Chromium les écrit en console.
 *
 * @returns Les messages, dans un tableau qui se remplit au fil du scénario.
 */
export function watchCspViolations(page: Page): string[] {
  const violations: string[] = []
  page.on('console', (message) => {
    if (message.text().includes('Content Security Policy')) violations.push(message.text())
  })
  return violations
}

/**
 * Consigne les animations CSS qui partent à partir de maintenant, sur toute la page.
 *
 * @returns De quoi lire celles parties : nom, durée et courbe.
 */
export async function watchAnimations(page: Page) {
  const runs = await page.evaluateHandle(() => {
    const seen: { name: string; duration: string; curve: string }[] = []
    addEventListener('animationstart', ({ target, animationName: name }) => {
      const { animationDuration: duration, animationTimingFunction: curve } = getComputedStyle(
        target as Element,
      )
      seen.push({ name, duration, curve })
    })
    return seen
  })
  return () => runs.jsonValue()
}

/**
 * Retient, sans les laisser agir, les clics que la page laisse au navigateur : un onglet ouvert
 * échapperait aux interceptions de la page. Un clic du bouton du milieu est un `auxclick`.
 *
 * @returns De quoi lire le nombre de clics que l'application n'a pas annulés.
 */
export async function holdNativeClicks(page: Page) {
  const clicks = await page.evaluateHandle(() => {
    const held = { count: 0 }
    for (const type of ['click', 'auxclick']) {
      addEventListener(type, (event) => {
        if (!event.defaultPrevented) held.count += 1
        event.preventDefault()
      })
    }
    return held
  })
  return async () => (await clicks.jsonValue()).count
}
