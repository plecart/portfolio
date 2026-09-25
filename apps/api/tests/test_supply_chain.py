"""Tests de la chaîne d'approvisionnement : actions et images épinglées, Dependabot.

Comme `test_infra.py`, ces tests lisent des fichiers de configuration sans rien exécuter. Ils
gardent ce qui ne se verrait qu'après le merge, et en silence : une action ou une image qui suit
une étiquette déplaçable, un écosystème que Dependabot ne surveille plus. La porte d'audit Python
a ses propres tests, dans `test_pip_audit_gate.py`.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

# `test_supply_chain.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
DEPENDABOT = REPOSITORY_ROOT / ".github" / "dependabot.yml"

# `uses: owner/action@<empreinte> # vX.Y.Z`. Le commentaire porte l'étiquette **la plus précise**
# du commit : Dependabot réécrit un commentaire qui se termine par une étiquette pointant encore
# sur le commit épinglé (`version_commenter.rb`, dependabot-core), et une étiquette majeure
# (`v7`) cesse d'y pointer dès qu'une version sort — précisément quand la mise à jour arrive.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<reference>\S+)(?P<comment>.*)$", re.MULTILINE)
PINNED_REFERENCE = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^ # v\d+\.\d+\.\d+$")

# Toute clé `uses`, quelle que soit sa forme. Dénombrement de la relecture de #5 : 10 formes de
# `uses:` recensées ; `USES` en lit 3 et en refuse 4 par excès (guillemets autour de la valeur,
# action locale, `docker://`, double espace avant `#`) ; les 3 autres lui échappaient — un fichier
# `.yaml`, un mapping en flux `{ uses: … }`, une clé entre guillemets. Le glob couvre la première,
# ce décompte les deux suivantes : une clé que `USES` ne lit pas fait échouer le test.
USES_KEY = re.compile(r"""\buses["']?\s*:""")

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

PYTHON_UPGRADES_IGNORED = {
    "dependency-name": "python",
    "update-types": ["version-update:semver-major", "version-update:semver-minor"],
}

# Tous les Dockerfile du dépôt : un Dockerfile ajouté est tenu aux mêmes règles sans retoucher
# les tests. Les noms d'étage de Docker sont insensibles à la casse, d'où `re.IGNORECASE`.
DOCKERFILES = sorted(REPOSITORY_ROOT.glob("infra/**/Dockerfile"))
FROM_LINE = re.compile(
    r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", re.MULTILINE | re.IGNORECASE
)
COPY_FROM = re.compile(r"^COPY\s+.*?--from=(\S+)", re.MULTILINE | re.IGNORECASE)
DIGEST_PINNED_IMAGE = re.compile(r"^[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}$")


def test_chaque_action_est_epinglee_par_empreinte_de_commit() -> None:
    """Une étiquette peut être déplacée par son propriétaire ou par un attaquant ; une empreinte non.

    L'incident `tj-actions/changed-files` (2025) est passé par là : des étiquettes de version
    redirigées vers un commit malveillant, exécuté sans signal par tous les dépôts qui les
    suivaient (brief de #5).
    """
    workflows = sorted([*WORKFLOWS_DIRECTORY.glob("*.yml"), *WORKFLOWS_DIRECTORY.glob("*.yaml")])
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


def test_dependabot_ne_propose_jamais_de_nouvelle_version_de_python() -> None:
    """La version de Python est une décision du projet, pas une mise à jour.

    `.python-version` l'épingle et l'image la suit sous test (`test_infra.py`) : une PR qui
    proposerait `3.13-slim-bookworm` échouerait chaque semaine, par construction. Dependabot ne
    propose donc, pour cette image, que la nouvelle empreinte de la même étiquette.
    """
    ignored = dependabot_entry("docker").get("ignore", [])

    assert PYTHON_UPGRADES_IGNORED in ignored


def dockerfile_stages(dockerfile: Path) -> tuple[list[str], set[str]]:
    """Les images citées par les `FROM` d'un Dockerfile, et les noms d'étage qu'il déclare.

    Un `FROM <étage>` qui reprend un étage déjà déclaré n'est pas une image : il est écarté.

    Returns:
        Les images, dans l'ordre du fichier, et l'ensemble des noms d'étage (`AS <nom>`).
    """
    lines = FROM_LINE.findall(dockerfile.read_text(encoding="utf-8"))
    stages = {stage.lower() for _, stage in lines if stage}
    return [image for image, _ in lines if image.lower() not in stages], stages


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda path: path.parent.name)
def test_chaque_image_de_base_est_epinglee_par_empreinte(dockerfile: Path) -> None:
    """Une étiquette d'image peut changer de contenu ; une empreinte non.

    Le guide « Building best practices » de Docker le recommande, et c'est ce qui donne prise à
    Dependabot : il propose la nouvelle empreinte quand l'étiquette bouge. L'étiquette est gardée
    devant l'empreinte, pour la lecture et pour que Dependabot sache quelle ligne suivre.
    """
    images, _ = dockerfile_stages(dockerfile)

    assert images, "aucune image de base trouvée — le motif a-t-il cessé de mordre ?"
    unpinned = [image for image in images if not DIGEST_PINNED_IMAGE.match(image)]
    assert not unpinned, f"{len(images)} images repassées, non épinglées : {unpinned}"


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda path: path.parent.name)
def test_toute_image_copiee_passe_par_un_etage_nomme(dockerfile: Path) -> None:
    """Dependabot ne lit que les lignes `FROM` (`docker/file_parser.rb`, dependabot-core).

    Une image citée seulement dans un `COPY --from=<image>` ne serait jamais mise à jour : elle
    est déclarée dans un étage à elle, et `COPY --from` en reprend le nom.
    """
    _, stages = dockerfile_stages(dockerfile)
    sources = COPY_FROM.findall(dockerfile.read_text(encoding="utf-8"))

    outside = [source for source in sources if source.lower() not in stages]
    assert not outside, f"{len(sources)} `COPY --from` repassés, hors d'un étage : {outside}"
