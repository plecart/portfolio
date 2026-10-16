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

DATABASES = {"default": database_settings(env.DATABASE_URL)}

# Stockage disque en développement (ADR 0004) ; R2 arrive avec #13, par un backend de fichiers,
# sans toucher aux modèles. Les fichiers sont servis sous `MEDIA_URL` — par Django lui-même en
# développement seulement (`config/urls.py`).
MEDIA_ROOT = env.MEDIA_ROOT
MEDIA_URL = "media/"

# Le broker du worker d'images (ADR 0015) : le Redis de l'ADR 0006, rôle 2. L'application Celery
# lit les réglages préfixés `CELERY_` (`config/celery.py`) ; aucun backend de résultats.
CELERY_BROKER_URL = str(env.REDIS_URL)

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# L'admin, seul back-office (ADR 0001), et les applications qu'il impose : `auth`,
# `contenttypes`, `sessions`, `messages`. `staticfiles` collecte ses fichiers statiques, que
# WhiteNoise sert (ADR 0014) — en développement aussi : `runserver_nostatic`, placé avant lui,
# retire ce service au `runserver` de Django ; sa configuration
# (`config/apps.py`) écarte les fichiers de `ninja` de la collecte. `ninja` n'est installé que pour
# sa commande `export_openapi_schema` (`make openapi`) : Django ne cherche les commandes de gestion
# que dans les applications installées. `corsheaders` porte ses contrôles de réglages (`manage.py
# check`). `content` porte le contenu du portfolio.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "config.apps.StaticFilesConfig",
    "ninja",
    "corsheaders",
    "content",
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
# ses propres vues, le middleware étend la protection à toute autre vue.
MIDDLEWARE = [
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
# collecte. `default` reste celui de Django : les fichiers téléversés, sous `MEDIA_ROOT`.
STATIC_ROOT = REPOSITORY_ROOT / "static"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Contenu en français seulement, sans plomberie multilingue (cadrage §3) : `LANGUAGE_CODE`
# traduit les écrans et messages propres à Django. Heure de Paris : le défaut de Django est
# `America/Chicago`.
LANGUAGE_CODE = "fr"
TIME_ZONE = "Europe/Paris"
