"""Tableaux en ligne de l'admin dont l'auteur ordonne les lignes par glisser-déposer (ADR 0013).

Un tableau en ligne hérite de `SortableInline`, et son modèle porte un entier `position` : chaque
ligne, enregistrée ou neuve, reçoit une poignée ; `inline_rows.js` réordonne les lignes, remplit
les positions dans l'ordre affiché à l'enregistrement — et remet les index là où Django les lit —,
replace les lignes dans cet ordre quand l'écran revient en erreur, et donne à toute ligne le même
bouton de suppression. On manipule les lignes — ajouter, retirer, déplacer —, puis on enregistre
une fois.

Le script et sa feuille valent pour tout tableau en ligne de l'écran qui les charge, ordonnable ou
non : bouton unique de suppression et libellé des lignes enregistrées retiré compris.

Les technologies d'un projet s'en servent ; la galerie de #9 s'en servira.
"""

from typing import Any, ClassVar

from config import strings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Field, Max, Model
from django.forms import BaseInlineFormSet, HiddenInput, ModelForm
from django.forms import Field as FormField
from django.forms.formsets import DELETION_FIELD_NAME
from django.forms.models import InlineForeignKeyField
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.safestring import SafeString

# Le champ du modèle qui porte l'ordre des lignes.
POSITION = "position"

# Les classes que `inline_rows.js` et `inline_rows.css` lisent : la poignée d'une ligne, et le champ
# caché de sa position.
HANDLE_CLASS = "sortable-handle"
POSITION_CLASS = "sortable-position"


class InlineRowForm[ChildT: Model](ModelForm[ChildT]):
    """Une ligne de tableau en ligne, qu'on peut retirer, rajouter ou changer avant
    l'enregistrement.

    Django vérifierait ligne par ligne, contre la base, les contraintes qui lisent le parent — une
    unicité (parent, objet) — : une ligne que le même envoi supprime ou change y existe encore, et
    reprendre son objet serait refusé. Le formset juge ces unicités entre les lignes qu'il garde
    (`BaseModelFormSet.validate_unique` : unicités sur des champs, sans condition ni expression ;
    lignes supprimées écartées quand toutes les lignes sont valides), et avec les lignes du parent
    que l'envoi ne porte pas (`SortableFormSet.validate_unique`). La base les garantit à la fin
    de l'enregistrement, à condition qu'elles y soient différées (`Deferrable.DEFERRED`) : Django
    écrit les lignes l'une après l'autre, et un échange entre deux lignes passe par un doublon.
    """

    def has_changed(self) -> bool:
        """Une ligne neuve dont seule la position est remplie n'a pas changé : `inline_rows.js`
        numérote toute ligne affichée, et Django doit ignorer encore une ligne neuve laissée vide
        — sans la valider, sans l'enregistrer."""
        if self.instance._state.adding:
            return any(name != POSITION for name in self.changed_data)
        return super().has_changed()

    def validate_constraints(self) -> None:
        """Les contraintes du modèle, hors celles qui lisent le parent et celles des champs déjà
        en erreur."""
        parent = {
            name for name, field in self.fields.items() if isinstance(field, InlineForeignKeyField)
        }
        try:
            self.instance.validate_constraints(exclude=parent | set(self.errors))
        except ValidationError as error:
            self.add_error(None, error)


