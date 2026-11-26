import { useEffect, useRef, useState } from 'react'
import { useProjects } from './api/useProjects.ts'
import { AuthorLinks } from './chrome/AuthorLinks.tsx'
import { SiteHeader } from './chrome/SiteHeader.tsx'
import { ProjectDialog } from './project/ProjectDialog.tsx'
import { ProjectFrame } from './project/ProjectFrame.tsx'
import { useProjectAddress } from './project/useProjectAddress.ts'
import { strings } from './strings.ts'
import { Table } from './table/Table.tsx'

/**
 * La valeur de `data-project-open` (spec §3.2) : `scrollbar` quand la page défile sous une barre
 * classique, que le verrou retire et dont la feuille garde la place ; vide sans défilement, ou sous
 * une barre qui ne prend pas de place, superposée ou masquée. Se lit sur la page déjà verrouillée :
 * sa hauteur, puis la barre d'une sonde qui défile toujours — 15 px sous une barre classique, 0
 * sous `--hide-scrollbars` comme sous `OverlayScrollbar` (Chromium de Playwright 1.64.1, mesuré le
 * 2026-11-26) ; `scrollbar-gutter` seul garde 10 px aux barres masquées.
 */
function scrollbarToKeep(): 'scrollbar' | '' {
  const root = document.documentElement
  if (root.scrollHeight <= root.clientHeight) return ''
  const probe = document.createElement('div')
  probe.style.position = 'absolute'
  probe.style.overflow = 'scroll'
  document.body.append(probe)
  const classic = probe.offsetWidth > probe.clientWidth
  probe.remove()
  return classic ? 'scrollbar' : ''
}

export default function App() {
  const table = useRef<HTMLElement>(null)
  const { status, projects, retry, retried } = useProjects()
  const { slug, open, close, dismiss } = useProjectAddress()
  const project = projects.find((candidate) => candidate.slug === slug)
  // La carte d'où la fiche s'ouvre, jusqu'à ce qu'elle y revienne : la fiche est à l'écran tout ce
  // temps, à l'adresse ou non.
  const [origin, setOrigin] = useState<HTMLElement | null>(null)
  // À l'adresse d'une fiche, la liste en route : la fiche est déjà à l'écran, par son cadre (§5.1).
  const awaiting = status === 'loading' && slug !== null
  const onScreen = awaiting || project !== undefined || origin !== null
  // Le cadre de fiche, posé pendant l'attente, reste sous la fiche arrivée jusqu'à la fin de son
  // fondu, qui le recouvre (`onEntered`) ; sans fiche — slug inconnu, échec, fermeture —, il part.
  const [framed, setFramed] = useState(awaiting)
  const stillFramed = awaiting || (framed && project !== undefined)
  if (stillFramed !== framed) setFramed(stillFramed)

  const unknownAddress = status === 'loaded' && slug !== null && project === undefined

  useEffect(() => {
    if (unknownAddress) dismiss()
  }, [unknownAddress, dismiss])

  useEffect(() => {
    document.documentElement.toggleAttribute('data-choreography', origin !== null)
  }, [origin])

  // La feuille lit l'attribut : le verrou de défilement, les cartes, l'entête et les liens de
  // l'auteur n'ont ni prop ni état de plus. Sa valeur, `scrollbarToKeep`, se relit à l'arrivée de
  // la liste, qui fait la hauteur de la page sous une fiche attendue à son adresse.
  useEffect(() => {
    const root = document.documentElement
    if (onScreen) {
      root.setAttribute('data-project-open', scrollbarToKeep())
    } else {
      root.removeAttribute('data-project-open')
    }
  }, [onScreen, projects])

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
      <SiteHeader inert={awaiting} />
      <Table
        ref={table}
        status={status}
        projects={projects}
        onRetry={retry}
        retried={retried}
        onOpen={openFromCard}
        projectOpen={onScreen}
      />
      <AuthorLinks table={table} inert={awaiting} />
      {framed && <ProjectFrame />}
      <ProjectDialog
        project={project}
        origin={origin}
        onClose={close}
        onLanded={() => setOrigin(null)}
        onEntered={() => setFramed(false)}
      />
    </>
  )
}
