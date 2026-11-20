"""Tests de l'API publique : la liste des projets publiés, `GET /api/projets` (brief de #10,
décisions 1 à 5 et 12), et sa politique HTTP (décisions 6 à 9)."""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from content.models import (
    COVER_MIN_SIDE,
    ProcessingState,
    Project,
    ProjectStatus,
    ProjectTechnology,
    Technology,
    TechnologyKind,
)
from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from factories import gallery_image, project, saved, section, technology
from pytest_django import DjangoCaptureOnCommitCallbacks
from test_django_project import run_python
from test_markdown_preview import importers

PROJECTS = "/api/projets"

# L'origine admise par l'environnement de test (`process_environment.py`), et une autre.
SITE_ORIGIN = "https://site.test"
OTHER_ORIGIN = "https://autre.test"
ALLOW_ORIGIN = "Access-Control-Allow-Origin"

# Une variante d'image prête, telle que le worker l'écrit.
VARIANT = {"name": "images/x/800.webp", "width": 800, "height": 800}

# Ce que le contrat n'expose à aucun niveau (décisions 2 et 3), écrit ici sans le lire dans le
# module des schémas.
UNEXPOSED_KEYS = {
    "cover",
    "original",
    "published",
    "position",
    "id",
    "created_at",
    "updated_at",
    "website",
}


def linked(owner: Project, *employed: Technology) -> None:
    """Rattache `employed` à `owner`, dans cet ordre."""
    for position, used in enumerate(employed, start=1):
        saved(ProjectTechnology(project=owner, technology=used, position=position))


def listed(client: Client) -> list[dict[str, Any]]:
    """Le corps de la liste, décodé, après avoir vérifié qu'elle répond `200`."""
    response = client.get(PROJECTS)
    assert response.status_code == 200
    return response.json()


def complete_project(slug: str, employed: Technology) -> Project:
    """Un projet publié de slug `slug`, avec `employed` pour technologie, une image et une
    section : chaque liste du contrat a de quoi déclencher sa requête."""
    published = saved(project(slug=slug, title=slug, published=True))
    linked(published, employed)
    saved(gallery_image(published))
    saved(section(published))
    return published


def project_with_variant(slug: str) -> None:
    """Un projet complet de slug `slug` dont la galerie porte aussi une image prête et sa
    variante : chaque clé du contrat figure dans le corps."""
    published = complete_project(slug, saved(technology()))
    saved(gallery_image(published, position=2, state=ProcessingState.READY, variants=[VARIANT]))


def keys(value: object) -> Iterator[str]:
    """Chaque clé d'objet de `value`, un JSON décodé, à tous les niveaux d'imbrication."""
    if isinstance(value, dict):
        for key, nested in cast("dict[str, object]", value).items():
            yield key
            yield from keys(nested)
    elif isinstance(value, list):
        for nested in cast("list[object]", value):
            yield from keys(nested)


@pytest.mark.django_db
def test_la_liste_rend_un_projet_publie_dans_le_contrat(client: Client) -> None:
    """L'entrée nommée du brief : technologies et sections dans l'ordre de l'admin, une image en
    attente sans variante puis une image prête, chaque fichier par son adresse absolue."""
    published = saved(project(published=True))
    linked(
        published,
        saved(technology(name="Vite", kind=TechnologyKind.TOOL)),
        saved(technology(name="Django")),
    )
    saved(section(published, position=2, title="Résultat", anchor="resultat", body="Livré."))
    saved(section(published))
    saved(gallery_image(published))
    saved(
        gallery_image(
            published,
            position=2,
            caption="Le détail.",
            state=ProcessingState.READY,
            variants=[VARIANT],
        )
    )

    [listed_project] = listed(client)

    technologies = listed_project.pop("technologies")
    assert [(used["name"], used["kind"]) for used in technologies] == [
        ("Vite", "tool"),
        ("Django", "framework"),
    ]
    assert all(
        used["icon"].startswith("http://testserver/media/technologies/") for used in technologies
    )
    assert listed_project.pop("sections") == [
        {
            "title": "Contexte et objectif",
            "anchor": "contexte-et-objectif",
            "body": "Pourquoi ce projet.",
        },
        {"title": "Résultat", "anchor": "resultat", "body": "Livré."},
    ]
    assert listed_project.pop("gallery") == [
        {
            "caption": "La fiche d'un projet.",
            "width": COVER_MIN_SIDE,
            "height": COVER_MIN_SIDE,
            "state": "pending",
            "variants": [],
        },
        {
            "caption": "Le détail.",
            "width": COVER_MIN_SIDE,
            "height": COVER_MIN_SIDE,
            "state": "ready",
            "variants": [
                {"url": "http://testserver/media/images/x/800.webp", "width": 800, "height": 800}
            ],
        },
    ]
    assert listed_project == {
        "slug": "portfolio",
        "title": "Portfolio",
        "summary": "Le site qui présente mes projets.",
        "description": "Une table de projets et leurs fiches.",
        "kind": "personal",
        "status": "ongoing",
        "started_on": "2026-09-01",
        "finished_on": None,
        "client": "",
        "repository_url": "",
        "demo_url": "",
        "showcase": False,
    }


