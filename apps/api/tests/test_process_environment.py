"""Tests de l'environnement du processus de test, posé avant que Django ne lise ses réglages."""

import re
from pathlib import Path

from config.env import ENV_FILE, Env
from django.conf import settings
from nested_sessions import pytest_session
from process_environment import NO_ENV_FILE, VALID_ENVIRONMENT

# Ce qu'une session lancée depuis un shell pollué doit encore réussir : tout ce qui lit les
# réglages et le fichier `.env`. Jamais ce module entier — il se relancerait lui-même.
SHELL_INDEPENDENT_TESTS = [
    "apps/api/tests/test_admin.py",
    "apps/api/tests/test_process_environment.py::test_le_processus_de_test_ne_lit_aucun_env_du_poste",
]


def test_le_processus_de_test_ne_lit_aucun_env_du_poste() -> None:
    """Le `.env` du poste appartient au développeur, pas aux tests : ils n'en lisent aucun.

    `config/env.py` résout `ENV_FILE` à son import, que pytest-django déclenche en chargeant les
    réglages : ce test prouve que le greffon est passé avant.
    """
    assert ENV_FILE == NO_ENV_FILE
    assert not NO_ENV_FILE.exists()


def test_l_environnement_de_test_couvre_exactement_les_variables_d_env() -> None:
    """Une variable d'`Env` absente d'ici serait lue dans le shell du développeur, ou tomberait
    sur son défaut : les tests vérifieraient alors une configuration que personne n'a choisie."""
    assert set(VALID_ENVIRONMENT) == set(Env.model_fields)


def test_django_est_configure_pour_les_tests() -> None:
    """Sans réglages, pytest-django **saute** les tests qui en ont besoin (« no Django settings »).

    Mesuré : sans réglages, les deux tests de l'admin finissent `skipped`. Une configuration perdue
    ferait donc sauter une partie de la suite, qui resterait verte sans l'avoir vérifiée.
    """
    assert settings.configured


def test_un_shell_pollue_ne_change_rien_a_la_session_de_test(tmp_path: Path) -> None:
    """Le processus de test ne dépend pas du shell qui le lance.

    Deux variables du shell changeraient ce que les tests vérifient : un `DJANGO_SETTINGS_MODULE`
    exporté pour un autre projet — pytest-django lit l'environnement avant `pyproject.toml` — et
    un `ENV_FILE` qui ferait lire un autre `.env`. Celui qu'on pose ici porte une clé inconnue :
    le lire ferait refuser le démarrage.
    """
    polluted_env_file = tmp_path / ".env"
    polluted_env_file.write_text("CLE_INCONNUE=refusee\n", encoding="utf-8")

    session = pytest_session(
        SHELL_INDEPENDENT_TESTS,
        DJANGO_SETTINGS_MODULE="un_autre_projet.settings",
        ENV_FILE=str(polluted_env_file),
    )

    assert session.returncode == 0, session.stdout + session.stderr
    assert re.search(r"\b3 passed\b", session.stdout), session.stdout
