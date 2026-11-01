/**
 * Les cartes de la table, en logique pure : leur ordre (spec §1.9), les technologies qu'elles
 * montrent (§1.4), leur pose (§1.3, §4.1), leurs états et leur libellé (§1.6, §4.1), leur taille
 * (§4.2, §5.5), leur couverture (§4.1), leur colonne (§3.1) et leur inclinaison (§4.1). Les projets
 * entrent tels que l'API les sert, rien n'est lu ailleurs.
 *
 * Typé depuis le schéma, et non par `api/projects.ts` : ce module-là lit `import.meta.env`, que
 * les tests, compilés sans les types de Vite (`tsconfig.node.json`), ne connaissent pas.
 */
import type { components } from '../api/schema.ts'
import { BREAKPOINT } from '../chrome/author-links-placement.ts'
import { strings } from '../strings.ts'

type Project = components['schemas']['ProjectOut']

/** Une technologie qu'un projet emploie, telle que l'API la sert. */
export type Technology = components['schemas']['TechnologyOut']

/** Les trois tailles de carte (spec §4.1) : une parmi d'autres, la vitrine, ou seule à table. */
export type CardSize = 'simple' | 'showcase' | 'solo'

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

/** L'inclinaison d'une carte au plus sur chaque axe, en degrés, de part et d'autre de 0 (spec §4.1). */
const MAX_TILT = 6

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
 * L'ordre de la table (spec §1.9) : la vitrine, puis les projets en cours, puis les autres —
 * terminés et archivés ensemble —, chaque groupe du plus récent au plus ancien, et à date égale
 * par slug croissant. Le slug étant unique, l'ordre est total.
 */
function compareProjects(a: Project, b: Project): number {
  return (
    Number(b.showcase) - Number(a.showcase) ||
    Number(b.status === 'ongoing') - Number(a.status === 'ongoing') ||
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
 * Le libellé du lien d'une carte (spec §4.1) : « Titre. Résumé. En cours. En ligne. », les états
 * présents seulement.
 */
export function cardLabel(project: Project): string {
  const { ongoing, live } = cardStates(project)
  return [
    project.title,
    project.summary,
    ...(ongoing ? [strings.stateOngoing] : []),
    ...(live ? [strings.stateLive] : []),
  ]
    .map(sentence)
    .join(' ')
}

/** La description du lien d'une carte : le nom de ses technologies (spec §1.4). */
export function cardDescription(project: Project): string {
  return cardTechnologies(project.technologies)
    .map((technology) => technology.name)
    .join(', ')
}

/**
 * La taille de la carte d'un projet : la vitrine n'existe pas quand la table n'a qu'une carte (spec
 * §4.2, §5.5).
 *
 * @param project Le projet.
 * @param count Le nombre de cartes de la table.
 */
export function cardSize(project: Project, count: number): CardSize {
  if (count === 1) return 'solo'
  return project.showcase ? 'showcase' : 'simple'
}

/**
 * Ce que l'image de couverture d'un projet demande à son `<img>` : la première image de la galerie,
 * par ses variantes (spec §4.1).
 *
 * La condition lit les variantes, jamais l'état : une couverture en attente, en échec ou absente
 * n'en a aucune.
 *
 * @returns `src`, `srcSet` et les dimensions de la première variante ; `null` sans variante.
 */
export function coverImage(
  project: Project,
): { src: string; srcSet: string; width: number; height: number } | null {
  const variants = project.gallery[0]?.variants ?? []
  if (variants.length === 0) return null
  const [{ url, width, height }] = variants
  const srcSet = variants.map((variant) => `${variant.url} ${variant.width}w`).join(', ')
  return { src: url, srcSet, width, height }
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

/** La position d'un point sur une longueur, de −1 à 1 depuis son milieu, bornée à ses extrémités. */
function fromMiddle(offset: number, length: number): number {
  return Math.max(-1, Math.min(1, (2 * offset) / length - 1))
}

/**
 * L'inclinaison d'une carte sous le pointeur (spec §4.1) : +6° sur chaque axe au coin haut droit de
 * la cellule, 0° en son centre. Le trombone et le post-it débordent de la cellule : un pointeur posé
 * sur eux reste borné à ±6°.
 *
 * @param pointer La position du pointeur, en px depuis la fenêtre.
 * @param cell La boîte de la cellule, immobile sous la carte qui bouge.
 * @returns Les rotations `rotateX` et `rotateY`, en degrés.
 */
export function cardTilt(
  { clientX, clientY }: { clientX: number; clientY: number },
  { left, top, width, height }: { left: number; top: number; width: number; height: number },
): { rotateX: number; rotateY: number } {
  return {
    rotateX: -fromMiddle(clientY - top, height) * MAX_TILT,
    rotateY: fromMiddle(clientX - left, width) * MAX_TILT,
  }
}
