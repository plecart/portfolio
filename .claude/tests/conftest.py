"""Les aides des tests de la pipeline. Chaque test les importe (`from conftest import …`) : aucune
fixture, et la suite tourne aussi sous `--noconftest`.

Charge un script d'un skill de `.claude/` pour le tester, ou le lance comme la session le lit. Les
scripts des skills vivent sous `.claude/skills/<skill>/scripts/` : un dossier caché, donc hors de
tout paquet importable. `ruff` les lit ; `pyright` aussi, mais par un projet à part
(`.claude/pyrightconfig.json`, lancé par `make typecheck`), le projet racine excluant les dossiers
cachés quoi que dise son `include` (mesuré le 2026-10-09). Ni l'un ni l'autre ne les exécute : la
seule porte qui éprouve leur *comportement* est cette suite, et c'est pourquoi elle les charge par
chemin.

Les aides que le back partage avec cette suite gardent leur seule définition dans des modules de
`apps/api/tests/` sans Django — `test_supply_chain.py`, `system_commands.py` — ; ce module les
réexporte. Le `conftest.py` du back porte le même nom de module, et pytest retire `conftest` de
`sys.modules` avant de charger chacun (`_importconftest`, pytest 9.2.0) : une session qui
collecte les deux suites rend aux imports d'ici le dernier chargé — `ImportError` quand
`.claude/tests` précède `apps` sur la ligne de commande, mesuré le 2026-11-04. Les deux suites se
lancent donc séparément, `make test` puis `make test-pipeline`.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from system_commands import bash_de_ce_systeme, make_dry_run
from test_supply_chain import prose_citations, texte_normalise, tracked_files

__all__ = [
    "REPOSITORY_ROOT",
    "bash_de_ce_systeme",
    "load_script",
    "make_dry_run",
    "pipe_environment",
    "prose_citations",
    "run_in_pipe",
    "script_path",
    "texte_normalise",
    "tracked_files",
]

# `conftest.py` → `tests` → `.claude` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# L'encodage qu'un tube reçoit d'un Python sans réglage sur ce poste, dont la page de code est
# cp1252 (`pipeline.config.md`, « Qualité »).
CONSOLE_ENCODING = "cp1252"


def script_path(skill: str, name: str) -> Path:
    """Le chemin de `.claude/skills/<skill>/scripts/<name>.py`.

    Raises:
        AssertionError: le script n'existe pas — un test qui le chargerait ou le lancerait
            passerait pour une raison étrangère à lui.
    """
    path = REPOSITORY_ROOT / ".claude" / "skills" / skill / "scripts" / f"{name}.py"
    assert path.is_file(), f"script introuvable : {path}"
    return path


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
    path = script_path(skill, name)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"{path} n'est pas chargeable comme module"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pipe_environment() -> dict[str, str]:
    """L'environnement de ce processus, l'encodage des flux standard de l'enfant imposé en
    cp1252 — celui que reçoit un tube sur ce poste.

    Hérité, `PYTHONIOENCODING=utf-8` — que le rôle `releveur` pose devant toute commande Python —
    met l'enfant en UTF-8 sans le correctif qu'un test de tube éprouve, et `PYTHONUTF8=1` de
    même : la mutation qui retire ce correctif y restait VERTE (dénombrement dans
    `test_l_enfant_d_un_tube_ecrit_en_cp1252_quel_que_soit_l_environnement_herite`). Imposée,
    `PYTHONIOENCODING` passe avant le mode UTF-8 et la locale, tube compris sous Windows
    (CPython, `Doc/using/cmdline.rst` et `Doc/library/os.rst`, « UTF-8 Mode », lus le
    2026-10-21) : ôter `PYTHONUTF8` n'y changerait rien, et ce test le mesure.
    """
    return {**os.environ, "PYTHONIOENCODING": CONSOLE_ENCODING}


def run_in_pipe(skill: str, name: str, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Lance `python <script> <args>` comme la session le lit : par un tube, sorties capturées en
    octets, flux standard de l'enfant en cp1252 (`pipe_environment`) quel que soit le shell. Un
    script qui ne reconfigure pas ses flux en UTF-8 y écrit donc illisible, sur ce poste comme
    sur un runner Linux — par la même documentation, non mesuré sur un runner. Pas de `-I` : il
    implique `-E`, qui ignore la variable qui fait le cas."""
    return subprocess.run(
        [sys.executable, str(script_path(skill, name)), *args],
        capture_output=True,
        env=pipe_environment(),
        check=False,
    )
