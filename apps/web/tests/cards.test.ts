/**
 * Les cartes de la table, en logique pure : leur ordre (spec §1.9), les technologies qu'elles
 * montrent (§1.4) et leur pose (§1.3, §4.1).
 */
import { describe, expect, test } from 'vitest'
import { buildProject, type Project } from '../e2e/projects.ts'
import { orderProjects } from '../src/table/cards.ts'

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

  test('situe un projet sans date de fin par sa date de début', () => {
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
