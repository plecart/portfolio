"""Tests de l'image `api` et des fichiers que le conteneur lit dans la copie de travail.

Ces tests lisent des fichiers comme du texte, sans construire l'image : ils gardent les
invariants qu'une relecture laisse filer. Que l'image **se construise** et **démarre** est
prouvé ailleurs — par le job `infra` de la CI, et par la pile qui tourne.
"""

import re
from pathlib import Path

# `test_image.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPOSITORY_ROOT / "infra" / "api" / "Dockerfile"
PYTHON_VERSION_FILE = REPOSITORY_ROOT / ".python-version"

# Toute image de base qui embarque un interpréteur porte sa version dans son nom. Le motif les
# capture toutes : le Dockerfile en a deux étages, et un seul qui dériverait suffirait à faire
# tourner l'application sur une version que le dépôt n'épingle nulle part.
BASE_IMAGE_VERSION = re.compile(r"^FROM python:(\d+\.\d+)[.-]", re.MULTILINE)

# Les fichiers qu'un outil Linux lit dans la **copie de travail** : ce que le shell du conteneur
# exécute, ce que buildkit analyse, ce dont Compose tire des valeurs. Un `\r` y est invisible à
# la relecture et ne se voit qu'à l'exécution — et jamais en CI, qui travaille sur un checkout
# Linux. Tout fichier ajouté à `infra/` et lu par un conteneur entre dans un de ces motifs.
CONTAINER_TEXT_GLOBS = [
    "infra/**/*.sh",
    "infra/**/Dockerfile",
    "infra/**/*.env",
    ".dockerignore",
    ".env.example",
]


def test_les_images_de_base_suivent_la_version_epinglee() -> None:
    """Deux épingles qui divergeraient en silence ne vaudraient pas mieux qu'aucune.

    Même garde que pour Node, où `.nvmrc` et le champ `engines` portent la même valeur sous
    la surveillance d'un test (`.claude/pipeline.config.md`, section « Stack »). `uv` lit
    `.python-version` sur le poste et en CI, mais une image de base porte sa version dans son
    nom : rien ne relie les deux, sinon ce test.
    """
    pinned = PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    found = BASE_IMAGE_VERSION.findall(DOCKERFILE.read_text(encoding="utf-8"))

    assert found, "aucune image de base `python:` trouvée — le motif a-t-il cessé de mordre ?"
    assert set(found) == {pinned}


def test_aucun_fichier_lu_par_un_conteneur_ne_porte_de_retour_windows() -> None:
    """Un `\\r` dans ces fichiers casse à l'exécution, et seulement sur un poste Windows.

    `core.autocrlf` réécrit la copie de travail en CRLF ; le dépôt garde du LF, donc la CI
    Linux ne voit jamais rien. `#!/bin/sh` suivi d'un `\\r` donne « exec … : no such file or
    directory » au démarrage du conteneur — sur une image pourtant construite verte.
    `.gitattributes` force le LF ; ce test vérifie qu'il couvre encore toute la population.
    """
    checked = sorted(path for glob in CONTAINER_TEXT_GLOBS for path in REPOSITORY_ROOT.glob(glob))

    assert checked, "aucun fichier trouvé — les motifs ont-ils cessé de mordre ?"
    faulty = [path for path in checked if b"\r\n" in path.read_bytes()]
    assert not faulty, f"{len(checked)} fichiers repassés, fins de ligne Windows dans {faulty}"
