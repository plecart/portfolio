"""Tests de la chaîne d'approvisionnement : actions, images et téléchargements épinglés, Dependabot.

Comme `test_infra.py`, ces tests lisent des fichiers de configuration sans rien exécuter. Ils
gardent ce qui ne se verrait qu'après le merge, et en silence : une action ou une image qui suit
une étiquette déplaçable, un écosystème que Dependabot ne surveille plus. La porte d'audit Python
a ses propres tests, dans `test_pip_audit_gate.py`.

Chaque garde lit les fichiers comme l'outil qu'elle protège : le YAML par un analyseur YAML, un
Dockerfile instruction par instruction comme Docker, et chaque `FROM` par sa première ligne comme
Dependabot. Un motif qui imiterait l'analyseur à la main laisserait passer les formes qu'il n'a
pas prévues. Les gardes sont donc des fonctions sur du texte, appliquées aux fichiers du dépôt et
à un recueil de formes — `WORKFLOW_FORMS`, `IMAGE_FORMS`, `SOURCE_FORMS`, `DOWNLOAD_FORMS`,
`DOCKERFILE_NAMES`, `COMPOSE_FORMS`, `COMPOSE_NAMES` :
chaque forme recensée par les relectures de #5 y a son cas, avec le verdict attendu. Une forme
nouvelle s'y ajoute ; celles jugées exotiques y figurent en `xfail` strict, qui signale le jour
où elles cesseraient d'échapper. La configuration de Dependabot, elle, est lue une fois par
l'analyseur YAML : sa garde prend les entrées déjà lues, et son recueil, `DEPENDABOT_FORMS`
(#125), des entrées construites.
"""

import json
import re
import subprocess
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

# `test_supply_chain.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPENDABOT = REPOSITORY_ROOT / ".github" / "dependabot.yml"
NPM_REFUSALS = REPOSITORY_ROOT / "apps" / "web" / "dependency-refusals.json"
WORKFLOW_GLOBS = [".github/workflows/*.yml", ".github/workflows/*.yaml"]
COMPOSITE_ACTION_GLOB = ".github/actions/**/action.y*ml"

# `uses: owner/action@<empreinte> # vX.Y.Z`. Le commentaire porte l'étiquette **la plus précise**
# du commit : Dependabot réécrit un commentaire qui se termine par une étiquette pointant encore
# sur le commit épinglé (`version_commenter.rb`, dependabot-core), et une étiquette majeure
# (`v7`) cesse d'y pointer dès qu'une version sort — précisément quand la mise à jour arrive.
# Le motif lit la ligne, commentaire compris ; l'analyseur YAML lit les `uses` réels, et les deux
# ensembles de références doivent coïncider — une forme que le motif ne lit pas (mapping en flux,
# clé entre guillemets) est signalée au lieu de passer inaperçue. Des ensembles et non des
# décomptes : une ancre YAML reprise ailleurs compte deux fois pour l'analyseur.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<reference>\S+)(?P<comment>.*)$", re.MULTILINE)
PINNED_REFERENCE = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^ # v\d+\.\d+\.\d+$")

# Les écosystèmes que Dependabot surveille (brief de #5), chacun avec un fichier qu'il doit trouver
# dans le dossier configuré.
ECOSYSTEM_MANIFESTS = {
    "uv": "uv.lock",
    "npm": "package-lock.json",
    "github-actions": ".github/workflows",
    "docker": "Dockerfile",
    "docker-compose": "compose.dev.yml",
}

# La politique commune à tous les écosystèmes : passage hebdomadaire, mineures et correctifs
# groupés — les majeures restent seules, chacune dans sa PR, sauf celles qu'un `ignore` refuse —,
# aucun libellé hors du mapping de `.claude/pipeline.config.md`, commits au format conventional du
# dépôt (brief de #5, briefing du 2026-09-25).
UPDATE_POLICY: dict[str, Any] = {
    "schedule": {"interval": "weekly"},
    "groups": {"minor-and-patch": {"update-types": ["minor", "patch"]}},
    "labels": [],
    "commit-message": {"prefix": "chore", "include": "scope"},
}

# Les clés qu'une entrée peut porter, toutes : la politique, plus ce qui identifie l'écosystème,
# plus les écarts décidés écosystème par écosystème. Une clé de plus peut changer la politique en
# silence — `open-pull-requests-limit: 0` coupe les mises à jour, un `ignore: "*"` aussi. Le ou
# les dossiers surveillés s'y ajoutent : `directory` pour un seul, `directories` pour plusieurs,
# jamais les deux (doc Dependabot, « directories »).
ENTRY_KEYS = {"package-ecosystem", *UPDATE_POLICY}
LOCATION_KEYS = {"directory", "directories"}
ECOSYSTEM_EXTRA_KEYS = {"docker": {"ignore"}, "docker-compose": {"ignore"}, "npm": {"ignore"}}

PYTHON_UPGRADES_IGNORED = {
    "dependency-name": "python",
    "update-types": ["version-update:semver-major", "version-update:semver-minor"],
}

NODE_TYPES_UPGRADES_IGNORED = {
    "dependency-name": "@types/node",
    "update-types": ["version-update:semver-major"],
}

REDIS_UPGRADES_IGNORED = {
    "dependency-name": "redis",
    "update-types": ["version-update:semver-major"],
}

# Le motif de nom par lequel Dependabot reconnaît un Dockerfile (`DOCKER_REGEXP`,
# `docker/file_fetcher.rb`) — `Dockerfile`, `Dockerfile.prod`, `Dockerfile-dev`, `api.Dockerfile`,
# `Containerfile` —, moins les fichiers d'exclusion `*.dockerignore`. Un document dont le nom
# contiendrait « dockerfile » serait lu et échouerait : un rouge visible vaut mieux qu'un trou.
DOCKERFILE_NAME = re.compile(r"dockerfile|containerfile", re.IGNORECASE)
DOCKERIGNORE_SUFFIX = ".dockerignore"

# Le motif de nom par lequel Dependabot reconnaît un fichier Compose (`FILENAME_REGEX`,
# `docker_compose/file_fetcher.rb`), recopié tel quel : non ancré, il reconnaît `compose.dev.yml`
# comme `compose.yml`. Dependabot ne l'applique qu'aux fichiers du dossier configuré, sans descendre
# dans ses sous-dossiers.
COMPOSE_NAME = re.compile(r"(docker-)?compose(-[\w]+)?(?>\.[\w-]+)?\.ya?ml", re.IGNORECASE)

# Un `FROM` lu comme Docker le lit : l'instruction entière, continuations jointes, indentation
# permise. Et tel que Dependabot le lit : sa première ligne seule, en colonne 0, l'image sur cette
# ligne, `--platform` pour seule option (`FROM_LINE`, `docker/file_parser.rb`). Les deux lectures
# doivent trouver la même image, sans quoi Dependabot ne la mettrait jamais à jour.
DOCKER_FROM = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)(?:\s+AS\s+(?P<stage>\S+))?", re.IGNORECASE
)
DEPENDABOT_FROM = re.compile(
    r"^FROM[ \t]+(?:--platform=\S+[ \t]+)?(?P<image>[^\s\\]\S*)", re.IGNORECASE
)

