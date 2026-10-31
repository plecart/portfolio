import { useRef } from 'react'
import { useProjects } from './api/useProjects.ts'
import { AuthorLinks } from './chrome/AuthorLinks.tsx'
import { SiteHeader } from './chrome/SiteHeader.tsx'
import { Table } from './table/Table.tsx'

export default function App() {
  const table = useRef<HTMLElement>(null)
  const { status, projects, retry, retried } = useProjects()

  return (
    <>
      <SiteHeader />
      <Table ref={table} status={status} projects={projects} onRetry={retry} retried={retried} />
      <AuthorLinks table={table} />
    </>
  )
}
