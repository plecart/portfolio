import { useCallback, useEffect, useState } from 'react'
import type { Project } from '../api/projects.ts'
import { ChevronLeftIcon, ChevronRightIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { GALLERY_SIZES, hasModifier, readyImages } from './project.ts'
import { useSwipe } from './useSwipe.ts'

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
 * L'image montrée parmi `count`, en boucle dans les deux sens (spec §4.4). ← et → la changent où que
 * soit le focus dans le panneau, qui le retient, d'où un écouteur global, tant que la galerie est
 * montée. Une touche modifiée reste au navigateur.
 *
 * @returns `index`, son rang ; `go`, le pas qui la change ; `navigable`, plus d'une image à montrer.
 */
function useImageIndex(count: number) {
  const [index, setIndex] = useState(0)
  const navigable = count > 1
  const go = useCallback(
    (step: number) => setIndex((current) => (current + step + count) % count),
    [count],
  )

  useEffect(() => {
    if (!navigable) return
    const followKey = (event: KeyboardEvent) => {
      const direction = DIRECTIONS.find(({ key }) => key === event.key)
      if (!direction || hasModifier(event)) return
      event.preventDefault()
      go(direction.step)
    }
    addEventListener('keydown', followKey)
    return () => removeEventListener('keydown', followKey)
  }, [navigable, go])

  return { index, go, navigable }
}

/**
 * La galerie d'une fiche (spec §4.4, §6.2) : une piste translatée dans un cadre carré, sa barre
 * dessous. Le carré et ses 28 px de barre se réservent en CSS : ni une image pas encore chargée, ni
 * une galerie sans image prête ne changent la hauteur du panneau (§3.2).
 *
 * Le `style` de la piste s'écrit par le CSSOM, que la CSP de production laisse passer. Les images
 * que la piste met hors du cadre sont retirées de l'arbre d'accessibilité.
 *
 * @param gallery Les images du projet, prêtes ou non.
 */
export function ProjectGallery({ gallery }: { gallery: Project['gallery'] }) {
  const images = readyImages(gallery)
  const { index, go, navigable } = useImageIndex(images.length)
  const swipe = useSwipe(go)

  return (
    <div role="group" aria-label={strings.projectImages} className="project-gallery">
      <div className="project-gallery-frame" {...(navigable && swipe)}>
        <div className="project-gallery-track" style={{ translate: `${-index * 100}%` }}>
          {images.map(({ caption, ...sources }, position) => (
            <img
              key={position}
              {...sources}
              sizes={GALLERY_SIZES}
              alt={caption}
              loading="lazy"
              aria-hidden={position !== index}
              className="project-gallery-image"
            />
          ))}
        </div>
        {navigable &&
          DIRECTIONS.map(({ step, label, side, Icon }) => (
            <button
              key={step}
              type="button"
              aria-label={label}
              className={`project-gallery-arrow ${side}`}
              onClick={() => go(step)}
            >
              <Icon />
            </button>
          ))}
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
  )
}
