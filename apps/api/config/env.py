"""Lecture de l'environnement du back.

Seul point du projet qui lit l'environnement (cadrage §6.6 « 12-factor, `.env` en développement
seulement », ADR 0001 « Configuration 12-factor : pydantic-settings »). `settings.py` instancie
`Env` une fois et pose chaque réglage Django depuis cette instance ; le reste du code lit
`django.conf.settings`, jamais l'environnement.

Ajouter une variable, c'est ajouter un champ typé ici **et** une ligne dans `.env.example`.
Aucun `os.environ` ailleurs, aucune valeur d'environnement en dur.
"""

from pydantic import PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(BaseSettings):
    """Variables d'environnement du back, validées une fois au démarrage.

    Un environnement incomplet ou mal formé fait échouer la construction avec une
    `ValidationError` : l'application refuse de démarrer plutôt que de tourner à moitié
    configurée.

    `extra="forbid"` est le défaut de `pydantic-settings` pour le fichier `.env` : une clé
    inconnue y est une faute de frappe, pas une option, et fait échouer le démarrage.

    Attributs :
        SECRET_KEY: clé de signature Django. Aucun défaut — l'absence est une erreur, jamais
            une valeur de repli. `SecretStr` pour qu'elle n'apparaisse pas dans une trace ni
            dans un journal.
        DATABASE_URL: adresse du Postgres applicatif (ADR 0005).
        REDIS_URL: adresse du Redis (ADR 0006). Déclarée et validée ici ; son premier lecteur
            (le cache Django) arrive avec #7, et `django-redis` avec lui.
    """

    model_config = SettingsConfigDict(env_file=".env")

    SECRET_KEY: SecretStr
    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn
