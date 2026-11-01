import { useEffect, useRef, type MouseEvent, type Ref } from 'react'
import type { Project } from '../api/projects.ts'
import type { ProjectsStatus } from '../api/useProjects.ts'
import { isModifiedClick } from '../project/project.ts'
import { strings } from '../strings.ts'
import { Card } from './Card.tsx'
import { cardSize, orderProjects, type CardSize } from './cards.ts'
import { useCardEntrance } from './useCardEntrance.ts'
import { useTouchReveal } from './useTouchReveal.ts'

/**
 * La grille de la table (spec §3.1) : marge intérieure 24 px 16 px 32 px autour d'une largeur
 * maximale de 1200 px — la borne compte les deux marges latérales, la largeur étant pleine pour que
 * la colonne flexible de `<main>` étire la grille ; pistes centrées, remplissage dense ; 16 px de
 * gouttière sous 600 px, 28 px au-dessus.
 */
const GRID_CLASSES = [
  'mx-auto grid w-full max-w-[calc(1200px+2*var(--s-4))] grid-flow-dense justify-center',
  'px-(--s-4) pt-(--s-5) pb-(--s-6)',
  'gap-(--s-4) sm:gap-[28px]',
].join(' ')

/**
 * Les pistes de la grille. Une table : deux colonnes `1fr` sous 600 px, au-dessus des pistes de
 * 240 px — deux à quatre colonnes selon la largeur. Une carte seule a sa propre piste : 80 % de la
 * table sous 600 px, 360 px au-dessus (spec §4.1, §5.5).
 */
const TRACK_CLASSES = 'grid-cols-2 sm:grid-cols-[repeat(auto-fit,240px)]'
const SOLO_TRACK_CLASSES = 'grid-cols-[80%] sm:grid-cols-[360px]'

/** La table à trois cartes avec vitrine (spec §5.5), que le chargement annonce (§5.1). */
const LOADING_FRAMES: readonly CardSize[] = ['showcase', 'simple', 'simple']

/**
 * Un cadre de chargement (spec §5.1) : une cellule de la table, au sens de `TABLE_CELL_SELECTOR`
 * — l'attribut sur la boîte de grille, la pulsation sur la face qu'elle contient. Inerte et caché
 * des technologies d'assistance ; la taille, la face, la photo et la bande d'une carte (§4.1),
 * sans contenu, et une barre de 40 % × 10 px en `--line`. Pulsation d'opacité, nulle en mouvement
 * réduit (§6.3).
 */
function LoadingFrame({ size }: { size: CardSize }) {
  return (
    <div data-table-cell aria-hidden inert className={`card-${size}`}>
      <div className="card-face animate-frame-pulse motion-reduce:animate-none">
        <div className="card-photo" />
        <div className="card-band">
          <div className="h-[10px] w-2/5 rounded-full bg-(--line)" />
        </div>
      </div>
    </div>
  )
}

/**
 * Le message d'erreur (spec §4.5), à la place de la table : centré dans l'espace entre l'entête et
 * les liens de l'auteur ; « Réessayer », à la ligne, est un bouton au style de lien, qui relance le
 * chargement. L'espace qui le précède ne se voit pas, mais garde les deux phrases séparées dans le
 * texte que lisent les technologies d'assistance.
 *
 * @param focusRetry Donne le focus à « Réessayer » à l'apparition : après une relance échouée, le
 *   bouton activé a disparu avec le message, et le focus serait retombé sur le document. Jamais au
 *   premier échec, qui ne suit aucune action du visiteur.
 */
function LoadError({ onRetry, focusRetry }: { onRetry: () => void; focusRetry: boolean }) {
  const retry = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (focusRetry) retry.current?.focus()
  }, [focusRetry])

  return (
    <div className="grid flex-1 place-items-center px-(--s-4) py-(--s-5)">
      <p role="status" className="text-center">
        {strings.loadError}{' '}
        <button
          ref={retry}
          type="button"
          onClick={onRetry}
          className="mx-auto block cursor-pointer text-(--accent) underline underline-offset-[3px] transition-colors hover:text-(--ink)"
        >
          {strings.retry}
        </button>
      </p>
    </div>
  )
}

/**
 * La table (`<main>`, spec §3.1) et ses états (§5.1-5.3) : les trois cadres pendant le chargement,
 * le message d'erreur en échec, puis les cartes dans l'ordre de `orderProjects` — rien pour une
 * liste vide. Elle s'étire entre l'entête et les liens de l'auteur, fait entrer ses cartes
 * (`useCardEntrance`) et tient la seule révélée au toucher (`useTouchReveal`).
 *
 * @param ref La table, que les liens de l'auteur mesurent.
 * @param status L'état du chargement ; `loading` rend la table occupée (`aria-busy`).
 * @param projects Les projets, vides tant que la liste n'est pas arrivée.
 * @param onRetry Relance le chargement, depuis le message d'erreur.
 * @param retried Une relance a déjà eu lieu : le message qui revient reprend le focus, et la table
 *   qui arrive le donne à sa première carte, le bouton activé ayant disparu.
 * @param onOpen Ouvre la fiche d'un projet, depuis le clic sur sa carte.
 * @param projectOpen La fiche est ouverte : les cartes attendent sa fermeture pour entrer.
 */
export function Table({
  ref,
  status,
  projects,
  onRetry,
  retried,
  onOpen,
  projectOpen,
}: {
  ref: Ref<HTMLElement>
  status: ProjectsStatus
  projects: Project[]
  onRetry: () => void
  retried: boolean
  onOpen: (slug: string) => void
  projectOpen: boolean
}) {
  const firstCard = useRef<HTMLAnchorElement>(null)
  const grid = useRef<HTMLDivElement>(null)
  const ordered = orderProjects(projects)

  const { revealed, revealOnTouch } = useTouchReveal()

  useCardEntrance(grid, projects, projectOpen)

  useEffect(() => {
    if (retried && status === 'loaded') firstCard.current?.focus()
  }, [retried, status])

  const openOnClick = (event: MouseEvent, slug: string) => {
    if (isModifiedClick(event)) return
    revealOnTouch(event, slug)
    if (event.defaultPrevented) return
    event.preventDefault()
    onOpen(slug)
  }

  return (
    // Le corps de page commence sous l'entête fixe de 56 px (spec §3.3). Une pose extrême passe la
    // marge de 16 px sous 600 px : `clip`, sans conteneur de défilement, la retient dans la page.
    <main
      ref={ref}
      aria-busy={status === 'loading' || undefined}
      className="flex flex-1 flex-col overflow-x-clip pt-14"
    >
      {status === 'error' ? (
        <LoadError onRetry={onRetry} focusRetry={retried} />
      ) : (
        <div
          ref={grid}
          className={`${GRID_CLASSES} ${ordered.length === 1 ? SOLO_TRACK_CLASSES : TRACK_CLASSES}`}
        >
          {status === 'loading' &&
            LOADING_FRAMES.map((size, index) => <LoadingFrame key={index} size={size} />)}
          {ordered.map((project, index) => (
            <Card
              key={project.slug}
              ref={index === 0 ? firstCard : undefined}
              project={project}
              size={cardSize(project, ordered.length)}
              revealed={project.slug === revealed}
              onClick={(event) => openOnClick(event, project.slug)}
            />
          ))}
        </div>
      )}
    </main>
  )
}
