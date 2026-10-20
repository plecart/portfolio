"""Sessions pytest imbriquées : éprouver la suite de l'extérieur, comme la lance un développeur.

Certaines garanties ne se voient que sur une session entière — un test sauté plutôt qu'échoué,
une variable du shell qui l'emporte, un conteneur démarré pour tous les tests. Elles se vérifient
en relançant pytest dans un processus à part, sur des tests nommés un à un.
"""

import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import pytest
from config.env import REPOSITORY_ROOT

# Posée dans chaque session imbriquée : celle qui la trouve déjà refuse d'en lancer une autre. Une
# sélection qui se contiendrait elle-même se relancerait sans fin.
NESTED_SESSION = "PORTFOLIO_NESTED_SESSION"

# Les balises JUnit d'une issue autre que la réussite, et le mot que pytest emploie pour chacune.
NOT_PASSED = {"failure": "failed", "error": "error", "skipped": "skipped"}


@dataclass(frozen=True)
class NestedSession:
    """Ce qu'une session imbriquée a produit.

    Attributs :
        exit_code: le code de sortie de pytest.
        outcomes: l'issue de chaque test lancé — `passed`, `failed`, `error` ou `skipped` —, par
            identifiant de test, tel que l'appelant l'a passé.
        report: la sortie de pytest, où se lisent les messages.
    """

    exit_code: int
    outcomes: dict[str, str]
    report: str


def run_nested_session(tests: Sequence[str], workdir: Path, **environment: str) -> NestedSession:
    """Lance pytest sur `tests` dans un processus à part, depuis la racine du dépôt.

    L'issue de chaque test est lue dans le rapport JUnit, jamais dans la ligne de bilan : un
    avertissement ou un test voisin ajouté la changerait sans rien changer à ce qu'on mesure. Les
    options pytest du shell (`PYTEST_ADDOPTS`) sont écartées : un `-x` hérité arrêterait la
    session au premier échec.

    La sortie s'échange en UTF-8 des deux côtés, posé à l'enfant et lu par le parent : décodée
    selon la page de code du poste, elle dépendait de l'environnement hérité. Mesuré le
    2026-10-20 : `PYTHONIOENCODING=utf-8` dans le shell — la forme que le rôle `releveur` pose
    devant toute commande Python — rendait `test_sans_reglages_chaque_test_echoue` rouge à tort,
    son message accentué relu en cp1252 ; seul rouge de `make test` sous cette variable. La
    valeur est imposée, même si l'appelant la passe dans `environment`.

    Args:
        tests: les identifiants des tests à lancer, relatifs à la racine, un par test.
        workdir: où écrire le rapport JUnit — le `tmp_path` du test appelant.
        environment: les variables à poser par-dessus l'environnement de ce processus.

    Returns:
        Le code de sortie, l'issue de chaque test et la sortie de pytest.

    Raises:
        pytest.fail.Exception: appelée depuis une session imbriquée.
    """
    if NESTED_SESSION in os.environ:
        pytest.fail("une session imbriquée n'en lance pas d'autre", pytrace=False)
    junit = workdir / "session.xml"
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", f"--junit-xml={junit}", *tests],
        cwd=REPOSITORY_ROOT,
        env={
            **_inherited_environment(),
            **environment,
            "PYTHONIOENCODING": "utf-8",
            NESTED_SESSION: "1",
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return NestedSession(process.returncode, _outcomes(junit), process.stdout)


def _inherited_environment() -> dict[str, str]:
    """L'environnement de ce processus, sans les options pytest du shell."""
    return {name: value for name, value in os.environ.items() if name != "PYTEST_ADDOPTS"}


def _outcomes(junit: Path) -> dict[str, str]:
    """L'issue de chaque cas du rapport JUnit, par identifiant — rien si pytest n'a rien écrit."""
    if not junit.exists():
        return {}
    return {_test_id(case): _outcome(case) for case in ElementTree.parse(junit).iter("testcase")}


def _test_id(case: ElementTree.Element) -> str:
    """L'identifiant pytest d'un cas : la classe JUnit `apps.api.tests.test_x` nomme le module
    `apps/api/tests/test_x.py`."""
    module = case.get("classname", "").replace(".", "/")
    return f"{module}.py::{case.get('name', '')}"


def _outcome(case: ElementTree.Element) -> str:
    """`passed`, sauf si le cas porte une balise d'échec, d'erreur ou de saut."""
    return next((NOT_PASSED[child.tag] for child in case if child.tag in NOT_PASSED), "passed")