# Les sources `from=` d'un `COPY` ou d'un `RUN`, lues dans les **options** de l'instruction
# seulement — un `RUN uvx --from=…` passe l'option à la commande, pas à Docker.
LEADING_OPTIONS = re.compile(r"^\s*(?:COPY|RUN)((?:\s+--\S+)+)", re.IGNORECASE)
FROM_SOURCE = re.compile(r"(?:--|[,=])from=([^\s,]+)", re.IGNORECASE)

# Un `ADD` qui télécharge, lu comme Docker : ses options en tête d'instruction, puis ses sources —
# en liste d'arguments ou en tableau JSON —, dont une adresse HTTP(S). BuildKit vérifie la somme
# d'un tel fichier avant de le copier quand les options portent `--checksum=sha256:<somme>` (doc
# Docker, « ADD --checksum ») ; sans elle, le fichier entre tel que le serveur le rend.
ADD_INSTRUCTION = re.compile(r"^\s*ADD(?P<options>(?:\s+--\S+)*)\s+(?P<sources>.*)$", re.IGNORECASE)
REMOTE_SOURCE = re.compile(r"(?:^|[\s\[\",])https?://", re.IGNORECASE)
CHECKSUM_OPTION = re.compile(r"(?:^|\s)--checksum=sha256:[0-9a-f]{64}(?:\s|$)")

# Un téléchargement par un `RUN` — `curl` ou `wget` vers une adresse HTTP(S) écrite en clair —,
# que rien ne vérifie : tout téléchargement passe par `ADD --checksum`. Le nom de l'outil est un mot
# entier, tiret compris : `curl-cffi` n'est pas `curl`. Les formes que ce motif ne lit pas —
# `git clone`, adresse tenue par un `ARG`, autre langage, `ADD git@` — figurent au recueil, en
# `xfail`.
RUN_DOWNLOAD = re.compile(
    r"^\s*RUN\b.*(?<![\w-])(?:curl|wget)(?![\w-])[^&;|]*https?://", re.IGNORECASE
)

# `image:<version x.y.z>[-variante]@sha256:<empreinte>` — même règle que pour les actions : la
# version la plus précise. Dependabot lit une épingle étiquette + empreinte comme « suivre les
# versions » (dependabot-core, PR #15103) : c'est une nouvelle version de correctif qui lui fait
# ouvrir une PR, et une étiquette sans correctif (`3.12`) n'en change jamais. Une image dont les
# étiquettes n'ont pas de version `x.y.z` demande une décision, pas un contournement de ce motif.
PINNED_IMAGE = re.compile(r"^[\w./:-]+:v?\d+\.\d+\.\d+[\w.-]*@sha256:[0-9a-f]{64}$")


# --- Les gardes : des fonctions sur du texte ---------------------------------------------------


def git_listing(root: Path, *flags: str) -> list[str]:
    """Les chemins que `git ls-files` rend sous ces drapeaux.

    `-z` rend les chemins bruts : sans lui, git met entre guillemets et échappe tout chemin non
    ASCII, qui ne désignerait plus aucun fichier.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", *flags],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [name for name in listing.split("\0") if name]


def repository_files(root: Path = REPOSITORY_ROOT) -> list[str]:
    """Les fichiers que le prochain commit peut contenir : suivis, ou nouveaux et non ignorés."""
    return git_listing(root, "--cached", "--others", "--exclude-standard")


def tracked_files(root: Path = REPOSITORY_ROOT) -> list[str]:
    """Les fichiers que le dépôt **contient**, index compris — le bloc-notes de personne.

    Distinct de `repository_files` : celui-ci inclut les fichiers nouveaux non ignorés, ce qui
    est juste pour une porte qui demande « que peut contenir le prochain commit ? », et faux
    pour une porte qui doit ignorer le brouillon **non suivi** d'une personne seule.

    Ce que cette population ne garantit pas : un verdict identique partout. `--cached` lit
    l'**index**, qui est local et ne se pousse pas — un brouillon simplement mis à l'index y
    entre, et fait alors rougir sur ce poste une porte que la CI voit verte. Mesuré le
    2026-10-12 sur `ee21cb5` : un fichier citant un module de test inexistant, `git add`-é et
    jamais commité, rend `test_aucun_renvoi_vers_un_module_de_test_inexistant` rouge en local.
    Le resserrement ferme le cas non suivi, pas la classe. Ce qui est épinglé, c'est la
    **différence entre les deux populations** :
    `test_les_deux_populations_de_fichiers_ne_sont_pas_la_meme` met `suivi.md` à l'index sans
    le commiter. Et que la porte emploie bien l'étroite est épinglé par
    `test_la_porte_des_renvois_ignore_un_brouillon_non_suivi`, qui **appelle la porte** au lieu
    de recalculer la population — c'est ce seul détail qui le distingue d'un doublon de
    `test_un_brouillon_non_suivi_n_entre_pas_dans_la_population`.

    Pourquoi deux tests, et pourquoi celui-là appelle la porte : sur un **arbre propre** les
    deux populations coïncident (239 chemins de part et d'autre — un décompte qui grossit à
    chaque lot, il se relit et ne se recopie pas), donc la ligne d'appel remise sur
    `repository_files()` laissait la suite **entièrement verte** — mutation vue VERTE le
    2026-10-12 sur `0b1790d`. Avec un brouillon **non suivi** planté à la racine, les deux
    populations divergent — l'étroite rend 11 modules cités et l'ignore, la large en rend 12 et
    le lit (ces décomptes bougent aussi) — et la même mutation rougit. C'est la divergence qui
    fait la preuve, pas l'un des deux verdicts.
    """
    return git_listing(root, "--cached")


def prose_citations(
    root: Path, population: Iterable[str], globs: Iterable[str], reference: re.Pattern[str]
) -> Iterator[tuple[Path, re.Match[str]]]:
    """Chaque renvoi que la prose du dépôt porte vers un artefact, avec le fichier qui le porte.

    La **lecture** est commune à toutes les portes de renvois entrants — parcourir des globs,
    écarter ce qui n'est pas dans la population, lire le fichier, apparier le motif. Ce qui
    diffère d'une porte à l'autre, c'est la population, le motif et la façon de résoudre le
    renvoi en chemin : chaque porte garde donc les trois chez elle, et une classe de renvoi
    supplémentaire s'ajoute par **extension** — un appel de plus — sans toucher à cette lecture.

    **Pathlib, pas wildmatch.** Les globs sont consommés par `Path.glob`, où `**` admet **zéro**
    composant : `.claude/**/*.md` apparie donc `.claude/pipeline.config.md`. Le `**` d'un pathspec
    git exige au moins un composant et ne l'apparie pas — mesuré. Une liste de globs transposée
    telle quelle en commande `git grep` rend donc moins de résultats que la porte, et c'est
    exactement ce qu'un dénombrement cité fait croire reproductible. Toute commande citée à côté
    d'une de ces populations ajoute le pathspec de la racine (`.claude/*.md`).

    Args:
        root: la racine à parcourir.
        population: les chemins relatifs, en POSIX, que l'appelant a le droit de lire. Tout
            fichier présent sur le disque mais absent de cette liste est ignoré — le choix de la
            population appartient donc à l'appelant.
        globs: les motifs de chemin, au sens de `Path.glob`, qui décrivent la prose à lire.
        reference: le motif du renvoi, dont les groupes nommés sont lus par l'appelant.

    Yields:
        Le couple (fichier citant, appariement). L'ordre n'est pas un engagement : les deux
        appelants agrègent dans un `dict` de `set`, et aucune porte n'en dépend.
    """
    allowed = set(population)
    for glob in globs:
        for path in root.glob(glob):
            if not path.is_file() or path.relative_to(root).as_posix() not in allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            yield from ((path, reference_found) for reference_found in reference.finditer(text))


def is_dockerfile(name: str) -> bool:
    """Le nom désigne-t-il un Dockerfile, au sens de Dependabot, hors `*.dockerignore` ?"""
    return bool(DOCKERFILE_NAME.search(name)) and not name.lower().endswith(DOCKERIGNORE_SUFFIX)


def uses_values(node: object) -> list[object]:
    """Les valeurs de toutes les clés `uses` d'un document YAML, à toute profondeur."""
    if isinstance(node, dict):
        mapping = cast(dict[object, object], node)
        found = [value for key, value in mapping.items() if key == "uses"]
        return found + [value for child in mapping.values() for value in uses_values(child)]
    if isinstance(node, list):
        return [value for item in cast(list[object], node) for value in uses_values(item)]
    return []


