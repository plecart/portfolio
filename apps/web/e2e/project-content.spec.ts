/**
 * Ce que la fiche donne à lire (spec §3.2, §4.3, §6.2, §6.3 ; issue #170) : son en-tête, sa ligne de
 * faits, sa stack, son Markdown, ses sections et leurs ancres, son défilement. Le dialogue, ses
 * adresses et ses fermetures : `project.spec.ts`.
 */
import type { Locator, Page } from '@playwright/test'
import { expect, test } from './api.ts'
import { resolveAll, rotationOf, settle } from './css.ts'
import {
  arriveAt,
  closeButton,
  expectClosed,
  expectNoOverflow,
  expectNoViolations,
  expectPanelBox,
  ficheProject,
  holdNativeClicks,
  LINKS,
  LONG_DESCRIPTION,
  nextImage,
  openFromTable,
  openProject,
  panel,
  readingColumn,
  watchCspViolations,
} from './project.ts'
import { buildImage, buildTechnology, FILES_ORIGIN, ONGOING } from './projects.ts'
import { scrollTop } from './scroll.ts'
import { cards, COLUMN_VIEWPORT, openTable, serveUnderCsp } from './table.ts'

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
    expect(await rotationOf(title)).toBe(-2)
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

    expect(await rotationOf(link)).toBe(-4)
    await expect(link).toHaveCSS('transition-duration', '0.15s')

    await link.hover()
    await settle(page)

    expect(await rotationOf(link)).toBe(-4)
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
    expect(await rotationOf(link)).toBe(-4)
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

test.describe('la description en Markdown', () => {
  const description = (page: Page) => page.locator('.project-description')

  for (const html of [
    '<script>alert(1)</script>',
    '<b>x</b>',
    '<img src=x onerror=alert(1)>',
    '<a href="javascript:alert(1)">x</a>',
  ]) {
    test(`${html} s’affiche en texte, sans élément créé`, async ({ page }) => {
      await arriveAt(page, { description: html })

      await expect(description(page)).toHaveText(html)
      await expect(description(page).locator('script, b, img, a')).toHaveCount(0)
    })
  }

  /** Les protocoles qu'un lien ne doit jamais porter. */
  const DANGEROUS = ['javascript:', 'vbscript:', 'data:']

  for (const markdown of [
    '[x](javascript:alert(1))',
    '[x](JaVaScRiPt:alert(1))',
    '[x](&#x6A;avascript:alert(1))',
    '[x](<java&#9;script:alert(1)>)',
    '<javascript:alert(1)>',
    '[x][r]\n\n[r]: javascript:alert(1)',
    '[x](data:text/html,x)',
    '[x](vbscript:x)',
  ]) {
    test(`${JSON.stringify(markdown)} ne porte aucun href dangereux`, async ({ page }) => {
      await arriveAt(page, { description: markdown })

      const links = description(page).locator('a')

      await expect(links).toHaveCount(1)
      expect(DANGEROUS).not.toContain(await links.evaluate((link: HTMLAnchorElement) => link.protocol))
    })
  }

  test('paragraphes, listes et liens conformes à §4.3, et axe ne trouve rien', async ({ page }) => {
    await arriveAt(page, {
      description: [
        'Un paragraphe avec [un lien](https://exemple.test/).',
        'Un autre, **en gras** et *en italique*.',
        '- un point\n- un autre',
        '1. premier\n2. second',
      ].join('\n\n'),
    })

    await expect(description(page)).toHaveCSS('margin-top', '16px')
    await expect(description(page).locator('p')).toHaveCount(2)
    await expect(description(page).locator('p').first()).toHaveCSS('margin-bottom', '12px')
    await expect(description(page).locator('p').first()).toHaveCSS('font-size', '16px')
    await expect(description(page).locator('strong')).toHaveText('en gras')
    await expect(description(page).locator('em')).toHaveText('en italique')
    const [list, numbered] = [description(page).locator('ul'), description(page).locator('ol')]
    await expect(list.getByRole('listitem')).toHaveText(['un point', 'un autre'])
    await expect(list).toHaveCSS('padding-left', '18px')
    await expect(list).toHaveCSS('list-style-type', 'disc')
    await expect(numbered).toHaveCSS('padding-left', '18px')
    await expect(numbered).toHaveCSS('list-style-type', 'decimal')
    const [accent] = await resolveAll(page, [['color', 'var(--accent)']])
    const link = description(page).getByRole('link', { name: 'un lien' })
    await expect(link).toHaveAttribute('href', 'https://exemple.test/')
    await expect(link).toHaveCSS('color', accent)
    await expect(link).toHaveCSS('text-decoration-line', 'underline')
    await expectNoViolations(page)
  })

  test('une seule ligne est un paragraphe comme les autres', async ({ page }) => {
    await arriveAt(page, { description: 'Une seule ligne.' })

    await expect(description(page).locator('p')).toHaveText('Une seule ligne.')
    await expect(description(page).locator('p')).toHaveCSS('margin-bottom', '12px')
  })

  test('un bloc entre deux lignes de tirets reste dans la description', async ({ page }) => {
    await arriveAt(page, { description: '---\ntitre: valeur\n---\n\nLa suite.' })

    await expect(description(page)).toContainText('titre: valeur')
    await expect(description(page)).toContainText('La suite.')
  })

  const LONG_LINE = 'une ligne de code très longue '.repeat(30)
  const LONG_TOKEN = 'x'.repeat(600)

  for (const [name, markdown] of [
    ['un bloc de code à longue ligne', `\`\`\`\n${LONG_LINE}\n\`\`\``],
    ['un bloc de code sans espace', `\`\`\`\n${LONG_TOKEN}\n\`\`\``],
    ['du code en ligne', `\`${LONG_TOKEN}\``],
    ['un tableau', `| ${LONG_TOKEN} | b |\n|---|---|\n| ${LONG_LINE} | d |`],
    ['une image', `![image](${FILES_ORIGIN}/images/fiche/960.webp)`],
  ]) {
    test(`${name} ne déborde pas`, async ({ page }) => {
      await arriveAt(page, { description: markdown })

      await expectNoOverflow(readingColumn(page))
      await expectNoOverflow(panel(page))
    })
  }
})

