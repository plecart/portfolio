/**
 * L'adresse d'une fiche (spec §3.2), ses faits, sa stack, ses sections (§4.3, §7) et sa galerie
 * (§4.4), en logique pure. Les projets entrent tels que l'API les sert ; typé depuis le schéma pour
 * la raison que donne `table/cards.ts`.
 */
import type { components } from '../api/schema.ts'
import { BREAKPOINT } from '../chrome/author-links-placement.ts'
import { strings } from '../strings.ts'
import { imageSources, type Technology } from '../table/cards.ts'

type GalleryImage = components['schemas']['GalleryImageOut']
type Project = components['schemas']['ProjectOut']
type Section = components['schemas']['SectionOut']

/** Le chemin d'une fiche, avec ou sans barre finale : un seul segment après `/projets/`. */
const PROJECT_PATH = /^\/projets\/([^/]+)\/?$/

/** Le début de l'identifiant d'une section (spec §4.3). */
const SECTION_ID_PREFIX = 's-'

/** Un jour sans heure de l'API se lit à minuit UTC : relu ailleurs, il changerait de mois. */
const MONTH_YEAR = new Intl.DateTimeFormat('fr-FR', {
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
})

/** Le type d'un projet, tel que la ligne de faits le dit (spec §7). */
const KIND_LABELS: Record<Project['kind'], string> = {
  personal: strings.kindPersonal,
  professional: strings.kindProfessional,
  school: strings.kindSchool,
}

const FACT_SEPARATOR = ' · '
const DATE_SEPARATOR = ' – '

/** Ce qu'un balayage doit dépasser en horizontal, en px, pour changer d'image (spec §4.4). */
const SWIPE_THRESHOLD = 40

/**
 * L'attribut `sizes` d'une image de galerie (spec §3.2) : `--photo` dès 600 px, recopiée de
 * `project.css` car `sizes` ne lit pas les propriétés CSS, sinon le panneau moins ses marges de 8 px.
 */
export const GALLERY_SIZES = [
  `(min-width: ${BREAKPOINT}px) min(100vh - 96px, 660px, (100vw - 92px) / 2)`,
  'calc(100vw - 16px)',
].join(', ')

/**
 * Le chemin de la fiche d'un projet.
 *
 * @param slug Le slug du projet.
 * @returns `/projets/<slug>`, l'adresse de la fiche et le `href` de sa carte.
 */
export function projectPath(slug: string): string {
  return `/projets/${slug}`
}

/**
 * Le slug que désigne un chemin.
 *
 * @param pathname Un chemin d'adresse (`location.pathname`).
 * @returns Le slug de `/projets/<slug>` ; `null` pour tout autre chemin.
 */
export function slugFromPath(pathname: string): string | null {
  return PROJECT_PATH.exec(pathname)?.[1] ?? null
}

/**
 * Un geste modifié reste au navigateur : ni son clic ni sa touche ne sont annulés. Le bouton du
 * milieu n'émet pas de `click`.
 */
export function hasModifier(event: {
  ctrlKey: boolean
  metaKey: boolean
  shiftKey: boolean
  altKey: boolean
}): boolean {
  return event.ctrlKey || event.metaKey || event.shiftKey || event.altKey
}

/** Le mois et l'année d'une date ISO, en minuscules : « janvier 2025 ». */
function monthYear(date: string): string {
  return MONTH_YEAR.format(new Date(date))
}

/** Un texte, sa première lettre en capitale. */
function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * Les dates d'un projet (spec §7) : « Depuis mars 2026 » tant qu'il est en cours, « Janvier 2025 –
 * juin 2025 » ensuite. Le modèle lie les deux : `finished_on` est nul si et seulement si le projet
 * est en cours (contraintes de `content.Project`).
 */
export function projectDates({
  started_on,
  finished_on,
}: Pick<Project, 'started_on' | 'finished_on'>): string {
  const start = monthYear(started_on)
  return finished_on === null
    ? `${strings.since} ${start}`
    : `${capitalize(start)}${DATE_SEPARATOR}${monthYear(finished_on)}`
}

/** La ligne de faits « Type · Dates · Client » (spec §4.3) ; sans client, ni lui ni son séparateur. */
export function projectFacts(project: Project): string {
  return [KIND_LABELS[project.kind], projectDates(project), project.client]
    .filter(Boolean)
    .join(FACT_SEPARATOR)
}

/**
 * Sépare les outils du reste de la stack (spec §4.3), chaque groupe dans l'ordre reçu.
 *
 * @param technologies Les technologies du projet, dans l'ordre de l'admin.
 */
export function splitStack(technologies: readonly Technology[]): {
  technologies: Technology[]
  tools: Technology[]
} {
  return {
    technologies: technologies.filter(({ kind }) => kind !== 'tool'),
    tools: technologies.filter(({ kind }) => kind === 'tool'),
  }
}

/** Les sections que la fiche montre (spec §4.3) : une section au corps vide n'est pas rendue. */
export function visibleSections(sections: readonly Section[]): Section[] {
  return sections.filter(({ body }) => body.trim() !== '')
}

/** L'identifiant d'une section, cible de son fragment (spec §4.3). */
export function sectionId(anchor: string): string {
  return `${SECTION_ID_PREFIX}${anchor}`
}

/** Un fragment d'adresse (`location.hash`) désigne-t-il une section ? */
export function isSectionHash(hash: string): boolean {
  return hash.startsWith(`#${SECTION_ID_PREFIX}`)
}

/**
 * Un lien vise-t-il un fragment de la page où il se trouve, quelle que soit la façon de l'écrire ?
 *
 * @param href L'adresse résolue du lien (`HTMLAnchorElement.href`).
 * @param page L'adresse de la page (`location.href`).
 */
export function isPageFragment(href: string, page: string): boolean {
  return href.includes('#') && href.split('#')[0] === page.split('#')[0]
}

/**
 * Les images que la galerie montre, dans l'ordre (spec §4.4) : celles qui ont des variantes.
 *
 * @param gallery Les images du projet, prêtes ou non.
 * @returns La légende et les sources (`imageSources`) de chacune.
 */
export function readyImages(gallery: readonly GalleryImage[]) {
  return gallery.flatMap(({ caption, variants }) => {
    const sources = imageSources(variants)
    return sources ? [{ caption, ...sources }] : []
  })
}

/**
 * Le pas d'un balayage (spec §4.4) : plus de 40 px en horizontal, dominant sur le vertical.
 *
 * @param dx Le déplacement horizontal, en px, positif vers la droite.
 * @param dy Le déplacement vertical, en px.
 * @returns `1` vers la gauche, l'image suivante ; `-1` vers la droite ; `0` sinon.
 */
export function swipeStep(dx: number, dy: number): number {
  const distance = Math.abs(dx)
  if (distance <= SWIPE_THRESHOLD || distance <= Math.abs(dy)) return 0
  return dx < 0 ? 1 : -1
}
