/** L'adresse et les faits d'une fiche (spec §3.2, §4.3, §7 ; issue #170), en logique pure. */
import { expect, test } from 'vitest'
import type { components } from '../src/api/schema.ts'
import {
  isSectionHash,
  projectDates,
  projectFacts,
  projectPath,
  readyImages,
  sectionId,
  slugFromPath,
  splitStack,
  swipeStep,
  visibleSections,
} from '../src/project/project.ts'
import { buildImage, buildProject, buildTechnology, FILES_ORIGIN, ONGOING } from '../e2e/projects.ts'

type Section = components['schemas']['SectionOut']

test.each([
  ['/', null],
  ['/projets/x', 'x'],
  ['/projets/x/', 'x'],
  ['/projets/', null],
  ['/projets/a/b', null],
])('le chemin %s désigne le slug %s', (pathname, slug) => {
  expect(slugFromPath(pathname)).toBe(slug)
})

test('le chemin d’une fiche se relit en son slug', () => {
  expect(slugFromPath(projectPath('atelier'))).toBe('atelier')
})

test('la suite tourne à l’ouest de Greenwich, où un jour lu en heure locale peut changer de mois', () => {
  expect(new Date().getTimezoneOffset()).toBeGreaterThan(0)
})

test.each([
  ['terminé', 'finished', '2025-01-15', '2025-06-30', 'Janvier 2025 – juin 2025'],
  ['archivé', 'archived', '2023-08-01', '2024-02-29', 'Août 2023 – février 2024'],
  ['sur un seul mois', 'finished', '2024-12-31', '2024-12-31', 'Décembre 2024 – décembre 2024'],
] as const)('un projet %s dit son début puis sa fin', (_, status, started_on, finished_on, dates) => {
  expect(projectDates(buildProject({ status, started_on, finished_on }))).toBe(dates)
})

test('un projet en cours dit depuis quand, sans capitale au mois', () => {
  expect(projectDates(buildProject({ ...ONGOING, started_on: '2026-03-01' }))).toBe(
    'Depuis mars 2026',
  )
})

test.each([
  ['personal', 'Perso'],
  ['professional', 'Pro'],
  ['school', 'École'],
] as const)('le type %s se lit %s', (kind, label) => {
  expect(projectFacts(buildProject({ kind })).split(' · ')[0]).toBe(label)
})

test('la ligne de faits : type, dates, client', () => {
  expect(projectFacts(buildProject({ kind: 'professional', client: 'Acme' }))).toBe(
    'Pro · Janvier 2025 – juin 2025 · Acme',
  )
})

test('sans client, le fait disparaît avec son séparateur', () => {
  expect(projectFacts(buildProject({ client: '' }))).toBe('Perso · Janvier 2025 – juin 2025')
})

test('les dates de la ligne de faits suivent le statut', () => {
  expect(projectFacts(buildProject({ ...ONGOING, started_on: '2026-03-01' }))).toBe(
    'Perso · Depuis mars 2026',
  )
})

test('la stack sépare les outils des technologies, l’ordre d’entrée conservé', () => {
  const [figma, react, git, docker] = [
    buildTechnology('Figma', 'tool'),
    buildTechnology('React', 'framework'),
    buildTechnology('Git', 'tool'),
    buildTechnology('Docker', 'infrastructure'),
  ]

  expect(splitStack([figma, react, git, docker])).toEqual({
    technologies: [react, docker],
    tools: [figma, git],
  })
})

test.each([
  ['une liste vide', []],
  ['un seul outil', [buildTechnology('Figma', 'tool')]],
])('la stack tient avec %s', (_, technologies) => {
  const { technologies: others, tools } = splitStack(technologies)

  expect([...others, ...tools]).toEqual(technologies)
})

const section = (anchor: string, body: string): Section => ({ title: anchor, anchor, body })

test.each([
  ['vide', ''],
  ['d’espaces', '   '],
  ['de retours à la ligne', '\n\n  \t\n'],
])('une section au corps %s est omise', (_, body) => {
  const kept = section('gardee', 'Un corps.')

  expect(visibleSections([section('omise', body), kept])).toEqual([kept])
})

test('les sections gardent l’ordre de l’admin', () => {
  const sections = [section('b', 'Deux.'), section('a', 'Un.')]

  expect(visibleSections(sections)).toEqual(sections)
})

test('l’ancre d’une section donne son identifiant et son fragment', () => {
  expect(sectionId('architecture')).toBe('s-architecture')
  expect(isSectionHash(`#${sectionId('architecture')}`)).toBe(true)
})

test.each(['', '#', '#root', '#s', '#section'])('%s ne désigne aucune section', (hash) => {
  expect(isSectionHash(hash)).toBe(false)
})

test('une image prête donne sa légende et ses sources, en largeurs', () => {
  expect(readyImages([buildImage('projet', 'Écran')])).toEqual([
    {
      caption: 'Écran',
      src: `${FILES_ORIGIN}/images/projet/480.webp`,
      srcSet: `${FILES_ORIGIN}/images/projet/480.webp 480w, ${FILES_ORIGIN}/images/projet/960.webp 960w`,
      width: 480,
      height: 480,
    },
  ])
})

test.each(['pending', 'failed'] as const)('une image à l’état %s n’entre pas', (state) => {
  const gallery = [
    buildImage('projet', 'Avant'),
    buildImage('projet', 'Sans variante', state),
    buildImage('projet', 'Après'),
  ]

  expect(readyImages(gallery).map(({ caption }) => caption)).toEqual(['Avant', 'Après'])
})

test('la condition lit les variantes : une image prête sans variante n’entre pas', () => {
  expect(readyImages([{ ...buildImage('projet', 'Écran'), variants: [] }])).toEqual([])
})

test.each([
  ['39 px vers la gauche : rien', -39, 0, 0],
  ['40 px tout juste : rien', -40, 0, 0],
  ['41 px vers la gauche : l’image suivante', -41, 0, 1],
  ['41 px vers la droite : l’image précédente', 41, 0, -1],
  ['plus vertical qu’horizontal : rien', -60, 61, 0],
  ['autant vertical qu’horizontal : rien', -60, -60, 0],
  ['plus horizontal que vertical : l’image suivante', -60, 59, 1],
])('balayage de %s', (_, dx, dy, step) => {
  expect(swipeStep(dx, dy)).toBe(step)
})
