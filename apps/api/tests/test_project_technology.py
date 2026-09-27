"""Tests de la technologie de projet : sa position, l'ordre qu'elle stocke, son unicité dans un
projet, et ce que la suppression d'un projet ou d'une technologie en fait."""

import pytest
from config import strings
from content.models import Project, ProjectTechnology, Technology
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from factories import project, saved, technology
from refusals import refusals


@pytest.fixture
def portfolio() -> Project:
    """Le projet de la fabrique, enregistré."""
    return saved(project())


def link(linked_project: Project, linked: Technology, position: int) -> ProjectTechnology:
    """Une technologie de projet enregistrée : `linked` à la place `position` de
    `linked_project`."""
    return saved(ProjectTechnology(project=linked_project, technology=linked, position=position))


def saved_technology(name: str) -> Technology:
    """Une technologie de la fabrique, enregistrée sous `name`."""
    return saved(technology(name=name))


@pytest.mark.django_db
def test_les_technologies_d_un_projet_se_lisent_dans_l_ordre_de_leur_position(
    portfolio: Project,
) -> None:
    """L'ordre stocké est celui de l'admin (décision 2) : par position, puis, à position égale,
    dans l'ordre de saisie — l'API de #10 l'expose tel quel, il ne doit rien au hasard."""
    django, python, react = (saved_technology(name) for name in ("Django", "Python", "React"))
    # Trois ordres qui divergent : la position, la clé — l'ordre de saisie — et l'écriture en
    # table, où Django, saisi avant Python, est écrit après lui. Sans l'ordre de saisie en second
    # critère, la lecture suivrait la table ; sans la position, elle suivrait la clé.
    for key, linked, position in ((1, react, 2), (3, python, 1), (2, django, 1)):
        ProjectTechnology(pk=key, project=portfolio, technology=linked, position=position).save()

    ordered = [row.technology for row in ProjectTechnology.objects.filter(project=portfolio)]

    assert ordered == [django, python, react]


@pytest.mark.django_db
def test_une_technologie_de_projet_exige_sa_position(portfolio: Project) -> None:
    """Le modèle ne choisit aucune position : l'écran Projet la pose, par le glisser-déposer ou la
    suivante pour une ligne neuve (décision 2, ADR 0013)."""
    unpositioned = ProjectTechnology(project=portfolio, technology=saved_technology("Django"))

    with pytest.raises(ValidationError) as refusal:
        unpositioned.full_clean()

    assert [code for code, _ in refusals(refusal.value, "position")] == ["null"]


@pytest.mark.django_db
def test_la_base_refuse_une_technologie_de_projet_sans_position(portfolio: Project) -> None:
    unpositioned = ProjectTechnology(project=portfolio, technology=saved_technology("Django"))

    with pytest.raises(IntegrityError, match='column "position"'), transaction.atomic():
        unpositioned.save()


@pytest.mark.django_db
def test_une_position_n_est_jamais_negative(portfolio: Project) -> None:
    """Un entier de 0 à 32 767 (glossaire) : le champ refuse une position négative, et la base
    aussi, par la contrainte que Django pose sur un champ positif."""
    negative = ProjectTechnology(
        project=portfolio, technology=saved_technology("Django"), position=-1
    )

    with pytest.raises(ValidationError) as refusal:
        negative.full_clean()
    with (
        pytest.raises(IntegrityError, match="content_projecttechnology_position_check"),
        transaction.atomic(),
    ):
        negative.save()

    assert [code for code, _ in refusals(refusal.value, "position")] == ["min_value"]


@pytest.mark.django_db
def test_un_projet_ne_porte_pas_deux_fois_la_meme_technologie(portfolio: Project) -> None:
    django = saved_technology("Django")
    link(portfolio, django, 1)

    with pytest.raises(ValidationError) as refusal:
        ProjectTechnology(project=portfolio, technology=django, position=2).full_clean()

    assert refusals(refusal.value) == [
        ("project_technology_taken", strings.PROJECT_TECHNOLOGY_TAKEN)
    ]


@pytest.mark.django_db
def test_la_base_refuse_deux_fois_la_meme_technologie_dans_un_projet(portfolio: Project) -> None:
    """L'unicité est différée : Postgres la vérifie à la validation de la transaction, que
    `check_constraints()` avance ici."""
    django = saved_technology("Django")
    link(portfolio, django, 1)

    with (
        pytest.raises(IntegrityError, match="content_project_technology_unique"),
        transaction.atomic(),
    ):
        link(portfolio, django, 2)
        connection.check_constraints()


@pytest.mark.django_db
def test_deux_projets_emploient_la_meme_technologie(portfolio: Project) -> None:
    """L'unicité vaut dans un projet, pas entre projets."""
    django = saved_technology("Django")
    link(portfolio, django, 1)
    other = project(slug="autre")
    other.save()

    shared = ProjectTechnology(project=other, technology=django, position=1)
    shared.full_clean()
    shared.save()


@pytest.mark.django_db
def test_une_technologie_employee_ne_se_supprime_pas(portfolio: Project) -> None:
    """Sa suppression retirerait en silence une ligne au projet, jusqu'à le laisser sans
    technologie : Django la refuse (`PROTECT`), l'admin nomme les projets qui l'emploient."""
    django = saved_technology("Django")
    link(portfolio, django, 1)

    with pytest.raises(ProtectedError):
        django.delete()


@pytest.mark.django_db
def test_un_projet_supprime_emporte_ses_technologies_de_projet_pas_les_technologies(
    portfolio: Project,
) -> None:
    django = saved_technology("Django")
    link(portfolio, django, 1)

    portfolio.delete()

    assert not ProjectTechnology.objects.exists()
    assert list(Technology.objects.all()) == [django]
