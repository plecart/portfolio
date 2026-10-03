"""Table de routage racine.

L'admin à `/admin/` (ADR 0001), avec l'aperçu Markdown de ses champs (brief de #8, décision 2) ;
l'API publique arrivera avec #10. Les fichiers téléversés sont servis par Django en développement
seulement : `static()` ne rend aucune route hors `DEBUG`, et en production ils vivent sur R2 (ADR
0004).
"""

from content.preview import PREVIEW_ROUTE, preview
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, path

urlpatterns: list[URLPattern | URLResolver] = [
    # Avant les routes de l'admin, dont la dernière attrape toute adresse restante
    # (`AdminSite.catch_all_view`) ; `admin_view` applique à l'aperçu leurs règles : connexion,
    # CSRF, jamais de cache.
    path("admin/markdown-preview/", admin.site.admin_view(preview), name=PREVIEW_ROUTE),
    path("admin/", admin.site.urls),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]
