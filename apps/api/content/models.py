"""Modèles du contenu : les technologies et les projets.

Toute règle que la base peut porter y est une contrainte du modèle (décision 10 du brief de #7) :
son code, identifiant stable du refus, est nommé sur la contrainte ; son message, texte affiché,
vient du catalogue. Django la vérifie dans `full_clean()` — donc dans l'admin —, Postgres la
garantit pour toute ligne écrite hors de l'admin. Quand un champ la vérifie déjà (`blank`,
`choices`), Django écarte la contrainte des champs en erreur : l'admin n'affiche jamais deux
messages pour une même faute.
"""

from datetime import date, datetime

from config import strings
from django.db import models
from django.db.models.functions import Length, Lower
from django.db.models.lookups import LessThanOrEqual

from content.validators import validate_svg


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


class Technology(models.Model):
    """Une technologie qu'un projet emploie (cadrage §6.1)."""

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
            models.CheckConstraint(
                condition=~models.Q(description=""),
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
    # Sans valeur par défaut : le tableau en ligne de l'écran Projet la pose, dans l'ordre affiché,
    # ou la suivante pour une ligne arrivée sans elle (`content/inlines.py`, décision 2, ADR 0013).
    position: models.PositiveSmallIntegerField[int, int] = models.PositiveSmallIntegerField(
        strings.PROJECT_TECHNOLOGY_POSITION
    )

    class Meta:
        verbose_name = strings.PROJECT_TECHNOLOGY
        verbose_name_plural = strings.PROJECT_TECHNOLOGIES
        # L'ordre de l'admin est l'ordre stocké ; à position égale, l'ordre de saisie.
        ordering = ("position", "id")
        constraints = (
            models.UniqueConstraint(
                fields=["project", "technology"],
                name="content_project_technology_unique",
                violation_error_code="project_technology_taken",
                violation_error_message=strings.PROJECT_TECHNOLOGY_TAKEN,
            ),
        )

    def __str__(self) -> str:
        return f"{self.project} · {self.technology}"
