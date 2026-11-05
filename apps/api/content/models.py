"""Modèles du contenu : les technologies, les projets, les sections de leur fiche technique et
les images de leur galerie, dont la première est la couverture.

Toute règle que la base peut porter y est une contrainte du modèle (décision 10 du brief de #7) :
son code, identifiant stable du refus, est nommé sur la contrainte ; son message, texte affiché,
vient du catalogue. Django la vérifie dans `full_clean()` — donc dans l'admin —, Postgres la
garantit pour toute ligne écrite hors de l'admin. Quand un champ la vérifie déjà (`blank`,
`choices`), Django écarte la contrainte des champs en erreur : l'admin n'affiche jamais deux
messages pour une même faute.
"""

from collections.abc import Mapping
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict

from config import strings
from django.db import models
from django.db.models.functions import Length, Lower
from django.db.models.lookups import LessThanOrEqual

from content.images import OriginalField, delete_folder_after_commit, validate_original
from content.stored_files import Removal, StoredFiles, delete_file_after_commit
from content.validators import validate_svg

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class TechnologyKind(models.TextChoices):
    """Le type d'une technologie. Valeurs stockées en anglais, exposées telles quelles par l'API
    (ADR 0010).

    Au niveau du module, et non dans `Technology` : la contrainte de `Meta` qui borne le type à
    ces valeurs ne voit pas les noms du corps de la classe qui l'entoure.
    """

    LANGUAGE = "language", strings.TECHNOLOGY_KIND_LANGUAGE
    FRAMEWORK = "framework", strings.TECHNOLOGY_KIND_FRAMEWORK
    INFRASTRUCTURE = "infrastructure", strings.TECHNOLOGY_KIND_INFRASTRUCTURE
    TOOL = "tool", strings.TECHNOLOGY_KIND_TOOL


class Technology(StoredFiles):
    """Une technologie qu'un projet emploie (cadrage §6.1).

    Son icône sort du stockage, seule, une fois validée la transaction qui supprime la technologie
    ou remplace son icône (`StoredFiles`) ; une technologie qu'un projet emploie ne se supprime pas,
    et garde son icône.
    """

    # Borne technique : la spec ne borne pas ce nom.
    name: models.CharField[str, str] = models.CharField(strings.TECHNOLOGY_NAME, max_length=50)
    kind: models.CharField[str, str] = models.CharField(
        strings.TECHNOLOGY_KIND, choices=TechnologyKind.choices
    )
    icon = models.FileField(
        strings.TECHNOLOGY_ICON, upload_to="technologies/", validators=[validate_svg]
    )
    # Stocké, ni exposé par l'API ni affiché sur le site en phase 1 — l'admin seul le montre : le
    # cadrage §6.1 le nomme (décision 11).
    # Borne technique, la valeur par défaut de Django écrite ici pour être lue.
    website: models.URLField[str, str] = models.URLField(
        strings.TECHNOLOGY_WEBSITE, max_length=200, blank=True
    )

    # Le fichier seul : toutes les icônes partagent le dossier `technologies/`.
    removals: ClassVar[Mapping[str, Removal]] = {"icon": delete_file_after_commit}

    class Meta:
        verbose_name = strings.TECHNOLOGY
        verbose_name_plural = strings.TECHNOLOGIES
        ordering = ("name",)
        constraints = (
            # Insensible à la casse : « Django » et « django » seraient la même technologie.
            models.UniqueConstraint(
                Lower("name"),
                name="content_technology_name_unique",
                violation_error_code="technology_name_taken",
                violation_error_message=strings.TECHNOLOGY_NAME_TAKEN,
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="content_technology_name_not_empty",
                violation_error_code="technology_name_missing",
                violation_error_message=strings.TECHNOLOGY_NAME_MISSING,
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=TechnologyKind.values),
                name="content_technology_kind_valid",
                violation_error_code="technology_kind_unknown",
                violation_error_message=strings.TECHNOLOGY_KIND_UNKNOWN,
            ),
            models.CheckConstraint(
                condition=~models.Q(icon=""),
                name="content_technology_icon_not_empty",
                violation_error_code="technology_icon_missing",
                violation_error_message=strings.TECHNOLOGY_ICON_MISSING,
            ),
        )

    def __str__(self) -> str:
        return self.name


