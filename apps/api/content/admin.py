"""Écrans d'admin du contenu."""

from collections.abc import Sequence
from typing import Any, ClassVar

from config import strings
from django.contrib import admin
from django.forms import BaseInlineFormSet, ModelForm
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from django_stubs_ext import StrOrPromise

from content.models import Project, ProjectTechnology, Technology

# Le côté de l'aperçu d'une icône dans la liste, en pixels : il tient dans une ligne de l'admin.
ICON_PREVIEW_SIZE = 24

# Le symbole « link » de Lucide (`icons/link.svg`), dérivé de Feather, à 16 px. Tracé de la
# couleur du texte : bleu dans un lien de l'admin, gris sous la classe `quiet` — deux couleurs que
# le thème sombre redéfinit.
# Copyright (c) 2026 Lucide Icons and Contributors (ISC) ; Copyright (c) 2013-present Cole Bemis
# (MIT). Notices de permission : https://github.com/lucide-icons/lucide/blob/main/LICENSE
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
            '<img src="{url}" alt="" width="{size}" height="{size}">',
            url=technology.icon.url,
            size=ICON_PREVIEW_SIZE,
        )

    @admin.display(description=strings.TECHNOLOGY_WEBSITE)
    def website_link(self, technology: Technology) -> SafeString:
        """Le site en symbole de lien : cliquable s'il est renseigné, ouvert dans un nouvel onglet
        — `noopener` retire à la page ouverte tout accès à l'admin —, grisé et inerte sinon."""
        if not technology.website:
            return format_html(
                '<span class="quiet" role="img" aria-label="{label}" title="{label}">'
                "{symbol}</span>",
                label=strings.TECHNOLOGY_WEBSITE_NONE,
                symbol=LINK_SYMBOL,
            )
        return format_html(
            '<a href="{url}" target="_blank" rel="noopener noreferrer" aria-label="{label}" '
            'title="{url}">{symbol}</a>',
            url=technology.website,
            label=strings.TECHNOLOGY_WEBSITE_OPEN.format(name=technology.name),
            symbol=LINK_SYMBOL,
        )


# Le formset des lignes de technologie d'un projet, tel que l'admin le fabrique.
ProjectTechnologyFormSetBase = BaseInlineFormSet[
    ProjectTechnology, Project, ModelForm[ProjectTechnology]
]


class ProjectTechnologyFormSet(ProjectTechnologyFormSetBase):
    """Les lignes de technologie d'un projet, avec les messages du catalogue pour les deux règles
    que le formulaire compare entre ses lignes, avant la base.

    « Au moins une technologie » : seule règle hors base (décision 10). Le message par défaut de
    Django parle de formulaires ; `% {"num": …}`, que Django lui applique, laisse intact un texte
    sans champ de format.
    """

    default_error_messages: ClassVar[dict[str, StrOrPromise]] = {
        "too_few_forms": strings.PROJECT_TECHNOLOGIES_MISSING
    }

    def get_unique_error_message(self, unique_check: Sequence[str]) -> str:
        """Le doublon (projet, technologie), seule unicité que les lignes comparent : Django
        nommerait le champ par son identifiant anglais
        (`BaseModelFormSet.get_unique_error_message`)."""
        return strings.PROJECT_TECHNOLOGY_TAKEN


class ProjectTechnologyInline(admin.TabularInline[ProjectTechnology, Project]):
    """Les technologies d'un projet, en ligne sur l'écran Projet : chacune à sa position, saisie
    (décision 2) ; la liste se réaffiche triée après l'enregistrement (`Meta.ordering`)."""

    model = ProjectTechnology
    formset = ProjectTechnologyFormSet
    fields = ("technology", "position")
    min_num = 1

    def get_formset(
        self, request: HttpRequest, obj: Project | None = None, **kwargs: Any
    ) -> type[ProjectTechnologyFormSetBase]:
        """Le formset, qui refuse un projet sans technologie. L'admin ne transmet pas
        `validate_min` à la fabrique du formset (`InlineModelAdmin.get_formset`) : `min_num` seul
        rend une ligne obligatoire, qu'un formulaire sans ligne ou la suppression des lignes
        enregistrées contournent."""
        return super().get_formset(request, obj, validate_min=True, **kwargs)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin[Project]):
    """Écran Projet : tous les champs du projet et ses technologies en ligne, en un seul écran
    (PRD, US 34). Le slug se remplit depuis le titre à la saisie et reste modifiable
    (décision 3)."""

    list_display = ("title", "kind", "status", "showcase", "published")
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {"slug": ("title",)}
    inlines = (ProjectTechnologyInline,)
