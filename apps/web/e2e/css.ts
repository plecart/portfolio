/**
 * Lecture de valeurs CSS calculées et attente des transitions, partagées par les scénarios.
 *
 * Une valeur se compare **résolue** : Chrome sérialise à sa manière ce qu'il calcule — une couleur
 * `color-mix()`, une ombre, une durée —, et seule la valeur calculée des deux côtés se compare.
 */
import type { Locator, Page } from '@playwright/test'

/** La rotation d'un élément, en degrés, au dixième, lue sur sa transformation calculée. */
export const rotationOf = (element: Locator) =>
  element.evaluate((node) => {
    const { a, b } = new DOMMatrix(getComputedStyle(node).transform)
    return Math.round((Math.atan2(b, a) * 1800) / Math.PI) / 10
  })

/**
 * Valeurs calculées de déclarations appliquées une à une à un élément sonde du document.
 *
 * @param page Page ouverte : la sonde hérite des propriétés personnalisées de `:root`.
 * @param declarations Paires `[propriété, valeur]`, par exemple `['color', 'var(--bg)']`.
 * @returns La valeur calculée de chaque propriété, dans l'ordre reçu ; une valeur invalide ou un
 *   jeton absent rend la valeur initiale de la propriété, qui ne correspond à aucune attente.
 */
export async function resolveAll(page: Page, declarations: [string, string][]): Promise<string[]> {
  return page.evaluate((pairs) => {
    const probe = document.createElement('div')
    document.body.append(probe)
    const values = pairs.map(([property, value]) => {
      probe.style.setProperty(property, value)
      const resolved = getComputedStyle(probe).getPropertyValue(property)
      probe.style.removeProperty(property)
      return resolved
    })
    probe.remove()
    return values
  }, declarations)
}

/**
 * Attend la fin des transitions en cours : ce qu'on lit ensuite les trouve arrivées. Une transition
 * remplacée en route rejette sa promesse `finished` : c'est une fin comme une autre.
 */
export async function settle(page: Page) {
  await page.evaluate(() => Promise.allSettled(document.getAnimations().map((a) => a.finished)))
}
