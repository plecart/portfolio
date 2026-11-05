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

La journalisation du worker est celle des réglages (ADR 0027) : branché ici, avant que le worker
ne configure quoi que ce soit, `connect_worker_signals` l'empêche d'y toucher.
"""

import os

from celery import Celery

from config.observability import connect_worker_signals

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Le module `tasks` de chaque application installée, importé quand le worker en a besoin : sans
# lui, le worker ne connaîtrait pas `content.tasks.process_image`.
app.autodiscover_tasks()
connect_worker_signals()
