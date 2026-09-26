"""Fixtures communes aux tests de `apps/api`."""

from collections.abc import Generator
from pathlib import Path

import pytest
from config.database import database_settings
from containers import postgres, running
from django.conf import settings
from django.test import override_settings
from process_environment import VALID_ENVIRONMENT
from pydantic import PostgresDsn, TypeAdapter

UNCONFIGURED = (
    "Django n'est pas configuré pour les tests : le greffon `process_environment`, chargé par "
    "l'`addopts` de `pyproject.toml`, pose `DJANGO_SETTINGS_MODULE`."
)


@pytest.fixture
def variables() -> dict[str, str]:
    """L'environnement valide, sous forme de dictionnaire — pour un sous-processus."""
    return dict(VALID_ENVIRONMENT)


@pytest.fixture(autouse=True)
def media_root(tmp_path: Path) -> Generator[None]:
    """Les fichiers qu'un test enregistre vont dans son dossier temporaire, jamais dans le dépôt.

    Le `MEDIA_ROOT` du processus de test est relatif à la racine du dépôt (`process_environment`) :
    sans ce dossier, une icône enregistrée par un test y atterrirait. Automatique, pour qu'aucun
    test ne puisse l'oublier.

    Sans réglages, le test échoue d'emblée, en disant pourquoi. La fixture `settings` de
    pytest-django le sauterait — et avec lui toute la suite, par cette fixture automatique : verte
    sans rien avoir vérifié. `override_settings` seul le laisserait tourner sur des réglages vides,
    et n'échouerait qu'au démontage, sans dire pourquoi (mesuré).
    """
    if not settings.configured:
        pytest.fail(UNCONFIGURED, pytrace=False)
    with override_settings(MEDIA_ROOT=tmp_path):
        yield


@pytest.fixture(scope="session")
def django_db_modify_db_settings() -> Generator[None]:
    """Pointe la base de test sur un Postgres démarré pour la session.

    Point d'extension que pytest-django documente pour déplacer la base de test : son
    `django_db_setup` en dépend, puis crée la base de test et joue les migrations. Le conteneur ne
    démarre donc que si un test touche la base, et s'arrête après la suppression de la base de
    test.

    L'adresse du conteneur passe par `database_settings`, la traduction qu'emprunte
    `DATABASE_URL` en production. Le dictionnaire est mis à jour en place : les connexions de
    Django en gardent une référence.
    """
    with running(postgres) as server:
        url = TypeAdapter(PostgresDsn).validate_python(server.get_connection_url())
        settings.DATABASES["default"].update(database_settings(url))
        yield
