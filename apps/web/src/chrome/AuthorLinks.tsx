import type { RefObject } from 'react'
import { strings } from '../strings.ts'
import { GitHubIcon, LinkedInIcon } from './icons.tsx'
import { useAuthorLinksPlacement } from './useAuthorLinksPlacement.ts'

/**
 * Les deux liens, dans l'ordre de la spec §3.4, ouverts dans le même onglet (brief de #18,
 * décision 10). Un lien de plus (places réservées de §1.13) est une entrée de plus.
 */
const LINKS = [
  { href: 'https://github.com/plecart', label: strings.authorGitHub, Icon: GitHubIcon },
  {
    href: 'https://www.linkedin.com/in/pacomebernier98/',
    label: strings.authorLinkedIn,
    Icon: LinkedInIcon,
  },
] as const

/**
 * Classes du `<footer>`, par intention, sous ses deux formes : pied de page par défaut, colonne
 * quand `data-docked` est posé. Les dimensions — filet de 48 × 1 px, disques et zones de 36 et
 * 38 px — sont propres à l'objet (spec §3.4, §6.2) ; le reste vient des jetons.
 */
const FOOTER_CLASSES = [
  // Pied de page : une rangée centrée après la table, 48 px au-dessus, 32 dessous, 24 entre deux.
  'group relative flex items-center justify-center gap-(--s-5) pt-(--s-7) pb-(--s-6)',
  // Le filet, centré en haut de la marge intérieure, donc 48 px au-dessus des icônes.
  'before:absolute before:top-0 before:left-[calc(50%_-_24px)] before:h-px before:w-12 before:bg-(--line)',
  // Colonne : fixe en bas à droite, à 24 px des bords, 8 px entre deux disques, sans filet.
  'data-docked:fixed data-docked:right-(--s-5) data-docked:bottom-(--s-5) data-docked:z-40',
  'data-docked:flex-col data-docked:gap-(--s-2) data-docked:p-0 data-docked:before:hidden',
].join(' ')

/** Classes d'un lien, sous les deux mêmes formes (`group-data-docked:` lit celle du `<footer>`). */
const LINK_CLASSES = [
  // Pied de page : une zone de 38 px (icône 22, marge 8), sans disque.
  'flex items-center justify-center rounded-full p-(--s-2) text-(--ink-2) hover:text-(--ink)',
  // Colonne : un disque de 36 px, papier, ombre au repos.
  'group-data-docked:size-9 group-data-docked:p-0 group-data-docked:bg-(--paper)',
  'group-data-docked:[box-shadow:var(--shadow-rest)]',
  // Encre en 150 ms, montée de 2 px en 240 ms (§2.7) ; en mouvement réduit, l'encre seule (§6.3).
  '[transition:color_var(--dur-fast)_var(--ease-out),translate_var(--dur)_var(--ease-out)]',
  'motion-safe:hover:-translate-y-0.5',
].join(' ')

/**
 * Les liens de l'auteur (spec §1.13, §3.4) : GitHub puis LinkedIn, icônes au trait et libellé
 * accessible, dans le `<footer>` de la page — dernier dans l'ordre de tabulation sous ses deux
 * formes. Colonne fixe ou pied de page selon la marge mesurée à côté de la table.
 *
 * @param table La table, dont les cellules décident de la forme (`useAuthorLinksPlacement`).
 */
export function AuthorLinks({ table }: { table: RefObject<HTMLElement | null> }) {
  const docked = useAuthorLinksPlacement(table) === 'column'

  return (
    <footer data-docked={docked || undefined} className={FOOTER_CLASSES}>
      {LINKS.map(({ href, label, Icon }) => (
        <a key={href} href={href} aria-label={label} className={LINK_CLASSES}>
          <Icon />
        </a>
      ))}
    </footer>
  )
}
