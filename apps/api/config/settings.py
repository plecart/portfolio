"""Réglages Django du back.

Module ordinaire : il ne lit pas l'environnement lui-même, il pose chaque constante depuis
l'unique instance d'`Env` (`config/env.py`). Aucune valeur d'environnement en dur, ici comme
ailleurs.

Chaque réglage arrive avec la brique qui l'utilise, jamais « au cas où » (ADR 0001, « aucun
résidu du squelette `startproject` »).
"""

import django_stubs_ext
from django.utils.csp import CSP

from config.database import database_settings
from config.env import REPOSITORY_ROOT, Env
from config.observability import configure_logging
from config.storage import media_storage

# Rend indexables à l'exécution les classes que django-stubs déclare génériques
# (`admin.ModelAdmin[Technology]`, `models.CharField[str, str]`) : c'est ce que pyright strict
# exige pour typer modèles et admin, et la voie que django-stubs documente.
django_stubs_ext.monkeypatch()

# Une seule lecture de l'environnement pour tout le processus : Django importe ce module une
# fois. `load()` et non `Env()` — c'est lui qui empêche une configuration refusée de recracher
# la clé de signature et le mot de passe de la base dans la trace de démarrage.
env = Env.load()

SECRET_KEY = env.SECRET_KEY.get_secret_value()
DEBUG = env.DEBUG
ALLOWED_HOSTS = env.ALLOWED_HOSTS

# La journalisation, posée ici une fois pour `api` comme pour `worker`, qui charge ces réglages
# (ADR 0027, `config/observability.py`) : une ligne JSON par événement en production, un rendu
# lisible en développement. `LOGGING_CONFIG = None` retire la configuration par défaut de Django,
# qui ajouterait son propre rendu aux loggers `django` en développement (`DEFAULT_LOGGING`) — la
# voie que la doc Django donne pour configurer soi-même (« Disabling logging configuration »).
LOGGING_CONFIG = None
configure_logging(debug=DEBUG)

