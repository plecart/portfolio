"""Tests de la technologie : nom unique, icône SVG obligatoire, site facultatif."""

import pytest
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from factories import SVG, svg_icon, technology

# Les formes d'un fichier qui n'est pas un document SVG — c'est le dénombrement qui compte : une
# extension qui ment, un contenu qui n'est pas du XML, du XML dont la racine n'est pas `svg`, et
# une racine `svg` hors de l'espace de noms SVG, qu'aucun navigateur n'affiche.
NOT_SVG = [
    ("extension étrangère", "icone.png", SVG),
    ("contenu illisible", "icone.svg", b"\x89PNG\r\n\x1a\n"),
    ("racine étrangère", "icone.svg", b'<html xmlns="http://www.w3.org/1999/xhtml"/>'),
    ("racine sans espace de noms", "icone.svg", b"<svg/>"),
]


def refusal_codes(error: ValidationError, field: str = NON_FIELD_ERRORS) -> list[str | None]:
    """Les codes des refus que `error` porte pour `field`."""
    return [refusal.code for refusal in error.error_dict[field]]


def test_une_icone_svg_est_acceptee() -> None:
    technology().clean_fields()


@pytest.mark.parametrize(
    ("name", "content"),
    [(name, content) for _, name, content in NOT_SVG],
    ids=[form for form, _, _ in NOT_SVG],
)
def test_une_icone_qui_n_est_pas_un_document_svg_est_refusee(name: str, content: bytes) -> None:
    with pytest.raises(ValidationError) as refusal:
        technology(icon=svg_icon(name, content)).clean_fields()

    assert refusal_codes(refusal.value, "icon") == ["icon_not_svg"]


def test_une_technologie_sans_icone_est_refusee() -> None:
    with pytest.raises(ValidationError) as refusal:
        technology(icon=None).clean_fields()

    assert list(refusal.value.error_dict) == ["icon"]


def test_le_site_est_facultatif() -> None:
    technology(website="").clean_fields()


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_deux_technologies_ne_portent_pas_le_meme_nom_a_la_casse_pres() -> None:
    technology(name="Django").save()

    with pytest.raises(ValidationError) as refusal:
        technology(name="django").full_clean()

    assert refusal_codes(refusal.value) == ["technology_name_taken"]


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_la_base_refuse_deux_technologies_du_meme_nom() -> None:
    technology(name="Django").save()

    with pytest.raises(IntegrityError), transaction.atomic():
        technology(name="DJANGO").save()
