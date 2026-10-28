"""Table de routage racine.

L'admin à `/admin/` (ADR 0001), avec l'aperçu Markdown de ses champs (brief de #8, décision 2) ;
l'API publique à `/api/` (brief de #10, décision 1) — `/projets/*` est la vue des aperçus de lien
sur l'hôte du site (ADR 0011), et l'URLconf ne distingue pas les hôtes. Les fichiers téléversés
sont servis par Django en développement seulement : `static()` ne rend aucune route hors `DEBUG`,
et en production ils vivent sur R2 (ADR 0004). `/favicon.ico` répond sans contenu (`no_icon`).
"""

from http import HTTPStatus

from content.api import api
from content.preview import PREVIEW_ROUTE, preview
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, URLResolver, path


def no_icon(request: HttpRequest) -> HttpResponse:
    """`/favicon.ico`, que le navigateur demande pour toute page de l'admin : l'hôte de l'API n'a
    pas d'icône, et le dit sans le 404 qui s'inscrirait en erreur dans la console de chaque
    écran."""
    return HttpResponse(status=HTTPStatus.NO_CONTENT)


urlpatterns: list[URLPattern | URLResolver] = [
    path("favicon.ico", no_icon),
    # Avant les routes de l'admin, dont la dernière attrape toute adresse restante
    # (`AdminSite.catch_all_view`) ; `admin_view` applique à l'aperçu leurs règles : connexion,
    # second facteur compris (`config/apps.py`), CSRF, jamais de cache.
    path("admin/markdown-preview/", admin.site.admin_view(preview), name=PREVIEW_ROUTE),
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]
