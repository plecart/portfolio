import type { Project } from '../api/projects.ts'
import { sectionId, visibleSections } from './project.ts'
import { ProjectMarkdown } from './ProjectMarkdown.tsx'
import { useSectionAnchor } from './useSectionAnchor.ts'

/**
 * Les sections d'une fiche (spec §4.3), repliées, dans l'ordre de l'admin. Elles vivent sans état :
 * `<details>` se déroule seul, et la feuille écrit son signe, décoratif.
 *
 * @param sections Les sections du projet ; celles au corps vide ne sont pas rendues.
 */
export function ProjectSections({ sections }: { sections: Project['sections'] }) {
  useSectionAnchor()

  const shown = visibleSections(sections)
  if (shown.length === 0) return null

  return (
    <div className="project-sections">
      {shown.map(({ anchor, title, body }) => (
        <details key={anchor} id={sectionId(anchor)} className="project-section">
          <summary>
            {title}
            <span className="project-section-sign" aria-hidden="true" />
          </summary>
          <ProjectMarkdown className="project-section-body">{body}</ProjectMarkdown>
        </details>
      ))}
    </div>
  )
}
