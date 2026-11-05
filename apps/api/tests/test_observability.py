"""Tests de l'observabilité du back (ADR 0027) : un seul rendu des journaux, une ligne JSON par
événement en production et un rendu lisible en développement, pour les loggers de l'application
comme pour ceux des bibliothèques ; une configuration posée une fois, que le worker garde ; un
identifiant de corrélation par requête HTTP et par exécution de tâche ; les erreurs remontées à
Sentry, et rien sans DSN ; rien de personnel, ni dans Sentry ni dans les journaux.

La configuration se pose à l'import des réglages, une fois par processus : elle s'éprouve par un
sous-processus neuf, comme `gunicorn` ou `celery -A config worker` le démarrent
(`test_django_project.run_python`). Le reste s'éprouve dans le processus de test, sur le rendu que
ses réglages y ont posé (`journal`), et sur un Sentry initialisé le temps d'un test, que son
transport factice empêche de rien envoyer (`sent`).
"""

import io
import json
import logging
import subprocess
from collections.abc import Callable, Generator
from typing import Any, cast

import pytest
import sentry_sdk
import structlog
from celery import shared_task
from config.observability import CORRELATION_ID, init_sentry
from content.tasks import process_image
from django.conf import settings
from django.contrib.auth.models import User
from django.core.handlers.wsgi import WSGIHandler, WSGIRequest
from django.core.signals import request_started
from django.db import close_old_connections
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from factories import gallery_image, project, saved
from pydantic import SecretStr
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from test_cache import make_unreadable
from test_django_project import run_python
from test_env import SENTRY_ENVIRONMENT

# Le démarrage de Django, dans un processus neuf.
STARTED = """
import logging, os, django, structlog
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
"""

# Un événement de chaque sorte de logger — l'appel qui le crée, le logger, le niveau, le message :
# celui de l'application, par `structlog` ; un logger de Django, dont la configuration par défaut
# ajouterait son propre rendu en développement ; les deux loggers de bibliothèque qui portent un
# incident : Redis injoignable (#11), un rappel `on_commit(robust=True)` en échec.
EVENTS = [
    ("structlog.get_logger", "content", "info", "un événement de l'application"),
    ("logging.getLogger", "django.request", "warning", "Not Found: /absent/"),
    ("logging.getLogger", "django_redis.cache", "error", "Exception ignored"),
    ("logging.getLogger", "django.db.backends.base", "error", "Error calling in on_commit()"),
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


@csrf_exempt
def failing_view(request: HttpRequest) -> HttpResponse:
    """Une vue de test qui échoue pour l'auteur connecté, qu'une variable locale tient — comme le
    code de l'admin tient la requête et ce qu'elle édite. Exemptée du contrôle CSRF, que la requête
    de test ne porte pas : ce n'est pas ce qu'elle éprouve."""
    author = request.user
    if author.is_authenticated:
        raise RuntimeError("panne de la vue")
    return HttpResponse()


# Les routes d'un test qui pose `ROOT_URLCONF` sur ce module.
urlpatterns = [path("journal/", journaling_view), path("panne/", failing_view)]


@shared_task
def journaling_task() -> None:
    """Une tâche de test : un événement."""
    structlog.get_logger(LOGGER).info("événement de la tâche")


@pytest.fixture(autouse=True)
def unbound_context() -> Generator[None]:
    """Aucun contexte de journal ne survit à un test, même interrompu au milieu d'une requête ou
    d'une tâche : le suivant part d'un contexte vide."""
    yield
    structlog.contextvars.clear_contextvars()


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


# Le DSN factice des tests d'`Env` : le transport factice n'envoie rien, et l'hôte ne se résout
# nulle part.
DSN = SecretStr(SENTRY_ENVIRONMENT["SENTRY_DSN"])

# Un événement tel que Sentry l'envoie : le JSON de l'enveloppe, déjà sérialisé.
SentEvent = dict[str, Any]


class RecordingTransport(Transport):
    """Un transport Sentry factice : il retient chaque enveloppe au lieu de l'envoyer, et ses
    événements à part."""

    def __init__(self) -> None:
        super().__init__()
        self.envelopes: list[Envelope] = []
        self.events: list[SentEvent] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)
        event = envelope.get_event()
        if event is not None:
            self.events.append(cast("SentEvent", event))