class SortableFormSet[ChildT: Model, ParentT: Model](
    BaseInlineFormSet[ChildT, ParentT, ModelForm[ChildT]]
):
    """Les lignes d'un tableau en ligne ordonné. Une ligne arrivée sans position, champ caché que
    l'auteur ne voit pas, en reçoit une au lieu d'échouer en base."""

    def get_form_kwargs(self, index: int | None) -> dict[str, Any]:
        """Toute ligne neuve peut rester vide, la première comprise : Django exige sinon les
        `min_num` premières (`BaseFormSet._construct_form`), quelle que soit la ligne que l'auteur a
        remplie ou placée en tête. Quand `validate_min` compte les lignes remplies, le minimum reste
        tenu."""
        kwargs = super().get_form_kwargs(index)
        if self.validate_min and index is not None and index >= self.initial_form_count():
            kwargs["empty_permitted"] = True
        return kwargs

    def _should_delete_form(self, form: ModelForm[ChildT]) -> bool:
        """Une ligne enregistrée dont l'objet a disparu depuis l'ouverture de l'écran — supprimé
        dans un second onglet — compte comme supprimée. Django la saute déjà à l'enregistrement
        (`BaseModelFormSet.save_existing_objects`), mais sa clé, introuvable, refusait sinon tout
        l'envoi, sans message visible : l'admin ne rend pas une ligne sans objet
        (`InlineAdminFormSet.__iter__`). Sinon, la règle de Django : la case « Supprimer ? »."""
        vanished = form in self.initial_forms and form.instance.pk is None
        return vanished or bool(form.cleaned_data.get(DELETION_FIELD_NAME, False))

    def validate_unique(self) -> None:
        """Les unicités qui lisent le parent, entre les lignes gardées (Django) et avec les lignes
        du parent que l'envoi ne porte pas : enregistrées ailleurs depuis l'ouverture de l'écran —
        un second onglet, un envoi renvoyé —, elles ne sont dans aucune ligne, et `InlineRowForm`
        ne juge plus ces unicités contre la base. Refusées ici, elles ne tombent pas sur la base à
        la fin de l'enregistrement."""
        super().validate_unique()
        carried = {form.instance.pk for form in self.initial_forms}
        others = [row for row in self.get_queryset() if row.pk not in carried]
        if not others:
            return
        kept = [form for form in self.forms if form.is_valid() and form not in self.deleted_forms]
        model = self.fk.model._meta
        attnames = {field.name: field.attname for field in model.concrete_fields}
        for constraint in model.total_unique_constraints:
            if self.fk.name not in constraint.fields:
                continue
            columns = [attnames[name] for name in constraint.fields]
            taken = {tuple(getattr(row, column) for column in columns) for row in others}
            for form in kept:
                if tuple(getattr(form.instance, column) for column in columns) in taken:
                    raise ValidationError(self.get_unique_error_message(list(constraint.fields)))
        # ponytail: deux envois simultanés échappent encore à ce contrôle et tombent sur la base à
        # la validation de la transaction, comme les clés étrangères différées de Django ;
        # `connection.check_constraints()` en fin d'enregistrement si cela devient un usage.

    def save_new(self, form: ModelForm[ChildT], commit: bool = True) -> ChildT:
        """Enregistre une ligne neuve. Sans position — le script qui la remplit n'a pas tourné —,
        elle se range après les autres lignes du parent."""
        if form.cleaned_data.get(POSITION) is None:
            siblings = type(form.instance)._default_manager.filter(**{self.fk.name: self.instance})
            last = siblings.aggregate(last=Max(POSITION))["last"]
            setattr(form.instance, POSITION, (last or 0) + 1)
        return super().save_new(form, commit=commit)

    def save_existing(self, form: ModelForm[ChildT], obj: ChildT, commit: bool = True) -> ChildT:
        """Enregistre une ligne enregistrée. Sans position — un envoi que ni l'écran ni le script ne
        produisent —, elle garde la sienne."""
        if form.cleaned_data.get(POSITION) is None:
            setattr(obj, POSITION, form.initial[POSITION])
        return super().save_existing(form, obj, commit=commit)


class SortableInline[ChildT: Model, ParentT: Model](admin.TabularInline[ChildT, ParentT]):
    """Un tableau en ligne dont les lignes s'ordonnent par glisser-déposer, ou au clavier.

    Ses `fields` commencent par `move`, la poignée, et contiennent `position`, qui y est caché. Un
    formset propre à l'écran hérite de `SortableFormSet` ; des `readonly_fields` propres gardent
    `move`, sans quoi Django le cherche parmi les champs du modèle. Une unicité du modèle qui lit
    le parent y est différée (`Deferrable.DEFERRED`, voir `InlineRowForm`) : sinon, un échange
    entre deux lignes enregistrées lèverait une erreur de base.
    """

    form = InlineRowForm
    formset = SortableFormSet
    readonly_fields = ("move",)

    class Media:
        css: ClassVar[dict[str, tuple[str, ...]]] = {"all": ("content/admin/inline_rows.css",)}
        js = ("content/admin/inline_rows.js",)

    @admin.display(description=strings.ADMIN_ROW_ORDER)
    def move(self, row: ChildT) -> SafeString:
        """La poignée de la ligne : un bouton, pour le clavier, que `inline_rows.js` rend
        glissable."""
        return format_html(
            '<button type="button" class="{handle}" aria-label="{label}" title="{label}">'
            '<span aria-hidden="true">⠿</span></button>',
            handle=HANDLE_CLASS,
            label=strings.ADMIN_ROW_MOVE,
        )

    def formfield_for_dbfield(
        self, db_field: Field[Any, Any], request: HttpRequest, **kwargs: Any
    ) -> FormField | None:
        """La position, cachée et facultative : `inline_rows.js` la remplit dans l'ordre affiché ;
        une ligne neuve arrivée sans elle se range après les autres, une ligne enregistrée garde la
        sienne (`SortableFormSet`)."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is not None and db_field.name == POSITION:
            formfield.widget = HiddenInput(attrs={"class": POSITION_CLASS})
            formfield.required = False
        return formfield
