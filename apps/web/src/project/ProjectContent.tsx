import { DialogTitle } from '@radix-ui/react-dialog'
import type { Project } from '../api/projects.ts'
import { ExternalLinkIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { StateRibbons, TechnologyRibbon, TechnologyRibbons } from '../table/Card.tsx'
import type { Technology } from '../table/cards.ts'
import { projectFacts, splitStack } from './project.ts'
import { ProjectMarkdown } from './ProjectMarkdown.tsx'
import { ProjectSections } from './ProjectSections.tsx'

/** Un post-it de lien (spec §4.3), ouvert dans le même onglet, comme les liens de l'auteur. */
function ProjectLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} className="postit project-link">
      {label}
      <ExternalLinkIcon />
    </a>
  )
}

/** L'en-tête (spec §4.3) : le post-it du titre, les liens qui existent, les rubans de la carte. */
function ProjectHeader({ project }: { project: Project }) {
  return (
    <div className="project-head">
      <DialogTitle className="postit project-title">{project.title}</DialogTitle>
      {project.demo_url && <ProjectLink href={project.demo_url} label={strings.viewSite} />}
      {project.repository_url && (
        <ProjectLink href={project.repository_url} label={strings.viewRepository} />
      )}
      <ul className="card-ribbons project-ribbons">
        <TechnologyRibbons project={project} />
        <StateRibbons project={project} />
      </ul>
    </div>
  )
}

/** Un groupe de la stack (spec §4.3) : son intertitre et ses rubans ; rien sans technologie. */
function StackGroup({ title, technologies }: { title: string; technologies: Technology[] }) {
  if (technologies.length === 0) return null
  return (
    <>
      <h3 className="project-stack-title">{title}</h3>
      <ul className="card-ribbons project-ribbons project-stack">
        {technologies.map((technology) => (
          <TechnologyRibbon key={technology.name} technology={technology} labelled />
        ))}
      </ul>
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
        <StackGroup title={strings.technologies} technologies={technologies} />
        <StackGroup title={strings.tools} technologies={tools} />
        <ProjectMarkdown className="project-description">{project.description}</ProjectMarkdown>
        <ProjectSections sections={project.sections} />
      </div>
    </div>
  )
}
