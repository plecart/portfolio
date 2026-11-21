"""Tests des fichiers d'infrastructure : images, point d'entrée, `Makefile`.

Ces tests lisent des fichiers, ou interrogent les outils qui les lisent — `make --dry-run`, Docker
pour le contexte de build —, sans construire d'image ni démarrer de conteneur. Ils gardent des
invariants dont la violation ne se voit qu'à l'exécution, et tard : un conteneur qui tourne en
root, des signaux qui n'atteignent jamais le serveur, une adresse de service revenue à
`127.0.0.1`. Chacun d'eux a été éprouvé par mutation — retiré du code, il rend ce test rouge.

Que les images **se construisent** et que la pile **démarre** est prouvé ailleurs : par le job
`infra` de la CI, et par la pile qu'on regarde tourner. Le scan des images a ses propres tests,
dans `test_image_scan.py`, leur publication dans `test_publication.py`, et le contenu des fichiers
Compose dans `test_compose.py`.
"""

import ast
import io
import itertools
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from call_witness import recording, witnessed
from config.env import Env
from system_commands import MAKEFILE, make_dry_run
from test_supply_chain import (
    DOCKER_FROM,
    WORKFLOW_GLOBS,
    dockerfile_instructions,
    prose_citations,
    repository_files,
    tracked_files,
)

# `test_infra.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPOSITORY_ROOT / "infra" / "api" / "Dockerfile"
ENTRYPOINT = REPOSITORY_ROOT / "infra" / "api" / "entrypoint.sh"
COMPOSE_DEV = REPOSITORY_ROOT / "infra" / "compose.dev.yml"
PYTHON_VERSION_FILE = REPOSITORY_ROOT / ".python-version"
DOCKERIGNORE = REPOSITORY_ROOT / ".dockerignore"
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
# Les portes d'avis : planifiées chaque jour, et appelées par le job `avis` de `CI_WORKFLOW`.
AVIS_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "avis.yml"
# La commande du pas qui libère le disque du runner avant le build des images, mot pour mot :
# la même dans `avis.yml` et dans `publish`, qui scannent tous deux (`test_ci_declencheurs.py`,
# `test_publication.py`).
DISQUE_RUN = (
    "df -h /\n"
    "sudo rm -rf /usr/local/lib/android /usr/share/dotnet /usr/local/.ghcup /opt/hostedtoolcache/CodeQL\n"
    "df -h /\n"
)

# Les Dockerfiles des images du dépôt, un par dossier `infra/<service>/` (ADR 0014).
IMAGE_DOCKERFILES = sorted(REPOSITORY_ROOT.glob("infra/*/Dockerfile"))

# Les images qui créent leur utilisateur et tournent sous lui : `useradd` sous Debian (`api`),
# `adduser` sous Alpine (`backup`). `caddy` tourne sous celui de son image officielle, `root`.
NON_ROOT_SERVICES = ["api", "backup"]

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

# Ce que l'image `api` sert, là où l'application le lit : le gabarit du site (ADR
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

# Toute image de base qui embarque un interpréteur porte sa version dans son nom. Le motif les
# capture toutes : un seul étage qui dériverait suffirait à faire tourner l'application sur une
# version que le dépôt n'épingle nulle part.
BASE_IMAGE_VERSION = re.compile(r"^FROM python:(\d+\.\d+)[.-]", re.MULTILINE)

# Le temps laissé à un lancement Docker d'un test, en secondes, tirage d'image compris. Sans lui,
# un conteneur qui ne finit pas fige la suite au lieu de la faire échouer : 3 h 40 sur le filtre
# gojq de `test_publication.py` le 2026-10-28, sans échec affiché. Au-dessus des 210 s qu'un
# `up --wait` peut attendre une sonde de production (`x-probe-timing`, 2 min puis 3 × 30 s).
DOCKER_DEADLINE = 300

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

