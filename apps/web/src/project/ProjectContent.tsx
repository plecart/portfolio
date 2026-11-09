import { DialogTitle } from '@radix-ui/react-dialog'
import { useId, useState } from 'react'
import type { Project } from '../api/projects.ts'
import { ExternalLinkIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { StateRibbons, TechnologyRibbon } from '../table/Card.tsx'
import { cardStates, type Technology } from '../table/cards.ts'
import { projectFacts, splitStack, stackButtonName, type StackKind } from './project.ts'
import { ProjectMarkdown } from './ProjectMarkdown.tsx'
import { ProjectSections } from './ProjectSections.tsx'
import { useStackFold } from './useStackFold.ts'

/** Un post-it de lien (spec §4.3), ouvert dans le même onglet, comme les liens de l'auteur. */
function ProjectLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} className="postit project-link">
      {label}
      <ExternalLinkIcon />
    </a>
  )
}

/**
 * L'en-tête (spec §4.3) : le post-it du titre, les liens qui existent, puis les rubans d'état ; sans
 * état, ni leur rangée ni sa marge basse. Les technologies de la carte sont dans la stack, où leurs
 * rubans volent (`useChoreography`).
 */
function ProjectHeader({ project }: { project: Project }) {
  const { ongoing, live } = cardStates(project)
  return (
    <div className="project-head">
      <DialogTitle className="postit postit-title project-title">{project.title}</DialogTitle>
      {project.demo_url && <ProjectLink href={project.demo_url} label={strings.viewSite} />}
      {project.repository_url && (
        <ProjectLink href={project.repository_url} label={strings.viewRepository} />
      )}
      {(ongoing || live) && (
        <ul className="card-ribbons project-ribbons">
          <StateRibbons project={project} />
        </ul>
      )}
    </div>
  )
}

/**
 * Les rubans d'un groupe de la stack, dans l'ordre de l'admin, sur deux rangées au plus (spec §4.3,
 * `useStackFold`). Ceux qui n'y tiennent pas sont retirés du rendu ; le ruban-bouton prend la
 * dernière place de la deuxième rangée, « +N ⌄ », et les déplie sur place : il devient alors
 * « Réduire ⌃ », en fin de liste, et garde son nom (`stackButtonName`) et le focus (spec §6.2).
 * L'état déplié vit avec la fiche rendue : chaque ouverture montre le groupe replié.
 *
 * @param kind Le groupe : ses technologies, ou ses outils.
 */
function StackList({ kind, technologies }: { kind: StackKind; technologies: Technology[] }) {
  const id = useId()
  const [expanded, setExpanded] = useState(false)
  const [list, shown] = useStackFold(expanded)
  // Le temps d'une mesure : tous les rubans, et le ruban-bouton à son compte le plus large.
  // ponytail: le « +N » se mesure à ce compte, pas au sien : un chiffre de trop au plus, donc parfois
  // un ruban de moins qu'il n'en tiendrait, jamais une troisième rangée ; le mesurer à son compte
  // réel demanderait une seconde mesure, une fois le repli connu.
  const measuring = shown === undefined
  const hidden = technologies.length - (shown ?? 0)
  return (
    <ul id={id} ref={list} className="card-ribbons project-ribbons project-stack">
      {(expanded || measuring ? technologies : technologies.slice(0, shown)).map((technology) => (
        <TechnologyRibbon key={technology.name} technology={technology} labelled />
      ))}
      {hidden > 0 && (
        <li className="card-ribbon project-more">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={id}
            aria-label={stackButtonName(kind, hidden)}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded && !measuring ? strings.collapseStack : `+${hidden} ${strings.expandStack}`}
          </button>
        </li>
      )}
    </ul>
  )
}

/**
 * Un groupe de la stack (spec §4.3) : son intertitre, « Technologies » ou « Outils », et ses rubans
 * (`StackList`) ; rien sans technologie.
 */
function StackGroup({ kind, technologies }: { kind: StackKind; technologies: Technology[] }) {
  if (technologies.length === 0) return null
  return (
    <>
      <h3 className="project-stack-title">{strings[kind]}</h3>
      <StackList kind={kind} technologies={technologies} />
    </>
  )
}

/**
 * La colonne de lecture d'une fiche (spec §3.2, §4.3) : l'en-tête, puis ce qui défile, arrêt de
 * tabulation (§6.2). Sans lien ni section, rien d'autre n'y porterait le clavier : le bouton
 * « Fermer » est hors de la colonne au bureau et, fixe sur téléphone, hors de portée du défilement
 * du panneau (Chromium 156, mesuré le 2026-11-01).
 *
 * @param project Le projet.
 */
export function ProjectContent({ project }: { project: Project }) {
  const { technologies, tools } = splitStack(project.technologies)
  return (
    <div className="project-reading">
      <ProjectHeader project={project} />
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className="project-scroll" tabIndex={0} role="region" aria-label={strings.projectReading}>
        <p className="project-facts">{projectFacts(project)}</p>
        <p className="project-summary">{project.summary}</p>
        <StackGroup kind="technologies" technologies={technologies} />
        <StackGroup kind="tools" technologies={tools} />
        <ProjectMarkdown className="project-description">{project.description}</ProjectMarkdown>
        <ProjectSections sections={project.sections} />
      </div>
    </div>
  )
}
