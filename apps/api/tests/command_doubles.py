"""Doubles des commandes qu'un script de skill lance par son `run` injecté — `gh`, `git` —, et
lecture de ce qu'il écrit.

Un script de skill lit ses commandes en octets (obs 108) : une réponse est un
`subprocess.CompletedProcess[bytes]`, ou une `OSError`, levée comme un exécutable introuvable.
"""

import json
import subprocess
from typing import Any

import pytest

Reply = subprocess.CompletedProcess[bytes] | OSError

# Ce que `altered` met à la place d'un champ pour le retirer.
ABSENT = object()


def success(stdout: bytes) -> subprocess.CompletedProcess[bytes]:
    """Une commande qui réussit et écrit `stdout` sur sa sortie standard."""
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr=b"")


def json_success(content: Any) -> subprocess.CompletedProcess[bytes]:
    """La sortie de `gh … --json` ou de `gh api` : le JSON brut, en UTF-8 — accents compris,
    comme l'API les rend."""
    return success(json.dumps(content, ensure_ascii=False).encode())


def failure(stderr: bytes) -> subprocess.CompletedProcess[bytes]:
    """Une commande qui sort en 1 sans rien écrire sur sa sortie standard."""
    return subprocess.CompletedProcess([], 1, stdout=b"", stderr=stderr)


def altered(content: Any, path: tuple[str | int, ...], value: Any) -> Any:
    """`content` dont le champ au bout de `path` vaut `value` — retiré pour `ABSENT` ; un chemin
    vide remplace le document entier."""
    if not path:
        return value
    *parents, key = path
    target = content
    for step in parents:
        target = target[step]
    if value is ABSENT:
        del target[key]
    else:
        target[key] = value
    return content


def stdout_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Ce que le script a écrit sur sa sortie standard, ligne par ligne."""
    return capsys.readouterr().out.splitlines()


def sortie_d_echec(capsys: pytest.CaptureFixture[str], issue: str) -> str:
    """La sortie d'un échec : une seule ligne, ouverte par son issue — « refus » quand rien n'est
    écrit, « relecture non conforme » quand le geste est lancé."""
    sortie = capsys.readouterr().out.strip()
    assert sortie.startswith(f"{issue} — "), sortie
    assert "\n" not in sortie, f"la sortie tient en plus d'une ligne : {sortie!r}"
    return sortie
