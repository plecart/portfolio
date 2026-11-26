/**
 * Le verrou de défilement de la fiche sous une barre classique (spec §3.2) : Chromium sans écran
 * masque ses barres, et la table n'y a aucune barre à perdre. Ce fichier les rend visibles, comme
 * `author-links-scrollbar.spec.ts`. Une page sans barre, elle, ne doit pas en gagner la place.
 */
import type { Page } from '@playwright/test'
import { projectPath } from '../src/project/project.ts'
import { expect, FAILURES, holdProjects, serving, test } from './api.ts'
import { settle } from './css.ts'
import { expectClosed, expectPanelBox, openFromTable, openProject, panel } from './project.ts'
import { PROJECT_SETS, type Project } from './projects.ts'
import { cards, COLUMN_VIEWPORT, openTable } from './table.ts'

test.use({ launchOptions: { ignoreDefaultArgs: ['--hide-scrollbars'] } })

test.skip(({ isMobile }) => isMobile, 'barre classique : le projet desktop la porte')

/** Une table haute, qui fait défiler la page sous sa barre, et une qui tient dans la fenêtre. */
const PAGES = [
  ['la page défile', PROJECT_SETS.twelveWithShowcase, true],
  ['la page ne défile pas', PROJECT_SETS.threeWithoutShowcase, false],
] as const

/** Le bord gauche de la première carte, sous la fiche comme sans elle. */
const firstCardLeft = async (page: Page) => (await page.locator('.card').first().boundingBox())!.x

for (const [name, projects, hasBar] of PAGES) {
  test(`${name} : ni la table ni le panneau ne bougent à l’ouverture`, async ({ page }) => {
    await page.setViewportSize(COLUMN_VIEWPORT)
    await openTable(page, projects)
    const card = cards(page).first()
    const left = (await card.boundingBox())!.x
    const width = await page.evaluate(() => document.documentElement.clientWidth)
    expect(width < COLUMN_VIEWPORT.width).toBe(hasBar)

    await openProject(card)

    expect(await firstCardLeft(page)).toBe(left)
    await expectPanelBox(page)
  })
}

/**
 * Ouvre l'adresse de la fiche du premier projet, la liste tenue en attente.
 *
 * @returns Le geste qui relâche la liste.
 */
async function openAddress(page: Page, projects: Project[]) {
  const release = await holdProjects(page)
  await page.goto(projectPath(projects[0].slug))
  return release
}

/**
 * Les chemins par lesquels la fiche vient sur la table (spec §3.2, §5.1) : la place de la barre se
 * mesure sur la page que la fiche recouvre, la liste arrivée, jamais sur la page vide de l'attente.
 */
const ARRIVALS: [string, (page: Page, projects: Project[]) => Promise<void>][] = [
  ['depuis une carte', openFromTable],
  [
    'à son adresse, la liste en route',
    async (page, projects) => (await openAddress(page, projects))(serving(projects)),
  ],
  [
    'à son adresse, après un échec et « Réessayer »',
    async (page, projects) => {
      const failure = await openAddress(page, projects)
      await failure(FAILURES['réseau injoignable'])
      const retry = await holdProjects(page)
      await page.getByRole('button', { name: 'Réessayer' }).click()
      await retry(serving(projects))
    },
  ],
]

for (const [arrival, arrive] of ARRIVALS) {
  for (const [name, projects] of PAGES) {
    test(`ouverte ${arrival}, ${name} : la table ne bouge pas à la fermeture`, async ({ page }) => {
      await page.setViewportSize(COLUMN_VIEWPORT)
      await arrive(page, projects)
      await expect(panel(page)).toBeVisible()
      await settle(page)
      const left = await firstCardLeft(page)

      await page.keyboard.press('Escape')
      await expectClosed(page)
      await settle(page)

      expect(await firstCardLeft(page)).toBe(left)
    })
  }
}

test('sous 600 px, le plein écran ne garde aucune gouttière à la barre', async ({ page }) => {
  const viewport = { width: 500, height: 800 }
  await page.setViewportSize(viewport)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  expect(await page.evaluate(() => document.documentElement.clientWidth)).toBeLessThan(viewport.width)

  await openProject(cards(page).first())

  await expectPanelBox(page)
})
