"""Tests du projet Django : il démarre, ses réglages viennent de l'environnement, ce que le
conteneur exige au démarrage est bien installé, et son application Celery trouve son broker —
puis s'exécute de façon synchrone dans la suite.

Le démarrage s'éprouve par un sous-processus lancé depuis `apps/api`, comme le ferait un humain
ou `gunicorn` : c'est le seul moyen d'éprouver `manage.py` et `config/wsgi.py` eux-mêmes, et pas
une reconstitution de ce qu'ils font.
"""

import ast
import json
import os
import re
import subprocess
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest
from celery import shared_task
from process_environment import NO_ENV_FILE

API_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = API_ROOT.parent.parent
TESTS_ROOT = API_ROOT / "tests"
# Les dossiers que `.dockerignore` écarte à toute profondeur (`**/…/`) et qui peuvent contenir du
# Python : un fichier du poste rangé là n'entre jamais dans l'image.
UNSHIPPED_DIRECTORIES = {".venv", "node_modules"}

# Lit les réglages Django résolus et les imprime en JSON. Passer par un sous-processus est
# nécessaire : `config.settings` s'évalue à l'import, une fois par processus.
SETTINGS_DUMP = (
    "import json, os;"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
    "from django.conf import settings;"
    "print(json.dumps({"
    "'SECRET_KEY': settings.SECRET_KEY,"
    "'DEBUG': settings.DEBUG,"
    "'ALLOWED_HOSTS': list(settings.ALLOWED_HOSTS),"
    "'DATABASES': settings.DATABASES,"
    "'MEDIA_ROOT': str(settings.MEDIA_ROOT),"
    "'ROOT_URLCONF': settings.ROOT_URLCONF,"
    "'WSGI_APPLICATION': settings.WSGI_APPLICATION,"
    "'TIME_ZONE': settings.TIME_ZONE,"
    "'CORS_ALLOWED_ORIGINS': list(settings.CORS_ALLOWED_ORIGINS),"
    "'MIDDLEWARE': list(settings.MIDDLEWARE)}))"
)

# Résout l'adresse d'un fichier téléversé. Dans un processus neuf : `config.urls` s'évalue une
# fois, à l'import, avec le `DEBUG` du moment.
MEDIA_RESOLUTION = """
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.urls import Resolver404, resolve
try:
    resolve('/media/technologies/icone.svg')
except Resolver404:
    print('absent')
else:
    print('servi')
"""


# Les dépendances que le conteneur exige au démarrage et qu'aucun code du dépôt n'importe
# encore : le pilote que Django charge à sa première connexion — les migrations, au démarrage du
# conteneur — et le serveur WSGI, commande par défaut de l'image. Sans cette liste, leur
# absence ne se verrait qu'au lancement du conteneur, loin du fichier qui l'a causée.
#
# Toute dépendance exigée à l'exécution mais importée par aucun module du dépôt s'ajoute ici.
STARTUP_IMPORTS = [
    (
        "pilote Postgres (ADR 0005)",
        "from django.db.backends.postgresql.base import DatabaseWrapper",
    ),
    ("serveur WSGI (ADR 0001)", "import gunicorn"),
    ("client Redis du broker (ADR 0015)", "import redis"),
]

# Le broker de l'application Celery que le démarrage de Django rend courante — celle qu'une tâche
# déclarée par `shared_task` emprunte pour s'enfiler depuis `api`. Dans un processus neuf, comme
# `gunicorn` le démarre.
CELERY_BROKER = """
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from celery import current_app
print(current_app.conf.broker_url)
print(current_app.conf.result_backend)
"""


