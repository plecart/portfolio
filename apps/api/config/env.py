"""Lecture de l'environnement du back.

Seul point du projet qui lit l'environnement (cadrage §6.6 « 12-factor, `.env` en développement
seulement », ADR 0001 « Configuration 12-factor : pydantic-settings »). `settings.py` instancie
`Env` une fois et pose chaque réglage Django depuis cette instance ; le reste du code lit
`django.conf.settings`, jamais l'environnement.

Ajouter une variable, c'est ajouter un champ typé ici **et** une ligne dans `.env.example`.
Aucun `os.environ` ailleurs, aucune valeur d'environnement en dur.
"""

from pathlib import Path
from typing import Self

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `env.py` → `config` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Seuil de Django lui-même : son contrôle `security.W009` signale une clé de moins de 50
# caractères. Il ne s'affiche qu'en `manage.py check --deploy`, que la CI ne lance pas — d'où
# ce refus au démarrage, qui, lui, ne peut pas passer inaperçu.
SECRET_KEY_MIN_LENGTH = 50


class Env(BaseSettings):
    """Variables d'environnement du back, validées une fois au démarrage.

    Une variable absente, d'un type faux ou hors de ses bornes fait échouer la construction
    avec une `ValidationError` : l'application refuse de démarrer plutôt que de tourner à
    moitié configurée. La cohérence *interne* d'une adresse de service, en revanche, n'est pas
    vérifiée ici — `PostgresDsn` accepte des URL bien formées mais inexploitables (sans nom de
    base, multi-hôtes) ; c'est `config/database.py` qui les refuse, au moment de les traduire.

    `extra="forbid"` est le défaut de `pydantic-settings` pour le fichier `.env` : une clé
    inconnue y est une faute de frappe, pas une option, et fait échouer le démarrage.

    Attributs :
        SECRET_KEY: clé de signature Django, d'au moins `SECRET_KEY_MIN_LENGTH` caractères.
            Aucun défaut — l'absence est une erreur, jamais une valeur de repli. `SecretStr`
            pour qu'elle n'apparaisse ni dans une trace, ni dans un journal, ni dans une
            sérialisation du modèle (8 formes recensées, les 8 sous test). Une fois déballée
            par `settings.py`, c'est Django qui en répond.
        DEBUG: mode de développement. Faux par défaut : un oubli laisse l'application en
            posture de production, jamais l'inverse.
        ALLOWED_HOSTS: noms d'hôte servis. Obligatoire dès que `DEBUG` est faux.
        DATABASE_URL: adresse du Postgres applicatif (ADR 0005).
        REDIS_URL: adresse du Redis (ADR 0006). Déclarée et validée ici ; son premier lecteur
            (le cache Django) arrive avec #7, et `django-redis` avec lui.
    """

    # Chemin absolu, pas relatif : `manage.py` se lance depuis `apps/api` et les tests depuis
    # la racine du dépôt. Un chemin relatif ferait lire deux fichiers différents.
    model_config = SettingsConfigDict(env_file=REPOSITORY_ROOT / ".env")

    SECRET_KEY: SecretStr = Field(min_length=SECRET_KEY_MIN_LENGTH)
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = []
    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn

    @model_validator(mode="after")
    def _require_allowed_host_outside_debug(self) -> Self:
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
