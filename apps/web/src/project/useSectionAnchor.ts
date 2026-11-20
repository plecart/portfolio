import { useEffect } from 'react'
import { isSectionHash } from './project.ts'

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'

/**
 * Ouvre la section d'un fragment et la fait défiler en vue (spec §4.3, §6.3) ; un fragment sans
 * section ne fait rien.
 *
 * Le défilement part à la résolution de `document.fonts.ready`, jamais dans l'appel : un défilement
 * animé garde la cible prise à son départ, et ce qui précède la section bouge encore. La police
 * arrive quand elle arrive (`font-display: swap`) ; `fonts.ready` n'attend qu'un chargement déjà
 * commencé, ce que fait le texte de la page sous la fiche, rendu avant elle. Les groupes de la stack, eux, se replient à
 * l'arrivée juste après les effets des sections (`useStackFold`) : React vide ces effets, puis rend
 * aussitôt, dans la même pile d'appels, la mise à jour que demande l'effet de mise en page du
 * repli — avant toute réaction de promesse.
 *
 * @param hash Un fragment d'adresse (`location.hash`).
 * @returns La section, si le fragment en désigne une.
 */
function showSection(hash: string) {
  const section = isSectionHash(hash) ? document.getElementById(hash.slice(1)) : null
  if (!section) return null
  section.setAttribute('open', '')
  // ponytail: une police qui n'arrive jamais retient le défilement ; un délai borné, s'il le faut.
  void document.fonts.ready.then(() =>
    section.scrollIntoView({ behavior: matchMedia(REDUCED_MOTION).matches ? 'auto' : 'smooth' }),
  )
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
