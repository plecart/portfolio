"""Tests de la traduction d'une adresse Postgres en réglages Django."""

import pytest
from config.database import database_settings
from pydantic import PostgresDsn, TypeAdapter

POSTGRES_URL = TypeAdapter(PostgresDsn)


def test_l_adresse_est_traduite_en_bloc_django() -> None:
    settings = database_settings(
        POSTGRES_URL.validate_python("postgresql://portfolio:secret@db.interne:5433/contenu")
    )

    assert settings == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "contenu",
        "USER": "portfolio",
        "PASSWORD": "secret",
        "HOST": "db.interne",
        "PORT": 5433,
    }


def test_un_mot_de_passe_encode_est_decode() -> None:
    """Un mot de passe contenant `@` ou `/` doit être encodé dans l'URL — et décodé ici."""
    settings = database_settings(
        POSTGRES_URL.validate_python("postgresql://portfolio:a%40b%2Fc@localhost:5432/contenu")
    )

    assert settings["PASSWORD"] == "a@b/c"


def test_le_port_par_defaut_est_celui_de_postgres() -> None:
    settings = database_settings(
        POSTGRES_URL.validate_python("postgresql://portfolio:secret@localhost/contenu")
    )

    assert settings["PORT"] == 5432


def test_plusieurs_hotes_sont_refuses() -> None:
    """Un seul Postgres (ADR 0005) : garder le premier hôte en silence cacherait l'erreur."""
    url = POSTGRES_URL.validate_python("postgresql://portfolio:secret@un:5432,deux:5432/contenu")

    with pytest.raises(ValueError, match="un seul hôte"):
        database_settings(url)


def test_une_adresse_sans_nom_de_base_est_refusee() -> None:
    """Un nom de base vide ne casse qu'à la connexion, loin du fichier qui l'a causé."""
    url = POSTGRES_URL.validate_python("postgresql://portfolio:secret@localhost:5432")

    with pytest.raises(ValueError, match="nom de base"):
        database_settings(url)
