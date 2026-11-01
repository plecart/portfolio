/**
 * La table de cartes polaroid au repos (spec §1.3, §1.4, §1.9, §3.1, §4.1, §4.2, §5.5, §6.1, §6.2 ;
 * issue #168), sur la page servie, l'API et les fichiers interceptés par les gestes d'`api.ts`.
 *
 * Les seuils de la marge sont prouvés en Vitest et sa relecture dans
 * `author-links-measure.spec.ts` ; ici, la vraie table sous la mesure.
 */
import { AxeBuilder } from '@axe-core/playwright'
import type { Locator, Page } from '@playwright/test'
import { cardPose } from '../src/table/cards.ts'
import { expect, FAILURES, holdProjects, serving, test, type Answer } from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  buildImage,
  buildProject,
  buildTechnology,
  ONGOING,
  PROJECT_SETS,
  type Project,
} from './projects.ts'
import { scrollThrough } from './scroll.ts'
import {
  cards,
  COLUMN_VIEWPORT,
  enterCards,
  entry,
  expectPlacement,
  face,
  focusByKeyboard,
  openTable,
  pose,
  serveUnderCsp,
  summary,
  TWO_CARDS,
} from './table.ts'

/** Les couches de la couverture d'une carte : l'image, puis la copie d'un projet en cours. */
const coverLayers = (card: Locator) => card.locator('img[srcset]')

/** La rotation d'un élément, en degrés, au dixième, lue sur sa transformation calculée. */
const rotationOf = (element: Locator) =>
  element.evaluate((node) => {
    const { a, b } = new DOMMatrix(getComputedStyle(node).transform)
    return Math.round((Math.atan2(b, a) * 1800) / Math.PI) / 10
  })

const TABLES = Object.entries(PROJECT_SETS).filter(([, projects]) => projects.length > 0)

