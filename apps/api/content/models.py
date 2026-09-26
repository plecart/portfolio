"""Modèles du contenu : les technologies ; les projets suivent (#7, lot 2).

Toute règle que la base peut porter y est déclarée une seule fois, comme contrainte du modèle,
avec son code et son message du catalogue (décision 10 du brief de #7) : Django la vérifie dans
`full_clean()` — donc dans l'admin —, Postgres la garantit quoi qu'il arrive.
"""

from config import strings
from django.db import models
from django.db.models.functions import Lower

from content.validators import validate_svg


class Technology(models.Model):
    """Une technologie qu'un projet emploie (cadrage §6.1)."""

    class Kind(models.TextChoices):
        """Valeurs stockées en anglais, exposées telles quelles par l'API (ADR 0010)."""

        LANGUAGE = "language", strings.TECHNOLOGY_KIND_LANGUAGE
        FRAMEWORK = "framework", strings.TECHNOLOGY_KIND_FRAMEWORK
        INFRASTRUCTURE = "infrastructure", strings.TECHNOLOGY_KIND_INFRASTRUCTURE
        TOOL = "tool", strings.TECHNOLOGY_KIND_TOOL

    # Borne technique : la spec ne borne pas ce nom.
    name: models.CharField[str, str] = models.CharField(strings.TECHNOLOGY_NAME, max_length=50)
    kind: models.CharField[str, str] = models.CharField(
        strings.TECHNOLOGY_KIND, choices=Kind.choices
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
        )

    def __str__(self) -> str:
        return self.name
