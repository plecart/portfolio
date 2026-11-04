"""Les commandes du système que lancent les tests du back et ceux de la pipeline
(`.claude/tests`) : `make`, sans hériter du shell qui lance les tests, et le `bash` POSIX de ce
système.

Sans Django : le `conftest.py` de `.claude/tests` réexporte ces aides, et `make image-test` charge
ce module par `test_infra.py` (`IMAGE_TESTS` de `infra/ci/changed_jobs.py`).
"""

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from functools import cache
from pathlib import Path

import pytest

# `system_commands.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MAKEFILE = REPOSITORY_ROOT / "Makefile"

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


@cache
def posix_bash() -> str | None:
    """Le `bash` que `bash_de_ce_systeme` rend, ou `None` : sondé une fois par processus, saut
    compris — sous Windows, chaque sonde lance un `bash`, celui de WSL au besoin."""
    bash = shutil.which("bash")
    if bash is not None and sys.platform == "win32":
        uname = subprocess.run(
            [bash, "-c", "uname -s"], capture_output=True, text=True, check=False
        )
        if not uname.stdout.startswith(("MINGW", "MSYS")):
            return None
    return bash


def bash_de_ce_systeme() -> str:
    """Le `bash` du `PATH`, par `shutil.which` (doc `subprocess`, avertissement de `Popen`), s'il lit
    les chemins de ce système ; sinon, le test qui l'appelle est sauté.

    Sous Windows, seul un `bash` MSYS est retenu, dont `uname -s` commence par `MINGW` ou
    `MSYS` (les deux mesurés sous Git Bash, selon `MSYSTEM`). Celui de WSL — le lanceur de
    `System32` comme l'alias de `WindowsApps`, tous deux sur le poste — rend `Linux`, et la commande
    y échoue : mesuré le 2026-10-26, 37 cas sur 37 sur « unexpected EOF while looking for
    matching » avec un `PATH` de shell Windows où `shutil.which` le trouve d'abord. Un `"bash"` nu,
    résolu par `CreateProcess`, le trouve même sous Git Bash. Ailleurs — en CI Linux, le test
    tourne — le `bash` du `PATH` sert tel quel.
    """
    bash = posix_bash()
    if bash is None:
        pytest.skip("pas de `bash` POSIX (absent, ou celui de WSL) : le test ne se joue pas ici")
    return bash
