/**
 * La fiche d'un projet (spec §1.10, §3.2, §5.4, §6.2 ; issue #170) : son dialogue, ses adresses et
 * ses fermetures, sur la page servie, l'API et les fichiers interceptés par les gestes d'`api.ts`.
 *
 * Tant que la fiche est ouverte, Radix cache la page aux technologies d'assistance : une carte ne s'y
 * trouve plus par son rôle, seulement avant l'ouverture ou après la fermeture.
 */
import type { Locator, Page } from '@playwright/test'
import {
  countProjectRequests,
  expect,
  FAILURES,
  holdProjects,
  serveProjects,
  serving,
  test,
} from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  arriveAt,
  CLOSINGS,
  closeButton,
  expectClosed,
  expectPanelBox,
  freezeAnimations,
  holdNativeClicks,
  LINKS,
  nextImage,
  openFromTable,
  openProject,
  panel,
  previousImage,
  readingColumn,
  watchAnimations,
  watchCspViolations,
} from './project.ts'
import { buildImage, PROJECT_SETS } from './projects.ts'
import { nextFrames, scrollGesture, scrollThrough, scrollTop } from './scroll.ts'
import {
  cards,
  COLUMN_VIEWPORT,
  enterCards,
  expectPlacement,
  openTable,
  serveUnderCsp,
  tilt,
  watchTransitions,
} from './table.ts'

/** Trois projets aux titres distincts. La première carte, celle du projet en cours : `projet-02`. */
const PROJECTS = PROJECT_SETS.threeWithoutShowcase
const FIRST = { title: 'Projet 02', path: '/projets/projet-02' }

test('la fiche est un dialogue modal nommé par son titre, le focus sur « Fermer la fiche »', async ({
  page,
}) => {
  await openFromTable(page, PROJECTS)

  await expect(panel(page)).toHaveAccessibleName(FIRST.title)
  await expect(panel(page)).toHaveAttribute('aria-modal', 'true')
  await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(FIRST.title)
  await expect(closeButton(page)).toBeFocused()
})

test('parcours clavier complet : Tab boucle sur tous les arrêts, Maj+Tab à l’envers', async ({
  page,
}) => {
  await arriveAt(page, {
    ...LINKS,
    gallery: [buildImage('fiche', 'Une'), buildImage('fiche', 'Deux')],
    sections: ['Architecture', 'Résultats'].map((title, index) => ({
      title,
      anchor: `section-${index}`,
      body: 'Un corps.',
    })),
  })
  const stops = [
    closeButton(page),
    previousImage(page),
    nextImage(page),
    panel(page).getByRole('link', { name: 'Voir le site' }),
    panel(page).getByRole('link', { name: 'Voir le dépôt' }),
    readingColumn(page),
    panel(page).locator('summary').first(),
    panel(page).locator('summary').last(),
  ]
  await expect(stops[0]).toBeFocused()

  for (const stop of [...stops.slice(1), stops[0]]) {
    await page.keyboard.press('Tab')
    await expect(stop).toBeFocused()
  }

  for (const stop of stops.slice(1).reverse().concat(stops[0])) {
    await page.keyboard.press('Shift+Tab')
    await expect(stop).toBeFocused()
  }
})

