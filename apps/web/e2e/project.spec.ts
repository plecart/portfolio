/**
 * La fiche d'un projet (spec §1.10, §3.2, §5.4, §6.2 ; issue #170) : son dialogue, ses adresses et
 * ses fermetures, sur la page servie, l'API et les fichiers interceptés par les gestes d'`api.ts`.
 *
 * Tant que la fiche est ouverte, Radix cache la page aux technologies d'assistance : une carte ne s'y
 * trouve plus par son rôle, seulement avant l'ouverture ou après la fermeture.
 */
import { AxeBuilder } from '@axe-core/playwright'
import type { Locator, Page } from '@playwright/test'
import { countProjectRequests, expect, serveProjects, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  closeButton,
  expectClosed,
  holdNativeClicks,
  openProject,
  panel,
  watchAnimations,
  watchCspViolations,
} from './project.ts'
import { PROJECT_SETS } from './projects.ts'
import { cards, COLUMN_VIEWPORT, openTable, serveUnderCsp } from './table.ts'

/** Trois projets aux titres distincts. La première carte, celle du projet en cours : `projet-02`. */
const PROJECTS = PROJECT_SETS.threeWithoutShowcase
const FIRST = { title: 'Projet 02', path: '/projets/projet-02' }

/** Les trois fermetures (spec §3.2). */
const CLOSINGS: [string, (page: Page) => Promise<unknown>][] = [
  ['le bouton', (page) => closeButton(page).click()],
  ['Échap', (page) => page.keyboard.press('Escape')],
  ['le retour du navigateur', (page) => page.goBack()],
]

test('la fiche est un dialogue modal nommé par son titre, le focus sur « Fermer la fiche »', async ({
  page,
}) => {
  await openTable(page, PROJECTS)

  await openProject(cards(page).first())

  await expect(panel(page)).toHaveAccessibleName(FIRST.title)
  await expect(panel(page)).toHaveAttribute('aria-modal', 'true')
  await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(FIRST.title)
  await expect(closeButton(page)).toBeFocused()
})

test('Tab et Maj+Tab ne sortent pas du panneau', async ({ page }) => {
  await openTable(page, PROJECTS)
  await openProject(cards(page).first())

  for (const key of ['Tab', 'Shift+Tab']) {
    await page.keyboard.press(key)

    await expect(closeButton(page)).toBeFocused()
  }
})

for (const [name, close] of CLOSINGS) {
  test(`${name} ferme la fiche et rend le focus à la carte`, async ({ page }) => {
    await openTable(page, PROJECTS)
    const card = cards(page).last()
    await openProject(card)

    await close(page)

    await expectClosed(page)
    await expect(page).toHaveURL('/')
    await expect(card).toBeFocused()
  })
}

test('une seule requête vers la liste, ouverture et fermetures comprises', async ({ page }) => {
  const requests = countProjectRequests(page)
  await openTable(page, PROJECTS)

  for (const [, close] of CLOSINGS) {
    await openProject(cards(page).first())
    await close(page)
    await expectClosed(page)
  }

  expect(requests()).toBe(1)
})

test('sous la CSP de production, ouvrir, faire défiler et fermer ne viole rien', async ({ page }) => {
  const violations = watchCspViolations(page)
  await serveUnderCsp(page)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)

  await openProject(cards(page).first())
  await page.mouse.wheel(0, 300)
  await closeButton(page).click()
  await expectClosed(page)

  expect(violations).toEqual([])
})

test('un clic hors du panneau ne ferme pas la fiche', async ({ page, isMobile }) => {
  test.skip(isMobile, 'plein écran : le panneau n’a pas de dehors')
  await openTable(page, PROJECTS)
  await openProject(cards(page).first())

  await page.mouse.click(4, 4)
  await settle(page)

  await expect(panel(page)).toHaveAttribute('data-state', 'open')
  await expect(page).toHaveURL(FIRST.path)
})

