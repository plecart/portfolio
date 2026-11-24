/**
 * Les cartes de la table, en logique pure : leur ordre (spec §1.9), les technologies qu'elles
 * montrent (§1.4), leur pose (§1.3, §4.1) et l'empreinte qui la tire, le nom et la description de
 * leur lien (§1.7, §4.1), leurs états (§1.6), leur taille et celle des cadres de chargement (§4.2,
 * §5.1, §5.5), leur couverture (§4.1) et leur colonne (§3.1).
 */
import { describe, expect, test } from 'vitest'
import {
  buildProject,
  buildTechnology,
  FILES_ORIGIN,
  ONGOING,
  PROJECT_SETS,
  type Project,
} from '../e2e/projects.ts'
import {
  cardColumns,
  cardDescription,
  cardNameSuffix,
  cardPose,
  cardSize,
  cardStates,
  cardTechnologies,
  coverImage,
  coverSizes,
  fnv1a,
  frameSizes,
  orderProjects,
  type Technology,
} from '../src/table/cards.ts'

/** Un projet terminé à la position `position`. */
function placed(slug: string, position: number): Project {
  return buildProject({ slug, position })
}

/** Un projet tel que l'API le servait avant les positions : sans la clé `position`. */
function unplaced(slug: string): Project {
  const project: Partial<Project> = buildProject({ slug })
  delete project.position
  return project as Project
}

/** Les slugs des projets, dans l'ordre de la table. */
function orderedSlugs(projects: readonly Project[]): string[] {
  return orderProjects(projects).map((project) => project.slug)
}

describe("l'ordre des cartes", () => {
  test('suit les positions, ni le slug, ni le statut, ni les dates, ni l’ordre reçu', () => {
    const projects = [
      placed('a', 3),
      { ...placed('b', 1), ...ONGOING, started_on: '2020-01-01' },
      placed('c', 2),
    ]
    expect(orderedSlugs(projects)).toEqual(['b', 'c', 'a'])
  })

  test('range la vitrine à sa position, comme les autres projets (spec §1.9)', () => {
    const projects = [placed('a', 1), placed('b', 2), { ...placed('vitrine', 3), showcase: true }]
    expect(orderedSlugs(projects)).toEqual(['a', 'b', 'vitrine'])
  })

  test('garde l’ordre reçu à position égale : celui de la saisie, que l’API sert', () => {
    expect(orderedSlugs([placed('zeta', 2), placed('beta', 2), placed('alpha', 1)])).toEqual([
      'alpha',
      'zeta',
      'beta',
    ])
  })

  test('garde l’ordre reçu d’une liste sans positions, que le cache de l’API sert encore au déploiement', () => {
    expect(orderedSlugs(['zeta', 'alpha', 'beta'].map(unplaced))).toEqual([
      'zeta',
      'alpha',
      'beta',
    ])
  })

  test('laisse la liste reçue dans son ordre', () => {
    const projects = [placed('second', 2), placed('premier', 1)]
    orderProjects(projects)
    expect(projects.map((project) => project.slug)).toEqual(['second', 'premier'])
  })

  test('rend une table vide pour une liste vide', () => {
    expect(orderProjects([])).toEqual([])
  })
})

/** Les noms des technologies que la carte montre. */
function cardNames(technologies: Technology[]): string[] {
  return cardTechnologies(technologies).map((shown) => shown.name)
}

describe('les technologies de la carte', () => {
  test("montre les trois premières dans l'ordre de l'admin", () => {
    const technologies = [
      buildTechnology('react', 'framework'),
      buildTechnology('typescript', 'language'),
      buildTechnology('docker', 'infrastructure'),
      buildTechnology('django', 'framework'),
    ]
    expect(cardNames(technologies)).toEqual(['react', 'typescript', 'docker'])
  })

  test('saute un outil sans le compter', () => {
    const technologies = [
      buildTechnology('figma', 'tool'),
      buildTechnology('react', 'framework'),
      buildTechnology('typescript', 'language'),
      buildTechnology('docker', 'infrastructure'),
    ]
    expect(cardNames(technologies)).toEqual(['react', 'typescript', 'docker'])
  })

  test('montre toutes les éligibles quand elles sont moins de trois', () => {
    const technologies = [buildTechnology('python', 'language'), buildTechnology('git', 'tool')]
    expect(cardNames(technologies)).toEqual(['python'])
  })

  test("ne montre rien quand le projet n'emploie que des outils", () => {
    expect(cardNames([buildTechnology('figma', 'tool')])).toEqual([])
  })

  test('joue les trois exemples du brief', () => {
    const figma = buildTechnology('Figma', 'tool')
    const docker = buildTechnology('Docker', 'infrastructure')
    const all = [
      figma,
      buildTechnology('TypeScript', 'language'),
      buildTechnology('React', 'framework'),
      buildTechnology('Django', 'framework'),
      docker,
    ]
    expect(cardNames(all)).toEqual(['TypeScript', 'React', 'Django'])
    expect(cardNames([figma, docker])).toEqual(['Docker'])
    expect(cardNames([figma])).toEqual([])
  })
})

