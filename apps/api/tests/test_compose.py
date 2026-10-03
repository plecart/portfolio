"""Tests des fichiers Compose : celui du poste, celui de la production, et l'invariant que
l'ADR 0012 tient entre les deux — mêmes images, même point d'entrée, mêmes services de données.

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
from test_infra import COMPOSE_DEV, IMAGE_DOCKERFILES, PUBLISH_PREFIX, make_dry_run
from test_supply_chain import compose_services

COMPOSE_PROD = COMPOSE_DEV.with_name("compose.yml")
PROD_ENV_EXAMPLE = COMPOSE_DEV.with_name("prod.env.example")
COMPOSE_BY_ENVIRONMENT = {"développement": COMPOSE_DEV, "production": COMPOSE_PROD}

# Les services de données, à la même image dans les deux fichiers (ADR 0012).
DATA_SERVICES = ["postgres", "redis"]

# Une image du dépôt en production : celle que le job `publish` a poussée sous le préfixe GHCR,
# à l'étiquette du commit que le job de déploiement fixe — jamais `latest`, jamais reconstruite
# pour un environnement (ADR 0012, critères de #16).
DEPLOYED_IMAGE = re.compile(
    rf"^{re.escape(PUBLISH_PREFIX)}(?P<image>[\w-]+):\$\{{IMAGE_TAG:\?[^}}]*\}}$"
)

# Une interpolation Compose : `${NOM…}`, ou `$NOM` sans accolades — que Compose résout aussi, à
# vide s'il manque, sur un simple avertissement (mesuré à la relecture de la PR #69). `$$` échappe
# le `$` destiné au shell du conteneur : les paires se lisent d'abord, et le `$` qui reste derrière
# elles interpole (`$$$X` rend `$` suivi de la valeur de `X`, mesuré).
INTERPOLATION = re.compile(
    r"(?<!\$)(?:\$\$)*\$(?:\{(?P<name>\w+)(?P<modifier>[^}]*)\}|(?P<bare>[A-Za-z_]\w*))"
)

# Ce qu'un service de production ne porte jamais : toute clé qui le rendrait joignable autrement
# que par le réseau du projet — un port publié, le réseau de l'hôte ou d'un autre conteneur, un
# réseau nommé qui pourrait être externe — ou qui reprendrait un autre fichier, hors de la vue de
# cette garde. `cloudflared` est la seule entrée, par une connexion sortante (D45).
EXPOSING_KEYS = ["ports", "network_mode", "networks", "extends"]

# Les clés du fichier qui ajoutent des services ou des réseaux : un réseau déclaré, même `default`,
# peut devenir externe ; un fichier inclus apporte ses propres services.
EXPOSING_TOP_LEVEL_KEYS = ["networks", "include"]

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
    """Les services d'un fichier Compose du dépôt, par nom — jamais une table vide : un test qui
    parcourt les services passerait à vide sur un fichier qu'on ne sait plus lire."""
    services = compose_services(compose_file.read_text(encoding="utf-8"))
    assert services, f"{compose_file.name} : aucun service lu"
    return cast(dict[str, dict[str, Any]], services)


def exposure_findings(text: str) -> list[str]:
    """Ce par quoi un fichier Compose rendrait un service joignable hors du réseau du projet.

    Returns:
        Un constat par clé de `EXPOSING_TOP_LEVEL_KEYS` portée par le fichier et par clé de
        `EXPOSING_KEYS` portée par un service. Liste vide : chaque service, tout entier écrit dans
        ce fichier, n'a que le réseau privé du projet.
    """
    document: dict[str, Any] = yaml.safe_load(text)
    declared = [f"fichier : {key}" for key in EXPOSING_TOP_LEVEL_KEYS if key in document]
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


def interpolations(text: str) -> list[re.Match[str]]:
    """Les interpolations d'un fichier Compose, lues dans ses chaînes — commentaires exclus."""
    return [
        match for value in strings(yaml.safe_load(text)) for match in INTERPOLATION.finditer(value)
    ]


def interpolation_findings(text: str) -> list[str]:
    """Les interpolations d'un fichier Compose qui ne sont pas exigées (`${NOM:?…}`) : une variable
    absente y deviendrait une valeur vide ou une valeur par défaut, au lieu d'arrêter Compose."""
    return [
        match.group()
        for match in interpolations(text)
        if match["bare"] or not match["modifier"].startswith(":?")
    ]