def workflow_findings(text: str) -> list[str]:
    """Ce qui, dans un workflow, n'est pas une action épinglée par empreinte.

    Returns:
        Un constat par `uses` non épinglé ou mal commenté ; un constat si l'analyseur YAML et le
        motif ne lisent pas les mêmes références — une forme que le motif ne sait pas vérifier.
        Liste vide : tout est épinglé.
    """
    matches = list(USES.finditer(text))
    read = {match["reference"] for match in matches}
    parsed = {str(value) for value in uses_values(yaml.safe_load(text))}
    unread = [f"forme non lue par le motif : {sorted(parsed ^ read)}"] if parsed != read else []
    return unread + [
        f"{match['reference']}{match['comment']}"
        for match in matches
        if not (
            PINNED_REFERENCE.match(match["reference"]) and VERSION_COMMENT.match(match["comment"])
        )
    ]


def dockerfile_instructions(text: str) -> list[tuple[str, str]]:
    """Les instructions d'un Dockerfile, chacune sous deux formes.

    Returns:
        Pour chaque instruction, dans l'ordre : sa première ligne telle qu'écrite — ce que lit
        Dependabot — et l'instruction entière, lignes de continuation jointes — ce que lit
        Docker. Lignes vides et commentaires sont écartés, y compris au milieu d'une
        continuation, comme Docker le fait.
    """
    instructions: list[tuple[str, str]] = []
    first, parts = "", list[str]()
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        first = first or line
        parts.append(line.rstrip().removesuffix("\\"))
        if not line.rstrip().endswith("\\"):
            instructions.append((first, " ".join(parts)))
            first, parts = "", []
    if first:
        instructions.append((first, " ".join(parts)))
    return instructions


def base_images(text: str) -> tuple[list[tuple[str, str]], set[str]]:
    """Les images de base d'un Dockerfile, et les noms d'étage qu'il déclare.

    Un `FROM` qui reprend un étage **déjà** déclaré n'est pas une image, ni `scratch`, image vide
    réservée par Docker : ils sont écartés. Un `FROM node AS node` cite donc bien l'image `node`.

    Returns:
        Pour chaque image, dans l'ordre : la première ligne de son `FROM` et l'image lue par
        Docker ; puis l'ensemble des noms d'étage, en minuscules.
    """
    images: list[tuple[str, str]] = []
    stages: set[str] = set()
    for first, instruction in dockerfile_instructions(text):
        declaration = DOCKER_FROM.match(instruction)
        if not declaration:
            continue
        if declaration["image"].lower() not in {*stages, "scratch"}:
            images.append((first, declaration["image"]))
        if declaration["stage"]:
            stages.add(declaration["stage"].lower())
    return images, stages


def image_findings(text: str) -> list[str]:
    """Ce qui, dans un Dockerfile, empêcherait Dependabot de tenir une image de base à jour.

    Returns:
        Un constat par BOM en tête (il cacherait le premier `FROM` à une lecture ligne à ligne),
        par `FROM` que Dependabot ne lit pas (indenté, image à la ligne suivante) et par image
        sans version `x.y.z` ni empreinte. Liste vide : tout est épinglé et lisible.
    """
    images, _ = base_images(text)
    unread = [
        f"`FROM` illisible par Dependabot : {image}"
        for first, image in images
        if not (read := DEPENDABOT_FROM.match(first)) or read["image"] != image
    ]
    unpinned = [
        f"sans version x.y.z devant l'empreinte : {image}"
        for _, image in images
        if not PINNED_IMAGE.match(image)
    ]
    return (["BOM en tête"] if text.startswith("\ufeff") else []) + unread + unpinned


def source_findings(text: str) -> list[str]:
    """Les images citées par `COPY --from` ou `RUN --mount=…from=` hors d'un étage nommé.

    Dependabot ne lit que les lignes `FROM` : une telle image ne serait jamais mise à jour. Un
    index (`--from=0`) désigne un étage par son rang, et n'échappe pas plus à Dependabot.
    """
    _, stages = base_images(text)
    sources = [
        source
        for _, instruction in dockerfile_instructions(text)
        if (options := LEADING_OPTIONS.match(instruction))
        for source in FROM_SOURCE.findall(options.group(1))
    ]
    return [source for source in sources if source.lower() not in stages and not source.isdigit()]


def downloads(text: str) -> list[tuple[str, str]]:
    """Les `ADD` d'un Dockerfile qui téléchargent : pour chacun, ses options et l'instruction
    entière, continuations jointes."""
    return [
        (match["options"], instruction)
        for _, instruction in dockerfile_instructions(text)
        if (match := ADD_INSTRUCTION.match(instruction)) and REMOTE_SOURCE.search(match["sources"])
    ]


def download_findings(text: str) -> list[str]:
    """Les téléchargements d'un Dockerfile que BuildKit ne vérifie pas : les `ADD` d'une adresse
    HTTP(S) dont les options ne portent pas de somme SHA-256 complète, et les `RUN` qui
    téléchargent par `curl` ou `wget`."""
    unchecked = [
        instruction
        for options, instruction in downloads(text)
        if not CHECKSUM_OPTION.search(options)
    ]
    fetched = [
        instruction
        for _, instruction in dockerfile_instructions(text)
        if RUN_DOWNLOAD.match(instruction)
    ]
    return unchecked + fetched


