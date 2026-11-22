/**
 * Les cartes de la table, en logique pure : leur ordre (spec §1.9), les technologies qu'elles
 * montrent (§1.4), leur pose (§1.3, §4.1), leurs états, le nom et la description de leur lien
 * (§1.6, §1.7, §4.1), leur taille et celle des cadres de chargement qui les annoncent (§4.2, §5.1,
 * §5.5), leur couverture (§4.1) et leur colonne (§3.1). Les projets entrent tels que l'API
 * les sert.
 *
 * Typé depuis le schéma, et non par `api/projects.ts` : ce module-là lit `import.meta.env`, que
 * les tests, compilés sans les types de Vite (`tsconfig.node.json`), ne connaissent pas.
 */
import type { components } from '../api/schema.ts'
import { BREAKPOINT } from '../chrome/author-links-placement.ts'
import { strings } from '../strings.ts'

type Project = components['schemas']['ProjectOut']
type Variant = components['schemas']['VariantOut']

/** Une technologie qu'un projet emploie, telle que l'API la sert. */
export type Technology = components['schemas']['TechnologyOut']

/** Les trois tailles de carte (spec §4.1) : une parmi d'autres, la vitrine, ou seule à table. */
export type CardSize = 'simple' | 'showcase' | 'solo'

/**
 * Le nombre de cadres que le chargement pose (spec §5.1). Il suit le nombre de projets publiés en
 * production, pour que les cadres annoncent la table qui les remplace : une PR de la voie courte de
 * `cycle-pr` le met à jour après chaque fiche publiée. Un écart ne casse rien — une finition,
 * jamais une condition de publication : ajouter un projet ne demande jamais de toucher au code
 * (cadrage §1).
 */
export const LOADING_FRAME_COUNT = 3

/** Les types de technologie qu'une carte montre (spec §1.4) : les outils restent sur la fiche. */
const CARD_KINDS: readonly Technology['kind'][] = ['language', 'framework', 'infrastructure']

/** Le nombre de technologies qu'une carte montre au plus (spec §1.4). */
const CARD_TECHNOLOGY_COUNT = 3

/**
 * L'écart de rotation d'une carte au plus, en degrés, de part et d'autre de 0 (spec §1.3, §4.1).
 */
const MAX_ROTATION = 3

/** Le décalage d'une carte au plus sur chaque axe, en px, de part et d'autre de 0 (spec §4.1). */
const MAX_OFFSET = 6

/** Le nombre de pas d'un écart, entre ses deux bornes comprises (prototype retenu). */
const JITTER_STEPS = 1000

/** Les deux constantes de FNV-1a sur 32 bits : la valeur de départ et le nombre premier. */
const FNV_OFFSET_BASIS = 2166136261
const FNV_PRIME = 16777619

/**
 * La largeur de la photo par taille de carte (spec §4.1) : mobile, carte moins ses deux cadres ;
 * bureau, en px.
 */
const COVER_WIDTHS: Record<CardSize, { mobile: string; desktop: string }> = {
  simple: { mobile: 'calc((100vw - 48px) / 2 - 16px)', desktop: '220px' },
  showcase: { mobile: 'calc(100vw - 56px)', desktop: '480px' },
  solo: { mobile: 'calc((100vw - 32px) * 0.8 - 16px)', desktop: '340px' },
}

/** La ponctuation qui finit déjà une phrase. */
const SENTENCE_END = /[.!?…]$/

/** Compare deux chaînes par unités de code — dates ISO, slugs —, sans dépendre de la locale. */
function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

/**
 * La date qui situe un projet dans son groupe : sa fin, à défaut son début. Un projet en cours n'a
 * pas de fin (contrat de `ProjectOut`) : il se situe par son début.
 */
function datedOn(project: Project): string {
  return project.finished_on ?? project.started_on
}

