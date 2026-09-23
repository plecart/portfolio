"""Lecture de l'environnement du back.

Seul point du projet qui lit l'environnement (cadrage §6.6 « 12-factor, `.env` en développement
seulement », ADR 0001 « Configuration 12-factor : pydantic-settings »). `settings.py` instancie
`Env` une fois et pose chaque réglage Django depuis cette instance ; le reste du code lit
`django.conf.settings`, jamais l'environnement.

Ajouter une variable, c'est ajouter un champ typé ici **et** une ligne dans `.env.example`.
Aucun `os.environ` ailleurs, aucune valeur d'environnement en dur.

Une seule exception, ici même : `ENV_FILE`, qui désigne le fichier `.env` et ne peut donc pas y
être déclarée. Elle est résolue par `env_file_path`, à part du modèle.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Self

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Configuration refusée au démarrage — énonce les champs fautifs, jamais leurs valeurs.

    `pydantic` joint la valeur d'entrée à chacun de ses messages d'erreur. C'est commode en
    développement et inacceptable ici : cet environnement porte la clé de signature et le mot
    de passe de la base, et une erreur de démarrage part sur stderr — journaux de conteneur,
    sortie de CI, collecteur d'erreurs. Trois formes ont été mesurées comme fuyantes (borne de
    longueur, URL mal formée, validateur de modèle qui reçoit l'environnement entier) ;
    `Env.load()` les reformule toutes par ce type.
    """


# `env.py` → `config` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Seuil de Django lui-même : son contrôle `security.W009` signale une clé de moins de 50
# caractères. Il ne s'affiche qu'en `manage.py check --deploy`, que la CI ne lance pas — d'où
# ce refus au démarrage, qui, lui, ne peut pas passer inaperçu.
SECRET_KEY_MIN_LENGTH = 50


def env_file_path(environ: Mapping[str, str]) -> Path:
    """Détermine quel fichier `.env` lire, d'après l'environnement donné.

    Args:
        environ: l'environnement du processus, ou n'importe quel dictionnaire — c'est ce qui
            rend cette résolution vérifiable sans toucher au vrai environnement.

    Returns:
        Le `.env` de la racine du dépôt par défaut. `ENV_FILE` permet de viser ailleurs : vers
        un autre fichier, ou vers un chemin inexistant pour n'en lire aucun, ce que
        `pydantic-settings` accepte sans bruit. Un chemin **relatif** est résolu depuis la
        racine du dépôt, jamais depuis le dossier courant : `manage.py` se lance depuis
        `apps/api` et les tests depuis la racine, et laisser le dossier courant décider ferait
        lire deux fichiers différents selon l'appelant — le défaut même que ce chemin absolu
        existe pour éviter.
    """
    demande = environ.get("ENV_FILE")
    if not demande:
        return REPOSITORY_ROOT / ".env"

    chemin = Path(demande)
    return chemin if chemin.is_absolute() else REPOSITORY_ROOT / chemin


# Résolu une fois, au chargement du module : `model_config` est évalué à la création de la
# classe. Poser `ENV_FILE` après cet import n'a donc aucun effet — un sous-processus, oui.
#
# C'est la seule variable d'environnement qui n'a pas de champ dans `Env` ni de ligne dans
# `.env` : c'est elle qui désigne `.env`.
ENV_FILE = env_file_path(os.environ)


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

    model_config = SettingsConfigDict(env_file=ENV_FILE)

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

    @classmethod
    def load(cls) -> Self:
        """Lit l'environnement, ou refuse de démarrer sans citer la moindre valeur.

        C'est le **seul** point d'entrée de la configuration : construire `Env()` directement
        laisse échapper une `ValidationError` de `pydantic`, qui porte les valeurs fautives.

        Returns:
            L'environnement validé.

        Raises:
            ConfigurationError: dès qu'une variable manque, a un type faux, sort de ses bornes
                ou rend l'ensemble incohérent. Le message ne garde que les champs et les motifs.
        """
        try:
            return cls()  # pyright: ignore[reportCallIssue]
        except ValidationError as erreur:
            # `from None` et non `from erreur` : chaîner l'erreur d'origine remettrait les
            # valeurs dans la trace, ce que tout ce mécanisme existe pour éviter.
            raise ConfigurationError(_champs_fautifs(erreur)) from None


def _champs_fautifs(erreur: ValidationError) -> str:
    """Résume une erreur de validation par ses champs et ses motifs, sans aucune valeur."""
    lignes = [
        f"{'.'.join(str(partie) for partie in details['loc']) or '<ensemble>'} : {details['msg']}"
        for details in erreur.errors()
    ]
    return "configuration refusée :\n  " + "\n  ".join(lignes)
