/**
 * La marge des liens de l'auteur sous une barre de défilement classique : elle se compte hors barre
 * (choix du mainteneur à l'arrêt visuel du lot 3 de #18, le 2026-10-14), donc la forme ne dépend ni
 * de la barre ni du chemin qui y mène.
 *
 * Chromium sans écran masque ses barres — Playwright lui passe `--hide-scrollbars` —, et sous lui
 * `clientWidth` vaut `innerWidth` : aucun autre scénario ne voit cette voie. Ce fichier les rend
 * visibles ; mesuré le 2026-10-14 sur le poste : barre fine de 10 px, `clientWidth` 1190 à 1200 px.
 */
import { expect, test, type Page } from '@playwright/test'
import { lengthenPage } from './scroll.ts'
import { expectPlacement, placeCells } from './table.ts'

test.use({ launchOptions: { ignoreDefaultArgs: ['--hide-scrollbars'] } })

test.skip(({ isMobile }) => isMobile, 'largeurs de bureau : le projet desktop les porte')

/** La largeur de la barre de défilement verticale, en px : le témoin que la voie est ouverte. */
const scrollbarWidth = (page: Page) =>
  page.evaluate(() => window.innerWidth - document.documentElement.clientWidth)

test('à 1200 px, la grille de 1044 px laisse la colonne, barre comprise (repère de spec §3.4)', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1200, height: 800 })
  await page.goto('/')
  await placeCells(page, [1044])
  await lengthenPage(page)

  expect(await scrollbarWidth(page)).toBeGreaterThan(0)
  await expectPlacement(page, 'column')
})

test('à 600 px, barre comprise, la table sans cellule laisse la colonne : le seuil se lit comme `sm:`', async ({
  page,
}) => {
  // Une requête média lit la largeur de la fenêtre, barre comprise : `innerWidth`, pas les 590 px
  // visibles.
  await page.setViewportSize({ width: 600, height: 800 })
  await page.goto('/')
  await lengthenPage(page)

  expect(await scrollbarWidth(page)).toBeGreaterThan(0)
  await expectPlacement(page, 'column')
})

test("le pied de page, qui fait naître la barre, ne s'y verrouille pas", async ({ page }) => {
  // Une cellule de 840 × 700 px à 1000 px de haut de 800 : 80 px de marge sans barre. Le pied de
  // page dans le flux porte la page à 874 px et fait naître la barre ; la colonne la ramène à 756.
  await page.setViewportSize({ width: 599, height: 800 })
  await page.goto('/')
  await placeCells(page, [840], 700)
  await expectPlacement(page, 'footer')
  expect(await scrollbarWidth(page)).toBeGreaterThan(0)

  await page.setViewportSize({ width: 1000, height: 800 })

  await expectPlacement(page, 'column')
})
