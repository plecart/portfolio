"""Tests du cache du contenu : la liste des projets servie depuis le cache, à l'identique de la
base ; le cache vidé après chaque écriture validée du contenu, jamais avant ni pour une écriture
annulée ; Redis injoignable sans effet pour le client (brief de #11, décisions 1, 3, 5, 7 à 10).

La suite tourne sur le cache en mémoire que pose le harnais (`conftest`, `memory_cache`), vidé
avant chaque test ; seul le test de Redis injoignable charge le vrai client, `django-redis`.
"""

import ast
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import config.settings
import content.models
import pytest
from content.models import Project, ProjectTechnology
from django.core.cache import caches
from django.db import transaction
from django.db.models import Model
from django.test import Client, override_settings
from factories import gallery_image, project, saved, section, technology
from pytest_django import DjangoAssertNumQueries, DjangoCaptureOnCommitCallbacks
from test_api import PROJECTS, complete_project, listed
from test_tasks import Rollback

# La durée de vie de chaque clé du cache (décision 5).
TTL = 300

# Le projet de la fabrique : son slug, son résumé, puis celui qu'un test écrit sans qu'aucun
# signal parte.
FACTORY_SLUG = "portfolio"
SUMMARY = "Le site qui présente mes projets."
CHANGED_SUMMARY = "Un résumé que seule la base connaît."

# Les modèles de contenu que sert la liste, en littéraux : l'écriture de chacun vide le cache
# (décision 3). `test_les_cas_de_purge_couvrent_chaque_modele_de_contenu` les confronte aux
# déclarations du module des modèles.
CONTENT_MODELS = ["GalleryImage", "Project", "ProjectTechnology", "Section", "Technology"]

# Une autre origine que celle du client de test, `http://testserver` : les options de sa requête,
# puis l'origine des adresses qu'elle doit recevoir. `portfolio.test` est l'hôte admis par
# l'environnement de test (`process_environment.py`).
OTHER_ORIGINS: dict[str, tuple[dict[str, Any], str]] = {
    "autre hôte": ({"headers": {"host": "portfolio.test"}}, "http://portfolio.test"),
    "autre schéma": ({"secure": True}, "https://testserver"),
}

# Les deux écritures d'une ligne qui vident le cache : `post_save` et `post_delete`.
WRITES: dict[str, Callable[[Model], object]] = {
    "enregistrement": lambda line: line.save(),
    "suppression": lambda line: line.delete(),
}


def served(client: Client) -> tuple[object, ...]:
    """Ce que `client` reçoit de la liste : statut, en-têtes de contenu et de cache, corps."""
    response = client.get(PROJECTS)
    return (
        response.status_code,
        response["Content-Type"],
        response["Cache-Control"],
        response["ETag"],
        response.content,
    )


def summary(client: Client) -> str:
    """Le résumé du projet de la fabrique, `portfolio`, dans la liste que `client` reçoit."""
    [listed_project] = [p for p in listed(client) if p["slug"] == FACTORY_SLUG]
    return listed_project["summary"]


def titles(client: Client) -> list[str]:
    """Le titre de chaque projet que `client` reçoit dans la liste."""
    return [listed_project["title"] for listed_project in listed(client)]


def declared_models() -> set[str]:
    """Les classes que le module des modèles de contenu déclare `(models.Model)`."""
    tree = ast.parse(Path(content.models.__file__).read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(ast.unparse(base) == "models.Model" for base in node.bases)
    }


def expiries() -> list[float | None]:
    """L'échéance de chaque clé du cache en mémoire, `None` pour une clé sans durée de vie.

    `LocMemCache` n'a pas d'API qui les lise : son dictionnaire `_expire_info` les tient, clé par
    clé (Django 6.1, `django/core/cache/backends/locmem.py`).
    """
    expire_info: dict[str, float | None] = vars(caches["default"])["_expire_info"]
    return list(expire_info.values())


@pytest.fixture
def lines() -> dict[str, Model]:
    """Pour chaque modèle de contenu, une ligne enregistrée, qu'un test enregistre de nouveau ou
    supprime seule : sa suppression n'emporte aucune autre ligne, et seul son modèle émet un
    signal. Le projet est donc un second projet, sans rien ; la technologie, une qu'aucun projet
    n'emploie — la base refuse de supprimer une technologie employée."""
    listed_project = saved(project(published=True))
    line = ProjectTechnology(project=listed_project, technology=saved(technology()), position=1)
    return {
        "GalleryImage": saved(gallery_image(listed_project)),
        "Project": saved(project(slug="sans-rien", published=True)),
        "ProjectTechnology": saved(line),
        "Section": saved(section(listed_project)),
        "Technology": saved(technology(name="Inemployée")),
    }