for (const [name, close] of CLOSINGS) {
  test(`${name} ferme la fiche et rend le focus à la carte`, async ({ page }) => {
    await openTable(page, PROJECTS)
    const card = cards(page).last()
    await openProject(card)

    await close(page)

    await expectClosed(page)
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

test('sous la CSP de production, la page ne défile pas pendant la fiche et rend sa position, sans violation', async ({
  page,
}) => {
  const violations = watchCspViolations(page)
  await serveUnderCsp(page)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  await card.scrollIntoViewIfNeeded()
  const top = await scrollTop(page)
  expect(top).toBeGreaterThan(0)

  await openProject(card)
  await scrollGesture(page, -100)

  expect(await scrollTop(page)).toBe(top)

  await closeButton(page).click()
  await expectClosed(page)

  expect(await scrollTop(page)).toBe(top)
  expect(violations).toEqual([])

  await scrollGesture(page, -100)

  expect(await scrollTop(page)).toBeLessThan(top)
})

test('une carte coupée par le bord de la fenêtre ne fait pas défiler la page à la fermeture', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  const box = (await card.boundingBox())!
  await scrollThrough(page, box.y + box.height / 2 - page.viewportSize()!.height)
  const top = await scrollTop(page)

  await card.dispatchEvent('click', { detail: 0 })
  await closeButton(page).click()
  await expectClosed(page)

  await expect(card).toBeFocused()
  expect(await scrollTop(page)).toBe(top)
})

test('une carte hors de la fenêtre après une arrivée directe y vient avec le focus', async ({ page }) => {
  await serveProjects(page, PROJECT_SETS.twelveWithShowcase)
  await page.goto('/projets/projet-01')

  await closeButton(page).click()
  await expectClosed(page)

  const card = cards(page).last()
  await expect(card).toBeFocused()
  await expect(card).toBeInViewport()
})

test('rouverte par l’historique, sans carte d’origine, la fiche efface toutes les cartes en 150 ms, sans transformation ni pointeur, et elles reviennent', async ({
  page,
}) => {
  await openTable(page, PROJECTS)
  await settle(page)
  const cells = await page.locator('.card').all()
  const [fast] = await resolveAll(page, [['transition-duration', 'var(--dur-fast)']])
  await openProject(cards(page).first())
  await closeButton(page).click()
  await expectClosed(page)

  await page.goForward()
  await expect(panel(page)).toBeVisible()

  for (const cell of cells) {
    await expect(cell).toHaveCSS('opacity', '0')
    await expect(cell).toHaveCSS('transition-property', 'opacity')
    await expect(cell).toHaveCSS('transition-duration', fast)
    await expect(cell).toHaveCSS('transform', 'none')
    await expect(cell).toHaveCSS('pointer-events', 'none')
  }

  await closeButton(page).click()
  await expectClosed(page)

  for (const cell of cells) {
    await expect(cell).toHaveCSS('opacity', '1')
    await expect(cell).toHaveCSS('pointer-events', 'auto')
  }
})

test('l’entête sort pendant la fiche, en haut de page aussi, et revient à la fermeture', async ({
  page,
}) => {
  await openTable(page, PROJECTS)
  const header = page.locator('header')
  await expect(header).toBeInViewport()

  await openProject(cards(page).first())

  await expect(header).not.toBeInViewport()

  await closeButton(page).click()

  await expect(header).toBeInViewport()
})

test('à 1280 × 800, la colonne des liens s’efface en 150 ms et revient à la fermeture', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'largeur de bureau : le projet desktop la porte')
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECTS)
  await expectPlacement(page, 'column')
  const footer = page.locator('footer')
  const [fast] = await resolveAll(page, [['transition-duration', 'var(--dur-fast)']])

  await expect(footer).toHaveCSS('transition-property', 'opacity')
  await expect(footer).toHaveCSS('transition-duration', fast)

  await openProject(cards(page).first())

  await expect(footer).toHaveCSS('opacity', '0')
  await expect(footer).toHaveCSS('pointer-events', 'none')

  await closeButton(page).click()

  await expect(footer).toHaveCSS('opacity', '1')
  await expect(footer).toHaveCSS('pointer-events', 'auto')
})

test('à 400 × 800, le pied de page reste sous le plein écran', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'le plein écran : le projet mobile')
  await page.setViewportSize({ width: 400, height: 800 })
  await openTable(page, PROJECTS)
  await expectPlacement(page, 'footer')

  await openProject(cards(page).first())

  await expect(page.locator('footer')).toHaveCSS('opacity', '1')
})

test('en mouvement réduit, l’entête et la fiche passent par un fondu seul', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await openTable(page, PROJECTS)
  const header = page.locator('header')
  const animations = await watchAnimations(page)

  await openProject(cards(page).first())

  await expect(header).toHaveCSS('opacity', '0')
  await expect(header).toHaveCSS('pointer-events', 'none')
  await expect(header).toHaveCSS('translate', 'none')
  await expect(panel(page)).toHaveCSS('transform', 'none')
  await expect(panel(page)).toHaveCSS('translate', 'none')

  await closeButton(page).click()
  await expectClosed(page)

  await expect(header).toHaveCSS('opacity', '1')
  await expect(header).toHaveCSS('pointer-events', 'auto')
  expect((await animations()).map(({ name }) => name)).toEqual(['project-in', 'project-out'])
})

test('un clic hors du panneau ne ferme pas la fiche', async ({ page, isMobile }) => {
  test.skip(isMobile, 'plein écran : le panneau n’a pas de dehors')
  await openFromTable(page, PROJECTS)

  await page.mouse.click(4, 4)
  await settle(page)

  await expect(panel(page)).toHaveAttribute('data-state', 'open')
  await expect(page).toHaveURL(FIRST.path)
})

