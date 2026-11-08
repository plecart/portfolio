import { DialogClose, DialogContent, DialogPortal, DialogTitle } from '@radix-ui/react-dialog'
import { type KeyboardEvent, type Ref, useEffect, useRef, useState } from 'react'
import { CloseIcon, ZoomInIcon, ZoomOutIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { directionStep, GalleryArrows } from './GalleryArrows.tsx'
import { PAPER_BUTTON, type readyImages } from './project.ts'
import {
  clampView,
  containedSize,
  FIT,
  MAX_SCALE,
  MIN_SCALE,
  panBy,
  type Point,
  type Size,
  type Stage,
  zoomAt,
} from './zoom.ts'

/** Une image prête de la galerie : sa légende et ses sources. */
type Image = ReturnType<typeof readyImages>[number]

/** Le pas d'un déplacement au clavier, en px (PR #250, H3). */
const PAN_STEP = 100

/**
 * Le déplacement de chaque flèche, une fois zoomé : celui du défilement d'une page, qui montre ce
 * qui est plus loin dans le sens de la flèche — l'image part à l'opposé.
 */
const PAN_KEYS = new Map<string, Point>([
  ['ArrowLeft', { x: PAN_STEP, y: 0 }],
  ['ArrowRight', { x: -PAN_STEP, y: 0 }],
  ['ArrowUp', { x: 0, y: PAN_STEP }],
  ['ArrowDown', { x: 0, y: -PAN_STEP }],
])

/** Le pas de zoom de chaque touche, d'une unité (PR #250, H1). */
const ZOOM_KEYS = new Map([
  ['+', 1],
  ['-', -1],
])

/** Les boutons de zoom de la barre, dans leur ordre : leur pas, leur nom, leur icône. */
const ZOOM_BUTTONS = [
  { by: -1, label: strings.zoomOut, Icon: ZoomOutIcon },
  { by: 1, label: strings.zoomIn, Icon: ZoomInIcon },
]

/** Le facteur est-il à la borne vers laquelle zoome ce pas ? */
const atBound = (scale: number, by: number) => (by < 0 ? scale <= MIN_SCALE : scale >= MAX_SCALE)

/**
 * La taille d'un élément, suivie à chaque redimensionnement.
 *
 * @returns `null` avant la première mesure.
 */
function useSize(element: HTMLElement | null): Size | null {
  const [size, setSize] = useState<Size | null>(null)

  useEffect(() => {
    if (!element) return
    const observer = new ResizeObserver(([{ contentRect }]) =>
      setSize({ width: contentRect.width, height: contentRect.height }),
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [element])

  return size
}

/** Le centre d'une zone : le point visé par un zoom au bouton ou à la touche (PR #250, H1). */
const centerOf = ({ width, height }: Size): Point => ({ x: width / 2, y: height / 2 })

type ViewerProps = {
  images: Image[]
  index: number
  onStep: (step: number) => void
  onClose: () => void
}

/**
 * La couche plein écran de la galerie (issue #243) : un dialogue imbriqué dans la fiche, à rendre
 * dans le `Dialog` qui la tient ouverte. Sans `DialogOverlay`, comme la fiche : son `RemoveScroll`
 * poserait un `<style>` que la CSP de production bloque.
 *
 * @param images Les images prêtes de la galerie, une au moins.
 * @param index Le rang de l'image montrée, celui de la galerie.
 * @param onStep Change l'image de la galerie, du pas reçu, en boucle.
 * @param onClose La fermeture par un clic sur le fond, hors de l'image ; Radix tient les autres.
 */
export function ImageViewer(props: ViewerProps) {
  return (
    <DialogPortal>
      <ViewerLayer {...props} />
    </DialogPortal>
  )
}

/**
 * Le contenu de la couche, monté le temps qu'elle est ouverte, fondus compris : son zoom repart de
 * ×1 à chaque ouverture. Radix lui pose la référence dont `DialogPortal` suit le fondu de sortie,
 * transmise au `DialogContent` : sans elle, la couche disparaîtrait sans fondu.
 *
 * Toute la fenêtre, sur la palette sombre (`data-scheme`, tokens.css), dans les deux modes : la
 * zone d'image, puis sa barre — légende, zoom, compteur. L'image tient entière dans la zone à ×1,
 * centrée ; une seule est montée, et changer d'image la remplace d'un coup, à ×1 (décision 7). Son
 * `transform` s'écrit par le CSSOM, comme la piste de la galerie.
 *
 * Le clavier, tenu par la couche qui retient le focus (décision 6) : + et − zooment d'une unité au
 * centre ; à ×1, ← et → changent d'image ; zoomé, ← → ↑ ↓ déplacent de 100 px, borné. Ctrl, Cmd
 * et Alt laissent la touche au navigateur ; Maj ne compte que pour les flèches. « Zoom arrière » et
 * « Zoom avant » se désactivent à leur borne : celui qui l'atteint passe le focus à l'autre, sans
 * quoi le navigateur le rendrait au document, hors de la couche (« focus fixup » de HTML ; une
 * flèche pressée ensuite s'y perdait parfois, Chromium 156, mesuré le 2026-11-08). Échap, le bouton
 * « Fermer l'image » et un clic sur le fond la ferment seule ; le focus revient à « Agrandir
 * l'image ».
 */
function ViewerLayer({
  ref,
  images,
  index,
  onStep,
  onClose,
}: ViewerProps & { ref?: Ref<HTMLDivElement> }) {
  const [zone, setZone] = useState<HTMLDivElement | null>(null)
  const zoneSize = useSize(zone)
  const [view, setView] = useState(FIT)
  const zoomButtons = useRef<(HTMLButtonElement | null)[]>([])
  const { caption, ...sources } = images[index]
  const stage: Stage | null = zoneSize && {
    zone: zoneSize,
    natural: { width: sources.width, height: sources.height },
  }
  // La vue rendue : bornée à la zone telle qu'elle est, la fenêtre ayant pu changer de taille.
  const shown = stage ? clampView(view, stage) : FIT
  const box = stage && containedSize(stage.zone, stage.natural)
  const navigable = images.length > 1

  const step = (by: number) => {
    setView(FIT)
    onStep(by)
  }
  /** Zoome d'une unité au centre de la zone ; rend le facteur atteint. */
  const zoomBy = (by: number) => {
    if (!stage) return shown.scale
    const next = zoomAt(shown, shown.scale + by, centerOf(stage.zone), stage)
    setView(next)
    return next.scale
  }

  /** Ce que fait une touche, selon le zoom ; rien pour une touche modifiée, hors Maj pour + et −. */
  const keyAction = ({ key, shiftKey, ctrlKey, metaKey, altKey }: KeyboardEvent) => {
    if (ctrlKey || metaKey || altKey) return
    const zoom = ZOOM_KEYS.get(key)
    // Le + s'obtient avec Maj sur certains claviers.
    if (zoom !== undefined) return () => zoomBy(zoom)
    if (shiftKey) return
    if (shown.scale > MIN_SCALE) {
      const delta = PAN_KEYS.get(key)
      return delta && (() => stage && setView(panBy(shown, delta, stage)))
    }
    const direction = directionStep(key)
    if (navigable && direction !== null) return () => step(direction)
  }

  return (
    <DialogContent
      ref={ref}
      aria-modal="true"
      aria-describedby={undefined}
      data-scheme="dark"
      className="image-viewer"
      onKeyDown={(event) => {
        const action = keyAction(event)
        if (!action) return
        event.preventDefault()
        action()
      }}
    >
      <DialogTitle className="sr-only">{strings.imageViewer}</DialogTitle>
      <DialogClose
        aria-label={strings.closeImage}
        className={`absolute top-(--s-2) right-(--s-2) z-10 ${PAPER_BUTTON}`}
      >
        <CloseIcon />
      </DialogClose>
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- Échap et « Fermer l'image » portent la fermeture au clavier */}
      <div
        ref={setZone}
        className="image-viewer-zone"
        onClick={(event) => event.target === event.currentTarget && onClose()}
      >
        <img
          key={index}
          {...sources}
          sizes="100vw"
          alt={caption}
          draggable={false}
          className="image-viewer-image"
          style={
            box
              ? { ...box, transform: `translate(${shown.x}px, ${shown.y}px) scale(${shown.scale})` }
              : undefined
          }
        />
        {navigable && <GalleryArrows onStep={step} />}
      </div>
      <div className="image-viewer-bar">
        <span className="project-gallery-caption">{caption}</span>
        {ZOOM_BUTTONS.map(({ by, label, Icon }, position) => (
          <button
            key={by}
            ref={(button) => {
              zoomButtons.current[position] = button
            }}
            type="button"
            aria-label={label}
            disabled={atBound(shown.scale, by)}
            className={`${PAPER_BUTTON} disabled:opacity-40`}
            onClick={() => {
              // Désactivé à sa borne, il perdrait le focus, et la couche son clavier : l'autre le prend.
              if (atBound(zoomBy(by), by)) zoomButtons.current[1 - position]?.focus()
            }}
          >
            <Icon />
          </button>
        ))}
        {navigable && (
          <span className="project-gallery-counter" aria-live="polite">
            {index + 1} / {images.length}
          </span>
        )}
      </div>
    </DialogContent>
  )
}
