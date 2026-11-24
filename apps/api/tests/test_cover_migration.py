"""Test de la migration qui fait de la couverture la première image de la galerie
(`content/migrations/0006_cover_to_gallery.py`, brief de #9, décision 4) : elle tourne sur une base
de test ramenée à l'état d'avant, garnie par les modèles historiques de cet état."""

from collections.abc import Callable
from typing import Any

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from factories import historical_project, image_upload

BEFORE = [("content", "0005_cover_galleryimage")]
AFTER = [("content", "0006_cover_to_gallery")]

# Les variantes d'une couverture déjà traitée : ni l'état ni elles ne sont les valeurs par défaut
# d'une image, qu'une recopie oubliée rendrait aussi.
READY_VARIANTS = [{"name": "images/couverture/w600.webp", "width": 600, "height": 600}]


def image_fields(**fields: object) -> dict[str, object]:
    """Les champs d'une image en attente, sans variante ; `fields` les complètent."""
    return {"state": "pending", "variants": [], **fields}


@pytest.mark.django_db(transaction=True)
def test_la_migration_fait_de_chaque_couverture_la_premiere_image_de_sa_galerie(
    migrate: Callable[[list[tuple[str, str]]], Any],
) -> None:
    """La couverture passe en tête, les images de la galerie reculent d'une place — même celle
    qui tenait la place 0, que la couverture prend : à place égale, l'ordre de saisie la mettrait
    devant. Même fichier, mêmes dimensions, même légende, même état, mêmes variantes ; le fichier
    reste dans le stockage, qu'aucune suppression n'atteint. Le projet est celui de la fabrique,
    écrit par le modèle historique : le modèle d'aujourd'hui porte des colonnes que cet état n'a
    pas encore."""
    before = migrate(BEFORE)
    portfolio = historical_project(before)
    stored = default_storage.save(
        "images/couverture/original.png", ContentFile(image_upload().read())
    )
    before.get_model("content", "Cover").objects.create(
        **image_fields(
            project_id=portfolio.pk,
            original=stored,
            width=1200,
            height=1200,
            caption="La table des projets.",
            state="ready",
            variants=READY_VARIANTS,
        )
    )
    before.get_model("content", "GalleryImage").objects.create(
        **image_fields(
            project_id=portfolio.pk,
            original="images/fiche/original.png",
            width=800,
            height=600,
            caption="La fiche.",
            position=0,
        )
    )

    after = migrate(AFTER)

    gallery = after.get_model("content", "GalleryImage").objects.filter(project_id=portfolio.pk)
    assert [
        (image.caption, image.original.name, image.width, image.height, image.state, image.variants)
        for image in gallery.order_by("position", "id")
    ] == [
        ("La table des projets.", stored, 1200, 1200, "ready", READY_VARIANTS),
        ("La fiche.", "images/fiche/original.png", 800, 600, "pending", []),
    ]
    assert default_storage.exists(stored)
    with pytest.raises(LookupError):
        after.get_model("content", "Cover")