# Cloudflare termine le TLS, `cloudflared` puis Caddy relaient en HTTP, et Caddy ne transmet
# `X-Forwarded-Proto` que depuis le réseau privé (`infra/caddy/Caddyfile`) : Django y lit le schéma
# du visiteur — sans quoi il voit `http`, et sa vérification d'origine du CSRF refuse les
# formulaires de l'admin. Ni redirection vers HTTPS ni HSTS : `.dev`, en HSTS préchargé, impose
# HTTPS dès le navigateur (ADR 0003). Les cookies de session et du jeton CSRF ne partent que sur
# HTTPS, hors du poste de développement.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# La CSP des réponses des vues, taillée pour l'admin (ADR 0020) : ses scripts et ses styles, ceux
# du projet compris, viennent de l'origine ou portent le nonce de la requête, que ses gabarits
# posent (`{% csp_nonce_attr %}`) ; aucun `unsafe-inline`, aucune source tierce, sauf l'hôte des
# médias sous R2, où pointent ses aperçus d'images. La requête de l'aperçu Markdown (`connect-src`)
# retombe sur `default-src`. Les quatre dernières directives sont posées à part : `base-uri`,
# `form-action` et `frame-ancestors` n'y retombent pas, et `object-src` y vaudrait `'self'`.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.NONCE],
    "img-src": [CSP.SELF, f"https://{env.MEDIA_HOST}"] if env.MEDIA_STORAGE == "r2" else [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

# L'unique superutilisateur de l'admin, que pose `manage.py ensure_superuser` (`access`). Le mot de
# passe reste un `SecretStr`, que seule la commande déballe : `manage.py diffsettings` l'affiche
# `SecretStr('**********')` (mesuré le 2026-10-28).
ADMIN_USERNAME = env.ADMIN_USERNAME
ADMIN_PASSWORD = env.ADMIN_PASSWORD

# Les quatre validateurs que `startproject` pose (`django/conf/project_template`) — le défaut de
# Django est une liste vide, qui n'en fait tourner aucun : similarité au nom, longueur minimale,
# mots de passe courants, entièrement numérique. La longueur passe des 8 de son défaut à 12 (PR
# #181) : le « mot de passe fort » de l'admin (cadrage §6.2), qu'`ensure_superuser` y soumet.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

DATABASES = {"default": database_settings(env.DATABASE_URL)}

# Le stockage des fichiers téléversés, choisi par `MEDIA_STORAGE` (ADR 0004, `config/storage.py`) :
# le disque, sous `MEDIA_ROOT`, et ses fichiers servis sous `MEDIA_URL` — par Django lui-même en
# développement seulement (`config/urls.py`) ; ou R2, dont les adresses sont sur `MEDIA_HOST`.
MEDIA_ROOT = env.MEDIA_ROOT
MEDIA_URL = "media/"

# Le gabarit des aperçus de lien (ADR 0011, `content/link_preview.py`) : l'`index.html` du front,
# relu à chaque requête de `/projets/<slug>`.
LINK_PREVIEW_TEMPLATE = env.LINK_PREVIEW_TEMPLATE

# Le broker du worker d'images (ADR 0015) : le Redis de l'ADR 0006, rôle 2. L'application Celery
# lit les réglages préfixés `CELERY_` (`config/celery.py`) ; aucun backend de résultats.
CELERY_BROKER_URL = str(env.REDIS_URL)

# Le cache du contenu (ADR 0006, rôle 1 ; `content/cache.py`), dans le même Redis que le broker.
# Chaque clé expire après `TIMEOUT` secondes. C'est un filet, pas le mécanisme : chaque écriture
# du contenu vide le cache ; les 300 s bornent la fraîcheur d'une écriture qui échapperait aux
# signaux — `QuerySet.update`, `bulk_create`/`bulk_update`, SQL brut, migration de données (brief
# de #11, décision 5 ; ADR 0006, « TTL courts »). Aucune clé du cache sans durée de vie : sous `volatile-lru`, les clés à durée de
# vie sont les seules que Redis évince, et la file du broker n'en a pas (ADR 0015). Redis
# injoignable ou muet : une connexion abandonne après 0,2 s, une réponse attendue aussi — sans ces
# délais, la connexion attendrait celui du système, la réponse sans fin (redis-py 6.4) ;
# l'exception est ignorée et journalisée (logger `django_redis.cache`), et la liste vient de la
# base (décision 7).
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": str(env.REDIS_URL),
        "TIMEOUT": 300,
        "OPTIONS": {
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_CONNECT_TIMEOUT": 0.2,
            "SOCKET_TIMEOUT": 0.2,
        },
    }
}
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# L'admin, seul back-office (ADR 0001) — par sa configuration (`config/apps.py`), qui en fait le
# site à second facteur de `django-otp` (#6) —, et les applications qu'il impose : `auth`,
# `contenttypes`, `sessions`, `messages`. `django_otp` porte le gabarit de la connexion à jeton, sa
# feuille de style et ses traductions ; `otp_totp` et `otp_static`, les deux appareils du second
# facteur : l'application TOTP et les codes de secours. `staticfiles` collecte ses fichiers
# statiques, que WhiteNoise sert (ADR 0014) — en développement aussi : `runserver_nostatic`, placé
# avant lui, retire ce service au `runserver` de Django ; sa configuration (`config/apps.py`)
# écarte les fichiers de `ninja` de la collecte. `ninja` n'est installé que pour sa commande
# `export_openapi_schema` (`make openapi`) : Django ne cherche les commandes de gestion que dans les
# applications installées. `corsheaders` porte ses contrôles de réglages (`manage.py check`).
# `content` porte le contenu du portfolio ; `access`, l'accès à l'admin — ses commandes
# `ensure_superuser` et `enroll_second_factor`, et le retrait des écrans de comptes et d'appareils,
# qui la veut après `auth`, `otp_totp` et `otp_static` : l'autodécouverte des modules `admin` suit
# cet ordre.
INSTALLED_APPS = [
    "config.apps.AdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "whitenoise.runserver_nostatic",
    "config.apps.StaticFilesConfig",
    "ninja",
    "corsheaders",
    "content",
    "access",
]

