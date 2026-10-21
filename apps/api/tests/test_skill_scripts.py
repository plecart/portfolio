"""Tests du lancement en tube des scripts de skills : l'encodage que l'enfant reçoit."""

import subprocess
import sys

import pytest
from skill_scripts import pipe_environment

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