class ProjectKind(models.TextChoices):
    """Le type d'un projet. Valeurs stockées en anglais, exposées telles quelles par l'API
    (ADR 0010) ; au niveau du module pour la même raison que `TechnologyKind`."""

    PERSONAL = "personal", strings.PROJECT_KIND_PERSONAL
    PROFESSIONAL = "professional", strings.PROJECT_KIND_PROFESSIONAL
    SCHOOL = "school", strings.PROJECT_KIND_SCHOOL


class ProjectStatus(models.TextChoices):
    """Le statut d'un projet. Valeurs stockées en anglais, exposées telles quelles par l'API
    (ADR 0010) ; au niveau du module pour la même raison que `TechnologyKind`."""

    ONGOING = "ongoing", strings.PROJECT_STATUS_ONGOING
    FINISHED = "finished", strings.PROJECT_STATUS_FINISHED
    ARCHIVED = "archived", strings.PROJECT_STATUS_ARCHIVED


# Un projet en cours : deux règles de dates en dépendent.
IS_ONGOING = models.Q(status=ProjectStatus.ONGOING)


class Project(models.Model):
    """Un projet du portfolio : une carte de la table, une fiche (cadrage §6.1, PRD « Modèle de
    contenu »).

    « En ligne » n'est pas un champ : le front le déduit de `demo_url` (spec §7, « Statuts »).
    """

    title: models.CharField[str, str] = models.CharField(strings.PROJECT_TITLE)
    # Unique par contrainte (`Meta`), dont l'index sert aussi la recherche par slug : l'index que
    # `SlugField` pose par défaut ferait double emploi.
    slug: models.SlugField[str, str] = models.SlugField(
        strings.PROJECT_SLUG, max_length=50, db_index=False
    )
    summary: models.CharField[str, str] = models.CharField(strings.PROJECT_SUMMARY)
    description: models.TextField[str, str] = models.TextField(strings.PROJECT_DESCRIPTION)
    kind: models.CharField[str, str] = models.CharField(
        strings.PROJECT_KIND, choices=ProjectKind.choices
    )
    status: models.CharField[str, str] = models.CharField(
        strings.PROJECT_STATUS, choices=ProjectStatus.choices
    )
    started_on: models.DateField[date, date] = models.DateField(strings.PROJECT_STARTED_ON)
    finished_on: models.DateField[date | None, date | None] = models.DateField(
        strings.PROJECT_FINISHED_ON, null=True, blank=True
    )
    client: models.CharField[str, str] = models.CharField(
        strings.PROJECT_CLIENT, max_length=100, blank=True
    )
    repository_url: models.URLField[str, str] = models.URLField(
        strings.PROJECT_REPOSITORY_URL, max_length=200, blank=True
    )
    demo_url: models.URLField[str, str] = models.URLField(
        strings.PROJECT_DEMO_URL, max_length=200, blank=True
    )
    showcase: models.BooleanField[bool, bool] = models.BooleanField(
        strings.PROJECT_SHOWCASE, default=False
    )
    published: models.BooleanField[bool, bool] = models.BooleanField(
        strings.PROJECT_PUBLISHED, default=False
    )
    created_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        strings.PROJECT_CREATED_AT, auto_now_add=True
    )
    updated_at: models.DateTimeField[datetime, datetime] = models.DateTimeField(
        strings.PROJECT_UPDATED_AT, auto_now=True
    )

    # Ses lignes de technologie, ses sections et sa galerie, que Django pose à l'exécution depuis
    # leurs modèles : déclarées ici pour que le typage les connaisse.
    projecttechnology_set: "RelatedManager[ProjectTechnology]"
    section_set: "RelatedManager[Section]"
    gallery: "RelatedManager[GalleryImage]"

    class Meta:
        verbose_name = strings.PROJECT
        verbose_name_plural = strings.PROJECTS
        constraints = (
            # Une contrainte, et non `unique=True` : le refus porte un code propre, là où
            # `unique=True` impose le code `unique` de Django (décision 10). Revers : l'admin affiche
            # ce refus en tête du formulaire, `validate_constraints` ne rangeant sous le champ que le
            # code `unique`.
            models.UniqueConstraint(
                fields=["slug"],
                name="content_project_slug_unique",
                violation_error_code="project_slug_taken",
                violation_error_message=strings.PROJECT_SLUG_TAKEN,
            ),
            # Un seul projet vitrine dans toute la table (spec §7, D48) : l'unicité ne porte que
            # sur la valeur vraie.
            models.UniqueConstraint(
                fields=["showcase"],
                condition=models.Q(showcase=True),
                name="content_project_single_showcase",
                violation_error_code="project_showcase_taken",
                violation_error_message=strings.PROJECT_SHOWCASE_TAKEN,
            ),
            # La forme que valide le champ lui-même, lettres sans accent, chiffres, traits d'union
            # et soulignés (`validate_slug`), et donc jamais vide : l'adresse `/projets/<slug>` de
            # la fiche en dépend.
            models.CheckConstraint(
                condition=models.Q(slug__regex=r"^[-a-zA-Z0-9_]+$"),
                name="content_project_slug_valid",
                violation_error_code="project_slug_invalid",
                violation_error_message=strings.PROJECT_SLUG_INVALID,
            ),
            models.CheckConstraint(
                condition=~models.Q(title=""),
                name="content_project_title_not_empty",
                violation_error_code="project_title_missing",
                violation_error_message=strings.PROJECT_TITLE_MISSING,
            ),
            models.CheckConstraint(
                condition=~models.Q(summary=""),
                name="content_project_summary_not_empty",
                violation_error_code="project_summary_missing",
                violation_error_message=strings.PROJECT_SUMMARY_MISSING,
            ),
            # Au moins un caractère qui n'est pas une espace, comme le corps d'une section :
            # l'admin garde la description telle que saisie (aperçu Markdown, #8), une description
            # d'espaces n'y devient plus vide. `\S` suit la locale libc de l'image.
            models.CheckConstraint(
                condition=models.Q(description__regex=r"\S"),
                name="content_project_description_not_empty",
                violation_error_code="project_description_missing",
                violation_error_message=strings.PROJECT_DESCRIPTION_MISSING,
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=ProjectKind.values),
                name="content_project_kind_valid",
                violation_error_code="project_kind_unknown",
                violation_error_message=strings.PROJECT_KIND_UNKNOWN,
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ProjectStatus.values),
                name="content_project_status_valid",
                violation_error_code="project_status_unknown",
                violation_error_message=strings.PROJECT_STATUS_UNKNOWN,
            ),
            # Les bornes de la spec §7 : un titre sur deux lignes du post-it, un résumé sur sept
            # lignes de la carte la plus étroite, aucun mot qui déborde d'une ligne.
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("title"), 30),
                name="content_project_title_length",
                violation_error_code="project_title_too_long",
                violation_error_message=strings.PROJECT_TITLE_TOO_LONG,
            ),
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("summary"), 120),
                name="content_project_summary_length",
                violation_error_code="project_summary_too_long",
                violation_error_message=strings.PROJECT_SUMMARY_TOO_LONG,
            ),
            # Un mot est un segment entre espaces ou traits d'union (décision 4) : aucun segment de
            # 21 caractères ou plus. Postgres évalue l'expression, en base comme dans
            # `full_clean()` ; une espace insécable n'y sépare pas deux mots, comme à l'écran. Ce
            # dernier point tient à la locale libc de l'image (mesuré) : une locale ICU en ferait un
            # séparateur, et les tests le verraient.
            models.CheckConstraint(
                condition=~models.Q(summary__regex=r"[^\s-]{21,}"),
                name="content_project_summary_words",
                violation_error_code="project_summary_word_too_long",
                violation_error_message=strings.PROJECT_SUMMARY_WORD_TOO_LONG,
            ),
            # Les dates (PRD « Modèle de contenu », décision 5) : une fin dès que le projet n'est
            # plus en cours, aucune tant qu'il l'est, jamais avant le début.
            models.CheckConstraint(
                condition=IS_ONGOING | models.Q(finished_on__isnull=False),
                name="content_project_finished_on_required",
                violation_error_code="project_finished_on_missing",
                violation_error_message=strings.PROJECT_FINISHED_ON_MISSING,
            ),
            models.CheckConstraint(
                condition=~IS_ONGOING | models.Q(finished_on__isnull=True),
                name="content_project_ongoing_unfinished",
                violation_error_code="project_ongoing_finished",
                violation_error_message=strings.PROJECT_ONGOING_FINISHED,
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(finished_on__isnull=True)
                    | models.Q(finished_on__gte=models.F("started_on"))
                ),
                name="content_project_dates_ordered",
                violation_error_code="project_dates_reversed",
                violation_error_message=strings.PROJECT_DATES_REVERSED,
            ),
        )

    def __str__(self) -> str:
        return self.title