for (const [table, projects] of TABLES) {
  for (const colorScheme of ['light', 'dark'] as const) {
    test(`table ${table} : aucune violation d'accessibilité — ${colorScheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme })
      await openTable(page, projects)
      await enterCards(page)

      const { violations } = await new AxeBuilder({ page }).analyze()

      expect(violations.map((violation) => violation.id)).toEqual([])
    })
  }
}

/**
 * Les dimensions de spec §4.1, §4.2 et §6.1, par taille de carte : son jeu, l'indice de la carte
 * dans la table, et ses mesures au bureau puis sur mobile — largeur de carte, de photo, hauteur de
 * face, taille du post-it, hauteur et taille des rubans. La bande et le cadre s'en déduisent.
 */
const DIMENSIONS = [
  [
    'simple',
    PROJECT_SETS.threeWithShowcase,
    1,
    [240, 220, 282, 14, 20, 11],
    [176, 160, 214, 13, 20, 11],
  ],
  [
    'vitrine',
    PROJECT_SETS.threeWithShowcase,
    0,
    [508, 480, 558, 18, 24, 12],
    [368, 344, 412, 16, 20, 11],
  ],
  ['seule', PROJECT_SETS.one, 0, [360, 340, 402, 14, 20, 11], [294, 278, 332, 13, 20, 11]],
] as const

for (const [size, projects, index, desktop, mobile] of DIMENSIONS) {
  test(`carte ${size} : les dimensions du tableau de §4.1, que \`sizes\` annonce`, async ({
    page,
    isMobile,
  }) => {
    if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
    await openTable(page, projects)
    const card = cards(page).nth(index)
    const cover = coverLayers(card).first()
    await expect(cover).toHaveJSProperty('complete', true)

    const measured = await card.evaluate((link: HTMLAnchorElement) => {
      const element = (selector: string) => link.querySelector<HTMLElement>(selector)!
      const pixels = (selector: string, property: 'fontSize' | 'height') =>
        parseFloat(getComputedStyle(element(selector))[property])
      return {
        sizes: [
          link.offsetWidth,
          element('.card-photo').offsetWidth,
          element('.card-face').offsetHeight,
          pixels('h2', 'fontSize'),
          pixels('li', 'height'),
          pixels('li', 'fontSize'),
        ],
        // Une image en largeurs a pour taille naturelle ce que `sizes` annonce pour elle.
        announced: link.querySelector('img')!.naturalWidth,
      }
    })

    const expected = isMobile ? mobile : desktop
    expect(measured.sizes).toEqual(expected)
    // Le navigateur arrondit la taille naturelle à l'entier inférieur.
    expect(Math.abs(measured.announced - expected[1])).toBeLessThanOrEqual(1)
  })
}

/**
 * Le slug que la pose pousse le plus loin d'un côté, `-1` à gauche et `1` à droite : la rotation
 * écarte le coin de la carte la plus haute de 5 px par degré (`sin 1°` × sa demi-hauteur, 300 px à
 * 599 px de large), le décalage s'y ajoute.
 */
function farthestSlug(side: -1 | 1): string {
  const reach = (slug: string) => {
    const { rotation, dx } = cardPose(slug)
    return Math.abs(rotation) * 5 + side * dx
  }
  return Array.from({ length: 1000 }, (_, number) => `projet-${number}`).reduce((farthest, slug) =>
    reach(slug) > reach(farthest) ? slug : farthest,
  )
}

/**
 * Chaque taille de carte sous la pose extrême, de chaque côté : son nom, sa table, et son indice
 * dans celle-ci. Le voisin d'une carte simple la place dans la colonne de son côté, l'ordre suivant
 * le slug.
 */
const EXTREME_TABLES = ([-1, 1] as const).flatMap((side): [string, Project[], number][] => {
  const name = side < 0 ? 'à gauche' : 'à droite'
  const extreme = buildProject({ slug: farthestSlug(side) })
  const neighbor = buildProject({ slug: side < 0 ? 'voisin' : 'atelier' })
  return [
    [`simple ${name}`, [extreme, neighbor], side < 0 ? 0 : 1],
    [`vitrine ${name}`, [{ ...extreme, showcase: true }, neighbor], 0],
    [`seule ${name}`, [extreme], 0],
  ]
})

/** L'anneau de focus d'une carte, depuis la face : 2 px, à 4 px d'elle (spec §6.2). */
const FOCUS_RING = 2 + 4

for (const width of [480, 599]) {
  for (const [name, projects, index] of EXTREME_TABLES) {
    test(`à ${width} px, la pose extrême d'une carte ${name} n'élargit pas la page`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await openTable(page, projects)

      const { innerWidth, overflow } = await page.evaluate(() => ({
        innerWidth: window.innerWidth,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      }))

      expect(overflow).toBe(0)
      // Sur un appareil mobile, c'est toute la mise en page qui s'élargirait avec la page.
      expect(innerWidth).toBe(width)
    })

    test(`à ${width} px, l'anneau de focus d'une carte ${name} reste dans la page`, async ({
      page,
      isMobile,
    }) => {
      test.skip(isMobile, 'sans survol, la carte focalisée garde sa pose (spec §4.1)')
      await page.setViewportSize({ width, height: 800 })
      await openTable(page, projects)
      const card = cards(page).nth(index)

      await focusByKeyboard(card)
      await settle(page)

      const { left, right, pageWidth } = await face(card).evaluate((layer) => ({
        left: layer.getBoundingClientRect().left,
        right: layer.getBoundingClientRect().right,
        pageWidth: document.documentElement.clientWidth,
      }))
      expect(left - FOCUS_RING).toBeGreaterThanOrEqual(0)
      expect(right + FOCUS_RING).toBeLessThanOrEqual(pageWidth)
    })
  }
}

test('douze cartes et la vitrine : quinze cellules sur quatre rangées, ou six sous elle (spec §5.5)', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)

  const rows = await cards(page).evaluateAll((links) => {
    const tops = links.map((link) => link.getBoundingClientRect().top)
    return [...new Set(tops)].map((top) => tops.filter((other) => other === top).length)
  })

  expect(rows).toEqual(isMobile ? [1, 2, 2, 2, 2, 2, 1] : [3, 2, 4, 3])
})

test('une cellule s’arrête à sa face : la rangée n’ajoute aucun vide cliquable sous une carte', async ({
  page,
  isMobile,
}) => {
  if (!isMobile) await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)

  const gaps = await cards(page).evaluateAll((links: HTMLAnchorElement[]) =>
    links.map((link) => link.offsetHeight - link.querySelector<HTMLElement>('.card-face')!.offsetHeight),
  )

  expect(gaps).toEqual(Array(12).fill(0))
})

