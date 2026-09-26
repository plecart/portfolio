"""Tests de l'admin Django : monté à `/admin/`, en français, fermé aux anonymes, et ses écrans."""

import pytest
from config import strings
from content.models import TechnologyKind
from django.test import Client
from django.urls import reverse
from django.utils.html import escape
from django.utils.text import capfirst
from django.utils.translation import gettext
from factories import svg_icon, technology

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
    with_website = technology(name="Django", website="https://www.djangoproject.com/")
    with_website.save()
    without_website = technology(name="Python")
    without_website.save()

    page = admin_client.get(reverse("admin:content_technology_changelist")).content.decode()

    columns = [
        strings.TECHNOLOGY_NAME,
        strings.TECHNOLOGY_KIND,
        strings.TECHNOLOGY_ICON,
        strings.TECHNOLOGY_WEBSITE,
    ]
    positions = [page.find(f">{escape(capfirst(column))}</") for column in columns]
    assert -1 not in positions
    assert positions == sorted(positions)
    for saved in (with_website, without_website):
        assert f'<img src="{saved.icon.url}"' in page
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
    saved = technology()
    saved.save()

    page = admin_client.get(reverse("admin:content_technology_change", args=[saved.pk]))

    assert f'href="/media/{saved.icon.name}"' in page.content.decode()
