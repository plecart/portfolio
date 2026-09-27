"""Tableaux en ligne de l'admin dont l'auteur ordonne les lignes par glisser-déposer (ADR 0013).

Un tableau en ligne hérite de `SortableInline`, et son modèle porte un entier `position` : chaque
ligne, enregistrée ou neuve, reçoit une poignée ; `inline_rows.js` réordonne les lignes, remplit
les positions dans l'ordre affiché à l'enregistrement et donne à toute ligne le même bouton de
suppression. On manipule les lignes — ajouter, retirer, déplacer —, puis on enregistre une fois.

Les technologies d'un projet s'en servent ; la galerie de #9 s'en servira.
"""

from typing import Any, ClassVar

from config import strings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Field, Max, Model
from django.forms import BaseInlineFormSet, HiddenInput, ModelForm
from django.forms import Field as FormField
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
    """Une ligne de tableau en ligne, qu'on peut retirer puis rajouter avant l'enregistrement.

    Django vérifierait ligne par ligne, contre la base, les contraintes qui lisent le parent — une
    unicité (parent, objet) — : une ligne que le même envoi supprime y existe encore, et la rajouter
    serait refusé. Le formset les juge entre les lignes qu'il garde
    (`BaseModelFormSet.validate_unique`, lignes supprimées écartées), et la base les garantit à
    l'enregistrement, qui supprime avant d'ajouter.
    """

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
    """Les lignes d'un tableau en ligne ordonné."""

    def save_new(self, form: ModelForm[ChildT], commit: bool = True) -> ChildT:
        """Enregistre une ligne neuve. Sans position — le script qui la remplit n'a pas tourné —,
        elle se range après les autres lignes du parent, au lieu d'échouer sur un champ que l'auteur
        ne voit pas."""
        row = super().save_new(form, commit=False)
        if form.cleaned_data.get(POSITION) is None:
            siblings = type(row)._default_manager.filter(**{self.fk.name: self.instance})
            last = siblings.aggregate(last=Max(POSITION))["last"]
            setattr(row, POSITION, (last or 0) + 1)
        if commit:
            row.save()
        return row


class SortableInline[ChildT: Model, ParentT: Model](admin.TabularInline[ChildT, ParentT]):
    """Un tableau en ligne dont les lignes s'ordonnent par glisser-déposer, ou au clavier.

    Ses `fields` commencent par `move`, la poignée, et contiennent `position`, qui y est caché. Un
    formset propre à l'écran hérite de `SortableFormSet`.
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
        """La position, cachée et facultative : `inline_rows.js` la remplit dans l'ordre affiché, et
        une ligne arrivée sans elle se range après les autres (`SortableFormSet.save_new`)."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield is not None and db_field.name == POSITION:
            formfield.widget = HiddenInput(attrs={"class": POSITION_CLASS})
            formfield.required = False
        return formfield
