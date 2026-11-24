"""Tests de l'écran Projet de l'admin : ses champs, ses technologies en ligne — ordonnées par
glisser-déposer, supprimées par un seul bouton —, et les refus qu'il affiche."""

import html
import json
import re
from typing import Any

import pytest
from config import strings
from content.inlines import HANDLE_CLASS, POSITION_CLASS
from content.models import Project, ProjectTechnology, Technology
from django.contrib.admin.helpers import InlineAdminFormSet
from django.core.files import File
from django.forms import FileField
from django.templatetags.static import static
from django.test import Client
from django.urls import reverse
from django.utils.html import escape
from django.utils.text import capfirst
from django.utils.translation import gettext
from factories import BLANK, gallery_image, image_upload, project, saved, technology
from static_code import code

# Chaque champ de l'écran d'ajout d'un projet, dans l'ordre de l'écran, et son libellé du
# catalogue ; puis ceux d'une ligne de technologie.
PROJECT_FIELD_LABELS = {
    "title": strings.PROJECT_TITLE,
    "slug": strings.PROJECT_SLUG,
    "summary": strings.PROJECT_SUMMARY,
    "description": strings.PROJECT_DESCRIPTION,
    "kind": strings.PROJECT_KIND,
    "status": strings.PROJECT_STATUS,
    "started_on": strings.PROJECT_STARTED_ON,
    "finished_on": strings.PROJECT_FINISHED_ON,
    "client": strings.PROJECT_CLIENT,
    "repository_url": strings.PROJECT_REPOSITORY_URL,
    "demo_url": strings.PROJECT_DEMO_URL,
    "showcase": strings.PROJECT_SHOWCASE,
    "published": strings.PROJECT_PUBLISHED,
}
PROJECT_TECHNOLOGY_FIELD_LABELS = {
    "technology": strings.TECHNOLOGY,
    "position": strings.PROJECT_TECHNOLOGY_POSITION,
}

# Le préfixe des lignes de technologie, de celles de la galerie et de celles de la fiche technique,
# dans le formulaire de l'écran Projet : le nom de la relation inverse
# (`BaseInlineFormSet.get_default_prefix`).
LINES = "projecttechnology_set"
GALLERY = "gallery"
ROWS = "section_set"

# Le script et la feuille des lignes en ligne : tri par glisser-déposer, bouton unique de
# suppression (`content/inlines.py`).
INLINE_ROWS_SCRIPT = "content/admin/inline_rows.js"
INLINE_ROWS_STYLE = "content/admin/inline_rows.css"

# Les classes des raccourcis que Django pose à côté d'une liste d'objets liés pour modifier, voir ou
# supprimer l'objet choisi (`admin/widgets/related_widget_wrapper.html`).
RELATED_LINKS = ["change-related", "view-related", "delete-related"]


def inline_group(response: Any, prefix: str) -> InlineAdminFormSet:
    """Le tableau en ligne `prefix` de l'écran que `response`, réponse du client de test, rend."""
    groups: list[InlineAdminFormSet] = response.context["inline_admin_formsets"]
    return next(group for group in groups if group.formset.prefix == prefix)


def group(page: str, prefix: str) -> str:
    """Le tableau en ligne `prefix` dans `page`, l'écran Projet rendu, jusqu'au tableau suivant."""
    start = page.index(f'id="{prefix}-group"')
    end = page.find("js-inline-admin-formset", start)
    return page[start : end if end != -1 else None]


def rendered_data(admin_client: Client, url: str) -> dict[str, object]:
    """Le formulaire que l'écran `url` rend, tel qu'un navigateur le renverrait sans rien toucher :
    champs du projet, formulaire de gestion et lignes de chaque tableau en ligne, cases cochées
    comprises. Un fichier déjà enregistré ne se renvoie pas : le navigateur n'envoie que celui que
    l'auteur choisit."""
    response = admin_client.get(url)
    forms = [response.context["adminform"].form]
    data: dict[str, object] = {}
    for inline in response.context["inline_admin_formsets"]:
        management = inline.formset.management_form
        data |= {management.add_prefix(name): value for name, value in management.initial.items()}
        forms += inline.formset.forms
    for form in forms:
        for name, field in form.fields.items():
            value = form[name].value()
            if isinstance(field, FileField):
                continue
            if value is True:
                data[form.add_prefix(name)] = "on"
            elif value not in (None, False, ""):
                data[form.add_prefix(name)] = value
    return data


