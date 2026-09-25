"""Tests de la chaîne d'approvisionnement : actions et images épinglées, Dependabot.

Comme `test_infra.py`, ces tests lisent des fichiers de configuration sans rien exécuter. Ils
gardent ce qui ne se verrait qu'après le merge, et en silence : une action ou une image qui suit
une étiquette déplaçable, un écosystème que Dependabot ne surveille plus. La porte d'audit Python
a ses propres tests, dans `test_pip_audit_gate.py`.
"""

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

# `test_supply_chain.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEPENDABOT = REPOSITORY_ROOT / ".github" / "dependabot.yml"

# `uses: owner/action@<empreinte> # vX.Y.Z`. Le commentaire porte l'étiquette **la plus précise**
# du commit : Dependabot réécrit un commentaire qui se termine par une étiquette pointant encore
# sur le commit épinglé (`version_commenter.rb`, dependabot-core), et une étiquette majeure
# (`v7`) cesse d'y pointer dès qu'une version sort — précisément quand la mise à jour arrive.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<reference>\S+)(?P<comment>.*)$", re.MULTILINE)
PINNED_REFERENCE = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^ # v\d+\.\d+\.\d+$")

# Les fichiers où GitHub lit des `uses:` : workflows, et actions composites du dépôt.
WORKFLOW_GLOBS = [
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/**/action.yml",
    ".github/actions/**/action.yaml",
]

# Toute clé `uses` hors commentaire, quelle que soit sa forme. Dénombrement des relectures de #5 :
# 12 formes recensées. `USES` en lit 3 et en refuse 4 par excès (guillemets autour de la valeur,
# action locale, `docker://`, double espace avant `#`) ; 3 lui échappaient — un fichier `.yaml`,
# un mapping en flux `{ uses: … }`, une clé entre guillemets —, fermées par `WORKFLOW_GLOBS` et
# par ce décompte ; une action composite sortait du glob ; un commentaire qui cite `uses:` faisait
# échouer le décompte à tort, d'où l'exclusion des commentaires.
USES_KEY = re.compile(r"""^[^#\n]*\buses["']?\s*:""", re.MULTILINE)

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