@pytest.fixture
def sentry_isolated() -> Generator[None]:
    """Le test dans sa propre portée Sentry, puis le client remis à zéro : rien de ce qu'il
    initialise ou enregistre ne passe au test suivant."""
    with sentry_sdk.isolation_scope():
        yield
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(None)


@pytest.fixture
def transport(sentry_isolated: None) -> RecordingTransport:
    """Le transport factice d'un Sentry initialisé le temps du test comme en production, sur le
    DSN de test."""
    transport = RecordingTransport()
    init_sentry(DSN, debug=False, transport=transport)
    return transport


@pytest.fixture
def sent(transport: RecordingTransport) -> list[SentEvent]:
    """Les événements que Sentry envoie pendant le test, retenus par le transport factice."""
    return transport.events


def exception_type(event: SentEvent) -> str:
    """Le type de l'exception que porte `event`, la dernière de sa chaîne."""
    return event["exception"]["values"][-1]["type"]


def test_sans_dsn_sentry_ne_s_initialise_pas(monkeypatch: pytest.MonkeyPatch) -> None:
    """DSN vide — le développement, les tests, la CI : `sentry_sdk.init` n'est jamais appelé, aucun
    client n'est actif, rien ne part. Le processus de test tourne lui-même ainsi
    (`process_environment`)."""
    calls: list[dict[str, object]] = []

    def recorded(**options: object) -> None:
        calls.append(options)

    monkeypatch.setattr(sentry_sdk, "init", recorded)

    init_sentry(SecretStr(""), debug=False)

    assert calls == []
    assert not sentry_sdk.is_initialized()


@pytest.mark.usefixtures("sentry_isolated")
@pytest.mark.parametrize(
    ("debug", "environment"),
    [(False, "production"), (True, "development")],
    ids=["production", "développement"],
)
def test_l_environnement_sentry_se_deduit_de_debug(debug: bool, environment: str) -> None:
    """Aucune variable de plus : `DEBUG` faux, c'est la production."""
    init_sentry(DSN, debug=debug, transport=RecordingTransport())

    assert sentry_sdk.get_client().options["environment"] == environment


@pytest.mark.django_db
@pytest.mark.usefixtures("unpropagated")
def test_un_echec_de_traitement_aux_reessais_epuises_envoie_un_seul_evenement(
    sent: list[SentEvent],
) -> None:
    """Un original illisible, quatre essais : les réessais ne sont pas des erreurs, et la ligne
    d'erreur que le worker journalise ensuite (`celery.app.trace`) n'en fait pas un second
    (`init_sentry`, deux voies dont chacune suffit). L'événement porte l'identifiant de la
    tâche."""
    image = saved(gallery_image(saved(project())))
    make_unreadable(image)

    result = process_image.delay(image.pk, image.original.name or "")

    assert result.state == "FAILURE"
    assert [(exception_type(event), event["tags"][CORRELATION_ID]) for event in sent] == [
        ("UnidentifiedImageError", result.id)
    ]


@pytest.mark.parametrize("logger", ["django_redis.cache", "django.db.backends.base"])
def test_un_evenement_d_erreur_d_un_logger_de_bibliotheque_envoie_un_evenement(
    sent: list[SentEvent], logger: str
) -> None:
    """Émis comme la bibliothèque l'émet — `logger.exception`, ou `logger.error` avec la trace,
    dans le `except` qui écarte l'erreur (`test_cache.py`, `test_tasks.py`) —, pendant une requête
    ou une tâche : un événement, qui porte l'identifiant de corrélation."""
    with structlog.contextvars.bound_contextvars(**{CORRELATION_ID: "identifiant-temoin"}):
        try:
            raise ConnectionError("Redis injoignable")
        except ConnectionError:
            logging.getLogger(logger).exception("Exception ignored")

    assert [(event["logger"], event["tags"][CORRELATION_ID]) for event in sent] == [
        (logger, "identifiant-temoin")
    ]


