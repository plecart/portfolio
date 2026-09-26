"""Modèles du contenu : les technologies ; les projets suivent (#7, lot 2).

Toute règle que la base peut porter y est une contrainte du modèle, avec son code et son
message du catalogue (décision 10 du brief de #7) : Django la vérifie dans `full_clean()` — donc
dans l'admin —, Postgres la garantit pour toute ligne écrite hors de l'admin. Quand un champ la
vérifie déjà (`blank`, `choices`), Django écarte la contrainte des champs en erreur : l'admin
n'affiche jamais deux messages pour une même faute.
"""

from config import strings
from django.db import models
from django.db.models.functions import Lower

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
    # Stocké sans être exposé ni affiché en phase 1 : le cadrage §6.1 le nomme (décision 11).
    website: models.URLField[str, str] = models.URLField(strings.TECHNOLOGY_WEBSITE, blank=True)

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
