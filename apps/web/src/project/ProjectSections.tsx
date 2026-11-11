import type { Project } from '../api/projects.ts'
import { sectionId, visibleSections } from './project.ts'
import { ProjectMarkdown } from './ProjectMarkdown.tsx'
import { useSectionAnchor } from './useSectionAnchor.ts'

/**
 * Les sections d'une fiche (spec §4.3), repliées, dans l'ordre de l'admin. Elles vivent sans état :
 * `<details>` se déroule seul, et la feuille écrit son signe, décoratif. Le titre d'une section est
 * un `<h3>`, au rang de « Technologies » et « Outils » (#265), que `<summary>` admet (spec HTML :
 * « phrasing content, optionally intermixed with heading content ») ; le préflight de Tailwind lui
 * laisse la typographie du `<summary>`.
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
            <h3>{title}</h3>
            <span className="project-section-sign" aria-hidden="true" />
          </summary>
          <ProjectMarkdown className="project-section-body">{body}</ProjectMarkdown>
        </details>
      ))}
    </div>
  )
}
