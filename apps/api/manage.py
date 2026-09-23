#!/usr/bin/env python
"""Point d'entrée des commandes Django, à lancer depuis `apps/api`."""

import os
import sys


def main() -> None:
    """Délègue la ligne de commande à Django, réglages `config.settings`."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
