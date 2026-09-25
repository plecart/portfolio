"""Tests de la chaîne d'approvisionnement : actions et images épinglées, Dependabot.

Comme `test_infra.py`, ces tests lisent des fichiers de configuration sans rien exécuter. Ils
gardent ce qui ne se verrait qu'après le merge, et en silence : une action ou une image qui suit
une étiquette déplaçable, un écosystème que Dependabot ne surveille plus. La porte d'audit Python
a ses propres tests, dans `test_pip_audit_gate.py`.

Chaque garde lit les fichiers comme l'outil qu'elle protège : le YAML par un analyseur YAML, un
Dockerfile instruction par instruction comme Docker, et chaque `FROM` par sa première ligne comme
Dependabot. Un motif qui imiterait l'analyseur à la main laisserait passer les formes qu'il n'a
pas prévues — les relectures de #5 ont rejoué 34 formes contre ces gardes (indentation,
continuation, ancre YAML, mapping en flux, `RUN --mount=from=`, BOM, nom non ASCII, fichier pas
encore suivi…), chacune au verdict attendu. Trois restent hors d'atteinte, jugées exotiques : une option de `RUN` dont la valeur entre guillemets contient
une espace, une clé `uses` sous le `with:` d'une action tierce, un `from` en colonne 0 dans un
heredoc.
"""

import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

# `test_supply_chain.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPENDABOT = REPOSITORY_ROOT / ".github" / "dependabot.yml"
WORKFLOW_GLOBS = [".github/workflows/*.yml", ".github/workflows/*.yaml"]
COMPOSITE_ACTION_GLOB = ".github/actions/**/action.y*ml"

# `uses: owner/action@<empreinte> # vX.Y.Z`. Le commentaire porte l'étiquette **la plus précise**
# du commit : Dependabot réécrit un commentaire qui se termine par une étiquette pointant encore
# sur le commit épinglé (`version_commenter.rb`, dependabot-core), et une étiquette majeure
# (`v7`) cesse d'y pointer dès qu'une version sort — précisément quand la mise à jour arrive.
# Le motif lit la ligne, commentaire compris ; l'analyseur YAML lit les `uses` réels, et les deux
# ensembles de références doivent coïncider — une forme que le motif ne lit pas (mapping en flux,
# clé entre guillemets) fait échouer le test au lieu de passer inaperçue. Des ensembles et non
# des décomptes : une ancre YAML reprise ailleurs compte deux fois pour l'analyseur.
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
}

# La politique commune à tous les écosystèmes : passage hebdomadaire, mineures et correctifs
# groupés — les majeures restent seules, chacune dans sa PR —, aucun libellé hors du mapping de
# `.claude/pipeline.config.md`, commits au format conventional du dépôt (brief de #5, briefing du
# 2026-09-25).
UPDATE_POLICY: dict[str, Any] = {
    "schedule": {"interval": "weekly"},
    "groups": {"minor-and-patch": {"update-types": ["minor", "patch"]}},
    "labels": [],
    "commit-message": {"prefix": "chore", "include": "scope"},
}

# Les clés qu'une entrée peut porter, toutes : la politique, plus ce qui identifie l'écosystème,
# plus les écarts décidés écosystème par écosystème. Une clé de plus peut changer la politique en
# silence — `open-pull-requests-limit: 0` coupe les mises à jour, un `ignore: "*"` aussi.
ENTRY_KEYS = {"package-ecosystem", "directory", *UPDATE_POLICY}
ECOSYSTEM_EXTRA_KEYS = {"docker": {"ignore"}}

PYTHON_UPGRADES_IGNORED = {
    "dependency-name": "python",
    "update-types": ["version-update:semver-major", "version-update:semver-minor"],
}

# Le motif de nom par lequel Dependabot reconnaît un Dockerfile (`DOCKER_REGEXP`,
# `docker/file_fetcher.rb`) — `Dockerfile`, `Dockerfile.prod`, `Dockerfile-dev`, `api.Dockerfile`,
# `Containerfile` —, moins les fichiers d'exclusion `*.dockerignore`. Un document dont le nom
# contiendrait « dockerfile » serait lu et échouerait : un rouge visible vaut mieux qu'un trou.
DOCKERFILE_NAME = re.compile(r"dockerfile|containerfile", re.IGNORECASE)
DOCKERIGNORE_SUFFIX = ".dockerignore"

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

# `image:<version x.y.z>[-variante]@sha256:<empreinte>` — même règle que pour les actions : la
# version la plus précise. Dependabot lit une épingle étiquette + empreinte comme « suivre les
# versions » (dependabot-core, PR #15103) : c'est une nouvelle version de correctif qui lui fait
# ouvrir une PR, et une étiquette sans correctif (`3.12`) n'en change jamais. Une image dont les
# étiquettes n'ont pas de version `x.y.z` demande une décision, pas un contournement de ce motif.
PINNED_IMAGE = re.compile(r"^[\w./:-]+:v?\d+\.\d+\.\d+[\w.-]*@sha256:[0-9a-f]{64}$")


