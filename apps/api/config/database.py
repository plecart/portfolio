"""Traduction d'une adresse Postgres en réglages Django.

Django n'accepte pas d'URL dans `DATABASES` : il attend un dictionnaire de champs. Cette
traduction vit ici plutôt que dans `settings.py` pour être testable sans charger Django, et
parce qu'elle a des cas limites propres (encodage des identifiants, port implicite).

Aucune dépendance : `dj-database-url` ferait ce travail, mais le projet n'a qu'une seule forme
d'adresse à traduire — celle d'un Postgres unique (ADR 0005).
"""

from urllib.parse import unquote

from pydantic import PostgresDsn

POSTGRES_BACKEND = "django.db.backends.postgresql"
DEFAULT_PORT = 5432

# `postgresql+asyncpg`, `postgresql+psycopg2`… sont des schémas valides pour `PostgresDsn` qui
# nomment un pilote ; le moteur Django ci-dessus n'en utilise aucun. Seules les deux formes
# neutres sont acceptées.
NEUTRAL_SCHEMES = ("postgres", "postgresql")


def database_settings(url: PostgresDsn) -> dict[str, str | int]:
    """Construit le bloc `DATABASES["default"]` correspondant à `url`.

    Args:
        url: adresse validée du Postgres applicatif, telle que `Env` la fournit.

    Returns:
        Le dictionnaire attendu par Django : `ENGINE`, `NAME`, `USER`, `PASSWORD`, `HOST`,
        `PORT`. Les **quatre** composants que l'URL transporte percent-encodés — utilisateur,
        mot de passe, hôte et nom de base — sont décodés.

    Raises:
        ValueError: dès que l'adresse dit quelque chose que cette traduction n'honorerait pas —
            plusieurs hôtes alors que le projet n'en sert qu'un (ADR 0005), aucun nom de base,
            un pilote explicite dans le schéma, ou des paramètres de connexion. Chacun de ces
            cas produit sinon une connexion plausible mais fausse, qui n'échoue qu'au premier
            accès, loin du fichier qui l'a causée.
    """
    if url.scheme not in NEUTRAL_SCHEMES:
        raise ValueError(
            f"schéma « {url.scheme} » : seuls {' et '.join(NEUTRAL_SCHEMES)} sont pris en charge"
        )

    if url.query:
        raise ValueError(f"paramètre de connexion non pris en charge : « {url.query} »")

    hosts = url.hosts()
    if len(hosts) != 1:
        raise ValueError(f"l'adresse Postgres doit désigner un seul hôte, {len(hosts)} trouvés")

    name = (url.path or "").lstrip("/")
    if not name:
        raise ValueError("l'adresse Postgres doit porter un nom de base de données")

    host = hosts[0]
    return {
        "ENGINE": POSTGRES_BACKEND,
        "NAME": unquote(name),
        "USER": unquote(host["username"] or ""),
        "PASSWORD": unquote(host["password"] or ""),
        "HOST": unquote(host["host"] or ""),
        "PORT": host["port"] or DEFAULT_PORT,
    }
