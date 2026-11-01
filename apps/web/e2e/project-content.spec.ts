/**
 * Ce que la fiche donne à lire (spec §3.2, §4.3, §6.2, §6.3 ; issue #170) : son en-tête, sa ligne de
 * faits, sa stack, son Markdown, ses sections et leurs ancres, son défilement. Le dialogue, ses
 * adresses et ses fermetures : `project.spec.ts`.
 */
import { AxeBuilder } from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { expect, serveProjects, test } from './api.ts'
import { settle } from './css.ts'
import { closeButton, openProject, panel, watchCspViolations } from './project.ts'
import { buildProject, buildTechnology, ONGOING, type Project } from './projects.ts'
import { cards, openTable, serveUnderCsp } from './table.ts'

/** Le projet d'une fiche à un seul slug, ces champs remplacés. */
const ficheProject = (overrides: Partial<Project> = {}) =>
  buildProject({ slug: 'fiche', title: 'Fiche', ...overrides })

/** Arrive sur la fiche par son adresse. */
async function arriveAt(page: Page, overrides: Partial<Project> = {}, hash = '') {
  await serveProjects(page, [ficheProject(overrides)])
  await page.goto(`/projets/fiche${hash}`)
  await expect(panel(page)).toBeVisible()
  await page.evaluate(async () => void (await document.fonts.ready))
  await settle(page)
}

/** Aucune violation d'axe sur ce qui est rendu. */
async function expectNoViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze()

  expect(violations.map((violation) => violation.id)).toEqual([])
}

/** La rotation d'un élément, en degrés, lue sur sa matrice calculée. */
const rotation = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((element) => {
    const { a, b } = new DOMMatrix(getComputedStyle(element).transform)
    return Math.round((Math.atan2(b, a) * 180) / Math.PI)
  })

const LINKS = {
  demo_url: 'https://demo.test/fiche',
  repository_url: 'https://depot.test/fiche',
}

const THREE_TECHNOLOGIES_AND_A_TOOL = [
  buildTechnology('TypeScript', 'language'),
  buildTechnology('Figma', 'tool'),
  buildTechnology('React', 'framework'),
  buildTechnology('Docker', 'infrastructure'),
  buildTechnology('Redis', 'infrastructure'),
]

