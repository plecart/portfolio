"""Table de routage racine.

L'admin à `/admin/` (ADR 0001), avec l'aperçu Markdown de ses champs (brief de #8, décision 2) ;
l'API publique à `/api/` (brief de #10, décision 1) — `/projets/*` est la vue des aperçus de lien
sur l'hôte du site (ADR 0011), et l'URLconf ne distingue pas les hôtes. Les fichiers téléversés
sont servis par Django en développement seulement : `static()` ne rend aucune route hors `DEBUG`,
et en production ils vivent sur R2 (ADR 0004).
"""

from content.api import api
from content.link_preview import link_preview
from content.preview import PREVIEW_ROUTE, preview
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, path, re_path

urlpatterns: list[URLPattern | URLResolver] = [
    # Avant les routes de l'admin, dont la dernière attrape toute adresse restante
    # (`AdminSite.catch_all_view`) ; `admin_view` applique à l'aperçu leurs règles : connexion,
    # second facteur compris (`config/apps.py`), CSRF, jamais de cache.
    path("admin/markdown-preview/", admin.site.admin_view(preview), name=PREVIEW_ROUTE),
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    # Toute adresse sous `projets/`, retours à la ligne compris : la vue juge elle-même ce qui suit,
    # et redirige ce qui n'est pas le slug d'un projet publié — jamais un 404 du résolveur (brief
    # de #14, décision 1). Le drapeau `s` est borné au groupe : posé sur tout le motif, `(?s)` fait
    # échouer chaque `reverse` de la table (`normalize`, `django/utils/regex_helper.py`).
    re_path(r"^projets/(?P<slug>(?s:.*))", link_preview),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]
