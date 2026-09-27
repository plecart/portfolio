"""Tests des fichiers d'infrastructure : image `api`, point d'entrée, Compose de développement.

Ces tests lisent des fichiers, ou interrogent les outils qui les lisent — `make --dry-run`, Docker
pour le contexte de build —, sans construire d'image ni démarrer de conteneur. Ils gardent des
invariants dont la violation ne se voit qu'à l'exécution, et tard : un conteneur qui tourne en
root, des signaux qui n'atteignent jamais le serveur, une adresse de service revenue à
`127.0.0.1`. Chacun d'eux a été éprouvé par mutation — retiré du code, il rend ce test rouge.

Que l'image **se construise** et que la pile **démarre** est prouvé ailleurs : par le job `infra`
de la CI, et par la pile qu'on regarde tourner.
"""

import io
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml
from config.env import Env
from containers import POSTGRES_IMAGE
from test_supply_chain import dockerfile_instructions

# `test_infra.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPOSITORY_ROOT / "infra" / "api" / "Dockerfile"
ENTRYPOINT = REPOSITORY_ROOT / "infra" / "api" / "entrypoint.sh"
COMPOSE_DEV = REPOSITORY_ROOT / "infra" / "compose.dev.yml"
MAKEFILE = REPOSITORY_ROOT / "Makefile"
PYTHON_VERSION_FILE = REPOSITORY_ROOT / ".python-version"
DOCKERIGNORE = REPOSITORY_ROOT / ".dockerignore"

# Une arborescence témoin du front : ce que sa compilation produit, et tout ce qui l'entoure.
WEB_TREE = [
    "apps/web/dist/index.html",
    "apps/web/dist/assets/index.js",
    "apps/web/index.html",
    "apps/web/package.json",
    "apps/web/src/main.tsx",
    "apps/web/node_modules/react/index.js",
]
WEB_BUILD_OUTPUT = {"apps/web/dist/index.html", "apps/web/dist/assets/index.js"}

# Le gabarit des aperçus de lien (ADR 0011) : la vue de #14 le lit à ce chemin, sa valeur par
# défaut (brief de #15, décision 10).
INDEX_COPY = "COPY apps/web/dist/index.html /app/web/index.html"

# La commande qui compile le front, celle de `make web-build`.
FRONT_BUILD = "npm run build"

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

# Les variables que lit le back : un `ARG` qui en nommerait une la réclamerait au build, un `ENV`
# la figerait dans l'image. Un montage de secret, lui, en réclamerait une quelle qu'elle soit.
ENV_FIELDS = re.compile(rf"\b(?:{'|'.join(Env.model_fields)})\b")
BUILD_DECLARATION = re.compile(r"^\s*(?:ARG|ENV)\b", re.IGNORECASE)
SECRET_MOUNT = "--mount=type=secret"

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
# apporte celles du poste (`127.0.0.1`), qui ne désignent rien depuis un conteneur ; ces trois
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

# Les fichiers qui citent des chemins dans leur prose plutôt que dans du code : commentaires
# d'infrastructure, documentation, workflows. Un module de test renommé y laisse des renvois
# entrants qu'aucune porte ne voit — mesuré : le Dockerfile a continué de désigner
# `test_image.py` après que ce module soit devenu `test_infra.py`, et seule une relecture l'a vu.
PROSE_GLOBS = ["infra/**/*", "*.md", "Makefile", ".github/workflows/*.yml", ".claude/**/*.md"]
TESTS_DIRECTORY = REPOSITORY_ROOT / "apps" / "api" / "tests"
TEST_MODULE_REFERENCE = re.compile(r"apps/api/tests/(?P<name>\w+\.py)")


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


