/**
 * Le chargement à l'adresse d'une fiche (spec §5.1, « À l'adresse d'une fiche » ; issue #292) : un
 * cadre de fiche seul, à la place des cadres de la table, que la fiche recouvre par son fondu, sur
 * la page servie, l'API interceptée par les gestes d'`api.ts`.
 *
 * Le critère e2e de l'issue — à `/projets/<slug>`, la réponse retardée, le cadre de fiche et aucun
 * cadre de table ; à `/`, l'inverse — tient dans les deux premiers scénarios.
 */
import type { Page } from '@playwright/test'
import { LOADING_FRAME_COUNT } from '../src/table/cards.ts'
import { expect, FAILURES, holdProjects, serving, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import { expectNoViolations, expectPanelBox, panel } from './project.ts'
import { PROJECT_SETS } from './projects.ts'
import { cards, COLUMN_VIEWPORT } from './table.ts'

/** Trois projets, dont `projet-03`, à l'adresse `FICHE`. */
const PROJECTS = PROJECT_SETS.threeWithoutShowcase
const FICHE = '/projets/projet-03'

/** Le cadre de fiche. */
const frame = (page: Page) => page.locator('[data-project-frame]')

/** Les cellules de la table : pendant son chargement, ses cadres. */
const cells = (page: Page) => page.locator('[data-table-cell]')

/** La page entière, qui porte l'état « fiche ouverte » (`data-project-open`). */
const root = (page: Page) => page.locator('html')

/**
 * Ouvre une adresse sur la requête de la liste tenue en attente : le chargement, table occupée.
 *
 * @returns Le geste qui relâche la liste.
 */
async function openLoading(page: Page, path = FICHE) {
  const release = await holdProjects(page)
  await page.goto(path)
  await expect(page.getByRole('main')).toHaveAttribute('aria-busy', 'true')
  return release
}

test('à l’adresse d’une fiche, un cadre de fiche seul, caché et inerte, sans bouton ni cadre de table', async ({
  page,
}) => {
  await openLoading(page)

  await expect(frame(page)).toHaveCount(1)
  await expect(cells(page)).toHaveCount(0)
  await expect(frame(page)).toHaveAttribute('aria-hidden', 'true')
  await expect(frame(page)).toHaveAttribute('inert')
  await expect(frame(page).locator('button')).toHaveCount(0)
})

test('à `/`, les cadres de la table, sans cadre de fiche', async ({ page }) => {
  await openLoading(page, '/')

  await expect(cells(page)).toHaveCount(LOADING_FRAME_COUNT)
  await expect(frame(page)).toHaveCount(0)
})

test('le cadre a la boîte du panneau : centrée, 1232 × 642 à 1280 × 800, la fenêtre sous 600 px (spec §3.2)', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
  await openLoading(page)

  await expectPanelBox(page, frame(page))
})