def probe_findings(text: str) -> list[str]:
    """Les services d'un fichier Compose qui n'ont pas de sonde à eux — que `up --wait` déclare
    prêts dès qu'ils tournent, même en boucle de redémarrage (mesure : en-tête de
    `infra/compose.yml`). Les images du dépôt et celle de `cloudflared` n'en déclarent aucune : un
    `healthcheck:` sans `test` n'hériterait de rien.

    Returns:
        Un constat par service sans `healthcheck.test`, ou dont la sonde est coupée (`disable`,
        `["NONE"]`). Liste vide : `--wait` attend que chaque service soit sain.
    """
    services: dict[str, dict[str, Any]] = yaml.safe_load(text)["services"]
    probes = {
        name: cast(dict[str, Any], service.get("healthcheck") or {})
        for name, service in services.items()
    }
    return [
        name
        for name, probe in probes.items()
        if not probe.get("test") or probe.get("disable") or probe["test"] == ["NONE"]
    ]


def environment_value(value: str) -> str:
    """Un fichier Compose minimal dont le seul service reçoit une variable de la valeur donnée."""
    return f"services:\n  api:\n    environment:\n      A: '{value}'\n"


# Forme → constat attendu (`True`) ou aucun (`False`).
INTERPOLATION_FORMS = {
    "exigée": (environment_value("${X:?}"), False),
    "exigée, avec message": (environment_value("${X:?absente}"), False),
    "sans modificateur": (environment_value("${X}"), True),
    "valeur par défaut": (environment_value("${X:-d}"), True),
    "exigée si absente seulement": (environment_value("${X?}"), True),
    "sans accolades": (environment_value("redis://redis:6379/$X"), True),
    "accolades échappées": (environment_value("$${X}"), False),
    "nom échappé": (environment_value("$$X"), False),
    "échappement suivi d'un nom": (environment_value("$$$X"), True),
    "deux échappements": (environment_value("$$$$X"), False),
}


def single_service(block: str) -> str:
    """Un fichier Compose minimal dont le seul service porte le bloc donné."""
    return f"services:\n  caddy:\n    image: caddy\n{block}"


# Forme → constat attendu (`True`) ou aucun (`False`).
EXPOSURE_FORMS = {
    "aucune clé de réseau": (single_service(""), False),
    "port exposé au réseau du projet seulement": (single_service('    expose: ["80"]\n'), False),
    "port publié": (single_service('    ports: ["80:80"]\n'), True),
    "port publié, syntaxe longue": (single_service("    ports:\n      - target: 80\n"), True),
    "réseau de l'hôte": (single_service("    network_mode: host\n"), True),
    "réseau d'un autre service": (single_service('    network_mode: "service:api"\n'), True),
    "réseau nommé": (
        single_service("    networks: [bordure]\n") + "networks:\n  bordure: {}\n",
        True,
    ),
    "réseau par défaut redéfini en externe": (
        single_service("") + "networks:\n  default:\n    name: host\n    external: true\n",
        True,
    ),
    "fichier inclus": ("include: [autre.yml]\n" + single_service(""), True),
    "service étendu": (
        single_service("    extends:\n      file: autre.yml\n      service: web\n"),
        True,
    ),
}


# Forme → constat attendu (`True`) ou aucun (`False`).
PROBE_FORMS = {
    "sonde": (single_service('    healthcheck:\n      test: ["CMD", "true"]\n'), False),
    "sonde par le shell": (single_service("    healthcheck:\n      test: true\n"), False),
    "sans sonde": (single_service(""), True),
    "réglages sans commande": (single_service("    healthcheck:\n      interval: 3s\n"), True),
    "sonde coupée": (
        single_service('    healthcheck:\n      test: ["CMD", "true"]\n      disable: true\n'),
        True,
    ),
    "sonde NONE": (single_service('    healthcheck:\n      test: ["NONE"]\n'), True),
}


@pytest.mark.parametrize(("text", "expected"), PROBE_FORMS.values(), ids=PROBE_FORMS.keys())
def test_la_garde_des_sondes_rend_son_verdict_sur_chaque_forme(text: str, expected: bool) -> None:
    """Chaque forme recensée : signalée si, et seulement si, le service n'a pas de sonde."""
    assert bool(probe_findings(text)) is expected, probe_findings(text)


