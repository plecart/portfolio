"""Tests du projet : ses champs, ses règles — celles que la base porte, avec leur code et le
message du catalogue —, la vitrine unique, le brouillon par défaut et les horodatages."""

from datetime import UTC, datetime, timedelta

import pytest
from config import strings
from content.models import Project, ProjectKind, ProjectStatus
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from factories import BLANK, STARTED_ON, project, url_of_length
from refusals import refusals

# Les bornes de la spec (§7) et les bornes techniques décidées au lot 1 : écrites ici, et non lues
# sur le modèle, pour qu'une borne changée dans le modèle fasse rougir ce fichier.
TITLE_MAX_LENGTH = 30
SUMMARY_MAX_LENGTH = 120
WORD_MAX_LENGTH = 20
SLUG_MAX_LENGTH = 50
CLIENT_MAX_LENGTH = 100
URL_MAX_LENGTH = 200

# Deux dates autour du début du projet de la fabrique.
DAY_BEFORE = STARTED_ON - timedelta(days=1)
DAY_AFTER = STARTED_ON + timedelta(days=1)

# Deux instants d'enregistrement, pour lire les horodatages sans dépendre de l'horloge.
CREATED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 9, 2, 18, 30, tzinfo=UTC)

# Les champs d'un projet, dans l'ordre de leur déclaration : ceux du PRD (« Modèle de contenu »),
# moins la couverture, qui est la première image de sa galerie (`GalleryImage`), plus la clé, la
# position (cadrage §6.1, D77) et les horodatages.
PROJECT_FIELDS = [
    "id",
    "title",
    "slug",
    "summary",
    "description",
    "kind",
    "status",
    "started_on",
    "finished_on",
    "client",
    "repository_url",
    "demo_url",
    "showcase",
    "published",
    "position",
    "created_at",
    "updated_at",
]


def summary_of_length(length: int) -> str:
    """Un résumé de `length` caractères dont aucun mot n'approche la borne des mots."""
    return ("résumé " * length)[:length]


# Ce que le projet accepte : chaque borne atteinte sans être dépassée — l'autre côté est dans
# `SPEC_RULES` ou `FIELD_REFUSALS` —, chaque type, le mot à traits d'union de la décision 4 et les
# dates de la décision 5.
ACCEPTANCES: list[tuple[str, dict[str, object]]] = [
    ("projet de la fabrique", {}),
    ("projet pro", {"kind": ProjectKind.PROFESSIONAL}),
    ("projet d'école", {"kind": ProjectKind.SCHOOL}),
    (f"titre de {TITLE_MAX_LENGTH} caractères", {"title": "t" * TITLE_MAX_LENGTH}),
    (
        f"résumé de {SUMMARY_MAX_LENGTH} caractères",
        {"summary": summary_of_length(SUMMARY_MAX_LENGTH)},
    ),
    (f"mot de {WORD_MAX_LENGTH} caractères", {"summary": "m" * WORD_MAX_LENGTH}),
    ("mots joints par des traits d'union", {"summary": "text-embeddings-inference"}),
    (
        "projet terminé le jour de son début",
        {"status": ProjectStatus.FINISHED, "finished_on": STARTED_ON},
    ),
    (
        "projet archivé après son début",
        {"status": ProjectStatus.ARCHIVED, "finished_on": DAY_AFTER},
    ),
    (f"slug de {SLUG_MAX_LENGTH} caractères", {"slug": "s" * SLUG_MAX_LENGTH}),
    ("slug de chiffres, traits d'union et soulignés", {"slug": "projet-2_bis"}),
    # `\S` suit la locale libc de l'image, comme pour le corps d'une section : une espace
    # insécable seule y compte comme un texte.
    ("description d'une espace insécable seule", {"description": "\N{NO-BREAK SPACE}"}),
    (f"client de {CLIENT_MAX_LENGTH} caractères", {"client": "c" * CLIENT_MAX_LENGTH}),
    (
        f"liens de {URL_MAX_LENGTH} caractères",
        {
            "repository_url": url_of_length(URL_MAX_LENGTH),
            "demo_url": url_of_length(URL_MAX_LENGTH),
        },
    ),
]