test.describe('l’historique, à partir de `/`', () => {
  test('ouvrir puis retour ferme, suivant rouvre la même fiche, qui se ferme comme les autres', async ({
    page,
  }) => {
    await openFromTable(page, PROJECTS)

    await page.goBack()

    await expectClosed(page)

    await page.goForward()

    await expect(panel(page)).toHaveAccessibleName(FIRST.title)
    await expect(page).toHaveURL(FIRST.path)

    await closeButton(page).click()

    await expectClosed(page)
  })

  const DOUBLE_CLOSINGS: [string, (page: Page) => Promise<unknown>][] = [
    ['un double clic sur « Fermer la fiche »', (page) => closeButton(page).dblclick()],
    [
      'Échap deux fois de suite',
      async ({ keyboard }) => {
        await Promise.all([keyboard.press('Escape'), keyboard.press('Escape')])
      },
    ],
  ]

  for (const [name, closeTwice] of DOUBLE_CLOSINGS) {
    test(`${name} ne ferme qu’une fois et reste sur le site`, async ({ page }) => {
      await openFromTable(page, PROJECTS)

      await closeTwice(page)

      await expectClosed(page)
    })
  }

  test('ouvrir ajoute une entrée, « Fermer la fiche » n’en laisse aucune de plus', async ({ page }) => {
    await openTable(page, PROJECTS)
    const entries = () => page.evaluate(() => history.length)
    const before = await entries()

    await openProject(cards(page).first())

    expect(await entries()).toBe(before + 1)

    await closeButton(page).click()

    await expectClosed(page)
    expect(await entries()).toBe(before + 1)

    await page.goForward()

    await expect(panel(page)).toBeVisible()
  })
})

test.describe('l’arrivée directe', () => {
  /** Les cellules de la table entrées. */
  const entered = (page: Page) => page.locator('.card[data-entered]')

  test('« Fermer la fiche » reste sur le site, à `/`, et rend le focus à la carte', async ({ page }) => {
    await serveProjects(page, PROJECTS)
    await page.goto(FIRST.path)
    await expect(panel(page)).toBeVisible()

    await closeButton(page).click()

    await expectClosed(page)
    await expect(cards(page).first()).toBeFocused()
  })

  test('le chargement d’abord, puis la fiche en fondu, le focus sur « Fermer la fiche »', async ({
    page,
  }) => {
    const release = await holdProjects(page)
    await page.goto(FIRST.path)

    await expect(page.locator('[data-table-cell]')).toHaveCount(3)
    await expect(panel(page)).toHaveCount(0)

    await release(serving(PROJECTS))

    await expect(panel(page)).toHaveAccessibleName(FIRST.title)
    await expect(panel(page)).toHaveCSS('animation-name', 'project-in')
    await expect(closeButton(page)).toBeFocused()
    await expect(page).toHaveTitle(FIRST.title)
  })

  test('en erreur, l’état d’erreur, puis la fiche quand « Réessayer » ramène la liste', async ({
    page,
  }) => {
    const failure = await holdProjects(page)
    await page.goto(FIRST.path)
    await failure(FAILURES['statut 500'])
    const retry = page.getByRole('button', { name: 'Réessayer' })
    await expect(retry).toBeVisible()
    await expect(panel(page)).toHaveCount(0)
    await expect(page).toHaveURL(FIRST.path)
    await serveProjects(page, PROJECTS)

    await retry.click()

    await expect(panel(page)).toHaveAccessibleName(FIRST.title)
    await expect(closeButton(page)).toBeFocused()
  })

  test('un slug absent de la liste ramène à `/`, sans fiche, et les cartes entrent', async ({ page }) => {
    await serveProjects(page, PROJECTS)

    await page.goto('/projets/inconnu')

    await expect(page).toHaveURL('/')
    await expect(entered(page)).toHaveCount(PROJECTS.length)
    await expect(panel(page)).toHaveCount(0)
  })

  test('les cartes n’entrent qu’à la fermeture de la fiche', async ({ page }) => {
    await serveProjects(page, PROJECTS)
    await page.goto(FIRST.path)
    await expect(panel(page)).toBeVisible()
    await settle(page)

    await expect(entered(page)).toHaveCount(0)

    await closeButton(page).click()
    await expectClosed(page)

    await expect(entered(page)).toHaveCount(PROJECTS.length)
  })
})

