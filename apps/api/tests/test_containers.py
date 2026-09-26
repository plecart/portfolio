"""Tests du Postgres des tests : l'image du développement, démarrée pour la session.

L'égalité de son image avec celle du Compose est tenue par `test_infra.py`, avec les autres
fichiers d'infrastructure.
"""

import pytest
from containers import postgres, running
from django.db import connection

# Un démon qui ne répond pas : le port 9 (« discard ») n'écoute sur aucun poste ni aucun runner.
UNREACHABLE_DOCKER = "tcp://127.0.0.1:9"


def test_sans_docker_un_test_de_base_echoue_en_disant_pourquoi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un échec qui nomme Docker, jamais un saut ni une trace de `docker-py` à déchiffrer.

    `DOCKER_HOST` est la variable que testcontainers lit, sauf si `~/.testcontainers.properties`
    pose `tc.host` — aucun poste du projet ni la CI ne le font.
    """
    monkeypatch.setenv("DOCKER_HOST", UNREACHABLE_DOCKER)

    with pytest.raises(pytest.fail.Exception, match="exigent Docker"), running(postgres):
        pass


@pytest.mark.django_db
def test_la_base_des_tests_est_un_postgres_avec_pgvector() -> None:
    """Le serveur démarré est bien l'image du développement : un Postgres qui porte `vector`.

    L'extension n'existe que dans l'image `pgvector/pgvector` (ADR 0005) : un autre Postgres —
    celui d'un poste, une image officielle — ne la proposerait pas.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")

        assert cursor.fetchone() == (1,)
