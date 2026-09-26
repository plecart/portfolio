"""Table de routage racine.

L'admin à `/admin/` (ADR 0001) ; l'API publique arrivera avec #10.
"""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
]
