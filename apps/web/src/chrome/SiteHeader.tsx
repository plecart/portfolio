import { strings } from '../strings.ts'
import { ThemeToggle } from './ThemeToggle.tsx'
import { useHeaderScroll } from './useHeaderScroll.ts'

/**
 * Classes de l'entête, par intention. Les dimensions — 56 px de haut (`h-14`), nom en 15 px — sont
 * propres à l'objet (spec §2.2, §2.3) ; le reste vient des jetons.
 */
const HEADER_CLASSES = [
  // Boîte : fixe en haut, au-dessus de la table ; 16 px de marge sous 600 px, 24 au-delà (§3.3).
  'fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between px-(--s-4) sm:px-(--s-5)',
  // Décollée dès 1 px : papier à 94 % (§2.1) et filet, la seule ombre de l'entête (§2.5).
  'data-detached:bg-[color-mix(in_srgb,var(--paper)_94%,transparent)]',
  'data-detached:[box-shadow:0_1px_0_var(--line)]',
  // Sortie et retour en 240 ms, fond et filet en 150 ms (§2.7).
  '[transition:translate_var(--dur)_var(--ease-out),opacity_var(--dur-fast)_var(--ease-out),background-color_var(--dur-fast)_var(--ease-out),box-shadow_var(--dur-fast)_var(--ease-out)]',
  // Sortie par le haut ; en mouvement réduit, fondu sans translation (§6.3). Le focus clavier la
  // retient, pas un focus posé au pointeur (§3.3).
  'motion-safe:data-hidden:not-has-focus-visible:-translate-y-full',
  'motion-reduce:data-hidden:not-has-focus-visible:pointer-events-none',
  'motion-reduce:data-hidden:not-has-focus-visible:opacity-0',
  // Fiche ouverte : la même sortie, quel que soit le défilement (§3.3).
  'motion-safe:project-open:-translate-y-full',
  'motion-reduce:project-open:pointer-events-none',
  'motion-reduce:project-open:opacity-0',
].join(' ')

/**
 * L'entête du site (spec §1.12, §3.3) : une ligne fixe, le nom à gauche — seul titre de niveau 1
 * de la page (brief de #18, décision 9), lien vers l'accueil —, le bouton de mode à droite, seul
 * en phase 1 : la place « Chat » est absente du DOM. Transparente en haut de page, elle se
 * décolle au défilement, sort en descendant, revient en remontant, et reste visible tant qu'elle
 * contient le focus clavier. Fiche ouverte, elle sort aussi, le temps de la fiche.
 *
 * @param inert Recouverte par le cadre d'une fiche attendue à son adresse (§5.1) : ni le focus ni
 *   le pointeur ne l'atteignent.
 */
export function SiteHeader({ inert }: { inert: boolean }) {
  const { detached, hidden } = useHeaderScroll()

  return (
    <header
      inert={inert}
      data-detached={detached || undefined}
      data-hidden={hidden || undefined}
      className={HEADER_CLASSES}
    >
      <h1 className="text-[15px] font-semibold tracking-[.01em]">
        <a href="/" className="transition-colors hover:text-(--accent)">
          {strings.siteName}
        </a>
      </h1>
      <ThemeToggle />
    </header>
  )
}
