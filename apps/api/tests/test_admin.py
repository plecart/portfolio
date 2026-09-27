"""Tests de l'admin Django : monté à `/admin/`, en français, fermé aux anonymes, et ses écrans."""

import html
import json
import re

import pytest
from config import strings
from content.models import Project, ProjectTechnology, Technology, TechnologyKind
from django.conf import settings
from django.contrib.staticfiles import finders
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

# Le script qui donne à chaque ligne en ligne le même bouton de suppression, et le script et la
# feuille qui les ordonnent par glisser-déposer.
INLINE_DELETE_SCRIPT = "content/admin/inline_delete.js"
INLINE_SORT_SCRIPT = "content/admin/inline_sort.js"
INLINE_ROWS_STYLE = "content/admin/inline_rows.css"

# Les classes des raccourcis que Django pose à côté d'une liste d'objets liés pour modifier, voir ou
# supprimer l'objet choisi (`admin/widgets/related_widget_wrapper.html`).
RELATED_LINKS = ["change-related", "view-related", "delete-related"]


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
def test_l_admin_accepte_une_technologie_retiree_puis_rajoutee_avant_l_enregistrement(
    admin_client: Client,
) -> None:
    """On manipule les lignes, puis on enregistre une fois : une technologie retirée puis
    rajoutée dans le même envoi n'est pas un doublon. La ligne retirée existe encore en base
    jusqu'à l'enregistrement ; l'unicité se juge entre les lignes gardées, pas contre elle."""
    django_, python = saved(technology(name="Django")), saved(technology(name="Python"))
    portfolio = saved_project(django_)
    saved(ProjectTechnology(project=portfolio, technology=python, position=2))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        f"{LINES}-0-DELETE": "on",
        f"{LINES}-1-DELETE": "on",
        **line(2, python, 1),
        **line(3, django_, 2),
    }

    response = admin_client.post(url, data)

    assert response.status_code == 302
    stored = ProjectTechnology.objects.filter(project=portfolio)
    assert [link.technology for link in stored] == [python, django_]


@pytest.mark.django_db
def test_l_admin_refuse_une_technologie_gardee_rajoutee_une_seconde_fois(
    admin_client: Client,
) -> None:
    """Le formset compare chaque ligne neuve aux lignes enregistrées qu'il garde : c'est lui, et
    non plus un contrôle ligne par ligne contre la base, qui refuse le doublon."""
    django_ = saved(technology(name="Django"))
    portfolio = saved_project(django_)
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | line(1, django_, 2)

    assert refused_lines(admin_client, url, data) == [strings.PROJECT_TECHNOLOGY_TAKEN]
    assert ProjectTechnology.objects.filter(project=portfolio).count() == 1


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


@pytest.mark.django_db
def test_chaque_ligne_de_technologie_porte_une_poignee_de_tri(admin_client: Client) -> None:
    """Décision 2 amendée (ADR 0013) : l'auteur fait glisser une ligne, enregistrée ou neuve, par
    sa poignée — ou la déplace au clavier. La position ne se saisit plus : elle voyage dans un champ
    caché que le script remplit à l'enregistrement, dans l'ordre affiché. Le glisser lui-même se
    regarde à l'écran (arrêt visuel) ; ce test tient ce que le serveur en livre."""
    portfolio = saved_project(saved(technology(name="Django")))

    response = admin_client.get(reverse("admin:content_project_change", args=[portfolio.pk]))
    page = response.content.decode()
    lines = response.context["inline_admin_formsets"][0].formset

    handle = f'class="sortable-handle" aria-label="{escape(strings.ADMIN_ROW_MOVE)}"'
    # Une poignée par ligne, enregistrée ou neuve, plus celle du modèle de ligne que l'admin clone.
    assert page.count(handle) == len(lines.forms) + 1
    positions = re.findall(rf'<input type="hidden" name="{LINES}-\d+-position"[^>]*>', page)
    assert len(positions) == len(lines.forms)
    assert all('class="sortable-position"' in position for position in positions)
    for asset in (INLINE_SORT_SCRIPT, INLINE_ROWS_STYLE):
        assert f"{settings.STATIC_URL}{asset}" in page


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
    assert f"{settings.STATIC_URL}{INLINE_DELETE_SCRIPT}" in page


@pytest.mark.django_db
def test_une_ligne_ajoutee_sans_position_se_range_apres_les_autres(admin_client: Client) -> None:
    """Sans le script — désactivé, ou en échec —, une ligne neuve arrive sans position :
    l'enregistrement la range après les autres, dans l'ordre du formulaire, au lieu de refuser un
    champ que l'auteur ne voit pas."""
    django_, python, react = (
        saved(technology(name=name)) for name in ("Django", "Python", "React")
    )
    portfolio = saved_project(django_)
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
        (django_, 1),
        (python, 2),
        (react, 3),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("screen", ["admin:content_project_add", "admin:content_technology_add"])
def test_chaque_fichier_statique_d_un_ecran_de_l_admin_existe(
    admin_client: Client, screen: str
) -> None:
    """Un script ou une feuille de style introuvable laisse l'écran sans son comportement, sans
    erreur visible en développement ; en production, le stockage à manifeste refuse de rendre la
    page. Chaque fichier que l'écran demande doit exister parmi les fichiers statiques."""
    page = admin_client.get(reverse(screen)).content.decode()

    requested = re.findall(rf'(?:src|href)="{re.escape(settings.STATIC_URL)}([^"]+)"', page)

    assert requested
    assert [path for path in requested if finders.find(path) is None] == []
