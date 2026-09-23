"""Traduction d'une adresse Postgres en réglages Django.

Django n'accepte pas d'URL dans `DATABASES` : il attend un dictionnaire de champs. Cette
traduction vit ici plutôt que dans `settings.py` pour être testable sans charger Django, et
parce qu'elle a des cas limites propres (encodage du mot de passe, port implicite).

Aucune dépendance : `dj-database-url` ferait ce travail, mais le projet n'a qu'une seule forme
d'adresse à traduire — celle d'un Postgres unique (ADR 0005).
"""

from urllib.parse import unquote

from pydantic import PostgresDsn

MOTEUR = "django.db.backends.postgresql"
PORT_PAR_DEFAUT = 5432


def reglages_postgres(adresse: PostgresDsn) -> dict[str, str | int]:
    """Construit le bloc `DATABASES["default"]` correspondant à `adresse`.

    Args:
        adresse: adresse validée du Postgres applicatif, telle que `Env` la fournit.

    Returns:
        Le dictionnaire attendu par Django : `ENGINE`, `NAME`, `USER`, `PASSWORD`, `HOST`,
        `PORT`. Les identifiants sont décodés — une URL les transporte percent-encodés.

    Raises:
        ValueError: si l'adresse est incomplète — plusieurs hôtes alors que le projet n'en sert
            qu'un (ADR 0005), ou aucun nom de base. Les deux produisent une adresse plausible
            qui n'échoue qu'à la connexion, loin du fichier qui l'a causée.
    """
    hotes = adresse.hosts()
    if len(hotes) != 1:
        raise ValueError(f"l'adresse Postgres doit désigner un seul hôte, {len(hotes)} trouvés")

    nom = (adresse.path or "").lstrip("/")
    if not nom:
        raise ValueError("l'adresse Postgres doit porter un nom de base de données")

    hote = hotes[0]
    return {
        "ENGINE": MOTEUR,
        "NAME": nom,
        "USER": unquote(hote["username"] or ""),
        "PASSWORD": unquote(hote["password"] or ""),
        "HOST": hote["host"] or "",
        "PORT": hote["port"] or PORT_PAR_DEFAUT,
    }
