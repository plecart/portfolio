import Markdown, { type MarkdownToJSX } from 'markdown-to-jsx/react'

/** Un bloc de texte : 12 px sous lui, 8 px dans une section (spec §4.3). */
const BLOCK_CLASSES = 'mb-(--s-3) in-[details]:mb-(--s-2)'

/** Une liste : le préflight de Tailwind lui a retiré son retrait et ses puces. */
const LIST_CLASSES = `${BLOCK_CLASSES} pl-[18px]`

/**
 * Le rendu de la fiche (ADR 0010, spec §4.3). Par défaut, seuls `script`, `iframe`, `style` et leurs
 * pareils sont échappés ; `disableParsingRawHTML` rend tout le HTML brut en texte. Sans `forceBlock`,
 * une seule ligne sortirait sans paragraphe ; sans `forceWrapper`, un seul bloc sans la classe de
 * l'appelant. Les URL dangereuses perdent leur `href` par le `sanitizer` par défaut.
 */
const OPTIONS: MarkdownToJSX.Options = {
  disableParsingRawHTML: true,
  forceBlock: true,
  forceWrapper: true,
  overrides: {
    p: { props: { className: BLOCK_CLASSES } },
    ul: { props: { className: `${LIST_CLASSES} list-disc` } },
    ol: { props: { className: `${LIST_CLASSES} list-decimal` } },
    a: { props: { className: 'text-(--accent) underline underline-offset-3' } },
  },
}

/**
 * Un texte en Markdown, rendu en éléments React : jamais d'insertion d'HTML.
 *
 * @param children Le Markdown.
 * @param className La classe de l'élément qui l'enveloppe.
 */
export function ProjectMarkdown({ children, className }: { children: string; className: string }) {
  return (
    <Markdown className={className} options={OPTIONS}>
      {children}
    </Markdown>
  )
}