# Les voies par lesquelles l'intégration `logging` de Sentry peut faire partir le contenu d'un
# événement `structlog` — son message et ses paires clé-valeur, que `wrap_for_formatter` passe
# ensemble, en dictionnaire, pour `msg` du `LogRecord` (`structlog/stdlib.py`) —, recensées dans
# `sentry_sdk/integrations/logging.py`, 2.74.0 ; chacune, la méthode du logger qui l'emprunte, ce
# que le transport factice en reçoit, et ce qu'il doit en recevoir. L'événement d'un `ERROR`
# (`EventHandler`) : son `logentry` — `message`, `formatted`, `params` — et ses `extra`. Le fil
# d'Ariane de tout événement d'au moins `INFO` (`BreadcrumbHandler`), que porte l'événement
# suivant : son `message` et ses `data`. Sentry Logs (`SentryLogsHandler`) : coupé, `enable_logs`
# n'étant pas posé ; activé, il fait partir le dictionnaire en `body` — mesuré au transport
# factice le 2026-11-05.
STRUCTLOG_PATHS: dict[str, tuple[str, Callable[[RecordingTransport], object], object]] = {
    "evenement": (
        "error",
        lambda transport: [
            (event["logentry"], event["tags"][CORRELATION_ID])
            for event in transport.events
            if event.get("logger") == LOGGER
        ],
        [({"message": "boom", "formatted": "boom"}, "identifiant-temoin")],
    ),
    "fil-d-ariane": (
        "info",
        lambda transport: [
            (crumb["message"], crumb["data"])
            for event in transport.events
            for crumb in event.get("breadcrumbs", {}).get("values", [])
            if crumb["category"] == LOGGER
        ],
        [("boom", {})],
    ),
    "sentry-logs": (
        "info",
        lambda transport: [
            item.type for envelope in transport.envelopes for item in envelope if item.type == "log"
        ],
        [],
    ),
}


@pytest.mark.parametrize("path", STRUCTLOG_PATHS)
def test_un_evenement_structlog_ne_part_que_sous_son_message(
    transport: RecordingTransport, path: str
) -> None:
    """Un événement `structlog` à paire clé-valeur témoin, pendant une requête ou une tâche, puis
    un événement qui emporte le fil d'Ariane, et tout ce qui attend envoyé (`flush`) : la voie ne
    porte que le message, `event` — et le tag de corrélation, pour l'événement ; rien, pour Sentry
    Logs —, et le témoin n'est nulle part dans ce que reçoit le transport."""
    method, carried, expected = STRUCTLOG_PATHS[path]
    witness = f"TEMOIN-{path}"
    with structlog.contextvars.bound_contextvars(**{CORRELATION_ID: "identifiant-temoin"}):
        getattr(structlog.get_logger(LOGGER), method)("boom", secret=witness)
        sentry_sdk.capture_message("clôture")
    sentry_sdk.flush()

    assert carried(transport) == expected
    assert witness.encode() not in b"".join(
        envelope.serialize() for envelope in transport.envelopes
    )


def test_le_dictionnaire_d_un_logger_standard_garde_son_message(sent: list[SentEvent]) -> None:
    """Un logger standard qui journalise un dictionnaire n'est pas pris pour `structlog` : son
    événement garde le dictionnaire pour message, jamais `"None"` ni la seule clé `event`."""
    logging.getLogger(LOGGER).error({"code": 42, "event": "x"})

    assert [event["logentry"]["message"] for event in sent] == ["{'code': 42, 'event': 'x'}"]


# L'auteur, seul compte de l'admin, à des valeurs reconnaissables : son identifiant ne se confond
# avec aucun chiffre d'un événement ou d'une ligne de journal.
AUTHOR_ID = 1618033988
AUTHOR = "auteur-reconnaissable"
AUTHOR_EMAIL = "auteur-reconnaissable@exemple.test"

# Ce que porte sa requête, chaque valeur reconnaissable : l'adresse du relais qui la transmet et
# celle du visiteur, que Cloudflare passe à l'origine (`CF-Connecting-IP`) — deux plages réservées
# à la documentation (RFC 5737) —, le jeton qu'Access y joint (`Cf-Access-Jwt-Assertion`), un
# en-tête qui porte l'adresse de l'auteur, un en-tête d'autorisation et un corps.
RELAY_ADDRESS = "203.0.113.77"
VISITOR_ADDRESS = "198.51.100.23"
AUTHORIZATION = "Bearer jeton-reconnaissable"
ACCESS_TOKEN = "jwt-access-reconnaissable"
BODY = "corps-reconnaissable"


