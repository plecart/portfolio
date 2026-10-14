/**
 * Les liens de l'auteur sur la page servie (spec §1.13, §3.4, §6.2, §6.3) : leurs libellés et leurs
 * adresses, leurs deux formes, l'ordre de tabulation, l'anneau de focus et les cibles. La mesure qui
 * choisit entre les deux formes : `author-links-measure.spec.ts`.
 */
import { expect, test } from '@playwright/test'
import { resolveAll } from './css.ts'
import { COLUMN_VIEWPORT, expectPlacement } from './table.ts'

/** Une largeur de mobile : les liens y sont toujours en pied de page (spec §6.1). */
const FOOTER_VIEWPORT = { width: 400, height: 800 }


test("les liens de l'auteur : GitHub puis LinkedIn, nommés, ouverts dans le même onglet", async ({
  page,
}) => {
  await page.goto('/')
  const links = page.getByRole('contentinfo').getByRole('link')

  await expect(links).toHaveCount(2)
  await expect(links.nth(0)).toHaveAccessibleName('GitHub de Pacôme Bernier')
  await expect(links.nth(0)).toHaveAttribute('href', 'https://github.com/plecart')
  await expect(links.nth(1)).toHaveAccessibleName('LinkedIn de Pacôme Bernier')
  await expect(links.nth(1)).toHaveAttribute('href', 'https://www.linkedin.com/in/pacomebernier98/')
  // Même onglet (brief de #18, décision 10 ; WCAG, technique G200).
  for (const link of await links.all()) await expect(link).not.toHaveAttribute('target')
})

test('en pied de page, les liens font une rangée centrée sous la table (spec §3.4)', async ({
  page,
}) => {
  await page.setViewportSize(FOOTER_VIEWPORT)
  await page.goto('/')
  const footer = page.getByRole('contentinfo')
  const links = footer.getByRole('link')
  const [line, ink2] = await resolveAll(page, [
    ['background-color', 'var(--line)'],
    ['color', 'var(--ink-2)'],
  ])

  await expectPlacement(page, 'footer')
  await expect(footer).toHaveCSS('padding', '48px 0px 32px')
  // Le filet de 48 × 1 px, centré au-dessus des icônes, en haut de la marge intérieure.
  expect(
    await footer.evaluate((element) => {
      const rule = getComputedStyle(element, '::before')
      return [rule.position, rule.top, rule.left, rule.width, rule.height, rule.backgroundColor]
    }),
  ).toEqual(['absolute', '0px', `${(FOOTER_VIEWPORT.width - 48) / 2}px`, '48px', '1px', line])

  const [main, row, first, second] = await Promise.all([
    page.getByRole('main').boundingBox(),
    footer.boundingBox(),
    links.nth(0).boundingBox(),
    links.nth(1).boundingBox(),
  ])
  // Après la table, dans le flux ; la rangée centrée dans la fenêtre.
  expect(row!.y).toBeGreaterThanOrEqual(main!.y + main!.height)
  expect((first!.x + second!.x + second!.width) / 2).toBe(FOOTER_VIEWPORT.width / 2)
  // Zones de 38 px (icône 22 et marge 8), 24 px d'écart — au moins 8 entre deux cibles (§6.2).
  expect([first!.width, first!.height, second!.width, second!.height]).toEqual([38, 38, 38, 38])
  expect(second!.x - (first!.x + first!.width)).toBe(24)

  for (const link of await links.all()) {
    // Sans disque : ni fond ni ombre ; l'icône au repos en `--ink-2`.
    await expect(link).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
    await expect(link).toHaveCSS('box-shadow', 'none')
    await expect(link).toHaveCSS('color', ink2)
    const icon = await link.locator('svg').boundingBox()
    expect([icon?.width, icon?.height]).toEqual([22, 22])
  }
})

