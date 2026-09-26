"""Tests de la technologie : ses champs, son icône SVG, son nom unique, et ce que la base porte."""

import pytest
from config import strings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from factories import SVG, svg_icon, technology

# Les refus que les champs portent eux-mêmes — bornes techniques, liste du type, présence — et le
# code que Django leur donne. Ces messages-là sont ceux de Django, traduits par `LANGUAGE_CODE`.
FIELD_REFUSALS = [
    ("nom de 51 caractères", {"name": "n" * 51}, "name", "max_length"),
    ("nom absent", {"name": ""}, "name", "blank"),
    ("type hors de sa liste", {"kind": "autre"}, "kind", "invalid_choice"),
    ("icône absente", {"icon": None}, "icon", "blank"),
    (
        "site de 201 caractères",
        {"website": "https://exemple.fr/" + "a" * 182},
        "website",
        "max_length",
    ),
]

# Les règles que la base porte en plus de la validation, une contrainte nommée chacune : l'API de
# #10 s'y fie même pour une ligne écrite hors de l'admin (brief de #7, décision 10 : « seule règle
# hors base : au moins une technologie »).
DATABASE_RULES = [
    ("type hors de sa liste", {"kind": "autre"}, "content_technology_kind_valid"),
    ("nom vide", {"name": ""}, "content_technology_name_not_empty"),
    ("icône vide", {"icon": ""}, "content_technology_icon_not_empty"),
]

# Les formes d'un fichier qui n'est pas un document SVG — c'est le dénombrement qui compte : une
# extension qui ment, un contenu qui n'est pas du XML, du XML dont la racine n'est pas `svg`, et
# une racine `svg` hors de l'espace de noms SVG, qu'aucun navigateur n'affiche.
NOT_SVG = [
    ("extension étrangère", "icone.png", SVG),
    ("contenu illisible", "icone.svg", b"\x89PNG\r\n\x1a\n"),
    ("racine étrangère", "icone.svg", b'<html xmlns="http://www.w3.org/1999/xhtml"/>'),
    ("racine sans espace de noms", "icone.svg", b"<svg/>"),
]


def refusals(error: ValidationError, field: str = NON_FIELD_ERRORS) -> list[tuple[str | None, str]]:
    """Les refus que `error` porte pour `field`, chacun en paire (code, message)."""
    return [(refusal.code, str(refusal.message)) for refusal in error.error_dict[field]]


def test_une_icone_svg_est_acceptee() -> None:
    technology().clean_fields()


def test_le_site_est_facultatif() -> None:
    technology(website="").clean_fields()


@pytest.mark.parametrize(
    ("fields", "field", "code"),
    [(fields, field, code) for _, fields, field, code in FIELD_REFUSALS],
    ids=[refusal for refusal, _, _, _ in FIELD_REFUSALS],
)
def test_un_champ_refuse_une_valeur_hors_de_ses_regles(
    fields: dict[str, object], field: str, code: str
) -> None:
    with pytest.raises(ValidationError) as refusal:
        technology(**fields).clean_fields()

    assert [refused for refused, _ in refusals(refusal.value, field)] == [code]


@pytest.mark.parametrize(
    ("name", "content"),
    [(name, content) for _, name, content in NOT_SVG],
    ids=[form for form, _, _ in NOT_SVG],
)
def test_une_icone_qui_n_est_pas_un_document_svg_est_refusee(name: str, content: bytes) -> None:
    with pytest.raises(ValidationError) as refusal:
        technology(icon=svg_icon(name, content)).clean_fields()

    assert refusals(refusal.value, "icon") == [("icon_not_svg", strings.ICON_NOT_SVG)]


@pytest.mark.django_db
def test_deux_technologies_ne_portent_pas_le_meme_nom_a_la_casse_pres() -> None:
    technology(name="Django").save()

    with pytest.raises(ValidationError) as refusal:
        technology(name="django").full_clean()

    assert refusals(refusal.value) == [("technology_name_taken", strings.TECHNOLOGY_NAME_TAKEN)]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "constraint"),
    [(fields, constraint) for _, fields, constraint in DATABASE_RULES],
    ids=[rule for rule, _, _ in DATABASE_RULES],
)
def test_la_base_refuse_une_technologie_qui_enfreint_ses_regles(
    fields: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        technology(**fields).save()


@pytest.mark.django_db
def test_la_base_refuse_deux_technologies_du_meme_nom() -> None:
    technology(name="Django").save()

    with (
        pytest.raises(IntegrityError, match="content_technology_name_unique"),
        transaction.atomic(),
    ):
        technology(name="DJANGO").save()