def repository_files() -> list[str]:
    """Les fichiers que le prochain commit peut contenir : suivis, ou nouveaux et non ignorés.

    `-z` rend les chemins bruts : sans lui, git met entre guillemets et échappe tout chemin non
    ASCII, qui ne désignerait plus aucun fichier.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [name for name in listing.split("\0") if name]


DOCKERFILES = sorted(
    path
    for path in (REPOSITORY_ROOT / name for name in repository_files())
    if DOCKERFILE_NAME.search(path.name)
    and not path.name.lower().endswith(DOCKERIGNORE_SUFFIX)
    and path.is_file()
)


def uses_values(node: object) -> list[object]:
    """Les valeurs de toutes les clés `uses` d'un document YAML, à toute profondeur."""
    if isinstance(node, dict):
        mapping = cast(dict[object, object], node)
        found = [value for key, value in mapping.items() if key == "uses"]
        return found + [value for child in mapping.values() for value in uses_values(child)]
    if isinstance(node, list):
        return [value for item in cast(list[object], node) for value in uses_values(item)]
    return []


def test_chaque_action_est_epinglee_par_empreinte_de_commit() -> None:
    """Une étiquette peut être déplacée par son propriétaire ou par un attaquant ; une empreinte non.

    L'incident `tj-actions/changed-files` (2025) est passé par là : des étiquettes de version
    redirigées vers un commit malveillant, exécuté sans signal par tous les dépôts qui les
    suivaient (brief de #5).
    """
    workflows = sorted(path for glob in WORKFLOW_GLOBS for path in REPOSITORY_ROOT.glob(glob))
    found: list[tuple[str, re.Match[str]]] = []
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        matches = list(USES.finditer(text))
        parsed = {str(value) for value in uses_values(yaml.safe_load(text))}
        assert parsed == {match["reference"] for match in matches}, (
            f"{workflow.name} : un `uses` échappe au motif — forme non lue, donc non vérifiée"
        )
        found += [(workflow.name, match) for match in matches]

    assert found, "aucun `uses:` trouvé — le motif a-t-il cessé de mordre ?"
    unpinned = [
        f"{name} : {match.group('reference')}{match.group('comment')}"
        for name, match in found
        if not (
            PINNED_REFERENCE.match(match.group("reference"))
            and VERSION_COMMENT.match(match.group("comment"))
        )
    ]
    assert not unpinned, f"{len(found)} `uses:` repassés, non épinglés : {unpinned}"


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
    """Les entrées `updates` de `.github/dependabot.yml`, une par écosystème surveillé."""
    return yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))["updates"]


def dependabot_entry(ecosystem: str) -> dict[str, Any]:
    """L'entrée Dependabot d'un écosystème ; le test échoue si elle manque."""
    entries = [entry for entry in dependabot_updates() if entry["package-ecosystem"] == ecosystem]
    assert entries, f"aucune entrée Dependabot pour « {ecosystem} »"
    return entries[0]


def test_dependabot_surveille_chaque_ecosysteme_une_seule_fois() -> None:
    """Une entrée en double ferait deux jeux de PR pour les mêmes dépendances ; une en moins, aucun."""
    ecosystems = sorted(entry["package-ecosystem"] for entry in dependabot_updates())

    assert ecosystems == sorted(ECOSYSTEM_MANIFESTS)


@pytest.mark.parametrize(("ecosystem", "manifest"), sorted(ECOSYSTEM_MANIFESTS.items()))
def test_chaque_ecosysteme_suit_la_politique_de_mise_a_jour(ecosystem: str, manifest: str) -> None:
    """Même politique partout, et un dossier qui contient bien ce que Dependabot doit y lire.

    Un dossier déplacé sans sa ligne de configuration ne fait échouer que la tâche Dependabot,
    dans un onglet que personne ne lit : ce test le fait échouer ici.
    """
    entry = dependabot_entry(ecosystem)
    directory = REPOSITORY_ROOT / entry["directory"].lstrip("/")

    assert (directory / manifest).exists(), f"{manifest} introuvable dans {entry['directory']}"
    assert {key: entry.get(key) for key in UPDATE_POLICY} == UPDATE_POLICY
    assert set(entry) == ENTRY_KEYS | ECOSYSTEM_EXTRA_KEYS.get(ecosystem, set())


def test_dependabot_ne_propose_jamais_de_nouvelle_version_de_python() -> None:
    """La version de Python est une décision du projet, pas une mise à jour.

    `.python-version` l'épingle et l'image la suit sous test (`test_infra.py`) : une PR qui
    proposerait `3.13.x-slim-bookworm` échouerait chaque semaine, par construction. Dependabot ne
    propose donc, pour cette image, que les versions de correctif de la 3.12.
    """
    ignored = dependabot_entry("docker").get("ignore", [])

    assert ignored == [PYTHON_UPGRADES_IGNORED]


