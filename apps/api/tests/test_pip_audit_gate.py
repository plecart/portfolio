"""Tests de la porte d'audit Python (`infra/ci/pip_audit_gate.py`) : exceptions datées.

La porte est lancée comme la CI la lance, en sous-processus, mais hors ligne : `pip-audit` n'y
reçoit que des options qui ne consultent aucun service. Ce qui est éprouvé, c'est le contrat de la
porte — une exception expirée ou mal écrite bloque avant l'audit, une exception valable est
transmise, le code de sortie de `pip-audit` remonte tel quel.
"""

import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

# `test_pip_audit_gate.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AUDIT_GATE = REPOSITORY_ROOT / "infra" / "ci" / "pip_audit_gate.py"

# Un identifiant d'avis quelconque : la porte ne le cherche nulle part, elle le transmet.
ADVISORY = "GHSA-aaaa-bbbb-cccc"

# Transmis à `pip-audit` à la place d'un audit réel : il répond sans réseau et sans rien auditer.
# C'est ce qui permet de savoir, sans dépendre de PyPI, si la porte a lancé `pip-audit` ou non.
PIP_AUDIT_VERSION = "--version"


def utc_today() -> date:
    """La date du jour telle que la porte la calcule : en UTC, celle de la CI."""
    return datetime.now(UTC).date()


def exception_entry(**changes: str | None) -> bytes:
    """Une exception valable, modifiée par `changes`, au format du fichier d'exceptions.

    Chaque changement remplace la valeur TOML brute d'un champ, ou le retire s'il vaut `None` ;
    un champ inconnu est ajouté. Un cas mal formé se lit ainsi comme l'écart exact qui le rend
    invalide.

    Args:
        changes: champ → valeur TOML brute (`'"texte"'`, `2026-12-31`), ou `None` pour le retirer.

    Returns:
        La table `[[exception]]`, encodée en UTF-8 ; par défaut, elle expire aujourd'hui (UTC).
    """
    fields: dict[str, str | None] = {
        "id": f'"{ADVISORY}"',
        "reason": '"aucun chemin d\'appel vers le code vulnérable"',
        "expires": utc_today().isoformat(),
        **changes,
    }
    lines = [f"{key} = {value}" for key, value in fields.items() if value is not None]
    return "\n".join(["[[exception]]", *lines, ""]).encode()


