"""Tests de l'image `api` : ce que le Dockerfile promet doit tenir sans relecteur.

Ces tests lisent le Dockerfile comme un texte, sans construire l'image : ils gardent les
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
