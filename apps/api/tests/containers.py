"""Conteneurs Docker des tests : les démarrer, ou faire échouer le test en disant pourquoi.

Les tests qui touchent la base tournent sur un vrai Postgres, démarré par testcontainers pour la
session (cadrage §8.4) : les règles du contenu sont des contraintes Postgres, qu'aucune base de
substitution ne vérifierait. Sans Docker, ces tests échouent, jamais ne sautent — un test sauté
se lit comme un vert.
"""

import secrets
from collections.abc import Callable, Generator
from contextlib import contextmanager

import pytest
from docker.errors import DockerException
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

# L'image du service `postgres` de `infra/compose.dev.yml` : les tests tournent sur le moteur et
# les extensions du développement (ADR 0005). `test_infra.py` tient l'égalité des deux.
POSTGRES_IMAGE = "pgvector/pgvector:pg16"

CONTAINER_REFUSED = (
    "Le conteneur des tests n'a pas démarré : {cause}\n"
    "Les tests qui touchent la base exigent Docker (testcontainers) : démarrer Docker, relancer."
)


def postgres() -> PostgresContainer:
    """Le Postgres des tests, hermétique et fermé.

    Identifiants explicites : sans eux, testcontainers lit `POSTGRES_USER`, `POSTGRES_PASSWORD` et
    `POSTGRES_DB` dans l'environnement du shell. Mot de passe tiré au hasard à chaque session :
    testcontainers publie le port sur toutes les interfaces du poste, et un superutilisateur
    Postgres au mot de passe connu, joignable depuis le réseau local, peut exécuter des commandes
    dans le conteneur (`COPY … FROM PROGRAM`).

    Returns:
        Le conteneur, pas encore démarré. `driver=None` : son adresse est une URL `postgresql://`
        sans pilote, la seule forme que `config/database.py` accepte.
    """
    return PostgresContainer(
        POSTGRES_IMAGE,
        username="portfolio",
        password=secrets.token_urlsafe(),
        dbname="portfolio",
        driver=None,
    )


@contextmanager
def running[C: DockerContainer](create: Callable[[], C]) -> Generator[C]:
    """Crée et démarre un conteneur pour la durée du bloc, puis l'arrête.

    Générique : rien ici n'est propre à Postgres. #11 y passera son Redis.

    Args:
        create: la fabrique du conteneur. Elle est appelée ici, et non par l'appelant, parce que
            construire un conteneur interroge déjà Docker — `docker-py` y négocie la version de
            son API, et lève `DockerException` si le démon ne répond pas.

    Yields:
        Le conteneur démarré, prêt : chaque module testcontainers attend son service.

    Raises:
        pytest.fail.Exception: Docker n'a pas pu créer ou démarrer le conteneur ; le message dit
            pourquoi et quoi faire.
    """
    try:
        container = create().start()
    except DockerException as error:
        pytest.fail(CONTAINER_REFUSED.format(cause=error), pytrace=False)
    try:
        yield container
    finally:
        container.stop()
