import { useCallback, useEffect, useState } from 'react'
import { projectPath, slugFromPath } from './project.ts'

/**
 * L'adresse du site, d'où dérive l'état « fiche ouverte » (spec §3.1, §3.2) : l'API History native,
 * sans bibliothèque de routage, pour deux adresses, `/` et `/projets/<slug>`. Une entrée d'historique
 * par ouverture, marquée `fromTable` : fermer revient alors dessus, ce qui laisse « suivant » rouvrir
 * la fiche. Sans cette marque — une arrivée directe —, revenir sortirait du site, et l'adresse se
 * remplace par `/`.
 *
 * @returns `slug`, celui de l'adresse ; `open` et `close`, l'ouverture depuis la table et la
 *   fermeture ; `dismiss`, le retour à `/` sans passer par l'historique.
 */
export function useProjectAddress() {
  const [slug, setSlug] = useState(() => slugFromPath(location.pathname))

  useEffect(() => {
    const readAddress = () => setSlug(slugFromPath(location.pathname))
    addEventListener('popstate', readAddress)
    return () => removeEventListener('popstate', readAddress)
  }, [])

  const open = (next: string) => {
    history.pushState({ fromTable: true }, '', projectPath(next))
    setSlug(next)
  }

  const dismiss = useCallback(() => {
    history.replaceState(null, '', '/')
    setSlug(null)
  }, [])

  // `history.back()` n'agit qu'au `popstate` suivant. L'état passe d'emblée à « fermée » : le dialogue,
  // contrôlé, n'appelle plus `close` d'ici là, et un double clic ne recule pas de deux entrées.
  const close = () => {
    if (history.state?.fromTable) {
      history.back()
      setSlug(null)
    } else dismiss()
  }

  return { slug, open, close, dismiss }
}
