"""Tests des fichiers Compose : celui du poste, celui de la production, et l'invariant que l'ADR 0012
tient entre les deux — mêmes images, même point d'entrée, mêmes services de données.

Comme `test_infra.py`, ces tests lisent des fichiers sans démarrer de conteneur, avec l'analyseur
YAML : c'est la valeur que Compose lira qui compte. Qu'un fichier se résolve est prouvé par
`make compose-config`, porte du job `infra` ; que la pile démarre, par la pile qu'on regarde tourner
— la production ne démarre que sur le VPS. Les images tierces qu'ils citent, épinglées et suivies
par Dependabot, ont leurs tests dans `test_supply_chain.py`.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from config.env import Env
from containers import POSTGRES_IMAGE
from test_env import declared_variables
from test_infra import COMPOSE_DEV, IMAGE_DOCKERFILES, PUBLISH_PREFIX

COMPOSE_PROD = COMPOSE_DEV.with_name("compose.yml")
PROD_ENV_EXAMPLE = COMPOSE_DEV.with_name("prod.env.example")
COMPOSE_FILES = {"développement": COMPOSE_DEV, "production": COMPOSE_PROD}

# Les services de données, à la même image dans les deux fichiers (ADR 0012).
DATA_SERVICES = ["postgres", "redis"]

# Une image du dépôt en production : celle que le job `publish` a poussée sous le préfixe GHCR,
# à l'étiquette du commit que le job de déploiement fixe — jamais `latest`, jamais reconstruite
# pour un environnement (ADR 0012, critères de #16).
DEPLOYED_IMAGE = re.compile(
    rf"^{re.escape(PUBLISH_PREFIX)}(?P<image>[\w-]+):\$\{{IMAGE_TAG:\?[^}}]*\}}$"
)

# Une interpolation Compose, `${NOM…}` ; `$$` échappe le `$` destiné au shell du conteneur.
INTERPOLATION = re.compile(r"(?<!\$)\$\{(?P<name>\w+)(?P<modifier>[^}]*)\}")

# Ce qu'un service de production ne porte jamais : toute clé qui le rendrait joignable autrement
# que par le réseau du projet — un port publié, le réseau de l'hôte ou d'un autre conteneur, un
# réseau nommé qui pourrait être externe. `cloudflared` est la seule entrée, par une connexion
# sortante (D45).
EXPOSING_KEYS = ["ports", "network_mode", "networks"]

# La sonde de `postgres` doit interroger le **réseau**, pas le socket Unix local. Pendant
# `initdb`, l'image postgres démarre un serveur temporaire avec `listen_addresses=''` : il
# accepte déjà le socket et refuse encore TCP. Mesuré sur `pgvector/pgvector:pg16` dans cet
# état — `pg_isready -U … -d …` rend « accepting connections » (0) quand la même sonde avec
# `-h 127.0.0.1` rend « no response » (2). Sans cet hôte, `service_healthy` peut se déclencher
# alors qu'`api` ne peut joindre personne, et ses migrations échouent au premier `up`.
POSTGRES_PROBE_HOST = "-h 127.0.0.1"

# Les adresses que le service `api` reçoit avec les noms de service. Sur le poste, `env_file`
# apporte celles du `.env` (`127.0.0.1`), qui ne désignent rien depuis un conteneur, et
# `environment:` les remplace ; en production, rien d'autre ne les apporte. Absentes, elles
# laissent `docker compose config` vert et ne cassent qu'au démarrage — d'où ce test.
SERVICE_ADDRESS_OVERRIDES = {
    "DATABASE_URL": "@postgres:5432/",
    "MEDIA_ROOT": "/app/media",
    "REDIS_URL": "redis://redis:6379",
}


def read_services(compose_file: Path) -> dict[str, dict[str, Any]]:
    """Les services d'un fichier Compose du dépôt, par nom."""
    return yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"]