def compose_services(text: str) -> dict[str, object]:
    """Les services d'un fichier Compose ; une table vide si le document YAML n'en est pas un.

    Un fichier Compose se reconnaît à son contenu — sa clé `services` est une table —, pas à son
    nom : celui de la pile du test de fumée de `caddy` (`infra/tests/caddy.yml`) n'en porte pas la
    marque.
    """
    document: object = yaml.safe_load(text)
    if not isinstance(document, dict):
        return {}
    services = cast(dict[str, object], document).get("services")
    return cast(dict[str, object], services) if isinstance(services, dict) else {}


def third_party_images(text: str) -> list[str]:
    """Les images tierces d'un fichier Compose, dans l'ordre de ses services.

    Une image étiquetée par une variable, ou nommée par une variable sans défaut (`${…}`), est une
    image du dépôt, construite par `make build` et publiée sur GHCR : Dependabot la saute
    (`docker_compose/file_parser.rb`). Une image tierce écrite ainsi échapperait donc à cette
    lecture ; Dependabot, lui, lit la valeur par défaut d'un nom interpolé, mais saute une
    étiquette interpolée. Les deux formes figurent au recueil, en `xfail`. En production, une telle
    image rougit tout de même : `test_compose.py` n'y admet d'image interpolée que celles du dépôt.
    """
    images = [
        cast(dict[str, object], service).get("image")
        for service in compose_services(text).values()
        if isinstance(service, dict)
    ]
    return [image for image in images if isinstance(image, str) and "${" not in image]


def compose_findings(text: str) -> list[str]:
    """Les images tierces d'un fichier Compose que Dependabot ne pourrait pas tenir à jour : celles
    qui ne sont pas épinglées comme une image de base (`PINNED_IMAGE`)."""
    return [image for image in third_party_images(text) if not PINNED_IMAGE.match(image)]


DOCKERFILES = sorted(
    path
    for path in (REPOSITORY_ROOT / name for name in repository_files())
    if is_dockerfile(path.name) and path.is_file()
)

COMPOSE_FILES = sorted(
    path
    for path in (REPOSITORY_ROOT / name for name in repository_files())
    if path.suffix in {".yml", ".yaml"}
    and path.is_file()
    and compose_services(path.read_text(encoding="utf-8"))
)


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
PINNED_STEP = f"      - uses: actions/checkout@{SHA} # v7.0.1\n"
PYTHON = "python:3.12.14-slim-bookworm@sha256:" + "a" * 64
UV = "ghcr.io/astral-sh/uv:0.12.5@sha256:" + "b" * 64
BASE = f"FROM {PYTHON} AS base\n"

EXOTIC = pytest.mark.xfail(strict=True, reason="forme exotique, hors d'atteinte (docstring)")


def workflow(steps: str) -> str:
    """Un workflow minimal dont le seul job porte les étapes données."""
    return f"on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n{steps}"


# Forme → constat attendu (`True`) ou aucun (`False`).
WORKFLOW_FORMS = {
    "étape épinglée": (workflow(PINNED_STEP), False),
    "étiquette au lieu d'empreinte": (workflow("      - uses: actions/checkout@v7\n"), True),
    "empreinte courte": (workflow("      - uses: actions/checkout@3d3c42e # v7.0.1\n"), True),
    "commentaire majeur": (workflow(f"      - uses: actions/checkout@{SHA} # v7\n"), True),
    "mapping en flux": (workflow(f"      - {{ uses: actions/checkout@{SHA} }}\n"), True),
    "clé entre guillemets": (workflow(f'      - "uses": actions/checkout@{SHA}\n'), True),
    "flux avec # dans une chaîne": (
        workflow(f'      - {{ name: "Étape #1", uses: actions/checkout@{SHA} }}\n'),
        True,
    ),
    "ancre YAML reprise": (
        (
            "on: push\njobs:\n  a:\n    steps:\n      - &checkout\n"
            f"        uses: actions/checkout@{SHA} # v7.0.1\n"
            "  b:\n    steps:\n      - *checkout\n"
        ),
        False,
    ),
    "flux compensé par un bloc run:": (
        workflow("      - { uses: actions/checkout@v4 }\n      - run: |\n    " + PINNED_STEP),
        True,
    ),
    "commentaire citant uses:": (workflow("      # un mot sur `uses:`\n" + PINNED_STEP), False),
    "workflow réutilisable épinglé": (
        f"on: push\njobs:\n  a:\n    uses: org/repo/.github/workflows/x.yml@{SHA} # v1.0.0\n",
        False,
    ),
    "workflow réutilisable sur une branche": (
        "on: push\njobs:\n  a:\n    uses: org/repo/.github/workflows/x.yml@main\n",
        True,
    ),
    "workflow vide": ("", False),
    "clé uses sous le with: d'une action": pytest.param(
        workflow(PINNED_STEP + "        with:\n          uses: autre-chose\n"),
        False,
        marks=EXOTIC,
    ),
}

IMAGE_FORMS = {
    "épinglée, version x.y.z": (BASE, False),
    "sans empreinte": ("FROM python:3.12.14-slim-bookworm AS base\n", True),
    "étiquette sans correctif": (f"FROM python:3.12-slim@sha256:{'a' * 64}\n", True),
    "avec --platform, épinglée": (f"FROM --platform=linux/amd64 {PYTHON}\n", False),
    "avec --platform, non épinglée": ("FROM --platform=linux/amd64 python:3.12\n", True),
    "en minuscules, non épinglée": ("from python:3.12 as base\n", True),
    "sans AS, non épinglée": ("FROM python:3.12\n", True),
    "FROM d'image indenté": ("  " + BASE, True),
    "FROM d'étage indenté": (BASE + "  FROM base AS runtime\n", False),
    "image à la ligne suivante": (f"FROM \\\n    {PYTHON} AS base\n", True),
    "--platform puis image à la ligne": (f"FROM --platform=linux/amd64 \\\n    {PYTHON}\n", True),
    "AS à la ligne suivante": (f"FROM {PYTHON} \\\n    AS base\n", False),
    "scratch": ("FROM scratch\n", False),
    "registre avec port, épinglée": (f"FROM localhost:5000/{UV.split('/', 1)[1]} AS uv\n", False),
    "image portant le nom de son étage": ("FROM node AS node\n", True),
    "BOM en tête": ("\ufeff" + BASE, True),
    "from en continuation de RUN": (BASE + 'RUN python -c "\\\nfrom os import sep"\n', False),
    "from en colonne 0 dans un heredoc": pytest.param(
        BASE + "RUN <<EOF\nfrom os import sep\nEOF\n", False, marks=EXOTIC
    ),
}

