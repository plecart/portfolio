"""Tests des fichiers d'infrastructure : image `api`, point d'entrée, Compose de développement.

Ces tests lisent des fichiers comme du texte, sans rien construire ni démarrer. Ils gardent des
invariants dont la violation ne se voit qu'à l'exécution, et tard : un conteneur qui tourne en
root, des signaux qui n'atteignent jamais le serveur, une adresse de service revenue à
`localhost`. Chacun d'eux a été éprouvé par mutation — retiré du code, il rend ce test rouge.

Que l'image **se construise** et que la pile **démarre** est prouvé ailleurs : par le job `infra`
de la CI, et par la pile qu'on regarde tourner.
"""

import re
from pathlib import Path

import pytest

# `test_infra.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPOSITORY_ROOT / "infra" / "api" / "Dockerfile"
ENTRYPOINT = REPOSITORY_ROOT / "infra" / "api" / "entrypoint.sh"
COMPOSE_DEV = REPOSITORY_ROOT / "infra" / "compose.dev.yml"
MAKEFILE = REPOSITORY_ROOT / "Makefile"
PYTHON_VERSION_FILE = REPOSITORY_ROOT / ".python-version"

# Le nom de l'image, déclaré des deux côtés : le `Makefile` le pose pour `docker build -t` et
# l'exporte, le Compose le reprend en défaut pour qu'un `docker compose` lancé à la main ne
# fabrique pas une seconde image sous un nom à lui. Deux noms qui dériveraient donneraient deux
# images du même Dockerfile, et #15 ne saurait plus laquelle publier.
MAKEFILE_IMAGE = re.compile(r"^API_IMAGE \?= (?P<name>\S+)$", re.MULTILINE)
COMPOSE_IMAGE = re.compile(r"^\s*image: \$\{API_IMAGE:-(?P<name>[^}]+)\}$", re.MULTILINE)

# Toute image de base qui embarque un interpréteur porte sa version dans son nom. Le motif les
# capture toutes : un seul étage qui dériverait suffirait à faire tourner l'application sur une
# version que le dépôt n'épingle nulle part.
BASE_IMAGE_VERSION = re.compile(r"^FROM python:(\d+\.\d+)[.-]", re.MULTILINE)

# La dernière instruction du point d'entrée, mot pour mot. Sans `exec`, le shell reste PID 1 :
# `docker stop` ne l'atteint jamais et le serveur est tué au bout du délai de grâce.
HAND_OVER = 'exec "$@"'

# La sonde de `postgres` doit interroger le **réseau**, pas le socket Unix local. Pendant
# `initdb`, l'image postgres démarre un serveur temporaire avec `listen_addresses=''` : il
# accepte déjà le socket et refuse encore TCP. Mesuré sur `pgvector/pgvector:pg16` dans cet
# état — `pg_isready -U … -d …` rend « accepting connections » (0) quand la même sonde avec
# `-h 127.0.0.1` rend « no response » (2). Sans cet hôte, `service_healthy` peut se déclencher
# alors qu'`api` ne peut joindre personne, et ses migrations échouent au premier `up`.
POSTGRES_PROBE_HOST = "-h 127.0.0.1"

# Les adresses que le service `api` doit recomposer avec les noms de service. `env_file: ../.env`
# apporte celles du poste (`localhost`), qui ne désignent rien depuis un conteneur ; ces trois
# lignes les remplacent, et `environment:` prime sur `env_file:`. Les retirer laisse
# `docker compose config` vert et ne casse qu'au démarrage — d'où ce test.
SERVICE_ADDRESS_OVERRIDES = {
    "DATABASE_URL": "@postgres:5432/",
    "MEDIA_ROOT": "/app/media",
    "REDIS_URL": "redis://redis:6379",
}

# Les fichiers qu'un outil Linux lit dans la **copie de travail** : ce que le shell du conteneur
# exécute, ce que buildkit analyse, ce dont Compose tire des valeurs, et l'épingle de version que
# `uv` relit dans l'image. Tout fichier ajouté à `infra/` et lu par un conteneur entre dans un de
# ces motifs — et chacun est vérifié séparément, sinon un motif devenu aveugle passerait inaperçu.
CONTAINER_TEXT_GLOBS = [
    "infra/**/*.sh",
    "infra/**/Dockerfile",
    "infra/**/*.env",
    ".dockerignore",
    ".env.example",
    ".python-version",
]


def shell_instructions(script: Path) -> list[str]:
    """Les lignes exécutables d'un script shell — ni vides, ni commentaires.

    Args:
        script: le script à lire.

    Returns:
        Les lignes restantes, détourées de leurs espaces, dans l'ordre du fichier. C'est cet
        ordre qui porte les invariants : un commentaire déplacé ne doit pas faire rougir un test.
    """
    return [
        stripped
        for line in script.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]