def exposure_findings(text: str) -> list[str]:
    """Ce par quoi un fichier Compose rendrait un service joignable hors du réseau du projet.

    Returns:
        Un constat par réseau déclaré au niveau du fichier — même le réseau `default`, qu'une
        déclaration peut rendre externe — et par clé de `EXPOSING_KEYS` portée par un service.
        Liste vide : chaque service n'a que le réseau privé du projet.
    """
    document: dict[str, Any] = yaml.safe_load(text)
    declared = (
        [f"réseaux déclarés : {sorted(document['networks'])}"] if "networks" in document else []
    )
    return declared + [
        f"{name} : {key}"
        for name, service in document["services"].items()
        for key in EXPOSING_KEYS
        if key in service
    ]


def strings(node: object) -> Iterator[str]:
    """Les chaînes d'un document YAML, à toute profondeur — commentaires exclus par l'analyseur."""
    if isinstance(node, dict):
        for value in cast(dict[object, object], node).values():
            yield from strings(value)
    elif isinstance(node, list):
        for item in cast(list[object], node):
            yield from strings(item)
    elif isinstance(node, str):
        yield node


def compose(service: str) -> str:
    """Un fichier Compose minimal dont le seul service porte le bloc donné."""
    return f"services:\n  caddy:\n    image: caddy\n{service}"


# Forme → constat attendu (`True`) ou aucun (`False`).
EXPOSURE_FORMS = {
    "aucune clé de réseau": (compose(""), False),
    "port exposé au réseau du projet seulement": (compose('    expose: ["80"]\n'), False),
    "port publié": (compose('    ports: ["80:80"]\n'), True),
    "port publié, syntaxe longue": (compose("    ports:\n      - target: 80\n"), True),
    "réseau de l'hôte": (compose("    network_mode: host\n"), True),
    "réseau d'un autre service": (compose('    network_mode: "service:api"\n'), True),
    "réseau nommé": (compose("    networks: [bordure]\n") + "networks:\n  bordure: {}\n", True),
    "réseau par défaut redéfini en externe": (
        compose("") + "networks:\n  default:\n    name: host\n    external: true\n",
        True,
    ),
}


@pytest.mark.parametrize(("text", "expected"), EXPOSURE_FORMS.values(), ids=EXPOSURE_FORMS.keys())
def test_la_garde_d_exposition_rend_son_verdict_sur_chaque_forme(text: str, expected: bool) -> None:
    """Chaque façon recensée de rendre un service joignable hors du réseau du projet."""
    assert bool(exposure_findings(text)) is expected, exposure_findings(text)


def test_aucun_service_de_production_n_est_joignable_hors_du_reseau_du_projet() -> None:
    """Aucun port web n'est ouvert sur le VPS : `cloudflared` sort vers Cloudflare, et c'est la
    seule entrée (D45, ADR 0003). Un port publié contournerait Cloudflare — WAF, Access, limite de
    débit."""
    findings = exposure_findings(COMPOSE_PROD.read_text(encoding="utf-8"))

    assert not findings, findings


@pytest.mark.parametrize("service", DATA_SERVICES)
def test_les_services_de_donnees_ont_la_meme_image_sur_le_poste_et_en_production(
    service: str,
) -> None:
    """L'invariant de l'ADR 0012 : un défaut de Postgres ou de Redis se reproduit sur le poste
    parce que c'est la même image, épingle comprise (brief de #16, décision 5)."""
    images = {name: read_services(path)[service]["image"] for name, path in COMPOSE_FILES.items()}

    assert len(set(images.values())) == 1, images


