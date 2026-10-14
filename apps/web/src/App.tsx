import { useRef } from 'react'
import { AuthorLinks } from './chrome/AuthorLinks.tsx'
import { SiteHeader } from './chrome/SiteHeader.tsx'

export default function App() {
  const table = useRef<HTMLElement>(null)

  return (
    <>
      <SiteHeader />
      {/* Le corps de page commence sous l'entête fixe de 56 px (spec §3.3). */}
      <main ref={table} className="pt-14" />
      <AuthorLinks table={table} />
    </>
  )
}
