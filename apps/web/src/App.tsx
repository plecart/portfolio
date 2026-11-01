import { useEffect, useRef } from 'react'
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

  const unknownAddress = status === 'loaded' && slug !== null && project === undefined

  useEffect(() => {
    if (unknownAddress) dismiss()
  }, [unknownAddress, dismiss])

  useEffect(() => {
    document.title = project?.title ?? strings.siteName
  }, [project])

  return (
    <>
      <SiteHeader />
      <Table
        ref={table}
        status={status}
        projects={projects}
        onRetry={retry}
        retried={retried}
        onOpen={open}
      />
      <AuthorLinks table={table} />
      <ProjectDialog project={project} onClose={close} />
    </>
  )
}