test('les cartes suivent l’ordre de la spec §1.9 : vitrine, en cours, puis du plus récent au plus ancien', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)

  const slugs = await cards(page).evaluateAll((links) =>
    links.map((link) => link.getAttribute('href')),
  )

  // `projet-02`, la vitrine ; les trois autres en cours (05, 08, 11), puis les autres.
  expect(slugs).toEqual(
    ['02', '11', '08', '05', '12', '10', '09', '07', '06', '04', '03', '01'].map(
      (number) => `/projets/projet-${number}`,
    ),
  )
})

test('les cartes remplacent les trois cadres à l’arrivée de la liste', async ({ page }) => {
  const release = await holdProjects(page)
  await page.goto('/')
  const cells = page.locator('[data-table-cell]')
  await expect(cells).toHaveCount(3)
  await expect(cards(page)).toHaveCount(0)

  await release(serving(PROJECT_SETS.twelveWithoutShowcase))

  await expect(cells).toHaveCount(12)
  await expect(cards(page)).toHaveCount(12)
})

/**
 * Les liens, nom et description, et le nom des titres, lus dans l'arbre d'accessibilité de Chromium :
 * le navigateur, pas Playwright ni axe, dont le calcul ne voit pas une liste `aria-hidden` que
 * `aria-describedby` désigne entrer dans le nom. Un nom se compare sans l'espace que Chromium pose
 * devant le point, entre le `<h2>` et le texte masqué qui le suit (« Atelier . En cours. »).
 */
async function accessibilityTree(page: Page) {
  const client = await page.context().newCDPSession(page)
  const { nodes } = await client.send('Accessibility.getFullAXTree')
  await client.detach()
  const named = (role: string) => nodes.filter((node) => node.role?.value === role)
  return {
    links: named('link').map(({ name, description }) => [
      name?.value.replaceAll(' .', '.'),
      description?.value,
    ]),
    headings: named('heading').map(({ name }) => name?.value),
  }
}

test('une carte est un lien vers sa fiche, nommé par son titre et ses états présents', async ({
  page,
}) => {
  await openTable(page, [
    buildProject({
      ...ONGOING,
      slug: 'atelier',
      title: 'Atelier',
      summary: 'Un atelier de reliure.',
      demo_url: 'https://demo.test/atelier',
    }),
    buildProject({ slug: 'banc', title: 'Banc', summary: 'Un banc de test' }),
    buildProject({ ...ONGOING, slug: 'question', title: 'Et après ?' }),
  ])

  const { links } = await accessibilityTree(page)

  expect(links).toContainEqual(['Atelier. En cours. En ligne.', 'Un atelier de reliure. TypeScript'])
  expect(links).toContainEqual(['Banc', 'Un banc de test. TypeScript'])
  expect(links.map(([name]) => name)).toContain('Et après ? En cours.')
  await expect(page.getByRole('link', { name: 'Atelier' })).toHaveAttribute(
    'href',
    '/projets/atelier',
  )
})

test('le résumé puis les technologies décrivent le lien : leur nom reste aux lecteurs d’écran (spec §1.4, §1.7)', async ({
  page,
}) => {
  await openTable(page, [
    buildProject({
      summary: 'Un site.',
      technologies: [buildTechnology('TypeScript', 'language'), buildTechnology('React', 'framework')],
    }),
  ])

  await expect(cards(page)).toHaveAccessibleDescription('Un site. TypeScript, React')
})

test('dans l’arbre d’accessibilité de Chromium, le résumé et les rubans restent hors du nom, carte révélée comprise', async ({
  page,
  isMobile,
}) => {
  await openTable(page, [buildProject({ ...ONGOING, title: 'Atelier', summary: 'Un atelier.' })])
  const card = cards(page)
  const link = ['Atelier. En cours.', 'Un atelier. TypeScript']
  expect((await accessibilityTree(page)).links).toContainEqual(link)

  await (isMobile ? card.tap() : card.hover())
  await expect(summary(card)).toHaveCSS('opacity', '1')

  const { links, headings } = await accessibilityTree(page)
  expect(links).toContainEqual(link)
  expect(headings).toContain('Atelier')
})

