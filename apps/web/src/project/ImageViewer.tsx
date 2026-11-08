import { DialogClose, DialogContent, DialogPortal, DialogTitle } from '@radix-ui/react-dialog'
import { type Ref, useState } from 'react'
import { CloseIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { GalleryArrows } from './GalleryArrows.tsx'
import { PAPER_BUTTON, type readyImages } from './project.ts'
import { useGestures } from './useGestures.ts'
import { useZoomView } from './useZoomView.ts'
import { keyCommand } from './viewerKeys.ts'
import { MIN_SCALE, panBy, stepZoom, toggleZoom, zoomAt } from './zoom.ts'

/** Une image prête de la galerie : sa légende et ses sources. */
type Image = ReturnType<typeof readyImages>[number]

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
 * @param onClose La fermeture par un toucher du fond, hors de l'image ; Radix tient les autres.
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
 * Le zoom (`useZoomView`) se commande de deux voies. Les gestes de la zone (`useGestures`) : le
 * double clic ou le double tape bascule de ×1 à ×2 au point visé, et revient à ×1 ; le glisser
 * déplace l'image ; molette et pincement zooment au point visé ; à ×1, un balayage du doigt change
 * d'image ; un toucher du fond ferme la couche. Le clavier, tenu par la couche qui retient le focus
 * (décision 6), suit `keyCommand` : + et − zooment d'une unité au centre de la zone ; à ×1, ← et →
 * changent d'image ; zoomé, ← → ↑ ↓ déplacent l'image. Le double clic et les touches glissent ;
 * l'image suit le reste sans retard. Échap et le bouton « Fermer l'image » la ferment seule aussi ;
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
  const { caption, ...sources } = images[index]
  const { shown, box, glide, change, hold, reset } = useZoomView(zone, {
    width: sources.width,
    height: sources.height,
  })
  const zoomed = shown.scale > MIN_SCALE
  const navigable = images.length > 1

  const step = (by: number) => {
    reset()
    onStep(by)
  }

  const gestures = useGestures(zone, {
    onDrag: (delta) => change((view, stage) => panBy(view, delta, stage)),
    onZoom: (factor, point) =>
      change((view, stage) => zoomAt(view, view.scale * factor, point, stage)),
    onPinchStart: hold,
    onPinch: (factor, from, to) =>
      change((_, stage, held) => zoomAt(held, held.scale * factor, from, stage, to)),
    onDoubleTap: (point) => change((view, stage) => toggleZoom(view, point, stage), true),
    onSwipe: (by) => {
      if (!zoomed) step(by)
    },
    onBackgroundTap: onClose,
  })

  return (
    <DialogContent
      ref={ref}
      aria-modal="true"
      aria-describedby={undefined}
      data-scheme="dark"
      className="image-viewer"
      onKeyDown={(event) => {
        const command = keyCommand(event, { zoomed, navigable })
        if (!command) return
        event.preventDefault()
        if ('step' in command) return step(command.step)
        change(
          (view, stage) =>
            'pan' in command
              ? panBy(view, command.pan, stage)
              : stepZoom(view, command.zoom, stage),
          true,
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
      <div
        ref={setZone}
        className="image-viewer-zone"
        data-zoomed={zoomed || undefined}
        {...gestures}
      >
        <img
          key={index}
          {...sources}
          sizes="100vw"
          alt={caption}
          draggable={false}
          className="image-viewer-image"
          data-glide={glide || undefined}
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
