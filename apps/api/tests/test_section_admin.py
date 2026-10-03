"""Tests de la fiche technique dans l'écran Projet : des sections libres en tableau en ligne, sous
les technologies, que l'auteur ajoute, retire et ordonne avant d'enregistrer (D55, D57)."""

import html
import json
import re

import pytest
from config import strings
from content.inlines import HANDLE_CLASS
from content.models import Project, Section
from django.test import Client
from django.urls import reverse
from django.utils.text import capfirst
from factories import BLANK, saved, section, technology
from test_project_admin import LINES, line, new_project_data, rendered_data, saved_project

# Le préfixe des lignes de section dans le formulaire de l'écran Projet : le nom de la relation
# inverse (`BaseInlineFormSet.get_default_prefix`).
ROWS = "section_set"

# Chaque champ d'une ligne de section que l'auteur voit, et son libellé du catalogue.
SECTION_FIELD_LABELS = {
    "title": strings.SECTION_TITLE,
    "anchor": strings.SECTION_ANCHOR,
    "body": strings.SECTION_BODY,
}


def row(index: int, title: str, body: str, position: int, anchor: str = "") -> dict[str, object]:
    """Les champs de la ligne `index` des sections d'un projet ; l'ancre, à défaut, est un slug du
    titre — proche de celle que l'écran préremplit, qui garde le souligné et retire
    l'apostrophe."""
    slug = anchor or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return {
        f"{ROWS}-{index}-title": title,
        f"{ROWS}-{index}-anchor": slug,
        f"{ROWS}-{index}-body": body,
        f"{ROWS}-{index}-position": position,
    }


def stored(owner: Project) -> list[tuple[str, str, str]]:
    """Les sections enregistrées de `owner`, dans l'ordre stocké : ancre, titre, corps."""
    return list(Section.objects.filter(project=owner).values_list("anchor", "title", "body"))


@pytest.mark.django_db
def test_l_ecran_projet_montre_la_fiche_technique_sous_les_technologies(
    admin_client: Client,
) -> None:
    """Un tableau en ligne titré, ses champs libellés du catalogue, rendu après celui des
    technologies (brief, « Comportement souhaité »)."""
    response = admin_client.get(reverse("admin:content_project_add"))
    lines, sections = response.context["inline_admin_formsets"]
    page = response.content.decode()

    assert lines.formset.prefix == LINES
    assert sections.formset.prefix == ROWS
    assert sections.opts.verbose_name_plural == strings.SECTIONS_HEADING
    assert {
        name: sections.formset.form.base_fields[name].label for name in SECTION_FIELD_LABELS
    } == {name: capfirst(label) for name, label in SECTION_FIELD_LABELS.items()}
    assert page.index(f'id="{LINES}-group"') < page.index(f'id="{ROWS}-group"')


@pytest.mark.django_db
def test_les_sections_ont_la_poignee_de_tri_des_lignes(admin_client: Client) -> None:
    """Le tableau des sections est un tableau en ligne ordonnable : chaque ligne porte la poignée
    que `inline_rows.js` rend glissable (ADR 0013)."""
    page = admin_client.get(reverse("admin:content_project_add")).content.decode()
    group = page[page.index(f'id="{ROWS}-group"') :]

    assert HANDLE_CLASS in group


@pytest.mark.django_db
def test_l_ancre_d_une_ligne_neuve_se_remplit_depuis_le_titre_pas_celle_d_une_ligne_enregistree(
    admin_client: Client,
) -> None:
    """Le script de l'admin préremplit l'ancre d'une ligne neuve depuis son titre ; l'ancre d'une
    section enregistrée ne suit plus un titre retouché : le site et le RAG la citent (US 57)."""
    portfolio = saved_project(saved(technology(name="Django")))
    saved(section(portfolio))
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    page = admin_client.get(url).content.decode()
    declaration = re.search(r'data-prepopulated-fields="([^"]*)"', page)

    assert declaration is not None
    prepopulated = json.loads(html.unescape(declaration.group(1)))
    rows = [(field["id"], field["dependency_ids"]) for field in prepopulated if ROWS in field["id"]]
    assert rows == [
        (f"#id_{ROWS}-1-anchor", [f"#id_{ROWS}-1-title"]),
        (f"#id_{ROWS}-__prefix__-anchor", [f"#id_{ROWS}-__prefix__-title"]),
    ]


