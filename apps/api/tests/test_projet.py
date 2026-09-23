"""Tests du projet Django : il démarre, et son point d'entrée de production se charge.

Ces deux vérifications passent par un sous-processus lancé depuis `apps/api`, comme le ferait
un humain ou `gunicorn` : c'est le seul moyen d'éprouver `manage.py` et `config/wsgi.py`
eux-mêmes, et pas une reconstitution de ce qu'ils font.
"""

import os
import subprocess
import sys
from pathlib import Path

RACINE_API = Path(__file__).resolve().parent.parent


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
