"""Tests de l'observabilité du back (ADR 0027) : un seul rendu des journaux, une ligne JSON par
événement en production et un rendu lisible en développement, pour les loggers de l'application
comme pour ceux des bibliothèques ; une configuration posée une fois, que le worker garde ; un
identifiant de corrélation par requête HTTP et par exécution de tâche.

La configuration se pose à l'import des réglages, une fois par processus : elle s'éprouve par un
sous-processus neuf, comme `gunicorn` ou `celery -A config worker` le démarrent
(`test_django_project.run_python`). Le reste s'éprouve dans le processus de test, sur le rendu que
ses réglages y ont posé (`journal`).
"""

import io
import json
import logging
import subprocess
from collections.abc import Callable, Generator
from typing import Any

import pytest
import structlog
from celery import shared_task
from config.observability import CORRELATION_ID
from django.http import HttpRequest, HttpResponse
from django.test import Client, override_settings
from django.urls import path
from test_django_project import run_python

# Le démarrage de Django, dans un processus neuf.
STARTED = """
import logging, os, django, structlog
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
"""

# Un événement de chaque sorte de logger — l'appel qui le crée, le logger, le niveau, le message :
# celui de l'application, par `structlog` ; un logger de Django, dont la configuration par défaut
# ajouterait son propre rendu en développement ; un logger de bibliothèque qui porte un incident
# (#11).
EVENTS = [
    ("structlog.get_logger", "content", "info", "un événement de l'application"),
    ("logging.getLogger", "django.request", "warning", "Not Found: /absent/"),
    ("logging.getLogger", "django_redis.cache", "error", "Exception ignored"),
]
LOGGED_EVENTS = STARTED + "\n".join(
    f"{factory}({name!r}).{level}({message!r})" for factory, name, level, message in EVENTS
)

# La configuration rejouée par-dessus celle du démarrage, puis un seul événement.
CONFIGURED_AGAIN = (
    STARTED
    + """
from config.observability import configure_logging
configure_logging(debug=False)
configure_logging(debug=False)
logging.getLogger('content').warning('une seule fois')
print(len(logging.getLogger().handlers))
"""
)

# Ce que fait le worker au démarrage, avant de consommer : `celery -A config worker` configure la
# journalisation (`Logging.setup`, `celery/app/log.py`) et détourne la sortie standard vers ses
# loggers, sauf si un récepteur répond au signal `setup_logging`.
WORKER_STARTED = (
    STARTED
    + """
from config.celery import app
app.log.setup(loglevel='INFO', redirect_stdouts=True)
logging.getLogger('celery.worker').warning('le worker garde le rendu des réglages')
"""
)


