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

# Ryuk, le conteneur de nettoyage de testcontainers, reçoit le socket Docker en écriture : c'est
# l'image la plus privilégiée que les tests lancent. Épinglée par empreinte, comme les images de
# base du Dockerfile — une étiquette peut changer de contenu, une empreinte non. L'étiquette reste
# celle que testcontainers attend : `test_process_environment.py` le vérifie à chaque montée.
# Dependabot ne voit pas cette épingle : l'empreinte d'une nouvelle étiquette se lit sur la ligne
# « Digest » de `docker buildx imagetools inspect testcontainers/ryuk:<étiquette>`.
RYUK_IMAGE = (
    "testcontainers/ryuk:0.8.1"
    "@sha256:bf3f74a47dee0acda89aba4b2fc9c7fdcf994a084db02a2d06566f07baae022e"
)

# Les variables des outils, hors des champs d'`Env` : quels réglages pytest-django charge — il lit
# l'environnement avant `pyproject.toml` —, quel fichier `Env` lit, quelle image Ryuk
# testcontainers lance, et par quelle adresse il joint ses conteneurs. `127.0.0.1` et non le
# `localhost` qu'il rend de lui-même : sous Windows, `localhost` se résout d'abord en `::1`, et
# un port publié pour `127.0.0.1` seulement ferait attendre chaque connexion.
TOOLING_ENVIRONMENT = {
    "DJANGO_SETTINGS_MODULE": "config.settings",
    "ENV_FILE": str(NO_ENV_FILE),
    "RYUK_CONTAINER_IMAGE": RYUK_IMAGE,
    "TESTCONTAINERS_HOST_OVERRIDE": "127.0.0.1",
}


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests() -> None:
    """Pose l'environnement de test avant que pytest-django ne charge les réglages."""
    os.environ.update(VALID_ENVIRONMENT | TOOLING_ENVIRONMENT)
