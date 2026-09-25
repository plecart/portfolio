"""Tests de la chaîne d'approvisionnement : actions et images épinglées, Dependabot.

Comme `test_infra.py`, ces tests lisent des fichiers de configuration sans rien exécuter. Ils
gardent ce qui ne se verrait qu'après le merge, et en silence : une action ou une image qui suit
une étiquette déplaçable, un écosystème que Dependabot ne surveille plus. La porte d'audit Python
a ses propres tests, dans `test_pip_audit_gate.py`.

Chaque garde lit les fichiers comme l'outil qu'elle protège : le YAML par un analyseur YAML, les
`FROM` ligne à ligne comme Dependabot. Un motif qui imiterait l'analyseur à la main laisserait
passer les formes qu'il n'a pas prévues : les relectures de #5 en ont recensé 25 (indentation,
continuation, mapping en flux, clé entre guillemets, `RUN --mount=from=`, nom non ASCII, fichier
pas encore suivi…), toutes rejouées contre ces gardes.
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
# Le motif lit la ligne, commentaire compris ; l'analyseur YAML compte les `uses` réels, et les
# deux décomptes doivent coïncider — une forme que le motif ne lit pas (mapping en flux, clé entre
# guillemets) fait échouer le test au lieu de passer inaperçue.
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

# Les noms de fichier que Docker traite comme un Dockerfile : `Dockerfile`, `Dockerfile.<variante>`,
# `<nom>.Dockerfile`, et leurs équivalents `Containerfile` — pas un `.md` qui en parle, ni un
# `Dockerfile.dockerignore`.
DOCKERFILE_NAME = re.compile(
    r"^(?:dockerfile|containerfile)(?:\.(?!dockerignore$).+)?$|\.(?:dockerfile|containerfile)$",
    re.IGNORECASE,
)

# Deux lectures d'un `FROM`. Celle de Docker : toute ligne qui ouvre une instruction `FROM`, même
# indentée ou continuée sur la ligne suivante. Celle de Dependabot : la colonne 0, l'image sur la
# même ligne, seule option `--platform` (`FROM_LINE`, `docker/file_parser.rb`). Tout `FROM` de
# Docker doit être lisible par Dependabot, sans quoi son image ne serait jamais mise à jour.
FROM_INSTRUCTION = re.compile(r"^[ \t]*FROM\b", re.MULTILINE | re.IGNORECASE)
READABLE_FROM = re.compile(
    r"^FROM[ \t]+(?:--platform=\S+[ \t]+)?(?P<image>[^\s\\]\S*)(?:[ \t]+AS[ \t]+(?P<stage>\S+))?",
    re.MULTILINE | re.IGNORECASE,
)

# Les sources `from=` d'un `COPY` ou d'un `RUN`, lues dans les **options** de l'instruction
# seulement — un `RUN uvx --from=…` passe l'option à la commande, pas à Docker. Lignes de
# continuation jointes d'abord : Docker les lit comme une seule instruction.
CONTINUATION = re.compile(r"\\[ \t]*\r?\n")
LEADING_OPTIONS = re.compile(r"^[ \t]*(?:COPY|RUN)((?:[ \t]+--\S+)+)", re.MULTILINE | re.IGNORECASE)
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
    if DOCKERFILE_NAME.search(path.name) and path.is_file()
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
        assert len(uses_values(yaml.safe_load(text))) == len(matches), (
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


def dockerfile_stages(dockerfile: Path) -> tuple[list[str], set[str]]:
    """Les images citées par les `FROM` d'un Dockerfile, et les noms d'étage qu'il déclare.

    Un `FROM <étage>` qui reprend un étage déjà déclaré n'est pas une image, ni `scratch`, image
    vide réservée par Docker : ils sont écartés.

    Returns:
        Les images, dans l'ordre du fichier, et l'ensemble des noms d'étage (`AS <nom>`).
    """
    lines = list(READABLE_FROM.finditer(dockerfile.read_text(encoding="utf-8")))
    stages = {line["stage"].lower() for line in lines if line["stage"]}
    images = [line["image"] for line in lines if line["image"].lower() not in {*stages, "scratch"}]
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
    doit lui être lisible — colonne 0, image sur la même ligne —, sans quoi l'épingle ne bougerait
    jamais.
    """
    text = dockerfile.read_text(encoding="utf-8")
    readable = READABLE_FROM.findall(text)
    assert len(FROM_INSTRUCTION.findall(text)) == len(readable), (
        "un `FROM` que Dependabot ne lit pas — indenté, ou image sur la ligne suivante"
    )
    images, _ = dockerfile_stages(dockerfile)

    assert images, "aucune image de base trouvée — le motif a-t-il cessé de mordre ?"
    unpinned = [image for image in images if not PINNED_IMAGE.match(image)]
    assert not unpinned, (
        f"{len(images)} images repassées, sans version x.y.z devant l'empreinte : {unpinned}"
    )


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=dockerfile_id)
def test_toute_image_copiee_passe_par_un_etage_nomme(dockerfile: Path) -> None:
    """Dependabot ne lit que les lignes `FROM` (`docker/file_parser.rb`, dependabot-core).

    Une image citée seulement par `COPY --from=<image>` ou `RUN --mount=from=<image>` ne serait
    jamais mise à jour : elle est déclarée dans un étage à elle, dont le nom est repris ensuite.
    """
    _, stages = dockerfile_stages(dockerfile)
    instructions = CONTINUATION.sub(" ", dockerfile.read_text(encoding="utf-8"))
    sources = [
        source
        for options in LEADING_OPTIONS.findall(instructions)
        for source in FROM_SOURCE.findall(options)
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
