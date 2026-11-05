"""L'observabilité du back : la journalisation structurée de `api` et de `worker` (ADR 0027).

Un seul point de configuration, `configure_logging`, appelé par les réglages Django
(`config/settings.py`) : `api` les charge au démarrage de Django, `worker` par l'application
Celery, qui les lit (`config_from_object`, `config/celery.py`). Django n'y ajoute rien
(`LOGGING_CONFIG = None`), et le worker non plus (`connect_worker_signals`).

Chaque événement — d'un logger `structlog` comme d'un logger standard : Django, Celery,
`django_redis`, l'application — passe par le même formateur, `structlog.stdlib.ProcessorFormatter`,
posé sur l'unique gestionnaire du logger racine (doc structlog, « Standard Library Logging »,
« Rendering using structlog-based formatters within logging ») : aucun ne sort sous deux formats.
Le code de l'application journalise par `structlog.get_logger(__name__)` ou
`logging.getLogger(__name__)`, sans rien configurer.

Hors de ce rendu : les lignes de `gunicorn` lui-même — démarrage, arrêt de ses workers —, qu'il
écrit par ses propres gestionnaires, sans les transmettre au logger racine (`propagate = False`,
`gunicorn/glogging.py`).
"""

import logging

import structlog
from celery.signals import setup_logging
from structlog.typing import Processor

# Ce que chaque événement porte, qu'il vienne de `structlog` ou d'un logger standard : le contexte
# lié au fil d'exécution (`structlog.contextvars`), le nom du logger, le niveau et l'heure UTC.
SHARED_PROCESSORS: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]

# Le rendu de chaque mode. La trace d'une exception est le texte de `traceback`, jamais ses
# variables locales — qui peuvent porter une donnée personnelle : `format_exc_info` en JSON, et non
# `dict_tracebacks`, dont chaque cadre porte ses `locals` (doc structlog, API, `dict_tracebacks`) ;
# `plain_traceback` en console, et non le rendu de Rich, que `ConsoleRenderer` choisit dès que Rich
# est installé (doc structlog, API, `ConsoleRenderer`) — il l'est sur le poste, par `pip-audit` —
# et qui les affiche (`RichTracebackFormatter.show_locals`, vrai par défaut, `structlog/dev.py`).
JSON_RENDERING: list[Processor] = [
    structlog.processors.format_exc_info,
    structlog.processors.JSONRenderer(),
]
CONSOLE_RENDERING: list[Processor] = [
    structlog.dev.ConsoleRenderer(exception_formatter=structlog.dev.plain_traceback),
]


def configure_logging(debug: bool) -> None:
    """Pose la journalisation du processus : une ligne JSON par événement en production, un rendu
    lisible en développement.

    Le logger racine reçoit un seul gestionnaire, vers la sortie d'erreur, et le niveau `INFO` ;
    tout logger sans gestionnaire à lui — ceux de Django, de Celery, des bibliothèques, de
    l'application — lui transmet ses événements. `structlog` est configuré pour passer par lui :
    ses événements prennent le même rendu que ceux des loggers standard.

    Idempotente : rejouée, elle remplace le gestionnaire du logger racine — et tout autre posé
    avant elle — au lieu d'en ajouter un.

    Args:
        debug: le `DEBUG` des réglages — vrai, le rendu lisible ; faux, le JSON.
    """
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *(CONSOLE_RENDERING if debug else JSON_RENDERING),
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    structlog.configure(
        processors=[*SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def keep_logging(**_: object) -> None:
    """Récepteur du signal `setup_logging` de Celery : ne fait rien, et c'est son rôle.

    Celery ne configure pas la journalisation dès qu'un récepteur répond à ce signal (doc Celery,
    « Signals », `setup_logging` : « Celery won't configure the loggers if this signal is
    connected ») ; sans lui, le worker remplacerait le gestionnaire du logger racine par le sien
    (`worker_hijack_root_logger`) et détournerait la sortie standard vers ses loggers. La
    journalisation reste celle des réglages, que le worker a chargés.
    """


def connect_worker_signals() -> None:
    """Branche le worker sur l'observabilité : la journalisation des réglages gardée
    (`keep_logging`).

    Appelée par `config/celery.py`, que `celery -A config worker` importe avant de configurer quoi
    que ce soit. Rejouée, elle ne branche rien de plus : un signal Celery ne tient qu'une fois un
    même récepteur.
    """
    setup_logging.connect(keep_logging)