def run_python(arguments: list[str], variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Exécute `python <arguments>` depuis `apps/api`, comme un humain ou `gunicorn` le lancent.

    Dans un environnement valide, sans le `.env` du poste — celui du développeur, qui ne regarde
    pas ces tests — ni le `DJANGO_SETTINGS_MODULE` du processus de test : `manage.py` et
    `config/wsgi.py` doivent le poser eux-mêmes, comme au démarrage du conteneur, où rien d'autre
    ne le pose.
    """
    inherited = {
        name: value for name, value in os.environ.items() if name != "DJANGO_SETTINGS_MODULE"
    }
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=API_ROOT,
        env={**inherited, "ENV_FILE": str(NO_ENV_FILE), **variables},
        capture_output=True,
        text=True,
        check=False,
    )


def test_le_projet_django_demarre(variables: dict[str, str]) -> None:
    """Sans avertissement : `check` seul ne refuse que les erreurs, et un réglage que l'admin
    attend — le processeur de contexte `request` (`admin.W411`) — manquerait en silence."""
    result = run_python(["manage.py", "check", "--fail-level", "WARNING"], variables)

    assert result.returncode == 0, result.stderr


def test_le_point_d_entree_wsgi_se_charge(variables: dict[str, str]) -> None:
    """C'est l'objet que `gunicorn` importera en production (ADR 0001)."""
    result = run_python(["-c", "from config.wsgi import application"], variables)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "statement",
    [statement for _, statement in STARTUP_IMPORTS],
    ids=[name for name, _ in STARTUP_IMPORTS],
)
def test_une_dependance_de_demarrage_est_installee(
    variables: dict[str, str], statement: str
) -> None:
    """Le démarrage du conteneur exige ces paquets ; rien d'autre dans le dépôt ne les importe.

    Le pilote se prouve par la classe de connexion de Django, pas par `import psycopg` :
    c'est ce chemin-là que `migrate` emprunte, et lui seul qui vérifie que Django sait s'en
    servir. `gunicorn` se prouve par sa seule présence — qu'il **tourne** se démontre sur
    Linux, au démarrage de l'image (le module qui ouvre le serveur importe `fcntl`, absent de
    Windows).
    """
    result = run_python(["-c", statement], variables)

    assert result.returncode == 0, result.stderr


def test_les_reglages_django_viennent_de_l_environnement(variables: dict[str, str]) -> None:
    """Le cœur de l'issue : chaque réglage vient d'`Env`, aucune valeur n'est écrite en dur.

    `manage.py check` ne regarde que la cohérence de Django, jamais la provenance des valeurs :
    des réglages entièrement codés en dur lui conviennent. Ce test compare donc les constantes
    résolues à l'environnement qui les a produites, ligne par ligne.
    """
    result = run_python(["-c", SETTINGS_DUMP], variables)
    assert result.returncode == 0, result.stderr

    settings = json.loads(result.stdout)

    assert settings["SECRET_KEY"] == variables["SECRET_KEY"]
    assert settings["DEBUG"] is False
    assert settings["ALLOWED_HOSTS"] == json.loads(variables["ALLOWED_HOSTS"])
    assert settings["DATABASES"]["default"] == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "portfolio",
        "USER": "portfolio",
        "PASSWORD": "secret",
        "HOST": "base.invalid",
        "PORT": 5432,
    }
    # Django pose `MEDIA_ROOT = ''` par défaut (`django.conf.global_settings`) : sans câblage,
    # ce réglage existe et vaut la chaîne vide. C'est pourquoi le test compare à la valeur
    # attendue plutôt que de vérifier la présence du réglage, qui serait toujours vraie.
    assert settings["MEDIA_ROOT"] == str(REPOSITORY_ROOT / variables["MEDIA_ROOT"])
    # Produit de l'arbitrage ASGI/WSGI consigné au journal de spec de #2 : sans cette ligne,
    # l'arbitrage ne serait garanti par rien.
    assert settings["WSGI_APPLICATION"] == "config.wsgi.application"
    assert settings["ROOT_URLCONF"] == "config.urls"
    # Produits de la décision 8 du brief de #7, que rien d'autre ne garde : retirés, ils ne
    # faisaient rougir aucun test (mesuré à la relecture). Le défaut de Django est
    # `America/Chicago`, et l'admin se protège seul du CSRF — le middleware couvre le reste.
    assert settings["TIME_ZONE"] == "Europe/Paris"
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings["MIDDLEWARE"]
    assert settings["CORS_ALLOWED_ORIGINS"] == json.loads(variables["CORS_ALLOWED_ORIGINS"])


@pytest.mark.parametrize(
    ("debug", "outcome"),
    [("true", "servi"), ("false", "absent")],
    ids=["développement", "production"],
)
def test_les_medias_ne_sont_servis_par_django_qu_en_developpement(
    variables: dict[str, str], debug: str, outcome: str
) -> None:
    """En production, les fichiers vivent sur R2 (ADR 0004), et la vue de Django qui les sert est
    réservée au développement (`django/views/static.py` : « SHOULD NOT be used in a production
    setting »)."""
    result = run_python(["-c", MEDIA_RESOLUTION], variables | {"DEBUG": debug})

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == outcome


@pytest.mark.parametrize(
    "redis_url",
    ["redis://cache.invalid:6379/0", "redis://autre.invalid:6380/1"],
    ids=["environnement de test", "autre adresse"],
)
def test_le_demarrage_de_django_charge_l_application_celery_et_son_broker(
    variables: dict[str, str], redis_url: str
) -> None:
    """Le broker vient d'`Env` (`REDIS_URL`, ADR 0015), par les réglages et leur espace de noms
    `CELERY_` — deux adresses, qu'aucune valeur écrite en dur ne satisfait ensemble ; et
    l'application est chargée au démarrage de Django, sans quoi une tâche enfilée par `api`
    partirait vers le broker par défaut de Celery. Aucun backend de résultats : l'état d'un
    traitement vit en base, Redis ne transporte que les messages (ADR 0015)."""
    result = run_python(["-c", CELERY_BROKER], variables | {"REDIS_URL": redis_url})

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [redis_url, "None"]


def test_la_commande_du_worker_trouve_l_application_et_ses_reglages(
    variables: dict[str, str],
) -> None:
    """`celery -A config …` — la commande du conteneur `worker` — ne passe ni par `manage.py` ni
    par `config/wsgi.py` : rien d'autre que l'application ne lui désigne les réglages Django.
    `report` imprime la configuration — sous les noms des réglages Django dont elle vient — sans
    joindre le broker."""
    result = run_python(["-m", "celery", "-A", "config", "report"], variables)

    assert result.returncode == 0, result.stderr
    assert f"CELERY_BROKER_URL: {variables['REDIS_URL']!r}" in result.stdout


# Les tâches que le worker connaît à son démarrage, dans un processus neuf : il importe
# l'application comme `celery -A config worker`, puis ses modules par défaut, comme le worker
# avant de consommer (`loader.import_default_modules`, qui déclenche `autodiscover_tasks`).
WORKER_TASKS = """
from config.celery import app
app.loader.import_default_modules()
print(sorted(name for name in app.tasks if not name.startswith('celery.')))
"""


def test_le_worker_connait_la_tache_des_images(variables: dict[str, str]) -> None:
    """Sans la découverte des modules `tasks`, le worker rejetterait comme inconnu chaque message
    que `api` enfile — et la suite, qui importe la tâche elle-même, ne le verrait pas."""
    result = run_python(["-c", WORKER_TASKS], variables)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['content.tasks.process_image']"


@shared_task
def doubled(value: int) -> int:
    """Une tâche de test : le double de `value`."""
    return 2 * value


@shared_task
def failing() -> None:
    """Une tâche de test qui échoue toujours."""
    raise RuntimeError("échec de la tâche")


def test_une_tache_s_execute_de_facon_synchrone_dans_la_suite() -> None:
    """Le harnais de test met l'application en mode synchrone (`conftest.py`, ADR 0015) : la suite
    n'a besoin d'aucun Redis — le broker du processus de test, `cache.invalid`, ne se résout
    nulle part (`process_environment.py`)."""
    assert doubled.delay(21).get() == 42


def test_l_exception_d_une_tache_sort_de_l_enfilement_dans_la_suite() -> None:
    """Sans propagation, le mode synchrone garderait l'exception dans le résultat, et un test
    d'échec verrait l'enfilement réussir."""
    with pytest.raises(RuntimeError, match="échec de la tâche"):
        failing.delay()


def production_sources() -> list[Path]:
    """Les fichiers Python que l'image embarque : `apps/api` entier, sans ses tests ni les
    dossiers du poste (`infra/api/Dockerfile`, `.dockerignore`) — `manage.py` compris, que le
    conteneur lance à chaque démarrage."""
    return [
        source
        for source in API_ROOT.rglob("*.py")
        if not source.is_relative_to(TESTS_ROOT)
        and not UNSHIPPED_DIRECTORIES & set(source.relative_to(API_ROOT).parts)
    ]


def imported_modules(source: Path) -> set[str]:
    """Les modules de premier niveau qu'un fichier importe, lus par l'analyseur de Python.

    Seuls les imports absolus comptent : un import relatif reste dans son paquet.
    """
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.partition(".")[0])
    return modules


def canonical(distribution: str) -> str:
    """Le nom normalisé d'une distribution (PEP 503) : `Django_Stubs.Ext` et `django-stubs-ext`
    désignent le même paquet."""
    return re.sub(r"[-_.]+", "-", distribution).lower()


def runtime_distributions() -> set[str]:
    """Ce que l'image installe — `uv sync --locked --no-dev` —, lu dans le verrou par `uv`."""
    # ponytail: marqueurs d'environnement ignorés — `tzdata ; sys_platform == 'win32'` compte comme
    # installé dans l'image Linux. Sans effet tant qu'aucun import de production ne vise une
    # distribution à marqueur ; sinon, les évaluer par `packaging.markers`, à déclarer en dev.
    export = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--package", "api", "--no-hashes"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {
        canonical(re.split(r"[=\[ ;]", line, maxsplit=1)[0])
        for line in export.splitlines()
        if line and not line.startswith(("#", " ", "-e"))
    }


def test_chaque_import_du_code_de_production_est_une_dependance_d_execution() -> None:
    """Un paquet importé par le code de production doit être installé par l'image.

    L'image s'installe sans les dépendances de développement : un paquet que le code importe
    mais que le verrou range en `dev` laisse l'image se construire, puis fait tomber le conteneur
    au démarrage — `migrate` charge les réglages. Aucune autre porte ne le voit : les tests
    tournent avec les dépendances de développement. Mesuré à la relecture sur `django-stubs-ext`.
    """
    sources = production_sources()
    first_party = {source.relative_to(API_ROOT).parts[0].removesuffix(".py") for source in sources}
    distributions = packages_distributions()
    runtime = runtime_distributions()

    third_party = {
        module
        for source in sources
        for module in imported_modules(source)
        if module not in sys.stdlib_module_names and module not in first_party
    }
    missing = {
        module: distributions.get(module, [])
        for module in third_party
        if not {canonical(name) for name in distributions.get(module, [])} & runtime
    }

    assert third_party, "aucun import tiers trouvé — la lecture des sources a-t-elle changé ?"
    assert not missing, f"importés en production, absents de l'image : {missing}"
