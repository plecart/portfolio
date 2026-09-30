"""Tests des fichiers d'infrastructure : images, point d'entrée, Compose de développement.

Ces tests lisent des fichiers, ou interrogent les outils qui les lisent — `make --dry-run`, Docker
pour le contexte de build —, sans construire d'image ni démarrer de conteneur. Ils gardent des
invariants dont la violation ne se voit qu'à l'exécution, et tard : un conteneur qui tourne en
root, des signaux qui n'atteignent jamais le serveur, une adresse de service revenue à
`127.0.0.1`. Chacun d'eux a été éprouvé par mutation — retiré du code, il rend ce test rouge.

Que les images **se construisent** et que la pile **démarre** est prouvé ailleurs : par le job
`infra` de la CI, et par la pile qu'on regarde tourner. Le scan des images a ses propres tests,
dans `test_image_scan.py`, et leur publication dans `test_publication.py`.
"""

import io
import os
import re
import shutil
import subprocess
import tarfile
from collections.abc import Iterable, Mapping
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
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"

# Les Dockerfiles des images du dépôt, un par dossier `infra/<service>/` (ADR 0014).
IMAGE_DOCKERFILES = sorted(REPOSITORY_ROOT.glob("infra/*/Dockerfile"))

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

# Des fichiers d'environnement du poste, là où `git` les ignore : à toute profondeur, y compris
# sous l'exception `!apps/web/dist`, que l'image `caddy` sert telle quelle.
LOCAL_ENV_FILES = {".env", "apps/api/.env", "apps/web/dist/.env", "infra/caddy/.env"}

# Ce que l'image `api` sert, là où l'application le lit : le gabarit des aperçus de lien (ADR
# 0011), chemin par défaut du réglage de #14 (brief de #15, décision 10), et les fichiers
# statiques collectés au build, que WhiteNoise sert depuis `STATIC_ROOT` (ADR 0014). Copiés
# après le `chown` de `/app` : ils restent à `root`, en lecture seule pour l'application.
SERVED_COPIES = [
    "COPY apps/web/dist/index.html /app/web/index.html",
    "COPY --from=build /app/static /app/static",
]
CHOWN = "chown -R api:api /app"

# La commande qui compile le front, celle de `make web-build`.
FRONT_BUILD = "npm run build"

# Le préfixe du nom des images, déclaré des deux côtés : le `Makefile` le pose pour `-t` et
# l'exporte, le Compose le reprend en défaut pour qu'un `docker compose` lancé à la main ne
# fabrique pas une seconde image `api` sous un nom à lui. Deux noms qui dériveraient donneraient
# deux images du même Dockerfile, et la publication ne saurait plus laquelle pousser.
MAKEFILE_PREFIX = re.compile(r"^IMAGE_PREFIX \?= (?P<prefix>\S+)$", re.MULTILINE)
# L'export du préfixe : l'environnement du processus l'emporte sur `--env-file`, donc sur un
# préfixe que `infra/dev.env` nommerait (mesuré à la relecture de la PR #53).
MAKEFILE_EXPORT = re.compile(r"^export IMAGE_PREFIX$", re.MULTILINE)
COMPOSE_API_IMAGE = re.compile(
    r"^\s*image: \$\{IMAGE_PREFIX:-(?P<prefix>[^}]+)\}api$", re.MULTILINE
)

# Le préfixe sous lequel la CI publie les images sur GHCR (brief de #15, décision 8).
PUBLISH_PREFIX = "ghcr.io/plecart/portfolio-"

# Une commande de build telle que `make --dry-run` l'imprime : son Dockerfile, son étiquette.
BUILD_COMMAND = re.compile(
    r"^docker buildx build .*-f (?P<dockerfile>\S+) -t (?P<tag>\S+) \.$", re.MULTILINE
)

# L'étiquette d'une entrée du cache local de BuildKit, dans une commande de build imprimée.
CACHE_TAG = re.compile(r"--cache-(?:from|to) type=local,\S*?\btag=(?P<tag>[^,\s]+)")

# Les variables que le `Makefile` laisse surcharger (`?=`) : `make_dry_run` les retire de
# l'environnement hérité, pour vérifier le `Makefile` et non le shell qui lance le test
# (`process_environment.py`). Mesuré : `IMAGE_PREFIX` exporté faisait rougir le test du nom des
# images.
OVERRIDABLE = re.compile(r"^(?P<name>\w+)[ \t]*\?=", re.MULTILINE)