def image_row(prefix: str, index: int = 0, /, **fields: object) -> dict[str, object]:
    """La ligne `index` du tableau d'images `prefix` remplie : une image valide et sa légende ;
    `fields` en remplace ou en ajoute, sous leur nom de modèle (`original`, `caption`,
    `position`). Un fichier est rembobiné : le client de test l'envoie depuis là où il en est, et
    une même table de cas sert à plusieurs tests."""
    row = {"original": image_upload(), "caption": "La table des projets.", **fields}
    for value in row.values():
        if isinstance(value, File):
            value.seek(0)
    return {f"{prefix}-{index}-{name}": value for name, value in row.items()}


def new_project_data(admin_client: Client, **fields: object) -> dict[str, object]:
    """Le formulaire d'ajout d'un projet, rempli avec le projet de la fabrique et sa première
    image, la couverture ; `fields` en remplace des champs ou remplit des lignes
    (`f"{LINES}-0-technology"`…)."""
    source = project()
    data = rendered_data(admin_client, reverse("admin:content_project_add")) | image_row(GALLERY)
    data |= {
        name: value
        for name in PROJECT_FIELD_LABELS
        if (value := getattr(source, name)) not in (None, False, "")
    }
    return data | fields


def line(index: int, linked: Technology, position: int) -> dict[str, object]:
    """Les champs de la ligne `index` des technologies d'un projet."""
    return {f"{LINES}-{index}-technology": linked.pk, f"{LINES}-{index}-position": position}


def saved_project(linked: Technology, **fields: object) -> Project:
    """Un projet de la fabrique, enregistré avec sa première image, la couverture, et `linked`
    pour seule technologie."""
    linking = saved(project(**fields))
    saved(gallery_image(linking))
    saved(ProjectTechnology(project=linking, technology=linked, position=1))
    return linking


def refused_rows(
    admin_client: Client, url: str, data: dict[str, object], prefix: str = LINES
) -> list[str]:
    """Envoie `data` à l'écran Projet `url` et rend les refus qu'il affiche au-dessus du tableau en
    ligne `prefix`, les technologies par défaut."""
    response = admin_client.post(url, data)
    return list(inline_group(response, prefix).formset.non_form_errors())


@pytest.mark.django_db
def test_l_ecran_projet_affiche_les_libelles_du_catalogue(admin_client: Client) -> None:
    """Toute chaîne du projet que l'écran montre vient du catalogue (décision 1) : champs dans
    l'ordre de l'écran, valeurs du type et du statut, titre, lignes de technologie. Les lignes de
    la fiche technique ont leurs propres tests (`test_section_admin.py`)."""
    response = admin_client.get(reverse("admin:content_project_add"))
    form = response.context["adminform"].form
    lines = inline_group(response, LINES)
    page = response.content.decode()

    assert [(name, field.label) for name, field in form.fields.items()] == [
        (name, capfirst(label)) for name, label in PROJECT_FIELD_LABELS.items()
    ]
    assert [label for value, label in form.fields["kind"].choices if value] == [
        strings.PROJECT_KIND_PERSONAL,
        strings.PROJECT_KIND_PROFESSIONAL,
        strings.PROJECT_KIND_SCHOOL,
    ]
    assert [label for value, label in form.fields["status"].choices if value] == [
        strings.PROJECT_STATUS_ONGOING,
        strings.PROJECT_STATUS_FINISHED,
        strings.PROJECT_STATUS_ARCHIVED,
    ]
    assert {
        name: lines.formset.form.base_fields[name].label for name in PROJECT_TECHNOLOGY_FIELD_LABELS
    } == {name: capfirst(label) for name, label in PROJECT_TECHNOLOGY_FIELD_LABELS.items()}
    assert f"<h1>{escape(gettext('Add %s') % strings.PROJECT)}</h1>" in page
    assert escape(capfirst(strings.PROJECT_TECHNOLOGIES)) in page
    assert f'<th class="column-move">{escape(capfirst(strings.ADMIN_ROW_ORDER))}' in page


