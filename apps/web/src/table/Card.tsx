import {
  useId,
  type ComponentProps,
  type CSSProperties,
  type MouseEventHandler,
  type Ref,
} from 'react'
import type { Project } from '../api/projects.ts'
import { projectPath } from '../project/project.ts'
import { strings } from '../strings.ts'
import {
  cardDescription,
  cardNameSuffix,
  cardPose,
  cardStates,
  cardTechnologies,
  coverImage,
  coverSizes,
  type CardSize,
} from './cards.ts'
import { useCardTilt } from './useCardTilt.ts'

/** La pose d'une carte, en variables : le redressement la remplace par une règle de la feuille. */
function poseStyle(slug: string): CSSProperties {
  const { rotation, dx, dy } = cardPose(slug)
  return {
    '--card-rotation': `${rotation}deg`,
    '--card-dx': `${dx}px`,
    '--card-dy': `${dy}px`,
  } as CSSProperties
}

/** Le trombone du post-it (spec §1.8, §4.1), décoratif. */
function Clip() {
  return (
    <svg
      className="card-clip"
      viewBox="0 0 14 30"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M4 8v15a3 3 0 0 0 6 0V6a2 2 0 0 0-4 0v15" />
      <path d="M4 8V6a3 3 0 0 1 6 0" />
    </svg>
  )
}

/** Une image de la carte : le nom du lien porte le sens, jamais son texte alternatif. */
function CardImage(props: ComponentProps<'img'>) {
  return <img alt="" loading="lazy" {...props} />
}

/**
 * La photo (spec §4.1) : le carré `--line`, l'image de couverture si elle a des variantes et, pour
 * un projet en cours, sa copie en niveaux de gris par-dessus — la même image, par CSS seulement. Le
 * bandeau de résumé la recouvre, masqué : le résumé est dans la description du lien.
 */
function Photo({ project, size }: { project: Project; size: CardSize }) {
  const cover = coverImage(project)
  const sizes = coverSizes(size)
  return (
    <div className="card-photo">
      {cover && <CardImage {...cover} sizes={sizes} />}
      {cover && cardStates(project).ongoing && (
        <CardImage {...cover} sizes={sizes} className="card-photo-grey" aria-hidden />
      )}
      <p className="card-summary" aria-hidden>
        <span className="card-summary-text">{project.summary}</span>
      </p>
    </div>
  )
}

/**
 * La bande basse (spec §4.1), masquée : le nom du lien porte les états, et sa description les
 * technologies. Les rubans de technologies à gauche, avec leur icône, leur nom en texte masqué et
 * en infobulle native ; les rubans d'état à droite. « Ouvrir » les remplace pendant la révélation
 * au toucher : un texte du lien, jamais un `<button>`, qu'un `<a>` ne peut contenir.
 */
function Band({ project }: { project: Project }) {
  const { ongoing, live } = cardStates(project)
  return (
    <div className="card-band" aria-hidden>
      <ul className="card-ribbons">
        {cardTechnologies(project.technologies).map(({ name, icon }) => (
          <li key={name} className="card-ribbon" title={name}>
            <CardImage src={icon} />
            <span className="sr-only">{name}</span>
          </li>
        ))}
      </ul>
      <ul className="card-ribbons">
        {ongoing && <li className="card-ribbon">{strings.ribbonOngoing}</li>}
        {live && (
          <li className="card-ribbon">
            <span className="card-dot" />
            {strings.ribbonLive}
          </li>
        )}
      </ul>
      <span className="card-open">{strings.openCard}</span>
    </div>
  )
}

/**
 * Une carte polaroid (spec §4.1, §4.2) : le lien est la cellule de la table, au sens de
 * `TABLE_CELL_SELECTOR` — sa boîte de grille, sans transformation. Il contient, de l'extérieur vers
 * l'intérieur, la couche d'entrée, la pose, la face et l'inclinaison, qui porte le trombone, le
 * post-it, la photo et la bande basse.
 *
 * Le lien tire son nom de son contenu, où restent exposés le `<h2>`, que la navigation par titres
 * lit seul, et la suite du nom, en texte masqué. Chromium sépare les deux d'une espace, devant
 * le point du titre (Chromium 156, mesuré le 2026-11-01). Ni `aria-label` ni `aria-labelledby` sur
 * le lien : `label-content-name-mismatch` (axe 4.14) comparerait ce nom au texte visible, où le
 * survol ajoute le résumé.
 *
 * Sa description, le résumé puis les technologies, vit dans un élément `hidden` : désigner la liste
 * des rubans la ferait entrer dans le nom du lien, tout `aria-hidden` qu'elle soit (Chromium 156,
 * mesuré le 2026-10-31).
 *
 * La pose passe par la prop `style` de React, qui écrit par le CSSOM : la CSP de production
 * bloquerait un attribut `style` analysé (`setAttribute`).
 *
 * @param project Le projet.
 * @param size La taille de la carte (`cardSize`).
 * @param revealed La carte est révélée au toucher (`useTouchReveal`).
 * @param onClick Le `click` du lien.
 * @param ref Le lien, que la table focalise après une relance réussie.
 */
export function Card({
  project,
  size,
  revealed,
  onClick,
  ref,
}: {
  project: Project
  size: CardSize
  revealed: boolean
  onClick: MouseEventHandler<HTMLAnchorElement>
  ref?: Ref<HTMLAnchorElement>
}) {
  const descriptionId = useId()
  const { layer, ...tiltGestures } = useCardTilt()

  return (
    <a
      ref={ref}
      href={projectPath(project.slug)}
      aria-describedby={descriptionId}
      data-table-cell
      data-revealed={revealed || undefined}
      className={`card card-${size}`}
      onClick={onClick}
      {...tiltGestures}
    >
      <div className="card-entry">
        <div className="card-pose" style={poseStyle(project.slug)}>
          <div className="card-face">
            <div ref={layer} className="card-tilt">
              <Clip />
              <h2 className="card-postit">{project.title}</h2>
              <span className="sr-only">{cardNameSuffix(project)}</span>
              <Photo project={project} size={size} />
              <Band project={project} />
            </div>
          </div>
        </div>
      </div>
      <span id={descriptionId} hidden>
        {cardDescription(project)}
      </span>
    </a>
  )
}