test('une carte porte son titre en `<h2>`, ses éléments décoratifs masqués', async ({ page }) => {
  await openTable(page, [buildProject({ ...ONGOING, title: 'Atelier' })])
  const card = cards(page)

  await expect(card.getByRole('heading', { level: 2, name: 'Atelier' })).toBeVisible()
  // Le point du titre et les états n'existent que pour le nom du lien.
  await expect(card.getByText('. En cours.')).toHaveClass('sr-only')
  await expect(card.locator('svg')).toHaveAttribute('aria-hidden', 'true')
  // La couverture, sa copie en noir et blanc, l'icône : le nom du lien les porte.
  expect(
    await card.locator('img').evaluateAll((images) => images.map((image) => image.getAttribute('alt'))),
  ).toEqual(['', '', ''])
  await expect(coverLayers(card).nth(1)).toHaveAttribute('aria-hidden', 'true')
  await expect(card.locator('.card-band')).toHaveAttribute('aria-hidden', 'true')
})

test('toutes les cartes sont des cibles de 36 px au moins, et toutes leurs images `lazy`', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)

  const boxes = await cards(page).evaluateAll((links) =>
    links.map((link) => link.getBoundingClientRect()).map(({ width, height }) => [width, height]),
  )
  const loading = await page
    .getByRole('main')
    .locator('img')
    .evaluateAll((images: HTMLImageElement[]) => images.map((image) => image.loading))

  expect(Math.min(...boxes.flat())).toBeGreaterThanOrEqual(36)
  // Onze couvertures, leurs quatre copies en cours, vingt icônes : toute la population.
  expect(loading).toEqual(Array(11 + 4 + 20).fill('lazy'))
})

test('un post-it long tient sur deux lignes au plus, large de la carte moins 28 px (spec §4.1)', async ({
  page,
}) => {
  // Trente caractères : le titre le plus long, en mots puis d'un seul tenant, qui atteint la borne.
  await openTable(page, [
    buildProject({ slug: 'a', title: 'Un titre long de trente lettre' }),
    buildProject({ slug: 'b', title: 'Untitrelongdetrentelettresdune' }),
  ])

  const postits = await cards(page).evaluateAll((links: HTMLAnchorElement[]) =>
    links.map((link) => {
      const postit = link.querySelector('h2')!
      const { lineHeight, paddingBottom, paddingTop } = getComputedStyle(postit)
      const inset = parseFloat(paddingTop) + parseFloat(paddingBottom)
      return {
        card: link.offsetWidth,
        width: postit.offsetWidth,
        lines: Math.round((postit.offsetHeight - inset) / parseFloat(lineHeight)),
      }
    }),
  )

  expect(postits[0].lines).toBe(2)
  expect(postits[1].width).toBe(postits[1].card - 28)
})

test('noir et blanc du projet en cours : la même image, recouverte par CSS (spec §4.1)', async ({
  page,
}) => {
  const requested = new Set<string>()
  page.on('request', (request) => {
    if (request.url().endsWith('.webp')) requested.add(request.url())
  })
  await openTable(page, [
    buildProject({ ...ONGOING, slug: 'en-cours' }),
    buildProject({ slug: 'termine' }),
  ])
  const [ongoing, finished] = [cards(page).first(), cards(page).last()]
  const layers = coverLayers(ongoing)

  await expect(layers).toHaveCount(2)
  await expect(layers.first()).toHaveCSS('filter', 'none')
  await expect(layers.last()).toHaveCSS('filter', 'grayscale(1)')
  await expect(layers.last()).toHaveJSProperty('complete', true)
  expect(await layers.last().evaluate((image: HTMLImageElement) => image.currentSrc)).toBe(
    await layers.first().evaluate((image: HTMLImageElement) => image.currentSrc),
  )
  // Pas de variante en noir et blanc : le projet en cours ne demande qu'un seul fichier.
  expect([...requested].filter((url) => url.includes('/en-cours/'))).toHaveLength(1)

  await expect(coverLayers(finished)).toHaveCount(1)
  await expect(coverLayers(finished)).toHaveCSS('filter', 'none')
})