@pytest.mark.django_db
def test_l_ecran_projet_range_technologies_galerie_puis_fiche_technique(
    admin_client: Client,
) -> None:
    """L'ordre des tableaux en ligne du PRD, « Back-office » (brief de #9, décision 11)."""
    page = admin_client.get(reverse("admin:content_project_add")).content.decode()

    positions = [page.find(f'id="{prefix}-group"') for prefix in (LINES, GALLERY, ROWS)]

    assert -1 not in positions
    assert positions == sorted(positions)


@pytest.mark.django_db
def test_l_ecran_projet_preremplit_le_slug_depuis_le_titre(admin_client: Client) -> None:
    """Le slug se remplit depuis le titre à la saisie (décision 3), par le script de l'admin, qui
    lit cette déclaration dans la page. Les champs du projet n'ont pas de préfixe dans leur
    identifiant ; ceux des lignes en ont un (l'ancre d'une section, `test_section_admin.py`)."""
    page = admin_client.get(reverse("admin:content_project_add")).content.decode()
    declaration = re.search(r'data-prepopulated-fields="([^"]*)"', page)

    assert declaration is not None
    prepopulated = json.loads(html.unescape(declaration.group(1)))
    assert [
        (field["name"], field["dependency_list"])
        for field in prepopulated
        if "-" not in field["id"]
    ] == [("slug", ["title"])]


