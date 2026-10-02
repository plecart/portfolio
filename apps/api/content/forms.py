"""Formulaires de l'admin du contenu."""

from typing import Any

from django import forms
from django.contrib.admin.widgets import AdminTextareaWidget

from content.models import Project, Section, SectionKey


class SectionField(forms.CharField):
    """Le bloc d'une section dans l'écran Projet : une zone de texte, titrée de la section,
    facultative.

    Le texte est gardé tel que saisi (`strip=False`) : en Markdown, une ligne de tête indentée est
    un bloc de code, et un texte retaillé paraîtrait changé à chaque enregistrement. Un bloc fait
    d'espaces n'en est pas moins vide (décision 7 du brief de #8, `ProjectForm.save_sections`).
    """

    def __init__(self, key: SectionKey) -> None:
        super().__init__(label=key.label, required=False, strip=False, widget=AdminTextareaWidget)
        self.key = key


class ProjectForm(forms.ModelForm[Project]):
    """Le formulaire de l'écran Projet : les champs du projet, puis un bloc par section de la
    fiche technique, dans l'ordre de la fiche — ni ajout, ni suppression, ni douzième bloc.

    Des champs du formulaire, et non un tableau en ligne (décision 6) : le script des tableaux en
    ligne (`content/inlines.py`) agit sur tout tableau de l'écran, et onze lignes préremplies
    demanderaient une clé cachée à valider. Un bloc rempli enregistre sa section, un bloc vide
    n'enregistre rien, un bloc vidé la supprime (`save_sections`). Le modèle reçoit son `Meta` de
    l'admin (`ModelAdmin.get_form`).

    Les blocs sont déclarés un à un : Django ne lit que les champs écrits dans le corps de la
    classe. `test_section_admin.py` exige un bloc par clé, dans l'ordre de l'énumération.
    """

    section_context = SectionField(SectionKey.CONTEXT)
    section_stack = SectionField(SectionKey.STACK)
    section_architecture = SectionField(SectionKey.ARCHITECTURE)
    section_data = SectionField(SectionKey.DATA)
    section_security = SectionField(SectionKey.SECURITY)
    section_async = SectionField(SectionKey.ASYNC)
    section_api = SectionField(SectionKey.API)
    section_deployment = SectionField(SectionKey.DEPLOYMENT)
    section_tests = SectionField(SectionKey.TESTS)
    section_decisions = SectionField(SectionKey.DECISIONS)
    section_retrospective = SectionField(SectionKey.RETROSPECTIVE)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Remplit le bloc de chaque section enregistrée du projet."""
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            return
        blocks = {key: name for name, key in self.section_fields().items()}
        for section in Section.objects.filter(project=self.instance):
            self.initial[blocks[SectionKey(section.key)]] = section.body

    @classmethod
    def section_fields(cls) -> dict[str, SectionKey]:
        """Le nom de chaque bloc et la clé de sa section, dans l'ordre de la fiche."""
        return {
            name: field.key
            for name, field in cls.base_fields.items()
            if isinstance(field, SectionField)
        }

    def save_sections(self) -> None:
        """Enregistre les blocs que l'auteur a changés, le projet déjà enregistré : un bloc rempli
        crée ou remplace sa section, un bloc vidé — ou réduit à des espaces — la supprime.

        Une écriture par bloc changé, et non `bulk_create` : les signaux d'enregistrement et de
        suppression d'une section restent émis — la purge du cache de #11 s'y branchera.
        `str.strip()` tient pour espace tout blanc Unicode, l'espace insécable comprise : il est
        plus strict que la contrainte de la base, qu'aucun bloc ne peut donc enfreindre.
        """
        for name, key in self.section_fields().items():
            if name not in self.changed_data:
                continue
            body: str = self.cleaned_data[name]
            if body.strip():
                Section.objects.update_or_create(
                    project=self.instance, key=key, defaults={"body": body}
                )
            else:
                Section.objects.filter(project=self.instance, key=key).delete()
