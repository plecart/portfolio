"""Table de routage racine.

L'admin à `/admin/` (ADR 0001) ; l'API publique arrivera avec #10. Les fichiers téléversés sont
servis par Django en développement seulement : `static()` ne rend aucune route hors `DEBUG`, et
en production ils vivent sur R2 (ADR 0004).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]
