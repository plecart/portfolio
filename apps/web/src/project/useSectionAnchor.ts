import { useEffect } from 'react'
import { isSectionHash } from './project.ts'

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'

/**
 * Ouvre la section d'un fragment et la fait défiler en vue (spec §4.3, §6.3) ; un fragment sans
 * section ne fait rien.
 *
 * @param hash Un fragment d'adresse (`location.hash`).
 * @returns La section, si le fragment en désigne une.
 */
function showSection(hash: string) {
  const section = isSectionHash(hash) ? document.getElementById(hash.slice(1)) : null
  section?.setAttribute('open', '')
  section?.scrollIntoView({ behavior: matchMedia(REDUCED_MOTION).matches ? 'auto' : 'smooth' })
  return section
}

/**
 * Suit un lien de la fiche vers une section (spec §4.3) : l'adresse se remplace, une entrée par
 * ouverture (§3.1), et garde `history.state`, dont dépend la fermeture (`useProjectAddress`). Le
 * focus va à la section : le parcours au clavier repart d'elle.
 *
 * @param hash Le fragment du lien.
 */
export function goToSection(hash: string) {
  history.replaceState(history.state, '', hash)
  showSection(hash)?.querySelector('summary')?.focus({ preventScroll: true })
}

/**
 * Suit l'ancre de l'adresse, tant que les sections sont montées : celle de l'ouverture, puis chaque
 * `hashchange`. Les `<details>` arrivent après le chargement de la page : l'ouverture native par
 * fragment ne les trouve pas.
 */
export function useSectionAnchor() {
  useEffect(() => {
    const showAnchor = () => void showSection(location.hash)
    showAnchor()
    addEventListener('hashchange', showAnchor)
    return () => removeEventListener('hashchange', showAnchor)
  }, [])
}