STAGES = f"FROM {UV} AS uv\n" + BASE
SOURCE_FORMS = {
    "COPY --from=<étage>": (STAGES + "COPY --from=uv /uv /bin/uv\n", False),
    "COPY --from=<image>": (BASE + f"COPY --from={UV} /uv /bin/uv\n", True),
    "COPY avec --link et --chown": (BASE + f"COPY --link --chown=1:1 --from={UV} /a /b\n", True),
    "COPY sur deux lignes": (BASE + f"COPY \\\n    --from={UV} /uv /bin/uv\n", True),
    "COPY indenté": (BASE + f"  COPY --from={UV} /uv /bin/uv\n", True),
    "COPY --from=<index>": (STAGES + "COPY --from=0 /uv /bin/uv\n", False),
    "RUN --mount=from=<image>": (BASE + f"RUN --mount=from={UV},source=/uv,target=/x true\n", True),
    "RUN --mount=type=bind,from=": (
        BASE + f"RUN --mount=type=bind,from={UV},target=/x true\n",
        True,
    ),
    "RUN uvx --from=": (BASE + "RUN uvx --from=httpie http --version\n", False),
    "RUN pandoc --from=": (BASE + "RUN pandoc --from=markdown -o x x\n", False),
    "étage déclaré avec AS à la ligne": (
        f"FROM {UV} \\\n    AS uv\n" + BASE + "COPY --from=uv /uv /bin/uv\n",
        False,
    ),
    "option entre guillemets contenant une espace": pytest.param(
        BASE + f'RUN --mount=type=cache,target="/a b" --mount=from={UV},target=/x true\n',
        True,
        marks=EXOTIC,
    ),
}

SUM = "d" * 64
TOOL = "https://exemple.org/outil /usr/local/bin/outil"
DOWNLOAD_FORMS = {
    "somme épinglée": (BASE + f"ADD --checksum=sha256:{SUM} {TOOL}\n", False),
    "somme et droits": (BASE + f"ADD --chmod=755 --checksum=sha256:{SUM} {TOOL}\n", False),
    "somme, source à la ligne": (BASE + f"ADD --checksum=sha256:{SUM} \\\n    {TOOL}\n", False),
    "fichier du contexte": (BASE + "ADD outil.tar.gz /opt/\n", False),
    "sans somme": (BASE + f"ADD {TOOL}\n", True),
    "sans somme, source à la ligne": (BASE + f"ADD \\\n    {TOOL}\n", True),
    "en minuscules, sans somme": (BASE + f"add {TOOL}\n", True),
    "somme tronquée": (BASE + f"ADD --checksum=sha256:{SUM[:12]} {TOOL}\n", True),
    "somme hors des options": (BASE + f"ADD {TOOL} --checksum=sha256:{SUM}\n", True),
    "adresse en seconde source": (BASE + f"ADD outil.tar.gz {TOOL}\n", True),
    "JSON, somme épinglée": (
        BASE + f'ADD --checksum=sha256:{SUM} ["https://exemple.org/outil", "/outil"]\n',
        False,
    ),
    "JSON, sans somme": (BASE + 'ADD ["https://exemple.org/outil", "/outil"]\n', True),
    "RUN curl": (BASE + "RUN curl -fsSLo /outil https://exemple.org/outil\n", True),
    "RUN wget après un paquet": (
        BASE + "RUN apk add curl && wget -qO- https://exemple.org/outil | tar -x\n",
        True,
    ),
    "RUN qui installe curl": (BASE + "RUN apk add --no-cache curl\n", False),
    "paquet dont le nom commence par curl": (
        BASE + "RUN pip install curl-cffi --index-url https://exemple.org/simple\n",
        False,
    ),
    "RUN git clone": pytest.param(
        BASE + "RUN git clone https://exemple.org/outil.git\n", True, marks=EXOTIC
    ),
    "adresse tenue par un ARG": pytest.param(
        BASE + 'ARG URL=https://exemple.org/outil\nRUN curl -fsSLo /outil "$URL"\n',
        True,
        marks=EXOTIC,
    ),
    "téléchargement par un autre langage": pytest.param(
        BASE
        + 'RUN python -c "import urllib.request as u; '
        + "u.urlretrieve('https://exemple.org/o', '/o')\"\n",
        True,
        marks=EXOTIC,
    ),
    "ADD d'un dépôt git": pytest.param(
        BASE + "ADD git@exemple.org:outil.git /outil\n", True, marks=EXOTIC
    ),
}

DOCKERFILE_NAMES = {
    "Dockerfile": True,
    "Dockerfile.prod": True,
    "Dockerfile-dev": True,
    "api.Dockerfile": True,
    "Containerfile": True,
    "café.Dockerfile": True,
    "notes-dockerfile.md": True,  # voulu : lu, puis rouge — un rouge visible plutôt qu'un trou
    "Dockerfile.dockerignore": False,
    "Dockerfile.dev.dockerignore": False,
    "README.md": False,
    "compose.dev.yml": False,
}

REDIS = "redis:7.4.11-alpine@sha256:" + "c" * 64


def compose(image: str) -> str:
    """Un fichier Compose minimal dont le seul service porte l'image donnée."""
    return f"services:\n  cache:\n    image: {image}\n"


COMPOSE_FORMS = {
    "image tierce épinglée": (compose(REDIS), False),
    "étiquette de majeure": (compose("redis:7-alpine"), True),
    "étiquette sans empreinte": (compose("redis:7.4.11-alpine"), True),
    "empreinte sans étiquette": (compose(f"redis@sha256:{'c' * 64}"), True),
    "image du dépôt, préfixe interpolé": (compose("${IMAGE_PREFIX:-portfolio-}api"), False),
    "image du dépôt, étiquette interpolée": (
        compose("ghcr.io/plecart/portfolio-api:${IMAGE_TAG:?}"),
        False,
    ),
    "service construit, sans image": ("services:\n  api:\n    build: .\n", False),
    "image tierce derrière une variable à défaut": pytest.param(
        compose("${CACHE_IMAGE:-redis:7-alpine}"), True, marks=EXOTIC
    ),
    "image tierce, étiquette interpolée": pytest.param(
        compose("redis:${CACHE_TAG:-7-alpine}"), True, marks=EXOTIC
    ),
}

COMPOSE_NAMES = {
    "compose.yml": True,
    "compose.dev.yml": True,
    "docker-compose.yaml": True,
    "compose-prod.yml": True,
    "caddy.yml": False,
}


@pytest.mark.parametrize(("text", "expected"), WORKFLOW_FORMS.values(), ids=WORKFLOW_FORMS.keys())
def test_la_garde_des_actions_rend_son_verdict_sur_chaque_forme(text: str, expected: bool) -> None:
    """Chaque forme de `uses:` recensée : signalée si, et seulement si, elle n'est pas épinglée."""
    assert bool(workflow_findings(text)) is expected, workflow_findings(text)


@pytest.mark.parametrize(("text", "expected"), IMAGE_FORMS.values(), ids=IMAGE_FORMS.keys())
def test_la_garde_des_images_rend_son_verdict_sur_chaque_forme(text: str, expected: bool) -> None:
    """Chaque forme de `FROM` recensée : signalée si Dependabot ne pourrait pas la tenir à jour."""
    assert bool(image_findings(text)) is expected, image_findings(text)


