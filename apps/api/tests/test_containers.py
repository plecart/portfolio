"""Tests du Postgres des tests : l'image du développement, démarrée pour la session.

L'égalité de son image avec celle du Compose est tenue par `test_infra.py`, avec les autres
fichiers d'infrastructure.
"""

import re
from unittest.mock import create_autospec

import pytest
from containers import postgres, running
from django.db import connection
from nested_sessions import pytest_session
from testcontainers.core.container import DockerContainer

# Un démon qui ne répond pas. `.invalid` ne se résout nulle part (RFC 2606) : docker-py échoue en
# 0,01 s, quand un port fermé de `127.0.0.1` lui coûte 2 s sous Windows (mesuré).
UNREACHABLE_DOCKER = "tcp://docker.invalid:2375"

# Ce que la session imbriquée lance : un test de base, et deux tests qui n'en touchent aucune.
BASE_TEST = (
    "apps/api/tests/test_containers.py::test_la_base_des_tests_est_un_postgres_avec_pgvector"
)
BASELESS_TESTS = "apps/api/tests/test_admin.py"


@pytest.mark.django_db
def test_la_base_des_tests_est_un_postgres_avec_pgvector() -> None:
    """Le serveur démarré est bien l'image du développement : un Postgres qui porte `vector`.

    L'extension n'existe que dans l'image `pgvector/pgvector` (ADR 0005) : un autre Postgres —
    celui d'un poste, une image officielle — ne la proposerait pas.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")

        assert cursor.fetchone() == (1,)


def test_le_postgres_des_tests_ignore_les_identifiants_du_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans identifiants explicites, testcontainers les lirait dans le shell (`POSTGRES_*`)."""
    for variable in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        monkeypatch.setenv(variable, "du-shell")

    server = postgres()

    assert (server.username, server.dbname) == ("portfolio", "portfolio")
    assert server.password != "du-shell"


def test_chaque_postgres_des_tests_tire_son_propre_mot_de_passe() -> None:
    """Son port est publié sur toutes les interfaces : un mot de passe connu y ouvrirait un
    superutilisateur à quiconque partage le réseau du poste."""
    assert postgres().password != postgres().password


def test_un_conteneur_dont_le_demarrage_echoue_est_arrete() -> None:
    """Un démarrage raté laisse un conteneur créé : `running` l'arrête quand même.

    Docker est une frontière du système : un double au gabarit de `DockerContainer` suffit à
    rejouer une attente de service qui expire.
    """
    container = create_autospec(DockerContainer, instance=True)
    container.start.side_effect = TimeoutError("service jamais prêt")

    with pytest.raises(TimeoutError), running(lambda: container):
        pass

    container.stop.assert_called_once_with()


def test_sans_docker_un_test_de_base_echoue_en_disant_pourquoi() -> None:
    """Sans Docker, le test de base échoue — jamais sauté — et les autres tournent.

    Éprouvé de bout en bout, dans une session pytest à part : c'est la suite entière qui doit
    rester rouge et lisible, pas seulement un utilitaire. Un test sauté se lirait comme un vert ;
    un conteneur démarré pour tous les tests ferait échouer ceux qui n'ont pas besoin de base ;
    une trace de docker-py noierait le message qui dit quoi faire.

    testcontainers cherche Docker dans `tc.host` (`~/.testcontainers.properties`), puis dans
    `DOCKER_HOST`, puis dans le contexte Docker courant : `DOCKER_HOST` suffit, tant qu'aucun poste
    ne pose `tc.host` — ni celui du projet ni la CI ne le font. Il réécrit aussi `DOCKER_HOST`
    dans l'environnement du processus au premier conteneur : d'où la valeur passée explicitement.
    """
    session = pytest_session([BASE_TEST, BASELESS_TESTS], DOCKER_HOST=UNREACHABLE_DOCKER)
    report = session.stdout

    assert session.returncode == pytest.ExitCode.TESTS_FAILED, report
    assert re.search(r"\b2 passed, 1 error\b", report), report
    assert "skipped" not in report
    assert "exigent Docker" in report
    # Les deux formes de chaînage : « The above exception was the direct cause… » et « During
    # handling of the above exception… ». `pytrace=False` en tait les types, jamais les messages.
    assert "above exception" not in report, "la chaîne de docker-py remonte avec le message"
