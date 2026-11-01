/**
 * Le verrou de défilement de la fiche sous une barre classique (spec §3.2) : Chromium sans écran
 * masque ses barres, et la table n'y a aucune barre à perdre. Ce fichier les rend visibles, comme
 * `author-links-scrollbar.spec.ts`. Une page sans barre, elle, ne doit pas en gagner la place.
 */
import { expect, test } from './api.ts'
import { openProject, panel } from './project.ts'
import { PROJECT_SETS } from './projects.ts'
import { cards, COLUMN_VIEWPORT, openTable } from './table.ts'

test.use({ launchOptions: { ignoreDefaultArgs: ['--hide-scrollbars'] } })

test.skip(({ isMobile }) => isMobile, 'barre classique : le projet desktop la porte')

for (const [name, projects, hasBar] of [
  ['la page défile', PROJECT_SETS.twelveWithShowcase, true],
  ['la page ne défile pas', PROJECT_SETS.threeWithoutShowcase, false],
] as const) {
  test(`${name} : ni la table ni le panneau ne bougent à l’ouverture`, async ({ page }) => {
    await page.setViewportSize(COLUMN_VIEWPORT)
    await openTable(page, projects)
    const card = cards(page).first()
    const left = (await card.boundingBox())!.x
    const width = await page.evaluate(() => document.documentElement.clientWidth)
    expect(width < COLUMN_VIEWPORT.width).toBe(hasBar)

    await openProject(card)

    expect((await page.locator('.card').first().boundingBox())!.x).toBe(left)
    expect(await panel(page).boundingBox()).toMatchObject({ x: 24, y: 75, width: 1232, height: 650 })
  })
}
