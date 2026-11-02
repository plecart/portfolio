/**
 * Les jeux de projets des scénarios (`e2e/projects.ts`) tiennent les règles du glossaire
 * (UBIQUITOUS_LANGUAGE.md, « Projet » et « API publique ») : une table ou une fiche éprouvée sur
 * une donnée que l'API ne peut pas servir prouverait un cas qui n'existe pas.
 *
 * Que les jeux suivent le contrat, `tsc` le prouve : ils sont typés par le module généré.
 */
import { expect, test } from 'vitest'
import { FILES_ORIGIN, PROJECT_SETS, type Project } from '../e2e/projects.ts'

/** Les jeux du brief de #19 (décision 10) : leur taille, et leur nombre de vitrines. */
const EXPECTED_SETS = {
  none: [0, 0],
  one: [1, 0],
  threeWithShowcase: [3, 1],
  threeWithoutShowcase: [3, 0],
  twelveWithShowcase: [12, 1],
  twelveWithoutShowcase: [12, 0],
}

/** Les manquements d'un projet aux règles du glossaire ; vide s'il les tient toutes. */
function glossaryViolations(project: Project): string[] {
  const words = project.summary.split(/[ -]/)
  const files = [
    ...project.technologies.map((technology) => technology.icon),
    ...project.gallery.flatMap((image) => image.variants.map((variant) => variant.url)),
  ]
  const anchors = project.sections.map((section) => section.anchor)
  const cover = project.gallery[0]
  const checks: [string, boolean][] = [
    ['titre de 30 caractères au plus', project.title.length <= 30],
    ['slug en lettres sans accent, chiffres, - et _', /^[A-Za-z0-9_-]{1,50}$/.test(project.slug)],
    ['résumé de 120 caractères au plus', project.summary.length <= 120],
    ['aucun mot du résumé de plus de 20 caractères', words.every((word) => word.length <= 20)],
    ['description non vide', project.description.trim() !== ''],
    ['client de 100 caractères au plus', project.client.length <= 100],
    [
      'liens de 200 caractères au plus',
      [project.repository_url, project.demo_url].every((url) => url.length <= 200),
    ],
    [
      'date de fin absente si et seulement si en cours',
      (project.finished_on === null) === (project.status === 'ongoing'),
    ],
    [
      'date de fin jamais avant le début',
      project.finished_on === null || project.finished_on >= project.started_on,
    ],
    ['une technologie au moins', project.technologies.length >= 1],
    ['nom de technologie de 50 caractères au plus', project.technologies.every((t) => t.name.length <= 50)],
    ['une image au moins', project.gallery.length >= 1],
    [
      'couverture carrée de 1200 px au moins',
      cover !== undefined && cover.width === cover.height && cover.width >= 1200,
    ],
    [
      'légende de 50 caractères au plus, jamais blanche',
      project.gallery.every((image) => image.caption.trim() !== '' && image.caption.length <= 50),
    ],
    [
      'variantes seulement à l’état prêt',
      project.gallery.every((image) => image.state === 'ready' || image.variants.length === 0),
    ],
    ['fichiers sur l’origine réservée', files.every((url) => url.startsWith(`${FILES_ORIGIN}/`))],
    ['ancres uniques dans le projet', new Set(anchors).size === anchors.length],
    [
      'sections bien formées',
      project.sections.every(
        (section) =>
          section.title.length <= 40 &&
          /^[A-Za-z0-9-]+$/.test(section.anchor) &&
          section.body.trim() !== '',
      ),
    ],
  ]
  return checks.filter(([, holds]) => !holds).map(([rule]) => `${project.slug} : ${rule}`)
}

test('les six jeux du brief, chacun de sa taille et avec sa vitrine', () => {
  const shapes = Object.fromEntries(
    Object.entries(PROJECT_SETS).map(([name, projects]) => [
      name,
      [projects.length, projects.filter((project) => project.showcase).length],
    ]),
  )

  expect(shapes).toEqual(EXPECTED_SETS)
})

for (const [name, projects] of Object.entries(PROJECT_SETS)) {
  test(`chaque projet du jeu ${name} tient les règles du glossaire`, () => {
    expect(projects.flatMap(glossaryViolations)).toEqual([])
  })

  test(`le jeu ${name} est trié par slug, sans doublon, comme l'API le sert`, () => {
    const slugs = projects.map((project) => project.slug)

    expect(slugs).toEqual([...new Set(slugs)].sort())
  })
}

test('le jeu de douze varie types, statuts et années, et porte une image en attente', () => {
  const projects = PROJECT_SETS.twelveWithShowcase

  // L'ordre des cartes se trie sur ces champs (spec §1.9) ; une image en attente n'a pas de
  // variante (glossaire, « Image de galerie »), et la carte la rend en carré `--line`.
  expect({
    kinds: new Set(projects.map((project) => project.kind)).size,
    statuses: new Set(projects.map((project) => project.status)).size,
    years: new Set(projects.map((project) => project.started_on.slice(0, 4))).size,
    pending: projects.some((project) =>
      project.gallery.some((image) => image.state === 'pending' && image.variants.length === 0),
    ),
  }).toEqual({ kinds: 3, statuses: 3, years: 12, pending: true })
})