@pytest.mark.parametrize(("text", "expected"), SOURCE_FORMS.values(), ids=SOURCE_FORMS.keys())
def test_la_garde_des_sources_rend_son_verdict_sur_chaque_forme(text: str, expected: bool) -> None:
    """Chaque forme de `from=` recensée : signalée si l'image échappe à un étage nommé."""
    assert bool(source_findings(text)) is expected, source_findings(text)


@pytest.mark.parametrize(("text", "expected"), DOWNLOAD_FORMS.values(), ids=DOWNLOAD_FORMS.keys())
def test_la_garde_des_telechargements_rend_son_verdict_sur_chaque_forme(
    text: str, expected: bool
) -> None:
    """Chaque forme d'`ADD` recensée : signalée si, et seulement si, elle télécharge sans somme."""
    assert bool(download_findings(text)) is expected, download_findings(text)


@pytest.mark.parametrize(("name", "expected"), DOCKERFILE_NAMES.items())
def test_un_dockerfile_se_reconnait_a_son_nom(name: str, expected: bool) -> None:
    """Le filtre de nom suit celui de Dependabot, moins les fichiers `*.dockerignore`."""
    assert is_dockerfile(name) is expected


@pytest.mark.parametrize(("text", "expected"), COMPOSE_FORMS.values(), ids=COMPOSE_FORMS.keys())
def test_la_garde_des_compose_rend_son_verdict_sur_chaque_forme(text: str, expected: bool) -> None:
    """Chaque forme d'`image:` recensée : signalée si, et seulement si, c'est une image tierce que
    Dependabot ne pourrait pas tenir à jour."""
    assert bool(compose_findings(text)) is expected, compose_findings(text)


@pytest.mark.parametrize(("name", "expected"), COMPOSE_NAMES.items())
def test_un_fichier_compose_se_reconnait_a_son_nom_comme_dependabot(
    name: str, expected: bool
) -> None:
    """Le motif de Dependabot, non ancré : `compose.dev.yml` en est, `caddy.yml` non."""
    assert bool(COMPOSE_NAME.search(name)) is expected


def test_un_dockerfile_pas_encore_suivi_est_deja_vu(tmp_path: Path) -> None:
    """Le prochain commit peut contenir un Dockerfile non encore ajouté : il est lu dès maintenant.

    Un nom non ASCII garde son chemin exact (`-z`) ; un fichier ignoré par `.gitignore` n'est pas
    lu, puisqu'il n'entrera dans aucun commit.
    """
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("ignoré.Dockerfile\n", encoding="utf-8")
    for name in ["Dockerfile", "café.Dockerfile", "ignoré.Dockerfile"]:
        (tmp_path / name).write_text(BASE, encoding="utf-8")

    listed = repository_files(tmp_path)

    assert {"Dockerfile", "café.Dockerfile"} <= set(listed)
    assert "ignoré.Dockerfile" not in listed


# --- Les fichiers du dépôt --------------------------------------------------------------------


def test_chaque_action_est_epinglee_par_empreinte_de_commit() -> None:
    """Une étiquette peut être déplacée par son propriétaire ou un attaquant ; une empreinte non.

    L'incident `tj-actions/changed-files` (2025) est passé par là : des étiquettes de version
    redirigées vers un commit malveillant, exécuté sans signal par tous les dépôts qui les
    suivaient (brief de #5).
    """
    workflows = sorted(path for glob in WORKFLOW_GLOBS for path in REPOSITORY_ROOT.glob(glob))
    texts = {path.name: path.read_text(encoding="utf-8") for path in workflows}

    assert any(USES.search(text) for text in texts.values()), "aucun `uses:` — motif aveugle ?"
    findings = {name: found for name, text in texts.items() if (found := workflow_findings(text))}
    assert not findings, f"{len(texts)} workflows repassés, actions non épinglées : {findings}"


def test_aucune_action_composite_n_echappe_a_dependabot() -> None:
    """L'entrée `github-actions` ne lit que `.github/workflows/` et la racine du dépôt.

    Une action composite de `.github/actions/` épinglée par empreinte n'y serait jamais mise à
    jour (`github_actions/file_fetcher.rb`, dependabot-core). Il n'en existe aucune : la première
    qui arrive fait échouer ce test, le temps d'ajouter son dossier à l'entrée Dependabot et à
    `WORKFLOW_GLOBS`.
    """
    composites = sorted(REPOSITORY_ROOT.glob(COMPOSITE_ACTION_GLOB))

    assert not composites, f"actions composites hors de Dependabot : {composites}"


def dependabot_updates() -> list[dict[str, Any]]:
    """Les entrées `updates` de `.github/dependabot.yml`."""
    return yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))["updates"]


def dependabot_entries(ecosystem: str) -> list[dict[str, Any]]:
    """Les entrées Dependabot d'un écosystème ; le test échoue s'il n'en a aucune."""
    entries = [entry for entry in dependabot_updates() if entry["package-ecosystem"] == ecosystem]
    assert entries, f"aucune entrée Dependabot pour « {ecosystem} »"
    return entries


def dependabot_entry(ecosystem: str) -> dict[str, Any]:
    """L'entrée Dependabot d'un écosystème qui n'en a qu'une ; le test échoue sinon."""
    entries = dependabot_entries(ecosystem)
    assert len(entries) == 1, (
        f"{len(entries)} entrées Dependabot pour « {ecosystem} », une attendue"
    )
    return entries[0]


def watched_directories(entry: dict[str, Any]) -> list[Path]:
    """Les dossiers qu'une entrée Dependabot surveille, par `directory`, `directories` ou les deux
    — ce dernier cas, invalide, est signalé par `policy_findings`, pas masqué ici."""
    names: list[str] = list(entry.get("directories", []))
    if "directory" in entry:
        names.append(entry["directory"])
    return [REPOSITORY_ROOT / name.lstrip("/") for name in names]


def watched_by(ecosystem: str) -> list[Path]:
    """Les dossiers que surveillent, ensemble, les entrées d'un écosystème."""
    return [path for entry in dependabot_entries(ecosystem) for path in watched_directories(entry)]


def location_findings(updates: list[dict[str, Any]]) -> list[str]:
    """Les dossiers qu'un même écosystème surveille plus d'une fois.

    Deux surveillances du même couple (écosystème, dossier) feraient deux jeux de PR pour les mêmes
    paquets. Le couple, et non l'écosystème : `docker` a une entrée par image, parce qu'une PR de
    groupe ouverte suspend l'examen de tous les dossiers de son entrée — « Deferring creation of a
    new pull request » aux journaux de Dependabot, cas `vu-group-multidir-all` de dependabot-core
    (brief de #125). Le dossier se compare en chemin, `/infra/api` et `infra/api/` ne font qu'un.
    """
    locations = Counter(
        (entry.get("package-ecosystem"), path)
        for entry in updates
        for path in watched_directories(entry)
    )
    return [
        f"{ecosystem} : {repository_id(path)} surveillé {count} fois"
        for (ecosystem, path), count in sorted(locations.items(), key=str)
        if count > 1
    ]


