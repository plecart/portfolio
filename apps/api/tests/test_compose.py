"""Tests des fichiers Compose : ce que chaque service doit recevoir pour joindre les autres.

Comme `test_infra.py`, ces tests lisent des fichiers sans démarrer de conteneur. Qu'un fichier se
résolve est prouvé par `make compose-config`, porte du job `infra` ; que la pile démarre, par la
pile qu'on regarde tourner. Les images tierces qu'ils citent — épinglées, suivies par Dependabot —
ont leurs tests dans `test_supply_chain.py`.
"""

import re

import pytest
import yaml
from containers import POSTGRES_IMAGE
from test_infra import COMPOSE_DEV

# La sonde de `postgres` doit interroger le **réseau**, pas le socket Unix local. Pendant
# `initdb`, l'image postgres démarre un serveur temporaire avec `listen_addresses=''` : il
# accepte déjà le socket et refuse encore TCP. Mesuré sur `pgvector/pgvector:pg16` dans cet
# état — `pg_isready -U … -d …` rend « accepting connections » (0) quand la même sonde avec
# `-h 127.0.0.1` rend « no response » (2). Sans cet hôte, `service_healthy` peut se déclencher
# alors qu'`api` ne peut joindre personne, et ses migrations échouent au premier `up`.
POSTGRES_PROBE_HOST = "-h 127.0.0.1"

# Les adresses que le service `api` doit recomposer avec les noms de service. `env_file: ../.env`
# apporte celles du poste (`127.0.0.1`), qui ne désignent rien depuis un conteneur ; ces trois
# lignes les remplacent, et `environment:` prime sur `env_file:`. Les retirer laisse
# `docker compose config` vert et ne casse qu'au démarrage — d'où ce test.
SERVICE_ADDRESS_OVERRIDES = {
    "DATABASE_URL": "@postgres:5432/",
    "MEDIA_ROOT": "/app/media",
    "REDIS_URL": "redis://redis:6379",
}


def test_les_tests_de_base_tournent_sur_l_image_postgres_du_compose() -> None:
    """Les tests vérifient les contraintes sur le moteur et les extensions du développement.

    Lu avec l'analyseur YAML, pas avec un motif : c'est la valeur que Compose lira qui compte.
    """
    compose = yaml.safe_load(COMPOSE_DEV.read_text(encoding="utf-8"))

    assert compose["services"]["postgres"]["image"] == POSTGRES_IMAGE


@pytest.mark.parametrize(("variable", "expected"), sorted(SERVICE_ADDRESS_OVERRIDES.items()))
def test_le_service_api_recompose_ses_adresses_de_service(variable: str, expected: str) -> None:
    """`env_file` apporte les adresses du poste ; seules ces lignes les rendent joignables.

    Les retirer ne fait rougir ni `make test` ni `make compose-config` : la pile démarre, puis
    `api` sort en 1 sur une connexion refusée pendant que les autres services restent vivants.
    """
    declaration = re.search(
        rf"^\s*{variable}:\s*(?P<value>\S.*)$",
        COMPOSE_DEV.read_text(encoding="utf-8"),
        re.MULTILINE,
    )

    assert declaration, f"« {variable} » a disparu du bloc `environment:` du service `api`"
    assert expected in declaration.group("value")


def test_la_sonde_de_postgres_interroge_le_reseau_et_non_le_socket_local() -> None:
    """Une sonde aveugle à l'état TCP déclare saine une base qu'`api` ne peut pas encore joindre.

    C'est le seul état qui compte : `api` se connecte par le réseau du Compose, jamais par le
    socket Unix du conteneur `postgres`.
    """
    probe = re.search(r"pg_isready[^\"]*", COMPOSE_DEV.read_text(encoding="utf-8"))

    assert probe, "la sonde `pg_isready` a disparu du service `postgres`"
    assert POSTGRES_PROBE_HOST in probe.group()
