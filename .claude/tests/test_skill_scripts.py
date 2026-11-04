"""Tests des portes des scripts de skills : l'encodage qu'un enfant reçoit en tube, et leur
couverture, avec celle des tests de la pipeline, par `make typecheck`."""

import json
import shlex
import subprocess
import sys

import pytest
from conftest import REPOSITORY_ROOT, make_dry_run, pipe_environment

# Le projet pyright des scripts des skills et des tests de la pipeline, que le projet racine ne
# voit pas (`Makefile`, cible `typecheck`).
PROJECT = REPOSITORY_ROOT / ".claude"

# Ce que le parent peut hériter du shell pour mettre l'enfant en UTF-8 sans son correctif ; une
# variable absente d'un cas est ôtée du parent.
VARIABLES = ("PYTHONIOENCODING", "PYTHONUTF8")
HERITAGES = {
    "aucun": {},
    "pythonioencoding-utf-8": {"PYTHONIOENCODING": "utf-8"},
    "pythonutf8": {"PYTHONUTF8": "1"},
    "les-deux": {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
}


@pytest.mark.parametrize("heritage", HERITAGES.values(), ids=HERITAGES.keys())
def test_l_enfant_d_un_tube_ecrit_en_cp1252_quel_que_soit_l_environnement_herite(
    heritage: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Dénombrement de la classe « un test de tube neutralisé par l'environnement hérité »,
    pris avant le correctif** (lot 4b de #134, cleanup holistique, 2026-10-21, sur `37e0846`).

    Population : chaque test qui lance un script de skill en sous-processus et assère sa sortie
    UTF-8 dans un tube — les lignes `sys.executable, str(` d'`apps/api/tests/`, 9, dont 2 hors de
    la classe : `test_ci_declencheurs.py` et `test_pip_audit_gate.py` lancent des scripts du
    dépôt, sans assertion d'encodage. Restent **7 tests, 12 cas** :
    `test_la_sortie_du_script_lance_en_tube_est_en_utf_8` d'`attente-ci`, `erreurs-ci`,
    `ecriture-relue`, `croisement-fichiers` et `sonde-outillage` (2 cas chacun), celui de
    `merge-lot` (1), et `test_la_sortie_standard_est_en_utf_8_quelle_que_soit_la_console` de
    `fin-transcript` (1). Mesuré par `mutation.py`, `PYTHONIOENCODING=utf-8` posé au parent :
    **11 cas sur 12 fuyaient** — la mutation qui retire `reconfigure` y restait VERTE ; le cas de
    `fin-transcript`, qui imposait déjà `PYTHONIOENCODING=cp1252`, rougissait. `PYTHONUTF8=1` seul
    fait de même : les 2 cas d'`attente-ci` VERTS. Les 7 passent désormais par `run_in_pipe`, qui
    impose cp1252 à tous : les 13 mutations — les 12 cas, et celle qui retire l'imposition —
    ROUGES sous chacun des deux héritages comme sans.

    Les tests de console cp1252 en processus de `test_mutation.py` et `test_bilan_session.py`
    remplacent `sys.stdout` : l'environnement n'y entre pas.
    """
    for nom in VARIABLES:
        if nom in heritage:
            monkeypatch.setenv(nom, heritage[nom])
        else:
            monkeypatch.delenv(nom, raising=False)
    sonde = "import sys; print(sys.stdout.encoding, sys.stderr.encoding)"

    done = subprocess.run(
        [sys.executable, "-c", sonde], capture_output=True, env=pipe_environment(), check=False
    )

    assert done.stdout.decode("ascii").split() == ["cp1252", "cp1252"]


def test_make_typecheck_lance_pyright_sur_le_projet_de_la_pipeline() -> None:
    """Retirer cette invocation laissait toute la suite verte : c'est le défaut d'origine de #145."""
    commandes = [shlex.split(ligne) for ligne in make_dry_run("typecheck").splitlines()]

    assert any(commande[-3:] == ["pyright", "-p", ".claude"] for commande in commandes)


def test_make_test_et_make_test_pipeline_lancent_chacun_leur_suite() -> None:
    """`make test` ne lit que `apps` ; `make test-pipeline` lit `.claude/tests` sans le greffon
    qui charge Django (ADR 0025) — retirer le drapeau laissait toute la suite verte."""
    (test,) = map(shlex.split, make_dry_run("test").splitlines())
    (pipeline,) = map(shlex.split, make_dry_run("test-pipeline").splitlines())

    assert test[-2:] == ["pytest", "apps"]
    assert pipeline[-4:] == ["pytest", ".claude/tests", "-p", "no:process_environment"]


def test_le_projet_pyright_de_la_pipeline_est_en_mode_strict() -> None:
    """Sans la clé, pyright analyserait les mêmes fichiers en mode basique, gardes vertes."""
    config = json.loads((PROJECT / "pyrightconfig.json").read_text(encoding="utf-8"))

    assert config["typeCheckingMode"] == "strict"


def test_le_projet_pyright_de_la_pipeline_analyse_ses_scripts_et_ses_tests() -> None:
    """Un projet mal réglé analyse moins qu'il ne prétend, et rend « 0 errors » quand même :
    `"include": ["*/scripts"]` y a été mesuré à 0 fichier analysé (#145), `skills/*/scripts` de
    même depuis `.claude` (2026-11-04). Le compte porte les scripts et les tests de la pipeline."""
    done = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "-p", str(PROJECT)],
        capture_output=True,
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    scripts = list(PROJECT.glob("skills/*/scripts/*.py"))
    tests = list(PROJECT.glob("tests/*.py"))
    assert scripts and tests, f"aucun script ou aucun test sous {PROJECT}"
    analysed = json.loads(done.stdout)["summary"]["filesAnalyzed"]
    assert analysed == len(scripts) + len(tests), done.stderr
