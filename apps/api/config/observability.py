"""L'observabilité du back : la journalisation structurée de `api` et de `worker`, l'identifiant de
corrélation de chaque requête et de chaque exécution de tâche, et la remontée de leurs erreurs à
Sentry (ADR 0027).

Un seul point de configuration, `configure_logging`, appelé par les réglages Django
(`config/settings.py`) : `api` les charge au démarrage de Django, `worker` par l'application
Celery, qui les lit (`config_from_object`, `config/celery.py`). Django n'y ajoute rien
(`LOGGING_CONFIG = None`), et le worker non plus (`connect_worker_signals`).

Chaque événement — d'un logger `structlog` comme d'un logger standard : Django, Celery,
`django_redis`, l'application — passe par le même formateur, `structlog.stdlib.ProcessorFormatter`,
posé sur l'unique gestionnaire du logger racine (doc structlog, « Standard Library Logging »,
« Rendering using structlog-based formatters within logging ») : aucun ne sort sous deux formats.
Le code de l'application journalise par `structlog.get_logger(__name__)` ou
`logging.getLogger(__name__)`, sans rien configurer. Une exception part à Sentry avec sa trace par
`exception()` ; à un logger `structlog`, `exc_info=True` ne la transmet pas : il reste une paire du
dictionnaire de l'événement, que `wrap_for_formatter` ne passe pas au `LogRecord`
(`structlog/stdlib.py`) — mesuré au transport factice le 2026-11-05.

Hors de ce rendu : les lignes de `gunicorn` lui-même — démarrage, arrêt de ses workers —, qu'il
écrit par ses propres gestionnaires, sans les transmettre au logger racine (`propagate = False`,
`gunicorn/glogging.py`).

L'identifiant de corrélation est lié au contexte de journal (`structlog.contextvars`) le temps
d'une requête (`correlation_middleware`) ou d'une exécution de tâche (`bind_task_id`) : chaque
événement émis pendant ce temps le porte, sous la clé `CORRELATION_ID` — et l'événement Sentry
capturé pendant ce temps aussi, en tag (`tag_correlation_id`).

Sentry s'initialise, lui aussi, depuis les réglages (`init_sentry`), et seulement si `SENTRY_DSN`
est posé.
"""

import logging
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import sentry_sdk
import structlog
from celery.signals import setup_logging, task_postrun, task_prerun
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from structlog.typing import Processor

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest
    from django.http.response import HttpResponseBase
    from pydantic import SecretStr
    from sentry_sdk.transport import Transport
    from sentry_sdk.types import Breadcrumb, BreadcrumbHint, Event, Hint

# La clé de l'identifiant de corrélation dans le contexte de journal.
CORRELATION_ID = "correlation_id"

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


def init_sentry(dsn: "SecretStr", debug: bool, transport: "Transport | None" = None) -> None:
    """Initialise Sentry pour les erreurs du processus — ou rien, sans DSN.

    DSN vide — le poste, les tests, la CI, les piles jetables : `sentry_sdk.init` n'est pas appelé,
    et rien ne part. Sinon, trois intégrations remontent les erreurs : Django, les exceptions non
    gérées de l'API ; Celery, les échecs de tâches ; `logging`, tout événement de niveau `ERROR`
    d'un logger. Un échec de tâche aux réessais épuisés n'en fait qu'un : un réessai (`Retry`)
    n'est pas une erreur, et la ligne d'erreur que Celery journalise ensuite, trace comprise
    (`celery.app.trace`), n'en fait pas un second, par deux voies dont chacune suffit :
    l'intégration Celery écarte ce logger (`ignore_logger`, `sentry_sdk/integrations/celery`), et
    l'intégration par défaut `DedupeIntegration` écarte une exception déjà capturée. Mesuré au
    transport factice le 2026-11-05, sentry-sdk 2.74.0 : un événement sans l'une, comme sans
    l'autre ; deux sans les deux. Il en va de même de la ligne de `django.request` pour l'exception
    d'une vue, que l'intégration Django reçoit par le signal `got_request_exception`.

    Erreurs seulement : ni `traces_sample_rate`, ni profilage. Aucune donnée personnelle de
    Sentry lui-même — ni utilisateur, ni cookie, ni adresse IP : `send_default_pii` reste faux,
    laissé à son défaut. Le passer, même à faux, émet un `DeprecationWarning` en 2.74.0
    (`_get_options`, `sentry_sdk/client.py`) ; absent, il vaut faux à chacune des quatre lectures
    que le SDK en fait (`client.py` : l'avertissement, le nettoyeur d'événements,
    `should_send_default_pii` ; `data_collection.py` : `_resolve_data_collection`). Ce défaut
    laisse passer trois choses, coupées ici : les variables locales des cadres d'une trace — celles
    d'une vue de l'admin peuvent tenir l'auteur (`include_local_variables`) ; le corps de la
    requête, envoyé quel que soit `send_default_pii` jusqu'à `max_request_body_size`
    (`RequestExtractor.extract_into_event`, `sentry_sdk/integrations/_wsgi_common.py`) ; et les
    en-têtes de la requête qu'il ne sait pas sensibles (`without_request_headers`). Un événement
    `structlog` ne part à Sentry que sous son message, en événement comme en fil d'Ariane
    (`structlog_message`). Chaque événement porte l'identifiant de corrélation en tag
    (`tag_correlation_id`).

    Rejouée avec un DSN, elle remplace le client ; les intégrations, elles, s'installent une fois
    par processus (`Integration.setup_once`) et restent sans effet sans client actif.

    Args:
        dsn: le `SENTRY_DSN` d'`Env`.
        debug: le `DEBUG` des réglages, d'où l'environnement Sentry : `development` s'il est vrai,
            `production` sinon.
        transport: ce par quoi partent les événements ; par défaut, celui de Sentry, en HTTP. Les
            tests en passent un factice, qui n'envoie rien.
    """
    if not dsn.get_secret_value():
        return
    sentry_sdk.init(
        dsn=dsn.get_secret_value(),
        environment="development" if debug else "production",
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            LoggingIntegration(event_level=logging.ERROR),
        ],
        include_local_variables=False,
        max_request_body_size="never",
        before_send=before_send,
        before_breadcrumb=before_breadcrumb,
        transport=transport,
    )


