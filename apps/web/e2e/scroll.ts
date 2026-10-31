/**
 * Défilement de la page servie, partagé par les scénarios.
 *
 * La table servie vide (le `test` d'`api.ts`) ne fait pas défiler la page : le scénario l'allonge
 * lui-même, et rien n'entre dans l'application pour cela (brief de #18, décision 12).
 */
import { expect, type Page } from '@playwright/test'

/** Allonge la page de quatre hauteurs de fenêtre, sous la table. */
export async function lengthenPage(page: Page) {
  await page.evaluate(() => {
    const filler = document.createElement('div')
    filler.style.height = '400vh'
    document.querySelector('main')?.append(filler)
  })
}

/**
 * Défile jusqu'à chaque position, une à une : l'entête lit le défilement une fois par image, et
 * deux positions dans la même image n'en feraient qu'une.
 */
export async function scrollThrough(page: Page, ...positions: number[]) {
  for (const y of positions) {
    await page.evaluate(
      (top) =>
        new Promise<void>((resolve) => {
          window.scrollTo(0, top)
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
        }),
      y,
    )
  }
}

/**
 * Décolle l'entête — page allongée, défilée de 1 px — et attend que son fond et son filet soient
 * posés (150 ms, spec §2.7) : ce qu'on mesure ensuite les trouve arrivés.
 */
export async function detachHeader(page: Page) {
  await lengthenPage(page)
  await scrollThrough(page, 1)
  await expect(page.getByRole('banner')).toHaveAttribute('data-detached')
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)))
}