class ProjectTechnology(models.Model):
    """Une technologie qu'un projet emploie, à sa place dans la liste du projet (PRD « Modèle de
    contenu »). Au moins une par projet : seule règle hors base, tenue par l'écran Projet
    (décision 10)."""

    # L'index de l'unicité (projet, technologie), mené par le projet, sert aussi ses recherches :
    # l'index que `ForeignKey` pose par défaut ferait double emploi.
    project: models.ForeignKey[Project, Project] = models.ForeignKey(
        Project, models.CASCADE, verbose_name=strings.PROJECT, db_index=False
    )
    # Protégée : supprimer une technologie employée retirerait en silence une ligne à des projets,
    # jusqu'à en laisser sans technologie. L'admin refuse et nomme les projets.
    technology: models.ForeignKey[Technology, Technology] = models.ForeignKey(
        Technology, models.PROTECT, verbose_name=strings.TECHNOLOGY
    )
    # Sans valeur par défaut : le tableau en ligne de l'écran Projet la pose, dans l'ordre affiché ;
    # une ligne neuve arrivée sans elle prend la suivante, une ligne enregistrée garde la sienne
    # (`content/inlines.py`, décision 2, ADR 0013).
    position: models.PositiveSmallIntegerField[int, int] = models.PositiveSmallIntegerField(
        strings.PROJECT_TECHNOLOGY_POSITION
    )

    class Meta:
        verbose_name = strings.PROJECT_TECHNOLOGY
        verbose_name_plural = strings.PROJECT_TECHNOLOGIES
        # L'ordre de l'admin est l'ordre stocké ; à position égale, l'ordre de saisie.
        ordering = ("position", "id")
        constraints = (
            # Différée à la fin de la transaction : l'écran Projet enregistre les lignes l'une
            # après l'autre, et un échange de technologies entre deux lignes passe par un état
            # intermédiaire en double. Django la vérifie encore dans `full_clean()` et entre les
            # lignes du formulaire, l'écran avec les lignes que l'envoi ne porte pas
            # (`SortableFormSet.validate_unique`) ; Postgres, à la validation de la transaction
            # seulement : un `transaction.atomic()` imbriqué n'en voit pas le refus, et Postgres
            # refuse `ON CONFLICT` sur elle (`bulk_create(ignore_conflicts=…)`,
            # `update_conflicts=…`).
            models.UniqueConstraint(
                fields=["project", "technology"],
                deferrable=models.Deferrable.DEFERRED,
                name="content_project_technology_unique",
                violation_error_code="project_technology_taken",
                violation_error_message=strings.PROJECT_TECHNOLOGY_TAKEN,
            ),
        )

    def __str__(self) -> str:
        return f"{self.project} · {self.technology}"