def policy_findings(entry: dict[str, Any]) -> list[str]:
    """Ce en quoi une entrée Dependabot s'écarte de la politique commune (`UPDATE_POLICY`).

    Chaque entrée porte sa copie de la politique, et chacune se compare à la constante, aucune aux
    autres : une copie qui dériverait seule rougit ici. Un écosystème inconnu, un dossier absent
    ou nommé deux fois, une clé hors de la politique et de ses écarts (`ECOSYSTEM_EXTRA_KEYS`) sont
    signalés aussi.
    """
    ecosystem = entry.get("package-ecosystem")
    findings = [] if ecosystem in ECOSYSTEM_MANIFESTS else [f"écosystème inconnu : {ecosystem!r}"]
    findings += [
        f"{ecosystem} : `{key}` vaut {entry.get(key)!r}"
        for key, expected in UPDATE_POLICY.items()
        if entry.get(key) != expected
    ]
    if len(set(entry) & LOCATION_KEYS) != 1:
        findings.append(f"{ecosystem} : `directory` ou `directories`, exactement un des deux")
    allowed = ENTRY_KEYS | LOCATION_KEYS | ECOSYSTEM_EXTRA_KEYS.get(str(ecosystem), set())
    findings += [
        f"{ecosystem} : clé hors politique `{key}`" for key in sorted(set(entry) - allowed)
    ]
    return findings


def dependabot_findings(updates: list[dict[str, Any]]) -> list[str]:
    """Les écarts d'une configuration Dependabot : dossiers surveillés deux fois, entrées hors
    politique."""
    return location_findings(updates) + [
        finding for entry in updates for finding in policy_findings(entry)
    ]


def update_entry(ecosystem: str, **keys: Any) -> dict[str, Any]:
    """Une entrée Dependabot conforme à la politique, plus `keys` ; une clé à `None` est retirée."""
    entry = {"package-ecosystem": ecosystem, **UPDATE_POLICY, **keys}
    return {key: value for key, value in entry.items() if value is not None}


DEPENDABOT_FORMS = {
    "une entrée par image": (
        [
            update_entry("docker", directory="/infra/api"),
            update_entry("docker", directory="/infra/caddy"),
        ],
        False,
    ),
    "même dossier, deux écosystèmes": (
        [update_entry("uv", directory="/"), update_entry("github-actions", directory="/")],
        False,
    ),
    "un `ignore` sur une entrée docker": (
        [update_entry("docker", directory="/infra/api", ignore=[PYTHON_UPGRADES_IGNORED])],
        False,
    ),
    "même dossier, deux entrées du même écosystème": (
        [
            update_entry("docker", directory="/infra/api"),
            update_entry("docker", directories=["/infra/caddy", "/infra/api"]),
        ],
        True,
    ),
    "même dossier, deux fois dans une entrée": (
        [update_entry("docker", directories=["/infra/api", "infra/api/"])],
        True,
    ),
    "cadence mensuelle": (
        [update_entry("docker", directory="/infra/caddy", schedule={"interval": "monthly"})],
        True,
    ),
    "sans groupe": ([update_entry("docker", directory="/infra/caddy", groups=None)], True),
    "libellés du bot": ([update_entry("docker", directory="/infra/caddy", labels=None)], True),
    "préfixe de commit autre": (
        [
            update_entry(
                "docker", directory="/infra/caddy", **{"commit-message": {"prefix": "deps"}}
            )
        ],
        True,
    ),
    "clé hors politique": (
        [update_entry("docker", directory="/infra/caddy", **{"open-pull-requests-limit": 0})],
        True,
    ),
    "un `ignore` hors des écarts permis": (
        [update_entry("uv", directory="/", ignore=[PYTHON_UPGRADES_IGNORED])],
        True,
    ),
    "`directory` et `directories`": (
        [update_entry("docker", directory="/a", directories=["/b"])],
        True,
    ),
    "aucun dossier": ([update_entry("docker")], True),
    "écosystème inconnu": ([update_entry("pip", directory="/")], True),
}


@pytest.mark.parametrize(
    ("updates", "expected"), DEPENDABOT_FORMS.values(), ids=DEPENDABOT_FORMS.keys()
)
def test_la_garde_de_dependabot_rend_son_verdict_sur_chaque_forme(
    updates: list[dict[str, Any]], expected: bool
) -> None:
    """Chaque forme recensée : signalée si un dossier est surveillé deux fois par un même
    écosystème, ou si une entrée s'écarte de la politique commune."""
    assert bool(dependabot_findings(updates)) is expected, dependabot_findings(updates)


def test_chaque_entree_dependabot_suit_la_politique_de_mise_a_jour() -> None:
    """Même politique partout, et aucun dossier surveillé deux fois par un même écosystème."""
    assert dependabot_findings(dependabot_updates()) == []


def test_dependabot_surveille_chaque_ecosysteme() -> None:
    """Un écosystème sans entrée n'aurait aucune PR."""
    ecosystems = {entry["package-ecosystem"] for entry in dependabot_updates()}

    assert ecosystems == set(ECOSYSTEM_MANIFESTS)


@pytest.mark.parametrize(("ecosystem", "manifest"), sorted(ECOSYSTEM_MANIFESTS.items()))
def test_chaque_dossier_surveille_contient_ce_que_dependabot_y_lit(
    ecosystem: str, manifest: str
) -> None:
    """Un dossier déplacé sans sa ligne de configuration ne fait échouer que la tâche Dependabot,
    dans un onglet que personne ne lit : ce test le fait échouer ici."""
    directories = watched_by(ecosystem)

    assert directories, f"les entrées « {ecosystem} » ne surveillent aucun dossier"
    assert [path for path in directories if not (path / manifest).exists()] == []


def test_chaque_image_a_son_entree_dependabot() -> None:
    """Une entrée `docker` par dossier d'image : une PR de groupe ouverte pour une image suspend
    l'examen des seuls dossiers de son entrée (`location_findings`), donc d'aucune autre image."""
    watched = [
        [repository_id(path) for path in watched_directories(entry)]
        for entry in dependabot_entries("docker")
    ]
    shared = [directories for directories in watched if len(directories) != 1]

    assert not shared, f"entrées `docker` qui surveillent plusieurs images : {shared}"


def test_dependabot_ne_propose_jamais_de_nouvelle_version_de_python() -> None:
    """La version de Python est une décision du projet, pas une mise à jour.

    `.python-version` l'épingle et l'image la suit sous test (`test_infra.py`) : une PR qui
    proposerait `3.13.x-slim-trixie` échouerait chaque semaine, par construction. Dependabot ne
    propose donc, pour l'image qui part de Python, que les versions de correctif de la 3.12 — et
    pour elle seule : sur une autre image, le refus viserait un paquet qu'elle n'a pas, et
    refuserait en silence le jour où elle en aurait un.
    """
    refusals = {
        repository_id(path): entry.get("ignore", [])
        for entry in dependabot_entries("docker")
        for path in watched_directories(entry)
    }
    expected = {
        repository_id(dockerfile.parent): (
            [PYTHON_UPGRADES_IGNORED]
            if any(
                image.startswith("python:")
                for _, image in base_images(dockerfile.read_text(encoding="utf-8"))[0]
            )
            else []
        )
        for dockerfile in DOCKERFILES
    }

    assert [PYTHON_UPGRADES_IGNORED] in expected.values(), "aucune image ne part de Python"
    assert refusals == expected


