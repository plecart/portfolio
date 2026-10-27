/**
 * Les cartes de la table, en logique pure : leur ordre (spec §1.9), les technologies qu'elles
 * montrent (§1.4) et leur pose (§1.3, §4.1).
 */
import { describe, expect, test } from 'vitest'
import { buildProject, FILES_ORIGIN, type Project } from '../e2e/projects.ts'
import { cardPose, cardTechnologies, orderProjects, type Technology } from '../src/table/cards.ts'

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
})

/** Les slugs d'une table de 200 projets. */
const SLUGS = Array.from({ length: 200 }, (_, index) => `projet-${index}`)

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

  test("varie d'un projet à l'autre", () => {
    const poses = new Set(SLUGS.map((slug) => JSON.stringify(cardPose(slug))))
    expect(poses.size).toBe(SLUGS.length)
  })

  test("tourne de 3° au plus, dans un sens ou dans l'autre", () => {
    expect(largest(SLUGS.map((slug) => cardPose(slug).rotation))).toBeLessThanOrEqual(3)
  })

  test('se décale de 6 px au plus sur chaque axe', () => {
    const offsets = SLUGS.map(cardPose).flatMap(({ dx, dy }) => [dx, dy])
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
