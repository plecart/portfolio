"""Tests de l'admin Django : monté à `/admin/`, en français, fermé aux anonymes, et ses écrans."""

import pytest
from django.test import Client
from django.urls import reverse
from factories import technology


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
def test_l_ecran_technologie_s_ouvre_avec_les_libelles_du_catalogue(admin_client: Client) -> None:
    response = admin_client.get(reverse("admin:content_technology_add"))

    assert response.status_code == 200
    assert "Icône" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("media_root")
def test_la_fiche_d_une_technologie_lie_son_icone_sous_les_medias(admin_client: Client) -> None:
    """Le lien que l'admin affiche sous « Actuellement » est l'adresse servie des médias."""
    saved = technology()
    saved.save()

    page = admin_client.get(reverse("admin:content_technology_change", args=[saved.pk]))

    assert f'href="/media/{saved.icon.name}"' in page.content.decode()
