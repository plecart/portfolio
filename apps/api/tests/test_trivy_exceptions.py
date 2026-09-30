"""Tests des exceptions du scan des images (`.trivyignore.yaml`) : complètes, datées, en vigueur.

Trivy lit ce fichier lui-même (`make scan`), et n'y exige que `id` : une entrée sans `expired_at`
vaut pour toujours, une clé mal orthographiée est ignorée sans un mot. La règle du projet est plus
stricte (ADR 0014) — chaque exception porte l'évaluation qui la fonde et la date où elle se
refait — et c'est cette garde qui la tient.

Comme dans `test_supply_chain.py`, la garde est une fonction sur du texte, appliquée au fichier du
dépôt et à un recueil de formes, `EXCEPTION_FORMS`, chacune avec son verdict attendu.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
import yaml

# `test_trivy_exceptions.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXCEPTIONS = REPOSITORY_ROOT / ".trivyignore.yaml"

# Les champs d'une exception, tous obligatoires. Un champ en plus est refusé comme un champ en
# moins, comme pour les exceptions de `pip-audit` : c'est presque toujours une faute de frappe sur
# un champ requis (`expire_at`), que Trivy ignorerait — l'exception deviendrait permanente.
FIELDS = {"id", "statement", "expired_at"}


def entry_findings(entry: object, today: date) -> list[str]:
    """Ce qui manque à une entrée pour être une exception valable à la date `today`.

    Args:
        entry: l'entrée lue par l'analyseur YAML.
        today: la date du jour, en UTC.

    Returns:
        Un constat par défaut relevé ; liste vide si l'exception est complète et en vigueur.
    """
    if not isinstance(entry, dict):
        return [f"table attendue, {type(entry).__name__} lu"]
    fields = cast(dict[object, object], entry)
    if set(fields) != FIELDS:
        return [f"champs {sorted(map(str, fields))}, attendus {sorted(FIELDS)}"]
    findings: list[str] = []
    for name in ("id", "statement"):
        value = fields[name]
        if not (isinstance(value, str) and value.strip()):
            findings.append(f"`{name}` doit être une chaîne non vide")
    expired_at = fields["expired_at"]
    # `datetime` hérite de `date` : sans le test de type exact, une date et heure passerait ici.
    if type(expired_at) is not date:
        findings.append("`expired_at` doit être une date YAML sans guillemets ni heure")
    # Trivy compare l'instant présent à minuit UTC du jour indiqué (`IgnoreFindings.Prune`,
    # `pkg/result/ignore.go`) : l'exception cesse de valoir dès le début de ce jour-là.
    elif expired_at <= today:
        findings.append(f"{fields['id']} : expirée depuis le {expired_at}, évaluation à refaire")
    return findings


def exception_findings(text: str, today: date) -> list[str]:
    """Ce qui, dans un fichier d'exceptions de Trivy, n'est pas une exception valable.

    Toutes les sections sont lues, quel que soit leur nom : une exception de secret ou de
    mauvaise configuration suit la même règle qu'une exception de vulnérabilité.

    Args:
        text: le contenu du fichier, au format YAML de Trivy.
        today: la date du jour, en UTC — celle de la CI et celle que Trivy compare.

    Returns:
        Un constat par entrée fautive, préfixé de sa section et de son rang ; liste vide si tout
        est valable, ou si le fichier ne porte aucune exception.
    """
    document: object = yaml.safe_load(text) or {}
    if not isinstance(document, dict):
        return [f"table de sections attendue, {type(document).__name__} lu"]
    findings: list[str] = []
    for section, entries in cast(dict[object, object], document).items():
        if not isinstance(entries, list):
            findings.append(f"{section} : liste d'exceptions attendue")
            continue
        for number, entry in enumerate(cast(list[object], entries), start=1):
            findings.extend(
                f"{section} n° {number} : {finding}" for finding in entry_findings(entry, today)
            )
    return findings


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

TODAY = date(2026, 9, 30)
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def exception_file(section: str = "vulnerabilities", **changes: str | None) -> str:
    """Un fichier d'une exception valable à la date `TODAY`, modifiée par `changes`.

    Chaque changement remplace la valeur YAML brute d'un champ, ou le retire s'il vaut `None` ;
    un champ inconnu est ajouté. Un cas mal formé se lit ainsi comme l'écart exact qui le rend
    invalide.
    """
    fields: dict[str, str | None] = {
        "id": "CVE-2026-0001",
        "statement": "Place, atteinte, alternatives.",
        "expired_at": TOMORROW,
        **changes,
    }
    lines = [f"{key}: {value}" for key, value in fields.items() if value is not None]
    return f"{section}:\n  - " + "\n    ".join(lines) + "\n"


# Forme → constat attendu (`True`) ou aucun (`False`).
EXCEPTION_FORMS = {
    "complète, expire demain": (exception_file(), False),
    "fichier sans exception": ("# aucune exception\n", False),
    "sans expired_at": (exception_file(expired_at=None), True),
    "sans statement": (exception_file(statement=None), True),
    "sans id": (exception_file(id=None), True),
    "statement vide": (exception_file(statement='""'), True),
    "id vide": (exception_file(id='""'), True),
    "expire aujourd'hui": (exception_file(expired_at=TODAY.isoformat()), True),
    "expirée hier": (exception_file(expired_at=YESTERDAY), True),
    "date entre guillemets": (exception_file(expired_at=f'"{TOMORROW}"'), True),
    "date et heure": (exception_file(expired_at=f"{TOMORROW}T00:00:00Z"), True),
    "champ mal orthographié": (exception_file(expired_at=None, expire_at=TOMORROW), True),
    "champ en trop": (exception_file(note="x"), True),
    "autre section, sans date": (exception_file(section="secrets", expired_at=None), True),
    "autre section, complète": (exception_file(section="secrets"), False),
    "entrée qui n'est pas une table": ("vulnerabilities:\n  - CVE-2026-0001\n", True),
    "section qui n'est pas une liste": ("vulnerabilities: CVE-2026-0001\n", True),
    "document qui n'est pas une table": ("- CVE-2026-0001\n", True),
}


@pytest.mark.parametrize(("text", "expected"), EXCEPTION_FORMS.values(), ids=EXCEPTION_FORMS.keys())
def test_la_garde_des_exceptions_rend_son_verdict_sur_chaque_forme(
    text: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, l'exception est incomplète, mal
    typée ou expirée."""
    assert bool(exception_findings(text, TODAY)) is expected, exception_findings(text, TODAY)


# --- Le fichier du dépôt ----------------------------------------------------------------------


def test_chaque_exception_du_scan_est_complete_et_en_vigueur() -> None:
    """Une exception ne devient permanente ni par oubli, ni par une clé mal orthographiée.

    Passée sa date, elle fait échouer ce test le jour même où Trivy cesse de l'appliquer : le
    rouge dit quelle évaluation refaire, avant même de lire le rapport du scan (ADR 0014). La
    date du jour est celle de l'UTC, comme pour les exceptions de `pip-audit` : le poste et la CI
    rendent le même verdict.
    """
    findings = exception_findings(EXCEPTIONS.read_text(encoding="utf-8"), datetime.now(UTC).date())

    assert not findings, findings
