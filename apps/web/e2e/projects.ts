/**
 * Les projets que les scénarios servent à la place de l'API, typés depuis son schéma OpenAPI
 * (`src/api/schema.ts`, `make web-openapi`) : un champ renommé dans le contrat casse leur
 * compilation (brief de #19, décision 10). Leurs règles de contenu — celles du glossaire — sont
 * tenues par `tests/fixtures.test.ts`.
 */
import { basename, join } from 'node:path'
import type { components } from '../src/api/schema.ts'

/** Un projet tel que l'API le sert. */
export type Project = components['schemas']['ProjectOut']

type Technology = components['schemas']['TechnologyOut']
type GalleryImage = components['schemas']['GalleryImageOut']

/**
 * L'origine des fichiers — icônes et variantes —, réservée aux scénarios : ni la page ni l'API, et
 * jamais résolue (`.test`, RFC 2606). Le `test` d'`api.ts` y intercepte toute requête.
 */
export const FILES_ORIGIN = 'https://fichiers.test'

/**
 * Le fichier de `fixtures/` qui répond à une adresse de l'origine des fichiers : la même icône pour
 * toutes les technologies, et les deux WebP carrés — 480 et 960 px de côté, générés une fois par
 * Pillow — pour toutes les variantes.
 *
 * @param pathname Le chemin de l'adresse, par exemple `/images/projet-01/480.webp`.
 */
export function fixturePath(pathname: string): string {
  return join(
    import.meta.dirname,
    'fixtures',
    pathname.endsWith('.svg') ? 'icon.svg' : basename(pathname),
  )
}

/** Une technologie de ce type, servie avec son icône. */
export function buildTechnology(name: string, kind: Technology['kind']): Technology {
  return { name, kind, icon: `${FILES_ORIGIN}/icones/${name.toLowerCase()}.svg` }
}

/** Les technologies que les projets puisent, une par type. */
const TECHNOLOGIES: Technology[] = (
  [
    ['TypeScript', 'language'],
    ['React', 'framework'],
    ['Django', 'framework'],
    ['Docker', 'infrastructure'],
    ['Figma', 'tool'],
  ] as const
).map(([name, kind]) => buildTechnology(name, kind))

/** Une image carrée de 1600 px : prête, avec ses variantes ; en attente ou en échec, sans elles. */
export function buildImage(
  slug: string,
  caption: string,
  state: GalleryImage['state'] = 'ready',
): GalleryImage {
  const variants = [480, 960].map((width) => ({
    url: `${FILES_ORIGIN}/images/${slug}/${width}.webp`,
    width,
    height: width,
  }))
  return { caption, width: 1600, height: 1600, state, variants: state === 'ready' ? variants : [] }
}

/** Les champs d'un projet en cours : sans date de fin, comme l'API le sert. */
export const ONGOING = { status: 'ongoing', finished_on: null } satisfies Partial<Project>

/**
 * Un projet publié complet, valide pour le glossaire.
 *
 * @param overrides Les champs qui remplacent ceux du projet type ; sa couverture prend le slug
 *   surchargé.
 */
export function buildProject(overrides: Partial<Project> = {}): Project {
  const slug = overrides.slug ?? 'projet'
  return {
    slug,
    title: 'Projet',
    summary: 'Un projet du portfolio, de la conception à la mise en ligne.',
    description: 'Le projet, **en Markdown**.\n\n- un point\n- un autre',
    kind: 'personal',
    status: 'finished',
    started_on: '2025-01-15',
    finished_on: '2025-06-30',
    client: '',
    repository_url: '',
    demo_url: '',
    showcase: false,
    technologies: TECHNOLOGIES.slice(0, 1),
    gallery: [buildImage(slug, 'Écran d’accueil')],
    sections: [],
    ...overrides,
  }
}

const KINDS: Project['kind'][] = ['personal', 'professional', 'school']
const STATUSES: Project['status'][] = ['finished', 'ongoing', 'archived']

/**
 * Le i-ième projet d'un jeu : types, statuts, années, technologies, liens et sections varient d'un
 * projet à l'autre, pour l'ordre et le contenu des cartes ; le septième a sa couverture en attente.
 */
function numberedProject(index: number, showcase: boolean): Project {
  const number = String(index + 1).padStart(2, '0')
  const slug = `projet-${number}`
  const status = STATUSES[index % STATUSES.length]
  const year = 2014 + index
  const state = index === 6 ? 'pending' : 'ready'
  const cover = buildImage(slug, `Projet ${number}, vue d’ensemble`, state)
  return buildProject({
    slug,
    title: `Projet ${number}`,
    kind: KINDS[index % KINDS.length],
    status,
    started_on: `${year}-03-01`,
    finished_on: status === 'ongoing' ? null : `${year}-11-15`,
    client: index % 3 === 1 ? 'Client du projet' : '',
    repository_url: index % 2 === 0 ? `https://depot.test/${slug}` : '',
    demo_url: index % 4 === 0 ? `https://demo.test/${slug}` : '',
    showcase,
    technologies: TECHNOLOGIES.slice(index % 4, (index % 4) + 1 + (index % 3)),
    gallery: index % 2 === 0 ? [cover, buildImage(slug, 'Détail de l’interface')] : [cover],
    sections:
      index % 2 === 0
        ? [{ title: 'Architecture', anchor: 'architecture', body: 'Les briques du projet.' }]
        : [],
  })
}

/** Un jeu de `count` projets, triés par slug comme l'API les sert ; la vitrine, si elle y est, en second. */
export function projectSet(count: number, showcase: boolean): Project[] {
  return Array.from({ length: count }, (_, index) => numberedProject(index, showcase && index === 1))
}

/**
 * Les six jeux du brief : aucun projet, un seul — sans vitrine, qui n'existe pas à cette taille
 * (spec §4.2) —, trois et douze, chacun avec et sans vitrine (une au plus, glossaire).
 */
export const PROJECT_SETS = {
  none: projectSet(0, false),
  one: projectSet(1, false),
  threeWithShowcase: projectSet(3, true),
  threeWithoutShowcase: projectSet(3, false),
  twelveWithShowcase: projectSet(12, true),
  twelveWithoutShowcase: projectSet(12, false),
} satisfies Record<string, Project[]>
