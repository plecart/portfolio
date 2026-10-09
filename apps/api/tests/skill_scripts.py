"""Charge un script d'un skill de `.claude/` pour le tester.

Les scripts des skills vivent sous `.claude/skills/<skill>/scripts/` : un dossier caché, donc
hors de tout paquet importable — et hors de `pyright`, qui exclut les dossiers cachés sans que
sa configuration puisse l'en empêcher (mesuré le 2026-10-09 : `filesAnalyzed` inchangé que
`.claude` figure ou non dans `include`, même en nommant le fichier). `ruff` les lit, lui. La
seule porte qui éprouve leur *comportement* est donc cette suite, et c'est pourquoi elle les
charge par chemin.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

# `skill_scripts.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def load_script(skill: str, name: str) -> ModuleType:
    """Importe `.claude/skills/<skill>/scripts/<name>.py` sous son nom de fichier.

    Args:
        skill: le dossier du skill, par exemple `cycle-pr`.
        name: le nom du script sans son extension, par exemple `mutation`.

    Returns:
        Le module exécuté, prêt à l'emploi.

    Raises:
        AssertionError: le script n'existe pas, ou Python refuse d'en faire un module — les
            deux états où un test de ce script passerait pour une raison étrangère à lui.
    """
    path = REPOSITORY_ROOT / ".claude" / "skills" / skill / "scripts" / f"{name}.py"
    assert path.is_file(), f"script introuvable : {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"{path} n'est pas chargeable comme module"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