@pytest.mark.django_db
def test_le_second_appel_de_la_liste_n_interroge_pas_la_base(
    client: Client, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    """Le premier appel remplit le cache ; le second est servi sans une requête en base."""
    complete_project("en-cache", saved(technology()))
    listed(client)

    with django_assert_num_queries(0):
        listed(client)


@pytest.mark.django_db
def test_la_reponse_servie_depuis_le_cache_est_celle_de_la_base(
    client: Client, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    """Même corps octet pour octet, donc même `ETag` (`ConditionalGetMiddleware`) ; même type,
    même `Cache-Control: no-cache` (brief de #10, décision 7)."""
    complete_project("identique", saved(technology()))
    from_base = served(client)

    with django_assert_num_queries(0):
        from_cache = served(client)

    assert from_cache == from_base


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("request_options", "origin"), OTHER_ORIGINS.values(), ids=OTHER_ORIGINS.keys()
)
def test_chaque_origine_recoit_la_liste_a_ses_propres_adresses(
    client: Client, request_options: dict[str, Any], origin: str
) -> None:
    """Le corps porte des adresses absolues construites sur l'origine de la requête : la liste en
    cache pour une origine n'est jamais servie à une autre (décision 10)."""
    complete_project("origines", saved(technology()))
    listed(client)

    response = client.get(PROJECTS, **request_options)

    assert response.json()[0]["technologies"][0]["icon"].startswith(f"{origin}/media/")


@pytest.mark.django_db
@pytest.mark.parametrize("write", WRITES.values(), ids=WRITES.keys())
@pytest.mark.parametrize("model", CONTENT_MODELS)
def test_une_ecriture_validee_d_un_modele_de_contenu_vide_le_cache(
    client: Client,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    lines: dict[str, Model],
    model: str,
    write: Callable[[Model], object],
) -> None:
    """La liste en cache, puis le résumé d'un projet changé par `QuerySet.update`, qui n'émet
    aucun signal : la liste servie depuis le cache ne le montre pas, jusqu'à l'écriture validée
    d'une ligne du modèle. Ce résumé, qu'aucune des écritures ne touche, est le témoin de la purge,
    le même pour chaque modèle : supprimer une technologie que nul n'emploie ne change rien
    d'autre à la liste."""
    listed(client)
    Project.objects.filter(slug=FACTORY_SLUG).update(summary=CHANGED_SUMMARY)
    from_cache = summary(client)

    with django_capture_on_commit_callbacks(execute=True):
        write(lines[model])

    assert (from_cache, summary(client)) == (SUMMARY, CHANGED_SUMMARY)


def test_les_cas_de_purge_couvrent_chaque_modele_de_contenu() -> None:
    """Un modèle ajouté au module des modèles de contenu rougit ici tant que ses deux cas — et sa
    ligne de `lines` — n'existent pas : la population du test paramétré est celle du module."""
    assert set(CONTENT_MODELS) == declared_models()


@pytest.mark.django_db
def test_une_ecriture_annulee_ne_vide_pas_le_cache(
    client: Client,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """Une transaction annulée n'a rien écrit : la liste reste servie depuis le cache."""
    published = saved(project(published=True))
    listed(client)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(Rollback),
        transaction.atomic(),
    ):
        published.title = "Jamais validé"
        published.save()
        raise Rollback

    with django_assert_num_queries(0):
        listed(client)


@pytest.mark.django_db
def test_le_cache_est_vide_apres_la_validation_jamais_avant(
    client: Client, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """Entre l'écriture et la validation, la liste vient encore du cache : vidé avant, il
    laisserait une requête concurrente y remettre le contenu que la base tient encore pour
    validé (décision 3)."""
    published = saved(project(published=True))
    listed(client)

    with django_capture_on_commit_callbacks() as callbacks:
        published.title = "Validé"
        published.save()
        before_commit = titles(client)
    for callback in callbacks:
        callback()

    assert (before_commit, titles(client)) == (["Portfolio"], ["Validé"])


@pytest.mark.django_db
def test_chaque_cle_ecrite_par_le_cache_porte_une_duree_de_vie(
    client: Client, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """La génération comme les réponses, à la création comme à la purge : aucune clé sans
    durée de vie, la seule sorte que `volatile-lru` évince — jamais la file du broker (décisions
    5 et 6, ADR 0015)."""
    published = saved(project(published=True))
    listed(client)
    first = expiries()
    with django_capture_on_commit_callbacks(execute=True):
        published.save()
    listed(client)
    written = first + expiries()
    deadline = time.time() + TTL

    assert written
    assert [expiry for expiry in written if expiry is None or expiry > deadline] == []


@pytest.mark.django_db
def test_redis_injoignable_la_liste_vient_de_la_base_et_l_incident_est_journalise(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    """Le vrai client, `django-redis`, sur les réglages de production — `REDIS_URL` vise une
    adresse qui ne se résout nulle part (`process_environment.py`) : `200` et le corps de la base,
    chaque exception ignorée journalisée par `django-redis` (décision 7)."""
    complete_project("degrade", saved(technology()))
    from_base = client.get(PROJECTS)

    with override_settings(CACHES=config.settings.CACHES):
        degraded = client.get(PROJECTS)

    assert (degraded.status_code, degraded.content) == (200, from_base.content)
    logged = {(r.name, r.levelno, r.getMessage()) for r in caplog.records if r.exc_info}
    assert logged == {("django_redis.cache", logging.ERROR, "Exception ignored")}