# Les fichiers qu'un outil Linux lit dans la **copie de travail** : ce qu'un shell exécute — dans
# le conteneur, ou sur le VPS (`infra/bootstrap.sh`) —, ce que buildkit analyse, la configuration
# que Caddy lit dans son image, l'horaire que `supercronic` lit dans la sienne, ce dont Compose tire
# des valeurs, l'épingle de version que `uv` relit dans l'image, et les exceptions que Trivy lit
# depuis son conteneur. Tout fichier ajouté à `infra/` et lu par un conteneur entre dans un de ces
# motifs — et chacun est vérifié séparément, sinon un motif devenu aveugle passerait inaperçu.
CONTAINER_TEXT_GLOBS = [
    "infra/**/*.sh",
    "infra/**/Dockerfile",
    "infra/**/Caddyfile",
    "infra/**/crontab",
    "infra/**/*.env",
    "infra/**/*.env.example",
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
# Les dossiers de modules de test, depuis la racine : un dossier ajouté entre ici, et la porte le
# lit sans autre changement.
TEST_DIRECTORIES = ("apps/api/tests", ".claude/tests")
TEST_MODULE_REFERENCE = re.compile(
    "(?P<path>(?:" + "|".join(re.escape(folder) for folder in TEST_DIRECTORIES) + r")/\w+\.py)"
)


def cited_test_modules(root: Path, population: Iterable[str]) -> dict[str, set[str]]:
    """Les modules de test que la prose du dépôt désigne, avec les fichiers qui citent.

    **Ce que cette porte ne couvre pas, et pourquoi on ne l'a pas élargie.** Elle apparie un
    chemin de *module* (`TEST_MODULE_REFERENCE`). Les renvois vers un *nom* de test ne sont
    gardés par rien, et `PROSE_GLOBS` n'inclut pas les sources Python du back — il en inclut
    trois par `infra/**/*` (mesuré) —, donc les renvois qui vivent dans les docstrings de
    `apps/api/` et dans `.claude/skills/*/scripts/` échappent même à cette porte-ci. Population
    recensée le 2026-10-12 sur `baaf79c` : **9 renvois, 0 cassé**.

    Deux élargissements ont été mesurés et écartés : une porte sur `` `test_\\w+` `` rend
    **3 faux positifs sur 8**, et `PROSE_GLOBS` étendu aux sources Python **3 sur 19**. Les
    trois sont les mêmes — les noms de test **synthétiques** des suites témoins de
    `test_mutation.py`, et le `test_x.py` d'exemple du `--help` de `mutation.py`. Fermer la
    classe demanderait de distinguer un renvoi d'un fixture, ce qu'aucun motif simple ne fait ;
    et un refus qui mord sur le travail ordinaire est un refus qu'on apprend à contourner.

    Args:
        root: la racine à parcourir.
        population: les chemins relatifs, en POSIX, que l'appelant a le droit de lire. Tout
            fichier présent sur le disque mais absent de cette liste est ignoré. Le choix de la
            population appartient donc à l'appelant : la porte passe `tracked_files()`, ce qui
            écarte le brouillon **non suivi** mais pas celui qui est mis à l'index — voir le
            docstring de `tracked_files`.

    Returns:
        Les chemins des modules cités, depuis la racine, chacun avec le nom des fichiers qui les
        citent.
    """
    cited: dict[str, set[str]] = {}
    for citing, reference in prose_citations(root, population, PROSE_GLOBS, TEST_MODULE_REFERENCE):
        cited.setdefault(reference.group("path"), set()).add(citing.name)
    return cited


def absent_test_modules(root: Path, cited: Mapping[str, set[str]]) -> dict[str, list[str]]:
    """Les modules cités que `root` ne porte pas, chacun avec les fichiers qui les citent."""
    return {path: sorted(where) for path, where in cited.items() if not (root / path).exists()}


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


def built_images(printed: str) -> dict[str, str]:
    """Les images d'une sortie de `make --dry-run build` : chaque Dockerfile, et son étiquette."""
    return {match["dockerfile"]: match["tag"] for match in BUILD_COMMAND.finditer(printed)}


def loaded_image(service: str) -> str:
    """Le nom que `make build` donne à l'image d'un service — celle qu'un test d'image
    (`infra/tests/`) doit trouver chargée.

    Sous le préfixe de l'appel, s'il en pose un : le `Makefile` exporte `IMAGE_PREFIX`, donc
    `make image-test IMAGE_PREFIX=…` teste les images que `make build IMAGE_PREFIX=…` a construites.
    """
    prefix = {"IMAGE_PREFIX": os.environ["IMAGE_PREFIX"]} if "IMAGE_PREFIX" in os.environ else {}
    return built_images(make_dry_run("build", environment=prefix))[f"infra/{service}/Dockerfile"]


def run_bounded(
    command: Sequence[str | Path],
    *,
    stdin: bytes | None = None,
    environment: Mapping[str, str] | None = None,
    check: bool = True,
    timeout: float = DOCKER_DEADLINE,
) -> subprocess.CompletedProcess[bytes]:
    """`command` jusqu'au bout, ou `TimeoutExpired` au bout de `timeout` secondes sans attendre ses
    tubes — sa descendance tuée sous Windows (`taskkill /T`), l'enfant direct seul ailleurs, où
    rien n'attend les tubes. `subprocess.run(timeout=…)` ne tue que l'enfant direct puis, sous
    Windows, attend les tubes que tient sa descendance — `docker compose` et `docker buildx` sont
    des plugins que `docker` lance en enfant : 46 s pour un délai de 5 s sur un `buildx`, mesuré à
    la relecture de la PR #185. Tout lancement Docker d'un test passe par ici, sauf un `Popen` qui
    porte son délai à son attente. Sauf `check=False`, un code de sortie non nul fait échouer, sa
    sortie d'erreur pour message."""
    process = subprocess.Popen(
        command,
        stdin=None if stdin is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            killer = ["taskkill", "/F", "/T", "/PID", str(process.pid)]
            subprocess.run(killer, capture_output=True, check=False)
        process.kill()
        raise
    assert not check or process.returncode == 0, stderr.decode(errors="replace")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def image_output(image: str, *command: str) -> str:
    """La sortie standard de `command`, lancée dans un conteneur jetable de l'image, hors de toute
    pile."""
    return run_bounded(["docker", "run", "--rm", image, *command]).stdout.decode()


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
    archive = run_bounded(
        ["docker", "buildx", "build", "-f", str(dockerfile), "--output", "type=tar,dest=-", root]
    ).stdout
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


def dated_front(root: Path, files: list[str]) -> Path:
    """Un front témoin sous `root/web`, compilé après ses sources : chaque chemin, dossiers
    compris, daté d'une heure plus tôt, puis `dist/index.html` d'une minute de plus — un `dist` à
    jour. Rend le dossier du front, à passer en `WEB`."""
    web = root / "web"
    for name in [*files, "dist/index.html"]:
        (web / name).parent.mkdir(parents=True, exist_ok=True)
        (web / name).write_text("", encoding="utf-8")
    sources = time.time() - 3600
    for path in [web, *web.rglob("*")]:
        os.utime(path, (sources, sources))
    os.utime(web / "dist" / "index.html", (sources + 60, sources + 60))
    return web


@pytest.mark.parametrize(
    "source",
    [
        "src/main.tsx",
        "src/assets/fonts/police.woff2",
        "public/icon.svg",
        "index.html",
        "vite.config.ts",
        "package.json",
        "package-lock.json",
        "tsconfig.app.json",
        ".env",
        ".env.production",
    ],
)
def test_build_recompile_le_front_plus_ancien_qu_une_de_ses_entrees(
    tmp_path: Path, source: str
) -> None:
    """Un `dist` repris d'une compilation antérieure — un worktree réutilisé — ne porte pas ce
    qu'on a ajouté au front depuis : `build` le recompile dès qu'une entrée de la compilation est
    plus récente que lui, à toute profondeur, et le reprend tant qu'il est à jour. Mesuré avant
    correction (PR #247) : trois icônes ajoutées à `public/` servies en `text/html`."""
    web = dated_front(tmp_path, [source])
    fresh = make_dry_run("build", WEB=web.as_posix())
    (web / source).touch()

    assert FRONT_BUILD not in fresh
    assert FRONT_BUILD in make_dry_run("build", WEB=web.as_posix())


def test_build_recompile_le_front_quand_un_fichier_quitte_ses_entrees(tmp_path: Path) -> None:
    """Retirer un fichier de `public/` date son dossier : `dist`, qui le porte encore, est périmé."""
    web = dated_front(tmp_path, ["public/icon.svg", "public/robots.txt"])
    (web / "public" / "icon.svg").unlink()

    assert FRONT_BUILD in make_dry_run("build", WEB=web.as_posix())


def test_build_ne_recompile_pas_le_front_pour_ce_qui_n_y_entre_pas(tmp_path: Path) -> None:
    """Les tests du front n'entrent pas dans `dist` : les modifier ne le recompile pas."""
    web = dated_front(tmp_path, ["src/main.tsx", "tests/cards.test.ts"])
    (web / "tests" / "cards.test.ts").touch()

    assert FRONT_BUILD not in make_dry_run("build", WEB=web.as_posix())


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


def job_steps(workflow: Path, job: str) -> list[dict[str, Any]]:
    """Les étapes du job `job` du workflow `workflow`, dans l'ordre."""
    return yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"][job]["steps"]


def build_flags(steps: list[dict[str, Any]]) -> list[str]:
    """Les drapeaux que chaque étape de `steps` passe au build par `DOCKER_BUILD_FLAGS`."""
    return [
        step["env"]["DOCKER_BUILD_FLAGS"]
        for step in steps
        if "DOCKER_BUILD_FLAGS" in step.get("env", {})
    ]


# Les jobs qui construisent les images avec le cache local — tous : un test le tient —, le
# workflow de chacun et s'il écrit le cache, sous une même clé : `infra` le lit et l'écrit, sur une
# PR ; `publish` aussi, sur `main` — l'entrée d'une PR n'est lisible que d'elle (ADR 0031) ;
# `avis` le lit seulement (ADR 0014, ADR 0019).
CACHED_BUILDS = {
    "infra": (CI_WORKFLOW, True),
    "publish": (CI_WORKFLOW, True),
    "avis": (AVIS_WORKFLOW, False),
}


def ci_build_flags(job: str) -> str:
    """Les drapeaux que l'unique étape de build du job `job` de `CACHED_BUILDS` passe par
    `DOCKER_BUILD_FLAGS`, lus dans son workflow."""
    flags = build_flags(job_steps(CACHED_BUILDS[job][0], job))
    assert len(flags) == 1, f"le job `{job}` a {len(flags)} étape qui passe `DOCKER_BUILD_FLAGS`"
    return flags[0]


def test_chaque_build_en_cache_de_la_ci_est_recense() -> None:
    """Chaque job d'un workflow qui passe des drapeaux au build est dans `CACHED_BUILDS` : absent,
    il échapperait aux tests de ses drapeaux — le job `avis` l'a fait, à son ajout (cleanup de la
    PR #187)."""
    workflows = [path for glob in WORKFLOW_GLOBS for path in REPOSITORY_ROOT.glob(glob)]
    building = {
        (workflow, job)
        for workflow in workflows
        for job, body in yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"].items()
        if build_flags(body.get("steps") or [])
    }
    assert building == {(workflow, job) for job, (workflow, _) in CACHED_BUILDS.items()}


def test_le_job_infra_teste_les_images_qu_il_vient_de_construire() -> None:
    """`make image-test` démarre les images que `make build` a chargées : avant le build, il n'a
    rien à démarrer ; absent, le Caddyfile de production n'est éprouvé nulle part en CI — mesuré à
    la relecture de la PR #67, l'étape retirée laissait toute la suite verte. Son étape ne porte
    que son nom et sa commande : ni `if` qui la sauterait, ni `continue-on-error` qui tolérerait
    son échec."""
    steps = job_steps(CI_WORKFLOW, "infra")
    commands = [step.get("run") for step in steps]

    assert "make build" in commands and "make image-test" in commands, commands
    position = commands.index("make image-test")
    assert commands.index("make build") < position
    assert set(steps[position]) == {"name", "run"}


@pytest.mark.parametrize("job", CACHED_BUILDS)
def test_la_ci_donne_a_chaque_image_son_entree_de_cache(job: str) -> None:
    """Les drapeaux du job, passés par l'environnement comme en CI puis développés par `make` :
    chaque image lit — et, dans `infra` et `publish`, écrit — son entrée du cache local, à son nom.
    Sous une même étiquette — le défaut, `latest` —, la dernière image construite remplace l'entrée
    des autres (doc Docker, « Local cache » ; mesuré à la relecture de la PR #53). Rouge aussi si le
    `Makefile` cesse de prendre ces drapeaux dans l'environnement (`=` au lieu de `?=`)."""
    _, writes = CACHED_BUILDS[job]
    flags = ci_build_flags(job)
    printed = make_dry_run("build", environment={"DOCKER_BUILD_FLAGS": flags})
    tags = {
        Path(match["dockerfile"]).parent.name: CACHE_TAG.findall(match.group())
        for match in BUILD_COMMAND.finditer(printed)
    }

    services = [path.parent.name for path in IMAGE_DOCKERFILES]
    assert tags == {service: [service] * (1 + writes) for service in services}
    assert ("--cache-to" in flags) is writes


@pytest.mark.parametrize("job", CACHED_BUILDS)
def test_la_ci_charge_dans_le_moteur_les_images_qu_elle_construit(job: str) -> None:
    """Sans `--load`, le pilote conteneurisé construit et jette : les tests des images d'`infra`,
    le scan d'`avis` et celui de `publish` ne trouveraient rien à lire."""
    assert "--load" in ci_build_flags(job).split()


# L'étage qui installe des paquets du système, et que la CI reconstruit à chaque build : leur
# version suit les dépôts de la distribution, qu'aucune clé de cache ne suit.
PACKAGE_STAGE = "paquets"
PACKAGE_INSTALL = re.compile(r"^RUN\b.*\b(?:apk add|apt-get install|apt install)\b", re.IGNORECASE)


def package_install_stages(text: str) -> list[str | None]:
    """L'étage de chaque `RUN` du Dockerfile qui installe des paquets du système — `None` pour un
    étage sans nom."""
    stage, stages = None, list[str | None]()
    for _, whole in dockerfile_instructions(text):
        if declaration := DOCKER_FROM.match(whole):
            stage = declaration["stage"]
        elif PACKAGE_INSTALL.match(whole.lstrip()):
            stages.append(stage)
    return stages


def test_les_paquets_du_systeme_s_installent_dans_l_etage_paquets() -> None:
    """Hors de l'étage `paquets`, une installation resterait en cache : la couche garderait des
    paquets corrigés depuis, que le scan trouve vulnérables — mesuré le 2026-10-24 (run
    40103586324) : `apk add` restauré du cache, `brotli-libs` 1.2.0-r1 HIGH dans `backup` ;
    reconstruit à froid le lendemain (run 40222600252), 0 au scan."""
    stages = [
        stage
        for dockerfile in IMAGE_DOCKERFILES
        for stage in package_install_stages(dockerfile.read_text(encoding="utf-8"))
    ]

    assert stages, "aucune installation de paquets lue — sa forme a-t-elle changé ?"
    assert set(stages) == {PACKAGE_STAGE}


@pytest.mark.parametrize("job", CACHED_BUILDS)
def test_la_ci_reconstruit_l_etage_paquets_a_chaque_build(job: str) -> None:
    """Chaque job reconstruit l'étage `paquets` sans le cache. `publish` et `avis` aussi : quand la
    clé d'`infra` existait déjà, `infra` ne réécrit pas l'entrée, et ils restaureraient l'ancienne
    couche."""
    assert f"--no-cache-filter {PACKAGE_STAGE}" in " ".join(ci_build_flags(job).split())


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


def build_environment(dockerfile: Path) -> dict[str, str]:
    """Les variables que la ligne `RUN … collectstatic` de `dockerfile` pose devant sa commande.

    Lues comme le shell du build les lit : chaque `NOM=valeur` qui précède la commande, citations
    retirées. La première chose qui n'est pas une affectation est la commande.
    """
    [instruction] = [
        whole
        for _, whole in dockerfile_instructions(dockerfile.read_text(encoding="utf-8"))
        if "collectstatic" in whole
    ]
    words = shlex.split(instruction.removeprefix("RUN"))
    assignments = itertools.takewhile(lambda word: "=" in word, words)
    return dict(word.split("=", 1) for word in assignments)


def test_l_environnement_factice_du_build_est_accepte_par_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un champ ajouté à `Env` sans sa valeur factice ici casse `make build` — en CI seulement,
    au job `infra`, loin du fichier qui l'a causé. La ligne se prouve donc comme le build la
    joue : ces variables, et elles seules, doivent faire démarrer `Env`."""
    for name in Env.model_fields:
        monkeypatch.delenv(name, raising=False)
    environment = build_environment(DOCKERFILE)
    assert environment, (
        "aucune affectation lue — la ligne `collectstatic` a-t-elle changé de forme ?"
    )
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    Env.load()


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


def entrypoint_calls(tmp_path: Path, steps: str | None) -> list[list[str]]:
    """Exécute le point d'entrée sous `sh`, `STARTUP_STEPS` valant `steps` — absente si `None` —,
    avec `python commande` pour commande reçue, et un témoin de `python` en tête du `PATH`
    (`call_witness`).

    Returns:
        Les appels du témoin, dans l'ordre : les étapes jouées par `manage.py`, puis la commande.
    """
    tools, log = tmp_path / "outils", tmp_path / "appels"
    tools.mkdir()
    witness = tools / "python"
    # `#!` : sans lui, le shell du poste Windows ne tient pas le témoin pour un exécutable, et le
    # `PATH` mène au vrai `python` (mesuré par `test_restore_workflow.py`).
    witness.write_text("#!/bin/sh\n" + recording(log), encoding="utf-8", newline="\n")
    witness.chmod(0o755)
    environment = {name: value for name, value in os.environ.items() if name != "STARTUP_STEPS"}
    environment["PATH"] = f"{tools}{os.pathsep}{os.environ['PATH']}"
    if steps is not None:
        environment["STARTUP_STEPS"] = steps
    done = subprocess.run(
        ["sh", ENTRYPOINT.as_posix(), "python", "commande"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return witnessed(log)


MIGRATE = ["python", "manage.py", "migrate"]
ENSURE_SUPERUSER = ["python", "manage.py", "ensure_superuser"]
COMMAND = ["python", "commande"]

# `STARTUP_STEPS` → les appels attendus. Absente, les migrations puis le superutilisateur, qui en a
# besoin (critère de #6). Vide, aucune étape : c'est ce qui permet au `worker` de partager l'image
# d'`api` sans rejouer les migrations (brief de #12, décision 11) — la forme `${VAR:=défaut}`
# traitait le vide comme l'absence, et migrait (mesuré à la clôture de #4).
STARTUP_FORMS = {
    "absente": (None, [MIGRATE, ENSURE_SUPERUSER, COMMAND]),
    "vide": ("", [COMMAND]),
    "deux étapes": ("migrate check", [MIGRATE, ["python", "manage.py", "check"], COMMAND]),
}


@pytest.mark.parametrize(("steps", "expected"), STARTUP_FORMS.values(), ids=STARTUP_FORMS.keys())
def test_le_point_d_entree_joue_les_etapes_demandees_puis_la_commande(
    tmp_path: Path, steps: str | None, expected: list[list[str]]
) -> None:
    """Absente, `STARTUP_STEPS` migre puis pose le superutilisateur : c'est la posture d'`api`.
    Vide, rien ne précède la commande : celle du `worker`, qu'`api` a migré avant lui."""
    assert entrypoint_calls(tmp_path, steps) == expected


@pytest.mark.parametrize("service", NON_ROOT_SERVICES)
def test_l_image_bascule_sur_un_utilisateur_non_root(service: str) -> None:
    """Un `USER` retiré laisse l'image tourner en root, et aucune autre porte ne le voit."""
    dockerfile = (REPOSITORY_ROOT / "infra" / service / "Dockerfile").read_text(encoding="utf-8")
    creation = re.search(
        r"^RUN (?:useradd|adduser) .*?(?P<name>\w+)\s*\\?$", dockerfile, re.MULTILINE
    )
    switch = re.search(r"^USER (?P<name>\w+)$", dockerfile, re.MULTILINE)

    assert creation, "aucun `RUN useradd` ni `adduser` — l'image crée-t-elle son utilisateur ?"
    assert switch, "aucune instruction `USER` : l'image démarrerait en root"
    assert switch.group("name") != "root"
    assert creation.start() < switch.start(), "`USER` doit suivre la création de l'utilisateur"


def test_aucun_renvoi_vers_un_module_de_test_inexistant() -> None:
    """Un module renommé laisse derrière lui des renvois que rien ne suit.

    La population d'un renommage inclut ses **renvois entrants** : la prose qui le désigne. Ils
    ne cassent aucune porte, se lisent comme justes, et n'échouent que pour le lecteur qui suit
    le lien — c'est-à-dire trop tard.

    La population est celle que le dépôt **contient** — `tracked_files()`, soit l'index —,
    jamais celle du disque : un brouillon **non suivi** suffirait sinon à faire rougir chez une
    personne seule. Ce que ce choix ne donne pas, c'est un verdict identique partout : l'index
    est local, donc un brouillon simplement `git add`-é y entre et rougit ici quand la CI reste
    verte (mesuré le 2026-10-12 sur `ee21cb5`, voir le docstring de `tracked_files`). Mesuré le
    2026-10-09, deux fois : `PR-PARALLELES.md`, tableau de bord éphémère d'une vague, citait un
    module de test d'une branche en vol ; puis, en relecture, un fichier de prose non suivi
    **et non ignoré** rougissait encore, parce qu'une population « suivis **ou** nouveaux non
    ignorés » les comprend. L'exclusion d'un artefact nommé ne ferme pas la classe ; la
    population, oui.
    """
    cited = cited_test_modules(REPOSITORY_ROOT, tracked_files())

    assert cited, "aucun renvoi trouvé — les motifs ont-ils cessé de mordre ?"
    missing = absent_test_modules(REPOSITORY_ROOT, cited)
    assert not missing, f"{len(cited)} modules cités, introuvables : {missing}"


@pytest.mark.parametrize("folder", ["apps/api/tests", ".claude/tests"])
def test_la_porte_des_renvois_lit_chaque_dossier_de_tests(tmp_path: Path, folder: str) -> None:
    """Un témoin de chaque côté dans chaque dossier de tests : le module cité qui existe passe,
    celui qui manque est rendu. Depuis le déplacement des tests de la pipeline, une porte réduite
    à `apps/api/tests` laissait passer tout renvoi cassé vers `.claude/tests`."""
    (tmp_path / folder).mkdir(parents=True)
    (tmp_path / folder / "test_present.py").write_text("", encoding="utf-8")
    (tmp_path / "brouillon.md").write_text(
        f"voir {folder}/test_present.py et {folder}/test_absent.py", encoding="utf-8"
    )

    cited = cited_test_modules(tmp_path, ["brouillon.md"])

    assert absent_test_modules(tmp_path, cited) == {f"{folder}/test_absent.py": ["brouillon.md"]}


def test_un_brouillon_non_suivi_n_entre_pas_dans_la_population(tmp_path: Path) -> None:
    """C'est la **population** qui décide, pas l'exclusion d'un artefact nommé.

    Ignorer `PR-PARALLELES.md` fermait l'occurrence ; seul le choix de la population ferme la
    classe — n'importe quel brouillon de prose non suivi la rouvrirait. Ce test le prouve dans
    les deux sens : hors population, le fichier n'est pas lu ; dedans, il l'est.
    """
    draft = tmp_path / "brouillon.md"
    draft.write_text("voir apps/api/tests/test_inexistant.py", encoding="utf-8")

    assert cited_test_modules(tmp_path, []) == {}
    assert cited_test_modules(tmp_path, ["brouillon.md"]) == {
        "apps/api/tests/test_inexistant.py": {"brouillon.md"}
    }


def test_la_porte_des_renvois_ignore_un_brouillon_non_suivi() -> None:
    """Épingle le choix de population **de la porte**, et non la population elle-même.

    Le test ci-dessus prouve qu'une population décide de ce qui est lu ; il ne prouve pas que
    la porte a choisi l'étroite. L'écart se mesure : sur un **arbre propre** les deux
    populations coïncident, donc la ligne d'appel remise sur `repository_files()` laisse la
    suite entièrement verte — mutation vue VERTE le 2026-10-12. Avec un brouillon **non suivi**
    planté à la racine, elles divergent — 11 modules cités contre 12 — et la même mutation
    rougit.

    D'où la forme : ce test **appelle la porte**, au lieu de recalculer la population étroite.
    C'est ce seul détail qui le distingue d'un doublon, et c'est lui qui fait mordre la
    mutation de la ligne d'appel.

    La sonde n'est pas suivie, donc invisible à `tracked_files()` : un résidu laissé par un
    `SIGKILL` ne rougirait rien — mesuré, suite entière verte avec la sonde en place. Le
    `finally` couvre l'échec d'assertion comme l'exception.
    """
    draft = REPOSITORY_ROOT / "zz-brouillon-non-suivi-de-la-porte.md"
    draft.write_text("voir apps/api/tests/test_inexistant_de_la_porte.py", encoding="utf-8")
    try:
        test_aucun_renvoi_vers_un_module_de_test_inexistant()
    finally:
        draft.unlink()


def test_les_deux_populations_de_fichiers_ne_sont_pas_la_meme(tmp_path: Path) -> None:
    """La porte a choisi la plus étroite des deux, et ce choix doit rester lisible.

    Éprouvé sur un dépôt jetable, jamais sur celui-ci : une comparaison des deux populations
    du clone courant serait vraie ou fausse selon ce que la personne a en cours, soit le défaut
    même que ce resserrement corrige. Première écriture de ce test, mesuré : l'assertion
    `tracked_files() < repository_files()` passait tant qu'un fichier non suivi existait et
    tombait dès que l'arbre était propre.
    """
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / "suivi.md").write_text("suivi", encoding="utf-8")
    (tmp_path / "brouillon.md").write_text("brouillon", encoding="utf-8")
    subprocess.run(["git", "add", "suivi.md"], cwd=tmp_path, check=True)

    assert tracked_files(tmp_path) == ["suivi.md"]
    assert sorted(repository_files(tmp_path)) == ["brouillon.md", "suivi.md"]


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


def docker_launches() -> dict[str, str]:
    """Les lancements Docker des tests du back et des images, par `fichier:ligne`, avec leur
    lanceur : chaque `subprocess.run`, `subprocess.Popen` ou `run_bounded` des tests des images —
    tous lancent Docker, directement ou par un script (`restore.sh`) —, et ceux des tests du back
    dont la commande nomme `docker` en littéral, lus par l'analyseur de Python. Dans les tests du
    back, une commande rangée dans une variable leur échappe."""
    return {
        f"{module.relative_to(REPOSITORY_ROOT).as_posix()}:{node.lineno}": ast.unparse(node.func)
        for folder in ("apps/api/tests", "infra/tests")
        for module in sorted((REPOSITORY_ROOT / folder).glob("*.py"))
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) in {"subprocess.run", "subprocess.Popen", "run_bounded"}
        and node.args
        and (folder == "infra/tests" or "'docker'" in ast.unparse(node.args[0]))
    }


