"""Tests du Postgres des tests : l'image du développement, jointe en IPv4, et l'échec qui dit
pourquoi quand Docker manque.

L'égalité de son image avec celle du Compose est tenue par `test_compose.py`, avec le reste du
contenu des fichiers Compose.
"""

import pytest
from containers import running
from django.db import connection
from docker.errors import DockerException
from testcontainers.core.container import DockerContainer


@pytest.mark.django_db
def test_la_base_des_tests_est_un_postgres_avec_pgvector() -> None:
    """Le serveur démarré est bien l'image du développement : un Postgres qui porte `vector`.

    L'extension n'existe que dans l'image `pgvector/pgvector` (ADR 0005) : un autre Postgres —
    celui d'un poste, une image officielle — ne la proposerait pas.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")

        assert cursor.fetchone() == (1,)


@pytest.mark.django_db
def test_le_postgres_des_tests_est_joint_en_ipv4() -> None:
    """`localhost` se résout d'abord en `::1` sous Windows : sur un port publié pour `127.0.0.1`
    seulement — le réglage recommandé du poste —, chaque connexion attendrait son délai avant de
    se replier (mesuré : 20 s, contre 0,01 s en `127.0.0.1`)."""
    assert connection.settings_dict["HOST"] == "127.0.0.1"


def test_sans_docker_un_conteneur_echoue_en_disant_pourquoi() -> None:
    """Sans Docker, le test qui demande un conteneur échoue — jamais sauté, un test sauté se lirait
    comme un vert — et le message cite la cause, puis dit quoi faire, sans la chaîne de docker-py
    qui le noyait.

    docker-py lève `DockerException` dès la construction de son client quand le démon ne répond
    pas (`_retrieve_server_version`, `docker/api/client.py`) : c'est ce que la fabrique rejoue.
    """

    def unreachable_docker() -> DockerContainer:
        raise DockerException("démon injoignable")

    # `BaseException` : un saut sortirait d'un `pytest.raises(pytest.fail.Exception)` et ferait
    # sauter ce test lui-même — vert à la lecture, le défaut même qu'il garde.
    with (
        pytest.raises(BaseException, match="démon injoignable\n.*exigent Docker") as refusal,
        running(unreachable_docker),
    ):
        pass

    assert refusal.type is pytest.fail.Exception, "le test est sauté, pas échoué"
    # `from None`, seule forme qui ne laisse ni cause ni contexte à afficher.
    assert refusal.value.__cause__ is None, "la chaîne de docker-py remonte"
    assert refusal.value.__suppress_context__, "la chaîne de docker-py remonte"