/**
 * L'ordre de la table (spec §1.9) : la vitrine, puis les projets terminés et archivés ensemble,
 * puis les projets en cours, chaque groupe du plus récent au plus ancien, et à date égale par slug
 * croissant. Le slug étant unique, l'ordre est total.
 */
function compareProjects(a: Project, b: Project): number {
  return (
    Number(b.showcase) - Number(a.showcase) ||
    Number(a.status === 'ongoing') - Number(b.status === 'ongoing') ||
    compareText(datedOn(b), datedOn(a)) ||
    compareText(a.slug, b.slug)
  )
}

/**
 * Les projets dans l'ordre de la table.
 *
 * Plusieurs vitrines — que la base refuse — passent toutes en tête, rangées entre elles comme les
 * autres projets.
 *
 * @param projects Les projets, dans l'ordre de l'API ; la liste n'est pas modifiée.
 * @returns Une nouvelle liste, ordonnée.
 */
export function orderProjects(projects: readonly Project[]): Project[] {
  return [...projects].sort(compareProjects)
}

/**
 * Les technologies que la carte d'un projet montre : les trois premières de type langage,
 * framework ou infra, dans l'ordre de l'admin ; moins s'il en a moins, jamais un outil.
 *
 * @param technologies Les technologies du projet, dans l'ordre de l'admin.
 */
export function cardTechnologies(technologies: readonly Technology[]): Technology[] {
  return technologies
    .filter((technology) => CARD_KINDS.includes(technology.kind))
    .slice(0, CARD_TECHNOLOGY_COUNT)
}

/**
 * L'empreinte FNV-1a sur 32 bits d'un texte, par unité de code UTF-16 — l'octet lui-même pour un
 * slug, ASCII —, en entier non signé.
 */
export function fnv1a(text: string): number {
  let hash = FNV_OFFSET_BASIS
  for (let index = 0; index < text.length; index++) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, FNV_PRIME)
  }
  return hash >>> 0
}

/** Un écart tiré de l'empreinte de `seed`, dans [−amplitude, +amplitude], bornes comprises. */
function jitter(seed: string, amplitude: number): number {
  return (((fnv1a(seed) % (JITTER_STEPS + 1)) / JITTER_STEPS) * 2 - 1) * amplitude
}

/**
 * La pose d'une carte sur la table (spec §1.3, §4.1) : une rotation et un décalage tirés de
 * l'empreinte de son slug, identiques à chaque visite. Valeurs brutes, sans arrondi.
 *
 * @returns La rotation en degrés, dans ±3 ; le décalage `dx`, `dy` en px, dans ±6 sur chaque axe.
 */
export function cardPose(slug: string): { rotation: number; dx: number; dy: number } {
  return {
    rotation: jitter(`${slug}:r`, MAX_ROTATION),
    dx: jitter(`${slug}:x`, MAX_OFFSET),
    dy: jitter(`${slug}:y`, MAX_OFFSET),
  }
}

/**
 * Les deux états d'un projet, indépendants (spec §1.6) : « en cours » suit son statut, « en ligne »
 * son lien démo, chaîne vide quand il n'en a pas.
 */
export function cardStates(project: Project): { ongoing: boolean; live: boolean } {
  return { ongoing: project.status === 'ongoing', live: project.demo_url !== '' }
}

/** Un texte en phrase : un point à la fin, sauf s'il finit déjà une phrase. */
function sentence(text: string): string {
  return SENTENCE_END.test(text) ? text : `${text}.`
}

/**
 * Ce que le nom du lien d'une carte, « Titre. En cours. En ligne. », ajoute à son titre : le point
 * du titre, s'il n'en finit pas déjà une phrase, puis les états présents ; rien sans état. Le résumé
 * est dans sa description.
 */