@pytest.mark.django_db
def test_la_description_d_un_projet_garde_son_texte_tel_que_saisi(admin_client: Client) -> None:
    """En Markdown, une ligne de tête indentée de quatre espaces est un bloc de code : la
    description s'enregistre sans être retaillée, comme le corps d'une section."""
    code = "    make dev\n"
    data = new_project_data(
        admin_client, description=code, **line(0, saved(technology(name="Django")), 1)
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert Project.objects.get().description == code


@pytest.mark.django_db
def test_un_projet_ajoute_dans_l_admin_se_range_en_dernier(admin_client: Client) -> None:
    """Spec §1.9 : la position ne se saisit pas sur l'écran, et un projet neuf arrive après tous
    les projets, brouillon compris — ici le dernier."""
    django = saved(technology(name="Django"))
    for position in (1, 2, 5):
        saved_project(django, slug=f"projet-{position}", position=position, published=position != 5)

    response = admin_client.post(
        reverse("admin:content_project_add"), new_project_data(admin_client, **line(0, django, 1))
    )

    assert response.status_code == 302
    assert Project.objects.get(slug=project().slug).position == 6


@pytest.mark.django_db
def test_l_admin_refuse_une_description_faite_d_espaces(admin_client: Client) -> None:
    """Gardée telle que saisie, une description d'espaces n'est plus retaillée en description vide :
    l'admin la refuse avec le message du catalogue, sans rien enregistrer."""
    data = new_project_data(
        admin_client, description=BLANK, **line(0, saved(technology(name="Django")), 1)
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 200
    assert strings.PROJECT_DESCRIPTION_MISSING in response.context["adminform"].form.errors.get(
        "__all__", []
    )
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_l_admin_enregistre_un_projet_et_reaffiche_ses_technologies_dans_l_ordre(
    admin_client: Client,
) -> None:
    """Un projet complet en un seul écran, technologies en ligne (critère de #7) ; la liste se
    réaffiche triée par position après l'enregistrement : l'ordre de l'admin est l'ordre stocké
    (décision 2)."""
    django, python = saved(technology(name="Django")), saved(technology(name="Python"))

    response = admin_client.post(
        reverse("admin:content_project_add"),
        new_project_data(admin_client, **line(0, django, 2), **line(1, python, 1)),
    )

    assert response.status_code == 302
    created = Project.objects.get()
    response = admin_client.get(reverse("admin:content_project_change", args=[created.pk]))
    shown = [
        form.instance.technology for form in inline_group(response, LINES).formset.initial_forms
    ]
    assert shown == [python, django]


@pytest.mark.django_db
def test_l_admin_reordonne_les_technologies_enregistrees(admin_client: Client) -> None:
    """Le geste principal (ADR 0013) : déplacer une ligne enregistrée. Le script renumérote les
    positions cachées dans l'ordre affiché ; l'enregistrement les stocke telles quelles."""
    django, python = saved(technology(name="Django")), saved(technology(name="Python"))
    portfolio = saved_project(django)
    saved(ProjectTechnology(project=portfolio, technology=python, position=2))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {f"{LINES}-0-position": 2, f"{LINES}-1-position": 1}

    response = admin_client.post(url, data)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [link.technology for link in stored] == [python, django]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lines",
    [
        {},
        {f"{LINES}-{index}-position": index + 1 for index in range(4)},
        {f"{LINES}-TOTAL_FORMS": 0},
    ],
    ids=["lignes laissées vides", "lignes vides numérotées par le script", "aucune ligne envoyée"],
)
def test_l_admin_refuse_un_projet_sans_technologie(
    admin_client: Client, lines: dict[str, object]
) -> None:
    """Seule règle hors base (décision 10) : l'écran la tient, avec le message du catalogue — même
    quand le script a numéroté les lignes vides, ou que le formulaire n'envoie aucune ligne."""
    url = reverse("admin:content_project_add")

    refusals = refused_rows(admin_client, url, new_project_data(admin_client, **lines))

    assert refusals == [strings.PROJECT_TECHNOLOGIES_MISSING]
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_l_admin_refuse_de_retirer_la_derniere_technologie_d_un_projet(
    admin_client: Client,
) -> None:
    django = saved(technology(name="Django"))
    portfolio = saved_project(django)
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    data = rendered_data(admin_client, url) | {f"{LINES}-0-DELETE": "on"}

    assert refused_rows(admin_client, url, data) == [strings.PROJECT_TECHNOLOGIES_MISSING]
    assert ProjectTechnology.objects.filter(project=portfolio).exists()


@pytest.mark.django_db
def test_l_admin_accepte_une_technologie_retiree_puis_rajoutee_avant_l_enregistrement(
    admin_client: Client,
) -> None:
    """On manipule les lignes, puis on enregistre une fois : une technologie retirée puis
    rajoutée dans le même envoi n'est pas un doublon. La ligne retirée existe encore en base
    jusqu'à l'enregistrement ; l'unicité se juge entre les lignes gardées, pas contre elle."""
    django, python = saved(technology(name="Django")), saved(technology(name="Python"))
    portfolio = saved_project(django)
    saved(ProjectTechnology(project=portfolio, technology=python, position=2))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        f"{LINES}-0-DELETE": "on",
        f"{LINES}-1-DELETE": "on",
        **line(2, python, 1),
        **line(3, django, 2),
    }

    response = admin_client.post(url, data)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [link.technology for link in stored] == [python, django]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "swapped",
    [True, False],
    ids=["deux lignes échangent leurs technologies", "une ligne reprend celle d'une ligne retirée"],
)
def test_l_admin_accepte_une_technologie_passee_d_une_ligne_enregistree_a_une_autre(
    admin_client: Client, swapped: bool
) -> None:
    """L'état final compte, pas l'ordre des écritures : Django modifie et supprime les lignes
    enregistrées l'une après l'autre, dans l'ordre du formulaire
    (`BaseModelFormSet.save_existing_objects`), et la première écriture reprend une technologie que
    la seconde libère."""
    django, python = saved(technology(name="Django")), saved(technology(name="Python"))
    portfolio = saved_project(django)
    saved(ProjectTechnology(project=portfolio, technology=python, position=2))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {f"{LINES}-0-technology": python.pk}
    data |= {f"{LINES}-1-technology": django.pk} if swapped else {f"{LINES}-1-DELETE": "on"}

    response = admin_client.post(url, data)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [link.technology for link in stored] == ([python, django] if swapped else [python])


