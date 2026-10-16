import { useEffect, useRef, type Ref } from 'react'
import type { ProjectsStatus } from '../api/useProjects.ts'
import { strings } from '../strings.ts'

/**
 * La grille de la table (spec §3.1) : marge intérieure 24 px 16 px 32 px autour d'une largeur
 * maximale de 1200 px — la borne compte les deux marges latérales, la largeur étant pleine pour que
 * la colonne flexible de `<main>` étire la grille ; remplissage dense. Sous 600 px, deux colonnes
 * `1fr` et 16 px de gouttière ; dès 600 px, des pistes de 240 px centrées et 28 px de gouttière —
 * deux à quatre colonnes selon la largeur.
 */
const GRID_CLASSES = [
  'mx-auto grid w-full max-w-[calc(1200px+2*var(--s-4))] grid-flow-dense',
  'px-(--s-4) pt-(--s-5) pb-(--s-6)',
  'grid-cols-2 gap-(--s-4)',
  'sm:grid-cols-[repeat(auto-fit,240px)] sm:justify-center sm:gap-[28px]',
].join(' ')

/**
 * Les deux cadres de chargement, aux dimensions des cartes qu'ils annoncent (spec §4.1, §6.1) :
 * cadre et bande basse, mobile puis bureau ; la photo est un carré de la largeur restante. Le
 * double occupe deux colonnes, et deux rangées dès 600 px (la première rangée entière sur mobile).
 */
const FRAMES = {
  showcase: {
    cell: 'col-span-2 sm:row-span-2',
    face: 'px-[12px] pt-[12px] sm:px-[14px] sm:pt-[14px]',
    band: 'min-h-[56px] sm:min-h-[64px]',
  },
  simple: {
    cell: '',
    face: 'px-[8px] pt-[8px] sm:px-[10px] sm:pt-[10px]',
    band: 'min-h-[46px] sm:min-h-[52px]',
  },
}

/** La table à trois cartes avec vitrine (spec §5.5), que le chargement annonce (§5.1). */
const LOADING_FRAMES = ['showcase', 'simple', 'simple'] as const

/**
 * Un cadre de chargement (spec §5.1) : une cellule de la table, au sens de `TABLE_CELL_SELECTOR`
 * — l'attribut sur la boîte de grille, la pulsation sur la face qu'elle contient. Inerte et caché
 * des technologies d'assistance ; papier et ombre de la face d'une carte (§4.1), zone image et
 * barre de 40 % × 10 px en `--line`. Pulsation d'opacité, nulle en mouvement réduit (§6.3).
 */
function LoadingFrame({ size }: { size: keyof typeof FRAMES }) {
  const { cell, face, band } = FRAMES[size]
  return (
    <div data-table-cell aria-hidden inert className={cell}>
      <div
        className={`${face} animate-frame-pulse rounded-(--r-card) bg-(--paper) [box-shadow:var(--shadow-rest)] motion-reduce:animate-none`}
      >
        <div className="aspect-square bg-(--line)" />
        <div className={`${band} flex items-center`}>
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
 * La table (`<main>`, spec §3.1) et les états qui précèdent ses cartes (§5.1-5.3) : les trois
 * cadres pendant le chargement, le message d'erreur en échec, la grille vide une fois la liste
 * arrivée — les cartes sont #20. Elle s'étire entre l'entête et les liens de l'auteur.
 *
 * @param ref La table, que les liens de l'auteur mesurent.
 * @param status L'état du chargement ; `loading` rend la table occupée (`aria-busy`).
 * @param onRetry Relance le chargement, depuis le message d'erreur.
 * @param retried Une relance a déjà eu lieu : le message qui revient reprend le focus.
 */
export function Table({
  ref,
  status,
  onRetry,
  retried,
}: {
  ref: Ref<HTMLElement>
  status: ProjectsStatus
  onRetry: () => void
  retried: boolean
}) {
  return (
    // Le corps de page commence sous l'entête fixe de 56 px (spec §3.3).
    <main ref={ref} aria-busy={status === 'loading' || undefined} className="flex flex-1 flex-col pt-14">
      {status === 'error' ? (
        <LoadError onRetry={onRetry} focusRetry={retried} />
      ) : (
        <div className={GRID_CLASSES}>
          {status === 'loading' &&
            LOADING_FRAMES.map((size, index) => <LoadingFrame key={index} size={size} />)}
        </div>
      )}
    </main>
  )
}
