"""Écrans d'admin du contenu."""

from django.contrib import admin

from content.models import Technology


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin[Technology]):
    """Écran Technologie : nom, type, icône et site ; la liste montre le nom et le type."""

    list_display = ("name", "kind")
