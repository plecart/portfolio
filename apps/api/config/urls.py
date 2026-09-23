"""Table de routage racine.

Vide tant qu'aucune brique n'expose d'URL : l'admin et l'API arrivent avec #7. Le module
existe parce que `ROOT_URLCONF` le désigne — Django refuse de démarrer sans lui.
"""

from django.urls import URLPattern, URLResolver

urlpatterns: list[URLPattern | URLResolver] = []