def before_send(event: "Event", hint: "Hint") -> "Event":
    """Crochet `before_send` de Sentry : chaque événement part sans les en-têtes de sa requête
    (`without_request_headers`), sous le seul message d'un événement `structlog`
    (`structlog_message`), et avec son identifiant de corrélation (`tag_correlation_id`).

    Sentry l'appelle dans le fil qui capture l'événement, avant de le confier à l'envoi en
    arrière-plan (`_prepare_event`, `sentry_sdk/client.py`) : le contexte y est encore celui de la
    requête ou de la tâche.

    Args:
        event: l'événement, tel que Sentry s'apprête à l'envoyer.
        hint: ce que Sentry joint à l'événement — celui d'un logger, son `LogRecord`.

    Returns:
        L'événement, jamais écarté.
    """
    message = structlog_message(hint)
    if message is not None:
        event["logentry"] = {"message": message, "formatted": message}
    return tag_correlation_id(without_request_headers(event))


def before_breadcrumb(crumb: "Breadcrumb", hint: "BreadcrumbHint") -> "Breadcrumb":
    """Crochet `before_breadcrumb` de Sentry : le fil d'Ariane d'un événement `structlog` ne garde
    que son message (`structlog_message`).

    Args:
        crumb: l'élément du fil d'Ariane, tel que Sentry s'apprête à l'ajouter.
        hint: ce que Sentry joint à l'élément — celui d'un logger, son `LogRecord`.

    Returns:
        L'élément, jamais écarté.
    """
    message = structlog_message(hint)
    if message is not None:
        crumb["message"] = message
    return crumb


def structlog_message(hint: "Hint") -> str | None:
    """Le message d'un événement `structlog` — la seule chaîne `event` de son dictionnaire —, ou
    `None` pour ce qui n'en vient pas.

    `wrap_for_formatter` passe ce dictionnaire entier, paires clé-valeur et horodatage compris, pour
    `msg` du `LogRecord` (`structlog/stdlib.py`), et l'intégration `logging` de Sentry en tire le
    message de l'événement comme celui du fil d'Ariane, avant de joindre le `LogRecord` au crochet
    (`hint["log_record"]`, `sentry_sdk/integrations/logging.py`) : les deux crochets y substituent
    ce message, sans quoi chaque paire partirait chez Sentry. Le `LogRecord` d'un événement
    `structlog` se reconnaît à l'attribut `_logger` que `wrap_for_formatter` y pose : un logger
    standard qui journalise un dictionnaire garde son message.

    Args:
        hint: ce que Sentry joint à un événement ou à un élément du fil d'Ariane.
    """
    record: object = hint.get("log_record")
    event_dict: object = getattr(record, "msg", None)
    if not hasattr(record, "_logger") or not isinstance(event_dict, dict):
        return None
    return str(cast("dict[str, object]", event_dict).get("event"))