describe("l'empreinte", () => {
  test('rend les vecteurs de référence FNV-1a 32 bits', () => {
    expect(fnv1a('')).toBe(0x811c9dc5)
    expect(fnv1a('a')).toBe(0xe40c292c)
  })
})

/** Les slugs d'une table de 200 projets. */
const SLUGS = Array.from({ length: 200 }, (_, index) => `projet-${index}`)

/** Les slugs des fixtures de l'e2e, chacun une fois. */
const FIXTURE_SLUGS = [
  ...new Set(Object.values(PROJECT_SETS).flatMap((set) => set.map((project) => project.slug))),
]

/** Les slugs dont la pose doit tenir ses bornes : ceux des fixtures, puis 1000 engendrés. */
const BOUNDED_SLUGS = [
  ...FIXTURE_SLUGS,
  ...Array.from({ length: 1000 }, (_, index) => `engendre-${index}`),
]

/** Le plus grand écart à zéro parmi ces valeurs. */
function largest(values: number[]): number {
  return Math.max(...values.map(Math.abs))
}

describe('la pose de la carte', () => {
  test("reste la même d'une visite à l'autre", () => {
    expect(cardPose('portfolio')).toEqual(cardPose('portfolio'))
  })

  test("tire la pose du prototype de l'empreinte FNV-1a du slug", () => {
    // Calculée hors de JavaScript, par une empreinte FNV-1a 32 bits de référence en Python.
    expect(cardPose('portfolio')).toEqual({ rotation: -0.738, dx: -3.2640000000000002, dy: -1.56 })
    // Les trois empreintes de `projet-0` ont le bit de signe à 1 : l'empreinte reste non signée.
    expect(cardPose('projet-0')).toEqual({
      rotation: -0.9180000000000001,
      dx: -0.04800000000000004,
      dy: -1.7520000000000002,
    })
  })

  // Population figée : sur 1000 slugs projet-N, 32 paires de poses coïncident (mesuré le
  // 2026-10-27) ; l'unicité n'est pas une propriété de la pose.
  test("varie d'un projet à l'autre", () => {
    const poses = new Set(SLUGS.map((slug) => JSON.stringify(cardPose(slug))))
    expect(poses.size).toBe(SLUGS.length)
  })

  test('tourne différemment au moins deux cartes des fixtures', () => {
    const rotations = new Set(FIXTURE_SLUGS.map((slug) => cardPose(slug).rotation))
    expect(rotations.size).toBeGreaterThanOrEqual(2)
  })

  test("tourne de 3° au plus, dans un sens ou dans l'autre", () => {
    expect(largest(BOUNDED_SLUGS.map((slug) => cardPose(slug).rotation))).toBeLessThanOrEqual(3)
  })

  test('se décale de 6 px au plus sur chaque axe', () => {
    const offsets = BOUNDED_SLUGS.map(cardPose).flatMap(({ dx, dy }) => [dx, dy])
    expect(largest(offsets)).toBeLessThanOrEqual(6)
  })

  // Des slugs dont l'empreinte tombe sur une borne, trouvés par la même empreinte de référence.
  test.each([
    ['projet-217', 'rotation', 3],
    ['projet-2360', 'rotation', -3],
    ['projet-277', 'dx', 6],
    ['projet-341', 'dx', -6],
  ] as const)('atteint ses bornes : %s, %s = %d', (slug, axis, bound) => {
    expect(cardPose(slug)[axis]).toBe(bound)
  })
})

describe('les états de la carte', () => {
  test('un projet sans statut en cours ni lien démo ne porte aucun état', () => {
    expect(cardStates(buildProject())).toEqual({ ongoing: false, live: false })
  })

  test('« en cours » suit le statut, « en ligne » le lien démo, indépendants', () => {
    expect(cardStates(buildProject(ONGOING))).toEqual({ ongoing: true, live: false })
    expect(cardStates(buildProject({ demo_url: 'https://demo.test' }))).toEqual({
      ongoing: false,
      live: true,
    })
  })

  test.each(['finished', 'archived'] as const)("un projet %s n'est pas en cours", (status) => {
    expect(cardStates(buildProject({ status })).ongoing).toBe(false)
  })
})

describe('le nom de la carte', () => {
  const titled = (overrides: Partial<Project>) => buildProject({ title: 'Portfolio', ...overrides })

  test('n’ajoute rien au titre, pas même un point, sans état', () => {
    expect(cardNameSuffix(titled({}))).toBe('')
  })

  test('ajoute le point du titre et « En cours. » à un projet en cours', () => {
    expect(cardNameSuffix(titled(ONGOING))).toBe('. En cours.')
  })

  test('ajoute le point du titre et « En ligne. » à un projet qui a un lien démo', () => {
    expect(cardNameSuffix(titled({ demo_url: 'https://demo.test' }))).toBe('. En ligne.')
  })

  test('dit les deux états dans l’ordre de la spec', () => {
    expect(cardNameSuffix(titled({ ...ONGOING, demo_url: 'https://demo.test' }))).toBe(
      '. En cours. En ligne.',
    )
  })

  test('ne redouble pas la ponctuation d’un titre', () => {
    expect(cardNameSuffix(titled({ title: 'Et après ?', demo_url: 'https://demo.test' }))).toBe(
      'En ligne.',
    )
  })
})

