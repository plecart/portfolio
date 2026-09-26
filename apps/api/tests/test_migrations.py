"""Aucun modèle sans sa migration."""

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_aucun_modele_n_attend_sa_migration() -> None:
    """Un modèle changé sans sa migration passerait toutes les portes, et sa contrainte
    n'existerait pas en base : `makemigrations --check` échoue dès qu'il en reste une à écrire,
    sans rien écrire — `--check` vaut `--dry-run` (`makemigrations.py`).

    `django_db` : la commande confronte l'historique des migrations à la base de test.
    """
    call_command("makemigrations", "--check")
