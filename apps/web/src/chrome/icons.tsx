import type { ReactNode } from 'react'

/**
 * Icônes au trait du prototype retenu (`cadre.html`, hors dépôt ; brief de #18, décision 10) :
 * tracées ici, sans paquet d'icônes (D27). Décoratives — l'élément qui les porte a son libellé —,
 * dans la couleur du texte, 20 px (spec §3.3).
 */
function StrokeIcon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="size-5"
    >
      {children}
    </svg>
  )
}

/** Soleil : le mode clair. */
export function SunIcon() {
  return (
    <StrokeIcon>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </StrokeIcon>
  )
}

/** Lune : le mode sombre. */
export function MoonIcon() {
  return (
    <StrokeIcon>
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
    </StrokeIcon>
  )
}
