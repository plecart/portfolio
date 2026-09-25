"""Tests de la chaîne d'approvisionnement : actions GitHub épinglées, Dependabot, audit Python.

Comme `test_infra.py`, ces tests lisent des fichiers de configuration sans rien exécuter sur
GitHub. Ils gardent ce qui ne se verrait qu'après le merge, et en silence : une action qui suit
une étiquette déplaçable, un écosystème que Dependabot ne surveille plus.
"""

import re
from pathlib import Path

# `test_supply_chain.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"

# `uses: owner/action@<empreinte> # vX.Y.Z`. Le commentaire n'est pas décoratif : Dependabot ne le
# réécrit que s'il se termine par l'étiquette de version **la plus précise** du commit épinglé
# (`version_commenter.rb`, dependabot-core). Un `# v7` resterait figé pendant que l'empreinte
# avance, et le commentaire finirait par mentir.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<reference>\S+)(?P<comment>.*)$", re.MULTILINE)
PINNED_REFERENCE = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^ # v\d+\.\d+\.\d+$")


def test_chaque_action_est_epinglee_par_empreinte_de_commit() -> None:
    """Une étiquette peut être déplacée par son propriétaire ou par un attaquant ; une empreinte non.

    L'incident `tj-actions/changed-files` (2025) est passé par là : des étiquettes de version
    redirigées vers un commit malveillant, exécuté sans signal par tous les dépôts qui les
    suivaient (brief de #5).
    """
    found = [
        (workflow.name, match)
        for workflow in sorted(WORKFLOWS_DIRECTORY.glob("*.yml"))
        for match in USES.finditer(workflow.read_text(encoding="utf-8"))
    ]

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
