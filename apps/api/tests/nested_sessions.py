"""Sessions pytest imbriquées : éprouver la suite de l'extérieur, comme la lance un développeur.

Certaines garanties ne se voient que sur une session entière — un test sauté plutôt qu'échoué,
une variable du shell qui l'emporte, un conteneur démarré pour tous les tests. Elles se vérifient
en relançant pytest dans un processus à part, sur une sélection de tests.
"""

import os
import subprocess
import sys
from collections.abc import Sequence

from config.env import REPOSITORY_ROOT


def pytest_session(tests: Sequence[str], **environment: str) -> subprocess.CompletedProcess[str]:
    """Lance pytest sur `tests` dans un processus à part, depuis la racine du dépôt.

    Args:
        tests: les identifiants de tests à lancer, relatifs à la racine. Jamais le test appelant
            lui-même : il se relancerait sans fin.
        environment: les variables à poser par-dessus l'environnement de ce processus.

    Returns:
        Le processus terminé ; le rapport de pytest est dans `stdout`. `-p no:cacheprovider` :
        la session imbriquée n'écrit pas dans le cache de la session qui la lance.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *tests],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        check=False,
    )