def dockerfile_instructions(dockerfile: Path) -> list[tuple[str, str]]:
    """Les instructions d'un Dockerfile, chacune sous deux formes.

    Returns:
        Pour chaque instruction, dans l'ordre : sa première ligne telle qu'écrite — ce que lit
        Dependabot — et l'instruction entière, lignes de continuation jointes — ce que lit
        Docker. Lignes vides et commentaires sont écartés, y compris au milieu d'une
        continuation, comme Docker le fait.
    """
    instructions: list[tuple[str, str]] = []
    first, parts = "", list[str]()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
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


def base_images(dockerfile: Path) -> tuple[list[tuple[str, str]], set[str]]:
    """Les images de base d'un Dockerfile, et les noms d'étage qu'il déclare.

    Un `FROM` qui reprend un étage **déjà** déclaré n'est pas une image, ni `scratch`, image vide
    réservée par Docker : ils sont écartés. Un `FROM node AS node` cite donc bien l'image `node`.

    Returns:
        Pour chaque image, dans l'ordre : la première ligne de son `FROM` et l'image lue par
        Docker ; puis l'ensemble des noms d'étage, en minuscules.
    """
    images: list[tuple[str, str]] = []
    stages: set[str] = set()
    for first, instruction in dockerfile_instructions(dockerfile):
        declaration = DOCKER_FROM.match(instruction)
        if not declaration:
            continue
        if declaration["image"].lower() not in {*stages, "scratch"}:
            images.append((first, declaration["image"]))
        if declaration["stage"]:
            stages.add(declaration["stage"].lower())
    return images, stages


def dockerfile_id(path: Path) -> str:
    """Identifiant de paramètre lisible : le chemin du Dockerfile depuis la racine du dépôt."""
    return path.relative_to(REPOSITORY_ROOT).as_posix()


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=dockerfile_id)
def test_chaque_image_de_base_est_epinglee_par_empreinte(dockerfile: Path) -> None:
    """Une étiquette d'image peut changer de contenu ; une empreinte non.

    Le guide « Building best practices » de Docker le recommande. L'étiquette reste devant
    l'empreinte, à sa version la plus précise : c'est elle qui porte les mises à jour, Dependabot
    proposant la version de correctif suivante, étiquette et empreinte ensemble. Et chaque `FROM`
    doit lui être lisible — colonne 0, image sur la première ligne —, sans quoi l'épingle ne
    bougerait jamais. Un BOM en tête cacherait le premier `FROM` à une lecture ligne à ligne.
    """
    assert not dockerfile.read_text(encoding="utf-8").startswith("﻿"), "BOM en tête"
    images, _ = base_images(dockerfile)

    assert images, "aucune image de base trouvée — le motif a-t-il cessé de mordre ?"
    unread = [
        image
        for first, image in images
        if not (read := DEPENDABOT_FROM.match(first)) or read["image"] != image
    ]
    assert not unread, f"`FROM` que Dependabot ne lit pas (indenté, image à la ligne) : {unread}"
    unpinned = [image for _, image in images if not PINNED_IMAGE.match(image)]
    assert not unpinned, (
        f"{len(images)} images repassées, sans version x.y.z devant l'empreinte : {unpinned}"
    )


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=dockerfile_id)
def test_toute_image_copiee_passe_par_un_etage_nomme(dockerfile: Path) -> None:
    """Dependabot ne lit que les lignes `FROM` (`docker/file_parser.rb`, dependabot-core).

    Une image citée seulement par `COPY --from=<image>` ou `RUN --mount=from=<image>` ne serait
    jamais mise à jour : elle est déclarée dans un étage à elle, dont le nom est repris ensuite.
    """
    _, stages = base_images(dockerfile)
    sources = [
        source
        for _, instruction in dockerfile_instructions(dockerfile)
        if (options := LEADING_OPTIONS.match(instruction))
        for source in FROM_SOURCE.findall(options.group(1))
    ]

    # Un index (`--from=0`) désigne un étage par son rang : il n'échappe pas plus à Dependabot.
    outside = [
        source for source in sources if source.lower() not in stages and not source.isdigit()
    ]
    assert not outside, f"{len(sources)} sources `from=` repassées, hors d'un étage : {outside}"


def test_dependabot_surveille_chaque_dockerfile() -> None:
    """Une image épinglée que Dependabot ne surveille pas garderait son empreinte pour toujours.

    Les deux tests ci-dessus s'appliquent à tout Dockerfile du dépôt ; celui-ci exige que son
    dossier figure aussi dans `.github/dependabot.yml`, sans quoi l'épinglage figerait l'image au
    lieu de la tenir à jour.
    """
    watched = REPOSITORY_ROOT / dependabot_entry("docker")["directory"].lstrip("/")

    unwatched = [dockerfile_id(path) for path in DOCKERFILES if path.parent != watched]
    assert not unwatched, (
        f"{len(DOCKERFILES)} Dockerfile repassés, hors de Dependabot : {unwatched}"
    )
