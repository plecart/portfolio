"""Tests de la chaîne d'approvisionnement : actions GitHub épinglées, Dependabot, audit Python.

Comme `test_infra.py`, ces tests lisent des fichiers de configuration sans rien exécuter sur
GitHub. Ils gardent ce qui ne se verrait qu'après le merge, et en silence : une action qui suit
une étiquette déplaçable, un écosystème que Dependabot ne surveille plus.
"""

import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

# `test_supply_chain.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
AUDIT_GATE = REPOSITORY_ROOT / "infra" / "ci" / "pip_audit_gate.py"

# Un identifiant d'avis quelconque : la porte ne le cherche nulle part, elle le transmet.
ADVISORY = "GHSA-aaaa-bbbb-cccc"

# Transmis à `pip-audit` à la place d'un audit réel : il répond sans réseau et sans rien auditer.
# C'est ce qui permet de savoir, sans dépendre de PyPI, si la porte a lancé `pip-audit` ou non.
PIP_AUDIT_VERSION = "--version"

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


def run_audit_gate(
    tmp_path: Path, exceptions: str, *forwarded: str
) -> subprocess.CompletedProcess[str]:
    """Lance la porte d'audit sur un fichier d'exceptions écrit pour le test.

    Args:
        tmp_path: dossier temporaire du test, où le fichier est écrit.
        exceptions: contenu TOML du fichier d'exceptions.
        forwarded: arguments que la porte doit transmettre à `pip-audit`.

    Returns:
        Le processus terminé, sorties capturées.
    """
    path = tmp_path / "exceptions.toml"
    path.write_text(exceptions, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(AUDIT_GATE), "--exceptions", str(path), *forwarded],
        capture_output=True,
        text=True,
        check=False,
    )


def utc_today() -> date:
    """La date du jour telle que la porte la calcule : en UTC, celle de la CI."""
    return datetime.now(UTC).date()


def exception_entry(expires: date) -> str:
    """Une exception bien formée, qui expire à la date donnée."""
    return (
        "[[exception]]\n"
        f'id = "{ADVISORY}"\n'
        'reason = "aucun chemin d\'appel vers le code vulnérable"\n'
        f"expires = {expires.isoformat()}\n"
    )


def test_une_exception_expiree_fait_echouer_l_audit_sans_le_lancer(tmp_path: Path) -> None:
    """Passée sa date, une exception rebloque : c'est ce qui l'empêche de devenir permanente.

    L'échec précède l'audit : `pip-audit` ne tourne pas du tout, pour qu'une exception expirée
    ne puisse jamais passer inaperçue derrière un audit qui, par ailleurs, serait vert.
    """
    yesterday = utc_today() - timedelta(days=1)

    result = run_audit_gate(tmp_path, exception_entry(yesterday), PIP_AUDIT_VERSION)

    assert result.returncode == 1
    assert ADVISORY in result.stderr
    assert "pip-audit" not in result.stdout, "`pip-audit` a tourné malgré l'exception expirée"


def test_une_exception_valable_est_transmise_a_pip_audit(tmp_path: Path) -> None:
    """Jusqu'à sa date incluse, l'avis est ignoré par `pip-audit` et l'audit tourne.

    La porte affiche la commande qu'elle lance : c'est ce que le journal de CI montre, et ce qui
    dit au lecteur quelles exceptions étaient en vigueur ce jour-là.
    """
    result = run_audit_gate(tmp_path, exception_entry(utc_today()), PIP_AUDIT_VERSION)

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("pip-audit"), "`pip-audit` n'a pas été lancé"
    assert f"--ignore-vuln {ADVISORY}" in result.stderr


def test_la_porte_rend_le_code_de_sortie_de_pip_audit(tmp_path: Path) -> None:
    """Une porte qui avalerait le code de `pip-audit` ne bloquerait jamais rien.

    Une option inconnue fait sortir `pip-audit` en 2 sans réseau ; une vulnérabilité trouvée le
    fait sortir en 1 par le même chemin. C'est ce chemin qui est éprouvé.
    """
    result = run_audit_gate(tmp_path, exception_entry(utc_today()), "--option-inconnue")

    assert result.returncode == 2, result.stderr


# Les fautes qu'une main commet en écrivant une exception. Chacune, sans validation, finit soit
# en trace d'appel illisible dans le journal de CI, soit — pire — en exception acceptée ou
# ignorée en silence : une date en chaîne ne se compare à rien, une table mal nommée n'est lue
# par personne.
MALFORMED_EXCEPTIONS = {
    "sans date": '[[exception]]\nid = "GHSA-aaaa-bbbb-cccc"\nreason = "r"\n',
    "date entre guillemets": (
        '[[exception]]\nid = "GHSA-aaaa-bbbb-cccc"\nreason = "r"\nexpires = "2099-01-01"\n'
    ),
    "date et heure": (
        '[[exception]]\nid = "GHSA-aaaa-bbbb-cccc"\nreason = "r"\nexpires = 2099-01-01T00:00:00\n'
    ),
    "raison vide": '[[exception]]\nid = "GHSA-aaaa-bbbb-cccc"\nreason = ""\nexpires = 2099-01-01\n',
    "champ mal orthographié": (
        '[[exception]]\nid = "GHSA-aaaa-bbbb-cccc"\nraison = "r"\nexpires = 2099-01-01\n'
    ),
    "table mal nommée": (
        '[[exceptions]]\nid = "GHSA-aaaa-bbbb-cccc"\nreason = "r"\nexpires = 2099-01-01\n'
    ),
    "TOML illisible": "[[exception]]\nexpires = \n",
}


@pytest.mark.parametrize(
    "exceptions", MALFORMED_EXCEPTIONS.values(), ids=MALFORMED_EXCEPTIONS.keys()
)
def test_un_fichier_d_exceptions_mal_forme_fait_echouer_l_audit(
    tmp_path: Path, exceptions: str
) -> None:
    """Un fichier mal formé est refusé avant l'audit, avec un message et sans trace d'appel."""
    result = run_audit_gate(tmp_path, exceptions, PIP_AUDIT_VERSION)

    assert result.returncode == 1
    assert "fichier d'exceptions invalide" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr
    assert "pip-audit" not in result.stdout, "`pip-audit` a tourné malgré un fichier invalide"