def test_chaque_lancement_docker_d_un_test_passe_par_run_bounded() -> None:
    """Un conteneur qui ne finit pas fait échouer son test par `TimeoutExpired`, au lieu de figer
    la suite : aucun `subprocess.run`, dont le délai attend la descendance sous Windows. Un `Popen`
    porte le sien à son attente, `communicate(timeout=…)`, qui lève sans rien attendre — un délai
    que ce test ne garde pas."""
    launches = docker_launches()

    assert launches, "aucun lancement Docker lu — la commande a-t-elle quitté son littéral ?"
    faulty = [where for where, launcher in launches.items() if launcher == "subprocess.run"]
    assert not faulty, f"{len(launches)} lancements repassés, hors de `run_bounded` : {faulty}"


def test_run_bounded_rend_la_main_au_delai_quand_un_petit_fils_tient_les_tubes() -> None:
    """Le petit-fils hérite des tubes, comme un plugin de `docker` : `subprocess.run(timeout=…)`
    l'attendrait jusqu'au bout, sous Windows."""
    grandchild = "import subprocess, sys; subprocess.run([sys.executable, '-c', 'import time; time.sleep(30)'])"
    started = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", grandchild], timeout=1)
    assert time.monotonic() - started < 15


def test_run_bounded_fait_echouer_un_code_non_nul_sa_sortie_d_erreur_pour_message() -> None:
    """Sans cette garde, une commande Docker en échec rendrait une sortie vide, et un test qui
    affirme une absence — aucun conteneur survivant — passerait à vide."""
    failing = [sys.executable, "-c", "import sys; sys.exit('panne de Docker')"]

    with pytest.raises(AssertionError, match="panne de Docker"):
        run_bounded(failing)
    assert run_bounded(failing, check=False).returncode == 1