class Section(models.Model):
    """Une section de la fiche technique d'un projet, à sa place dans la fiche : un titre, une
    ancre stable et un corps en Markdown (cadrage §6.1, D57).

    L'auteur en crée autant qu'il veut, sans titre imposé, et les ordonne ; aucune n'est
    obligatoire, et aucune n'est vide : une section sans texte n'est pas enregistrée, le site
    l'omet (spec §7).
    """

    # L'index de l'unicité (projet, ancre), mené par le projet, sert aussi ses recherches : l'index
    # que `ForeignKey` pose par défaut ferait double emploi.
    project: models.ForeignKey[Project, Project] = models.ForeignKey(
        Project, models.CASCADE, verbose_name=strings.PROJECT, db_index=False
    )
    # Borné par une contrainte (`Meta`), comme le titre d'un projet : le refus porte un code propre.
    title: models.CharField[str, str] = models.CharField(strings.SECTION_TITLE)
    # Préremplie depuis le titre dans l'écran Projet, et toujours modifiable : c'est elle que le site
    # et le RAG citent (`#s-<ancre>`, US 57), elle ne suit pas un titre retouché. Borne technique :
    # le slug d'un titre de 40 caractères est plus court. L'index de l'unicité suffit.
    anchor: models.SlugField[str, str] = models.SlugField(
        strings.SECTION_ANCHOR, max_length=50, db_index=False
    )
    # Aucune borne : la spec §7 n'en fixe pas.
    body: models.TextField[str, str] = models.TextField(strings.SECTION_BODY)
    # Sans valeur par défaut : le tableau en ligne de l'écran Projet la pose, dans l'ordre affiché
    # (`content/inlines.py`, D55).
    position: models.PositiveSmallIntegerField[int, int] = models.PositiveSmallIntegerField(
        strings.SECTION_POSITION
    )

    class Meta:
        verbose_name = strings.SECTION
        verbose_name_plural = strings.SECTIONS
        # L'ordre de l'admin est l'ordre stocké ; à position égale, l'ordre de saisie.
        ordering = ("position", "id")
        constraints = (
            # Différée à la fin de la transaction, comme celle des technologies d'un projet : deux
            # lignes qui échangent leurs ancres passent par un état intermédiaire en double
            # (`content/inlines.py`).
            models.UniqueConstraint(
                fields=["project", "anchor"],
                deferrable=models.Deferrable.DEFERRED,
                name="content_section_anchor_unique",
                violation_error_code="section_anchor_taken",
                violation_error_message=strings.SECTION_ANCHOR_TAKEN,
            ),
            models.CheckConstraint(
                condition=~models.Q(title=""),
                name="content_section_title_not_empty",
                violation_error_code="section_title_missing",
                violation_error_message=strings.SECTION_TITLE_MISSING,
            ),
            # La borne de la spec §7 : un titre courant de 40 caractères tient sur une ligne de la
            # fiche mobile de 360 px.
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("title"), 40),
                name="content_section_title_length",
                violation_error_code="section_title_too_long",
                violation_error_message=strings.SECTION_TITLE_TOO_LONG,
            ),
            # La forme de la spec §7 — lettres sans accent, chiffres, traits d'union —, donc
            # jamais vide : le souligné, que le champ de slug admet, n'en est pas.
            models.CheckConstraint(
                condition=models.Q(anchor__regex=r"^[-a-zA-Z0-9]+$"),
                name="content_section_anchor_valid",
                violation_error_code="section_anchor_invalid",
                violation_error_message=strings.SECTION_ANCHOR_INVALID,
            ),
            # Au moins un caractère qui n'est pas une espace : un corps d'espaces est vide.
            # `\S` suit la locale libc de l'image, comme pour les mots du résumé : une espace
            # insécable seule y compte comme un texte, et les tests le verraient changer.
            models.CheckConstraint(
                condition=models.Q(body__regex=r"\S"),
                name="content_section_body_not_empty",
                violation_error_code="section_body_missing",
                violation_error_message=strings.SECTION_BODY_MISSING,
            ),
        )

    def __str__(self) -> str:
        return f"{self.project} · {self.title}"