def test_les_images_de_base_suivent_la_version_epinglee() -> None:
    """Deux épingles qui divergeraient en silence ne vaudraient pas mieux qu'aucune.

    Même garde que pour Node, où `.nvmrc` et le champ `engines` portent la même valeur sous la
    surveillance d'un test (`.claude/pipeline.config.md`, section « Stack »). `uv` lit
    `.python-version` sur le poste et en CI, mais une image de base porte sa version dans son
    nom : rien ne relie les deux, sinon ce test.
    """
    pinned = PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    found = BASE_IMAGE_VERSION.findall(DOCKERFILE.read_text(encoding="utf-8"))

    assert found, "aucune image de base `python:` trouvée — le motif a-t-il cessé de mordre ?"
    assert set(found) == {pinned}


def test_le_compose_et_le_makefile_nomment_la_meme_image() -> None:
    """Mesuré avant correction : `make build` et `make dev` produisaient deux images distinctes."""
    from_makefile = MAKEFILE_IMAGE.search(MAKEFILE.read_text(encoding="utf-8"))
    from_compose = COMPOSE_IMAGE.search(COMPOSE_DEV.read_text(encoding="utf-8"))

    assert from_makefile, "`API_IMAGE ?=` a disparu du `Makefile`"
    assert from_compose, (
        "le service `api` ne reprend plus `${API_IMAGE}` — Compose se nommerait seul"
    )
    assert from_makefile.group("name") == from_compose.group("name")


def test_le_point_d_entree_cede_la_place_a_la_commande() -> None:
    """Sans `exec`, le shell reste PID 1 et `docker stop` n'arrête jamais proprement le serveur."""
    instructions = shell_instructions(ENTRYPOINT)

    assert instructions, "point d'entrée vide — le fichier a-t-il changé de forme ?"
    assert instructions[-1] == HAND_OVER


def test_le_point_d_entree_joue_ses_etapes_avant_la_commande() -> None:
    """L'ordre est la décision : démarrer le serveur sur une base non migrée produit des erreurs
    à la première requête, loin de leur cause."""
    instructions = shell_instructions(ENTRYPOINT)
    steps = [index for index, line in enumerate(instructions) if line.startswith("for step in")]

    assert steps, "la boucle d'étapes a disparu du point d'entrée"
    assert HAND_OVER in instructions, "la remise de main a disparu du point d'entrée"
    assert steps[0] < instructions.index(HAND_OVER)


def test_l_image_bascule_sur_un_utilisateur_non_root() -> None:
    """Un `USER` retiré laisse l'image tourner en root, et aucune autre porte ne le voit."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    creation = re.search(r"^RUN useradd .*?(?P<name>\w+)\s*\\?$", dockerfile, re.MULTILINE)
    switch = re.search(r"^USER (?P<name>\w+)$", dockerfile, re.MULTILINE)

    assert creation, "aucun `RUN useradd` — l'image crée-t-elle encore son utilisateur ?"
    assert switch, "aucune instruction `USER` : l'image démarrerait en root"
    assert switch.group("name") != "root"
    assert creation.start() < switch.start(), "`USER` doit suivre la création de l'utilisateur"


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


@pytest.mark.parametrize("glob", CONTAINER_TEXT_GLOBS)
def test_chaque_motif_de_fichier_de_conteneur_apparie_un_fichier(glob: str) -> None:
    """Une garde d'union ne voit pas un motif devenu aveugle : les autres la remplissent.

    Mesuré : un script renommé sans son suffixe `.sh` échappait à la fois à `.gitattributes` et
    au test de fins de ligne, qui restait vert parce que d'autres motifs peuplaient la liste.
    """
    assert list(REPOSITORY_ROOT.glob(glob)), f"le motif « {glob} » n'apparie plus aucun fichier"


def test_aucun_fichier_lu_par_un_conteneur_ne_porte_de_retour_windows() -> None:
    """Un `\\r` dans ces fichiers casse à l'exécution, et seulement sur un poste Windows.

    `core.autocrlf` réécrit la copie de travail en CRLF ; le dépôt garde du LF, donc la CI Linux
    ne voit jamais rien. `#!/bin/sh` suivi d'un `\\r` donne « exec … : no such file or
    directory » au démarrage du conteneur — sur une image pourtant construite verte.
    """
    checked = sorted(path for glob in CONTAINER_TEXT_GLOBS for path in REPOSITORY_ROOT.glob(glob))

    assert checked, "aucun fichier trouvé — les motifs ont-ils cessé de mordre ?"
    faulty = [path for path in checked if b"\r\n" in path.read_bytes()]
    assert not faulty, f"{len(checked)} fichiers repassés, fins de ligne Windows dans {faulty}"