test.describe('l’entrée des cartes autour d’une fiche ouverte depuis la table', () => {
  test('une carte déjà entrée ne rejoue rien à la fermeture', async ({ page }) => {
    await openTable(page, PROJECT_SETS.twelveWithShowcase)
    await enterCards(page)
    const transitions = await watchTransitions(page)

    await openProject(cards(page).first())
    await closeButton(page).click()
    await expectClosed(page)

    expect(await transitions('card-entry')).toEqual([])
  })

  test('une carte pas encore entrée entre encore après la fermeture', async ({ page }) => {
    await openFromTable(page, PROJECT_SETS.twelveWithShowcase)
    await closeButton(page).click()
    await expectClosed(page)
    const last = cards(page).last()
    await expect(last).not.toHaveAttribute('data-entered')

    await last.scrollIntoViewIfNeeded()

    await expect(last).toHaveAttribute('data-entered')
  })
})

test('fiche ouverte, le pointeur sur une carte n’incline rien', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans pointeur : rien n’incline')
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const cell = page.locator('.card').nth(8)
  const box = (await cell.boundingBox())!
  // La carte sous la marge basse du panneau, entre 725 et 800 px : le pointeur l'y atteindrait.
  const [x, y] = [box.x + box.width / 2, 760]
  await scrollThrough(page, box.y + box.height / 2 - y)
  const moveOver = async () => {
    await page.mouse.move(x, y)
    await page.mouse.move(x + 20, y + 10)
  }

  await moveOver()
  await expect(tilt(cell)).not.toHaveCSS('transform', 'none')
  await page.mouse.move(0, 0)
  await expect(tilt(cell)).toHaveCSS('transform', 'none')

  await cell.dispatchEvent('click', { detail: 0 })
  await expect(panel(page)).toBeVisible()
  await settle(page)
  await moveOver()
  await nextFrames(page)

  await expect(tilt(cell)).toHaveCSS('transform', 'none')
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

test('à l’arrivée directe, les fondus : entrée 200 ms, sortie 150 ms, `--ease-out`, le panneau retiré à la fin', async ({
  page,
}) => {
  const release = await holdProjects(page)
  await page.goto(FIRST.path)
  const [content, fast, curve] = await resolveAll(page, [
    ['animation-duration', 'var(--dur-content)'],
    ['animation-duration', 'var(--dur-fast)'],
    ['animation-timing-function', 'var(--ease-out)'],
  ])
  const animations = await watchAnimations(page)

  await release(serving(PROJECTS))
  await expect(panel(page)).toBeVisible()
  await closeButton(page).click()
  await expectClosed(page)

  // Sans la pulsation des cadres de chargement, qui peut partir après le geste.
  expect((await animations()).filter(({ name }) => name.startsWith('project-'))).toEqual([
    { name: 'project-in', duration: content, curve },
    { name: 'project-out', duration: fast, curve },
  ])
})

test('à l’arrivée directe, pendant le fondu de sortie, le panneau garde son titre', async ({ page }) => {
  await arriveAt(page, { title: FIRST.title })
  await freezeAnimations(page)

  await page.keyboard.press('Escape')

  await expect(panel(page)).toHaveAttribute('data-state', 'closed')
  await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(FIRST.title)
})

test('le panneau : papier, ombre soulevée, z-index 30, sans voile', async ({ page }) => {
  await openFromTable(page, PROJECTS)
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
  await openFromTable(page, PROJECTS)
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
    [1280, 800, 594, 1232, 642],
    [1440, 900, 660, 1364, 708],
    [1024, 768, 466, 976, 514],
    [1280, 600, 504, 1052, 552],
  ]) {
    test(`à ${width} × ${height}, le panneau mesure ${panelWidth} × ${panelHeight}, deux colonnes de ${photo} px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height })
      await openFromTable(page, PROJECTS)

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
    await openFromTable(page, PROJECTS)

    expect(await panel(page).locator('.project-head').boundingBox()).toMatchObject({ x: 652, y: 101 })
  })
})

test('à 400 px, le panneau est la fenêtre : une colonne, rayon 0, marge 8 px', async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, 'le plein écran : le projet mobile')
  await openTable(page, PROJECTS)
  const { width } = page.viewportSize()!

  await openProject(cards(page).first())

  await expectPanelBox(page)
  await expect(panel(page)).toHaveCSS('border-top-left-radius', '0px')
  await expect(panel(page)).toHaveCSS('padding-top', '8px')
  await expect(panel(page)).toHaveCSS('grid-template-columns', `${width - 16}px`)
  await expect(panel(page)).toHaveCSS('row-gap', '12px')
})