describe('la description de la carte', () => {
  test('dit le résumé, puis nomme les technologies que la carte montre, sans les outils', () => {
    const technologies = [
      buildTechnology('Figma', 'tool'),
      buildTechnology('TypeScript', 'language'),
      buildTechnology('React', 'framework'),
    ]

    expect(cardDescription(buildProject({ summary: 'Un site', technologies }))).toBe(
      'Un site. TypeScript, React',
    )
  })

  test('s’arrête au résumé quand la carte ne montre aucune technologie', () => {
    expect(cardDescription(buildProject({ summary: 'Un site', technologies: [] }))).toBe('Un site.')
  })

  test.each([
    ['un point', 'Un site.'],
    ['un point d’exclamation', 'Un site !'],
    ['un point d’interrogation', 'Un site ?'],
    ['des points de suspension', 'Un site…'],
  ])('ne redouble pas la ponctuation d’un résumé qui finit par %s', (_, summary) => {
    expect(cardDescription(buildProject({ summary, technologies: [] }))).toBe(summary)
  })
})

describe('la taille de la carte', () => {
  test('une carte parmi d’autres est simple', () => {
    expect(cardSize(buildProject(), 3)).toBe('simple')
  })

  test('le projet vitrine, parmi d’autres, a la carte vitrine', () => {
    expect(cardSize(buildProject({ showcase: true }), 3)).toBe('showcase')
  })

  test.each([false, true])('un projet seul a la carte seule, vitrine : %s', (showcase) => {
    expect(cardSize(buildProject({ showcase }), 1)).toBe('solo')
  })
})

describe('la taille des cadres de chargement', () => {
  test.each([
    [1, ['solo']],
    [2, ['showcase', 'simple']],
    [3, ['showcase', 'simple', 'simple']],
  ] as const)('%d cadre(s) prennent la taille des cartes qu’ils annoncent : %j', (count, sizes) => {
    expect(frameSizes(count)).toEqual(sizes)
  })
})

describe('la couverture de la carte', () => {
  const image = (state: 'ready' | 'pending' | 'failed', widths: number[]) => ({
    caption: 'Écran',
    width: 1600,
    height: 1600,
    state,
    variants: widths.map((width) => ({ url: `${FILES_ORIGIN}/${width}.webp`, width, height: width })),
  })

  test('décrit chaque variante de la première image, en largeurs', () => {
    expect(coverImage(buildProject({ gallery: [image('ready', [480, 960])] }))).toEqual({
      src: `${FILES_ORIGIN}/480.webp`,
      srcSet: `${FILES_ORIGIN}/480.webp 480w, ${FILES_ORIGIN}/960.webp 960w`,
      width: 480,
      height: 480,
    })
  })

  test('ne lit que la première image de la galerie', () => {
    const gallery = [image('pending', []), image('ready', [480])]

    expect(coverImage(buildProject({ gallery }))).toBeNull()
  })

  test.each([
    ['en attente', [image('pending', [])]],
    ['en échec', [image('failed', [])]],
    ['une galerie vide', []],
  ])('rien à montrer : %s', (_, gallery) => {
    expect(coverImage(buildProject({ gallery }))).toBeNull()
  })

  // La condition lit les variantes, jamais l'état : une image prête sans variante ne se rend pas.
  test('rien à montrer non plus sans variante, même à l’état prêt', () => {
    expect(coverImage(buildProject({ gallery: [image('ready', [])] }))).toBeNull()
  })

  test.each([
    ['simple', '(min-width: 600px) 220px, calc((100vw - 48px) / 2 - 16px)'],
    ['showcase', '(min-width: 600px) 480px, calc(100vw - 56px)'],
    ['solo', '(min-width: 600px) 340px, calc((100vw - 32px) * 0.8 - 16px)'],
  ] as const)('annonce la largeur de la photo du tableau de §4.1 — %s', (size, sizes) => {
    expect(coverSizes(size)).toBe(sizes)
  })
})

describe("l'indice de colonne d'une carte", () => {
  // Spec §3.1 : à 1280 px, 118 px de marge, pistes de 240 px et gouttière de 28 px.
  const STEP = 240 + 28
  const column = (index: number) => 118 + index * STEP

  test('se compte depuis la première colonne, au pas des pistes', () => {
    expect(cardColumns([0, 1, 2, 3].map(column), STEP)).toEqual([0, 1, 2, 3])
  })

  test('une vitrine compte pour ses deux colonnes : la carte voisine garde sa vraie colonne', () => {
    expect(cardColumns([column(0), column(2), column(3)], STEP)).toEqual([0, 2, 3])
  })

  test('tolère un bord fractionnaire', () => {
    expect(cardColumns([16, 207.8, 16.2], 192)).toEqual([0, 1, 0])
  })
})
