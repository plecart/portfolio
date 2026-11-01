/**
 * Les cartes de la table, en logique pure : leur ordre (spec §1.9), les technologies qu'elles
 * montrent (§1.4), leur pose (§1.3, §4.1) et l'empreinte qui la tire, leur libellé (§4.1), leurs
 * états (§1.6), leur taille (§4.2, §5.5), leur couverture (§4.1), leur colonne (§3.1) et leur
 * inclinaison (§4.1).
 */
import { describe, expect, test } from 'vitest'
import { buildProject, FILES_ORIGIN, PROJECT_SETS, type Project } from '../e2e/projects.ts'
import {
  cardColumns,
  cardDescription,
  cardLabel,
  cardPose,
  cardSize,
  cardStates,
  cardTechnologies,
  cardTilt,
  coverImage,
  coverSizes,
  fnv1a,
  orderProjects,
  type Technology,
} from '../src/table/cards.ts'

/** Un projet en cours, commencé à `started_on` : sans date de fin, comme l'API le sert. */
function ongoing(slug: string, started_on: string): Project {
  return buildProject({ slug, status: 'ongoing', started_on, finished_on: null })
}

/**
 * Un projet terminé ou archivé, fini à `finished_on` ; commencé avant toutes les dates de ces
 * tests, une fin n'étant jamais avant le début.
 */
function ended(slug: string, finished_on: string, status: Project['status'] = 'finished'): Project {
  return buildProject({ slug, status, started_on: '2000-01-01', finished_on })
}

/** Les slugs des projets, dans l'ordre de la table. */
function orderedSlugs(projects: Project[]): string[] {
  return orderProjects(projects).map((project) => project.slug)
}

describe("l'ordre des cartes", () => {
  test('met la vitrine devant un projet en cours plus récent', () => {
    const showcase = { ...ended('vitrine', '2020-06-01'), showcase: true }
    expect(orderedSlugs([ongoing('en-cours', '2026-01-01'), showcase])).toEqual([
      'vitrine',
      'en-cours',
    ])
  })

  test('range les projets en cours de la date de début la plus récente à la plus ancienne', () => {
    const projects = [
      ongoing('debut-2024', '2024-03-01'),
      ongoing('debut-2026', '2026-01-10'),
      ongoing('debut-2025', '2025-07-20'),
    ]
    expect(orderedSlugs(projects)).toEqual(['debut-2026', 'debut-2025', 'debut-2024'])
  })

  test('range les projets terminés et archivés après tous les projets en cours', () => {
    const projects = [
      ended('fin-2026', '2026-03-01'),
      ended('archive-2026', '2026-02-01', 'archived'),
      ongoing('debut-2019', '2019-01-01'),
    ]
    expect(orderedSlugs(projects)[0]).toBe('debut-2019')
  })

  test('range terminés et archivés ensemble, de la fin la plus récente à la plus ancienne', () => {
    const projects = [
      ended('fin-2024', '2024-11-30'),
      ended('archive-2025', '2025-05-01', 'archived'),
      ended('fin-2026', '2026-01-15'),
    ]
    expect(orderedSlugs(projects)).toEqual(['fin-2026', 'archive-2025', 'fin-2024'])
  })

  test('situe par sa date de début un projet archivé sans date de fin, que la base refuse', () => {
    const undated = buildProject({
      slug: 'debut-2025',
      status: 'archived',
      started_on: '2025-03-01',
      finished_on: null,
    })
    const projects = [ended('fin-2024', '2024-06-01'), undated, ended('fin-2026', '2026-01-01')]
    expect(orderedSlugs(projects)).toEqual(['fin-2026', 'debut-2025', 'fin-2024'])
  })

  test('départage deux projets de même date par slug croissant', () => {
    const projects = [ended('beta', '2025-06-01'), ended('alpha', '2025-06-01')]
    expect(orderedSlugs(projects)).toEqual(['alpha', 'beta'])
  })

  test('range plusieurs vitrines, que la base refuse, entre elles comme les autres projets', () => {
    const showcases = [
      { ...ended('vitrine-terminee', '2026-01-01'), showcase: true },
      { ...ongoing('vitrine-en-cours', '2020-01-01'), showcase: true },
    ]
    expect(orderedSlugs([ongoing('en-cours', '2026-02-01'), ...showcases])).toEqual([
      'vitrine-en-cours',
      'vitrine-terminee',
      'en-cours',
    ])
  })

  test('laisse la liste reçue dans son ordre', () => {
    const projects = [ended('fin-2024', '2024-01-01'), ended('fin-2025', '2025-01-01')]
    orderProjects(projects)
    expect(projects.map((project) => project.slug)).toEqual(['fin-2024', 'fin-2025'])
  })

  test('rend une table vide pour une liste vide', () => {
    expect(orderProjects([])).toEqual([])
  })

  test("range l'entrée A–F du brief en A, B, D, F, C, E, sans la modifier", () => {
    const e = buildProject({
      slug: 'e',
      status: 'archived',
      started_on: '2022-02-01',
      finished_on: null,
    })
    // F, slug « ab », passe avant C à date de fin égale.
    const projects = [
      { ...ended('a', '2024-01-10'), showcase: true },
      ongoing('b', '2026-01-05'),
      ended('c', '2025-06-30'),
      ongoing('d', '2025-03-01'),
      e,
      ended('ab', '2025-06-30'),
    ]
    expect(orderedSlugs(projects)).toEqual(['a', 'b', 'd', 'ab', 'c', 'e'])
    expect(projects.map((project) => project.slug)).toEqual(['a', 'b', 'c', 'd', 'e', 'ab'])
  })
})

