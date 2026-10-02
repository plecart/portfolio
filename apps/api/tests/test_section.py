"""Tests de la section de fiche technique : ses onze clés, ses règles en base et dans
`full_clean()`, et ce que la suppression d'un projet en fait."""

import pytest
from config import strings
from content.models import Project, Section, SectionKey
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from factories import project, saved, section
from refusals import refusals

# Un corps fait d'espaces seulement — espace, retour à la ligne, tabulation : vide pour l'auteur
# comme pour le site (décision 7).
BLANK_BODY = " \n\t "

# Les règles que la base porte, une contrainte nommée chacune (décision 5), avec le refus de la
# contrainte — code et message du catalogue — et celui que `full_clean()` rend, champ et code. Le
# champ refuse lui-même un corps vide et une clé hors de ses choix, et Django écarte alors la
# contrainte : l'admin n'affiche jamais deux messages pour une faute. Un corps d'espaces, que le
# champ accepte, n'est refusé que par la contrainte.
DATABASE_GUARDS = [
    (
        "corps vide",
        {"body": ""},
        "content_section_body_not_empty",
        ("section_body_missing", strings.SECTION_BODY_MISSING),
        ("body", "blank"),
    ),
    (
        "corps fait d'espaces",
        {"body": BLANK_BODY},
        "content_section_body_not_empty",
        ("section_body_missing", strings.SECTION_BODY_MISSING),
        (NON_FIELD_ERRORS, "section_body_missing"),
    ),
    (
        "clé hors de l'énumération",
        {"key": "autre"},
        "content_section_key_valid",
        ("section_key_unknown", strings.SECTION_KEY_UNKNOWN),
        ("key", "invalid_choice"),
    ),
]
GUARD_IDS = [guard for guard, *_ in DATABASE_GUARDS]


@pytest.fixture
def portfolio() -> Project:
    """Le projet de la fabrique, enregistré."""
    return saved(project())


def test_les_cles_des_sections_sont_les_ancres_de_la_spec_dans_l_ordre() -> None:
    """Les valeurs stockées sont les ancres `#s-<clé>` du site et du RAG (spec §4.3, US 57),
    exposées telles quelles par l'API (#10) : un contrat, dans l'ordre de l'écran et du site."""
    assert SectionKey.values == [
        "contexte",
        "stack",
        "architecture",
        "donnees",
        "securite",
        "asynchrone",
        "api",
        "deploiement",
        "tests",
        "decisions",
        "bilan",
    ]


def test_une_section_porte_un_projet_une_cle_et_un_corps() -> None:
    assert [field.name for field in Section._meta.concrete_fields] == [
        "id",
        "project",
        "key",
        "body",
    ]


@pytest.mark.django_db
def test_une_section_valide_passe_ses_regles(portfolio: Project) -> None:
    """`django_db` : `full_clean()` fait évaluer les contraintes par la base."""
    section(portfolio).full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "cleaned"),
    [(fields, cleaned) for _, fields, _, _, cleaned in DATABASE_GUARDS],
    ids=GUARD_IDS,
)
def test_full_clean_refuse_une_section_hors_de_ses_regles(
    portfolio: Project, fields: dict[str, object], cleaned: tuple[str, str]
) -> None:
    """Un seul refus, sur un seul champ."""
    field, code = cleaned
    with pytest.raises(ValidationError) as error:
        section(portfolio, **fields).full_clean()

    assert error.value.error_dict.keys() == {field}
    assert [refused for refused, _ in refusals(error.value, field)] == [code]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "refusal"),
    [(fields, refusal) for _, fields, _, refusal, _ in DATABASE_GUARDS],
    ids=GUARD_IDS,
)
def test_une_garde_de_la_base_refuse_avec_le_code_et_le_message_du_catalogue(
    portfolio: Project, fields: dict[str, object], refusal: tuple[str, str]
) -> None:
    """`validate_constraints()` seul rend le refus de la contrainte, que `full_clean()` écarte
    quand le champ est déjà en erreur."""
    with pytest.raises(ValidationError) as error:
        section(portfolio, **fields).validate_constraints()

    assert refusals(error.value) == [refusal]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "constraint"),
    [(fields, constraint) for _, fields, constraint, _, _ in DATABASE_GUARDS],
    ids=GUARD_IDS,
)
def test_la_base_refuse_une_section_qui_enfreint_ses_regles(
    portfolio: Project, fields: dict[str, object], constraint: str
) -> None:
    """Pour une ligne écrite hors de l'admin, que l'API de #10 tiendra pour valide."""
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        section(portfolio, **fields).save()


@pytest.mark.django_db
def test_un_projet_ne_porte_pas_deux_fois_la_meme_section(portfolio: Project) -> None:
    saved(section(portfolio))

    with pytest.raises(ValidationError) as refusal:
        section(portfolio, body="Autre texte.").full_clean()

    assert refusals(refusal.value) == [("section_key_taken", strings.SECTION_KEY_TAKEN)]


@pytest.mark.django_db
def test_la_base_refuse_deux_fois_la_meme_section_dans_un_projet(portfolio: Project) -> None:
    saved(section(portfolio))

    with pytest.raises(IntegrityError, match="content_section_key_unique"), transaction.atomic():
        section(portfolio, body="Autre texte.").save()


@pytest.mark.django_db
def test_deux_projets_portent_chacun_la_meme_section(portfolio: Project) -> None:
    """L'unicité vaut dans un projet, pas entre projets."""
    saved(section(portfolio))
    other = saved(project(slug="autre"))

    shared = section(other)
    shared.full_clean()
    shared.save()


@pytest.mark.django_db
def test_un_projet_supprime_emporte_ses_sections(portfolio: Project) -> None:
    saved(section(portfolio))

    portfolio.delete()

    assert not Section.objects.exists()