# L'identifiant de corrélation en tête (ADR 0027, `config/observability.py`) : tout ce que
# journalise une requête le porte, jusqu'aux refus des middlewares qui le suivent ; il n'ouvre ni
# session ni utilisateur. Puis `SecurityMiddleware`, juste devant WhiteNoise (doc WhiteNoise,
# « Enable WhiteNoise ») : ses en-têtes — `nosniff`, `Referrer-Policy` et `Cross-Origin-Opener-Policy`, aux défauts de
# Django — couvrent aussi les fichiers statiques. Puis WhiteNoise : une requête de fichier statique
# s'arrête là, sans ouvrir de session. Puis CORS, borné aux routes de l'API (`CORS_URLS_REGEX`) —
# après WhiteNoise, et non avant comme le propose django-cors-headers : aucun fichier statique
# n'est servi sous `/api/`. Puis le `GET` conditionnel : `ETag` d'empreinte du corps et `304` sur
# `If-None-Match` (cadrage §6.7), pour toute réponse qui n'est pas `no-store` — l'admin, en
# `never_cache`, n'en reçoit pas ; **après** CORS, parce que le `304` qu'il construit ne recopie pas
# `Access-Control-Allow-Origin` (`get_conditional_response`, Django 6.1.1), et CORS doit le
# reposer. Puis les trois que l'admin exige (contrôles `admin.E408` à `admin.E410`), plus CSRF
# (cadrage §6.6) : l'admin protège déjà ses propres vues, le middleware étend la protection à toute
# autre vue. Celui de `django-otp` juste après l'authentification, que sa docstring exige avant lui
# (`django_otp/middleware.py`) : il lit dans la session l'appareil qui a vérifié l'utilisateur —
# `request.user.is_verified()`, que le site de l'admin consulte. La CSP en dernier (`SECURE_CSP`) :
# elle pose le nonce de la requête avant la vue, et un middleware qui le lirait se placerait après
# elle — aucun ne le lit.
MIDDLEWARE = [
    "config.observability.correlation_middleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

# CORS restreint à l'origine du site (ADR 0008), pour les seules routes de l'API publique : l'admin
# n'a pas vocation à être appelé depuis le site. Un `GET` sans cookie : aucune autre option de
# django-cors-headers n'est nécessaire.
CORS_ALLOWED_ORIGINS = env.CORS_ALLOWED_ORIGINS
CORS_URLS_REGEX = r"^/api/"

# Les gabarits de l'admin vivent dans son application (`APP_DIRS`). Ses processeurs de contexte :
# `auth` et `messages` sont exigés (`admin.E402`, `admin.E404`), `request` alimente sa barre de
# navigation (`admin.W411`), `csp` donne à ses balises le nonce de la requête
# (`{% csp_nonce_attr %}`).
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
            ],
        },
    },
]

# Exigé par `staticfiles`, qui refuse de démarrer sans lui : le défaut de Django est `None`.
STATIC_URL = "static/"

# Les fichiers statiques sont collectés au build de l'image (`/app/static`), jamais dans le
# dépôt : sur le poste, WhiteNoise les lit à la source (`DEBUG`), et les tests les collectent dans
# un dossier temporaire (ADR 0014). Le stockage ajoute à chaque nom l'empreinte de son contenu et
# en garde une copie compressée : le navigateur conserve un fichier indéfiniment, et une nouvelle
# version change de nom. Il refuse aussi de rendre une page qui cite un fichier absent de la
# collecte. `default` est celui des fichiers téléversés, ci-dessus.
STATIC_ROOT = REPOSITORY_ROOT / "static"
STORAGES = {
    "default": media_storage(env),
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Contenu en français seulement, sans plomberie multilingue (cadrage §3) : `LANGUAGE_CODE`
# traduit les écrans et messages propres à Django. Heure de Paris : le défaut de Django est
# `America/Chicago`.
LANGUAGE_CODE = "fr"
TIME_ZONE = "Europe/Paris"