export function cardNameSuffix(project: Project): string {
  const { ongoing, live } = cardStates(project)
  const states = [...(ongoing ? [strings.stateOngoing] : []), ...(live ? [strings.stateLive] : [])]
  if (states.length === 0) return ''
  const titleEnd = sentence(project.title).slice(project.title.length)
  return [titleEnd, ...states.map(sentence)].filter(Boolean).join(' ')
}

/** La description du lien d'une carte : son résumé, puis ses technologies (spec §1.4, §1.7). */
export function cardDescription(project: Project): string {
  const technologies = cardTechnologies(project.technologies).map(({ name }) => name)
  return [sentence(project.summary), technologies.join(', ')].filter(Boolean).join(' ')
}

/**
 * La taille d'une cellule de la table, carte ou cadre de chargement : la vitrine n'existe pas quand
 * la table n'a qu'une cellule (spec §4.2, §5.5).
 *
 * @param showcase La cellule tient le rôle de la vitrine.
 * @param count Le nombre de cellules de la table.
 */
function cellSize(showcase: boolean, count: number): CardSize {
  if (count === 1) return 'solo'
  return showcase ? 'showcase' : 'simple'
}

/**
 * La taille de la carte d'un projet, par la règle des cellules (`cellSize`).
 *
 * @param project Le projet.
 * @param count Le nombre de cartes de la table.
 */
export function cardSize(project: Project, count: number): CardSize {
  return cellSize(project.showcase, count)
}

/**
 * La taille de chaque cadre de chargement (spec §5.1) : celle de la carte qu'il annonce, par la
 * règle des cellules (`cellSize`), le premier tenant le rôle de la vitrine, que la table met en
 * tête (§1.9, §5.5). Sans projet vitrine, le cadre double laisse place à deux cartes simples
 * (§5.1).
 *
 * @param count Le nombre de cadres.
 * @returns Une taille par cadre, dans l'ordre de la table.
 */
export function frameSizes(count: number): CardSize[] {
  return Array.from({ length: count }, (_, index) => cellSize(index === 0, count))
}

/**
 * Ce qu'une image du projet demande à son `<img>`.
 *
 * La condition lit les variantes, jamais l'état : une image en attente ou en échec n'en a aucune.
 *
 * @param variants Les variantes de l'image.
 * @returns `src`, `srcSet` et les dimensions de la première variante ; `null` sans variante.
 */
export function imageSources(
  variants: readonly Variant[],
): { src: string; srcSet: string; width: number; height: number } | null {
  if (variants.length === 0) return null
  const [{ url, width, height }] = variants
  const srcSet = variants.map((variant) => `${variant.url} ${variant.width}w`).join(', ')
  return { src: url, srcSet, width, height }
}

/**
 * L'image de couverture d'un projet : la première de sa galerie (spec §4.1).
 *
 * @returns Ses sources (`imageSources`) ; `null` si elle n'en a pas, ou s'il n'y en a aucune.
 */
export function coverImage(project: Project) {
  return imageSources(project.gallery[0]?.variants ?? [])
}

/** L'attribut `sizes` de la photo d'une carte (spec §4.1) : sa largeur de part et d'autre de 600 px. */
export function coverSizes(size: CardSize): string {
  const { mobile, desktop } = COVER_WIDTHS[size]
  return `(min-width: ${BREAKPOINT}px) ${desktop}, ${mobile}`
}

/**
 * L'indice de colonne de chaque cellule de la table (spec §3.1) : l'écart de son bord gauche à celui
 * de la première colonne, compté en pas de grille. Le rang parmi les bords gauches ne suffirait pas :
 * une vitrine en tête couvre deux colonnes, et aucune carte n'y commence la seconde.
 *
 * @param lefts Le bord gauche de chaque cellule, en px ; la première colonne en porte au moins un,
 *   la grille se remplissant depuis elle.
 * @param step Une piste et sa gouttière, en px.
 */
export function cardColumns(lefts: readonly number[], step: number): number[] {
  const first = Math.min(...lefts)
  return lefts.map((left) => Math.round((left - first) / step))
}