def test_chaque_service_de_production_a_une_sonde() -> None:
    """Le job de déploiement rougit par `docker compose up -d --wait` : il ne voit un conteneur
    qui ne démarre pas que si ce conteneur a une sonde (`probe_findings`)."""
    assert probe_findings(COMPOSE_PROD.read_text(encoding="utf-8")) == []


def test_les_metriques_de_cloudflared_restent_dans_son_conteneur() -> None:
    """Le serveur de métriques que sa sonde interroge écoute par défaut sur toutes les interfaces,
    donc sur le réseau du projet : il n'écoute que dans le conteneur."""
    metrics = read_services(COMPOSE_PROD)["cloudflared"]["environment"]["TUNNEL_METRICS"]

    assert metrics.startswith("127.0.0.1:")


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
    images = {
        name: read_services(path)[service]["image"] for name, path in COMPOSE_BY_ENVIRONMENT.items()
    }

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


@pytest.mark.parametrize(
    "compose_file", COMPOSE_BY_ENVIRONMENT.values(), ids=COMPOSE_BY_ENVIRONMENT.keys()
)
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
    text = COMPOSE_PROD.read_text(encoding="utf-8")
    found = interpolations(text)

    assert found, "aucune interpolation lue — le motif a-t-il cessé de mordre ?"
    assert interpolation_findings(text) == []
    names = {match["name"] or match["bare"] for match in found}
    assert names == set(declared_variables(PROD_ENV_EXAMPLE))


@pytest.mark.parametrize(
    ("text", "expected"), INTERPOLATION_FORMS.values(), ids=INTERPOLATION_FORMS.keys()
)
def test_la_garde_des_interpolations_rend_son_verdict_sur_chaque_forme(
    text: str, expected: bool
) -> None:
    """Chaque forme d'interpolation recensée : signalée si, et seulement si, une variable absente
    ne ferait pas échouer la résolution."""
    assert bool(interpolation_findings(text)) is expected, interpolation_findings(text)


@pytest.mark.parametrize(
    "compose_file", COMPOSE_BY_ENVIRONMENT.values(), ids=COMPOSE_BY_ENVIRONMENT.keys()
)
def test_make_compose_config_resout_chaque_fichier_compose(compose_file: Path) -> None:
    """Le job `infra` ne prouve la résolution que des fichiers que la cible lui fait résoudre :
    sans sa ligne, le Compose de production n'était résolu nulle part, et toute la suite restait
    verte (mesuré à la relecture de la PR #69)."""
    printed = make_dry_run("compose-config")

    assert f"-f infra/{compose_file.name} config --quiet" in printed


def test_les_tests_de_base_tournent_sur_l_image_postgres_du_compose() -> None:
    """Les tests vérifient les contraintes sur le moteur et les extensions du développement — donc
    de la production, à la même image."""
    assert read_services(COMPOSE_DEV)["postgres"]["image"] == POSTGRES_IMAGE


@pytest.mark.parametrize(
    "compose_file", COMPOSE_BY_ENVIRONMENT.values(), ids=COMPOSE_BY_ENVIRONMENT.keys()
)
@pytest.mark.parametrize(("variable", "expected"), sorted(SERVICE_ADDRESS_OVERRIDES.items()))
def test_le_service_api_recoit_ses_adresses_de_service(
    compose_file: Path, variable: str, expected: str
) -> None:
    """Les retirer ne fait rougir ni `make test` ni `make compose-config` : la pile démarre, puis
    `api` sort en 1 sur une connexion refusée pendant que les autres services restent vivants."""
    environment = read_services(compose_file)["api"]["environment"]

    assert expected in environment[variable]


@pytest.mark.parametrize(
    "compose_file", COMPOSE_BY_ENVIRONMENT.values(), ids=COMPOSE_BY_ENVIRONMENT.keys()
)
def test_la_sonde_de_postgres_interroge_le_reseau_et_non_le_socket_local(
    compose_file: Path,
) -> None:
    """Une sonde aveugle à l'état TCP déclare saine une base qu'`api` ne peut pas encore joindre.

    C'est le seul état qui compte : `api` se connecte par le réseau du Compose, jamais par le
    socket Unix du conteneur `postgres`.
    """
    probe = " ".join(read_services(compose_file)["postgres"]["healthcheck"]["test"])

    assert "pg_isready" in probe and POSTGRES_PROBE_HOST in probe