def test_la_production_tire_chaque_image_du_depot_publiee_a_l_etiquette_du_commit() -> None:
    """Chaque image du dépôt — une par dossier `infra/<service>/` — tourne en production telle que
    `publish` l'a poussée : préfixe GHCR, étiquette du commit, aucune construction sur le VPS. Une
    même image peut servir plusieurs services (le `worker` de #12 reprendra celle d'`api`)."""
    production = read_services(COMPOSE_PROD)
    deployed = {
        name: DEPLOYED_IMAGE.match(service["image"])
        for name, service in production.items()
        if "${" in service["image"]
    }

    assert all(deployed.values()), deployed
    images = {match["image"] for match in deployed.values() if match}
    assert images == {path.parent.name for path in IMAGE_DOCKERFILES}
    assert [name for name, service in production.items() if "build" in service] == []


@pytest.mark.parametrize("compose_file", COMPOSE_FILES.values(), ids=COMPOSE_FILES.keys())
def test_aucun_service_ne_remplace_le_point_d_entree_de_son_image(compose_file: Path) -> None:
    """Le point d'entrée partagé — migrations, puis la commande — est celui de l'image, dans les
    deux fichiers (ADR 0012) : un `entrypoint:` le court-circuiterait sur un seul environnement."""
    overriding = [name for name, svc in read_services(compose_file).items() if "entrypoint" in svc]

    assert overriding == []


def test_api_recoit_en_production_chaque_variable_du_back() -> None:
    """Sans `env_file` en production, chaque variable de `Env` passe par `environment:` : un champ
    ajouté au back sans sa ligne ici empêcherait `api` de démarrer, au déploiement seulement.
    `DEBUG` seul en est absent : absent vaut faux, la posture de production (`.env.example`)."""
    environment = read_services(COMPOSE_PROD)["api"]["environment"]

    assert set(environment) == set(Env.model_fields) - {"DEBUG"}


def test_chaque_variable_de_production_est_exigee_et_declaree_dans_son_modele() -> None:
    """`${NOM:?…}` partout : une variable absente du `.env` du VPS fait échouer la résolution,
    au lieu de démarrer un service sur une valeur vide. Et `infra/prod.env.example` les déclare
    toutes, rien de plus : c'est le modèle de ce `.env`, et ce que `make compose-config` résout."""
    found = [
        match
        for text in strings(yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8")))
        for match in INTERPOLATION.finditer(text)
    ]

    assert found, "aucune interpolation lue — le motif a-t-il cessé de mordre ?"
    assert [match.group() for match in found if not match["modifier"].startswith(":?")] == []
    assert {match["name"] for match in found} == set(declared_variables(PROD_ENV_EXAMPLE))


def test_les_tests_de_base_tournent_sur_l_image_postgres_du_compose() -> None:
    """Les tests vérifient les contraintes sur le moteur et les extensions du développement — donc
    de la production, à la même image."""
    assert read_services(COMPOSE_DEV)["postgres"]["image"] == POSTGRES_IMAGE


@pytest.mark.parametrize("compose_file", COMPOSE_FILES.values(), ids=COMPOSE_FILES.keys())
@pytest.mark.parametrize(("variable", "expected"), sorted(SERVICE_ADDRESS_OVERRIDES.items()))
def test_le_service_api_recoit_ses_adresses_de_service(
    compose_file: Path, variable: str, expected: str
) -> None:
    """Les retirer ne fait rougir ni `make test` ni `make compose-config` : la pile démarre, puis
    `api` sort en 1 sur une connexion refusée pendant que les autres services restent vivants."""
    environment = read_services(compose_file)["api"]["environment"]

    assert expected in environment[variable]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES.values(), ids=COMPOSE_FILES.keys())
def test_la_sonde_de_postgres_interroge_le_reseau_et_non_le_socket_local(
    compose_file: Path,
) -> None:
    """Une sonde aveugle à l'état TCP déclare saine une base qu'`api` ne peut pas encore joindre.

    C'est le seul état qui compte : `api` se connecte par le réseau du Compose, jamais par le
    socket Unix du conteneur `postgres`.
    """
    probe = " ".join(read_services(compose_file)["postgres"]["healthcheck"]["test"])

    assert "pg_isready" in probe and POSTGRES_PROBE_HOST in probe