class ProcessingState(models.TextChoices):
    """L'état de traitement d'une image : le worker de #12 la convertit et en produit les
    variantes. Valeurs stockées en anglais, exposées telles quelles par l'API (ADR 0010) ; au
    niveau du module pour la même raison que `TechnologyKind`."""

    PENDING = "pending", strings.PROCESSING_STATE_PENDING
    READY = "ready", strings.PROCESSING_STATE_READY
    FAILED = "failed", strings.PROCESSING_STATE_FAILED


class Variant(TypedDict):
    """Une variante d'une image, telle que le worker de #12 l'écrit et que l'API de #10 l'expose
    (décision 5) : `name` est son nom de stockage, dont le stockage déduit l'adresse."""

    name: str
    width: int
    height: int


# La borne de la spec §7 : une légende tient sur la ligne de la barre de galerie, à côté du
# compteur.
CAPTION_MAX_LENGTH = 50

# Le côté minimal de la couverture, première image de la galerie (spec §1.11 et §7).
COVER_MIN_SIDE = 1200


class GalleryImage(StoredFiles):
    """Une image de la galerie d'un projet, à sa place dans la galerie (`project.gallery`). Le
    site l'affiche entière dans le cadre carré, sur fond neutre (spec §1.11).

    La première est la couverture : la photo de la carte, la première image de la fiche et
    l'`og:image` (spec §1.11 et §7, ADR 0011), carrée, d'au moins 1200 px de côté. Ces règles
    lisent l'ordre des images d'un projet, comme « une image au moins » : la base ne peut pas les
    porter, l'écran Projet les tient (brief de #9, décision 4).

    L'original est gardé tel que téléversé, jamais recadré ni réencodé (spec §1.11). Le worker en
    produit les variantes et seul il écrit l'état et les variantes (brief de #9, décision 5 ;
    `content/tasks.py`) : ici, une image naît « en attente », sans variante, et son traitement est
    enfilé après la validation de la transaction qui la crée ou remplace son original.

    L'original que la ligne ne nomme plus — l'image supprimée, seule ou avec son projet, ou son
    original remplacé — sort du stockage avec son dossier, variantes comprises, une fois la
    transaction validée, jamais si elle est annulée (décision 10 ; `StoredFiles`).
    """

    original = OriginalField(
        strings.IMAGE_ORIGINAL,
        width_field="width",
        height_field="height",
        validators=[validate_original],
    )
    # Remplies par Django depuis l'original téléversé (décision 8), jamais saisies. Non éditables,
    # elles ne sont pas validées (`Field.validate`) : un fichier qui n'est pas une image n'a pas
    # de dimensions, et son seul refus est celui de l'original — l'admin n'affiche jamais trois
    # messages pour une faute. La colonne, elle, n'admet pas d'absence.
    width: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        strings.IMAGE_WIDTH, editable=False
    )
    height: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(
        strings.IMAGE_HEIGHT, editable=False
    )
    # Bornée par une contrainte (`Meta`), comme le titre d'un projet : le refus porte un code
    # propre. Elle sert de texte alternatif (spec §4.4).
    caption: models.CharField[str, str] = models.CharField(strings.IMAGE_CAPTION)
    # Écrits par le worker de #12 seul (décision 5), donc non éditables — et non validés par le
    # champ : un état hors de sa liste n'a que le refus de sa contrainte.
    state: models.CharField[str, str] = models.CharField(
        strings.IMAGE_STATE,
        choices=ProcessingState.choices,
        default=ProcessingState.PENDING,
        editable=False,
    )
    variants: models.JSONField[list[Variant], list[Variant]] = models.JSONField(
        strings.IMAGE_VARIANTS, default=list, editable=False
    )
    project: models.ForeignKey[Project, Project] = models.ForeignKey(
        Project, models.CASCADE, related_name="gallery", verbose_name=strings.PROJECT
    )
    # Sans valeur par défaut : le tableau en ligne de l'écran Projet la pose, dans l'ordre affiché
    # (`content/inlines.py`, D55). Aucune unicité ne lit le projet : à position égale, l'ordre de
    # saisie.
    position: models.PositiveSmallIntegerField[int, int] = models.PositiveSmallIntegerField(
        strings.GALLERY_IMAGE_POSITION
    )

    # Le dossier entier : le worker range les variantes à côté de l'original, et peut y en écrire
    # entre la lecture de la ligne et son écriture, que la ligne ne nomme pas
    # (`delete_folder_after_commit`).
    removals: ClassVar[Mapping[str, Removal]] = {"original": delete_folder_after_commit}

    class Meta:
        verbose_name = strings.GALLERY_IMAGE
        verbose_name_plural = strings.GALLERY_IMAGES
        # L'ordre de l'admin est l'ordre stocké ; à position égale, l'ordre de saisie.
        ordering = ("position", "id")
        constraints = (
            models.CheckConstraint(
                condition=~models.Q(original=""),
                name="content_galleryimage_original_not_empty",
                violation_error_code="image_original_missing",
                violation_error_message=strings.IMAGE_ORIGINAL_MISSING,
            ),
            # Au moins un caractère qui n'est pas une espace, comme le corps d'une section : une
            # légende d'espaces ne dit rien au lecteur d'écran.
            models.CheckConstraint(
                condition=models.Q(caption__regex=r"\S"),
                name="content_galleryimage_caption_not_empty",
                violation_error_code="image_caption_missing",
                violation_error_message=strings.IMAGE_CAPTION_MISSING,
            ),
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("caption"), CAPTION_MAX_LENGTH),
                name="content_galleryimage_caption_length",
                violation_error_code="image_caption_too_long",
                violation_error_message=strings.IMAGE_CAPTION_TOO_LONG,
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=ProcessingState.values),
                name="content_galleryimage_state_valid",
                violation_error_code="image_state_unknown",
                violation_error_message=strings.IMAGE_STATE_UNKNOWN,
            ),
            # Des variantes seulement à l'état « prêt » (décision 5) : l'API de #10 ne sert
            # jamais celles d'une image en attente ou en échec.
            models.CheckConstraint(
                condition=models.Q(state=ProcessingState.READY) | models.Q(variants=[]),
                name="content_galleryimage_variants_ready",
                violation_error_code="image_variants_unready",
                violation_error_message=strings.IMAGE_VARIANTS_UNREADY,
            ),
        )

    def __str__(self) -> str:
        return f"{self.project} · {self.caption}"

    def save_replacing(self, replaced: Mapping[str, str], **kwargs: Any) -> None:
        """Écrit l'image ; un original remplacé la remet en attente ; un original neuf est traité
        par le worker.

        Remplacer l'original d'une image enregistrée — un nouveau fichier, téléversé ou
        enregistré par `OriginalFile.save` — la remet à l'état « en attente » et vide ses
        variantes : elles décrivaient l'ancien fichier (décision 5). Un enregistrement partiel
        (`update_fields`) qui écrit l'original écrit aussi ses dimensions, qui décrivent le nouveau
        fichier, et l'état et les variantes qu'un remplacement remet à zéro.

        Les deux enregistrements qui mettent l'image « en attente » — sa création, le
        remplacement de son original — enfilent son traitement, une fois la transaction validée
        (`process_after_commit`, brief de #12, décision 5) ; aucun autre.

        Args:
            replaced: ceux de `StoredFiles.save_replacing` ; l'original, s'il est remplacé.
            kwargs: ceux de `Model.save`.
        """
        creating = self._state.adding
        replacing = "original" in replaced
        if replacing:
            self.state = ProcessingState.PENDING
            self.variants = []
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "original" in update_fields:
            reset = {"state", "variants"} if replacing else set[str]()
            kwargs["update_fields"] = update_fields | {"width", "height", *reset}
        super().save_replacing(replaced, **kwargs)
        if creating or replacing:
            # Importée ici : la tâche lit ce module, qui ne peut donc pas la lire à son chargement.
            from content.tasks import process_after_commit

            process_after_commit(self.pk, self.original.name or "")
