import { useEffect, useState } from 'react'
import { fetchProjects, type Project } from './projects.ts'

/** Où en est la liste : en route, en échec, ou arrivée. */
export type ProjectsStatus = 'loading' | 'error' | 'loaded'

/**
 * La liste des projets, chargée une fois au montage (spec §1.3) ; la requête est abandonnée au
 * démontage.
 *
 * @returns L'état du chargement et les projets — vides tant que la liste n'est pas arrivée.
 */
export function useProjects(): { status: ProjectsStatus; projects: Project[] } {
  const [state, setState] = useState<{ status: ProjectsStatus; projects: Project[] }>({
    status: 'loading',
    projects: [],
  })

  useEffect(() => {
    const controller = new AbortController()
    fetchProjects(controller.signal).then(
      (projects) => setState({ status: 'loaded', projects }),
      // Un abandon n'est pas un échec : c'est le démontage, ou le double effet du mode strict.
      () => {
        if (!controller.signal.aborted) setState({ status: 'error', projects: [] })
      },
    )
    return () => controller.abort()
  }, [])

  return state
}