# Ce qu'un `make` englobant transmet au nôtre par l'environnement : ses options et les variables
# de sa ligne de commande (`MAKEFLAGS`, doc GNU make « Communicating Options to a Sub-make »), des
# makefiles à lire en plus (`MAKEFILES`), et sa profondeur (`MAKELEVEL`), qui fait imprimer au
# nôtre « Entering directory » comme à un sous-make. Mesuré : `make test IMAGE_PREFIX=zz-` faisait
# rougir le test du nom des images, et `make test` la lecture ligne à ligne de `make push`.
MAKE_CONTROL = {"MAKEFLAGS", "GNUMAKEFLAGS", "MAKEFILES", "MAKELEVEL"}

# Toute image de base qui embarque un interpréteur porte sa version dans son nom. Le motif les
# capture toutes : un seul étage qui dériverait suffirait à faire tourner l'application sur une
# version que le dépôt n'épingle nulle part.
BASE_IMAGE_VERSION = re.compile(r"^FROM python:(\d+\.\d+)[.-]", re.MULTILINE)

# Les variables que lit le back : un `ARG` qui en nommerait une la réclamerait au build, un `ENV`
# la figerait dans l'image — sans égard à la casse, comme `pydantic-settings` les lit
# (`case_sensitive=False` par défaut : `secret_key` configure `SECRET_KEY`, mesuré dans l'image à
# la relecture de la PR #53). Comme nom déclaré seulement, jamais dans une valeur :
# `ENV LOG_LEVEL=debug` ne déclare pas `DEBUG`. Un montage de secret, lui, en réclamerait une
# quelle qu'elle soit.
ENV_FIELDS = re.compile(rf"\s(?:{'|'.join(Env.model_fields)})(?=[=\s]|$)", re.IGNORECASE)
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
# exécute, ce que buildkit analyse, ce dont Compose tire des valeurs, l'épingle de version que
# `uv` relit dans l'image, et les exceptions que Trivy lit depuis son conteneur. Tout fichier
# ajouté à `infra/` et lu par un conteneur entre dans un de ces motifs — et chacun est vérifié
# séparément, sinon un motif devenu aveugle passerait inaperçu.
CONTAINER_TEXT_GLOBS = [
    "infra/**/*.sh",
    "infra/**/Dockerfile",
    "infra/**/*.env",
    ".dockerignore",
    ".env.example",
    ".python-version",
    ".trivyignore.yaml",
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


def run_make(
    *arguments: str,
    makefile: Path = MAKEFILE,
    directory: Path = REPOSITORY_ROOT,
    environment: Mapping[str, str] | None = None,
    **variables: str,
) -> subprocess.CompletedProcess[str]:
    """Lance `make` sur un `Makefile` — celui du dépôt par défaut —, sans hériter du shell qui
    lance les tests.

    Ni les variables que le `Makefile` laisse surcharger, ni ce qu'un `make` englobant transmet
    (`make test IMAGE_PREFIX=…`) ne viennent du processus qui lance les tests : seules celles que
    l'appel pose comptent.

    Args:
        arguments: les options et la cible de `make`.
        makefile: le fichier de commandes — celui du dépôt, ou une copie témoin.
        directory: le dossier où `make` tourne — la racine du dépôt, ou une arborescence témoin.
        environment: des variables posées dans l'environnement, comme la CI les passe.
        variables: des variables posées sur la ligne de commande, qui priment sur le `Makefile`.

    Returns:
        Le processus terminé, sorties capturées ; son code de sortie n'est pas vérifié.
    """
    ignored = set(OVERRIDABLE.findall(makefile.read_text(encoding="utf-8"))) | MAKE_CONTROL
    inherited = {name: value for name, value in os.environ.items() if name not in ignored}
    assignments = [f"{name}={value}" for name, value in variables.items()]
    return subprocess.run(
        ["make", "-f", str(makefile), *arguments, *assignments],
        cwd=directory,
        env=inherited | dict(environment or {}),
        capture_output=True,
        text=True,
        check=False,
    )


def make_dry_run(
    target: str,
    directory: Path = REPOSITORY_ROOT,
    environment: Mapping[str, str] | None = None,
    **variables: str,
) -> str:
    """Les commandes que le `Makefile` du dépôt exécuterait pour `target`, sans les exécuter.

    Returns:
        La sortie de `make --dry-run`, variables développées — y compris celles des appels
        récursifs à `$(MAKE)`, que `--dry-run` parcourt sans rien exécuter.
    """
    printed = run_make(
        "--dry-run",
        target,
        makefile=MAKEFILE,
        directory=directory,
        environment=environment,
        **variables,
    )
    printed.check_returncode()
    return printed.stdout


def built_images(printed: str) -> dict[str, str]:
    """Les images d'une sortie de `make --dry-run build` : chaque Dockerfile, et son étiquette."""
    return {match["dockerfile"]: match["tag"] for match in BUILD_COMMAND.finditer(printed)}


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


def write_tree(root: Path, names: Iterable[str]) -> None:
    """Une arborescence témoin de fichiers vides sous `root`, avec le `.dockerignore` du dépôt.

    Args:
        root: le dossier de contexte à créer.
        names: les chemins des fichiers, relatifs à `root`.
    """
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    shutil.copy(DOCKERIGNORE, root / ".dockerignore")


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
    makefile = MAKEFILE.read_text(encoding="utf-8")
    from_makefile = MAKEFILE_PREFIX.search(makefile)
    from_compose = COMPOSE_API_IMAGE.search(COMPOSE_DEV.read_text(encoding="utf-8"))

    assert from_makefile, "`IMAGE_PREFIX ?=` a disparu du `Makefile`"
    assert from_compose, (
        "le service `api` ne reprend plus `${IMAGE_PREFIX}` — Compose se nommerait seul"
    )
    assert from_makefile.group("prefix") == from_compose.group("prefix")
    assert MAKEFILE_EXPORT.search(makefile), (
        "`export IMAGE_PREFIX` a disparu : `infra/dev.env` pourrait nommer l'image de `make dev`"
    )


def test_les_tests_de_base_tournent_sur_l_image_postgres_du_compose() -> None:
    """Les tests vérifient les contraintes sur le moteur et les extensions du développement.

    Lu avec l'analyseur YAML, pas avec un motif : c'est la valeur que Compose lira qui compte.
    """
    compose = yaml.safe_load(COMPOSE_DEV.read_text(encoding="utf-8"))

    assert compose["services"]["postgres"]["image"] == POSTGRES_IMAGE


def test_make_build_construit_une_image_par_dossier_d_infra() -> None:
    """Une image par dossier `infra/<service>/` qui porte un `Dockerfile`, nommée
    `<préfixe><service>` (ADR 0014) : rien de plus, rien de moins.

    Lit les commandes que `make` produira vraiment, expansion des variables comprise. Deux
    défauts sont passés par là, invisibles à la lecture du `Makefile` et à toutes les portes
    locales :

    - un `export` posé **avant** l'affectation `?=` définit la variable à vide, `?=` cesse
      d'assigner, et l'image part sous un autre nom — mesuré sur l'ancien nom d'image, qui partait
      sans étiquette (`-t  .`) ;
    - `docker build` utilise **toujours** le builder par défaut du moteur, quel que soit
      `docker buildx use`. La documentation Docker vise explicitement ce cas : « If you use
      build scripts, such as `make`, that use the `docker build` command, update your build
      commands to `docker buildx build`. » Sans quoi l'export de cache échoue en CI.
    """
    declared = MAKEFILE_PREFIX.search(MAKEFILE.read_text(encoding="utf-8"))
    assert declared, "`IMAGE_PREFIX ?=` a disparu du `Makefile`"
    prefix = declared["prefix"]
    expected = {
        path.relative_to(REPOSITORY_ROOT).as_posix(): prefix + path.parent.name
        for path in IMAGE_DOCKERFILES
    }

    printed = make_dry_run("build")

    assert built_images(printed) == expected, printed


def test_ajouter_un_dossier_a_infra_suffit_a_construire_son_image(tmp_path: Path) -> None:
    """`make build` trouve les images d'après les dossiers, pas d'après une liste à tenir : un
    dossier de plus est une image de plus, un dossier sans `Dockerfile` n'en est pas une.

    Le `Makefile` du dépôt tourne sur une arborescence témoin, front compilé compris.
    """
    for service in ("alpha", "beta"):
        (tmp_path / "infra" / service).mkdir(parents=True)
        (tmp_path / "infra" / service / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "infra" / "outils").mkdir()
    compiled = tmp_path / "apps" / "web" / "dist" / "index.html"
    compiled.parent.mkdir(parents=True)
    compiled.write_text("", encoding="utf-8")

    built = built_images(make_dry_run("build", directory=tmp_path))

    assert sorted(built) == ["infra/alpha/Dockerfile", "infra/beta/Dockerfile"]


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
    write_tree(root, WEB_TREE)

    sent = build_context(root)

    assert {name for name in sent if name.startswith("apps/web/")} == WEB_BUILD_OUTPUT


def test_le_contexte_de_build_ne_porte_aucun_fichier_d_environnement(tmp_path: Path) -> None:
    """Un `.env` envoyé au build entre dans l'image dès qu'un `COPY` prend son dossier entier —
    mesuré à la relecture de la PR #53 : `apps/api/.env` finissait dans l'image `api`. `git`
    l'ignore à toute profondeur ; le `.dockerignore` doit en faire autant."""
    root = tmp_path / "contexte"
    write_tree(root, LOCAL_ENV_FILES)

    assert build_context(root) & LOCAL_ENV_FILES == set()


@pytest.mark.parametrize("copy", SERVED_COPIES)
def test_l_image_api_copie_ce_qu_elle_sert_apres_le_chown(copy: str) -> None:
    """Déplacée, la copie perd son lecteur (la vue de #14, WhiteNoise) ; retirée, l'image se
    construit encore et la CI reste verte, puis l'admin répond 500 faute de statiques (mesuré à la
    relecture de la PR #53) ; faite avant le dernier `chown`, elle donne ces fichiers à
    l'application."""
    instructions = [
        whole for _, whole in dockerfile_instructions(DOCKERFILE.read_text(encoding="utf-8"))
    ]
    chown = [index for index, instruction in enumerate(instructions) if CHOWN in instruction]

    assert chown, "le `chown` de `/app` a disparu — le motif a-t-il cessé de mordre ?"
    assert copy in instructions
    assert instructions.index(copy) > chown[-1]


def ci_build_flags(job: str) -> str | None:
    """Les drapeaux qu'une étape du job `job` de la CI passe au build par `DOCKER_BUILD_FLAGS`."""
    steps = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"][job]["steps"]
    return next(
        (
            step["env"]["DOCKER_BUILD_FLAGS"]
            for step in steps
            if "DOCKER_BUILD_FLAGS" in step.get("env", {})
        ),
        None,
    )


# Les jobs qui construisent les images avec le cache local, et les entrées que chaque image y
# cite : `infra` le lit et l'écrit ; `publish` le lit seulement — il reconstruit ce qu'`infra`
# vient d'y écrire (ADR 0014).
CACHED_BUILDS = {"infra": 2, "publish": 1}


@pytest.mark.parametrize(("job", "entries"), CACHED_BUILDS.items())
def test_la_ci_donne_a_chaque_image_son_entree_de_cache(job: str, entries: int) -> None:
    """Les drapeaux du job, passés par l'environnement comme en CI puis développés par `make` :
    chaque image lit — et, dans `infra`, écrit — son entrée du cache local, à son nom. Sous une
    même étiquette — le défaut, `latest` —, la dernière image construite remplace l'entrée des
    autres (doc Docker, « Local cache » ; mesuré à la relecture de la PR #53). Rouge aussi si le
    `Makefile` cesse de prendre ces drapeaux dans l'environnement (`=` au lieu de `?=`)."""
    flags = ci_build_flags(job)
    assert flags, (
        f"aucune étape du job `{job}` ne passe `DOCKER_BUILD_FLAGS` — sa forme a-t-elle changé ?"
    )

    printed = make_dry_run("build", environment={"DOCKER_BUILD_FLAGS": flags})
    tags = {
        Path(match["dockerfile"]).parent.name: CACHE_TAG.findall(match.group())
        for match in BUILD_COMMAND.finditer(printed)
    }

    services = [path.parent.name for path in IMAGE_DOCKERFILES]
    assert tags == {service: [service] * entries for service in services}


@pytest.mark.parametrize(
    "dockerfile", IMAGE_DOCKERFILES, ids=[path.parent.name for path in IMAGE_DOCKERFILES]
)
def test_le_build_des_images_ne_demande_aucun_secret(dockerfile: Path) -> None:
    """Le build n'attend aucun secret : le job `infra` construit les images sans en avoir aucun.

    `collectstatic` charge pourtant les réglages de `api`, donc `Env.load()` (ADR 0014) : ses
    valeurs factices vivent sur sa ligne de `RUN`. Un `ARG` qui nommerait une variable d'`Env` la
    réclamerait à la commande de build, un montage de secret aussi ; un `ENV` la figerait dans
    l'image, lisible par `docker inspect` — dans toute image publiée, pas seulement dans `api`.
    """
    instructions = [
        whole for _, whole in dockerfile_instructions(dockerfile.read_text(encoding="utf-8"))
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
