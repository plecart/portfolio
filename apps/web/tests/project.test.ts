/**
 * L'adresse et les faits d'une fiche (spec §3.2, §4.3, §7 ; issue #170), en logique pure ; et la
 * copie de la taille de la galerie que porte la vue des aperçus de lien (#27).
 */
import { readFileSync } from 'node:fs'
import { expect, test } from 'vitest'
import type { components } from '../src/api/schema.ts'
import {
  GALLERY_SIZES,
  isPageFragment,
  isSectionHash,
  projectDates,
  projectFacts,
  projectPath,
  sectionId,
  shownImages,
  slugFromPath,
  splitStack,
  stackButtonName,
  swipeStep,
  visibleSections,
} from '../src/project/project.ts'
import { cardTechnologies } from '../src/table/cards.ts'
import { buildImage, buildProject, buildTechnology, FILES_ORIGIN, ONGOING } from '../e2e/projects.ts'

type GalleryImage = components['schemas']['GalleryImageOut']
type Section = components['schemas']['SectionOut']

/** La vue des aperçus de lien : elle précharge l’image de tête à la taille de la galerie (#27). */
const LINK_PREVIEW = new URL('../../api/content/link_preview.py', import.meta.url)

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

test('les trois premières technologies de la stack sont celles de la carte, dans l’ordre : leurs rubans y volent (spec §4.6)', () => {
  const technologies = [
    buildTechnology('Figma', 'tool'),
    buildTechnology('TypeScript', 'language'),
    buildTechnology('Git', 'tool'),
    buildTechnology('React', 'framework'),
    buildTechnology('Docker', 'infrastructure'),
    buildTechnology('Redis', 'infrastructure'),
  ]

  expect(splitStack(technologies).technologies.slice(0, 3)).toEqual(cardTechnologies(technologies))
})

test.each([
  ['technologies', 1, 'Afficher ou réduire 1 autre technologie'],
  ['technologies', 3, 'Afficher ou réduire les 3 autres technologies'],
  ['tools', 1, 'Afficher ou réduire 1 autre outil'],
  ['tools', 12, 'Afficher ou réduire les 12 autres outils'],
] as const)('le ruban-bouton du groupe %s, %i ruban(s) replié(s) : « %s »', (kind, hidden, name) => {
  expect(stackButtonName(kind, hidden)).toBe(name)
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

const PAGE = 'https://site.test/projets/fiche'

test.each([
  ['une ancre de la page', `${PAGE}#s-a`, PAGE, true],
  ['un fragment vide', `${PAGE}#`, PAGE, true],
  ['une autre ancre, la page sur la sienne', `${PAGE}#s-a`, `${PAGE}#s-b`, true],
  ['la page sans fragment', PAGE, PAGE, false],
  ['une autre requête', `${PAGE}?a=1#x`, PAGE, false],
  ['un autre chemin', 'https://site.test/autre#x', PAGE, false],
  ['une autre origine', 'https://autre.test/projets/fiche#x', PAGE, false],
])('%s', (_, href, page, expected) => {
  expect(isPageFragment(href, page)).toBe(expected)
})

/** Une image de la galerie d'un projet : prête, en attente, en échec. */
const ready = (caption: string) => buildImage('projet', caption)
const pending = (caption: string) => buildImage('projet', caption, 'pending')
const failed = (caption: string) => buildImage('projet', caption, 'failed')

/** Les légendes des images que la fiche montre (`shownImages`). */
const shownCaptions = (gallery: GalleryImage[]) =>
  shownImages(gallery).images.map(({ caption }) => caption)

test('une image montrée donne sa légende et ses sources, en largeurs', () => {
  expect(shownImages([buildImage('projet', 'Écran')]).images).toEqual([
    {
      caption: 'Écran',
      src: `${FILES_ORIGIN}/images/projet/480.webp`,
      srcSet: `${FILES_ORIGIN}/images/projet/480.webp 480w, ${FILES_ORIGIN}/images/projet/960.webp 960w`,
      width: 480,
      height: 480,
    },
  ])
})

test.each<[string, GalleryImage[], string[], boolean]>([
  ['A, B et C prêtes : B puis C', [ready('A'), ready('B'), ready('C')], ['B', 'C'], false],
  ['A et B prêtes : B seule', [ready('A'), ready('B')], ['B'], false],
  ['A seule : la couverture seule', [ready('A')], ['A'], true],
  ['A prête, B en attente : la couverture seule', [ready('A'), pending('B')], ['A'], true],
  ['A prête, B en échec : la couverture seule', [ready('A'), failed('B')], ['A'], true],
  ['A en attente, B prête : B seule', [pending('A'), ready('B')], ['B'], false],
  ['aucune prête : rien', [pending('A'), failed('B')], [], false],
  ['une galerie vide : rien', [], [], false],
])('la couverture A ne se montre que sans autre image prête — %s', (_, gallery, captions, coverOnly) => {
  const shown = shownImages(gallery)

  expect(shown.images.map(({ caption }) => caption)).toEqual(captions)
  expect(shown.coverOnly).toBe(coverOnly)
})

test.each(['pending', 'failed'] as const)('une image à l’état %s n’entre pas', (state) => {
  const gallery = [
    ready('Couverture'),
    ready('Avant'),
    buildImage('projet', 'Sans variante', state),
    ready('Après'),
  ]

  expect(shownCaptions(gallery)).toEqual(['Avant', 'Après'])
})

test.each<[string, GalleryImage[], string[]]>([
  ['une autre image', [ready('A'), { ...ready('B'), variants: [] }], ['A']],
  ['la couverture', [{ ...ready('A'), variants: [] }], []],
])('la condition lit les variantes : %s prête sans variante n’entre pas', (_, gallery, captions) => {
  expect(shownCaptions(gallery)).toEqual(captions)
})

test('l’image de tête se précharge à la taille de la galerie : la vue des aperçus en porte la copie', () => {
  expect(readFileSync(LINK_PREVIEW, 'utf8')).toContain(`"${GALLERY_SIZES}"`)
})

test('la classe de la fiche que pré-rend la vue des aperçus est une règle de la feuille du site', () => {
  const [, name] = readFileSync(LINK_PREVIEW, 'utf8').match(/PRERENDER_CLASS = "([^"]+)"/) ?? []

  expect(readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')).toContain(`.${name} {`)
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