@pytest.mark.django_db
def test_l_admin_refuse_une_technologie_gardee_rajoutee_une_seconde_fois(
    admin_client: Client,
) -> None:
    """Le formset compare chaque ligne neuve aux lignes enregistrées qu'il garde : c'est lui, et
    non plus un contrôle ligne par ligne contre la base, qui refuse le doublon."""
    django = saved(technology(name="Django"))
    portfolio = saved_project(django)
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | line(1, django, 2)

    assert refused_rows(admin_client, url, data) == [strings.PROJECT_TECHNOLOGY_TAKEN]
    assert ProjectTechnology.objects.filter(project=portfolio).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "resent",
    [False, True],
    ids=["ligne enregistrée depuis un autre onglet", "même envoi renvoyé"],
)
def test_l_admin_refuse_une_technologie_enregistree_depuis_l_ouverture_de_l_ecran(
    admin_client: Client, resent: bool
) -> None:
    """Une ligne enregistrée ailleurs depuis l'ouverture de l'écran — un second onglet, un envoi
    renvoyé — n'est dans aucune ligne de l'envoi : le formulaire la compare quand même aux lignes
    gardées, et refuse le doublon au lieu de le laisser à la base. La ligne en double est marquée,
    comme Django marque un doublon entre les lignes de l'envoi."""
    django, python = saved(technology(name="Django")), saved(technology(name="Python"))
    portfolio = saved_project(django)
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | line(1, python, 2)
    if resent:
        assert admin_client.post(url, data).status_code == 302
    else:
        saved(ProjectTechnology(project=portfolio, technology=python, position=2))

    lines = inline_group(admin_client.post(url, data), LINES).formset

    assert list(lines.non_form_errors()) == [strings.PROJECT_TECHNOLOGY_TAKEN]
    assert [list(form.non_field_errors()) for form in lines.forms[:2]] == [
        [],
        [lines.get_form_error()],
    ]
    assert ProjectTechnology.objects.filter(project=portfolio).count() == 2


@pytest.mark.django_db
def test_une_ligne_supprimee_ailleurs_depuis_l_ouverture_de_l_ecran_ne_bloque_pas_l_envoi(
    admin_client: Client,
) -> None:
    """Un second onglet supprime une ligne après l'ouverture de l'écran : l'envoi la porte encore.
    Django la saute à l'enregistrement (`BaseModelFormSet.save_existing_objects`), mais sa clé,
    introuvable, refusait l'envoi sans message visible, en boucle : elle compte comme supprimée,
    et le reste de l'envoi s'enregistre."""
    django, react, vue = (saved(technology(name=name)) for name in ("Django", "React", "Vue"))
    portfolio = saved_project(django)
    gone = saved(ProjectTechnology(project=portfolio, technology=react, position=2))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | line(2, vue, 3)
    gone.delete()

    response = admin_client.post(url, data)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [link.technology for link in stored] == [django, vue]


@pytest.mark.django_db
def test_une_ligne_supprimee_ne_doublonne_pas_une_ligne_enregistree_depuis_l_ouverture(
    admin_client: Client,
) -> None:
    """Une ligne que l'envoi supprime ne compte pas, même changée avant sa suppression : elle ne
    doublonne pas une ligne enregistrée ailleurs depuis l'ouverture de l'écran."""
    django, python, react = (saved(technology(name=name)) for name in ("Django", "Python", "React"))
    portfolio = saved_project(django)
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | line(1, react, 1)
    data |= {f"{LINES}-0-technology": python.pk, f"{LINES}-0-DELETE": "on"}
    saved(ProjectTechnology(project=portfolio, technology=python, position=2))

    response = admin_client.post(url, data)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [link.technology for link in stored] == [react, python]


@pytest.mark.django_db
def test_l_admin_refuse_deux_fois_la_meme_technologie_dans_un_projet(
    admin_client: Client,
) -> None:
    """Le formulaire compare ses lignes entre elles avant la base : message du catalogue, là où
    Django nommerait le champ par son identifiant anglais."""
    django = saved(technology(name="Django"))
    data = new_project_data(admin_client, **line(0, django, 1), **line(1, django, 2))

    refusals = refused_rows(admin_client, reverse("admin:content_project_add"), data)

    assert refusals == [strings.PROJECT_TECHNOLOGY_TAKEN]
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_l_admin_refuse_une_seconde_vitrine(admin_client: Client) -> None:
    """La contrainte en base suffit : le formulaire affiche son message (PRD, « Décisions de test »
    : refus du second vitrine à travers le formulaire)."""
    django = saved(technology(name="Django"))
    saved_project(django, showcase=True)

    response = admin_client.post(
        reverse("admin:content_project_add"),
        new_project_data(admin_client, slug="autre", showcase="on", **line(0, django, 1)),
    )

    assert response.context["adminform"].form.non_field_errors() == [strings.PROJECT_SHOWCASE_TAKEN]
    assert Project.objects.count() == 1


@pytest.mark.django_db
def test_le_slug_d_un_projet_publie_se_modifie_a_l_ecran(admin_client: Client) -> None:
    """Décision 3 : toujours modifiable, projet publié ou non. Les anciens liens mènent alors à
    l'accueil (ADR 0009)."""
    portfolio = saved_project(saved(technology(name="Django")), published=True)
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    response = admin_client.post(url, rendered_data(admin_client, url) | {"slug": "nouveau"})

    assert response.status_code == 302
    portfolio.refresh_from_db()
    assert portfolio.slug == "nouveau"


