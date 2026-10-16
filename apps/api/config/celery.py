"""L'application Celery du back : le moteur du worker d'images (ADR 0015).

Forme prescrite par la documentation Celery, « First steps with Django » : une application par
projet, configurée par les réglages Django sous l'espace de noms `CELERY_` — `CELERY_BROKER_URL`
devient `broker_url`. Ces réglages viennent eux-mêmes d'`Env` (`config/settings.py`) : aucune
valeur d'environnement n'est lue ici.

Deux voies la chargent :

- le démarrage de Django, par `config/__init__.py` : elle devient l'application courante, celle
  qu'une tâche déclarée par `shared_task` emprunte pour s'enfiler depuis `api` ;
- la commande du worker, `celery -A config worker`, qui importe `config` sans passer par
  `manage.py` ni par `config/wsgi.py` : d'où le module de réglages posé par défaut ci-dessous.

Aucun backend de résultats : l'état d'un traitement vit en base, Redis ne transporte que les
messages (ADR 0015, ADR 0006). Les tests la mettent en mode synchrone depuis leur harnais
(`tests/conftest.py`), jamais par un réglage d'ici.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# ponytail: aucune découverte des modules de tâches — il n'en existe aucun. `app.autodiscover_tasks()`
# arrive avec la première tâche (#12, lot 3), sans quoi le worker ne la connaîtrait pas.
app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
