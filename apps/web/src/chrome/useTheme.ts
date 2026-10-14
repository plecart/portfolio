import { useState, useSyncExternalStore } from 'react'

/** Un mode d'affichage : les deux palettes de la spec §2.1. */
type Mode = 'light' | 'dark'

/**
 * Clé du mode mémorisé dans `localStorage`. Écrite aussi dans `public/theme.js`, script classique
 * hors de la compilation, qui la relit avant le premier rendu : leur accord est prouvé par le
 * scénario « mémorisé et retrouvé après rechargement » (`e2e/theme.spec.ts`).
 */
const STORAGE_KEY = 'theme'

const DARK_SCHEME = '(prefers-color-scheme: dark)'

function systemMode(): Mode {
  return matchMedia(DARK_SCHEME).matches ? 'dark' : 'light'
}

/**
 * Applique un changement de palette d'un coup (spec §4.6 ; brief de #18, décision 10). Les couleurs
 * que la spec §2.7 fait glisser — survol, fond et filet de l'entête — glisseraient sinon au
 * changement de mode, quand le reste de la page bascule : `data-switching` coupe toute transition
 * (`src/tokens.css`) le temps du calcul de style qui pose la nouvelle palette, forcé ici avant de
 * le retirer.
 *
 * ponytail: côté système, la coupure vit dans l'écouteur de `change`, qui arrive parfois une image
 * après le changement ; un calcul de style qu'un script force entre les deux laisse encore glisser
 * (mesuré en e2e, par une lecture dans `requestAnimationFrame`). À reprendre si cela se voit.
 */
function withoutTransitions(change: () => void) {
  const root = document.documentElement
  root.dataset.switching = ''
  change()
  getComputedStyle(root).getPropertyValue('color')
  delete root.dataset.switching
}

function subscribeToSystem(onChange: () => void): () => void {
  const query = matchMedia(DARK_SCHEME)
  const change = () => withoutTransitions(onChange)
  query.addEventListener('change', change)
  return () => query.removeEventListener('change', change)
}

/** Le mode forcé sur `<html>` — posé avant le premier rendu par `public/theme.js` —, s'il y en a un. */
function forcedOnRoot(): Mode | undefined {
  const { theme } = document.documentElement.dataset
  return theme === 'light' || theme === 'dark' ? theme : undefined
}

/**
 * Force un mode, ou rend la main au système : `data-theme` sur `<html>`, que lisent les jetons
 * (`src/tokens.css`), et la valeur mémorisée. Un stockage refusé (navigation privée, cookies
 * bloqués) laisse le mode en place jusqu'au rechargement.
 */
function applyForced(mode: Mode | undefined) {
  const root = document.documentElement
  if (mode) root.dataset.theme = mode
  else delete root.dataset.theme

  try {
    if (mode) localStorage.setItem(STORAGE_KEY, mode)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Stockage refusé : le mode tient pour cette visite.
  }
}

/**
 * Le mode affiché et le geste du bouton de mode (spec §1.5 ; brief de #18, décision 2).
 *
 * Le mode affiché est le mode forcé s'il y en a un, celui du système sinon, suivi en direct. Le
 * clic vise toujours l'autre mode : contraire au système, il est forcé et mémorisé ; égal au
 * système, le forçage et la mémoire sont retirés, et le site suit de nouveau le système. Une valeur
 * mémorisée devenue égale au système (il a changé entre-temps) reste donc jusqu'au prochain clic.
 *
 * @returns `mode`, le mode affiché, et `toggle`, le clic.
 */
export function useTheme(): { mode: Mode; toggle: () => void } {
  const system = useSyncExternalStore(subscribeToSystem, systemMode)
  const [forced, setForced] = useState(forcedOnRoot)
  const mode = forced ?? system

  const toggle = () => {
    const next = mode === 'dark' ? 'light' : 'dark'
    const force = next === system ? undefined : next
    withoutTransitions(() => applyForced(force))
    setForced(force)
  }

  return { mode, toggle }
}