test('en colonne, les liens sont deux disques fixes en bas à droite (spec §3.4)', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'largeur de bureau : le projet desktop la porte')
  await page.setViewportSize(COLUMN_VIEWPORT)
  await page.goto('/')
  const footer = page.getByRole('contentinfo')
  const links = footer.getByRole('link')
  const [paper, shadowRest, ink2] = await resolveAll(page, [
    ['background-color', 'var(--paper)'],
    ['box-shadow', 'var(--shadow-rest)'],
    ['color', 'var(--ink-2)'],
  ])

  await expectPlacement(page, 'column')
  await expect(footer).toHaveCSS('z-index', '40')
  // Sans filet.
  expect(await footer.evaluate((element) => getComputedStyle(element, '::before').display)).toBe(
    'none',
  )

  const [column, first, second] = await Promise.all([
    footer.boundingBox(),
    links.nth(0).boundingBox(),
    links.nth(1).boundingBox(),
  ])
  // 36 px de large, 80 de haut pour deux disques, à 24 px des bords de la fenêtre.
  expect([column?.x, column?.y, column?.width, column?.height]).toEqual([
    COLUMN_VIEWPORT.width - 24 - 36,
    COLUMN_VIEWPORT.height - 24 - 80,
    36,
    80,
  ])
  // Disques de 36 px, 8 px d'écart — au moins 8 entre deux cibles (§6.2).
  expect([first!.width, first!.height, second!.width, second!.height]).toEqual([36, 36, 36, 36])
  expect(second!.y - (first!.y + first!.height)).toBe(8)

  for (const link of await links.all()) {
    await expect(link).toHaveCSS('background-color', paper)
    await expect(link).toHaveCSS('box-shadow', shadowRest)
    await expect(link).toHaveCSS('color', ink2)
    const icon = await link.locator('svg').boundingBox()
    expect([icon?.width, icon?.height]).toEqual([22, 22])
  }
})

/*
 * Survol, sous les deux formes : l'encre en 150 ms, la montée de 2 px en 240 ms (spec §2.7, §3.4) ;
 * en mouvement réduit, la couleur seule (§6.3).
 */
for (const [form, viewport] of [
  ['pied de page', FOOTER_VIEWPORT],
  ['colonne', COLUMN_VIEWPORT],
] as const) {
  for (const reducedMotion of ['no-preference', 'reduce'] as const) {
    test(`au survol, une icône prend l'encre — ${form}, mouvement ${reducedMotion}`, async ({
      page,
      isMobile,
    }) => {
      test.skip(isMobile, 'un écran tactile ne survole pas : `hover:` exige `(hover: hover)`')
      await page.emulateMedia({ reducedMotion })
      await page.setViewportSize(viewport)
      await page.goto('/')
      const link = page.getByRole('link', { name: 'GitHub de Pacôme Bernier' })
      const [ink] = await resolveAll(page, [['color', 'var(--ink)']])

      await expect(link).toHaveCSS('transition-property', 'color, translate')
      await expect(link).toHaveCSS('transition-duration', '0.15s, 0.24s')

      await link.hover()

      await expect(link).toHaveCSS('color', ink)
      await expect(link).toHaveCSS('translate', reducedMotion === 'reduce' ? 'none' : '0px -2px')
    })
  }
}

test('Tab parcourt le nom, le bouton de mode, puis GitHub et LinkedIn (spec §6.2)', async ({
  page,
}) => {
  await page.goto('/')
  const [ring] = await resolveAll(page, [['outline', '2px solid var(--accent)']])
  const order = [
    page.getByRole('link', { name: 'Pacôme Bernier', exact: true }),
    page.getByRole('banner').getByRole('button'),
    page.getByRole('link', { name: 'GitHub de Pacôme Bernier' }),
    page.getByRole('link', { name: 'LinkedIn de Pacôme Bernier' }),
  ]

  for (const [index, target] of order.entries()) {
    await page.keyboard.press('Tab')
    await expect(target).toBeFocused()
    // L'anneau de focus des liens de l'auteur : 2 px `--accent` à 3 px (spec §6.2).
    if (index >= 2) {
      expect(
        await target.evaluate((element) => {
          const style = getComputedStyle(element)
          return [style.outline, style.outlineOffset]
        }),
      ).toEqual([ring, '3px'])
    }
  }
})
