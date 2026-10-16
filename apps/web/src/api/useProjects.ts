import { useEffect, useState } from 'react'
import { fetchProjects, type Project } from './projects.ts'

/** Où en est la liste : en route, en échec, ou arrivée. */
export type ProjectsStatus = 'loading' | 'error' | 'loaded'

type ProjectsState = { status: ProjectsStatus; projects: Project[] }

const LOADING: ProjectsState = { status: 'loading', projects: [] }

/**
 * La liste des projets, chargée une fois au montage (spec §1.3) ; la requête est abandonnée au
 * démontage.
 *
 * @returns L'état du chargement, les projets — vides tant que la liste n'est pas arrivée — et
 *   `retry`, qui relance le même chargement sans recharger la page (spec §5.2).
 */
export function useProjects(): ProjectsState & { retry: () => void } {
  const [state, setState] = useState(LOADING)
  // Chaque tentative relance l'effet : « Réessayer » rejoue la requête de démarrage, rien d'autre.
  const [attempt, setAttempt] = useState(0)

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
  }, [attempt])

  const retry = () => {
    setState(LOADING)
    setAttempt((count) => count + 1)
  }

  return { ...state, retry }
}
