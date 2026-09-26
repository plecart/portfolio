"""Tests du Postgres des tests : l'image du développement, démarrée pour la session.

L'égalité de son image avec celle du Compose est tenue par `test_infra.py`, avec les autres
fichiers d'infrastructure.
"""

from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import containers
import pytest
from containers import postgres, running
from django.db import connection
from nested_sessions import run_nested_session
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

# Un démon qui ne répond pas. `.invalid` ne se résout nulle part (RFC 2606) : docker-py échoue en
# 0,01 s, quand un port fermé de `127.0.0.1` lui coûte 2 s sous Windows (mesuré).
UNREACHABLE_DOCKER = "tcp://docker.invalid:2375"

# Ce que la session imbriquée lance : un test de base, et deux tests qui n'en touchent aucune.
BASE_TEST = (
    "apps/api/tests/test_containers.py::test_la_base_des_tests_est_un_postgres_avec_pgvector"
)
BASELESS_TESTS = [
    "apps/api/tests/test_admin.py::test_l_admin_renvoie_un_visiteur_anonyme_vers_la_connexion",
    "apps/api/tests/test_admin.py::test_l_admin_parle_francais",
]


@pytest.mark.django_db
def test_la_base_des_tests_est_un_postgres_avec_pgvector() -> None:
    """Le serveur démarré est bien l'image du développement : un Postgres qui porte `vector`.

    L'extension n'existe que dans l'image `pgvector/pgvector` (ADR 0005) : un autre Postgres —
    celui d'un poste, une image officielle — ne la proposerait pas.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")

        assert cursor.fetchone() == (1,)


@pytest.fixture
def postgres_class(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """`PostgresContainer` remplacé par un double à son gabarit : la fabrique s'éprouve sur ce
    qu'elle passe à testcontainers, sans Docker — construire le vrai conteneur l'interroge."""
    double = create_autospec(PostgresContainer)
    monkeypatch.setattr(containers, "PostgresContainer", double)
    return double


def test_le_postgres_des_tests_recoit_des_identifiants_explicites(
    postgres_class: MagicMock,
) -> None:
    """Un identifiant absent ou vide, testcontainers le lit dans le shell — `POSTGRES_USER`,
    `POSTGRES_PASSWORD`, `POSTGRES_DB` (`username or os.environ.get(…)`, lu dans son module
    Postgres) : un poste qui les exporte changerait la base des tests."""
    postgres()

    arguments = postgres_class.call_args.kwargs
    assert (arguments["username"], arguments["dbname"]) == ("portfolio", "portfolio")
    assert arguments["password"]


def test_chaque_postgres_des_tests_tire_son_propre_mot_de_passe(
    postgres_class: MagicMock,
) -> None:
    """Son port est publié sur toutes les interfaces : un mot de passe connu y ouvrirait un
    superutilisateur à quiconque partage le réseau du poste."""
    postgres()
    postgres()

    first, second = (call.kwargs["password"] for call in postgres_class.call_args_list)
    assert first != second


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


def test_sans_docker_un_test_de_base_echoue_en_disant_pourquoi(tmp_path: Path) -> None:
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
    session = run_nested_session(
        [BASE_TEST, *BASELESS_TESTS], tmp_path, DOCKER_HOST=UNREACHABLE_DOCKER
    )

    expected = {BASE_TEST: "error"} | dict.fromkeys(BASELESS_TESTS, "passed")
    assert session.outcomes == expected, session.report
    assert session.exit_code == pytest.ExitCode.TESTS_FAILED
    assert "exigent Docker" in session.report
    # Les deux formes de chaînage : « The above exception was the direct cause… » et « During
    # handling of the above exception… ». `pytrace=False` en tait les types, jamais les messages.
    assert "above exception" not in session.report, "la chaîne de docker-py remonte"