test.describe('l’historique, à partir de `/`', () => {
  test('ouvrir puis retour ferme, puis suivant rouvre la même fiche', async ({ page }) => {
    await openTable(page, PROJECTS)
    await openProject(cards(page).first())

    await page.goBack()

    await expectClosed(page)
    await expect(page).toHaveURL('/')

    await page.goForward()

    await expect(panel(page)).toHaveAccessibleName(FIRST.title)
    await expect(page).toHaveURL(FIRST.path)
  })

  test('une fiche rouverte par suivant se ferme comme les autres', async ({ page }) => {
    await openTable(page, PROJECTS)
    await openProject(cards(page).first())
    await page.goBack()
    await expectClosed(page)
    await page.goForward()
    await expect(panel(page)).toBeVisible()

    await closeButton(page).click()

    await expectClosed(page)
    await expect(page).toHaveURL('/')
  })

  test('ouvrir ajoute une entrée, « Fermer la fiche » n’en laisse aucune de plus', async ({ page }) => {
    await openTable(page, PROJECTS)
    const entries = () => page.evaluate(() => history.length)
    const before = await entries()

    await openProject(cards(page).first())

    expect(await entries()).toBe(before + 1)

    await closeButton(page).click()

    await expectClosed(page)
    await expect(page).toHaveURL('/')
    expect(await entries()).toBe(before + 1)

    await page.goForward()

    await expect(panel(page)).toBeVisible()
  })
})

test('arrivée directe puis « Fermer la fiche » : on reste sur le site, à `/`', async ({ page }) => {
  await serveProjects(page, PROJECTS)
  await page.goto(FIRST.path)
  await expect(panel(page)).toBeVisible()

  await closeButton(page).click()

  await expectClosed(page)
  await expect(page).toHaveURL('/')
  await expect(cards(page).first()).toBeFocused()
})

/** Les clics qui restent ceux d'un lien. */
const NATIVE_CLICKS: [string, Parameters<Locator['click']>[0]][] = [
  ['Ctrl', { modifiers: ['Control'] }],
  ['⌘', { modifiers: ['Meta'] }],
  ['Maj', { modifiers: ['Shift'] }],
  ['Alt', { modifiers: ['Alt'] }],
  ['le bouton du milieu', { button: 'middle' }],
]

for (const [name, options] of NATIVE_CLICKS) {
  test(`${name} sur une carte garde le geste du navigateur : aucune fiche dans la page`, async ({
    page,
  }) => {
    await openTable(page, PROJECTS)
    const nativeClicks = await holdNativeClicks(page)

    await cards(page).first().click(options)

    expect(await nativeClicks()).toBe(1)
    await expect(panel(page)).toHaveCount(0)
    await expect(page).toHaveURL('/')
  })
}

test('le titre de l’onglet suit l’adresse (ADR 0011)', async ({ page }) => {
  await openTable(page, PROJECTS)
  await expect(page).toHaveTitle('Pacôme Bernier')

  await openProject(cards(page).first())
  await expect(page).toHaveTitle(FIRST.title)

  await closeButton(page).click()
  await expect(page).toHaveTitle('Pacôme Bernier')
})

test('un clic sans contact (`detail` à 0) ouvre d’emblée', async ({ page }) => {
  await openTable(page, PROJECTS)

  await cards(page).first().dispatchEvent('click', { detail: 0 })

  await expect(panel(page)).toBeVisible()
})

test('sur un appareil à survol, un clic ouvre la fiche d’emblée', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans survol : le premier toucher révèle')
  await openTable(page, PROJECTS)

  await cards(page).first().click()

  await expect(panel(page)).toBeVisible()
})

test('au toucher, le premier révèle, le second ouvre et finit la révélation', async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, 'un appareil sans survol : le projet mobile')
  await openTable(page, PROJECTS)
  const card = cards(page).first()
  const cell = page.locator(`.card[href="${FIRST.path}"]`)

  await card.tap()

  await expect(cell).toHaveAttribute('data-revealed')
  await expect(panel(page)).toHaveCount(0)

  await card.tap()

  await expect(panel(page)).toBeVisible()
  await expect(cell).not.toHaveAttribute('data-revealed')
})

test('les fondus : entrée 200 ms, sortie 150 ms, `--ease-out`, le panneau retiré à la fin', async ({
  page,
}) => {
  await openTable(page, PROJECTS)
  const [content, fast, curve] = await resolveAll(page, [
    ['animation-duration', 'var(--dur-content)'],
    ['animation-duration', 'var(--dur-fast)'],
    ['animation-timing-function', 'var(--ease-out)'],
  ])
  const animations = await watchAnimations(page)

  await openProject(cards(page).first())
  await closeButton(page).click()
  await expectClosed(page)

  expect(await animations()).toEqual([
    { name: 'project-in', duration: content, curve },
    { name: 'project-out', duration: fast, curve },
  ])
})

