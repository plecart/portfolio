"""Fixtures communes aux tests de `apps/api`."""

from collections.abc import Generator

import pytest
from config.database import database_settings
from containers import postgres, running
from django.conf import settings
from process_environment import VALID_ENVIRONMENT
from pydantic import PostgresDsn, TypeAdapter


@pytest.fixture
def variables() -> dict[str, str]:
    """L'environnement valide, sous forme de dictionnaire — pour un sous-processus."""
    return dict(VALID_ENVIRONMENT)


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, variables: dict[str, str]) -> pytest.MonkeyPatch:
    """Pose l'environnement valide dans ce processus et rend la main pour le corrompre."""
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


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
