"""Lecture de l'environnement du back.

Seul point du projet qui lit l'environnement (cadrage §6.6 « 12-factor, `.env` en développement
seulement », ADR 0001 « Configuration 12-factor : pydantic-settings »). `settings.py` instancie
`Env` une fois et pose chaque réglage Django depuis cette instance ; le reste du code lit
`django.conf.settings`, jamais l'environnement.

Ajouter une variable, c'est ajouter un champ typé ici **et** une ligne dans `.env.example`.
Aucun `os.environ` ailleurs, aucune valeur d'environnement en dur.
"""

from typing import Self

from pydantic import PostgresDsn, RedisDsn, SecretStr, model_validator
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
        DEBUG: mode de développement. Faux par défaut : un oubli laisse l'application en
            posture de production, jamais l'inverse.
        ALLOWED_HOSTS: noms d'hôte servis. Obligatoire dès que `DEBUG` est faux.
        DATABASE_URL: adresse du Postgres applicatif (ADR 0005).
        REDIS_URL: adresse du Redis (ADR 0006). Déclarée et validée ici ; son premier lecteur
            (le cache Django) arrive avec #7, et `django-redis` avec lui.
    """

    model_config = SettingsConfigDict(env_file=".env")

    SECRET_KEY: SecretStr
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = []
    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn

    @model_validator(mode="after")
    def _exiger_un_hote_hors_debug(self) -> Self:
        """Refuse de démarrer en posture de production sans nom d'hôte servi.

        Django l'exige déjà — « When DEBUG is set to False, the ALLOWED_HOSTS setting is
        mandatory » (checklist de déploiement, doc 6.0) — et rejette les requêtes dont l'en-tête
        `Host` est inconnu. Mais ce rejet arrive *à la requête* : le site répond en erreur, ce
        qui se lit comme une panne et non comme une configuration incomplète. Échouer au
        démarrage met le défaut sous les yeux de qui peut le réparer.
        """
        if not self.DEBUG and not self.ALLOWED_HOSTS:
            raise ValueError("ALLOWED_HOSTS est obligatoire quand DEBUG est faux")
        return self