test('le panneau : papier, ombre soulevée, z-index 30, sans voile', async ({ page }) => {
  await openTable(page, PROJECTS)
  await openProject(cards(page).first())
  const [paper, lift] = await resolveAll(page, [
    ['background-color', 'var(--paper)'],
    ['box-shadow', 'var(--shadow-lift)'],
  ])

  await expect(panel(page)).toHaveCSS('background-color', paper)
  await expect(panel(page)).toHaveCSS('box-shadow', lift)
  await expect(panel(page)).toHaveCSS('z-index', '30')
  await expect(panel(page)).toHaveCSS('transform', 'none')
  await expect(page.locator('body > [data-state]')).toHaveCount(1)
})

test('« Fermer la fiche » : 36 px, en haut à droite, à 8 px des bords, papier, disque', async ({
  page,
}) => {
  await openTable(page, PROJECTS)
  await openProject(cards(page).first())
  const box = (await panel(page).boundingBox())!
  const [paper] = await resolveAll(page, [['background-color', 'var(--paper)']])

  const button = (await closeButton(page).boundingBox())!

  expect(button).toEqual({ x: box.x + box.width - 44, y: box.y + 8, width: 36, height: 36 })
  await expect(closeButton(page)).toHaveCSS('background-color', paper)
  const radius = await closeButton(page).evaluate(
    (element) => getComputedStyle(element).borderTopLeftRadius,
  )
  expect(parseFloat(radius)).toBeGreaterThanOrEqual(button.width / 2)
  expect(await closeButton(page).locator('svg').boundingBox()).toMatchObject({ width: 20, height: 20 })
})

test.describe('les dimensions de spec §3.2', () => {
  test.skip(({ isMobile }) => isMobile, 'largeurs de bureau : le projet desktop les porte')

  for (const [width, height, photo, panelWidth, panelHeight] of [
    [1280, 800, 594, 1232, 650],
    [1440, 900, 660, 1364, 716],
    [1024, 768, 466, 976, 522],
  ]) {
    test(`à ${width} × ${height}, le panneau mesure ${panelWidth} × ${panelHeight}, deux colonnes de ${photo} px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height })
      await openTable(page, PROJECTS)

      await openProject(cards(page).first())

      expect(await panel(page).boundingBox()).toEqual({
        x: (width - panelWidth) / 2,
        y: (height - panelHeight) / 2,
        width: panelWidth,
        height: panelHeight,
      })
      await expect(panel(page)).toHaveCSS('border-top-left-radius', '2px')
      await expect(panel(page)).toHaveCSS('padding-top', '10px')
      await expect(panel(page)).toHaveCSS('grid-template-columns', `${photo}px ${photo}px`)
      await expect(panel(page)).toHaveCSS('column-gap', '24px')
    })
  }

  test('le titre est dans la colonne de lecture, à 12 px du haut du panneau, marge comprise', async ({
    page,
  }) => {
    await page.setViewportSize(COLUMN_VIEWPORT)
    await openTable(page, PROJECTS)

    await openProject(cards(page).first())

    expect(await panel(page).getByRole('heading').boundingBox()).toMatchObject({ x: 652, y: 97 })
  })
})

test('à 400 px, le panneau est la fenêtre : une colonne, rayon 0, marge 8 px', async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, 'le plein écran : le projet mobile')
  await openTable(page, PROJECTS)
  const { width, height } = page.viewportSize()!

  await openProject(cards(page).first())

  expect(await panel(page).boundingBox()).toEqual({ x: 0, y: 0, width, height })
  await expect(panel(page)).toHaveCSS('border-top-left-radius', '0px')
  await expect(panel(page)).toHaveCSS('padding-top', '8px')
  await expect(panel(page)).toHaveCSS('grid-template-columns', `${width - 16}px`)
  await expect(panel(page)).toHaveCSS('row-gap', '12px')
})

test('fiche ouverte, aucune violation d’accessibilité', async ({ page }) => {
  await openTable(page, PROJECTS)
  await openProject(cards(page).first())

  const { violations } = await new AxeBuilder({ page }).analyze()

  expect(violations.map((violation) => violation.id)).toEqual([])
})
