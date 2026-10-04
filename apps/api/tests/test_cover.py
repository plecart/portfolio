"""Tests de la couverture : sa forme — carrée, 1200 px de côté au moins —, une par projet, et ce
que la suppression du projet en fait. Ce qu'elle partage avec l'image de galerie est éprouvé dans
`test_images.py`."""

import pytest
from config import strings
from content.models import Cover, Project
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from factories import cover, image_upload, project, saved
from refusals import refusals

# Le côté minimal (spec §1.11 et §7), écrit ici et non lu sur le modèle, pour qu'une borne changée
# fasse rougir ce fichier.
MIN_SIDE = 1200

NOT_SQUARE = ("cover_not_square", strings.COVER_NOT_SQUARE)
TOO_SMALL = ("cover_too_small", strings.COVER_TOO_SMALL)

# Les formes refusées, bornes éprouvées des deux côtés : chacune avec les refus qu'elle porte,
# dans l'ordre des contraintes, et la contrainte que la base lui oppose en premier.
SHAPE_REFUSALS = [
    (
        f"{MIN_SIDE - 1} × {MIN_SIDE - 1}",
        (MIN_SIDE - 1, MIN_SIDE - 1),
        [TOO_SMALL],
        "content_cover_min_side",
    ),
    (
        f"{MIN_SIDE} × {MIN_SIDE + 1}",
        (MIN_SIDE, MIN_SIDE + 1),
        [NOT_SQUARE],
        "content_cover_square",
    ),
    (
        f"{MIN_SIDE + 1} × {MIN_SIDE}",
        (MIN_SIDE + 1, MIN_SIDE),
        [NOT_SQUARE],
        "content_cover_square",
    ),
    # Le petit côté compte : plus large que la borne, mais trop basse.
    (
        f"{MIN_SIDE + 100} × {MIN_SIDE - 100}",
        (MIN_SIDE + 100, MIN_SIDE - 100),
        [NOT_SQUARE, TOO_SMALL],
        "content_cover_",
    ),
]
SHAPE_IDS = [shape for shape, *_ in SHAPE_REFUSALS]


@pytest.fixture
def portfolio() -> Project:
    """Le projet de la fabrique, enregistré."""
    return saved(project())


@pytest.mark.django_db
@pytest.mark.parametrize(
    "size", [(MIN_SIDE, MIN_SIDE), (MIN_SIDE + 1, MIN_SIDE + 1)], ids=["à la borne", "au-delà"]
)
def test_une_couverture_carree_d_au_moins_1200_px_est_acceptee(
    portfolio: Project, size: tuple[int, int]
) -> None:
    cover(portfolio, original=image_upload(size=size)).full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("size", "expected"),
    [(size, expected) for _, size, expected, _ in SHAPE_REFUSALS],
    ids=SHAPE_IDS,
)
def test_full_clean_refuse_une_couverture_hors_de_sa_forme(
    portfolio: Project, size: tuple[int, int], expected: list[tuple[str, str]]
) -> None:
    """Les deux règles lisent les dimensions stockées (décision 8), avec le code et le message du
    catalogue."""
    with pytest.raises(ValidationError) as error:
        cover(portfolio, original=image_upload(size=size)).full_clean()

    assert refusals(error.value) == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("size", "constraint"),
    [(size, constraint) for _, size, _, constraint in SHAPE_REFUSALS],
    ids=SHAPE_IDS,
)
def test_la_base_refuse_une_couverture_hors_de_sa_forme(
    portfolio: Project, size: tuple[int, int], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        cover(portfolio, original=image_upload(size=size)).save()


@pytest.mark.django_db
def test_un_projet_porte_sa_couverture(portfolio: Project) -> None:
    made = saved(cover(portfolio))

    assert Project.objects.get(pk=portfolio.pk).cover == made


@pytest.mark.django_db
def test_un_projet_ne_porte_pas_deux_couvertures(portfolio: Project) -> None:
    saved(cover(portfolio))

    with pytest.raises(ValidationError) as refusal:
        cover(portfolio).full_clean()

    assert [code for code, _ in refusals(refusal.value, "project")] == ["unique"]


@pytest.mark.django_db
def test_la_base_refuse_deux_couvertures_a_un_projet(portfolio: Project) -> None:
    saved(cover(portfolio))

    with pytest.raises(IntegrityError, match="project_id"), transaction.atomic():
        cover(portfolio).save()


@pytest.mark.django_db
def test_un_projet_supprime_emporte_sa_couverture(portfolio: Project) -> None:
    saved(cover(portfolio))

    portfolio.delete()

    assert not Cover.objects.exists()
