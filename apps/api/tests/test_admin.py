"""Tests de l'admin Django : monté à `/admin/`, en français, fermé aux anonymes, et ses écrans."""

import html
import json
import re

import pytest
from config import strings
from content.models import Project, ProjectTechnology, Technology, TechnologyKind
from django.test import Client
from django.urls import reverse
from django.utils.html import escape
from django.utils.text import capfirst
from django.utils.translation import gettext
from factories import project, saved, svg_icon, technology

# Chaque champ de l'écran d'ajout d'une technologie, et son libellé du catalogue.
TECHNOLOGY_FIELD_LABELS = {
    "name": strings.TECHNOLOGY_NAME,
    "kind": strings.TECHNOLOGY_KIND,
    "icon": strings.TECHNOLOGY_ICON,
    "website": strings.TECHNOLOGY_WEBSITE,
}

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

# Le préfixe des lignes de technologie dans le formulaire de l'écran Projet : le nom de la relation
# inverse (`BaseInlineFormSet.get_default_prefix`).
LINES = "projecttechnology_set"


def rendered_data(admin_client: Client, url: str) -> dict[str, object]:
    """Le formulaire que l'écran `url` rend, tel qu'un navigateur le renverrait sans rien toucher :
    champs du projet, formulaire de gestion et lignes de technologie, cases cochées comprises."""
    response = admin_client.get(url)
    forms = [response.context["adminform"].form]
    data: dict[str, object] = {}
    for inline in response.context["inline_admin_formsets"]:
        management = inline.formset.management_form
        data |= {management.add_prefix(name): value for name, value in management.initial.items()}
        forms += inline.formset.forms
    for form in forms:
        for name in form.fields:
            value = form[name].value()
            if value is True:
                data[form.add_prefix(name)] = "on"
            elif value not in (None, False, ""):
                data[form.add_prefix(name)] = value
    return data


def new_project_data(admin_client: Client, **fields: object) -> dict[str, object]:
    """Le formulaire d'ajout d'un projet, rempli avec le projet de la fabrique ; `fields` en
    remplace des champs ou remplit des lignes (`f"{LINES}-0-technology"`…)."""
    source = project()
    data = rendered_data(admin_client, reverse("admin:content_project_add"))
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
    """Un projet de la fabrique, enregistré avec `linked` pour seule technologie."""
    linking = saved(project(**fields))
    saved(ProjectTechnology(project=linking, technology=linked, position=1))
    return linking


def refused_lines(admin_client: Client, url: str, data: dict[str, object]) -> list[str]:
    """Envoie `data` à l'écran Projet `url` et rend les refus qu'il affiche au-dessus des lignes de
    technologie."""
    response = admin_client.post(url, data)
    return list(response.context["inline_admin_formsets"][0].formset.non_form_errors())


def test_l_admin_renvoie_un_visiteur_anonyme_vers_la_connexion(client: Client) -> None:
    response = client.get("/admin/")

    assert response.status_code == 302
    assert response["Location"] == "/admin/login/?next=/admin/"


def test_l_admin_parle_francais(client: Client) -> None:
    """Contenu en français seulement (cadrage §3) : les écrans de Django aussi."""
    page = client.get("/admin/login/").content.decode()

    assert '<html lang="fr"' in page
    assert "Connexion" in page


@pytest.mark.django_db
def test_l_ecran_technologie_affiche_les_libelles_du_catalogue(admin_client: Client) -> None:
    """Toute chaîne du projet que l'écran montre vient du catalogue (décision 1).

    Les libellés se lisent dans le formulaire que l'admin rend, pas par une recherche dans la
    page : l'admin affiche lui-même « Nom du modèle », et un « Nom » perdu y passerait inaperçu.
    """
    response = admin_client.get(reverse("admin:content_technology_add"))
    form = response.context["adminform"].form
    page = response.content.decode()

    labels = {name: capfirst(label) for name, label in TECHNOLOGY_FIELD_LABELS.items()}
    assert {name: field.label for name, field in form.fields.items()} == labels
    assert [label for value, label in form.fields["kind"].choices if value] == [
        strings.TECHNOLOGY_KIND_LANGUAGE,
        strings.TECHNOLOGY_KIND_FRAMEWORK,
        strings.TECHNOLOGY_KIND_INFRASTRUCTURE,
        strings.TECHNOLOGY_KIND_TOOL,
    ]
    for link in (strings.CONTENT, strings.TECHNOLOGIES):
        assert f">{escape(capfirst(link))}</a>" in page
    # Le nom du modèle ne s'affiche que dans le titre de l'écran — `<title>`, `<h1>`, fil
    # d'Ariane, tous lus sur `verbose_name` : le `<h1>` suffit. « Add %s » de l'admin, traduit
    # (`django/contrib/admin/options.py`).
    assert f"<h1>{escape(gettext('Add %s') % strings.TECHNOLOGY)}</h1>" in page


@pytest.mark.django_db
def test_la_liste_des_technologies_montre_l_icone_et_le_lien_du_site(
    admin_client: Client,
) -> None:
    """Colonnes dans l'ordre nom, type, icône, site. L'icône en petit ; le site en symbole de lien,
    cliquable s'il est renseigné — bleu, couleur des liens de l'admin —, grisé et inerte sinon.
    En-têtes et libellés accessibles du catalogue (décision 1)."""
    with_website = saved(technology(name="Django", website="https://www.djangoproject.com/"))
    without_website = saved(technology(name="Python"))

    page = admin_client.get(reverse("admin:content_technology_changelist")).content.decode()

    # Les colonnes sont les champs de l'écran d'ajout, dans le même ordre.
    columns = TECHNOLOGY_FIELD_LABELS.values()
    positions = [page.find(f">{escape(capfirst(column))}</") for column in columns]
    assert -1 not in positions
    assert positions == sorted(positions)
    for listed in (with_website, without_website):
        assert f'<img src="{listed.icon.url}"' in page
    link = (
        f'<a href="{with_website.website}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="{escape(strings.TECHNOLOGY_WEBSITE_OPEN.format(name=with_website.name))}"'
    )
    greyed = (
        f'<span class="quiet" role="img" aria-label="{escape(strings.TECHNOLOGY_WEBSITE_NONE)}"'
    )
    assert (page.count(link), page.count(greyed)) == (1, 1)