/** Deux sections montrées, une omise entre elles ; un corps de deux blocs, l'autre avec un lien. */
const SECTIONS = [
  { title: 'Architecture', anchor: 'architecture', body: 'Les briques du projet.\n\n- une\n- deux' },
  { title: 'Section vide', anchor: 'vide', body: ' \n ' },
  { title: 'Résultats', anchor: 'resultats', body: 'Ce que le projet a [donné](https://exemple.test/).' },
]

/** Ce qui défile : la colonne au bureau, le panneau sur téléphone (spec §4.3). */
const scroller = (page: Page, isMobile: boolean) =>
  isMobile ? panel(page) : readingColumn(page)

const section = (page: Page, anchor: string) => page.locator(`[id="s-${anchor}"]`)

/** Attend la section posée à 8 px du haut de ce qui défile (`scroll-margin-top`). */
async function expectScrolledTo(page: Page, anchor: string, isMobile: boolean) {
  const scrollerTop = (await scroller(page, isMobile).boundingBox())!.y
  await expect
    .poll(async () => Math.round((await section(page, anchor).boundingBox())!.y - scrollerTop))
    .toBe(8)
}

test.describe('les sections', () => {
  test('dans l’ordre de l’admin, repliées, les vides omises, et axe ne trouve rien', async ({
    page,
  }) => {
    await arriveAt(page, { sections: SECTIONS })

    const sections = panel(page).locator('details')

    await expect(sections).toHaveCount(2)
    await expect(sections.locator('summary')).toHaveText(['Architecture', 'Résultats'])
    await expect(sections.nth(0)).toHaveAttribute('id', 's-architecture')
    await expect(sections.nth(1)).toHaveAttribute('id', 's-resultats')
    await expect(sections.nth(0)).not.toHaveAttribute('open')
    await expect(sections.nth(1)).not.toHaveAttribute('open')
    await expect(panel(page).getByText('Les briques du projet.')).toBeHidden()
    await expectNoViolations(page)
  })

  test('sans section à montrer, aucun bloc', async ({ page }) => {
    await arriveAt(page, { sections: [SECTIONS[1]] })

    await expect(page.locator('.project-sections')).toHaveCount(0)
  })

  test('la mise en forme de §4.3', async ({ page }) => {
    await arriveAt(page, { sections: SECTIONS })
    const [ink, ink2, line] = await resolveAll(page, [
      ['color', 'var(--ink)'],
      ['color', 'var(--ink-2)'],
      ['border-top-color', 'var(--line)'],
    ])

    const block = page.locator('.project-sections')
    await expect(block).toHaveCSS('margin-top', '16px')
    await expect(block).toHaveCSS('border-top', `1px solid ${line}`)
    const details = section(page, 'architecture')
    await expect(details).toHaveCSS('border-bottom', `1px solid ${line}`)
    await expect(details).toHaveCSS('scroll-margin-top', '8px')
    const summary = details.locator('summary')
    await expect(summary).toHaveCSS('height', '47px')
    await expect(summary).toHaveCSS('font-size', '15px')
    await expect(summary).toHaveCSS('font-weight', '700')
    await expect(summary).toHaveCSS('color', ink)
    await expect(summary).toHaveCSS('list-style-type', 'none')
    const sign = summary.locator('[aria-hidden="true"]')
    await expect(sign).toHaveCSS('font-size', '18px')
    await expect(sign).toHaveCSS('color', ink2)
    const [summaryBox, signBox] = [await summary.boundingBox(), await sign.boundingBox()]
    expect(signBox!.x + signBox!.width).toBe(summaryBox!.x + summaryBox!.width)

    await summary.click()

    await expect(details.locator('p')).toHaveCSS('margin-bottom', '8px')
    await expect(details.locator('p')).toHaveCSS('font-size', '16px')
    await expect(details.locator('.project-section-body')).toHaveCSS('margin-bottom', '12px')
  })

  /** Le signe d'une section, tel que la feuille l'écrit. */
  const sign = (page: Page, anchor: string) =>
    section(page, anchor)
      .locator('summary [aria-hidden="true"]')
      .evaluate((element) => getComputedStyle(element, '::before').content)

  test('un clic déroule, « + » devient « − », et l’adresse ne change pas', async ({ page }) => {
    await arriveAt(page, { sections: SECTIONS })
    const url = page.url()
    expect(await sign(page, 'architecture')).toBe('"+"')

    await section(page, 'architecture').locator('summary').click()

    await expect(panel(page).getByText('Les briques du projet.')).toBeVisible()
    expect(await sign(page, 'architecture')).toBe('"−"')
    expect(page.url()).toBe(url)
  })

  test('au clavier, Entrée déroule', async ({ page }) => {
    await arriveAt(page, { sections: SECTIONS })

    await section(page, 'architecture').locator('summary').press('Enter')

    await expect(section(page, 'architecture')).toHaveAttribute('open')
  })

  test('un lien dans une section repliée ne retient pas le focus', async ({ page }) => {
    await arriveAt(page, { sections: SECTIONS })
    await panel(page).locator('summary').last().focus()

    await page.keyboard.press('Tab')

    await expect(closeButton(page)).toBeFocused()
  })
})