def run_audit_gate(
    tmp_path: Path, exceptions: bytes | None, *forwarded: str, timezone: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Lance la porte d'audit, depuis `tmp_path`, sur un fichier d'exceptions écrit pour le test.

    Args:
        tmp_path: dossier temporaire du test : il reçoit le fichier et sert de dossier courant.
        exceptions: contenu du fichier d'exceptions ; `None` pour un fichier absent.
        forwarded: arguments que la porte doit transmettre à `pip-audit`.
        timezone: valeur de `TZ` pour la porte, c'est-à-dire son fuseau local ; celui du poste
            par défaut.

    Returns:
        Le processus terminé, sorties capturées.
    """
    path = tmp_path / "exceptions.toml"
    if exceptions is not None:
        path.write_bytes(exceptions)
    environment = dict(os.environ)
    if timezone:
        environment["TZ"] = timezone
    return subprocess.run(
        [sys.executable, str(AUDIT_GATE), "--exceptions", str(path), *forwarded],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def offline_audit(tmp_path: Path) -> list[str]:
    """Les arguments d'un audit réel, mais hors ligne, que `pip-audit` journalise.

    `--dry-run` sur un environnement vide ne consulte aucun service ; `-v` fait journaliser par
    `pip-audit` les arguments qu'il a reçus, dont `ignore_vulns`. C'est ce qui prouve la
    transmission des exceptions : l'écho de la commande par la porte ne prouve que l'écho.
    """
    empty = tmp_path / "environnement-vide"
    empty.mkdir()
    return ["-v", "--dry-run", "--progress-spinner", "off", "--path", str(empty)]


def test_une_exception_expiree_fait_echouer_l_audit_sans_le_lancer(tmp_path: Path) -> None:
    """Passée sa date, une exception rebloque : c'est ce qui l'empêche de devenir permanente.

    L'échec précède l'audit : `pip-audit` ne tourne pas du tout, pour qu'une exception expirée
    ne puisse jamais passer inaperçue derrière un audit qui, par ailleurs, serait vert.
    """
    yesterday = (utc_today() - timedelta(days=1)).isoformat()

    result = run_audit_gate(tmp_path, exception_entry(expires=yesterday), PIP_AUDIT_VERSION)

    assert result.returncode == 1
    assert ADVISORY in result.stderr
    assert "pip-audit" not in result.stdout, "`pip-audit` a tourné malgré l'exception expirée"


def test_une_exception_valable_est_transmise_a_pip_audit(tmp_path: Path) -> None:
    """Jusqu'à sa date incluse, `pip-audit` reçoit l'ordre d'ignorer l'avis, et l'audit tourne."""
    result = run_audit_gate(tmp_path, exception_entry(), *offline_audit(tmp_path))

    assert result.returncode == 0, result.stderr
    assert f"ignore_vulns=['{ADVISORY}']" in result.stderr


# Deux fuseaux extrêmes. À toute heure, l'un d'eux décale la date locale d'un jour par rapport à la
# date UTC : UTC+14 dès 10 h UTC, UTC-12 avant midi UTC. Une porte qui lirait la date locale fait
# donc échouer l'un des deux cas, quelle que soit l'heure du run. Notation POSIX de `TZ`, honorée
# aussi par le CRT de Windows (mesuré) — le signe y est inversé : `AAA-14` est en avance sur UTC.
@pytest.mark.parametrize(
    ("timezone", "age_in_days", "expected"),
    [("AAA-14", 0, 0), ("AAA+12", 1, 1)],
    ids=["UTC+14, expire aujourd'hui en UTC", "UTC-12, a expiré hier en UTC"],
)
def test_la_date_du_jour_est_celle_de_l_utc(
    tmp_path: Path, timezone: str, age_in_days: int, expected: int
) -> None:
    """Le poste et la CI rendent le même verdict, quel que soit le fuseau du poste."""
    expires = (utc_today() - timedelta(days=age_in_days)).isoformat()

    result = run_audit_gate(
        tmp_path, exception_entry(expires=expires), PIP_AUDIT_VERSION, timezone=timezone
    )

    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize(
    ("forwarded", "expected", "trace"),
    [
        (("--option-inconnue",), 2, "pip-audit: error"),
        (("-r", "requirements-absent.txt"), 1, "invalid requirements input"),
    ],
    ids=["refus d'une option", "échec de l'audit"],
)
def test_la_porte_rend_le_code_de_sortie_de_pip_audit(
    tmp_path: Path, forwarded: tuple[str, ...], expected: int, trace: str
) -> None:
    """Une porte qui avalerait le code de `pip-audit` ne bloquerait jamais rien.

    Les deux codes viennent de `pip-audit` lui-même, sans réseau — `trace` le prouve : 2 pour une
    option qu'il refuse, 1 pour un audit qui échoue, le code d'une vulnérabilité trouvée. Le
    fichier d'exceptions est vide : le test ne dépend pas de la date.
    """
    result = run_audit_gate(tmp_path, b"", *forwarded)

    assert result.returncode == expected, result.stderr
    assert trace in result.stderr


# Les formes que prend un fichier d'exceptions mal écrit : 14 recensées sur les 10 branches de
# validation de la porte, toutes refusées avant l'audit. Sans validation, chacune finit en trace
# d'appel illisible dans le journal de CI, ou — pire — en exception acceptée à tort ou ignorée en
# silence : une date en chaîne ne se compare à rien, une table mal nommée n'est lue par personne,
# un `id` entouré d'espaces ne correspond à aucun avis. Toute branche de validation ajoutée à la
# porte ajoute sa forme ici.
MALFORMED_EXCEPTIONS: dict[str, bytes | None] = {
    "fichier absent": None,
    "encodage autre qu'UTF-8": '[[exception]]\nreason = "é"\n'.encode("latin-1"),
    "TOML illisible": b"[[exception]]\nexpires = \n",
    "table mal nommée": exception_entry().replace(b"[[exception]]", b"[[exceptions]]"),
    # Un entier et non une chaîne : une chaîne s'itère, et la branche suivante la refuserait
    # quand même — seul un non-itérable montre que ces deux branches-là mordent.
    "exception qui n'est pas une liste": b"exception = 2026\n",
    "entrée qui n'est pas une table": b"exception = [2026]\n",
    "sans date": exception_entry(expires=None),
    "champ en trop": exception_entry(note='"x"'),
    "champ mal orthographié": exception_entry(reason=None, raison='"r"'),
    "id vide": exception_entry(id='""'),
    "id entouré d'espaces": exception_entry(id=f'" {ADVISORY} "'),
    "raison vide": exception_entry(reason='""'),
    "date entre guillemets": exception_entry(expires='"2099-01-01"'),
    "date et heure": exception_entry(expires="2099-01-01T00:00:00"),
}


@pytest.mark.parametrize(
    "exceptions", MALFORMED_EXCEPTIONS.values(), ids=MALFORMED_EXCEPTIONS.keys()
)
def test_un_fichier_d_exceptions_mal_forme_fait_echouer_l_audit(
    tmp_path: Path, exceptions: bytes | None
) -> None:
    """Un fichier mal formé est refusé avant l'audit, avec un message et sans trace d'appel."""
    result = run_audit_gate(tmp_path, exceptions, PIP_AUDIT_VERSION)

    assert result.returncode == 1
    assert "fichier d'exceptions invalide" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr
    assert "pip-audit" not in result.stdout, "`pip-audit` a tourné malgré un fichier invalide"
