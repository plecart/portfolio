"""Tests du harnais : l'environnement du processus de test, posé avant que Django ne lise ses
réglages, et ce qu'il garantit à chaque test — des réglages présents, des fichiers hors du dépôt."""

import os
import re
import subprocess
import sys
from pathlib import Path

from config.env import ENV_FILE, REPOSITORY_ROOT, Env
from django.core.files.storage import default_storage
from nested_sessions import run_nested_session
from process_environment import NO_ENV_FILE, RYUK_IMAGE, VALID_ENVIRONMENT
from testcontainers.core.config import testcontainers_config

# Imprime l'image Ryuk que testcontainers choisit de lui-même, faute de variable qui l'épingle.
# Dans un processus à part : la configuration est lue une fois, à l'import du module.
RYUK_DEFAULT = (
    "from testcontainers.core.config import testcontainers_config as c; print(c.ryuk_image)"
)

# Ce qu'une session lancée depuis un shell pollué doit encore réussir : des tests qui lisent les
# réglages, le fichier `.env` et l'adresse des conteneurs.
SHELL_INDEPENDENT_TESTS = [
    "apps/api/tests/test_admin.py::test_l_admin_renvoie_un_visiteur_anonyme_vers_la_connexion",
    "apps/api/tests/test_admin.py::test_l_admin_parle_francais",
    "apps/api/tests/test_process_environment.py::test_le_processus_de_test_ne_lit_aucun_env_du_poste",
    "apps/api/tests/test_process_environment.py::test_testcontainers_joint_ses_conteneurs_en_ipv4",
]

# Un test qui passerait sans réglages : s'il échoue dans une session sans réglages, c'est le
# harnais qui l'a fait échouer.
SETTINGLESS_TEST = (
    "apps/api/tests/test_process_environment.py"
    "::test_l_environnement_de_test_couvre_exactement_les_variables_d_env"
)


def test_le_processus_de_test_ne_lit_aucun_env_du_poste() -> None:
    """Le `.env` du poste appartient au développeur, pas aux tests : ils n'en lisent aucun.

    `config/env.py` résout `ENV_FILE` une fois, à son import : ce test prouve que la variable du
    greffon était déjà posée à ce moment-là.
    """
    assert ENV_FILE == NO_ENV_FILE
    assert not NO_ENV_FILE.exists()


def test_l_environnement_de_test_couvre_exactement_les_variables_d_env() -> None:
    """Une variable d'`Env` absente d'ici serait lue dans le shell du développeur, ou tomberait
    sur son défaut : les tests vérifieraient alors une configuration que personne n'a choisie."""
    assert set(VALID_ENVIRONMENT) == set(Env.model_fields)


def test_testcontainers_joint_ses_conteneurs_en_ipv4() -> None:
    """L'adresse que testcontainers rend en premier (`DockerClient.host`), sans Docker : la
    session au shell pollué l'éprouve ainsi à peu de frais. `test_containers.py` vérifie la
    connexion elle-même."""
    assert testcontainers_config.tc_host_override == "127.0.0.1"


def test_ryuk_tourne_sur_l_image_epinglee() -> None:
    """testcontainers lit son image Ryuk à l'import : le greffon doit l'avoir posée avant."""
    assert testcontainers_config.ryuk_image == RYUK_IMAGE


def test_l_epingle_de_ryuk_suit_l_image_que_testcontainers_attend() -> None:
    """Une montée de testcontainers qui change d'image Ryuk fait rougir ce test.

    Sans lui, l'épingle garderait en silence l'ancienne image, que la nouvelle version ne sait
    peut-être plus piloter. La mise à jour se fait alors dans la PR de montée : étiquette et
    empreinte ensemble.
    """
    default = subprocess.run(
        [sys.executable, "-c", RYUK_DEFAULT],
        env={name: value for name, value in os.environ.items() if name != "RYUK_CONTAINER_IMAGE"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tag, _, digest = RYUK_IMAGE.partition("@")

    assert tag == default
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)


def test_sans_reglages_chaque_test_echoue(tmp_path: Path) -> None:
    """Sans réglages, pytest-django **saute** les tests qui en ont besoin (« no Django settings ») :
    une configuration perdue laisserait la suite verte sans l'avoir vérifiée. La fixture
    automatique `media_root` fait échouer chaque test à la place.

    Les réglages se perdent quand le greffon `process_environment` n'est pas chargé, et que le
    shell ne pose pas `DJANGO_SETTINGS_MODULE` : `-o addopts=` retire le `-p` de `pyproject.toml`.
    """
    session = run_nested_session(
        [SETTINGLESS_TEST], tmp_path, PYTEST_ADDOPTS="-o addopts=", DJANGO_SETTINGS_MODULE=""
    )

    assert session.outcomes == {SETTINGLESS_TEST: "error"}, session.report
    assert "Django n'est pas configuré" in session.report


def test_un_fichier_enregistre_par_un_test_ne_va_pas_dans_le_depot() -> None:
    """Le `MEDIA_ROOT` du processus vise le dépôt — relatif à dessein, voir `VALID_ENVIRONMENT`.
    Un test qui enregistre un fichier l'écrirait donc là, sans qu'aucune porte ne le voie, et un
    `git add -A` le commiterait. Ce test ne demande aucune fixture : il vaut pour tous les autres.
    """
    stored = Path(default_storage.path("technologies/icone.svg"))

    assert not stored.is_relative_to(REPOSITORY_ROOT), stored


def test_un_shell_pollue_ne_change_rien_a_la_session_de_test(tmp_path: Path) -> None:
    """Le processus de test ne dépend pas du shell qui le lance.

    Trois variables du shell changeraient ce que les tests vérifient : un `DJANGO_SETTINGS_MODULE`
    exporté pour un autre projet — pytest-django lit l'environnement avant `pyproject.toml` —, un
    `ENV_FILE` qui ferait lire un autre `.env`, et un `TC_HOST` qui l'emporterait sur l'adresse
    des conteneurs. Le `.env` qu'on pose ici porte une clé inconnue : le lire ferait refuser le
    démarrage.
    """
    polluted_env_file = tmp_path / ".env"
    polluted_env_file.write_text("CLE_INCONNUE=refusee\n", encoding="utf-8")

    session = run_nested_session(
        SHELL_INDEPENDENT_TESTS,
        tmp_path,
        DJANGO_SETTINGS_MODULE="un_autre_projet.settings",
        ENV_FILE=str(polluted_env_file),
        TC_HOST="localhost",
    )

    assert session.outcomes == dict.fromkeys(SHELL_INDEPENDENT_TESTS, "passed"), session.report
