"""Tests du cache du contenu : la liste des projets servie depuis le cache, à l'identique de la
base, jamais une réponse d'erreur ni une lecture antérieure à une écriture validée ; le cache vidé
après chaque écriture validée du contenu, jamais avant ni pour une écriture annulée, et par la
tâche d'image après chacune de ses écritures ; Redis injoignable sans effet pour le client, au
prix de deux opérations sur Redis au plus (brief de #11, décisions 1, 3 à 5, 7 à 10).

La suite tourne sur le cache en mémoire que pose le harnais (`conftest`, `memory_cache`), vidé
avant chaque test ; seuls les tests de Redis injoignable chargent le vrai client, `django-redis`.
"""

import ast
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import config.settings
import content.api
import content.models
import pytest
from content import tasks
from content.api import published_projects
from content.models import GalleryImage, ProcessingState, Project, ProjectTechnology, Variant
from content.tasks import process_image
from content.variants import make_variants
from django.core.cache import caches
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.db import transaction
from django.db.models import Model
from django.test import Client, override_settings
from factories import gallery_image, project, saved, section, technology
from ninja.errors import HttpError
from pytest_django import DjangoAssertNumQueries, DjangoCaptureOnCommitCallbacks
from test_api import PROJECTS, complete_project, listed
from test_tasks import Rollback, variant_files

# La durée de vie de chaque clé du cache (décision 5).
TTL = 300

# Les opérations sur Redis qu'une requête de la liste paie quand Redis ne répond pas : lire la
# génération, puis tenter d'en poser une neuve. Sur un Redis figé, chacune attend ses délais
# (`REDIS_DELAYS`) avant d'être ignorée — de l'ordre de 0,2 s, mesuré par la relecture de la
# PR #218 sur un hôte qui ne répond pas.
OPERATIONS_WITHOUT_REDIS = 2

# Les délais de `django-redis` qu'une opération sur un Redis muet attend (décision 7) : chacun
# posé, et d'au plus `REDIS_DELAY` secondes.
REDIS_DELAYS = ["SOCKET_CONNECT_TIMEOUT", "SOCKET_TIMEOUT"]
REDIS_DELAY = 0.2

# Des options de `django-redis`, puis les délais que la garde doit y signaler.
DELAY_FORMS: dict[str, tuple[dict[str, object], list[str]]] = {
    "délai de connexion absent": ({"SOCKET_TIMEOUT": 0.2}, ["SOCKET_CONNECT_TIMEOUT"]),
    "délai de réponse sans fin": (
        {"SOCKET_CONNECT_TIMEOUT": 0.2, "SOCKET_TIMEOUT": None},
        ["SOCKET_TIMEOUT"],
    ),
    "délais trop longs": (
        {"SOCKET_CONNECT_TIMEOUT": 5, "SOCKET_TIMEOUT": 0.3},
        ["SOCKET_CONNECT_TIMEOUT", "SOCKET_TIMEOUT"],
    ),
}

# L'issue d'un traitement : son original rendu illisible ou non, puis l'état qu'il écrit.
OUTCOMES: dict[str, tuple[bool, ProcessingState]] = {
    "prêt": (False, ProcessingState.READY),
    "échec": (True, ProcessingState.FAILED),
}

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


