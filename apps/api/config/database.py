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


def database_settings(url: PostgresDsn) -> dict[str, str | int]:
    """Construit le bloc `DATABASES["default"]` correspondant à `url`.

    Args:
        url: adresse validée du Postgres applicatif, telle que `Env` la fournit.

    Returns:
        Le dictionnaire attendu par Django : `ENGINE`, `NAME`, `USER`, `PASSWORD`, `HOST`,
        `PORT`. Les identifiants sont décodés — une URL les transporte percent-encodés.

    Raises:
        ValueError: si l'adresse est incomplète — plusieurs hôtes alors que le projet n'en sert
            qu'un (ADR 0005), ou aucun nom de base. Les deux produisent une adresse plausible
            qui n'échoue qu'à la connexion, loin du fichier qui l'a causée.
    """
    hosts = url.hosts()
    if len(hosts) != 1:
        raise ValueError(f"l'adresse Postgres doit désigner un seul hôte, {len(hosts)} trouvés")

    name = (url.path or "").lstrip("/")
    if not name:
        raise ValueError("l'adresse Postgres doit porter un nom de base de données")

    host = hosts[0]
    return {
        "ENGINE": POSTGRES_BACKEND,
        "NAME": name,
        "USER": unquote(host["username"] or ""),
        "PASSWORD": unquote(host["password"] or ""),
        "HOST": host["host"] or "",
        "PORT": host["port"] or DEFAULT_PORT,
    }
