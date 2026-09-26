"""Environnement du processus de test, posé avant que Django ne lise ses réglages.

pytest-django charge `config.settings` — qui lit l'environnement par `Env.load()` — avant
d'importer le moindre `conftest.py`. Ce module est donc un greffon pytest, chargé par `-p`
(`pyproject.toml`) : son crochet passe avant celui de pytest-django, comme la documentation de
pytest-django le prescrit (« Changing your app before Django gets set up »).

Le processus de test ne dépend ni du shell qui le lance ni du `.env` du poste : chaque variable
qu'il lit est posée ici, par-dessus celles du shell.
"""

import os
from pathlib import Path

import pytest

# Un environnement complet et valide. Chaque test en retire ou en corrompt une seule entrée,
# pour que l'échec attendu ne puisse venir que de celle-là.
VALID_ENVIRONMENT = {
    # Sans accent, et au-dessus du seuil de 50 caractères exigé par `Env`.
    "SECRET_KEY": "cle-de-test-sans-valeur-reelle-uniquement-pour-les-tests",
    "DEBUG": "false",
    "ALLOWED_HOSTS": '["portfolio.test"]',
    # Jamais contactées : les tests de base visent le conteneur de `containers.py`. `.invalid` ne
    # se résout nulle part (RFC 2606) — une connexion égarée échoue aussitôt, là où un serveur
    # local absent la ferait attendre plus de deux minutes sous Windows (mesuré).
    "DATABASE_URL": "postgresql://portfolio:secret@base.invalid:5432/portfolio",
    "REDIS_URL": "redis://cache.invalid:6379/0",
    # Relatif à dessein : c'est la forme que `.env.example` propose, donc celle que la plupart
    # des clones porteront, et la seule qui éprouve l'ancrage sur la racine du dépôt.
    "MEDIA_ROOT": "fichiers-de-test",
}

# Un chemin qui n'existe pas : `pydantic-settings` n'y lit rien, sans bruit.
NO_ENV_FILE = Path(__file__).with_name("aucun-fichier-env")

# Les variables des outils, hors des champs d'`Env` : quels réglages pytest-django charge — il lit
# l'environnement avant `pyproject.toml` —, et quel fichier `Env` lit.
TOOLING_ENVIRONMENT = {
    "DJANGO_SETTINGS_MODULE": "config.settings",
    "ENV_FILE": str(NO_ENV_FILE),
}


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests() -> None:
    """Pose l'environnement de test avant que pytest-django ne charge les réglages."""
    os.environ.update(VALID_ENVIRONMENT | TOOLING_ENVIRONMENT)
