import { DialogClose, DialogContent, DialogPortal, DialogTitle } from '@radix-ui/react-dialog'
import { type Ref, useEffect, useState } from 'react'
import { CloseIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { GalleryArrows } from './GalleryArrows.tsx'
import { PAPER_BUTTON, type readyImages } from './project.ts'
import { keyCommand } from './viewerKeys.ts'
import {
  clampView,
  containedSize,
  FIT,
  MIN_SCALE,
  panBy,
  type Point,
  type Size,
  type Stage,
  zoomAt,
} from './zoom.ts'

/** Une image prête de la galerie : sa légende et ses sources. */
type Image = ReturnType<typeof readyImages>[number]

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

/** Le centre d'une zone : le point visé par un zoom à la touche (PR #250, H1). */
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
 * @param index Le rang de l'image montrée, celui que la galerie a choisi.
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
 * zone d'image, puis sa barre — légende et compteur ; aucun bouton de zoom (décision 8). L'image
 * tient entière dans la zone à ×1, centrée ; une seule est montée, et changer d'image la remplace
 * d'un coup, à ×1 (décision 7). Son `transform` s'écrit par le CSSOM, comme la piste de la galerie.
 *
 * Le clavier, tenu par la couche qui retient le focus (décision 6), suit `keyCommand` : + et −
 * zooment d'une unité au centre de la zone ; à ×1, ← et → changent d'image ; zoomé, ← → ↑ ↓
 * déplacent l'image. Échap, le bouton « Fermer l'image » et un clic sur le fond la ferment seule ;
 * le focus revient à « Agrandir l'image ».
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

  return (
    <DialogContent
      ref={ref}
      aria-modal="true"
      aria-describedby={undefined}
      data-scheme="dark"
      className="image-viewer"
      onKeyDown={(event) => {
        const command = keyCommand(event, { zoomed: shown.scale > MIN_SCALE, navigable })
        if (!command) return
        event.preventDefault()
        if ('step' in command) return step(command.step)
        if (!stage) return
        setView(
          'pan' in command
            ? panBy(shown, command.pan, stage)
            : zoomAt(shown, shown.scale + command.zoom, centerOf(stage.zone), stage),
        )
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
        {navigable && (
          <span className="project-gallery-counter" aria-live="polite">
            {index + 1} / {images.length}
          </span>
        )}
      </div>
    </DialogContent>
  )
}