test.describe('les ancres', () => {
  /** Une section dont le corps, une fois déroulé, laisse de quoi la monter en haut. */
  const LONG_SECTIONS = [...SECTIONS.slice(0, 2), { ...SECTIONS[2], body: LONG_DESCRIPTION }]
  const FICHE = { description: LONG_DESCRIPTION, sections: LONG_SECTIONS }

  test('une arrivée directe ouvre la section, la fait défiler et laisse le focus au bouton', async ({
    page,
    isMobile,
  }) => {
    await arriveAt(page, FICHE, '#s-resultats')

    await expect(section(page, 'resultats')).toHaveAttribute('open')
    await expect(section(page, 'architecture')).not.toHaveAttribute('open')
    await expectScrolledTo(page, 'resultats', isMobile)
    await expect(closeButton(page)).toBeFocused()
    expect(await scrollTop(page)).toBe(0)
  })

  test('hashchange ouvre la section de la nouvelle ancre', async ({ page, isMobile }) => {
    await arriveAt(page, FICHE)

    await page.evaluate(() => {
      location.hash = '#s-resultats'
    })

    await expect(section(page, 'resultats')).toHaveAttribute('open')
    await expectScrolledTo(page, 'resultats', isMobile)
  })

  for (const [name, hash] of [
    ['une ancre inconnue', '#s-inconnue'],
    ['une section omise', '#s-vide'],
    ['un fragment sans section', '#root'],
  ]) {
    test(`${name} ne fait rien`, async ({ page, isMobile }) => {
      await arriveAt(page, FICHE, hash)

      await expect(panel(page).locator('details[open]')).toHaveCount(0)
      expect(await scroller(page, isMobile).evaluate((element) => element.scrollTop)).toBe(0)
    })
  }

  /** Une fiche à lien vers cette adresse, en tête d'une description qui repousse ses sections loin. */
  const linkedFiche = (href: string) => ({
    description: `[Le lien](${href})\n\n${LONG_DESCRIPTION}`,
    sections: LONG_SECTIONS,
  })
  const LINKED = linkedFiche('#s-resultats')
  const descriptionLink = (page: Page) => panel(page).getByRole('link', { name: 'Le lien' })

  /** La fiche ouverte depuis la table, un lien vers cette adresse en tête de sa description. */
  const openWithLink = (page: Page, href: string) =>
    openFromTable(page, [ficheProject(linkedFiche(href))])

  test('après un lien de la fiche, le bouton revient à la table, sans fragment', async ({ page }) => {
    await openWithLink(page, '#s-resultats')
    await descriptionLink(page).click()

    await closeButton(page).click()

    await expectClosed(page)

    await page.goForward()

    await expect(panel(page)).toBeVisible()
    await expect(page).toHaveURL('/projets/fiche#s-resultats')
  })

  test('après une arrivée directe sur une ancre, le bouton ne laisse pas de fragment', async ({
    page,
  }) => {
    await arriveAt(page, FICHE, '#s-resultats')

    await closeButton(page).click()

    await expectClosed(page)
  })

  test('au clavier, Entrée sur un lien ouvre la section et y porte le focus', async ({ page }) => {
    await arriveAt(page, LINKED)

    await descriptionLink(page).focus()
    await page.keyboard.press('Enter')

    await expect(section(page, 'resultats')).toHaveAttribute('open')
    await expect(section(page, 'resultats').locator('summary')).toBeFocused()
  })

  for (const hash of ['#s-resultats', '#autre']) {
    test(`Ctrl sur un lien vers ${hash} garde le geste du navigateur`, async ({ page }) => {
      await arriveAt(page, linkedFiche(hash))
      const heldClicks = await holdNativeClicks(page)

      await descriptionLink(page).click({ modifiers: ['ControlOrMeta'] })

      expect(await heldClicks()).toBe(1)
      await expect(section(page, 'resultats')).not.toHaveAttribute('open')
    })
  }

  for (const [name, href, url, opened] of [
    ['d’une section', '#s-resultats', '/projets/fiche#s-resultats', 1],
    ['d’une section inconnue', '#s-inconnue', '/projets/fiche#s-inconnue', 0],
    ['hors section', '#autre', '/projets/fiche', 0],
    ['vide', '#', '/projets/fiche', 0],
    ['d’une section, par le chemin de la fiche', '/projets/fiche#s-resultats', '/projets/fiche#s-resultats', 1],
    ['hors section, par le chemin de la fiche', '/projets/fiche#autre', '/projets/fiche', 0],
  ] as const) {
    test(`le fragment ${name} n’ajoute aucune entrée : un seul retour ferme`, async ({ page }) => {
      await openWithLink(page, href)
      const entries = await page.evaluate(() => history.length)

      await descriptionLink(page).click()

      await expect(panel(page).locator('details[open]')).toHaveCount(opened)
      await expect(page).toHaveURL(url)
      expect(await page.evaluate(() => history.length)).toBe(entries)
      expect(await page.evaluate(() => history.state)).toEqual({ fromTable: true })

      await page.goBack()

      await expectClosed(page)
    })
  }

  for (const [name, href] of [
    ['relatif', '/autre'],
    ['relatif à fragment', '/autre#s-resultats'],
    ['absolu', 'https://exemple.test/'],
    ['absolu à fragment', 'https://exemple.test/#s-resultats'],
  ]) {
    test(`un lien ${name} reste au navigateur`, async ({ page }) => {
      await openWithLink(page, href)
      const heldClicks = await holdNativeClicks(page)

      await descriptionLink(page).click()

      expect(await heldClicks()).toBe(1)
    })
  }

  /** Compte les défilements de la page à partir de maintenant, sur tout élément. */
  async function watchScrolls(page: Page) {
    const scrolls = await page.evaluateHandle(() => {
      const seen = { count: 0 }
      addEventListener('scroll', () => (seen.count += 1), { capture: true })
      return seen
    })
    return async () => (await scrolls.jsonValue()).count
  }

  test('le défilement vers une ancre est animé', async ({ page, isMobile }) => {
    await arriveAt(page, LINKED)
    const scrolls = await watchScrolls(page)

    await descriptionLink(page).click()

    await expectScrolledTo(page, 'resultats', isMobile)
    expect(await scrolls()).toBeGreaterThan(1)
  })

  test('en mouvement réduit, il est instantané', async ({ page, isMobile }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await arriveAt(page, LINKED)
    const scrolls = await watchScrolls(page)

    await descriptionLink(page).click()

    await expectScrolledTo(page, 'resultats', isMobile)
    expect(await scrolls()).toBe(1)
  })
})

