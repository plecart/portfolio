import { strings } from '../strings.ts'
import { GitHubIcon, LinkedInIcon } from './icons.tsx'

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
 * Classes du pied de page, par intention. Les dimensions — filet de 48 × 1 px — sont propres à
 * l'objet (spec §3.4) ; le reste vient des jetons.
 */
const FOOTER_CLASSES = [
  // Une rangée centrée après la table : 48 px au-dessus, 32 dessous, 24 entre deux liens (§3.4).
  'relative flex items-center justify-center gap-(--s-5) pt-(--s-7) pb-(--s-6)',
  // Le filet, centré en haut de la marge intérieure, donc 48 px au-dessus des icônes.
  'before:absolute before:top-0 before:left-[calc(50%_-_24px)] before:h-px before:w-12 before:bg-(--line)',
].join(' ')

/** Classes d'un lien : une zone de 38 px (icône 22, marge 8 ; spec §3.4, §6.2). */
const LINK_CLASSES = [
  'flex rounded-full p-(--s-2) text-(--ink-2) hover:text-(--ink)',
  // Encre en 150 ms, montée de 2 px en 240 ms (§2.7) ; en mouvement réduit, l'encre seule (§6.3).
  '[transition:color_var(--dur-fast)_var(--ease-out),translate_var(--dur)_var(--ease-out)]',
  'motion-safe:hover:-translate-y-0.5',
].join(' ')

/**
 * Les liens de l'auteur (spec §1.13, §3.4) : GitHub puis LinkedIn, icônes au trait et libellé
 * accessible, dans le `<footer>` de la page — dernier dans l'ordre de tabulation.
 */
export function AuthorLinks() {
  return (
    <footer className={FOOTER_CLASSES}>
      {LINKS.map(({ href, label, Icon }) => (
        <a key={href} href={href} aria-label={label} className={LINK_CLASSES}>
          <Icon />
        </a>
      ))}
    </footer>
  )
}