def slow_delays(options: dict[str, object]) -> list[str]:
    """Les délais de `REDIS_DELAYS` que `options` ne pose pas, pose sans borne (`None`), ou pose
    au-delà de `REDIS_DELAY`."""
    return [
        name
        for name in REDIS_DELAYS
        if not isinstance(delay := options.get(name), int | float) or delay > REDIS_DELAY
    ]


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
def test_une_liste_lue_avant_une_ecriture_validee_n_est_pas_servie_apres(
    client: Client,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La vue lit la base, puis une écriture du contenu est validée et vide le cache, avant que la
    réponse ne soit gardée : l'appel suivant montre le contenu neuf. La génération est lue avant
    la base (décision 8) ; relue après, elle rangerait l'ancien contenu sous la neuve."""
    published = saved(project(published=True))

    def read_then_written() -> list[Project]:
        read = list(published_projects())
        with django_capture_on_commit_callbacks(execute=True):
            published.title = "Écrit pendant la lecture"
            published.save()
        return read

    with monkeypatch.context() as patched:
        patched.setattr(content.api, "published_projects", read_then_written)
        during = titles(client)

    assert (during, titles(client)) == (["Portfolio"], ["Écrit pendant la lecture"])


@pytest.mark.django_db
def test_une_reponse_d_erreur_de_la_vue_n_entre_pas_dans_le_cache(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une erreur que django-ninja rend en réponse (`on_exception`) n'est jamais gardée : l'appel
    suivant relit la base, et rend la liste."""
    saved(project(published=True))

    def unavailable() -> list[Project]:
        raise HttpError(503, "Base injoignable.")

    with monkeypatch.context() as patched:
        patched.setattr(content.api, "published_projects", unavailable)
        failed = client.get(PROJECTS).status_code

    assert (failed, titles(client)) == (503, ["Portfolio"])


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


@pytest.mark.django_db
def test_redis_injoignable_une_requete_de_la_liste_ne_paie_que_deux_operations(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    """Le vrai client sur l'adresse injoignable : chaque opération sur Redis échoue, puis
    `django-redis` l'ignore et la journalise, une entrée chacune (`omit_exception`,
    `django_redis/cache.py` 7.0.0). La génération lue, une neuve qui ne se pose pas, et rien ne se
    lit ni ne s'écrit ensuite."""
    with override_settings(CACHES=config.settings.CACHES):
        client.get(PROJECTS)

    ignored = [record for record in caplog.records if record.name == "django_redis.cache"]
    assert len(ignored) == OPERATIONS_WITHOUT_REDIS


def test_les_delais_de_redis_des_reglages_sont_courts() -> None:
    """Chaque opération sur un Redis qui ne répond pas les attend avant que la liste ne vienne de
    la base (décision 7)."""
    options = cast("dict[str, object]", config.settings.CACHES["default"]["OPTIONS"])

    assert slow_delays(options) == []


@pytest.mark.parametrize(("options", "expected"), DELAY_FORMS.values(), ids=DELAY_FORMS.keys())
def test_la_garde_des_delais_de_redis_rend_son_verdict_sur_chaque_forme(
    options: dict[str, object], expected: list[str]
) -> None:
    """Les réglages de cache ne se mutent pas (réglage de sécurité, `mutation.py`) : la garde se
    voit rougir ici, sur des options construites."""
    assert slow_delays(options) == expected


def gallery_states(client: Client) -> list[str]:
    """L'état de chaque image de la galerie du seul projet de la liste que `client` reçoit."""
    [listed_project] = listed(client)
    return [image["state"] for image in listed_project["gallery"]]


def replace_original_silently(image: GalleryImage) -> None:
    """Remplace l'original de la ligne de `image` sans qu'aucun signal parte (`QuerySet.update`) :
    l'écriture conditionnelle de la tâche ne la trouve plus, et seule la tâche pourrait vider le
    cache."""
    GalleryImage.objects.filter(pk=image.pk).update(original="images/autre/original.png")


def make_unreadable(image: GalleryImage) -> None:
    """Remplace le fichier de l'original de `image` par des octets qui ne sont pas une image :
    chaque essai de son traitement échoue."""
    name = image.original.name or ""
    default_storage.delete(name)
    default_storage.save(name, ContentFile(b"Plus une image."))


@pytest.fixture
def pending_image() -> GalleryImage:
    """Une image en attente d'un projet publié, enregistrée hors de tout rappel exécuté : son
    traitement n'est pas enfilé, et le test le lance lui-même."""
    return saved(gallery_image(saved(project(published=True))))


@pytest.mark.django_db
def test_la_liste_montre_l_image_prete_des_la_fin_de_son_traitement(
    client: Client, pending_image: GalleryImage
) -> None:
    """L'écriture du worker échappe aux signaux (`QuerySet.update`) : la tâche vide le cache
    elle-même, sans attendre la durée de vie (décision 4)."""
    before = gallery_states(client)

    process_image.delay(pending_image.pk, pending_image.original.name or "")

    assert (before, gallery_states(client)) == (["pending"], ["ready"])


@pytest.mark.django_db
@pytest.mark.usefixtures("unpropagated")
def test_la_liste_montre_l_image_en_echec_des_la_fin_de_son_traitement(
    client: Client, pending_image: GalleryImage
) -> None:
    """Un original devenu illisible : réessais épuisés, l'image passe en échec, et la tâche vide
    le cache de même."""
    make_unreadable(pending_image)
    before = gallery_states(client)

    process_image.delay(pending_image.pk, pending_image.original.name or "")

    assert (before, gallery_states(client)) == (["pending"], ["failed"])


@pytest.mark.django_db
@pytest.mark.usefixtures("unpropagated")
@pytest.mark.parametrize(("unreadable", "state"), OUTCOMES.values(), ids=OUTCOMES.keys())
def test_une_purge_qui_echoue_est_journalisee_sans_defaire_le_traitement(
    pending_image: GalleryImage,
    caplog: pytest.LogCaptureFixture,
    unreadable: bool,
    state: ProcessingState,
) -> None:
    """Le vrai client sur une adresse injoignable, ses exceptions non ignorées : la purge lève
    après l'écriture de « prêt » comme d'« échec ». L'image garde l'état écrit, sans réessai qui
    la ferait passer de « prêt » à « échec », son dossier ne tient que les variantes qu'elle
    nomme, et l'erreur est journalisée avec sa trace — `django-redis` ne journalise que celles
    qu'il ignore."""
    if unreadable:
        make_unreadable(pending_image)
    production = config.settings.CACHES["default"]
    options = cast("dict[str, object]", production["OPTIONS"])
    raising = {**production, "OPTIONS": {**options, "IGNORE_EXCEPTIONS": False}}

    with override_settings(CACHES={"default": raising}):
        process_image.delay(pending_image.pk, pending_image.original.name or "")

    row = GalleryImage.objects.get(pk=pending_image.pk)
    named = sorted(variant["name"].rsplit("/", 1)[1] for variant in row.variants)
    logged = [(r.levelno, bool(r.exc_info)) for r in caplog.records if r.name == "content.tasks"]
    assert (row.state, variant_files(row), logged) == (state, named, [(logging.ERROR, True)])


@pytest.mark.django_db
def test_un_traitement_qui_n_ecrit_rien_ne_vide_pas_le_cache(
    client: Client,
    pending_image: GalleryImage,
    monkeypatch: pytest.MonkeyPatch,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """L'original remplacé pendant le traitement : « prêt » ne s'écrit sur aucune ligne, et la
    liste reste servie depuis le cache."""
    listed(client)

    def replaced_meanwhile(storage: Storage, original_name: str) -> list[Variant]:
        replace_original_silently(pending_image)
        return make_variants(storage, original_name)

    monkeypatch.setattr(tasks, "make_variants", replaced_meanwhile)
    process_image.delay(pending_image.pk, pending_image.original.name or "")

    with django_assert_num_queries(0):
        listed(client)


@pytest.mark.django_db
@pytest.mark.usefixtures("unpropagated")
def test_un_echec_qui_n_ecrit_rien_ne_vide_pas_le_cache(
    client: Client,
    pending_image: GalleryImage,
    monkeypatch: pytest.MonkeyPatch,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """L'original remplacé pendant le dernier essai : « échec » ne s'écrit sur aucune ligne, et
    la liste reste servie depuis le cache."""
    listed(client)
    attempts: list[str] = []

    def failing(storage: Storage, original_name: str) -> list[Variant]:
        attempts.append(original_name)
        if len(attempts) == tasks.MAX_RETRIES + 1:
            replace_original_silently(pending_image)
        raise OSError("stockage injoignable")

    monkeypatch.setattr(tasks, "make_variants", failing)
    process_image.delay(pending_image.pk, pending_image.original.name or "")

    with django_assert_num_queries(0):
        listed(client)