test.describe('le défilement', () => {
  const LONG = { description: LONG_DESCRIPTION }

  /** Fait défiler un élément, résolu une fois la position posée. */
  const scrollTo = (element: Locator, top: number) =>
    element.evaluate((scrolled, y) => scrolled.scrollTo({ top: y, behavior: 'instant' }), top)

  const scrolledBy = (element: Locator) => element.evaluate((scrolled) => scrolled.scrollTop)

  test('à 1280 × 800, seule la colonne défile, sous un en-tête fixe', async ({ page, isMobile }) => {
    test.skip(isMobile, 'au bureau : le projet desktop')
    await page.setViewportSize(COLUMN_VIEWPORT)
    await arriveAt(page, { ...LONG, ...LINKS })
    const column = readingColumn(page)
    const head = page.locator('.project-head')
    const before = await head.boundingBox()

    await expect(column).toHaveCSS('overflow-y', 'auto')
    await expect(column).toHaveCSS('margin-bottom', '16px')
    await expect(column).toHaveCSS('scrollbar-width', 'thin')
    expect(Math.round(before!.height)).toBe(89)
    expect(Math.round((await column.boundingBox())!.height + 16)).toBe(529)

    await scrollTo(column, 300)

    expect(await scrolledBy(column)).toBe(300)
    expect(await head.boundingBox()).toEqual(before)
    await expect(panel(page)).toHaveCSS('overflow-y', 'visible')
  })

  test('sur téléphone, tout défile avec le panneau, le bouton reste en haut à droite', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'le plein écran : le projet mobile')
    await arriveAt(page, { ...LONG, ...LINKS, title: 'Un titre de trente caractères.' })
    const button = await closeButton(page).boundingBox()

    await expect(readingColumn(page)).toHaveCSS('overflow-y', 'visible')
    await expect(panel(page)).toHaveCSS('overflow-y', 'auto')
    await expect(panel(page)).toHaveCSS('scrollbar-width', 'thin')
    await closeButton(page).click({ trial: true })

    await scrollTo(panel(page), 300)

    expect(await scrolledBy(panel(page))).toBe(300)
    expect(await closeButton(page).boundingBox()).toEqual(button)
    await closeButton(page).click()
    await expectClosed(page)
  })

  test('sur téléphone, un ruban qui passe sous le bouton reste dessous', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'le plein écran : le projet mobile')
    const name = 'Une technologie au nom qui atteint le bord droit de la colonne'
    await arriveAt(page, { ...LONG, technologies: [buildTechnology(name, 'tool')] })
    const button = (await closeButton(page).boundingBox())!
    const ribbon = (await page.locator('.project-stack .card-ribbon').boundingBox())!
    expect(ribbon.x + ribbon.width).toBeGreaterThan(button.x + button.width / 2)
    const { y, height } = ribbon

    await scrollTo(panel(page), y + height / 2 - (button.y + button.height / 2))

    await closeButton(page).click({ trial: true })
  })

  test('une description longue, sans lien ni section, défile au clavier, le focus d’ouverture au bouton', async ({
    page,
    isMobile,
  }) => {
    await arriveAt(page, LONG)
    await expect(closeButton(page)).toBeFocused()

    await page.keyboard.press('Tab')

    await expect(readingColumn(page)).toBeFocused()

    await page.keyboard.press('PageDown')

    await expect.poll(() => scrolledBy(scroller(page, isMobile))).toBeGreaterThan(0)
    await expectNoViolations(page)
  })

  test('l’anneau de focus d’une section tient dans la colonne, le texte à sa place', async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, 'la colonne ne coupe rien sur téléphone')
    await arriveAt(page, { ...LONG, sections: SECTIONS })
    const column = (await readingColumn(page).boundingBox())!
    const summary = (await page.locator('summary').first().boundingBox())!
    const head = (await page.locator('.project-head').boundingBox())!

    expect(summary.x - column.x).toBeGreaterThanOrEqual(5)
    expect(column.x + column.width - (summary.x + summary.width)).toBeGreaterThanOrEqual(5)
    expect(summary.x).toBe(head.x)
    expect(summary.x + summary.width).toBe(head.x + head.width - 8)
  })
})

