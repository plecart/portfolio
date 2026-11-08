"""Écrans d'admin du contenu."""

import math
from collections.abc import Sequence
from typing import Any, ClassVar

from config import strings
from django.contrib import admin
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.db.models import Field
from django.forms import CharField, ModelForm
from django.forms import Field as FormField
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from django_stubs_ext import StrOrPromise

from content.inlines import SortableFormSet, SortableInline
from content.models import (
    COVER_MIN_SIDE,
    GalleryImage,
    Project,
    ProjectTechnology,
    Section,
    Technology,
)
from content.preview import MarkdownFieldsAdmin

# Le côté de l'aperçu d'une icône dans la liste, en pixels : il tient dans une ligne de l'admin.
ICON_PREVIEW_SIZE = 24

# Le côté du cadre carré où l'aperçu d'une image du projet tient entière, en pixels (décision 11).
IMAGE_PREVIEW_SIZE = 120

# La classe de l'aperçu d'une image, que `image_preview.css` lit.
IMAGE_PREVIEW_CLASS = "image-preview"

# Le refus d'un champ d'une image laissé vide : celui de la contrainte qui dit la même chose.
IMAGE_REQUIRED_MESSAGES = {
    "original": strings.IMAGE_ORIGINAL_MISSING,
    "caption": strings.IMAGE_CAPTION_MISSING,
}

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


class ProjectTechnologyFormSet(SortableFormSet[ProjectTechnology, Project]):
    """Les lignes de technologie d'un projet, avec les messages du catalogue pour les deux règles
    que le formulaire compare entre ses lignes, avant la base : le doublon (projet, technologie),
    et « au moins une technologie ».

    « Au moins une technologie » : règle hors base (décision 10). Le message par défaut de Django
    parle de formulaires ; `% {"num": …}`, que Django lui applique, laisse intact un texte sans
    champ de format.
    """

    default_error_messages: ClassVar[dict[str, StrOrPromise]] = {
        "too_few_forms": strings.PROJECT_TECHNOLOGIES_MISSING
    }
    unique_error_message = strings.PROJECT_TECHNOLOGY_TAKEN


