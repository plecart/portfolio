/**
 * La légende de l'image montrée et, à plusieurs images, son compteur « n / N » (spec §4.4) : la
 * barre de la galerie et celle de sa couche plein écran les portent, chacune à sa place
 * (`project.css`).
 *
 * @param caption La légende ; absente sans image prête.
 * @param index Le rang de l'image montrée.
 * @param count Le nombre d'images.
 */
export function GalleryCaption({
  caption,
  index,
  count,
}: {
  caption?: string
  index: number
  count: number
}) {
  return (
    <>
      <span className="project-gallery-caption">{caption}</span>
      {count > 1 && (
        <span className="project-gallery-counter" aria-live="polite">
          {index + 1} / {count}
        </span>
      )}
    </>
  )
}
