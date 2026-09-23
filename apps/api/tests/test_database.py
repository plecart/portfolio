"""Tests de la traduction d'une adresse Postgres en réglages Django."""

import pytest
from config.database import NEUTRAL_SCHEMES, database_settings
from pydantic import PostgresDsn, TypeAdapter

POSTGRES_URL = TypeAdapter(PostgresDsn)

# Les schémas que `PostgresDsn` accepte et qui nomment un pilote. Tirés de pydantic plutôt
# qu'écrits à la main : une version qui en ajoute un le met sous test le jour même, et une
# version qui déplace cet attribut casse ici, bruyamment, plutôt que de rétrécir la couverture
# en silence.
_ALLOWED_SCHEMES = PostgresDsn._constraints.allowed_schemes  # pyright: ignore[reportPrivateUsage]
assert _ALLOWED_SCHEMES is not None, "pydantic n'expose plus la liste des schémas de PostgresDsn"

DRIVER_SCHEMES = [schema for schema in _ALLOWED_SCHEMES if schema not in NEUTRAL_SCHEMES]


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


def test_les_quatre_identifiants_encodes_sont_decodes() -> None:
    """Quatre composants de l'URL voyagent percent-encodés, et les quatre atterrissent dans
    `DATABASES` : utilisateur, mot de passe, hôte (forme socket Unix) et nom de base. N'en
    décoder qu'une partie donne des identifiants faux sans jamais lever d'erreur.
    """
    settings = database_settings(
        POSTGRES_URL.validate_python("postgresql://a%40u:a%40p@%2Fvar%2Frun%2Fpg:5432/ma%20base")
    )

    assert settings["USER"] == "a@u"
    assert settings["PASSWORD"] == "a@p"
    assert settings["HOST"] == "/var/run/pg"
    assert settings["NAME"] == "ma base"


def test_un_parametre_de_connexion_est_refuse() -> None:
    """`?sslmode=require` change la sécurité de la connexion ; le jeter en silence, jamais."""
    url = POSTGRES_URL.validate_python("postgresql://u:p@h:5432/db?sslmode=require")

    with pytest.raises(ValueError, match="paramètre"):
        database_settings(url)


@pytest.mark.parametrize("schema", DRIVER_SCHEMES)
def test_un_pilote_explicite_est_refuse(schema: str) -> None:
    """Tout schéma qui nomme un pilote est refusé — la liste vient de pydantic, pas d'un choix."""
    url = POSTGRES_URL.validate_python(f"{schema}://u:p@h:5432/db")

    with pytest.raises(ValueError, match="schéma"):
        database_settings(url)


@pytest.mark.parametrize("schema", NEUTRAL_SCHEMES)
def test_un_schema_neutre_est_accepte(schema: str) -> None:
    """Le pendant du test précédent : le garde ne doit pas mordre sur les formes légitimes."""
    url = POSTGRES_URL.validate_python(f"{schema}://u:p@h:5432/db")

    assert database_settings(url)["NAME"] == "db"


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
