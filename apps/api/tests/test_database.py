"""Tests de la traduction d'une adresse Postgres en réglages Django."""

import pytest
from config.database import reglages_postgres
from pydantic import PostgresDsn, TypeAdapter

ADRESSE = TypeAdapter(PostgresDsn)


def test_l_adresse_est_traduite_en_bloc_django() -> None:
    reglages = reglages_postgres(
        ADRESSE.validate_python("postgresql://portfolio:secret@db.interne:5433/contenu")
    )

    assert reglages == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "contenu",
        "USER": "portfolio",
        "PASSWORD": "secret",
        "HOST": "db.interne",
        "PORT": 5433,
    }


def test_un_mot_de_passe_encode_est_decode() -> None:
    """Un mot de passe contenant `@` ou `/` doit être encodé dans l'URL — et décodé ici."""
    reglages = reglages_postgres(
        ADRESSE.validate_python("postgresql://portfolio:a%40b%2Fc@localhost:5432/contenu")
    )

    assert reglages["PASSWORD"] == "a@b/c"


def test_le_port_par_defaut_est_celui_de_postgres() -> None:
    reglages = reglages_postgres(
        ADRESSE.validate_python("postgresql://portfolio:secret@localhost/contenu")
    )

    assert reglages["PORT"] == 5432


def test_plusieurs_hotes_sont_refuses() -> None:
    """Un seul Postgres (ADR 0005) : garder le premier hôte en silence cacherait l'erreur."""
    adresse = ADRESSE.validate_python("postgresql://portfolio:secret@un:5432,deux:5432/contenu")

    with pytest.raises(ValueError, match="un seul hôte"):
        reglages_postgres(adresse)


def test_une_adresse_sans_nom_de_base_est_refusee() -> None:
    """Un nom de base vide ne casse qu'à la connexion, loin du fichier qui l'a causé."""
    adresse = ADRESSE.validate_python("postgresql://portfolio:secret@localhost:5432")

    with pytest.raises(ValueError, match="nom de base"):
        reglages_postgres(adresse)