def launched(script: str, variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Le résultat de `script`, lancé dans un processus neuf sur l'environnement `variables` : les
    journaux sortent sur sa sortie d'erreur."""
    result = run_python(["-c", script], variables)
    assert result.returncode == 0, result.stderr
    return result


def is_json(line: str) -> bool:
    """Vrai si `line` est un objet JSON entier."""
    try:
        return isinstance(json.loads(line), dict)
    except json.JSONDecodeError:
        return False


def test_en_production_chaque_evenement_est_une_ligne_json(variables: dict[str, str]) -> None:
    """`DEBUG` faux : une ligne JSON par événement, quel que soit le logger, et une seule — le
    logger, le niveau et le message y sont des champs."""
    lines = launched(LOGGED_EVENTS, variables).stderr.splitlines()

    events = [json.loads(line) for line in lines]
    assert [(event["logger"], event["level"], event["event"]) for event in events] == [
        (name, level, message) for _, name, level, message in EVENTS
    ]


def test_en_developpement_chaque_evenement_est_rendu_lisible(variables: dict[str, str]) -> None:
    """`DEBUG` vrai : une ligne lisible par événement, et une seule — la configuration par défaut
    de Django ajouterait la sienne aux loggers `django` (`DEFAULT_LOGGING`, handler `console`)."""
    lines = launched(LOGGED_EVENTS, variables | {"DEBUG": "true"}).stderr.splitlines()

    assert len(lines) == len(EVENTS), lines
    rendered = [
        (message in line, is_json(line))
        for line, (_, _, _, message) in zip(lines, EVENTS, strict=True)
    ]
    assert rendered == [(True, False)] * len(EVENTS)


def test_la_configuration_rejouee_ne_double_aucune_ligne(variables: dict[str, str]) -> None:
    """Rejouée, la configuration remplace son gestionnaire au lieu d'en ajouter un : un seul
    gestionnaire, une seule ligne par événement."""
    result = launched(CONFIGURED_AGAIN, variables)

    assert result.stdout.strip() == "1"
    assert [json.loads(line)["event"] for line in result.stderr.splitlines()] == ["une seule fois"]


def test_le_worker_garde_la_journalisation_des_reglages(variables: dict[str, str]) -> None:
    """Le worker ne reconfigure rien par-dessus les réglages : sans récepteur du signal
    `setup_logging`, Celery remplacerait le gestionnaire du logger racine par le sien, à son propre
    format (`worker_hijack_root_logger`)."""
    lines = launched(WORKER_STARTED, variables).stderr.splitlines()

    assert [json.loads(line)["event"] for line in lines] == [
        "le worker garde le rendu des réglages"
    ]


# Le logger de l'application que journalisent la vue et la tâche de test.
LOGGER = "content"

# Les événements journalisés depuis le début d'un test, chacun l'objet de sa ligne JSON.
Journal = Callable[[], list[dict[str, Any]]]


def journaling_view(request: HttpRequest) -> HttpResponse:
    """Une vue de test : deux événements, par les deux sortes de loggers."""
    structlog.get_logger(LOGGER).info("premier événement de la requête")
    logging.getLogger(LOGGER).info("second événement de la requête")
    return HttpResponse()


# Les routes d'un test qui pose `ROOT_URLCONF` sur ce module.
urlpatterns = [path("journal/", journaling_view)]


@shared_task
def journaling_task() -> None:
    """Une tâche de test : un événement."""
    structlog.get_logger(LOGGER).info("événement de la tâche")


@pytest.fixture
def journal() -> Generator[Journal]:
    """Les événements journalisés pendant le test, rendus par le formateur que les réglages ont
    posé sur le logger racine — une ligne JSON chacun, `DEBUG` étant faux —, qu'emprunte un
    gestionnaire de plus, retiré après le test."""
    root = logging.getLogger()
    [configured] = [
        handler
        for handler in root.handlers
        if isinstance(handler.formatter, structlog.stdlib.ProcessorFormatter)
    ]
    stream = io.StringIO()
    reader = logging.StreamHandler(stream)
    reader.setFormatter(configured.formatter)
    root.addHandler(reader)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    root.removeHandler(reader)


def correlation_ids(events: list[dict[str, Any]]) -> list[str | None]:
    """L'identifiant de corrélation de chaque événement du logger de l'application, `None` pour
    celui qui n'en porte pas."""
    return [event.get(CORRELATION_ID) for event in events if event["logger"] == LOGGER]


@override_settings(ROOT_URLCONF=__name__)
def test_chaque_requete_porte_son_identifiant_de_correlation(
    client: Client, journal: Journal
) -> None:
    """Deux requêtes successives : un identifiant chacune, porté par tous ses événements ; aucun
    après elles — le contexte ne survit pas à la requête."""
    client.get("/journal/")
    client.get("/journal/")
    structlog.get_logger(LOGGER).info("hors de toute requête")

    ids = correlation_ids(journal())
    first, second = ids[0], ids[2]
    assert ids == [first, first, second, second, None]
    assert None not in (first, second)
    assert first != second


def test_chaque_tache_porte_son_identifiant_de_correlation(journal: Journal) -> None:
    """L'identifiant d'une exécution de tâche est celui de la tâche ; aucun après elle — le
    contexte ne passe pas d'une tâche à la suivante."""
    first = journaling_task.delay()
    second = journaling_task.delay()
    structlog.get_logger(LOGGER).info("hors de toute tâche")

    assert correlation_ids(journal()) == [first.id, second.id, None]
