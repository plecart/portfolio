"""Réglages Django du back.

Module ordinaire : il ne lit pas l'environnement lui-même, il pose chaque constante depuis
l'unique instance d'`Env` (`config/env.py`). Aucune valeur d'environnement en dur, ici comme
ailleurs.

Chaque réglage arrive avec la brique qui l'utilise, jamais « au cas où » (ADR 0001, « aucun
résidu du squelette `startproject` »). Ce qui manque encore est délibéré : les en-têtes de
sécurité et la CSP (#6), le cache Redis (#11).
"""

from config.database import database_settings
from config.env import Env

# Une seule lecture de l'environnement pour tout le processus : Django importe ce module une
# fois. `load()` et non `Env()` — c'est lui qui empêche une configuration refusée de recracher
# la clé de signature et le mot de passe de la base dans la trace de démarrage.
env = Env.load()

SECRET_KEY = env.SECRET_KEY.get_secret_value()
DEBUG = env.DEBUG
ALLOWED_HOSTS = env.ALLOWED_HOSTS

DATABASES = {"default": database_settings(env.DATABASE_URL)}

# Stockage disque en développement (ADR 0004) ; R2 arrive avec #13, par un backend de fichiers,
# sans toucher aux modèles. `MEDIA_URL` n'est pas posé : rien ne sert encore de fichier.
MEDIA_ROOT = env.MEDIA_ROOT

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# L'admin, seul back-office (ADR 0001), et les applications qu'il impose : `auth`,
# `contenttypes`, `sessions`, `messages`. `staticfiles` sert son CSS en développement.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

# Les trois que l'admin exige (contrôles `admin.E408` à `admin.E410`), plus CSRF (cadrage §6.6) :
# l'admin protège déjà ses propres vues, le middleware étend la protection à toute autre vue.
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

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

STATIC_URL = "static/"

# Contenu en français seulement, sans plomberie multilingue (cadrage §3) : `LANGUAGE_CODE`
# traduit les écrans et messages propres à Django. Heure de Paris : le défaut de Django est
# `America/Chicago`.
LANGUAGE_CODE = "fr"
TIME_ZONE = "Europe/Paris"