# Tous les Dockerfile suivis par git, sous le motif de nom que Dependabot reconnaît
# (`/dockerfile|containerfile/i`, `docker/file_fetcher.rb`, dependabot-core) : un Dockerfile
# ajouté n'importe où est tenu aux mêmes règles sans retoucher les tests.
DOCKERFILE_NAME = re.compile(r"dockerfile|containerfile", re.IGNORECASE)
DOCKERFILES = sorted(
    REPOSITORY_ROOT / name
    for name in subprocess.run(
        ["git", "ls-files"], cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    if DOCKERFILE_NAME.search(Path(name).name)
)

# Lecture d'un Dockerfile, les lignes de continuation jointes d'abord : une instruction par ligne.
# Les instructions et les noms d'étage sont insensibles à la casse, d'où `re.IGNORECASE`.
# Dénombrement des relectures de #5, 19 formes : `FROM` avec ou sans `AS`, avec `--platform`, en
# minuscules, sur deux lignes, indenté (lu, puis refusé : Dependabot n'en lit que la colonne 0),
# `scratch`, registre avec port ; image citée par `COPY --from` — simple, avec `--chown`/`--link`,
# sur deux lignes, indenté, par index d'étage — ou par `RUN --mount=from=`, `type=bind,from=`.
CONTINUATION = re.compile(r"\\\r?\n")
FROM_LINE = re.compile(
    r"^(?P<indent>[ \t]*)FROM\s+(?:--\S+\s+)*(?P<image>\S+)(?:\s+AS\s+(?P<stage>\S+))?",
    re.MULTILINE | re.IGNORECASE,
)
COPY_OR_RUN = re.compile(r"^[ \t]*(?:COPY|RUN)\b.*$", re.MULTILINE | re.IGNORECASE)
FROM_SOURCE = re.compile(r"(?:--|[,=])from=([^\s,]+)", re.IGNORECASE)
# `image:<version x.y.z>[-variante]@sha256:<empreinte>` — même règle que pour les actions : la
# version la plus précise. Dependabot lit une épingle étiquette + empreinte comme « suivre les
# versions » (dependabot-core, PR #15103) : c'est une nouvelle version de correctif qui lui fait
# ouvrir une PR, et une étiquette sans correctif (`3.12`) n'en change jamais.
PINNED_IMAGE = re.compile(r"^[\w./:-]+:v?\d+\.\d+\.\d+[\w.-]*@sha256:[0-9a-f]{64}$")


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
        assert len(USES_KEY.findall(text)) == len(matches), (
            f"{workflow.name} : une clé `uses` échappe au motif — forme non lue, donc non vérifiée"
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


def dockerfile_instructions(dockerfile: Path) -> str:
    """Le Dockerfile, ses lignes de continuation jointes : une instruction par ligne."""
    return CONTINUATION.sub(" ", dockerfile.read_text(encoding="utf-8"))


def dockerfile_stages(dockerfile: Path) -> tuple[list[re.Match[str]], set[str]]:
    """Les `FROM` d'un Dockerfile qui citent une image, et les noms d'étage qu'il déclare.

    Un `FROM <étage>` qui reprend un étage déjà déclaré n'est pas une image, ni `scratch`, image
    vide réservée par Docker : ils sont écartés.

    Returns:
        Les `FROM` retenus, dans l'ordre du fichier, et l'ensemble des noms d'étage (`AS <nom>`).
    """
    lines = list(FROM_LINE.finditer(dockerfile_instructions(dockerfile)))
    stages = {line["stage"].lower() for line in lines if line["stage"]}
    images = [line for line in lines if line["image"].lower() not in {*stages, "scratch"}]
    return images, stages


def dockerfile_id(path: Path) -> str:
    """Identifiant de paramètre lisible : le chemin du Dockerfile depuis la racine du dépôt."""
    return path.relative_to(REPOSITORY_ROOT).as_posix()


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=dockerfile_id)
def test_chaque_image_de_base_est_epinglee_par_empreinte(dockerfile: Path) -> None:
    """Une étiquette d'image peut changer de contenu ; une empreinte non.

    Le guide « Building best practices » de Docker le recommande. L'étiquette reste devant
    l'empreinte, à sa version la plus précise : c'est elle qui porte les mises à jour, Dependabot
    proposant la version de correctif suivante, étiquette et empreinte ensemble. Un `FROM` indenté
    est refusé : Dependabot ne lit que ceux de la colonne 0 (`docker/file_parser.rb`).
    """
    images, _ = dockerfile_stages(dockerfile)

    assert images, "aucune image de base trouvée — le motif a-t-il cessé de mordre ?"
    unread = [line["image"] for line in images if line["indent"]]
    assert not unread, f"`FROM` indentés, que Dependabot ne lit pas : {unread}"
    unpinned = [line["image"] for line in images if not PINNED_IMAGE.match(line["image"])]
    assert not unpinned, f"{len(images)} images repassées, non épinglées : {unpinned}"


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=dockerfile_id)
def test_toute_image_copiee_passe_par_un_etage_nomme(dockerfile: Path) -> None:
    """Dependabot ne lit que les lignes `FROM` (`docker/file_parser.rb`, dependabot-core).

    Une image citée seulement par `COPY --from=<image>` ou `RUN --mount=from=<image>` ne serait
    jamais mise à jour : elle est déclarée dans un étage à elle, dont le nom est repris ensuite.
    """
    _, stages = dockerfile_stages(dockerfile)
    sources = [
        source
        for instruction in COPY_OR_RUN.finditer(dockerfile_instructions(dockerfile))
        for source in FROM_SOURCE.findall(instruction.group())
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
