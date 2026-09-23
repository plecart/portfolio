"""Tests du projet Django : il démarre, et son point d'entrée de production se charge.

Ces deux vérifications passent par un sous-processus lancé depuis `apps/api`, comme le ferait
un humain ou `gunicorn` : c'est le seul moyen d'éprouver `manage.py` et `config/wsgi.py`
eux-mêmes, et pas une reconstitution de ce qu'ils font.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

RACINE_API = Path(__file__).resolve().parent.parent

# Lit les réglages Django résolus et les imprime en JSON. Passer par un sous-processus est
# nécessaire : `config.settings` s'évalue à l'import, une fois par processus.
LECTURE_DES_REGLAGES = (
    "import json, os;"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
    "from django.conf import settings;"
    "print(json.dumps({"
    "'SECRET_KEY': settings.SECRET_KEY,"
    "'DEBUG': settings.DEBUG,"
    "'ALLOWED_HOSTS': list(settings.ALLOWED_HOSTS),"
    "'DATABASES': settings.DATABASES,"
    "'ROOT_URLCONF': settings.ROOT_URLCONF,"
    "'WSGI_APPLICATION': settings.WSGI_APPLICATION}))"
)


def lancer(arguments: list[str], variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Exécute `python <arguments>` depuis `apps/api`, dans un environnement valide."""
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=RACINE_API,
        env={**os.environ, **variables},
        capture_output=True,
        text=True,
        check=False,
    )


def test_le_projet_django_demarre(variables: dict[str, str]) -> None:
    resultat = lancer(["manage.py", "check"], variables)

    assert resultat.returncode == 0, resultat.stderr


def test_le_point_d_entree_wsgi_se_charge(variables: dict[str, str]) -> None:
    """C'est l'objet que `gunicorn` importera en production (ADR 0001)."""
    resultat = lancer(["-c", "from config.wsgi import application"], variables)

    assert resultat.returncode == 0, resultat.stderr


def test_les_reglages_django_viennent_de_l_environnement(variables: dict[str, str]) -> None:
    """Le cœur de l'issue : chaque réglage vient d'`Env`, aucune valeur n'est écrite en dur.

    `manage.py check` ne regarde que la cohérence de Django, jamais la provenance des valeurs :
    des réglages entièrement codés en dur lui conviennent. Ce test compare donc les constantes
    résolues à l'environnement qui les a produites, ligne par ligne.
    """
    resultat = lancer(["-c", LECTURE_DES_REGLAGES], variables)
    assert resultat.returncode == 0, resultat.stderr

    reglages = json.loads(resultat.stdout)

    assert reglages["SECRET_KEY"] == variables["SECRET_KEY"]
    assert reglages["DEBUG"] is False
    assert reglages["ALLOWED_HOSTS"] == json.loads(variables["ALLOWED_HOSTS"])
    assert reglages["DATABASES"]["default"] == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "portfolio",
        "USER": "portfolio",
        "PASSWORD": "secret",
        "HOST": "localhost",
        "PORT": 5432,
    }
    # Produit de l'arbitrage ASGI/WSGI consigné au journal de spec de #2 : sans cette ligne,
    # l'arbitrage ne serait garanti par rien.
    assert reglages["WSGI_APPLICATION"] == "config.wsgi.application"
    assert reglages["ROOT_URLCONF"] == "config.urls"
