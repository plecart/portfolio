import { SiteHeader } from './chrome/SiteHeader.tsx'

export default function App() {
  return (
    <>
      <SiteHeader />
      {/* Le corps de page commence sous l'entête fixe de 56 px (spec §3.3). */}
      <main className="pt-14" />
    </>
  )
}
