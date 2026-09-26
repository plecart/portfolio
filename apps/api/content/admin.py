"""Écrans d'admin du contenu."""

from config import strings
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import SafeString

from content.models import Technology

# Le côté de l'aperçu d'une icône dans la liste, en pixels : il tient dans une ligne de l'admin.
ICON_PREVIEW_SIZE = 24


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin[Technology]):
    """Écran Technologie : nom, type, icône et site. La liste montre le nom, l'icône en petit, le
    type, et si un site est renseigné."""

    list_display = ("name", "icon_preview", "kind", "has_website")

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

    @admin.display(description=strings.TECHNOLOGY_WEBSITE, boolean=True)
    def has_website(self, technology: Technology) -> bool:
        """Vrai si un site est renseigné : l'admin l'affiche en ✔ ou ✘."""
        return bool(technology.website)
