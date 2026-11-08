import type { ReactNode } from 'react'

/**
 * Icônes au trait du prototype retenu (`cadre.html`, hors dépôt ; brief de #18, décision 10) :
 * tracées ici, sans paquet d'icônes (D27). Décoratives — l'élément qui les porte a son libellé —,
 * dans la couleur du texte. Par défaut, celles de l'entête : 20 px (spec §3.3), trait de 1,6.
 */
function StrokeIcon({
  children,
  strokeWidth = 1.6,
  className = 'size-5',
}: {
  children: ReactNode
  strokeWidth?: number
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
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

/** Croix : fermer. */
export function CloseIcon() {
  return (
    <StrokeIcon>
      <path d="M6 6l12 12M18 6L6 18" />
    </StrokeIcon>
  )
}

/**
 * Une icône de la galerie et de sa couche plein écran : 18 px, comme ses flèches (spec §4.4), trait
 * de 1,8 comme au prototype.
 */
function GalleryIcon({ path }: { path: string }) {
  return (
    <StrokeIcon strokeWidth={1.8} className="size-[18px]">
      <path d={path} />
    </StrokeIcon>
  )
}

/** Chevron vers la gauche : l'image précédente. */
export function ChevronLeftIcon() {
  return <GalleryIcon path="M15 5l-7 7 7 7" />
}

/** Chevron vers la droite : l'image suivante. */
export function ChevronRightIcon() {
  return <GalleryIcon path="M9 5l7 7-7 7" />
}

/** Deux flèches vers les coins : agrandir l'image en plein écran. */
export function ExpandIcon() {
  return <GalleryIcon path="M14 4h6v6M10 20H4v-6M20 4l-6 6M4 20l6-6" />
}

/** Plus : zoom avant. */
export function ZoomInIcon() {
  return <GalleryIcon path="M12 5v14M5 12h14" />
}

/** Moins : zoom arrière. */
export function ZoomOutIcon() {
  return <GalleryIcon path="M5 12h14" />
}

/** Lien externe : celle des post-its de la fiche, 14 px (spec §4.3). */
export function ExternalLinkIcon() {
  return (
    <StrokeIcon className="size-3.5">
      <path d="M14 5h5v5M19 5l-9 9M11 5H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
    </StrokeIcon>
  )
}

/** Icônes des liens de l'auteur : 22 px (spec §3.4), trait de 1,5 comme au prototype. */
function AuthorLinkIcon({ children }: { children: ReactNode }) {
  return (
    <StrokeIcon strokeWidth={1.5} className="size-[22px]">
      {children}
    </StrokeIcon>
  )
}

/** GitHub. */
export function GitHubIcon() {
  return (
    <AuthorLinkIcon>
      <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />
    </AuthorLinkIcon>
  )
}

/** LinkedIn. */
export function LinkedInIcon() {
  return (
    <AuthorLinkIcon>
      <rect x="3" y="3" width="18" height="18" rx="3" />
      <path d="M8 10v7M8 7v.01M12 17v-7M16 17v-4a2 2 0 0 0-4 0" />
    </AuthorLinkIcon>
  )
}
