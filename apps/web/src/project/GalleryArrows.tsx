import { ChevronLeftIcon, ChevronRightIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'

/** Les deux sens de la galerie (spec §4.4) : sa flèche à l'écran et sa touche. */
const DIRECTIONS = [
  {
    step: -1,
    key: 'ArrowLeft',
    label: strings.previousImage,
    side: 'left-(--s-2)',
    Icon: ChevronLeftIcon,
  },
  {
    step: 1,
    key: 'ArrowRight',
    label: strings.nextImage,
    side: 'right-(--s-2)',
    Icon: ChevronRightIcon,
  },
]

/**
 * Le pas de la touche d'un sens de la galerie (spec §4.4).
 *
 * @param key La touche (`KeyboardEvent.key`).
 * @returns `-1` pour ←, `1` pour → ; `null` pour toute autre touche.
 */
export function directionStep(key: string): number | null {
  return DIRECTIONS.find((direction) => direction.key === key)?.step ?? null
}

/**
 * Les flèches de la galerie (spec §4.4) : 36 px, rondes, centrées verticalement dans leur cadre, à
 * 8 px de ses bords. La galerie et sa couche plein écran les posent chacune dans le sien, qui les
 * positionne (`project.css`).
 *
 * @param onStep Reçoit le pas de la flèche : `-1` l'image précédente, `1` la suivante.
 */
export function GalleryArrows({ onStep }: { onStep: (step: number) => void }) {
  return DIRECTIONS.map(({ step, label, side, Icon }) => (
    <button
      key={step}
      type="button"
      aria-label={label}
      className={`project-gallery-arrow ${side}`}
      onClick={() => onStep(step)}
    >
      <Icon />
    </button>
  ))
}