test('dans le cadre, la photo de la galerie, puis dans la colonne de lecture le bloc du titre et trois barres (spec §5.1)', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
  const release = await openLoading(page)
  const [line] = await resolveAll(page, [['background-color', 'var(--line)']])
  // La photo, puis la colonne : le bloc du titre et les barres, dans leur rangée.
  const parts = await frame(page).evaluate((element) => {
    const box = (node: Element) => {
      const { x, y, width, height } = node.getBoundingClientRect()
      return { x, y, width, height }
    }
    const [photo, reading] = element.children
    const [title, bars] = reading.children
    const area = box(reading)
    const style = getComputedStyle(reading)
    const [top, right, left] = [style.paddingTop, style.paddingRight, style.paddingLeft].map(
      parseFloat,
    )
    return {
      photo: box(photo),
      reading: { x: area.x, width: area.width, padding: style.padding },
      // L'intérieur de la colonne, hors de ses marges.
      column: { x: area.x + left, y: area.y + top, width: area.width - left - right },
      title: box(title),
      bars: [...bars.children].map(box),
      transform: getComputedStyle(title).transform,
      colors: [photo, title, ...bars.children].map(
        (node) => getComputedStyle(node).backgroundColor,
      ),
    }
  })

  await release(serving(PROJECTS))
  await expect(panel(page)).toBeVisible()
  await settle(page)
  const fiche = await panel(page).evaluate((element) => {
    const photo = element.querySelector('.project-gallery-frame')!.getBoundingClientRect()
    const reading = element.querySelector('.project-reading')!
    const { x, width } = reading.getBoundingClientRect()
    // Le post-it du titre seul sur une ligne : son interligne et ses marges. Sa boîte, elle,
    // s'étire à la hauteur d'un post-it de lien voisin, dans la rangée de l'en-tête.
    const title = getComputedStyle(element.querySelector('.project-title')!)
    return {
      photo: { x: photo.x, y: photo.y, width: photo.width, height: photo.height },
      reading: { x, width, padding: getComputedStyle(reading).padding },
      titleHeight: [title.lineHeight, title.paddingTop, title.paddingBottom]
        .map(parseFloat)
        .reduce((sum, length) => sum + length),
    }
  })

  expect(parts.photo).toEqual(fiche.photo)
  expect(parts.reading).toEqual(fiche.reading)
  // Le post-it du titre sur une ligne, droit, sur la moitié de la colonne, en haut.
  expect(parts.title.height).toBe(fiche.titleHeight)
  expect(parts.transform).toBe('none')
  expect([parts.title.x, parts.title.y]).toEqual([parts.column.x, parts.column.y])
  expect(parts.title.width).toBeCloseTo(parts.column.width / 2, 0)
  // Trois barres de 10 px, à 100 %, 85 % et 60 % de la colonne, 16 px sous le bloc, 12 px entre
  // elles.
  expect(parts.bars).toHaveLength(3)
  const firstBar = parts.title.y + parts.title.height + 16
  for (const [index, share] of [1, 0.85, 0.6].entries()) {
    const bar = parts.bars[index]
    expect(bar.x).toBe(parts.column.x)
    expect(bar.y).toBeCloseTo(firstBar + index * (10 + 12), 0)
    expect(bar.width).toBeCloseTo(parts.column.width * share, 0)
    expect(bar.height).toBe(10)
  }
  expect(new Set(parts.colors)).toEqual(new Set([line]))
})

test('pendant le chargement, la page est déjà « fiche ouverte », et le reste à l’arrivée de la fiche (spec §3.3, §3.4)', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
  const release = await openLoading(page)

  await expect(root(page)).toHaveAttribute('data-project-open')
  await expect(root(page)).toHaveCSS('overflow', 'hidden')
  await expect(page.locator('header')).not.toBeInViewport()
  // Sous 600 px, le pied de page reste sous le plein écran (spec §3.4).
  if (!isMobile) await expect(page.locator('footer')).toHaveCSS('opacity', '0')

  // Un témoin posé dans la page : tout changement de l'attribut, retrait compris, y laisse une
  // trace.
  const changes = await page.evaluateHandle(() => {
    const seen: (string | null)[] = []
    const witness = new MutationObserver((records) =>
      seen.push(...records.map(({ oldValue }) => oldValue)),
    )
    witness.observe(document.documentElement, {
      attributeFilter: ['data-project-open'],
      attributeOldValue: true,
    })
    return seen
  })
  await release(serving(PROJECTS))
  await expect(panel(page)).toBeVisible()
  await settle(page)

  expect(await changes.jsonValue()).toEqual([])
})

