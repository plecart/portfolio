/**
 * L'entête sur la page servie (spec §1.12, §3.3) : sa boîte aux deux largeurs, son fond au
 * défilement, sa sortie et son retour, le focus qui la ramène, et le mouvement réduit (§6.3).
 *
 * La page est allongée par le scénario (`scroll.ts`). Les seuils exacts du défilement sont prouvés
 * en Vitest (`tests/header-scroll.test.ts`) ; ici, leur effet à l'écran.
 */
import { expect, test } from '@playwright/test'
import { resolveAll } from './css.ts'
import { lengthenPage, scrollThrough } from './scroll.ts'

test("l'entête est une ligne fixe de 56 px, et son nom le titre de la page", async ({ page }) => {
  await page.goto('/')
  const header = page.getByRole('banner')
  const name = page.getByRole('heading', { level: 1 })

  await expect(name).toHaveCount(1)
  await expect(name).toHaveText('Pacôme Bernier')
  await expect(name.getByRole('link')).toHaveAttribute('href', '/')
  expect(
    await header.evaluate((element) => {
      const style = getComputedStyle(element)
      return [style.position, style.top, style.height, style.zIndex]
    }),
  ).toEqual(['fixed', '0px', '56px', '40'])
  expect(
    await name.evaluate((element) => {
      const style = getComputedStyle(element)
      return [style.fontSize, style.fontWeight, style.letterSpacing]
    }),
  ).toEqual(['15px', '600', '0.15px'])
  // Le corps de page commence sous l'entête.
  await expect(page.getByRole('main')).toHaveCSS('padding-top', '56px')
})

test("la marge intérieure de l'entête passe de 16 à 24 px à 600 px de large", async ({ page }) => {
  await page.goto('/')
  const header = page.getByRole('banner')

  await page.setViewportSize({ width: 599, height: 800 })
  await expect(header).toHaveCSS('padding', '0px 16px')

  await page.setViewportSize({ width: 600, height: 800 })
  await expect(header).toHaveCSS('padding', '0px 24px')
})

test("l'entête prend son fond et son filet dès 1 px de défilement", async ({ page }) => {
  await page.goto('/')
  await lengthenPage(page)
  const header = page.getByRole('banner')
  const [paper94, rule] = await resolveAll(page, [
    ['background-color', 'color-mix(in srgb, var(--paper) 94%, transparent)'],
    ['box-shadow', '0 1px 0 var(--line)'],
  ])

  await expect(header).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await expect(header).toHaveCSS('box-shadow', 'none')

  await scrollThrough(page, 1)

  await expect(header).toHaveCSS('background-color', paper94)
  await expect(header).toHaveCSS('box-shadow', rule)
})

test("l'entête sort après 8 px vers le bas au-delà de 56 px, et revient après 8 px vers le haut", async ({
  page,
}) => {
  await page.goto('/')
  await lengthenPage(page)
  const header = page.getByRole('banner')

  // Sortie et retour en 240 ms ; fond, filet et fondu en 150 ms (spec §2.7).
  await expect(header).toHaveCSS(
    'transition-property',
    'translate, opacity, background-color, box-shadow',
  )
  await expect(header).toHaveCSS('transition-duration', '0.24s, 0.15s, 0.15s, 0.15s')

  await scrollThrough(page, 56, 64)
  await expect(header).toBeInViewport()

  await scrollThrough(page, 65)
  await expect(header).not.toBeInViewport()

  await scrollThrough(page, 300, 292)
  await expect(header).not.toBeInViewport()

  await scrollThrough(page, 291)
  await expect(header).toBeInViewport()
})

test("l'entête sortie revient dès qu'elle reçoit le focus", async ({ page }) => {
  await page.goto('/')
  await lengthenPage(page)
  const header = page.getByRole('banner')
  await scrollThrough(page, 300)
  await expect(header).not.toBeInViewport()

  await page.keyboard.press('Tab')

  await expect(header.getByRole('link', { name: 'Pacôme Bernier' })).toBeFocused()
  await expect(header).toBeInViewport()
})

test("en mouvement réduit, l'entête sort et revient par un fondu, sans translation", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await lengthenPage(page)
  const header = page.getByRole('banner')

  await scrollThrough(page, 300)

  await expect(header).toHaveCSS('opacity', '0')
  await expect(header).toHaveCSS('pointer-events', 'none')
  await expect(header).toHaveCSS('translate', 'none')

  await scrollThrough(page, 291)

  await expect(header).toHaveCSS('opacity', '1')
})