@pytest.fixture
def admin_user(django_user_model: type[User], db: None) -> User:
    """L'auteur, à ses valeurs reconnaissables — remplace la fixture de pytest-django, que
    `admin_client` (`conftest.py`) connecte et vérifie par un second facteur."""
    return django_user_model.objects.create_superuser(
        pk=AUTHOR_ID, username=AUTHOR, email=AUTHOR_EMAIL, password="phrase-de-passe-de-test"
    )


@pytest.fixture
def served() -> Generator[Callable[[WSGIRequest], str]]:
    """Sert une requête par un `WSGIHandler`, ce qu'est `config.wsgi.application`, l'objet que
    `gunicorn` appelle (`get_wsgi_application`) — et que l'intégration Django de Sentry enveloppe
    de son middleware WSGI, qui joint à l'événement les en-têtes de la requête et son adresse ; le
    client de test de Django n'y passe pas. Construit au test, et non à l'import du module : ses
    middlewares s'instancient alors, WhiteNoise compris, sur les fichiers statiques collectés.

    Sans la fermeture des connexions à la base que chaque requête déclenche
    (`close_old_connections`, au signal `request_started`) : elle romprait la transaction du test,
    ce que le client de test de Django évite de même (`ClientHandler`).

    Returns:
        Une fonction qui sert la requête et rend le statut de la réponse.
    """

    application = WSGIHandler()

    def serve(request: WSGIRequest) -> str:
        statuses: list[str] = []

        def start_response(
            status: str, headers: list[tuple[str, str]], exc_info: object = None
        ) -> Callable[[bytes], object]:
            statuses.append(status)
            return lambda _body: None

        application(request.environ, start_response)
        return statuses[0]

    request_started.disconnect(close_old_connections)
    yield serve
    request_started.connect(close_old_connections)


@override_settings(ROOT_URLCONF=__name__)
def test_rien_de_personnel_ne_part_d_une_requete_de_l_admin_en_erreur(
    admin_client: Client,
    served: Callable[[WSGIRequest], str],
    sent: list[SentEvent],
    journal: Journal,
) -> None:
    """Une requête de l'auteur connecté qui échoue, servie comme en production : un événement, qui
    porte l'identifiant de corrélation de ses lignes de journal, et rien de ce qui désigne l'auteur
    ou sa requête — ni son identifiant, son nom ou son adresse, ni l'adresse du relais ou du
    visiteur, ni le cookie de session, ni l'en-tête d'autorisation, ni le jeton d'Access, ni le
    corps —, dans l'événement comme dans les lignes de journal."""
    factory = RequestFactory()
    factory.cookies = admin_client.cookies
    request = factory.post(
        "/panne/",
        {"note": BODY},
        headers={
            "Authorization": AUTHORIZATION,
            "CF-Connecting-IP": VISITOR_ADDRESS,
            "Cf-Access-Jwt-Assertion": ACCESS_TOKEN,
            "Cf-Access-Authenticated-User-Email": AUTHOR_EMAIL,
        },
        REMOTE_ADDR=RELAY_ADDRESS,
    )

    status = served(request)

    session = admin_client.cookies[settings.SESSION_COOKIE_NAME].value
    identifying = [
        str(AUTHOR_ID),
        AUTHOR,
        AUTHOR_EMAIL,
        RELAY_ADDRESS,
        VISITOR_ADDRESS,
        session,
        AUTHORIZATION,
        ACCESS_TOKEN,
        BODY,
    ]
    [event] = sent
    [logged] = [line for line in journal() if line["logger"] == "django.request"]
    assert (status, exception_type(event), event["tags"][CORRELATION_ID]) == (
        "500 Internal Server Error",
        "RuntimeError",
        logged[CORRELATION_ID],
    )
    assert [value for value in identifying if value in json.dumps(sent)] == []
    assert [value for value in identifying if value in json.dumps(journal())] == []