/** Une technologie de ce type, nommée `name`. */
function technology(name: string, kind: Technology['kind']): Technology {
  return { name, kind, icon: `${FILES_ORIGIN}/icones/${name}.svg` }
}

/** Les noms des technologies que la carte montre. */
function cardNames(technologies: Technology[]): string[] {
  return cardTechnologies(technologies).map((shown) => shown.name)
}

describe('les technologies de la carte', () => {
  test("montre les trois premières dans l'ordre de l'admin", () => {
    const technologies = [
      technology('react', 'framework'),
      technology('typescript', 'language'),
      technology('docker', 'infrastructure'),
      technology('django', 'framework'),
    ]
    expect(cardNames(technologies)).toEqual(['react', 'typescript', 'docker'])
  })

  test('saute un outil sans le compter', () => {
    const technologies = [
      technology('figma', 'tool'),
      technology('react', 'framework'),
      technology('typescript', 'language'),
      technology('docker', 'infrastructure'),
    ]
    expect(cardNames(technologies)).toEqual(['react', 'typescript', 'docker'])
  })

  test('montre toutes les éligibles quand elles sont moins de trois', () => {
    const technologies = [technology('python', 'language'), technology('git', 'tool')]
    expect(cardNames(technologies)).toEqual(['python'])
  })

  test("ne montre rien quand le projet n'emploie que des outils", () => {
    expect(cardNames([technology('figma', 'tool')])).toEqual([])
  })

  test('joue les trois exemples du brief', () => {
    const figma = technology('Figma', 'tool')
    const docker = technology('Docker', 'infrastructure')
    const all = [
      figma,
      technology('TypeScript', 'language'),
      technology('React', 'framework'),
      technology('Django', 'framework'),
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
    expect(cardStates(ongoing('en-cours', '2026-01-01')).ongoing).toBe(true)
    expect(cardStates(ongoing('en-cours', '2026-01-01')).live).toBe(false)
    expect(cardStates(buildProject({ demo_url: 'https://demo.test' }))).toEqual({
      ongoing: false,
      live: true,
    })
  })

  test.each(['finished', 'archived'] as const)("un projet %s n'est pas en cours", (status) => {
    expect(cardStates(buildProject({ status })).ongoing).toBe(false)
  })
})

describe('le libellé de la carte', () => {
  const titled = (overrides: Partial<Project>) =>
    buildProject({ title: 'Portfolio', summary: 'Un site', ...overrides })

  test('dit le titre puis le résumé, et aucun état absent', () => {
    expect(cardLabel(titled({}))).toBe('Portfolio. Un site.')
  })

  test('ajoute « En cours. » à un projet en cours', () => {
    expect(cardLabel(titled({ status: 'ongoing', finished_on: null }))).toBe(
      'Portfolio. Un site. En cours.',
    )
  })

  test('ajoute « En ligne. » à un projet qui a un lien démo', () => {
    expect(cardLabel(titled({ demo_url: 'https://demo.test' }))).toBe('Portfolio. Un site. En ligne.')
  })

  test('dit les deux états dans l’ordre de la spec', () => {
    expect(
      cardLabel(titled({ status: 'ongoing', finished_on: null, demo_url: 'https://demo.test' })),
    ).toBe('Portfolio. Un site. En cours. En ligne.')
  })

  test.each([
    ['un point', 'Un site.'],
    ['un point d’exclamation', 'Un site !'],
    ['un point d’interrogation', 'Un site ?'],
    ['des points de suspension', 'Un site…'],
  ])('ne redouble pas la ponctuation d’un résumé qui finit par %s', (_, summary) => {
    expect(cardLabel(titled({ summary }))).toBe(`Portfolio. ${summary}`)
  })

  test('ne redouble pas non plus celle d’un titre', () => {
    expect(cardLabel(titled({ title: 'Et après ?' }))).toBe('Et après ? Un site.')
  })
})

describe('la description de la carte', () => {
  test('nomme les technologies que la carte montre, sans les outils', () => {
    const icon = `${FILES_ORIGIN}/icone.svg`
    const technologies: Technology[] = [
      { name: 'Figma', kind: 'tool', icon },
      { name: 'TypeScript', kind: 'language', icon },
      { name: 'React', kind: 'framework', icon },
    ]

    expect(cardDescription(buildProject({ technologies }))).toBe('TypeScript, React')
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

describe("l'inclinaison d'une carte", () => {
  const CELL = { left: 100, top: 200, width: 240, height: 282 }
  const [right, bottom] = [CELL.left + CELL.width, CELL.top + CELL.height]
  const tiltAt = (clientX: number, clientY: number) => cardTilt({ clientX, clientY }, CELL)

  test('au coin haut droit : +6° sur chaque axe', () => {
    expect(tiltAt(right, CELL.top)).toEqual({ rotateX: 6, rotateY: 6 })
  })

  test('au coin bas gauche : −6° sur chaque axe', () => {
    expect(tiltAt(CELL.left, bottom)).toEqual({ rotateX: -6, rotateY: -6 })
  })

  test('au centre : 0°', () => {
    const { rotateX, rotateY } = tiltAt(CELL.left + CELL.width / 2, CELL.top + CELL.height / 2)

    expect(rotateX).toBeCloseTo(0)
    expect(rotateY).toBeCloseTo(0)
  })

  test('chaque axe suit le sien : le haut au milieu ne touche que `rotateX`', () => {
    const { rotateX, rotateY } = tiltAt(CELL.left + CELL.width / 2, CELL.top)

    expect(rotateX).toBe(6)
    expect(rotateY).toBeCloseTo(0)
  })

  test('hors de la cellule, sur un trombone qui la déborde : ±6° au plus', () => {
    expect(tiltAt(CELL.left - 20, CELL.top - 14)).toEqual({ rotateX: 6, rotateY: -6 })
  })
})