# Les refus que les champs portent eux-mêmes — bornes techniques, forme, liste, présence — et le
# code que Django leur donne, seul refus de `full_clean()` : Django écarte la contrainte d'un champ
# déjà en erreur, l'admin n'affiche jamais deux messages pour une faute. Ces messages-là sont ceux
# de Django, traduits par `LANGUAGE_CODE`.
FIELD_REFUSALS = [
    ("slug absent", {"slug": ""}, "slug", "blank"),
    (
        f"slug de {SLUG_MAX_LENGTH + 1} caractères",
        {"slug": "s" * (SLUG_MAX_LENGTH + 1)},
        "slug",
        "max_length",
    ),
    ("slug hors de sa forme", {"slug": "mon projet"}, "slug", "invalid"),
    ("slug accentué", {"slug": "projét"}, "slug", "invalid"),
    ("titre absent", {"title": ""}, "title", "blank"),
    ("résumé absent", {"summary": ""}, "summary", "blank"),
    ("description absente", {"description": ""}, "description", "blank"),
    ("type absent", {"kind": ""}, "kind", "blank"),
    ("type hors de sa liste", {"kind": "autre"}, "kind", "invalid_choice"),
    ("statut absent", {"status": ""}, "status", "blank"),
    ("statut hors de sa liste", {"status": "autre"}, "status", "invalid_choice"),
    ("date de début absente", {"started_on": None}, "started_on", "null"),
    (
        f"client de {CLIENT_MAX_LENGTH + 1} caractères",
        {"client": "c" * (CLIENT_MAX_LENGTH + 1)},
        "client",
        "max_length",
    ),
    (
        f"lien du dépôt de {URL_MAX_LENGTH + 1} caractères",
        {"repository_url": url_of_length(URL_MAX_LENGTH + 1)},
        "repository_url",
        "max_length",
    ),
    ("lien du dépôt hors de sa forme", {"repository_url": "depot"}, "repository_url", "invalid"),
    (
        f"lien de la démo de {URL_MAX_LENGTH + 1} caractères",
        {"demo_url": url_of_length(URL_MAX_LENGTH + 1)},
        "demo_url",
        "max_length",
    ),
    ("lien de la démo hors de sa forme", {"demo_url": "demo"}, "demo_url", "invalid"),
]

# Ce que la base porte en plus d'une validation de champ (PR #49, arbitrage I8 du mainteneur) :
# pour une ligne écrite hors de l'admin, que l'API de #10 tient pour valide. Le statut hors de sa
# liste porte une date de fin, pour n'enfreindre que sa propre contrainte.
DATABASE_GUARDS = [
    (
        "slug vide",
        {"slug": ""},
        "content_project_slug_valid",
        ("project_slug_invalid", strings.PROJECT_SLUG_INVALID),
    ),
    (
        "slug hors de sa forme",
        {"slug": "mon projet"},
        "content_project_slug_valid",
        ("project_slug_invalid", strings.PROJECT_SLUG_INVALID),
    ),
    (
        "slug accentué",
        {"slug": "projét"},
        "content_project_slug_valid",
        ("project_slug_invalid", strings.PROJECT_SLUG_INVALID),
    ),
    (
        "titre vide",
        {"title": ""},
        "content_project_title_not_empty",
        ("project_title_missing", strings.PROJECT_TITLE_MISSING),
    ),
    (
        "résumé vide",
        {"summary": ""},
        "content_project_summary_not_empty",
        ("project_summary_missing", strings.PROJECT_SUMMARY_MISSING),
    ),
    (
        "description vide",
        {"description": ""},
        "content_project_description_not_empty",
        ("project_description_missing", strings.PROJECT_DESCRIPTION_MISSING),
    ),
    (
        "type hors de sa liste",
        {"kind": "autre"},
        "content_project_kind_valid",
        ("project_kind_unknown", strings.PROJECT_KIND_UNKNOWN),
    ),
    (
        "statut hors de sa liste",
        {"status": "autre", "finished_on": DAY_AFTER},
        "content_project_status_valid",
        ("project_status_unknown", strings.PROJECT_STATUS_UNKNOWN),
    ),
]

