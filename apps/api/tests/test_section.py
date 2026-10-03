"""Tests de la section de fiche technique : ses champs, ses règles en base et dans
`full_clean()`, l'ordre qu'elle stocke, et ce que la suppression d'un projet en fait."""

import pytest
from config import strings
from content.models import Project, Section
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, connection, transaction
from factories import BLANK, project, saved, section
from refusals import refusals

# La borne du titre (spec §7) : un titre courant de cette longueur tient sur une ligne de la fiche
# mobile.
TITLE_MAX_LENGTH = 40

# Les règles que la base porte, une contrainte nommée chacune (décision 7), avec le refus de la
# contrainte — code et message du catalogue — et celui que `full_clean()` rend, champ et code.
# Quand le champ refuse lui-même la valeur (vide, hors de la forme d'un slug), Django écarte la
# contrainte : l'admin n'affiche jamais deux messages pour une faute.
DATABASE_GUARDS = [
    (
        "titre vide",
        {"title": ""},
        "content_section_title_not_empty",
        ("section_title_missing", strings.SECTION_TITLE_MISSING),
        ("title", "blank"),
    ),
    (
        f"titre de {TITLE_MAX_LENGTH + 1} caractères",
        {"title": "t" * (TITLE_MAX_LENGTH + 1)},
        "content_section_title_length",
        ("section_title_too_long", strings.SECTION_TITLE_TOO_LONG),
        (NON_FIELD_ERRORS, "section_title_too_long"),
    ),
    (
        "ancre vide",
        {"anchor": ""},
        "content_section_anchor_valid",
        ("section_anchor_invalid", strings.SECTION_ANCHOR_INVALID),
        ("anchor", "blank"),
    ),
    (
        "ancre avec une espace",
        {"anchor": "mon ancre"},
        "content_section_anchor_valid",
        ("section_anchor_invalid", strings.SECTION_ANCHOR_INVALID),
        ("anchor", "invalid"),
    ),
    (
        "ancre accentuée",
        {"anchor": "données"},
        "content_section_anchor_valid",
        ("section_anchor_invalid", strings.SECTION_ANCHOR_INVALID),
        ("anchor", "invalid"),
    ),
    # Le champ de slug accepte le souligné ; la spec §7 ne le prévoit pas : seule la contrainte le
    # refuse.
    (
        "ancre avec un souligné",
        {"anchor": "mon_ancre"},
        "content_section_anchor_valid",
        ("section_anchor_invalid", strings.SECTION_ANCHOR_INVALID),
        (NON_FIELD_ERRORS, "section_anchor_invalid"),
    ),
    (
        "corps vide",
        {"body": ""},
        "content_section_body_not_empty",
        ("section_body_missing", strings.SECTION_BODY_MISSING),
        ("body", "blank"),
    ),
    (
        "corps fait d'espaces",
        {"body": BLANK},
        "content_section_body_not_empty",
        ("section_body_missing", strings.SECTION_BODY_MISSING),
        (NON_FIELD_ERRORS, "section_body_missing"),
    ),
]
GUARD_IDS = [guard for guard, *_ in DATABASE_GUARDS]


@pytest.fixture
def portfolio() -> Project:
    """Le projet de la fabrique, enregistré."""
    return saved(project())


def test_une_section_porte_un_projet_un_titre_une_ancre_un_corps_et_une_position() -> None:
    assert [field.name for field in Section._meta.concrete_fields] == [
        "id",
        "project",
        "title",
        "anchor",
        "body",
        "position",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [{}, {"title": "t" * TITLE_MAX_LENGTH}, {"anchor": "Tests-et-qualite-2"}],
    ids=["section de la fabrique", "titre à la borne", "ancre en majuscules et chiffres"],
)
def test_une_section_accepte_des_valeurs_dans_ses_regles(
    portfolio: Project, fields: dict[str, object]
) -> None:
    """`django_db` : `full_clean()` fait évaluer les contraintes par la base."""
    section(portfolio, **fields).full_clean()


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
def test_une_espace_insecable_seule_compte_comme_un_texte_en_base(portfolio: Project) -> None:
    """`\\S` suit la locale libc de l'image : une locale ICU ferait de l'espace insécable une
    espace, et la règle changerait sans un mot."""
    lone = section(portfolio, body=" ")

    lone.full_clean()
    lone.save()


@pytest.mark.django_db
def test_une_section_exige_sa_position(portfolio: Project) -> None:
    """Le modèle ne choisit aucune position : l'écran Projet la pose, par le glisser-déposer ou la
    suivante pour une ligne neuve (D55)."""
    with pytest.raises(ValidationError) as refusal:
        section(portfolio, position=None).full_clean()

    assert [code for code, _ in refusals(refusal.value, "position")] == ["null"]


@pytest.mark.django_db
def test_les_sections_d_un_projet_se_lisent_dans_l_ordre_de_leur_position(
    portfolio: Project,
) -> None:
    """L'ordre stocké est celui de l'admin : par position, puis dans l'ordre de saisie — l'API de
    #10 l'expose tel quel. Trois ordres qui divergent : position, clé, écriture en table."""
    for key, anchor, position in ((1, "bilan", 2), (3, "stack", 1), (2, "contexte", 1)):
        Section(
            pk=key, project=portfolio, title=anchor, anchor=anchor, body="Texte.", position=position
        ).save()

    ordered = [row.anchor for row in Section.objects.filter(project=portfolio)]

    assert ordered == ["contexte", "stack", "bilan"]


@pytest.mark.django_db
def test_un_projet_ne_porte_pas_deux_fois_la_meme_ancre(portfolio: Project) -> None:
    saved(section(portfolio))

    with pytest.raises(ValidationError) as refusal:
        section(portfolio, title="Autre titre", position=2).full_clean()

    assert refusals(refusal.value) == [("section_anchor_taken", strings.SECTION_ANCHOR_TAKEN)]


@pytest.mark.django_db
def test_la_base_refuse_deux_fois_la_meme_ancre_dans_un_projet(portfolio: Project) -> None:
    """L'unicité est différée : Postgres la vérifie à la validation de la transaction, que
    `check_constraints()` avance ici."""
    saved(section(portfolio))

    with pytest.raises(IntegrityError, match="content_section_anchor_unique"), transaction.atomic():
        saved(section(portfolio, title="Autre titre", position=2))
        connection.check_constraints()


@pytest.mark.django_db
def test_deux_projets_portent_chacun_la_meme_ancre(portfolio: Project) -> None:
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
