"""Réglages Django du back.

Module ordinaire : il ne lit pas l'environnement lui-même, il pose chaque constante depuis
l'unique instance d'`Env` (`config/env.py`). Aucune valeur d'environnement en dur, ici comme
ailleurs.

Chaque réglage arrive avec la brique qui l'utilise, jamais « au cas où » (ADR 0001, « aucun
résidu du squelette `startproject` »). Ce qui manque encore est délibéré : les en-têtes de
sécurité et la CSP (#6), le cache Redis (#11).
"""

import django_stubs_ext

from config.database import database_settings
from config.env import REPOSITORY_ROOT, Env
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

# Le broker du worker d'images (ADR 0015) : le Redis de l'ADR 0006, rôle 2. L'application Celery
# lit les réglages préfixés `CELERY_` (`config/celery.py`) ; aucun backend de résultats.
CELERY_BROKER_URL = str(env.REDIS_URL)

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# L'admin, seul back-office (ADR 0001) — par sa configuration (`config/apps.py`), qui en fait le
# site à second facteur de `django-otp` (#6) —, et les applications qu'il impose : `auth`,
# `contenttypes`, `sessions`, `messages`. `django_otp` porte le gabarit de la connexion à jeton, sa
# feuille de style et ses traductions ; `otp_totp` et `otp_static`, les deux appareils du second facteur : l'application
# TOTP et les codes de secours. `staticfiles` collecte ses fichiers statiques, que
# WhiteNoise sert (ADR 0014) — en développement aussi : `runserver_nostatic`, placé avant lui,
# retire ce service au `runserver` de Django ; sa configuration
# (`config/apps.py`) écarte les fichiers de `ninja` de la collecte. `ninja` n'est installé que pour
# sa commande `export_openapi_schema` (`make openapi`) : Django ne cherche les commandes de gestion
# que dans les applications installées. `corsheaders` porte ses contrôles de réglages (`manage.py
# check`). `content` porte le contenu du portfolio ; `access`, l'accès à l'admin — ses commandes
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

# WhiteNoise en tête : une requête de fichier statique s'arrête là, sans ouvrir de session. Le
# `SecurityMiddleware` de #6 viendra juste devant lui (doc WhiteNoise, « Enable WhiteNoise »).
# Puis CORS, borné aux routes de l'API (`CORS_URLS_REGEX`) — après WhiteNoise, et non avant comme
# le propose django-cors-headers : aucun fichier statique n'est servi sous `/api/`. Puis le `GET`
# conditionnel : `ETag` d'empreinte du corps et `304` sur `If-None-Match` (cadrage §6.7), pour
# toute réponse qui n'est pas `no-store` — l'admin, en `never_cache`, n'en reçoit pas ; **après**
# CORS, parce que le `304` qu'il construit ne recopie pas `Access-Control-Allow-Origin`
# (`get_conditional_response`, Django 6.1.1), et CORS doit le reposer. Puis les trois que l'admin
# exige (contrôles `admin.E408` à `admin.E410`), plus CSRF (cadrage §6.6) : l'admin protège déjà
# ses propres vues, le middleware étend la protection à toute autre vue. Celui de `django-otp`
# juste après l'authentification, comme sa docstring l'exige (`django_otp/middleware.py`) : il lit
# dans la session l'appareil qui a vérifié l'utilisateur — `request.user.is_verified()`, que le
# site de l'admin consulte.
MIDDLEWARE = [
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

# CORS restreint à l'origine du site (ADR 0008), pour les seules routes de l'API publique : l'admin
# n'a pas vocation à être appelé depuis le site. Un `GET` sans cookie : aucune autre option de
# django-cors-headers n'est nécessaire.
CORS_ALLOWED_ORIGINS = env.CORS_ALLOWED_ORIGINS
CORS_URLS_REGEX = r"^/api/"

# Les gabarits de l'admin vivent dans son application (`APP_DIRS`). Ses processeurs de contexte :
# `auth` et `messages` sont exigés (`admin.E402`, `admin.E404`), `request` alimente sa barre de
# navigation (`admin.W411`).
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
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
