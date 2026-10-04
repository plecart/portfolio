"""Tests de l'image de galerie : plusieurs par projet, l'ordre qu'elle stocke, et ce que la
suppression du projet en fait. Ce qu'elle partage avec la couverture est éprouvé dans
`test_images.py`."""

import pytest
from content.models import GalleryImage, Project
from django.core.exceptions import ValidationError
from factories import gallery_image, project, saved
from refusals import refusals


@pytest.fixture
def portfolio() -> Project:
    """Le projet de la fabrique, enregistré."""
    return saved(project())


@pytest.mark.django_db
def test_une_image_de_galerie_exige_sa_position(portfolio: Project) -> None:
    """Le modèle ne choisit aucune position : l'écran Projet la pose, par le glisser-déposer ou la
    suivante pour une ligne neuve (D55)."""
    with pytest.raises(ValidationError) as refusal:
        gallery_image(portfolio, position=None).full_clean()

    assert [code for code, _ in refusals(refusal.value, "position")] == ["null"]


@pytest.mark.django_db
def test_la_galerie_d_un_projet_se_lit_dans_l_ordre_de_ses_positions(portfolio: Project) -> None:
    """L'ordre stocké est celui de l'admin : par position, puis dans l'ordre de saisie — aucune
    unicité ne lit le projet, deux images peuvent partager une position. Trois ordres qui
    divergent : position, clé, écriture en table."""
    for key, caption, position in ((1, "bilan", 2), (3, "stack", 1), (2, "contexte", 1)):
        saved(gallery_image(portfolio, pk=key, caption=caption, position=position))

    assert [image.caption for image in portfolio.gallery.all()] == ["contexte", "stack", "bilan"]


@pytest.mark.django_db
def test_un_projet_supprime_emporte_sa_galerie(portfolio: Project) -> None:
    saved(gallery_image(portfolio))
    saved(gallery_image(portfolio, position=2))

    portfolio.delete()

    assert not GalleryImage.objects.exists()
