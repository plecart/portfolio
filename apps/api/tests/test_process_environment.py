"""Tests de l'épingle de Ryuk, posée par le greffon `process_environment` avant que testcontainers
ne lise sa configuration.

Gardée au retrait du harnais en trop (#11, décision 2) pour un défaut documenté : en mars 2026,
les étiquettes des deux actions de Trivy ont été déplacées vers un voleur d'identifiants
(GHSA-69fq-xp46-6x23, ADR 0014 §Décision) — et Ryuk reçoit le socket Docker en écriture.
"""

import os
import re
import subprocess
import sys

from process_environment import RYUK_IMAGE
from testcontainers.core.config import testcontainers_config

# Imprime l'image Ryuk que testcontainers choisit de lui-même, faute de variable qui l'épingle.
# Dans un processus à part : la configuration est lue une fois, à l'import du module.
RYUK_DEFAULT = (
    "from testcontainers.core.config import testcontainers_config as c; print(c.ryuk_image)"
)


def test_ryuk_tourne_sur_l_image_epinglee() -> None:
    """testcontainers lit son image Ryuk à l'import : le greffon doit l'avoir posée avant."""
    assert testcontainers_config.ryuk_image == RYUK_IMAGE


def test_l_epingle_de_ryuk_suit_l_image_que_testcontainers_attend() -> None:
    """Une montée de testcontainers qui change d'image Ryuk fait rougir ce test.

    Sans lui, l'épingle garderait en silence l'ancienne image, que la nouvelle version ne sait
    peut-être plus piloter. La mise à jour se fait alors dans la PR de montée : étiquette et
    empreinte ensemble.
    """
    default = subprocess.run(
        [sys.executable, "-c", RYUK_DEFAULT],
        env={name: value for name, value in os.environ.items() if name != "RYUK_CONTAINER_IMAGE"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tag, _, digest = RYUK_IMAGE.partition("@")

    assert tag == default
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
