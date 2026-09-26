"""Tests de l'environnement du processus de test, posé avant que Django ne lise ses réglages."""

from config.env import ENV_FILE
from django.conf import settings
from process_environment import NO_ENV_FILE


def test_le_processus_de_test_ne_lit_aucun_env_du_poste() -> None:
    """Le `.env` du poste appartient au développeur, pas aux tests : ils n'en lisent aucun.

    `config/env.py` résout `ENV_FILE` à son import, que pytest-django déclenche en chargeant les
    réglages : ce test prouve que le greffon est passé avant.
    """
    assert ENV_FILE == NO_ENV_FILE
    assert not NO_ENV_FILE.exists()


def test_django_est_configure_pour_les_tests() -> None:
    """Sans réglages, pytest-django **saute** les tests de base (« no Django settings »).

    Mesuré : un test de base sans configuration rend `1 skipped`. Une configuration perdue ferait
    donc sauter tous les tests de base à la fois, et la suite resterait verte sans rien vérifier.
    """
    assert settings.configured
