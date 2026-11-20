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
  type Technology,
} from './cards.ts'

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
 * La photo (spec §4.1) : le carré `--line` et l'image de couverture si elle a des variantes. Le
 * bandeau de résumé la recouvre, masqué : le résumé est dans la description du lien.
 */
function Photo({ project, size }: { project: Project; size: CardSize }) {
  const cover = coverImage(project)
  return (
    <div className="card-photo">
      {cover && <CardImage {...cover} sizes={coverSizes(size)} />}
      <p className="card-summary" aria-hidden>
        <span className="card-summary-text">{project.summary}</span>
      </p>
    </div>
  )
}

/**
 * La sangle de chantier d'un projet en cours (spec §4.1), décorative : deux boîtes, qui la coupent
 * 3 px au-delà du cadre puis au cadre (`card.css`).
 */
function Strap() {
  return (
    <span className="card-strap" aria-hidden>
      <span className="card-strap-stripes" />
    </span>
  )
}

/**
 * Un ruban de technologie (spec §4.1) : son icône, son nom (`card-ribbon-name`) en texte masqué et en
 * infobulle native. Son nom est aussi son identité (`data-ribbon`) : le ruban de la carte vole vers
 * celui de la fiche qui porte la même, et la copie de celui-ci efface le sien en se roulant à la
 * largeur du premier (`useChoreography`).
 *
 * L'icône, décorative, n'est que la forme du fichier téléversé : un masque sur l'encre du ruban
 * (`card.css`, #271). Son adresse passe par la prop `style`, comme la pose de `Card`, et la copie
 * volante la reçoit avec l'attribut que `cloneNode` recopie.
 *
 * @param technology La technologie.
 * @param labelled Son nom en clair, sans infobulle : la stack de la fiche (§4.3).
 */
export function TechnologyRibbon({
  technology: { name, icon },
  labelled = false,
}: {
  technology: Technology
  labelled?: boolean
}) {
  return (
    <li className="card-ribbon" data-ribbon={name} title={labelled ? undefined : name}>
      <span
        className="card-ribbon-icon"
        style={{ '--icon': `url("${icon}")` } as CSSProperties}
        aria-hidden
      />
      <span className={labelled ? 'card-ribbon-name' : 'card-ribbon-name sr-only'}>{name}</span>
    </li>
  )
}

/** Les rubans de technologies d'un projet, ceux de sa carte (spec §1.4). */
function TechnologyRibbons({ project }: { project: Project }) {
  return cardTechnologies(project.technologies).map((technology) => (
    <TechnologyRibbon key={technology.name} technology={technology} />
  ))
}

/**
 * Un ruban d'état (spec §4.1) : son point, fixe, à la couleur de l'état, puis son texte. Son identité
 * est l'état, comme celle d'un ruban de technologie est son nom (`TechnologyRibbon`).
 */
function StateRibbon({
  state,
  label,
}: {
  state: keyof ReturnType<typeof cardStates>
  label: string
}) {
  return (
    <li className="card-ribbon" data-ribbon={state}>
      <span className={`card-dot card-dot-${state}`} />
      {label}
    </li>
  )
}

/** Les rubans d'état d'un projet (spec §4.1), les états présents seulement. */
export function StateRibbons({ project }: { project: Project }) {
  const { ongoing, live } = cardStates(project)
  return (
    <>
      {ongoing && <StateRibbon state="ongoing" label={strings.ribbonOngoing} />}
      {live && <StateRibbon state="live" label={strings.ribbonLive} />}
    </>
  )
}

/**
 * La bande basse (spec §4.1), masquée : le nom du lien porte les états, et sa description les
 * technologies. Les rubans de technologies à gauche, les rubans d'état à droite, même passés à la
 * ligne. « Ouvrir » les remplace pendant la révélation au toucher : un texte du lien, jamais un
 * `<button>`, qu'un `<a>` ne peut contenir.
 */
function Band({ project }: { project: Project }) {
  return (
    <div className="card-band" aria-hidden>
      <ul className="card-ribbons">
        <TechnologyRibbons project={project} />
      </ul>
      <ul className="card-ribbons card-states">
        <StateRibbons project={project} />
      </ul>
      <span className="card-open">{strings.openCard}</span>
    </div>
  )
}

/**
 * Une carte polaroid (spec §4.1, §4.2) : le lien est la cellule de la table, au sens de
 * `TABLE_CELL_SELECTOR` — sa boîte de grille, sans transformation. Il contient, de l'extérieur vers
 * l'intérieur, la couche d'entrée, la pose et la face, qui porte le trombone, le post-it, la photo,
 * la sangle d'un projet en cours et la bande basse.
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

  return (
    <a
      ref={ref}
      href={projectPath(project.slug)}
      aria-describedby={descriptionId}
      data-table-cell
      data-revealed={revealed || undefined}
      className={`card card-${size}`}
      onClick={onClick}
    >
      <div className="card-entry">
        <div className="card-pose" style={poseStyle(project.slug)}>
          <div className="card-face">
            <Clip />
            <h2 className="postit postit-title card-postit">
              <span className="card-postit-text">{project.title}</span>
            </h2>
            <span className="sr-only">{cardNameSuffix(project)}</span>
            <Photo project={project} size={size} />
            {cardStates(project).ongoing && <Strap />}
            <Band project={project} />
          </div>
        </div>
      </div>
      <span id={descriptionId} hidden>
        {cardDescription(project)}
      </span>
    </a>
  )
}
