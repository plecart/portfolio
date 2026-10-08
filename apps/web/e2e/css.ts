/**
 * Lecture de valeurs CSS calculées, partagée par les scénarios.
 *
 * Une valeur se compare **résolue** : Chrome sérialise à sa manière ce qu'il calcule — une couleur
 * `color-mix()`, une ombre, une durée —, et seule la valeur calculée des deux côtés se compare.
 */
import type { Page } from '@playwright/test'

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