test('les rubans : trois technologies au plus, icône, nom masqué et infobulle (spec §4.1)', async ({
  page,
}) => {
  const shown = [
    buildTechnology('TypeScript', 'language'),
    buildTechnology('React', 'framework'),
    buildTechnology('Docker', 'infrastructure'),
  ]
  await openTable(page, [
    buildProject({
      technologies: [
        buildTechnology('Figma', 'tool'),
        ...shown,
        buildTechnology('Django', 'framework'),
      ],
    }),
  ])
  const ribbons = cards(page).locator('li')

  await expect(ribbons).toHaveText(shown.map(({ name }) => name))
  for (const [index, { name, icon }] of shown.entries()) {
    const ribbon = ribbons.nth(index)
    await expect(ribbon).toHaveAttribute('title', name)
    await expect(ribbon.locator('img')).toHaveAttribute('src', icon)
    await expect(ribbon.locator('img')).toHaveAttribute('alt', '')
    await expect(ribbon.getByText(name)).toHaveClass('sr-only')
  }
  expect(await Promise.all((await ribbons.all()).map(rotationOf))).toEqual([-1.5, 1, -1.5])
})

test('les rubans d’état : « en cours » en texte, « en ligne » avec son point de 6 px', async ({
  page,
}) => {
  await openTable(page, [
    buildProject({ ...ONGOING, demo_url: 'https://demo.test/projet', technologies: [] }),
  ])
  const ribbons = cards(page).locator('li')
  const [accent] = await resolveAll(page, [['background-color', 'var(--accent)']])

  await expect(ribbons).toHaveText(['en cours', 'en ligne'])
  await expect(ribbons.first().locator('.card-dot')).toHaveCount(0)
  const dot = ribbons.last().locator('.card-dot')
  await expect(dot).toHaveCSS('background-color', accent)
  await expect(dot).toHaveCSS('width', '6px')
  await expect(dot).toHaveCSS('height', '6px')
})

test('à 320 px, la carte simple la plus chargée garde ses rubans dans sa bande (spec §4.1)', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 })
  await openTable(page, TWO_CARDS)

  const overflows = await cards(page)
    .first()
    .locator('.card-ribbons')
    .evaluateAll((lists) =>
      lists.map(
        (list) =>
          list.getBoundingClientRect().right - list.parentElement!.getBoundingClientRect().right,
      ),
    )

  expect(Math.max(...overflows)).toBeLessThanOrEqual(0)
})

test('un projet sans état ne porte aucun ruban d’état', async ({ page }) => {
  await openTable(page, [buildProject()])

  await expect(cards(page).locator('li', { hasText: 'en cours' })).toHaveCount(0)
  await expect(cards(page).locator('li', { hasText: 'en ligne' })).toHaveCount(0)
})

test('la pose vient de l’empreinte du slug, sous la CSP de production, sur un enfant de la cellule', async ({
  page,
}) => {
  await serveUnderCsp(page)
  await openTable(page, [buildProject({ slug: 'portfolio' })])
  const card = cards(page)
  // La pose de `tests/cards.test.ts`, calculée hors de JavaScript.
  const [posed] = await resolveAll(page, [
    ['transform', 'rotate(-0.738deg) translate(-3.264px, -1.56px)'],
  ])

  await expect(pose(card)).toHaveCSS('transform', posed)
  await expect(card).toHaveCSS('transform', 'none')
  await expect(entry(card)).toHaveCSS('transform', 'none')
})

for (const [width, placement] of [
  [1280, 'column'],
  [1200, 'column'],
  [1000, 'column'],
  [1100, 'footer'],
  [600, 'footer'],
] as const) {
  test(`liens de l'auteur, douze cartes à ${width} px : ${placement} (spec §3.4)`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, 'largeurs de bureau : le projet desktop les porte')
    await page.setViewportSize({ ...COLUMN_VIEWPORT, width })
    await openTable(page, PROJECT_SETS.twelveWithShowcase)

    // À 1200 px, 78 px de marge pour une garde de 76 : une mesure qui suivrait la pose basculerait.
    await expectPlacement(page, placement)
  })
}

