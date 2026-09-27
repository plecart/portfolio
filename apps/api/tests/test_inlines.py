"""Tests du tableau en ligne ordonnable générique (`content/inlines.py`), hors de tout écran : ce
dont la galerie de #9 héritera."""

import inspect

import pytest
from config import strings
from content.inlines import InlineRowForm, SortableFormSet, SortableInline
from content.models import Project
from django.core.exceptions import NON_FIELD_ERRORS
from django.forms import model_to_dict, modelform_factory
from factories import project, saved


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("slug", "fields_in_error", "refusals"),
    [("portfolio", set[str](), [strings.PROJECT_SLUG_TAKEN]), ("mon projet", {"slug"}, [])],
    ids=["contrainte qui ne lit pas le parent", "champ déjà en erreur"],
)
def test_une_ligne_juge_les_contraintes_qui_ne_lisent_pas_le_parent(
    slug: str, fields_in_error: set[str], refusals: list[str]
) -> None:
    """`InlineRowForm` n'écarte que les contraintes qui lisent le parent, et celles des champs déjà
    en erreur, qui n'affichent pas un second message. Le projet, sans parent, sert de modèle :
    toutes ses contraintes s'y appliquent."""
    saved(project())
    form_class = modelform_factory(Project, form=InlineRowForm, fields="__all__")
    data = {
        name: value
        for name, value in model_to_dict(project(slug=slug)).items()
        if value not in (None, False, "")
    }

    form = form_class(data)

    assert not form.is_valid()
    assert set(form.errors) - {NON_FIELD_ERRORS} == fields_in_error
    assert form.non_field_errors() == refusals


def test_un_tableau_ordonnable_range_par_defaut_ses_lignes_neuves_sans_position() -> None:
    """Un tableau qui n'a pas de formset propre hérite de `SortableFormSet`, qui pose la position
    d'une ligne arrivée sans elle. Lu sans résolution générique, que pyright strict refuse sur la
    classe."""
    assert issubclass(inspect.getattr_static(SortableInline, "formset"), SortableFormSet)
