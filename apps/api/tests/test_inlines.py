"""Tests du tableau en ligne ordonnable générique (`content/inlines.py`), hors de tout écran : ce
dont les technologies, la galerie et les sections d'un projet héritent."""

import inspect

import pytest
from config import strings
from content.inlines import InlineRowForm, SortableFormSet, SortableInline
from content.models import Project, ProjectTechnology
from django.apps import apps
from django.contrib import admin
from django.core.exceptions import NON_FIELD_ERRORS
from django.db.models import Deferrable
from django.forms import (
    BaseInlineFormSet,
    ModelForm,
    inlineformset_factory,
    model_to_dict,
    modelform_factory,
)
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


def test_toute_unicite_d_un_tableau_ordonnable_qui_lit_le_parent_est_differee() -> None:
    """Django écrit les lignes l'une après l'autre (`BaseModelFormSet.save_existing_objects`) :
    deux lignes qui échangent leurs objets passent par un doublon, que la base ne doit juger qu'à
    la fin de l'enregistrement (`InlineRowForm`). Vaut pour tout tableau en ligne de l'admin qui
    hérite de `SortableInline`."""
    sortable = [
        (parent, inspect.getattr_static(inline, "model"))
        for parent in apps.get_models()
        if admin.site.is_registered(parent)
        for inline in admin.site.get_model_admin(parent).inlines
        if issubclass(inline, SortableInline)
    ]
    reading_parent = {
        f"{child.__name__}.{constraint.name}": constraint.deferrable
        for parent, child in sortable
        for constraint in child._meta.total_unique_constraints
        if any(child._meta.get_field(name).related_model is parent for name in constraint.fields)
    }

    assert reading_parent
    assert reading_parent == dict.fromkeys(reading_parent, Deferrable.DEFERRED)


@pytest.mark.parametrize(
    ("validate_min", "optional"),
    [(False, [False, True]), (True, [True, True])],
    ids=["minimum tenu par les lignes obligatoires", "minimum compte sur les lignes remplies"],
)
def test_la_premiere_ligne_neuve_n_est_facultative_que_si_le_minimum_se_compte(
    validate_min: bool, optional: list[bool]
) -> None:
    """Sans `validate_min`, les `min_num` premières lignes neuves, obligatoires, sont le seul
    minimum du tableau : `SortableFormSet` ne les rend facultatives que quand le minimum se compte
    sur les lignes remplies."""
    formset_class: type[BaseInlineFormSet[ProjectTechnology, Project, ModelForm[ProjectTechnology]]]
    formset_class = inlineformset_factory(
        Project,
        ProjectTechnology,
        form=InlineRowForm,
        formset=SortableFormSet,
        fields=("technology", "position"),
        min_num=1,
        validate_min=validate_min,
        extra=1,
    )

    assert [form.empty_permitted for form in formset_class().forms] == optional