def without_request_headers(event: "Event") -> "Event":
    """Retire de `event` tous les en-têtes de sa requête.

    Sentry ne masque que ceux qu'il sait sensibles — `Authorization`, `Cookie`, `X-Forwarded-For`,
    `X-Real-Ip`… (`SENSITIVE_ENV_KEYS`, `sentry_sdk/integrations/_wsgi_common.py`) — et laisse
    passer ceux que la chaîne de production ajoute : `CF-Connecting-IP`, l'adresse du visiteur que
    Cloudflare transmet à l'origine (doc Cloudflare, « HTTP request headers »), et
    `Cf-Access-Jwt-Assertion`, le jeton signé qu'Access joint à chaque requête de l'admin (doc
    Cloudflare, « Validate JWTs »). Une liste de refus ne suit pas ce qu'un relais ajoute : aucun
    en-tête ne part.

    Args:
        event: l'événement, sérialisé ; un événement hors requête n'a pas d'en-têtes.

    Returns:
        `event`, modifié en place.
    """
    event.get("request", {}).pop("headers", None)
    return event


def tag_correlation_id(event: "Event") -> "Event":
    """Pose en tag de `event` l'identifiant de corrélation lié au contexte de journal — celui de la
    requête ou de la tâche en cours —, sous la même clé ; hors de l'une comme de l'autre,
    l'événement n'a pas ce tag.

    Args:
        event: l'événement, capturé dans le fil de la requête ou de la tâche.

    Returns:
        `event`, modifié en place.
    """
    correlation_id = structlog.contextvars.get_contextvars().get(CORRELATION_ID)
    if correlation_id is not None:
        event.setdefault("tags", {})[CORRELATION_ID] = correlation_id
    return event


def correlation_middleware(
    get_response: "Callable[[HttpRequest], HttpResponseBase]",
) -> "Callable[[HttpRequest], HttpResponseBase]":
    """Middleware Django : un identifiant de corrélation neuf par requête HTTP, lié au contexte de
    journal le temps de la requête.

    L'identifiant est engendré ici (`uuid4`), jamais lu dans la requête : un en-tête que le client
    envoie n'est pas une donnée de confiance. À la sortie, le contexte retrouve son état d'avant
    (`structlog.contextvars.bound_contextvars`) : rien ne passe à la requête suivante. Placé en
    tête de `MIDDLEWARE` (`config/settings.py`).

    Args:
        get_response: la suite de la chaîne des middlewares.

    Returns:
        Le middleware : il rend la réponse de `get_response`.
    """

    def middleware(request: "HttpRequest") -> "HttpResponseBase":
        with structlog.contextvars.bound_contextvars(**{CORRELATION_ID: str(uuid4())}):
            return get_response(request)

    return middleware


def bind_task_id(task_id: str, **_: object) -> None:
    """Récepteur du signal `task_prerun` de Celery : l'identifiant de la tâche qui démarre devient
    l'identifiant de corrélation de son exécution.

    Args:
        task_id: l'identifiant de la tâche, que Celery passe à ce signal (doc Celery, « Signals »,
            `task_prerun`).
    """
    structlog.contextvars.bind_contextvars(**{CORRELATION_ID: task_id})


def unbind_task_id(**_: object) -> None:
    """Récepteur du signal `task_postrun` de Celery : délie l'identifiant de la tâche qui finit —
    réussie ou en échec, Celery envoie ce signal dans un `finally` (`celery/app/trace.py`) —, et la
    suivante ne l'hérite pas."""
    # ponytail: délie au lieu de restaurer — une tâche exécutée dans une requête, ce que seul le
    # mode synchrone des tests fait, retire à la fin de cette requête son identifiant ; restaurer
    # l'état d'avant par les jetons de `bind_contextvars` si une tâche doit un jour s'exécuter dans
    # le processus de l'API.
    structlog.contextvars.unbind_contextvars(CORRELATION_ID)


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
    (`keep_logging`), l'identifiant de chaque tâche lié le temps de son exécution (`bind_task_id`,
    `unbind_task_id`).

    Appelée par `config/celery.py`, que `celery -A config worker` importe avant de configurer quoi
    que ce soit. Rejouée, elle ne branche rien de plus : un signal Celery ne tient qu'une fois un
    même récepteur.
    """
    setup_logging.connect(keep_logging)
    task_prerun.connect(bind_task_id)
    task_postrun.connect(unbind_task_id)
