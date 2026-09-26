"""Écrans d'admin du contenu."""

from config import strings
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

from content.models import Technology

# Le côté de l'aperçu d'une icône dans la liste, en pixels : il tient dans une ligne de l'admin.
ICON_PREVIEW_SIZE = 24

# Le symbole « link » de Lucide (`icons/link.svg`, licences ISC et MIT), à 16 px. Tracé de la
# couleur du texte : bleu dans un lien de l'admin, gris sous la classe `quiet` — deux couleurs que
# le thème sombre redéfinit.
LINK_SYMBOL = mark_safe(
    '<svg aria-hidden="true" focusable="false" width="16" height="16" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
    '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'
    "</svg>"
)


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin[Technology]):
    """Écran Technologie : nom, type, icône et site. La liste les montre dans cet ordre, l'icône en
    petit et le site en symbole de lien."""

    list_display = ("name", "kind", "icon_preview", "website_link")

    @admin.display(description=strings.TECHNOLOGY_ICON)
    def icon_preview(self, technology: Technology) -> SafeString:
        """L'icône par `<img>`, où un SVG n'exécute aucun script ; texte alternatif vide, le nom
        est sur la même ligne. La taille passe par des attributs, pas par `style` : une CSP
        stricte (#6) refuse les styles en ligne."""
        return format_html(
            '<img src="{}" alt="" width="{}" height="{}">',
            technology.icon.url,
            ICON_PREVIEW_SIZE,
            ICON_PREVIEW_SIZE,
        )

    @admin.display(description=strings.TECHNOLOGY_WEBSITE)
    def website_link(self, technology: Technology) -> SafeString:
        """Le site en symbole de lien : cliquable s'il est renseigné, ouvert dans un nouvel onglet
        — `noopener` retire à la page ouverte tout accès à l'admin —, grisé et inerte sinon."""
        if not technology.website:
            return format_html(
                '<span class="quiet" role="img" aria-label="{}" title="{}">{}</span>',
                strings.TECHNOLOGY_WEBSITE_NONE,
                strings.TECHNOLOGY_WEBSITE_NONE,
                LINK_SYMBOL,
            )
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer" aria-label="{}" title="{}">'
            "{}</a>",
            technology.website,
            strings.TECHNOLOGY_WEBSITE_OPEN.format(name=technology.name),
            technology.website,
            LINK_SYMBOL,
        )