test.describe('l’en-tête', () => {
  test('le post-it du titre : <h2>, 22 / 600, rotation −2°', async ({ page }) => {
    await arriveAt(page)

    const title = panel(page).getByRole('heading', { level: 2 })

    await expect(title).toHaveText('Fiche')
    await expect(title).toHaveCSS('font-size', '22px')
    await expect(title).toHaveCSS('font-weight', '600')
    await expect(title).toHaveCSS('padding', '8px 14px 8px 16px')
    await expect(title).toHaveCSS('margin-bottom', '8px')
    expect(await rotation(page, '.project-title')).toBe(-2)
  })

  test('« Voir le site » puis « Voir le dépôt », dans le même onglet', async ({ page }) => {
    await arriveAt(page, LINKS)

    const links = panel(page).getByRole('link')

    await expect(links).toHaveCount(2)
    await expect(links.nth(0)).toHaveAccessibleName('Voir le site')
    await expect(links.nth(0)).toHaveAttribute('href', LINKS.demo_url)
    await expect(links.nth(1)).toHaveAccessibleName('Voir le dépôt')
    await expect(links.nth(1)).toHaveAttribute('href', LINKS.repository_url)
    await expect(links.nth(0)).not.toHaveAttribute('target')
    await expect(links.nth(0)).toHaveCSS('font-size', '15px')
    await expect(links.nth(0)).toHaveCSS('font-weight', '600')
    await expect(links.nth(0).locator('svg')).toHaveCSS('width', '14px')
    await expect(links.nth(0).locator('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  for (const [name, links, labels] of [
    ['le seul site', { demo_url: LINKS.demo_url }, ['Voir le site']],
    ['le seul dépôt', { repository_url: LINKS.repository_url }, ['Voir le dépôt']],
    ['aucun lien', {}, []],
  ] as const) {
    test(`${name} : un post-it par lien qui existe`, async ({ page }) => {
      await arriveAt(page, links)

      await expect(panel(page).getByRole('link')).toHaveText([...labels])
    })
  }

  test('au survol, le lien monte de 2 px en 150 ms et garde ses −4°', async ({ page, isMobile }) => {
    test.skip(isMobile, 'appareil sans survol')
    await arriveAt(page, LINKS)
    const link = panel(page).getByRole('link').first()
    const before = (await link.boundingBox())!

    expect(await rotation(page, '.project-link')).toBe(-4)
    await expect(link).toHaveCSS('transition-duration', '0.15s')

    await link.hover()
    await settle(page)

    expect(await rotation(page, '.project-link')).toBe(-4)
    expect((await link.boundingBox())!.y).toBeCloseTo(before.y - 2)
  })

  test('en mouvement réduit, le lien ne monte pas', async ({ page, isMobile }) => {
    test.skip(isMobile, 'appareil sans survol')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await arriveAt(page, LINKS)
    const link = panel(page).getByRole('link').first()
    const before = (await link.boundingBox())!

    await link.hover()
    await settle(page)

    expect((await link.boundingBox())!.y).toBe(before.y)
    expect(await rotation(page, '.project-link')).toBe(-4)
  })

  test('les rubans de la carte sont exposés aux technologies d’assistance', async ({ page }) => {
    await arriveAt(page, {
      ...ONGOING,
      demo_url: LINKS.demo_url,
      technologies: THREE_TECHNOLOGIES_AND_A_TOOL,
    })

    const ribbons = panel(page).locator('.project-head').getByRole('listitem')

    await expect(ribbons).toHaveText(['TypeScript', 'React', 'Docker', 'en cours', 'en ligne'])
    await expect(panel(page).locator('.project-head .project-ribbons')).toHaveCSS(
      'column-gap',
      '8px',
    )
  })
})

test.describe('ce qui défile', () => {
  test('la ligne de faits, puis le résumé', async ({ page }) => {
    await arriveAt(page, { kind: 'professional', client: 'Acme', summary: 'Le résumé.' })

    const facts = page.locator('.project-facts')

    await expect(facts).toHaveText('Pro · Janvier 2025 – juin 2025 · Acme')
    await expect(facts).toHaveCSS('font-size', '13px')
    await expect(facts).toHaveCSS('margin-bottom', '16px')
    await expect(page.locator('.project-facts + .project-summary')).toHaveText('Le résumé.')
    await expect(page.locator('.project-summary')).toHaveCSS('font-size', '16px')
  })

  test('toutes les technologies, puis les outils, nommés en clair', async ({ page }) => {
    await arriveAt(page, { technologies: THREE_TECHNOLOGIES_AND_A_TOOL })

    const headings = panel(page).getByRole('heading', { level: 3 })

    await expect(headings).toHaveText(['Technologies', 'Outils'])
    await expect(headings.first()).toHaveCSS('text-transform', 'uppercase')
    await expect(headings.first()).toHaveCSS('margin', '12px 0px 8px')
    const stacks = page.locator('.project-stack')
    await expect(stacks.first().getByRole('listitem')).toHaveText([
      'TypeScript',
      'React',
      'Docker',
      'Redis',
    ])
    await expect(stacks.last().getByRole('listitem')).toHaveText(['Figma'])
    await expect(stacks.first().getByRole('listitem').first()).toHaveCSS('padding-inline-start', '8px')
    await expect(stacks.first().getByRole('listitem').first()).toHaveCSS('column-gap', '6px')
    await expect(stacks.first().locator('.sr-only')).toHaveCount(0)
  })

  test('sans outil, ni intertitre « Outils » ni rubans', async ({ page }) => {
    await arriveAt(page, { technologies: [buildTechnology('React', 'framework')] })

    await expect(panel(page).getByRole('heading', { level: 3 })).toHaveText(['Technologies'])
    await expect(page.locator('.project-stack')).toHaveCount(1)
  })
})

test('fiche complète : les repères de §3.2 tiennent et axe ne trouve rien', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize({ width: 1280, height: 800 })
  await arriveAt(page, {
    ...ONGOING,
    ...LINKS,
    client: 'Acme',
    technologies: THREE_TECHNOLOGIES_AND_A_TOOL,
  })
  const { width, height } = page.viewportSize()!

  expect(await panel(page).boundingBox()).toEqual(
    isMobile
      ? { x: 0, y: 0, width, height }
      : { x: 24, y: 75, width: 1232, height: 650 },
  )
  await expectNoViolations(page)
})

test('sous la CSP de production, une fiche complète ne produit aucune violation', async ({ page }) => {
  const violations = watchCspViolations(page)
  await serveUnderCsp(page)
  await openTable(page, [ficheProject({ ...LINKS, technologies: THREE_TECHNOLOGIES_AND_A_TOOL })])

  await openProject(cards(page).first())

  await expect(closeButton(page)).toBeFocused()
  expect(violations).toEqual([])
})
