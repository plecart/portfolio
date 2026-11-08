import { Dialog, DialogTrigger } from '@radix-ui/react-dialog'
import { useCallback, useEffect, useState } from 'react'
import type { Project } from '../api/projects.ts'
import { ExpandIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { GalleryArrows } from './GalleryArrows.tsx'
import { ImageViewer } from './ImageViewer.tsx'
import { directionStep, GALLERY_SIZES, hasModifier, readyImages } from './project.ts'
import { useClickWithoutSwipe, useSwipe } from './useSwipe.ts'

/**
 * L'image montrée parmi `count`, en boucle dans les deux sens (spec §4.4). ← et → la changent où que
 * soit le focus dans le panneau, qui le retient, d'où un écouteur global, tant que la galerie est
 * montée et qu'il écoute. Une touche modifiée reste au navigateur.
 *
 * @param count Le nombre d'images.
 * @param listening L'écouteur est posé ; suspendu, la couche plein écran tient seule les flèches
 *   (issue #243, décision 6).
 * @returns `index`, son rang ; `go`, le pas qui la change ; `navigable`, plus d'une image à montrer.
 */
function useImageIndex(count: number, listening: boolean) {
  const [index, setIndex] = useState(0)
  const navigable = count > 1
  const go = useCallback(
    (step: number) => setIndex((current) => (current + step + count) % count),
    [count],
  )

  useEffect(() => {
    if (!navigable || !listening) return
    const followKey = (event: KeyboardEvent) => {
      const step = directionStep(event.key)
      if (step === null || hasModifier(event)) return
      event.preventDefault()
      go(step)
    }
    addEventListener('keydown', followKey)
    return () => removeEventListener('keydown', followKey)
  }, [navigable, listening, go])

  return { index, go, navigable }
}

/**
 * La galerie d'une fiche (spec §4.4, §6.2) : une piste translatée dans un cadre carré, sa barre
 * dessous. Le carré et ses 20 px de barre se réservent en CSS : ni une image pas encore chargée, ni
 * une galerie sans image prête ne changent la hauteur du panneau (§3.2).
 *
 * Le `style` de la piste s'écrit par le CSSOM, que la CSP de production laisse passer. Les images
 * que la piste met hors du cadre sont retirées de l'arbre d'accessibilité.
 *
 * Son image s'ouvre en plein écran (issue #243) par « Agrandir l'image », ou d'un clic qui n'est pas
 * un balayage : la couche, second dialogue imbriqué dans la fiche, partage son rang et le lui laisse
 * à la fermeture, où Radix rend le focus au bouton. Elle n'a pas d'entrée d'historique : elle se
 * ferme avec la fiche, au même rendu.
 *
 * @param gallery Les images du projet, prêtes ou non.
 * @param open La fiche est ouverte ; fermée, elle ferme la couche avec elle.
 * @param rewound La fiche revient à sa carte : la galerie montre d'un coup sa première image, la
 *   photo de la carte (spec §4.6), quelle que soit celle choisie.
 */
export function ProjectGallery({
  gallery,
  open,
  rewound = false,
}: {
  gallery: Project['gallery']
  open: boolean
  rewound?: boolean
}) {
  const images = readyImages(gallery)
  const [viewing, setViewing] = useState(false)
  if (viewing && !open) setViewing(false)
  const { index: chosen, go, navigable } = useImageIndex(images.length, !viewing)
  const index = rewound ? 0 : chosen
  const swipe = useSwipe(go)
  const openOnClick = useClickWithoutSwipe(() => setViewing(true))
  const viewable = images.length > 0

  return (
    <Dialog open={viewing} onOpenChange={setViewing}>
      <div role="group" aria-label={strings.projectImages} className="project-gallery">
        <div className="project-gallery-frame" {...(navigable && swipe)}>
          {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- « Agrandir l'image » porte le geste au clavier */}
          <div
            className="project-gallery-track"
            data-rewound={rewound || undefined}
            style={{ translate: `${-index * 100}%` }}
            onPointerDown={openOnClick.onPointerDown}
            onClick={openOnClick.onClick}
          >
            {images.map(({ caption, ...sources }, position) => (
              <img
                key={position}
                {...sources}
                sizes={GALLERY_SIZES}
                draggable={false}
                alt={caption}
                loading="lazy"
                aria-hidden={position !== index}
                className="project-gallery-image"
              />
            ))}
          </div>
          {navigable && <GalleryArrows onStep={go} />}
          {viewable && (
            <DialogTrigger aria-label={strings.expandImage} className="project-gallery-expand">
              <ExpandIcon />
            </DialogTrigger>
          )}
        </div>
        <div className="project-gallery-bar">
          <span className="project-gallery-caption">{images[index]?.caption}</span>
          {navigable && (
            <span className="project-gallery-counter" aria-live="polite">
              {index + 1} / {images.length}
            </span>
          )}
        </div>
      </div>
      {viewable && (
        <ImageViewer images={images} index={index} onStep={go} onClose={() => setViewing(false)} />
      )}
    </Dialog>
  )
}
