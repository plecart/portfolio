"""Réglages Django du back.

Module ordinaire : il ne lit pas l'environnement lui-même, il pose chaque constante depuis
l'unique instance d'`Env` (`config/env.py`). Aucune valeur d'environnement en dur, ici comme
ailleurs.

Ce que ce fichier **ne contient pas** est délibéré (ADR 0001, « aucun résidu du squelette
`startproject` ») : ni application, ni middleware, ni gabarit, ni fichiers statiques, ni
internationalisation. Chacun arrive avec la brique qui l'utilise, jamais « au cas où ».
"""

from config.database import reglages_postgres
from config.env import Env

# Une seule lecture de l'environnement pour tout le processus : Django importe ce module une
# fois. Le commentaire `pyright: ignore` est le contournement documenté par `pydantic-settings`
# pour les champs sans défaut, résolus depuis l'environnement et non depuis l'appel.
env = Env()  # pyright: ignore[reportCallIssue]

SECRET_KEY = env.SECRET_KEY.get_secret_value()
DEBUG = env.DEBUG
ALLOWED_HOSTS = env.ALLOWED_HOSTS

DATABASES = {"default": reglages_postgres(env.DATABASE_URL)}

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ponytail: aucune application ni middleware tant qu'aucune requête n'est servie. L'admin, ses
# dépendances imposées (auth, contenttypes, sessions, messages — ADR 0001) et les middlewares
# de sécurité arrivent avec #7, première brique qui expose une URL.
INSTALLED_APPS: list[str] = []
MIDDLEWARE: list[str] = []
