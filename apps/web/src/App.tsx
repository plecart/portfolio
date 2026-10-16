import { useRef } from 'react'
import { useProjects } from './api/useProjects.ts'
import { AuthorLinks } from './chrome/AuthorLinks.tsx'
import { SiteHeader } from './chrome/SiteHeader.tsx'

export default function App() {
  const table = useRef<HTMLElement>(null)
  const { status } = useProjects()

  return (
    <>
      <SiteHeader />
      {/* Le corps de page commence sous l'entête fixe de 56 px (spec §3.3). */}
      <main ref={table} aria-busy={status === 'loading' || undefined} className="pt-14" />
      <AuthorLinks table={table} />
    </>
  )
}
