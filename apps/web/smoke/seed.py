"""La semence de la fumée (#26) : un projet publié, sa couverture, une technologie et une section,
écrits dans la pile par le conteneur `api`, qui lit ce fichier sur son entrée standard
(`docker compose exec -T api python -`, depuis `global-setup.ts`). L'image publiée ne porte aucun
test, et aucune fixture n'entre dans `apps/api` : la donnée appartient au test (brief de #26,
décision 6).

Les modèles de l'admin, sans son formulaire : les fichiers vont au stockage de production — le
témoin S3 de la pile —, et l'image de la galerie enfile son traitement en naissant
(`GalleryImage.save`) ; le `worker` le reprend et en produit les variantes. Écrit sur sa sortie, en
JSON, ce que les scénarios lisent du projet semé, et le bucket où ses fichiers vivent.
"""

import io
import json
import os
from datetime import date

import django

# Une icône SVG minimale : la racine `svg` dans l'espace de noms SVG, que `validate_svg` exige.
ICON = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="16" height="16"/></svg>'


def main() -> None:
    """Sème la pile, puis écrit le projet semé sur la sortie."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    # Après `django.setup()` : les modèles exigent les applications chargées.
    from content.models import (
        COVER_MIN_SIDE,
        GalleryImage,
        Project,
        ProjectKind,
        ProjectStatus,
        ProjectTechnology,
        Section,
        Technology,
        TechnologyKind,
    )
    from django.core.files.base import ContentFile
    from PIL import Image

    technology = Technology.objects.create(
        name="Django", kind=TechnologyKind.FRAMEWORK, icon=ContentFile(ICON, name="django.svg")
    )
    project = Project.objects.create(
        title="Fumée",
        slug="fumee",
        summary="Le projet que la fumée sème pour éprouver la pile complète.",
        description="La fiche du projet semé par la fumée.",
        kind=ProjectKind.PERSONAL,
        status=ProjectStatus.ONGOING,
        started_on=date(2026, 11, 5),
        published=True,
    )
    ProjectTechnology.objects.create(project=project, technology=technology, position=0)
    section = Section.objects.create(
        project=project,
        title="Architecture",
        anchor="architecture",
        body="La pile complète, semée puis jetée.",
        position=0,
    )
    # Une vraie image, carrée et au côté minimal de la couverture (spec §1.11) : le worker en tire
    # toutes les variantes, celle de l'`og:image` comprise.
    cover = io.BytesIO()
    Image.new("RGB", (COVER_MIN_SIDE, COVER_MIN_SIDE), "teal").save(cover, format="PNG")
    GalleryImage.objects.create(
        project=project,
        original=ContentFile(cover.getvalue(), name="couverture.png"),
        caption="La couverture de la fumée",
        position=0,
    )
    seeded = {
        "slug": project.slug,
        "title": project.title,
        "summary": project.summary,
        "section": section.title,
        "bucket": os.environ["MEDIA_R2_BUCKET"],
    }
    print(json.dumps(seeded))


if __name__ == "__main__":
    main()