def make_dry_run(target: str, **variables: str) -> str:
    """Les commandes que `make` exécuterait pour `target`, sans les exécuter.

    Args:
        target: la cible du `Makefile`.
        variables: des variables posées sur la ligne de commande, qui priment sur le `Makefile`.

    Returns:
        La sortie de `make --dry-run`, variables développées — y compris celles des appels
        récursifs à `$(MAKE)`, que `--dry-run` parcourt sans rien exécuter.
    """
    return subprocess.run(
        ["make", "--dry-run", target, *(f"{name}={value}" for name, value in variables.items())],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def build_context(root: Path) -> set[str]:
    """Les fichiers que Docker enverrait au build depuis `root`, selon son `.dockerignore`.

    Docker lui-même en juge : l'arborescence est copiée dans une image vide, exportée en archive
    sur la sortie standard. Aucune image n'est tirée, rien n'est chargé dans le moteur.

    Args:
        root: le dossier de contexte, `.dockerignore` compris.

    Returns:
        Les chemins des fichiers reçus, relatifs à `root`.
    """
    dockerfile = root.parent / "Dockerfile"
    dockerfile.write_text("FROM scratch\nCOPY . /\n", encoding="utf-8")
    export = ["docker", "buildx", "build", "-f", str(dockerfile), "--output", "type=tar,dest=-"]
    archive = subprocess.run([*export, str(root)], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as received:
        return {member.name.removeprefix("./") for member in received if member.isfile()}


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


def test_les_tests_de_base_tournent_sur_l_image_postgres_du_compose() -> None:
    """Les tests vérifient les contraintes sur le moteur et les extensions du développement.

    Lu avec l'analyseur YAML, pas avec un motif : c'est la valeur que Compose lira qui compte.
    """
    compose = yaml.safe_load(COMPOSE_DEV.read_text(encoding="utf-8"))

    assert compose["services"]["postgres"]["image"] == POSTGRES_IMAGE


def test_la_cible_build_produit_une_commande_complete() -> None:
    """Lit la commande que `make` produira vraiment, expansion des variables comprise.

    Les autres tests de ce module comparent deux textes ; celui-ci interroge `make`. La
    différence n'est pas théorique — deux défauts sont passés par là, tous deux invisibles à la
    lecture du `Makefile` et à toutes les portes locales :

    - un `export API_IMAGE` posé **avant** l'affectation `?=` définit la variable à vide, `?=`
      cesse d'assigner, et l'image part sans étiquette (`-t  .`) ;
    - `docker build` utilise **toujours** le builder par défaut du moteur, quel que soit
      `docker buildx use`. La documentation Docker vise explicitement ce cas : « If you use
      build scripts, such as `make`, that use the `docker build` command, update your build
      commands to `docker buildx build`. » Sans quoi l'export de cache échoue en CI.
    """
    declared = MAKEFILE_IMAGE.search(MAKEFILE.read_text(encoding="utf-8"))
    assert declared, "`API_IMAGE ?=` a disparu du `Makefile`"

    printed = make_dry_run("build")
    tag = re.search(r"-t\s+(?P<name>\S+)", printed)

    assert "docker buildx build" in printed, "`docker build` ignorerait le builder sélectionné"
    assert tag, "la commande de build ne porte plus d'étiquette `-t`"
    assert tag.group("name") == declared.group("name")


@pytest.mark.parametrize("target", ["build", "dev"])
def test_build_et_dev_compilent_le_front_s_il_manque(tmp_path: Path, target: str) -> None:
    """Les images copient le front compilé : sans lui, leur build échouerait. `build` et `dev` le
    compilent donc s'il manque, et le reprennent tel quel sinon — `make web-build` le recompile à
    la demande (brief de #15, critères du lot 1).

    Le front témoin vit dans un dossier temporaire : celui du dépôt n'est ni lu ni touché.
    """
    web = tmp_path / "web"
    missing = make_dry_run(target, WEB=web.as_posix())
    compiled = web / "dist" / "index.html"
    compiled.parent.mkdir(parents=True)
    compiled.write_text("", encoding="utf-8")

    assert FRONT_BUILD in missing
    assert FRONT_BUILD not in make_dry_run(target, WEB=web.as_posix())


def test_le_contexte_de_build_ne_porte_du_front_que_sa_compilation(tmp_path: Path) -> None:
    """`caddy` sert `apps/web/dist`, `api` en garde `index.html` (ADR 0014) : ce dossier entre dans
    le contexte de build, et rien d'autre du front — ni ses sources, ni ses dépendances, qui
    pèseraient sur chaque build sans rien apporter aux images.

    Docker en juge, avec le `.dockerignore` du dépôt, sur une arborescence témoin : c'est la
    dernière ligne qui correspond qui décide (doc Docker), et un motif qui l'imiterait ici
    laisserait passer les formes qu'il n'a pas prévues.
    """
    root = tmp_path / "contexte"
    for name in WEB_TREE:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    shutil.copy(DOCKERIGNORE, root / ".dockerignore")

    sent = build_context(root)

    assert {name for name in sent if name.startswith("apps/web/")} == WEB_BUILD_OUTPUT


def test_l_image_api_garde_le_gabarit_du_front_la_ou_14_le_lit() -> None:
    """Le gabarit des aperçus de lien vit en `/app/web/index.html`, chemin par défaut du réglage de
    #14 (brief de #15, décision 10) : déplacé, la vue de #14 ne le trouverait plus."""
    instructions = [
        whole for _, whole in dockerfile_instructions(DOCKERFILE.read_text(encoding="utf-8"))
    ]

    assert INDEX_COPY in instructions


def test_le_build_de_l_image_ne_demande_aucun_secret() -> None:
    """Le build n'attend aucun secret : le job `infra` construit l'image sans en avoir aucun.

    `collectstatic` charge pourtant les réglages, donc `Env.load()` (ADR 0014) : ses valeurs
    factices vivent sur sa ligne de `RUN`. Un `ARG` qui nommerait une variable d'`Env` la
    réclamerait à la commande de build, un montage de secret aussi ; un `ENV` la figerait dans
    l'image, lisible par `docker inspect`.
    """
    instructions = [
        whole for _, whole in dockerfile_instructions(DOCKERFILE.read_text(encoding="utf-8"))
    ]

    assert instructions, "aucune instruction lue — le Dockerfile a-t-il changé de forme ?"
    assert [i for i in instructions if BUILD_DECLARATION.match(i) and ENV_FIELDS.search(i)] == []
    assert [i for i in instructions if SECRET_MOUNT in i] == []


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


def test_aucun_renvoi_vers_un_module_de_test_inexistant() -> None:
    """Un module renommé laisse derrière lui des renvois que rien ne suit.

    La population d'un renommage inclut ses **renvois entrants** : la prose qui le désigne. Ils
    ne cassent aucune porte, se lisent comme justes, et n'échouent que pour le lecteur qui suit
    le lien — c'est-à-dire trop tard.
    """
    cited: dict[str, set[str]] = {}
    for glob in PROSE_GLOBS:
        for path in REPOSITORY_ROOT.glob(glob):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for reference in TEST_MODULE_REFERENCE.finditer(text):
                cited.setdefault(reference.group("name"), set()).add(path.name)

    assert cited, "aucun renvoi trouvé — les motifs ont-ils cessé de mordre ?"
    missing = {
        name: sorted(where)
        for name, where in cited.items()
        if not (TESTS_DIRECTORY / name).exists()
    }
    assert not missing, f"{len(cited)} modules cités, introuvables : {missing}"


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