@pytest.mark.django_db
def test_chaque_ligne_de_technologie_porte_une_poignee_de_tri(admin_client: Client) -> None:
    """Décision 2 amendée (ADR 0013) : l'auteur fait glisser une ligne, enregistrée ou neuve, par
    sa poignée — ou la déplace au clavier. La position ne se saisit plus : elle voyage dans un champ
    caché que le script remplit à l'enregistrement, dans l'ordre affiché. Le glisser lui-même se
    regarde à l'écran (arrêt visuel) ; ce test tient ce que le serveur en livre."""
    portfolio = saved_project(saved(technology(name="Django")))

    response = admin_client.get(reverse("admin:content_project_change", args=[portfolio.pk]))
    page = response.content.decode()
    lines = inline_group(response, LINES).formset

    # `type="button"` : sans lui, un bouton de formulaire l'envoie (`submit` par défaut, HTML).
    handle = (
        f'<button type="button" class="sortable-handle" '
        f'aria-label="{escape(strings.ADMIN_ROW_MOVE)}"'
    )
    # Une poignée par ligne, enregistrée ou neuve, plus celle du modèle de ligne que l'admin clone ;
    # dans le tableau des technologies seul : la galerie et les sections ont leurs propres poignées.
    assert group(page, LINES).count(handle) == len(lines.forms) + 1
    positions = re.findall(rf'<input type="hidden" name="{LINES}-\d+-position"[^>]*>', page)
    assert len(positions) == len(lines.forms)
    assert all('class="sortable-position"' in position for position in positions)
    for asset in (INLINE_ROWS_SCRIPT, INLINE_ROWS_STYLE):
        assert static(asset) in page


@pytest.mark.django_db
def test_une_ligne_de_technologie_ne_modifie_ni_ne_supprime_la_technologie(
    admin_client: Client,
) -> None:
    """L'écran Projet choisit des technologies, il ne les édite pas : des raccourcis que Django pose
    à côté de la liste, seul reste l'ajout d'une technologie manquante. Les autres ouvraient la
    technologie elle-même — la supprimer la retirait de tout le site."""
    portfolio = saved_project(saved(technology(name="Django")))

    page = admin_client.get(
        reverse("admin:content_project_change", args=[portfolio.pk])
    ).content.decode()

    assert "add-related" in page
    assert [link for link in RELATED_LINKS if link in page] == []


@pytest.mark.django_db
def test_l_ecran_projet_charge_le_bouton_unique_de_suppression_des_lignes(
    admin_client: Client,
) -> None:
    """Django supprime une ligne neuve par un bouton, une ligne enregistrée par une case à cocher ;
    le script de l'écran donne à toutes le même bouton. Son effet se regarde à l'écran (arrêt
    visuel) ; ce test tient ce que le serveur en livre : la case, que le script cache, et le script.
    """
    portfolio = saved_project(saved(technology(name="Django")))

    page = admin_client.get(
        reverse("admin:content_project_change", args=[portfolio.pk])
    ).content.decode()

    assert f'name="{LINES}-0-DELETE"' in page
    assert static(INLINE_ROWS_SCRIPT) in page


