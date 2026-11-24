"""Tests de l'admin Django : monté à `/admin/`, en français, fermé aux anonymes, ses fichiers
statiques, et l'écran Technologie. L'écran Projet a les siens (`test_project_admin.py`), et sa
liste aussi (`test_project_list_admin.py`)."""

import re

import pytest
from config import strings
from content.models import ProjectTechnology, Technology, TechnologyKind
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
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
    portfolio = saved(project())
    saved(ProjectTechnology(project=portfolio, technology=django, position=1))
    url = reverse("admin:content_technology_delete", args=[django.pk])

    page = admin_client.get(url).content.decode()
    admin_client.post(url, {"post": "yes"})

    assert escape(f"{portfolio.title} · {django.name}") in page
    assert Technology.objects.filter(pk=django.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("screen", ["admin:content_project_add", "admin:content_technology_add"])
def test_chaque_fichier_statique_d_un_ecran_de_l_admin_existe(
    admin_client: Client, screen: str
) -> None:
    """Un script ou une feuille de style introuvable laisse l'écran sans son comportement, sans
    erreur visible en développement ; en production, le stockage à manifeste (ADR 0014) refuse de
    rendre la page. Chaque fichier que l'écran demande — sous son nom versionné — doit exister
    parmi les fichiers collectés, ceux que WhiteNoise sert."""
    page = admin_client.get(reverse(screen)).content.decode()

    requested = re.findall(rf'(?:src|href)="{re.escape(settings.STATIC_URL)}([^"]+)"', page)

    assert requested
    assert [path for path in requested if not staticfiles_storage.exists(path)] == []