@pytest.mark.django_db
def test_une_adresse_que_le_stockage_rend_absolue_reste_telle_quelle(client: Client) -> None:
    """R2 rend des adresses absolues, sur l'hôte des médias (`config/storage.py`) : la liste les
    garde telles quelles, jamais réécrites sur l'hôte de la requête (décision 5). Un `MEDIA_URL`
    absolu fait rendre au stockage disque la même forme d'adresse."""
    project_with_variant("medias")

    with override_settings(MEDIA_URL="https://media.test/"):
        [listed_project] = listed(client)

    assert listed_project["technologies"][0]["icon"].startswith("https://media.test/technologies/")
    assert listed_project["gallery"][1]["variants"][0]["url"] == (
        "https://media.test/images/x/800.webp"
    )


@pytest.mark.django_db
def test_un_brouillon_n_est_jamais_liste(client: Client) -> None:
    """Seuls les projets publiés figurent dans la liste."""
    employed = saved(technology())
    complete_project("publie", employed)
    draft = complete_project("brouillon", employed)
    draft.published = False
    draft.save()

    assert [listed_project["slug"] for listed_project in listed(client)] == ["publie"]


@pytest.mark.django_db
def test_sans_projet_publie_la_liste_est_vide(client: Client) -> None:
    """Une liste vide est `[]` en `200`, jamais une erreur."""
    saved(project())

    assert listed(client) == []


@pytest.mark.django_db
def test_un_projet_termine_rend_ses_deux_dates_iso(client: Client) -> None:
    """Les dates sont en ISO 8601 ; la date de fin d'un projet terminé est exposée."""
    finished = complete_project("termine", saved(technology()))
    finished.status = ProjectStatus.FINISHED
    finished.finished_on = date(2026, 9, 30)
    finished.save()

    [listed_project] = listed(client)

    assert (listed_project["started_on"], listed_project["finished_on"]) == (
        "2026-09-01",
        "2026-09-30",
    )


@pytest.mark.django_db
def test_la_liste_suit_l_ordre_des_slugs(client: Client) -> None:
    """Un même contenu rend toujours le même corps : la liste suit le slug, pas l'ordre physique
    des lignes. Réenregistrer « alpha » le place après « zeta » dans la table — Postgres écrit une
    nouvelle version de la ligne —, si bien qu'une liste sans tri rendrait l'ordre inverse."""
    employed = saved(technology())
    alpha = complete_project("alpha", employed)
    complete_project("zeta", employed)
    alpha.save()

    assert [listed_project["slug"] for listed_project in listed(client)] == ["alpha", "zeta"]


@pytest.mark.django_db
def test_le_contrat_n_expose_aucun_champ_ecarte(client: Client) -> None:
    """Aucune clé écartée par les décisions 2 et 3, à aucun niveau du corps — projet,
    technologies, galerie, variantes, sections."""
    project_with_variant("complet")

    body = listed(client)

    assert {"technologies", "gallery", "url", "sections", "anchor"} <= set(keys(body))
    assert UNEXPOSED_KEYS.isdisjoint(keys(body))


@pytest.mark.django_db
def test_la_liste_coute_autant_de_requetes_pour_un_projet_que_pour_douze(client: Client) -> None:
    """Le nombre de requêtes SQL ne dépend pas du nombre de projets (décision 12) : l'invariant est
    l'égalité des deux décomptes, jamais leur valeur. Le cache vidé, le second appel lit la base
    comme le premier."""
    employed = saved(technology())
    complete_project("projet-0", employed)
    with CaptureQueriesContext(connection) as single:
        listed(client)
    for index in range(1, 12):
        complete_project(f"projet-{index}", employed)
    cache.clear()

    with CaptureQueriesContext(connection) as twelve:
        assert len(listed(client)) == 12

    assert len(twelve) == len(single)


@pytest.mark.parametrize("route", ["/api/docs", "/api/openapi.json"])
def test_ni_docs_ni_schema_ne_sont_servis_en_ligne(client: Client, route: str) -> None:
    """Rien ne consomme les docs interactives ni le schéma en ligne (décision 10) : le schéma vit
    dans `apps/api/openapi.json`."""
    assert client.get(route).status_code == 404


@pytest.mark.django_db
def test_l_origine_du_site_est_admise(client: Client) -> None:
    """L'origine admise reçoit la sienne en retour, et la réponse varie par origine : un cache
    partagé ne doit jamais servir à une origine ce qui a été répondu à une autre (décision 8)."""
    response = client.get(PROJECTS, headers={"origin": SITE_ORIGIN})

    assert response.status_code == 200
    assert response[ALLOW_ORIGIN] == SITE_ORIGIN
    assert "origin" in response["Vary"].lower()