@pytest.mark.django_db
def test_l_ecran_projet_livre_au_script_les_prises_qu_il_lit(admin_client: Client) -> None:
    """`inline_rows.js` n'a pas de test de navigateur (ADR 0013) : ce test en tient la part
    serveur. Le script lit les classes que `content/inlines.py` pose, et ce que rend le gabarit de
    Django (`admin/edit_inline/tabular.html`), qu'une montée de version peut déplacer : les options
    du tableau — préfixe, libellé du bouton de suppression —, son bloc, sa ligne modèle, les lignes
    enregistrées, la rangée des refus d'une ligne, et la case de suppression, qui revient cochée
    quand l'écran revient en erreur."""
    django = saved(technology(name="Django"))
    portfolio = saved_project(django)
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    script = code(INLINE_ROWS_SCRIPT)
    refused = rendered_data(admin_client, url) | {
        "title": "",
        f"{LINES}-0-DELETE": "on",
        **line(1, django, 1),
        **line(2, django, 2),
    }

    page = admin_client.post(url, refused).content.decode()

    for hook in (
        f".{HANDLE_CLASS}",
        f"input.{POSITION_CLASS}",
        "tr.form-row",
        "tr.empty-form",
        "has_original",
        "row-form-errors",
        ".inline-group",
        "td.delete input[type=checkbox]",
        ".js-inline-admin-formset",
        "dataset.inlineFormset",
        "deleteText",
    ):
        assert hook in script
    declarations = re.findall(
        r'class="js-inline-admin-formset[^>]*data-inline-formset="([^"]*)"', page
    )
    options = [json.loads(html.unescape(declaration))["options"] for declaration in declarations]
    assert (LINES, gettext("Remove")) in [
        (option["prefix"], option["deleteText"]) for option in options
    ]
    assert 'class="js-inline-admin-formset inline-group"' in page
    assert '<tr class="form-row has_original"' in page
    assert re.search(rf'<tr class="form-row\s+empty-form"\s+id="{LINES}-empty"', page)
    assert '<tr class="row-form-errors">' in page
    deleted = rf'<td class="delete"><input type="checkbox" name="{LINES}-0-DELETE"[^>]*checked'
    assert re.search(deleted, page)


@pytest.mark.django_db
def test_une_ligne_neuve_dont_seule_la_position_est_remplie_est_ignoree(
    admin_client: Client,
) -> None:
    """Le script numérote toute ligne affichée, y compris une ligne neuve laissée vide ou vidée
    après un refus : sa position seule ne la change pas, et l'écran l'ignore comme Django ignore
    une ligne vide, au lieu de la refuser."""
    django = saved(technology(name="Django"))
    portfolio = saved_project(django)
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    response = admin_client.post(url, rendered_data(admin_client, url) | {f"{LINES}-1-position": 2})

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [link.technology for link in stored] == [django]


@pytest.mark.django_db
def test_une_ligne_vide_affichee_en_tete_de_l_ecran_d_ajout_est_ignoree(
    admin_client: Client,
) -> None:
    """Django exige les `min_num` premières lignes neuves, quelle que soit celle que l'auteur a
    remplie : une ligne vide glissée en tête serait refusée. « Au moins une technologie » se compte
    sur les lignes remplies (`validate_min`), et toute ligne neuve vide est ignorée."""
    django = saved(technology(name="Django"))
    data = new_project_data(admin_client, **{f"{LINES}-0-position": 1}, **line(1, django, 2))

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert [link.technology for link in ProjectTechnology.objects.all()] == [django]


@pytest.mark.django_db
def test_une_ligne_enregistree_arrivee_sans_position_garde_la_sienne(admin_client: Client) -> None:
    """La position est facultative dans le formulaire : un envoi qui la vide pour une ligne
    enregistrée — ni l'écran ni le script n'en produisent — garde la position stockée au lieu
    d'échouer en base. La seconde n'est pas celle qu'une renumérotation lui donnerait : garder et
    renuméroter se distinguent."""
    django, python = saved(technology(name="Django")), saved(technology(name="Python"))
    portfolio = saved_project(django)
    saved(ProjectTechnology(project=portfolio, technology=python, position=5))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    blanked = {f"{LINES}-0-position": "", f"{LINES}-1-position": ""}

    response = admin_client.post(url, rendered_data(admin_client, url) | blanked)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [(link.technology, link.position) for link in stored] == [(django, 1), (python, 5)]


@pytest.mark.django_db
def test_une_ligne_ajoutee_sans_position_se_range_apres_les_autres(admin_client: Client) -> None:
    """Sans le script — désactivé, ou en échec —, une ligne neuve arrive sans position :
    l'enregistrement la range après les autres, dans l'ordre du formulaire, au lieu de refuser un
    champ que l'auteur ne voit pas."""
    django, python, react = (saved(technology(name=name)) for name in ("Django", "Python", "React"))
    portfolio = saved_project(django)
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    new_lines = {
        f"{LINES}-1-technology": python.pk,
        f"{LINES}-1-position": "",
        f"{LINES}-2-technology": react.pk,
        f"{LINES}-2-position": "",
    }

    response = admin_client.post(url, rendered_data(admin_client, url) | new_lines)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [(link.technology, link.position) for link in stored] == [
        (django, 1),
        (python, 2),
        (react, 3),
    ]
