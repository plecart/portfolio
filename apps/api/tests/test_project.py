"""Tests du projet Django : il démarre, ses réglages viennent de l'environnement, et ce que le
conteneur exige au démarrage est bien installé.

Toutes ces vérifications passent par un sous-processus lancé depuis `apps/api`, comme le ferait
un humain ou `gunicorn` : c'est le seul moyen d'éprouver `manage.py` et `config/wsgi.py`
eux-mêmes, et pas une reconstitution de ce qu'ils font.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from process_environment import NO_ENV_FILE

API_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = API_ROOT.parent.parent

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
    "'WSGI_APPLICATION': settings.WSGI_APPLICATION}))"
)


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
]


def run_python(arguments: list[str], variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Exécute `python <arguments>` depuis `apps/api`, dans un environnement valide, sans lire le
    `.env` du poste — celui du développeur, qui ne regarde pas ces tests."""
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=API_ROOT,
        env={**os.environ, "ENV_FILE": str(NO_ENV_FILE), **variables},
        capture_output=True,
        text=True,
        check=False,
    )


def test_le_projet_django_demarre(variables: dict[str, str]) -> None:
    result = run_python(["manage.py", "check"], variables)

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
