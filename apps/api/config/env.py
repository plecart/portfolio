"""Lecture de l'environnement du back.

Seul point du projet qui lit l'environnement (cadrage §6.6 « 12-factor, `.env` en développement
seulement », ADR 0001 « Configuration 12-factor : pydantic-settings »). `settings.py` appelle
`Env.load()` une fois et pose chaque réglage Django depuis l'instance obtenue ; le reste du code
lit `django.conf.settings`, jamais l'environnement.

Ajouter une variable, c'est ajouter un champ typé ici **et** une ligne dans `.env.example`.
Aucun `os.environ` ailleurs, aucune valeur d'environnement en dur.

Une seule exception, ici même : `ENV_FILE`, qui désigne le fichier `.env` et ne peut donc pas y
être déclarée. Elle est résolue par `env_file_path`, à part du modèle.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

REFUSAL = "configuration refusée :\n  "


class ConfigurationError(RuntimeError):
    """Configuration refusée au démarrage — énonce les champs fautifs, jamais leurs valeurs.

    `pydantic` joint la valeur d'entrée à chacun de ses messages d'erreur. C'est commode en
    développement et inacceptable ici : cet environnement porte la clé de signature et le mot
    de passe de la base, et une erreur de démarrage part sur stderr — journaux de conteneur,
    sortie de CI, collecteur d'erreurs.

    **Six** mécanismes de refus ont été recensés : borne de longueur, URL mal formée,
    validateur de modèle qui reçoit l'environnement entier, validateur de champ qui reçoit la
    liste entière des origines — les quatre fuyaient —, valeur hors de sa liste, dont le message
    énumère les valeurs admises et tait celle reçue, et échec de lecture d'une *source*, qui
    ne fuit pas mais lève un type d'exception distinct. `Env.load()`
    les reformule tous par ce type, et `INVALID_CONFIGURATIONS` (`tests/test_env.py`) en tient
    le dénombrement : c'est le test qui garde la classe close, pas cette phrase.
    """


# `env.py` → `config` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Seuil de Django lui-même : son contrôle `security.W009` signale une clé de moins de 50
# caractères. Il ne s'affiche qu'en `manage.py check --deploy`, que la CI ne lance pas — d'où
# ce refus au démarrage, qui, lui, ne peut pas passer inaperçu.
SECRET_KEY_MIN_LENGTH = 50


def _anchored_path(path: Path) -> Path:
    """Ancre un chemin relatif sur la racine du dépôt.

    `manage.py` se lance depuis `apps/api` et les tests depuis la racine : laisser le dossier
    courant trancher ferait viser deux endroits différents selon l'appelant. Tout chemin que le
    back lit dans l'environnement passe par ici.

    Args:
        path: le chemin tel que l'environnement le donne, relatif ou absolu.

    Returns:
        `path` inchangé s'il est absolu ; sinon le même chemin sous la racine du dépôt.
    """
    return path if path.is_absolute() else REPOSITORY_ROOT / path


# Les variables que le stockage R2 exige non vides (`MEDIA_STORAGE=r2`) ; le disque les ignore.
R2_VARIABLES = (
    "MEDIA_HOST",
    "MEDIA_R2_ENDPOINT",
    "MEDIA_R2_BUCKET",
    "MEDIA_R2_ACCESS_KEY_ID",
    "MEDIA_R2_SECRET_ACCESS_KEY",
)

# Le port que le navigateur tait dans `Origin`, par schéma — et les seuls schémas qu'il y écrit.
DEFAULT_PORTS = {"http": 80, "https": 443}


def _browser_origin(origin: str) -> str | None:
    """La forme sous laquelle un navigateur enverrait `origin` dans l'en-tête `Origin`.

    Args:
        origin: une origine telle que l'environnement la donne.

    Returns:
        `schéma://hôte[:port]` — hôte en minuscules, port seulement s'il n'est pas celui du
        schéma — ou `None` si rien de tel ne se déduit : schéma hors HTTP, hôte absent, port
        illisible. Tout ce qui n'y figure pas (chemin, requête, fragment, identifiant) est perdu,
        ce qui rend une entrée non canonique différente de sa forme canonique. Un hôte IPv6 n'est
        pas rendu entre crochets : une telle origine est refusée.
    """
    parts = urlsplit(origin)
    try:
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in DEFAULT_PORTS or not parts.hostname:
        return None
    suffix = "" if port in (None, DEFAULT_PORTS[parts.scheme]) else f":{port}"
    return f"{parts.scheme}://{parts.hostname}{suffix}"


def env_file_path(environ: Mapping[str, str]) -> Path:
    """Détermine quel fichier `.env` lire, d'après l'environnement donné.

    Args:
        environ: l'environnement du processus, ou n'importe quel dictionnaire — c'est ce qui
            rend cette résolution vérifiable sans toucher au vrai environnement.

    Returns:
        Le `.env` de la racine du dépôt par défaut. `ENV_FILE` permet de viser ailleurs : vers
        un autre fichier, ou vers un chemin inexistant pour n'en lire aucun, ce que
        `pydantic-settings` accepte sans bruit. Un chemin **relatif** est ancré sur la racine du
        dépôt par `_anchored_path`.
    """
    requested = environ.get("ENV_FILE")
    if not requested:
        return REPOSITORY_ROOT / ".env"

    return _anchored_path(Path(requested))


def _faulty_fields(error: ValidationError) -> str:
    """Résume une erreur de validation par ses champs et ses motifs, sans aucune valeur."""
    return "\n  ".join(
        f"{'.'.join(str(part) for part in details['loc']) or '<ensemble>'} : {details['msg']}"
        for details in error.errors()
    )


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
        REDIS_URL: adresse du Redis (ADR 0006), que lisent le broker de l'application Celery
            (ADR 0015, `CELERY_BROKER_URL`) et le cache Django, par `django-redis` (`CACHES`).
        MEDIA_ROOT: dossier où atterrissent les fichiers téléversés (ADR 0004, « Développement :
            stockage disque par défaut de Django »). Le conteneur reçoit le chemin absolu de son
            volume ; sur le poste, un chemin relatif est ancré sur la racine du dépôt.
        MEDIA_STORAGE: le stockage des fichiers téléversés (`config/storage.py`) : `disk`, par
            défaut, sous `MEDIA_ROOT` ; ou `r2`, le bucket public des images sur Cloudflare R2
            (ADR 0004), en production. Toute autre valeur est refusée. Avec `r2`, chacune des
            cinq variables suivantes est exigée non vide (`R2_VARIABLES`) ; le disque les ignore.
        MEDIA_HOST: l'hôte public des fichiers sous `r2`, le CDN devant le bucket : l'adresse
            d'un fichier est `https://<MEDIA_HOST>/<chemin>`.
        MEDIA_R2_ENDPOINT: l'adresse S3 du compte R2, `https://<compte>.r2.cloudflarestorage.com`.
        MEDIA_R2_BUCKET: le nom du bucket public des images, distinct de celui des sauvegardes.
        MEDIA_R2_ACCESS_KEY_ID: l'identifiant du jeton R2 borné à ce bucket, qui doit pouvoir
            le lister — la suppression d'une image liste le dossier de son original.
        MEDIA_R2_SECRET_ACCESS_KEY: le secret de ce jeton, `SecretStr` comme `SECRET_KEY`.
        CORS_ALLOWED_ORIGINS: les origines admises à appeler l'API publique, et en `DEBUG` à
            charger les fichiers téléversés qu'elle sert — celle du site (ADR 0008, « CORS
            restreint à l'origine du site »), liste JSON comme `ALLOWED_HOSTS`.
            Une origine est un schéma et un hôte, rien d'autre ; au moins une, en `DEBUG` aussi :
            le site ne peut pas appeler l'API sans elle.
        ADMIN_USERNAME: le nom de l'unique superutilisateur de l'admin, que la commande
            `ensure_superuser` crée ou met à jour au démarrage d'`api` (`STARTUP_STEPS`,
            `infra/api/entrypoint.sh`).
        ADMIN_PASSWORD: son mot de passe, `SecretStr` comme `SECRET_KEY`. Vides par défaut, comme
            les variables du stockage R2 : le `collectstatic` du build de l'image et `make openapi`
            chargent `Env` sans avoir l'usage du compte. C'est la commande qui refuse un compte
            vide, et Compose qui exige les deux en production.
        LINK_PREVIEW_TEMPLATE: le gabarit du site (ADR 0011) : l'`index.html` du
            front, dont la vue de `/projets/<slug>` remplit les paires marquées pour le projet,
            et qui porte l'identité du site, que lisent aussi `/sitemap.xml` et `/llms.txt`
            (`content/site.py`, #265). Par défaut
            `/app/web/index.html`, où l'image `api` copie la compilation (ADR 0014) ; sur le
            poste, un chemin relatif est ancré sur la racine du dépôt, comme `MEDIA_ROOT`.
        SENTRY_DSN: le DSN du projet Sentry qui reçoit les erreurs de `api` et de `worker`
            (ADR 0027, `config/observability.py`). Vide par défaut, et hors de la production :
            Sentry ne s'initialise pas, rien ne part. `SecretStr` comme `SECRET_KEY` : qui le
            connaît envoie des événements au projet, et en épuise le quota.
    """

    model_config = SettingsConfigDict(env_file=ENV_FILE)

    SECRET_KEY: SecretStr = Field(min_length=SECRET_KEY_MIN_LENGTH)
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = []
    DATABASE_URL: PostgresDsn
    REDIS_URL: RedisDsn
    MEDIA_ROOT: Path = REPOSITORY_ROOT / "media"
    MEDIA_STORAGE: Literal["disk", "r2"] = "disk"
    MEDIA_HOST: str = ""
    MEDIA_R2_ENDPOINT: str = ""
    MEDIA_R2_BUCKET: str = ""
    MEDIA_R2_ACCESS_KEY_ID: str = ""
    MEDIA_R2_SECRET_ACCESS_KEY: SecretStr = SecretStr("")
    CORS_ALLOWED_ORIGINS: list[str] = Field(min_length=1)
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: SecretStr = SecretStr("")
    LINK_PREVIEW_TEMPLATE: Path = Path("/app/web/index.html")
    SENTRY_DSN: SecretStr = SecretStr("")

    @field_validator("MEDIA_ROOT", "LINK_PREVIEW_TEMPLATE")
    @classmethod
    def _anchor_paths(cls, value: Path) -> Path:
        """Ancre un chemin relatif, comme `ENV_FILE` l'est déjà."""
        return _anchored_path(value)

    @field_validator("CORS_ALLOWED_ORIGINS")
    @classmethod
    def _require_browser_origins(cls, origins: list[str]) -> list[str]:
        """Refuse toute origine qui n'est pas écrite comme un navigateur l'enverrait.

        `django-cors-headers` compare l'en-tête `Origin` à chaque entrée, schéma et hôte tels
        quels (`_url_in_whitelist`), et un navigateur l'envoie sous une seule forme :
        `schéma://hôte[:port]`, hôte en minuscules, port absent s'il est celui du schéma. Une
        entrée qui s'en écarte — chemin, identifiant, majuscule, port par défaut écrit — passe
        les contrôles `E013`/`E014` de cors-headers, ou ne les rencontre jamais (`manage.py
        check`, que le conteneur ne lance pas), et laisse le site sans API sans qu'aucune erreur
        ne le dise. D'où le refus au démarrage, comme le reste : l'entrée doit être égale à sa
        forme canonique (`_browser_origin`).

        `list[str]` et non `list[AnyHttpUrl]` : pydantic ajoute un `/` final (mesuré le
        2026-10-15, pydantic 2.13.5 : `https://site.test` → `https://site.test/`), que cors-headers
        lirait comme un chemin.
        """
        if any(_browser_origin(origin) != origin for origin in origins):
            raise ValueError("chaque origine s'écrit `schéma://hôte[:port]`, comme un navigateur")
        return origins

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

    @model_validator(mode="after")
    def _require_r2_variables(self) -> Self:
        """Refuse de démarrer sur R2 sans chacune de ses variables, et nomme celles qui manquent.

        `django-storages` ne joint le bucket qu'au premier fichier (`S3Storage.connection`, créée
        à la demande) : sans ce refus, une variable vide ne se verrait qu'au premier téléversement.
        """
        missing = [name for name in R2_VARIABLES if not getattr(self, name)]
        if self.MEDIA_STORAGE == "r2" and missing:
            raise ValueError(f"MEDIA_STORAGE vaut r2, il manque : {', '.join(missing)}")
        return self

    @classmethod
    def load(cls) -> Self:
        """Lit l'environnement, ou refuse de démarrer sans citer la moindre valeur.

        C'est le **seul** point d'entrée de la configuration : construire `Env()` directement
        laisse échapper une `ValidationError` de `pydantic`, qui porte les valeurs fautives.

        Deux exceptions à rattraper, pas une : `pydantic` valide le modèle, mais
        `pydantic-settings` lit d'abord les *sources*, et une valeur de champ complexe qui n'est
        pas du JSON lisible échoue là, avant toute validation, avec un type propre.

        Returns:
            L'environnement validé.

        Raises:
            ConfigurationError: dès qu'une variable manque, a un type faux, sort de ses bornes,
                rend l'ensemble incohérent, ou n'est pas lisible par sa source. Le message ne
                garde que les champs et les motifs.
        """
        # `from None` et non `from error`, dans les deux branches : chaîner l'erreur d'origine
        # remettrait les valeurs dans la trace, ce que tout ce mécanisme existe pour éviter.
        try:
            return cls()  # pyright: ignore[reportCallIssue]
        except ValidationError as error:
            raise ConfigurationError(REFUSAL + _faulty_fields(error)) from None
        except SettingsError as error:
            # Erreur de source : le message nomme déjà le champ et la source, sans la valeur.
            raise ConfigurationError(REFUSAL + str(error)) from None
