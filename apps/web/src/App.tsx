import { useEffect, useRef, useState } from 'react'
import { useProjects } from './api/useProjects.ts'
import { AuthorLinks } from './chrome/AuthorLinks.tsx'
import { SiteHeader } from './chrome/SiteHeader.tsx'
import { ProjectDialog } from './project/ProjectDialog.tsx'
import { useProjectAddress } from './project/useProjectAddress.ts'
import { strings } from './strings.ts'
import { Table } from './table/Table.tsx'

export default function App() {
  const table = useRef<HTMLElement>(null)
  const { status, projects, retry, retried } = useProjects()
  const { slug, open, close, dismiss } = useProjectAddress()
  const project = projects.find((candidate) => candidate.slug === slug)
  // La carte d'où la fiche s'ouvre, jusqu'à ce qu'elle y revienne : la fiche est à l'écran tout ce
  // temps, à l'adresse ou non.
  const [origin, setOrigin] = useState<HTMLElement | null>(null)
  const onScreen = project !== undefined || origin !== null

  const unknownAddress = status === 'loaded' && slug !== null && project === undefined

  useEffect(() => {
    if (unknownAddress) dismiss()
  }, [unknownAddress, dismiss])

  // Avant l'attribut de la fiche ouverte : une carte qui le lirait seul commencerait à s'effacer par
  // la feuille, sous la chorégraphie.
  useEffect(() => {
    document.documentElement.toggleAttribute('data-choreography', origin !== null)
  }, [origin])

  // La feuille lit l'attribut : le verrou de défilement, les cartes, l'entête et les liens de
  // l'auteur n'ont ni prop ni état de plus. Sa valeur dit si une barre classique a sa place à garder,
  // lue avant le verrou, qui la retire.
  useEffect(() => {
    const root = document.documentElement
    if (onScreen) {
      root.setAttribute('data-project-open', innerWidth > root.clientWidth ? 'scrollbar' : '')
    } else {
      root.removeAttribute('data-project-open')
    }
  }, [onScreen])

  useEffect(() => {
    document.title = project?.title ?? strings.siteName
  }, [project])

  // Une ouverture n'est prise qu'une fois la fiche revenue à sa carte (décision de #22).
  const openFromCard = (next: string, card: HTMLElement) => {
    if (origin) return
    setOrigin(card)
    open(next)
  }

  return (
    <>
      <SiteHeader />
      <Table
        ref={table}
        status={status}
        projects={projects}
        onRetry={retry}
        retried={retried}
        onOpen={openFromCard}
        projectOpen={onScreen}
      />
      <AuthorLinks table={table} />
      <ProjectDialog
        project={project}
        origin={origin}
        onClose={close}
        onLanded={() => setOrigin(null)}
      />
    </>
  )
}