@pytest.mark.django_db
def test_l_admin_enregistre_les_sections_dans_l_ordre_affiche(admin_client: Client) -> None:
    django = saved(technology(name="Django"))
    data = new_project_data(
        admin_client,
        **line(0, django, 1),
        **row(0, "Bilan", "Ce que j'en retiens.", 2),
        **row(1, "Contexte", "Pourquoi ce projet.", 1),
        **{f"{ROWS}-TOTAL_FORMS": 2},
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert stored(Project.objects.get()) == [
        ("contexte", "Contexte", "Pourquoi ce projet."),
        ("bilan", "Bilan", "Ce que j'en retiens."),
    ]


@pytest.mark.django_db
def test_une_ligne_de_section_laissee_vide_n_enregistre_rien(admin_client: Client) -> None:
    """Le script numérote toute ligne affichée : une ligne neuve dont seule la position est
    remplie est ignorée (`InlineRowForm.has_changed`)."""
    django = saved(technology(name="Django"))
    data = new_project_data(admin_client, **line(0, django, 1), **{f"{ROWS}-0-position": 1})

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert stored(Project.objects.get()) == []


@pytest.mark.django_db
@pytest.mark.parametrize("body", ["", BLANK], ids=["texte vide", "texte fait d'espaces"])
def test_une_ligne_titree_sans_texte_est_refusee_avec_le_message_du_catalogue(
    admin_client: Client, body: str
) -> None:
    """Décision du mainteneur : pas de titre sans texte. Le champ refuse le vide, la contrainte
    les espaces ; même message du catalogue sous le champ ou en tête de la ligne."""
    django = saved(technology(name="Django"))
    data = new_project_data(admin_client, **line(0, django, 1), **row(0, "Stack", body, 1))

    response = admin_client.post(reverse("admin:content_project_add"), data)

    form = response.context["inline_admin_formsets"][1].formset.forms[0]
    assert response.status_code == 200
    assert [*form.errors.get("body", []), *form.non_field_errors()] == [
        strings.SECTION_BODY_MISSING
    ]
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_le_corps_d_une_section_garde_son_texte_tel_que_saisi(admin_client: Client) -> None:
    """En Markdown, une ligne de tête indentée de quatre espaces est un bloc de code : le texte
    s'enregistre sans être retaillé."""
    django = saved(technology(name="Django"))
    code = "    make dev\n"
    data = new_project_data(admin_client, **line(0, django, 1), **row(0, "Tests", code, 1))

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert stored(Project.objects.get()) == [("tests", "Tests", code)]


@pytest.mark.django_db
def test_deux_lignes_ne_portent_pas_la_meme_ancre(admin_client: Client) -> None:
    django = saved(technology(name="Django"))
    data = new_project_data(
        admin_client,
        **line(0, django, 1),
        **row(0, "Stack", "Django.", 1),
        **row(1, "Stack", "React.", 2),
        **{f"{ROWS}-TOTAL_FORMS": 2},
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    sections = response.context["inline_admin_formsets"][1].formset
    assert list(sections.non_form_errors()) == [strings.SECTION_ANCHOR_TAKEN]
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_l_auteur_retire_et_reordonne_les_sections_enregistrees(admin_client: Client) -> None:
    """On retire une ligne et on en déplace une autre, puis on enregistre une fois ; les sections
    d'un autre projet, aux mêmes ancres, ne bougent pas."""
    django = saved(technology(name="Django"))
    portfolio, other = saved_project(django), saved_project(django, slug="autre")
    for position, title in enumerate(("Contexte", "Stack", "Bilan"), start=1):
        saved(section(portfolio, title=title, anchor=title.lower(), position=position))
        saved(section(other, title=title, anchor=title.lower(), position=position))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        f"{ROWS}-0-DELETE": "on",
        f"{ROWS}-1-position": 2,
        f"{ROWS}-2-position": 1,
    }

    response = admin_client.post(url, data)

    assert response.status_code == 302
    assert [anchor for anchor, _, _ in stored(portfolio)] == ["bilan", "stack"]
    assert [anchor for anchor, _, _ in stored(other)] == ["contexte", "stack", "bilan"]


@pytest.mark.django_db
def test_deux_sections_enregistrees_echangent_leurs_ancres(admin_client: Client) -> None:
    """L'état final compte, pas l'ordre des écritures : Django enregistre les lignes l'une après
    l'autre, et la première reprend une ancre que la seconde libère — l'unicité est différée."""
    portfolio = saved_project(saved(technology(name="Django")))
    saved(section(portfolio, title="Contexte", anchor="contexte", position=1))
    saved(section(portfolio, title="Stack", anchor="stack", position=2))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        f"{ROWS}-0-anchor": "stack",
        f"{ROWS}-1-anchor": "contexte",
    }

    response = admin_client.post(url, data)

    assert response.status_code == 302
    assert [(anchor, title) for anchor, title, _ in stored(portfolio)] == [
        ("stack", "Contexte"),
        ("contexte", "Stack"),
    ]