@pytest.mark.django_db
def test_une_autre_origine_ne_recoit_rien(client: Client) -> None:
    """Toute autre origine est refusée par le navigateur : aucun en-tête CORS (décision 8)."""
    response = client.get(PROJECTS, headers={"origin": OTHER_ORIGIN})

    assert response.status_code == 200
    assert not response.has_header(ALLOW_ORIGIN)


def test_cors_est_borne_aux_routes_de_l_api(client: Client) -> None:
    """L'admin n'a pas vocation à être appelé depuis le site, même depuis l'origine admise
    (décision 8, `CORS_URLS_REGEX`)."""
    response = client.get("/admin/login/", headers={"origin": SITE_ORIGIN})

    assert response.status_code == 200
    assert not response.has_header(ALLOW_ORIGIN)


# Demande une icône téléversée depuis chaque origine passée en argument, et imprime, par origine, le
# statut et l'en-tête CORS reçus. Dans un processus neuf : `config.urls` ne rend la route `/media/`
# qu'en `DEBUG`, une fois, à l'import (`test_django_project.py`), et le processus de test tourne
# sans. L'hôte est celui qu'admet l'environnement de test.
MEDIA_CORS = """
import json, os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.test import Client
answers = {}
for origin in sys.argv[1:]:
    response = Client().get(
        '/media/technologies/icone.svg', headers={'host': 'portfolio.test', 'origin': origin}
    )
    answers[origin] = [response.status_code, response.headers.get('Access-Control-Allow-Origin')]
print(json.dumps(answers))
"""


def test_un_media_servi_en_developpement_n_admet_que_l_origine_du_site(
    variables: dict[str, str], tmp_path: Path
) -> None:
    """Sur le poste, le site affiche les icônes en masque CSS, qui se charge en CORS, depuis
    l'origine de l'API (#271) : la seule origine du site les reçoit, comme la liste."""
    icon = tmp_path / "technologies" / "icone.svg"
    icon.parent.mkdir()
    icon.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')

    result = run_python(
        ["-c", MEDIA_CORS, SITE_ORIGIN, OTHER_ORIGIN],
        variables | {"DEBUG": "true", "MEDIA_ROOT": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {SITE_ORIGIN: [200, SITE_ORIGIN], OTHER_ORIGIN: [200, None]}


@pytest.mark.django_db
def test_la_liste_se_revalide_a_chaque_visite(client: Client) -> None:
    """`Cache-Control: no-cache`, exactement : stocker, revalider à chaque visite, `304` si rien
    n'a changé (décision 7) — ni `max-age`, ni `no-store`, qui empêcherait l'`ETag`."""
    response = client.get(PROJECTS)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-cache"


@pytest.mark.django_db
def test_la_liste_ne_pose_aucun_cookie(client: Client) -> None:
    """Ni session ni CSRF : la liste n'ouvre aucune session et ne pose aucun cookie (décision 9,
    ADR 0008 « sans cookie »)."""
    response = client.get(PROJECTS)

    assert response.status_code == 200
    assert not response.has_header("Set-Cookie")
    assert not response.cookies


@pytest.mark.django_db
def test_l_etag_est_l_empreinte_du_corps(
    client: Client, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """Même contenu, même `ETag` — le second appel est servi depuis le cache ; une légende
    modifiée — un changement qu'`updated_at` du projet ne voit pas — en change, une fois
    l'écriture validée et le cache vidé (décision 6 ; brief de #11, décision 3)."""
    published = complete_project("empreinte", saved(technology()))

    first, second = client.get(PROJECTS), client.get(PROJECTS)
    image = published.gallery.get()
    image.caption = "Une autre légende."
    with django_capture_on_commit_callbacks(execute=True):
        image.save()
    third = client.get(PROJECTS)

    assert first["ETag"] == second["ETag"]
    assert third["ETag"] != first["ETag"]


@pytest.mark.django_db
def test_un_etag_correspondant_rend_304_sans_corps(client: Client) -> None:
    """`If-None-Match` égal → `304` à corps vide, qui garde l'en-tête CORS : le navigateur du
    site lit la réponse conditionnelle comme les autres (décision 6)."""
    complete_project("conditionnel", saved(technology()))
    etag = client.get(PROJECTS)["ETag"]

    response = client.get(PROJECTS, headers={"if-none-match": etag, "origin": SITE_ORIGIN})

    assert response.status_code == 304
    assert response.content == b""
    assert response[ALLOW_ORIGIN] == SITE_ORIGIN


@pytest.mark.django_db
def test_un_etag_different_rend_le_corps(client: Client) -> None:
    """`If-None-Match` différent → `200` avec le corps."""
    complete_project("perime", saved(technology()))

    response = client.get(PROJECTS, headers={"if-none-match": '"perime"'})

    assert response.status_code == 200
    assert response.json()


def test_seuls_les_modules_de_l_api_importent_django_ninja() -> None:
    """django-ninja ne sert qu'à l'API publique : son instance et son contrat, que les tests
    ci-dessus atteignent par la route."""
    assert importers("ninja") == {"content.api", "content.schemas"}
