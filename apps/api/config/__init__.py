"""Le projet Django du back.

L'application Celery est importée ici pour être chargée au démarrage de Django, comme la
documentation Celery le prescrit (« First steps with Django ») : sans cet import, une tâche
enfilée par `api` partirait vers le broker par défaut de Celery, pas vers `REDIS_URL`.
"""

from config.celery import app as celery_app

__all__ = ["celery_app"]
