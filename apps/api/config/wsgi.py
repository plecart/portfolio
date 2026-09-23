"""Point d'entrée WSGI du back.

C'est l'objet que `gunicorn` importe en production (ADR 0001, « Serveur WSGI : `gunicorn` »).
Le projet n'expose pas d'entrée ASGI : l'asynchrone de la phase 2 vivra dans un service séparé
(cadrage §5.2), et un second point d'entrée inutilisé serait du résidu.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