@pytest.mark.django_db
def test_l_admin_refuse_un_doublon_avec_le_message_du_catalogue(admin_client: Client) -> None:
    """La contrainte suffit : l'admin affiche son message sans second `clean()` (décision 10)."""
    technology(name="Django").save()

    response = admin_client.post(
        reverse("admin:content_technology_add"),
        {"name": "django", "kind": TechnologyKind.FRAMEWORK, "icon": svg_icon(), "website": ""},
    )

    assert response.status_code == 200
    assert escape(strings.TECHNOLOGY_NAME_TAKEN) in response.content.decode()


@pytest.mark.django_db
def test_la_fiche_d_une_technologie_lie_son_icone_sous_les_medias(admin_client: Client) -> None:
    """Le lien que l'admin affiche sous « Actuellement » est l'adresse servie des médias."""
    stored = saved(technology())

    page = admin_client.get(reverse("admin:content_technology_change", args=[stored.pk]))

    assert f'href="/media/{stored.icon.name}"' in page.content.decode()


@pytest.mark.django_db
def test_l_admin_refuse_de_supprimer_une_technologie_employee(admin_client: Client) -> None:
    """La suppression est protégée (`PROTECT`) : l'écran de confirmation nomme les technologies de
    projet qui l'empêchent, et la technologie reste."""
    django = saved(technology(name="Django"))
    portfolio = saved_project(django)
    url = reverse("admin:content_technology_delete", args=[django.pk])

    page = admin_client.get(url).content.decode()
    admin_client.post(url, {"post": "yes"})

    assert escape(f"{portfolio.title} · {django.name}") in page
    assert Technology.objects.filter(pk=django.pk).exists()


@pytest.mark.django_db
def test_l_ecran_projet_affiche_les_libelles_du_catalogue(admin_client: Client) -> None:
    """Toute chaîne du projet que l'écran montre vient du catalogue (décision 1) : champs dans
    l'ordre de l'écran, valeurs du type et du statut, titre, lignes de technologie."""
    response = admin_client.get(reverse("admin:content_project_add"))
    form = response.context["adminform"].form
    lines = response.context["inline_admin_formsets"][0]
    page = response.content.decode()

    assert {name: field.label for name, field in form.fields.items()} == {
        name: capfirst(label) for name, label in PROJECT_FIELD_LABELS.items()
    }
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


@pytest.mark.django_db
def test_l_ecran_projet_preremplit_le_slug_depuis_le_titre(admin_client: Client) -> None:
    """Le slug se remplit depuis le titre à la saisie (décision 3), par le script de l'admin, qui
    lit cette déclaration dans la page."""
    page = admin_client.get(reverse("admin:content_project_add")).content.decode()
    declaration = re.search(r'data-prepopulated-fields="([^"]*)"', page)

    assert declaration is not None
    prepopulated = json.loads(html.unescape(declaration.group(1)))
    assert [(field["name"], field["dependency_list"]) for field in prepopulated] == [
        ("slug", ["title"])
    ]


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
        form.instance.technology
        for form in response.context["inline_admin_formsets"][0].formset.initial_forms
    ]
    assert shown == [python, django]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lines",
    [{}, {f"{LINES}-TOTAL_FORMS": 0}],
    ids=["lignes laissées vides", "aucune ligne envoyée"],
)
def test_l_admin_refuse_un_projet_sans_technologie(
    admin_client: Client, lines: dict[str, object]
) -> None:
    """Seule règle hors base (décision 10) : l'écran la tient, avec le message du catalogue — même
    quand le formulaire n'envoie aucune ligne, ce que la ligne obligatoire seule laisserait
    passer."""
    url = reverse("admin:content_project_add")

    refusals = refused_lines(admin_client, url, new_project_data(admin_client, **lines))

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

    assert refused_lines(admin_client, url, data) == [strings.PROJECT_TECHNOLOGIES_MISSING]
    assert ProjectTechnology.objects.filter(project=portfolio).exists()


@pytest.mark.django_db
def test_l_admin_refuse_deux_fois_la_meme_technologie_dans_un_projet(
    admin_client: Client,
) -> None:
    """Le formulaire compare ses lignes entre elles avant la base : message du catalogue, là où
    Django nommerait le champ par son identifiant anglais."""
    django = saved(technology(name="Django"))
    data = new_project_data(admin_client, **line(0, django, 1), **line(1, django, 2))

    refusals = refused_lines(admin_client, reverse("admin:content_project_add"), data)

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
def test_la_liste_des_projets_montre_titre_type_statut_vitrine_et_publication(
    admin_client: Client,
) -> None:
    saved_project(saved(technology(name="Django")))

    page = admin_client.get(reverse("admin:content_project_changelist")).content.decode()

    columns = [
        strings.PROJECT_TITLE,
        strings.PROJECT_KIND,
        strings.PROJECT_STATUS,
        strings.PROJECT_SHOWCASE,
        strings.PROJECT_PUBLISHED,
    ]
    positions = [page.find(f">{escape(capfirst(column))}</") for column in columns]
    assert -1 not in positions
    assert positions == sorted(positions)