test('la fiche apparaît par-dessus le cadre par son fondu de 200 ms, puis le cadre est retiré (spec §4.6, §5.1)', async ({
  page,
}) => {
  const release = await openLoading(page)
  await expect(frame(page)).toHaveCount(1)
  const [duration, curve] = await resolveAll(page, [
    ['animation-duration', 'var(--dur-content)'],
    ['animation-timing-function', 'var(--ease-out)'],
  ])
  // Le fondu de la fiche, figé dès son départ : placé à mi-course, il se lit à loisir.
  await page.evaluate(() =>
    addEventListener('animationstart', ({ target, animationName }) => {
      const element = target as Element
      if (animationName !== 'project-in' || !element.matches('[role="dialog"]')) return
      for (const animation of element.getAnimations()) animation.pause()
    }),
  )

  await release(serving(PROJECTS))

  await expect(panel(page)).toHaveCSS('animation-name', 'project-in')
  await expect(panel(page)).toHaveCSS('animation-duration', duration)
  await expect(panel(page)).toHaveCSS('animation-timing-function', curve)
  expect(duration).toBe('0.2s')
  const playStates = () =>
    panel(page).evaluate((element) => element.getAnimations().map(({ playState }) => playState))
  await expect.poll(playStates).toEqual(['paused'])
  // À mi-fondu, la fiche à demi opaque, et le cadre dessous : même couche, rendu avant elle.
  const midway = await page.evaluate(() => {
    const panel = document.querySelector('[role="dialog"]')!
    const frame = document.querySelector('[data-project-frame]')
    const [fade] = panel.getAnimations()
    fade.currentTime = (fade.effect!.getComputedTiming().endTime as number) / 2
    return {
      opacity: Number(getComputedStyle(panel).opacity),
      layers: frame && [getComputedStyle(frame).zIndex, getComputedStyle(panel).zIndex],
      before: Boolean(
        frame && frame.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING,
      ),
    }
  })
  expect(midway.opacity).toBeGreaterThan(0)
  expect(midway.opacity).toBeLessThan(1)
  expect(midway.layers).toEqual(['30', '30'])
  expect(midway.before).toBe(true)

  await panel(page).evaluate((element) => {
    for (const animation of element.getAnimations()) animation.play()
  })

  await expect(frame(page)).toHaveCount(0)
  await expect(panel(page)).toHaveCSS('opacity', '1')
})

test('un slug inconnu retire le cadre : l’adresse devient `/`, et la table s’affiche', async ({ page }) => {
  const release = await openLoading(page, '/projets/inconnu')
  await expect(frame(page)).toHaveCount(1)

  await release(serving(PROJECTS))

  await expect(page).toHaveURL('/')
  await expect(frame(page)).toHaveCount(0)
  await expect(root(page)).not.toHaveAttribute('data-project-open')
  await expect(cards(page)).toHaveCount(PROJECTS.length)
})

test('un échec affiche le message d’erreur sans cadre de fiche, et « Réessayer » repasse par le cadre', async ({
  page,
}) => {
  const failure = await openLoading(page)
  await expect(frame(page)).toHaveCount(1)

  await failure(FAILURES['réseau injoignable'])

  await expect(page.getByRole('status')).toHaveText('Les projets ne se chargent pas. Réessayer')
  await expect(frame(page)).toHaveCount(0)
  await expect(root(page)).not.toHaveAttribute('data-project-open')
  const retry = await holdProjects(page)

  await page.getByRole('button', { name: 'Réessayer' }).click()

  await expect(frame(page)).toHaveCount(1)
  await expect(cells(page)).toHaveCount(0)
  await retry(serving(PROJECTS))
  await expect(panel(page)).toBeVisible()
})

for (const [motion, pulse] of [
  ['no-preference', 'frame-pulse'],
  ['reduce', 'none'],
] as const) {
  test(`le cadre pulse comme ceux de la table, jamais en mouvement réduit — ${motion} (spec §5.1, §6.3)`, async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: motion })
    await openLoading(page)

    await expect(frame(page)).toHaveCSS('animation-name', pulse)
  })
}

for (const colorScheme of ['light', 'dark'] as const) {
  test(`chargement à l’adresse d’une fiche : aucune violation d’accessibilité — ${colorScheme}`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme })
    await openLoading(page)
    await expect(frame(page)).toHaveCount(1)

    await expectNoViolations(page)
  })
}