def test_dependabot_ne_propose_jamais_de_nouvelle_majeure_de_redis() -> None:
    """Redis 7 est une décision du projet (ADR 0006), comme la version de Python : une PR Redis 8
    se refuserait à chaque passage. Les versions de correctif de la 7 passent."""
    ignored = dependabot_entry("docker-compose").get("ignore", [])

    assert ignored == [REDIS_UPGRADES_IGNORED]


def npm_majors_refused() -> list[dict[str, Any]]:
    """Les règles `ignore` que la table des refus npm exige, dans son ordre.

    `apps/web/dependency-refusals.json` est la seule liste des refus qui expirent : chaque entrée
    nomme les paquets dont la majeure est refusée et le plugin dont la plage de pairs fonde le
    refus. Le test Vitest qui les fait expirer lit la même table.
    """
    refusals = json.loads(NPM_REFUSALS.read_text(encoding="utf-8"))
    return [
        {"dependency-name": name, "update-types": ["version-update:semver-major"]}
        for refusal in refusals
        for name in refusal["refused"]
    ]


def test_dependabot_ne_refuse_sur_npm_que_la_table_des_refus_et_les_types_de_node() -> None:
    """Les `ignore` npm sont ceux de la table des refus, puis celui de `@types/node`.

    Une règle hors de la table refuserait en silence et pour toujours : aucun test ne la ferait
    expirer. Une entrée de la table sans sa règle ne refuserait rien. Retirer une entrée pour faire
    taire le test qui expire rougit donc ici, tant que la règle reste en place : le refus se lève
    en entier, ou pas du tout (`docs/frontend-outillage.md` §2.4).

    `@types/node` est la seule règle hors table, parce qu'elle ne tombe jamais seule : ses types
    suivent la majeure de Node, que le projet change à la main, comme la version de Python de
    l'image. `apps/web/tests/configuration.test.ts` exige les deux majeures égales ; la règle
    empêche Dependabot de proposer, chaque semaine, des types en avance sur le runtime.
    """
    ignored = dependabot_entry("npm").get("ignore", [])

    assert ignored == [*npm_majors_refused(), NODE_TYPES_UPGRADES_IGNORED]


def repository_id(path: Path) -> str:
    """Identifiant de paramètre lisible : le chemin du fichier depuis la racine du dépôt."""
    return path.relative_to(REPOSITORY_ROOT).as_posix()


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=repository_id)
def test_chaque_image_de_base_est_epinglee_par_empreinte(dockerfile: Path) -> None:
    """Une étiquette d'image peut changer de contenu ; une empreinte non.

    Le guide « Building best practices » de Docker le recommande. L'étiquette reste devant
    l'empreinte, à sa version la plus précise : c'est elle qui porte les mises à jour, Dependabot
    proposant la version de correctif suivante, étiquette et empreinte ensemble. Et chaque `FROM`
    doit lui être lisible — colonne 0, image sur la première ligne —, sans quoi l'épingle ne
    bougerait jamais.
    """
    text = dockerfile.read_text(encoding="utf-8")

    assert base_images(text)[0], "aucune image de base trouvée — le motif a-t-il cessé de mordre ?"
    assert not image_findings(text), image_findings(text)


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=repository_id)
def test_toute_image_copiee_passe_par_un_etage_nomme(dockerfile: Path) -> None:
    """Dependabot ne lit que les lignes `FROM` (`docker/file_parser.rb`, dependabot-core).

    Une image citée seulement par `COPY --from=<image>` ou `RUN --mount=from=<image>` ne serait
    jamais mise à jour : elle est déclarée dans un étage à elle, dont le nom est repris ensuite.
    """
    outside = source_findings(dockerfile.read_text(encoding="utf-8"))

    assert not outside, f"sources `from=` hors d'un étage : {outside}"


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=repository_id)
def test_chaque_telechargement_d_une_image_est_verifie_par_sa_somme(dockerfile: Path) -> None:
    """Un binaire sans image officielle entre par le fichier de sa release (`age`, `supercronic` :
    brief de #23, décision 1), que Dependabot ne suit pas : sa somme épinglée est la seule chose
    qui l'empêche de changer en silence, chez l'éditeur ou en chemin. Un `RUN curl` ou `wget`
    n'en a aucune : tout téléchargement passe par `ADD --checksum`."""
    findings = download_findings(dockerfile.read_text(encoding="utf-8"))

    assert not findings, f"téléchargements sans somme : {findings}"


def test_la_garde_des_telechargements_lit_ceux_du_depot() -> None:
    """Une garde qui ne lit aucun téléchargement passe à vide : l'image `backup` en porte."""
    assert any(downloads(path.read_text(encoding="utf-8")) for path in DOCKERFILES), (
        "aucun `ADD` d'une adresse lu — le motif a-t-il cessé de mordre ?"
    )


def test_dependabot_surveille_chaque_dockerfile() -> None:
    """Une image épinglée que Dependabot ne surveille pas garderait son empreinte pour toujours.

    Les deux tests ci-dessus s'appliquent à tout Dockerfile du dépôt ; celui-ci exige que son
    dossier figure aussi dans `.github/dependabot.yml`, sans quoi l'épinglage figerait l'image au
    lieu de la tenir à jour.
    """
    watched = watched_by("docker")

    unwatched = [repository_id(path) for path in DOCKERFILES if path.parent not in watched]
    assert not unwatched, (
        f"{len(DOCKERFILES)} Dockerfile repassés, hors de Dependabot : {unwatched}"
    )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=repository_id)
def test_chaque_image_tierce_d_un_compose_est_epinglee_par_empreinte(compose_file: Path) -> None:
    """Même règle que pour les images de base, pour la même raison : une étiquette peut changer de
    contenu, une empreinte non, et l'étiquette précise devant elle porte les mises à jour (brief de
    #16, décision 5)."""
    findings = compose_findings(compose_file.read_text(encoding="utf-8"))

    assert not findings, f"images tierces non épinglées : {findings}"


def test_dependabot_lit_chaque_compose_qui_cite_une_image_tierce() -> None:
    """Une image épinglée que Dependabot ne lit pas garderait son empreinte pour toujours. Il ne
    lit que les fichiers du dossier configuré dont le nom répond à son motif (`COMPOSE_NAME`)."""
    watched = watched_directories(dependabot_entry("docker-compose"))
    citing = [
        path for path in COMPOSE_FILES if third_party_images(path.read_text(encoding="utf-8"))
    ]

    assert citing, "aucun fichier Compose ne cite d'image tierce — la lecture a-t-elle cessé ?"
    unread = [
        repository_id(path)
        for path in citing
        if path.parent not in watched or not COMPOSE_NAME.search(path.name)
    ]
    assert not unread, (
        f"{len(COMPOSE_FILES)} fichiers Compose repassés, hors de Dependabot : {unread}"
    )