class ProjectTechnologyInline(SortableInline[ProjectTechnology, Project]):
    """Les technologies d'un projet, en ligne sur l'écran Projet, dans l'ordre stocké
    (`Meta.ordering`) et ordonnées par glisser-déposer (décision 2, ADR 0013). Au moins une."""

    model = ProjectTechnology
    formset = ProjectTechnologyFormSet
    fields = ("move", "technology", "position")
    min_num = 1

    def formfield_for_dbfield(
        self, db_field: Field[Any, Any], request: HttpRequest, **kwargs: Any
    ) -> FormField | None:
        """La liste des technologies, sans les raccourcis qui modifient, montrent ou suppriment la
        technologie choisie : l'écran Projet choisit des technologies, il ne les édite pas, et
        supprimer depuis une ligne retirerait la technologie de tout le site. L'ajout d'une
        technologie manquante reste."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is not None and isinstance(formfield.widget, RelatedFieldWidgetWrapper):
            formfield.widget.can_change_related = False
            formfield.widget.can_view_related = False
            formfield.widget.can_delete_related = False
        return formfield


class GalleryFormSet(SortableFormSet[GalleryImage, Project]):
    """Les images d'un projet : une au moins, brouillon compris, et la première — la couverture —
    carrée, d'au moins `COVER_MIN_SIDE` px de côté (brief de #9, décisions 2, 4 et 8). Ces règles
    lisent les images ensemble : la base ne peut pas les porter, le formulaire les tient, comme
    « au moins une technologie ». Le message par défaut de Django pour le minimum parle de
    formulaires."""

    default_error_messages: ClassVar[dict[str, StrOrPromise]] = {
        "too_few_forms": strings.PROJECT_IMAGES_MISSING
    }

    def clean(self) -> None:
        """Les règles de `SortableFormSet`, puis la couverture : la première des images gardées,
        dans l'ordre que l'enregistrement donne à la galerie (`_rank`), refusée sous sa ligne si
        elle n'est pas carrée, ou si son petit côté fait moins de `COVER_MIN_SIDE` px. Elle est
        jugée à chaque enregistrement du projet, son fichier changé ou non : une couverture
        enregistrée sous une borne plus basse est refusée, sans tolérance (brief de #242,
        décision 2). Une ligne déjà refusée n'est pas jugée une seconde fois : ses dimensions ne
        décrivent rien d'admis. Une image glissée en tête devient la couverture, et en reçoit les
        règles."""
        super().clean()
        kept = self.kept_forms()
        if not kept:
            return
        # ponytail: seules les lignes de l'envoi sont jugées ; une image enregistrée ailleurs
        # depuis l'ouverture de l'écran (un second onglet) peut se ranger devant la couverture
        # jugée. Juger aussi ces lignes, comme `validate_unique`, si deux onglets deviennent un
        # usage.
        cover = min(kept, key=self._rank)
        if cover.errors:
            return
        width, height = cover.instance.width, cover.instance.height
        if width != height:
            cover.add_error(None, strings.GALLERY_COVER_NOT_SQUARE)
        if min(width, height) < COVER_MIN_SIDE:
            cover.add_error(None, strings.GALLERY_COVER_TOO_SMALL)

    def _rank(self, form: ModelForm[GalleryImage]) -> float:
        """Le rang d'une ligne dans la galerie enregistrée : sa position (`position_of`) ; une
        ligne neuve sans position vient après toutes les autres, là où `save_new` la range. À
        rang égal, `min` garde l'ordre du formulaire, celui de l'enregistrement."""
        position = self.position_of(form)
        return math.inf if position is None else position


class GalleryInline(SortableInline[GalleryImage, Project]):
    """La galerie d'un projet, sous ses technologies : des images que l'auteur ajoute, retire et
    ordonne par glisser-déposer, puis enregistre une fois ; la première est la couverture
    (décision 11, ADR 0013). Son modèle n'a aucune unicité qui lise le projet : à position égale,
    l'ordre de saisie.

    Chaque image enregistrée montre son aperçu, et son état en texte, sous son libellé : seul le
    worker de #12 le fait avancer (décision 5).
    """

    # La feuille des aperçus ; le script et la feuille des lignes ordonnables viennent de
    # `SortableInline`, Django réunit les deux le long de l'héritage.
    class Media(SortableInline.Media):
        css: ClassVar[dict[str, tuple[str, ...]]] = {"all": ("content/admin/image_preview.css",)}

    model = GalleryImage
    formset = GalleryFormSet
    fields = ("move", "preview", "original", "caption", "state", "position")
    readonly_fields = ("move", "preview", "state")
    verbose_name_plural = strings.GALLERY_HEADING
    min_num = 1
    # Une ligne neuve en plus des images enregistrées, comme la fiche technique : l'auteur en
    # ajoute d'autres par le bouton de l'écran. Aucune à l'ajout (`get_extra`).
    extra = 1

    def get_extra(self, request: HttpRequest, obj: Project | None = None, **kwargs: Any) -> int:
        """Les lignes neuves en plus : aucune sur l'écran d'ajout, où la ligne obligatoire
        (`min_num`) est déjà vide — une seule ligne s'y montre (arrêt visuel du 2026-10-14) ;
        `extra` sur un projet enregistré."""
        return 0 if obj is None else self.extra

    @admin.display(description=strings.IMAGE_PREVIEW)
    def preview(self, image: GalleryImage) -> str:
        """L'original enregistré, dans un `<img>` : un cadre carré nommé en attributs, où
        `image_preview.css` le fait tenir entier, proportions gardées — l'orientation EXIF
        comprise, que les dimensions stockées ignorent. Jamais de `style` en ligne : une CSP
        stricte (#6) le refuse. La légende sert de texte alternatif (spec §4.4).

        Rien pour une image dont l'original n'est pas stocké : une ligne neuve, ou un fichier
        choisi dans un envoi refusé — l'aperçu apparaît après l'enregistrement (décision 3)."""
        if not image.original.stored:
            return ""
        return format_html(
            '<img src="{url}" alt="{alt}" width="{side}" height="{side}" class="{preview}">',
            url=image.original.url,
            alt=image.caption,
            side=IMAGE_PREVIEW_SIZE,
            preview=IMAGE_PREVIEW_CLASS,
        )

    def formfield_for_dbfield(
        self, db_field: Field[Any, Any], request: HttpRequest, **kwargs: Any
    ) -> FormField | None:
        """Le champ de Django ; l'original et la légende, refusés vides avec le message du
        catalogue que leurs contraintes portent."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        message = IMAGE_REQUIRED_MESSAGES.get(db_field.name)
        if formfield is not None and message is not None:
            formfield.error_messages["required"] = message
        return formfield


class SectionFormSet(SortableFormSet[Section, Project]):
    """Les sections d'un projet, avec le message du catalogue pour la seule unicité que le
    formulaire compare entre ses lignes, avant la base : l'ancre."""

    unique_error_message = strings.SECTION_ANCHOR_TAKEN


class SectionInline(MarkdownFieldsAdmin[Section], SortableInline[Section, Project]):
    """La fiche technique d'un projet, en ligne sur l'écran Projet, sous sa galerie : des
    sections libres que l'auteur ajoute, retire et ordonne par glisser-déposer (D55, D57).
    L'ancre se remplit depuis le titre à la saisie et reste modifiable, comme le slug du
    projet ; le corps, en Markdown, a son aperçu."""

    model = Section
    formset = SectionFormSet
    fields = ("move", "title", "anchor", "body", "position")
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {"anchor": ("title",)}
    markdown_fields = ("body",)
    verbose_name_plural = strings.SECTIONS_HEADING
    # Une seule ligne neuve à l'ouverture, et non les trois de Django : une section, son corps
    # surtout, tient de la place ; l'auteur en ajoute d'autres par le bouton de l'écran.
    extra = 1

    def formfield_for_dbfield(
        self, db_field: Field[Any, Any], request: HttpRequest, **kwargs: Any
    ) -> FormField | None:
        """Le corps, refusé vide avec le message du catalogue, comme s'il était fait d'espaces : la
        contrainte de la base dit la même chose."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if isinstance(formfield, CharField) and db_field.name == "body":
            formfield.error_messages["required"] = strings.SECTION_BODY_MISSING
        return formfield


@admin.register(Project)
class ProjectAdmin(MarkdownFieldsAdmin[Project], admin.ModelAdmin[Project]):
    """Écran Projet : tous les champs du projet, ses technologies en ligne, sa galerie — dont la
    première image est la couverture —, puis sa fiche technique, en un seul écran (PRD, US 34). Le
    slug se remplit depuis le titre à la saisie et reste modifiable (décision 3) ; la description,
    en Markdown, a son aperçu."""

    list_display = ("title", "kind", "status", "showcase", "published")
    markdown_fields = ("description",)
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {"slug": ("title",)}
    inlines = (ProjectTechnologyInline, GalleryInline, SectionInline)