test.describe('un client à la borne de #7, 100 caractères', () => {
  const WORDS =
    'Compagnie générale des établissements industriels et commerciaux de la région d’Auvergne-Rhône-Alpes'
  const LINE = 19.5

  for (const [name, client] of [
    ['en mots', WORDS],
    ['sans une espace', 'x'.repeat(100)],
  ]) {
    test(`${name} : trois lignes au plus, sans déborder ni bouger l’en-tête`, async ({ page }) => {
      expect(client).toHaveLength(100)
      await arriveAt(page, { client: 'Acme' })
      const head = await page.locator('.project-head').boundingBox()

      await arriveAt(page, { client })

      const facts = page.locator('.project-facts')
      expect((await facts.boundingBox())!.height).toBeLessThanOrEqual(3 * LINE)
      for (const element of [facts, readingColumn(page), panel(page)]) {
        await expectNoOverflow(element)
      }
      expect(await page.locator('.project-head').boundingBox()).toEqual(head)
    })
  }
})

test('fiche complète : les repères de §3.2 tiennent et axe ne trouve rien', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
  await arriveAt(page, {
    ...ONGOING,
    ...LINKS,
    client: 'Acme',
    technologies: THREE_TECHNOLOGIES_AND_A_TOOL,
    sections: SECTIONS,
  })

  await expectPanelBox(page)
  await expectNoViolations(page)
})

test('sous la CSP de production, une fiche complète et sa navigation ne produisent aucune violation', async ({
  page,
}) => {
  const violations = watchCspViolations(page)
  await serveUnderCsp(page)
  await openTable(page, [
    ficheProject({
      ...LINKS,
      gallery: [buildImage('fiche', 'Une'), buildImage('fiche', 'Deux')],
      description: `[Voir](#s-resultats)\n\n${LONG_DESCRIPTION}`,
      technologies: THREE_TECHNOLOGIES_AND_A_TOOL,
      sections: SECTIONS,
    }),
  ])

  await openProject(cards(page).first())
  await panel(page).getByRole('link', { name: 'Voir', exact: true }).click()
  await nextImage(page).click()
  await page.keyboard.press('ArrowLeft')
  await closeButton(page).click()
  await expectClosed(page)

  expect(violations).toEqual([])
})