for (const [name, projects] of [
  ['non marquée', PROJECT_SETS.one],
  ['marquée vitrine', PROJECT_SETS.one.map((project) => ({ ...project, showcase: true }))],
] as const) {
  test(`carte seule, ${name} : la carte seule, jamais la vitrine (spec §4.2, §5.5)`, async ({
    page,
    isMobile,
  }) => {
    if (!isMobile) await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 1100 })
    await openTable(page, projects)

    const box = (await cards(page).boundingBox())!

    if (isMobile) {
      // 80 % des 368 px de la table, centrée.
      expect(box.width).toBeCloseTo(294.4, 1)
      expect(box.x).toBeCloseTo((400 - 294.4) / 2, 1)
      await expectPlacement(page, 'footer')
    } else {
      expect([box.x, box.width]).toEqual([370, 360])
      await expectPlacement(page, 'column')
    }
  })
}

/** Ouvre la page sur un premier échec, « Réessayer » focalisé ; rend le geste qui relance. */
async function openFailed(page: Page): Promise<(answer: Answer) => Promise<void>> {
  const failure = await holdProjects(page)
  await page.goto('/')
  await failure(FAILURES['statut 500'])
  await page.getByRole('button', { name: 'Réessayer' }).focus()
  const retry = await holdProjects(page)
  return async (answer) => {
    await page.keyboard.press('Enter')
    await retry(answer)
    await expect(page.getByRole('main')).not.toHaveAttribute('aria-busy')
  }
}

for (const [name, projects, href] of [
  ['la vitrine', PROJECT_SETS.threeWithShowcase, '/projets/projet-02'],
  ['la première carte', PROJECT_SETS.threeWithoutShowcase, '/projets/projet-02'],
] as const) {
  test(`après une relance réussie au clavier, le focus va sur ${name}`, async ({ page }) => {
    const retry = await openFailed(page)

    await retry(serving(projects))

    const active = cards(page).first()
    await expect(active).toBeFocused()
    await expect(active).toHaveAttribute('href', href)
  })
}

test('après une relance réussie sur une liste vide, le focus n’est posé nulle part', async ({
  page,
}) => {
  const retry = await openFailed(page)

  await retry(serving(PROJECT_SETS.none))

  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true)
})

/**
 * Trois formes, les premières images sans variante que l'API peut servir (issue #168) ; le projet
 * est en cours, pour que la couche noir et blanc ait une raison d'exister.
 */
const COVERLESS: [string, Project['gallery']][] = [
  ['en attente', [buildImage('projet', 'Écran', 'pending')]],
  ['en échec', [buildImage('projet', 'Écran', 'failed')]],
  ['galerie vide', []],
]

for (const [name, gallery] of COVERLESS) {
  test(`couverture sans variante, ${name} : la carte entière, un carré --line, sans image`, async ({
    page,
  }) => {
    await openTable(page, [buildProject({ ...ONGOING, title: 'Atelier', gallery })])
    const card = cards(page)
    const [line] = await resolveAll(page, [['background-color', 'var(--line)']])
    const photo = card.locator('.card-photo')

    await expect(card.getByRole('heading', { name: 'Atelier' })).toBeVisible()
    await expect(card.locator('li').last()).toHaveText('en cours')
    await expect(photo).toHaveCSS('background-color', line)
    expect(
      await photo.evaluate((box: HTMLElement) => box.offsetWidth - box.offsetHeight),
    ).toBe(0)
    await expect(photo.locator('img')).toHaveCount(0)
  })
}

test('rechargée défilée, une page haute d’emblée ouvre l’entête décollée', async ({ page }) => {
  // Allongée avant le montage, rien n'entre dans l'application : la liste arrive trop tard pour que
  // le navigateur restaure tout le défilement.
  await page.addInitScript(() => {
    const sheet = new CSSStyleSheet()
    sheet.replaceSync('body { min-height: 500vh }')
    document.adoptedStyleSheets = [sheet]
  })
  await page.goto('/')
  await scrollThrough(page, 1000)

  await page.reload()

  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(1000)
  await expect(page.getByRole('banner')).toHaveAttribute('data-detached')
})

test('rechargée, la table de douze cartes ouvre l’entête selon le défilement constaté', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  await scrollThrough(page, 1000)

  await page.reload()
  await expect(cards(page)).toHaveCount(12)

  const followsScroll = () =>
    page
      .getByRole('banner')
      .evaluate((header) => window.scrollY > 0 === header.hasAttribute('data-detached'))
  await expect.poll(followsScroll).toBe(true)
})