# Les règles de la spec (§7) et du brief (décisions 4 et 5), une contrainte nommée chacune : la
# base les garantit, et `full_clean()` — donc l'admin — les refuse avec leur code et le message du
# catalogue, sans autre refus.
SPEC_RULES = [
    (
        f"titre de {TITLE_MAX_LENGTH + 1} caractères",
        {"title": "t" * (TITLE_MAX_LENGTH + 1)},
        "content_project_title_length",
        ("project_title_too_long", strings.PROJECT_TITLE_TOO_LONG),
    ),
    (
        f"résumé de {SUMMARY_MAX_LENGTH + 1} caractères",
        {"summary": summary_of_length(SUMMARY_MAX_LENGTH + 1)},
        "content_project_summary_length",
        ("project_summary_too_long", strings.PROJECT_SUMMARY_TOO_LONG),
    ),
    (
        f"mot de {WORD_MAX_LENGTH + 1} caractères",
        {"summary": "m" * (WORD_MAX_LENGTH + 1)},
        "content_project_summary_words",
        ("project_summary_word_too_long", strings.PROJECT_SUMMARY_WORD_TOO_LONG),
    ),
    # Une description d'espaces est vide pour l'auteur comme pour le site ; l'admin la garde
    # telle que saisie (aperçu Markdown, #8), c'est donc la base qui la refuse.
    (
        "description faite d'espaces",
        {"description": BLANK},
        "content_project_description_not_empty",
        ("project_description_missing", strings.PROJECT_DESCRIPTION_MISSING),
    ),
    (
        "mot trop long au milieu d'un résumé",
        {"summary": "Un projet anticonstitutionnellement court."},
        "content_project_summary_words",
        ("project_summary_word_too_long", strings.PROJECT_SUMMARY_WORD_TOO_LONG),
    ),
    # La liste des séparateurs est fermée (décision 4) : ni l'espace insécable ni l'espace
    # fine insécable, usuelles en typographie française, ni la barre oblique — un navigateur ne
    # coupe pas la ligne à une insécable.
    (
        "mots joints par une espace insécable",
        {"summary": "\N{NO-BREAK SPACE}".join(["m" * 10, "m" * 10])},
        "content_project_summary_words",
        ("project_summary_word_too_long", strings.PROJECT_SUMMARY_WORD_TOO_LONG),
    ),
    (
        "mots joints par une espace fine insécable",
        {"summary": "\N{NARROW NO-BREAK SPACE}".join(["m" * 10, "m" * 10])},
        "content_project_summary_words",
        ("project_summary_word_too_long", strings.PROJECT_SUMMARY_WORD_TOO_LONG),
    ),
    (
        "mots joints par une barre oblique",
        {"summary": "/".join(["m" * 10, "m" * 10])},
        "content_project_summary_words",
        ("project_summary_word_too_long", strings.PROJECT_SUMMARY_WORD_TOO_LONG),
    ),
    (
        "projet terminé sans date de fin",
        {"status": ProjectStatus.FINISHED},
        "content_project_finished_on_required",
        ("project_finished_on_missing", strings.PROJECT_FINISHED_ON_MISSING),
    ),
    (
        "projet archivé sans date de fin",
        {"status": ProjectStatus.ARCHIVED},
        "content_project_finished_on_required",
        ("project_finished_on_missing", strings.PROJECT_FINISHED_ON_MISSING),
    ),
    (
        "projet en cours avec une date de fin",
        {"finished_on": DAY_AFTER},
        "content_project_ongoing_unfinished",
        ("project_ongoing_finished", strings.PROJECT_ONGOING_FINISHED),
    ),
    (
        "date de fin avant la date de début",
        {"status": ProjectStatus.FINISHED, "finished_on": DAY_BEFORE},
        "content_project_dates_ordered",
        ("project_dates_reversed", strings.PROJECT_DATES_REVERSED),
    ),
]


