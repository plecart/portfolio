"""La couverture devient la première image de la galerie (brief de #9, décision 4, 2026-10-08).

Chaque couverture passe en tête de la galerie de son projet — même fichier, mêmes dimensions,
même légende, même état —, puis le modèle `Cover` disparaît. Aucun fichier ne quitte le stockage :
l'image neuve reprend le nom de l'original, et ni la suppression de la table ni les modèles
historiques n'émettent le signal qui supprime les fichiers d'une image.

Le retour recrée la table vide et laisse les images en galerie : rien ne se perd.
"""

from typing import Any

from django.db import migrations
from django.db.models import F


def covers_to_gallery(apps: Any, schema_editor: Any) -> None:
    """Chaque couverture devient la première image de sa galerie : les images du projet reculent
    d'une place, la couverture prend la première."""
    cover_model = apps.get_model("content", "Cover")
    gallery_model = apps.get_model("content", "GalleryImage")
    for cover in cover_model.objects.all():
        gallery_model.objects.filter(project_id=cover.project_id).update(position=F("position") + 1)
        gallery_model.objects.create(
            project_id=cover.project_id,
            original=cover.original.name,
            width=cover.width,
            height=cover.height,
            caption=cover.caption,
            state=cover.state,
            variants=cover.variants,
            position=0,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0005_cover_galleryimage"),
    ]

    operations = [
        migrations.RunPython(covers_to_gallery, migrations.RunPython.noop),
        migrations.DeleteModel(name="Cover"),
    ]
