"""Point d'entrée des commandes Django, à lancer depuis `apps/api`.

Pas de shebang : rien n'exécute ce fichier directement. `CONTRIBUTING.md`, le `Makefile` et les
tests passent tous par l'interpréteur (`uv run python manage.py …`). Un shebang sans bit
exécutable est d'ailleurs refusé par ruff (`EXE001`) — sur POSIX seulement, donc invisible
depuis un poste Windows.
"""

import os
import sys


def main() -> None:
    """Délègue la ligne de commande à Django, réglages `config.settings`."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