# Les colonnes qu'une règle exige, obligatoires en base : une contrainte de vérification qui lit
# NULL rend « inconnu » et laisse passer la ligne — seule la colonne `NOT NULL` la refuse. La date
# de début est obligatoire d'elle-même (PRD « Modèle de contenu »).
REQUIRED_COLUMNS = ["title", "slug", "summary", "description", "kind", "status", "started_on"]


def test_un_projet_porte_les_champs_du_prd_et_aucun_champ_en_ligne() -> None:
    """« En ligne » n'est pas un champ : le front le déduit de la présence du lien démo (spec §7,
    « Statuts » ; ADR 0010), et le back n'en calcule rien (décision du lot 1 de #7)."""
    assert [field.name for field in Project._meta.concrete_fields] == PROJECT_FIELDS


def test_les_valeurs_du_type_et_du_statut_sont_celles_que_l_api_expose() -> None:
    """Les valeurs stockées sont un contrat : l'API les expose telles quelles (ADR 0010), et le
    glossaire les nomme. Leurs libellés, eux, sont tenus par l'écran (`test_project_admin.py`)."""
    assert ProjectKind.values == ["personal", "professional", "school"]
    assert ProjectStatus.values == ["ongoing", "finished", "archived"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [fields for _, fields in ACCEPTANCES],
    ids=[acceptance for acceptance, _ in ACCEPTANCES],
)
def test_un_projet_accepte_des_valeurs_dans_ses_regles(fields: dict[str, object]) -> None:
    """`django_db` : `full_clean()` fait évaluer les contraintes par la base."""
    project(**fields).full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "refusal"),
    [(fields, refusal) for _, fields, _, refusal in SPEC_RULES],
    ids=[rule for rule, _, _, _ in SPEC_RULES],
)
def test_une_regle_de_la_spec_refuse_avec_le_code_et_le_message_du_catalogue(
    fields: dict[str, object], refusal: tuple[str, str]
) -> None:
    with pytest.raises(ValidationError) as error:
        project(**fields).full_clean()

    assert error.value.error_dict.keys() == {NON_FIELD_ERRORS}
    assert refusals(error.value) == [refusal]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "field", "code"),
    [(fields, field, code) for _, fields, field, code in FIELD_REFUSALS],
    ids=[refusal for refusal, _, _, _ in FIELD_REFUSALS],
)
def test_un_champ_refuse_une_valeur_hors_de_ses_regles(
    fields: dict[str, object], field: str, code: str
) -> None:
    with pytest.raises(ValidationError) as refusal:
        project(**fields).full_clean()

    assert refusal.value.error_dict.keys() == {field}
    assert [refused for refused, _ in refusals(refusal.value, field)] == [code]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "refusal"),
    [(fields, refusal) for _, fields, _, refusal in DATABASE_GUARDS],
    ids=[guard for guard, _, _, _ in DATABASE_GUARDS],
)
def test_une_garde_de_la_base_refuse_avec_le_code_et_le_message_du_catalogue(
    fields: dict[str, object], refusal: tuple[str, str]
) -> None:
    """`validate_constraints()` seul rend ces refus : `full_clean()` écarte la contrainte d'un
    champ déjà en erreur, et l'admin n'affiche que le refus du champ."""
    with pytest.raises(ValidationError) as error:
        project(**fields).validate_constraints()

    assert refusals(error.value) == [refusal]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "constraint"),
    [(fields, constraint) for _, fields, constraint, _ in SPEC_RULES + DATABASE_GUARDS],
    ids=[rule for rule, _, _, _ in SPEC_RULES + DATABASE_GUARDS],
)
def test_la_base_refuse_un_projet_qui_enfreint_ses_regles(
    fields: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        project(**fields).save()


@pytest.mark.django_db
@pytest.mark.parametrize("column", REQUIRED_COLUMNS)
def test_la_base_refuse_un_projet_sans_valeur_dans_une_colonne_obligatoire(column: str) -> None:
    """Postgres nomme la colonne dans son refus (« null value in column … »), qu'il vérifie avant
    toute contrainte de vérification."""
    with pytest.raises(IntegrityError, match=f'column "{column}"'), transaction.atomic():
        project(**{column: None}).save()


@pytest.mark.django_db
def test_deux_projets_ne_portent_pas_le_meme_slug() -> None:
    """Code et message du catalogue, là où `unique=True` imposerait le code `unique` de Django."""
    project().save()

    with pytest.raises(ValidationError) as refusal:
        project(title="Autre").full_clean()

    assert refusals(refusal.value) == [("project_slug_taken", strings.PROJECT_SLUG_TAKEN)]


@pytest.mark.django_db
def test_la_base_refuse_deux_projets_du_meme_slug() -> None:
    project().save()

    with (
        pytest.raises(IntegrityError, match="content_project_slug_unique"),
        transaction.atomic(),
    ):
        project(title="Autre").save()


@pytest.mark.django_db
def test_un_seul_projet_est_la_vitrine() -> None:
    project(showcase=True).save()

    with pytest.raises(ValidationError) as refusal:
        project(slug="autre", showcase=True).full_clean()

    assert refusals(refusal.value) == [("project_showcase_taken", strings.PROJECT_SHOWCASE_TAKEN)]


@pytest.mark.django_db
def test_la_base_refuse_une_seconde_vitrine() -> None:
    project(showcase=True).save()

    with (
        pytest.raises(IntegrityError, match="content_project_single_showcase"),
        transaction.atomic(),
    ):
        project(slug="autre", showcase=True).save()


@pytest.mark.django_db
def test_la_vitrine_ne_gene_ni_elle_meme_ni_les_autres_projets() -> None:
    """L'unicité ne vaut que pour la vitrine vraie : la vitrine enregistrée se revalide, et les
    projets hors vitrine s'ajoutent sans limite."""
    showcase = project(showcase=True)
    showcase.save()
    showcase.full_clean()
    for slug in ("deux", "trois"):
        other = project(slug=slug)
        other.full_clean()
        other.save()


@pytest.mark.django_db
def test_un_projet_nait_brouillon() -> None:
    """Un projet n'apparaît sur le site que publié (PRD, US 41) ; il naît brouillon."""
    created = project()
    created.save()
    created.refresh_from_db()

    assert created.published is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("stored", "expected"),
    [([1, 2, 5], 6), ([], 1)],
    ids=["après le dernier, brouillon compris", "base vide"],
)
def test_un_projet_enregistre_sans_position_se_range_apres_tous_les_projets(
    stored: list[int], expected: int
) -> None:
    """Spec §1.9 : un projet neuf se range en dernier, sur tous les projets — le dernier enregistré
    est un brouillon, qui garde son rang ; les projets enregistrés avec une position la gardent."""
    for position in stored:
        project(
            slug=f"projet-{position}", position=position, published=position != stored[-1]
        ).save()

    created = project(slug="neuf")
    created.save()
    created.refresh_from_db()

    assert created.position == expected
    assert list(Project.objects.exclude(pk=created.pk).values_list("position", flat=True)) == stored


@pytest.mark.django_db
def test_un_projet_date_sa_creation_et_sa_derniere_modification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Django date les deux champs par `timezone.now()` à l'enregistrement : la création une fois,
    la modification à chaque fois."""
    edited = project()
    monkeypatch.setattr(timezone, "now", lambda: CREATED_AT)
    edited.save()
    monkeypatch.setattr(timezone, "now", lambda: UPDATED_AT)
    edited.save()
    edited.refresh_from_db()

    assert (edited.created_at, edited.updated_at) == (CREATED_AT, UPDATED_AT)
