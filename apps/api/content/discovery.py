"""Les fichiers de découverte du site, que Caddy relaie vers `api` sur l'hôte du site (ADR 0030,
#265) : `/sitemap.xml`, le plan du site au protocole sitemaps 0.9.

Lus dans la base à chaque rendu — une publication s'y voit sans recompilation (ADR 0008) — et dans
l'identité du site que porte le gabarit (`content/site.py`), seule source de l'origine : jamais un
réglage ni la requête, que `django.contrib.sitemaps` lirait.
"""

from collections.abc import Callable
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

from content.api import published_projects
from content.cache import cached_response
from content.models import Project
from content.site import Site, read_template

# L'espace de noms du protocole sitemaps 0.9 (sitemaps.org).
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def sitemap_xml(site: Site, projects: list[Project]) -> str:
    """Le plan du site : l'accueil, daté de la fiche la plus récente — sans date s'il n'y en a
    aucune —, puis chaque fiche de `projects`, datée de sa dernière modification. Les dates sont au
    format W3C (`isoformat`), comme le `dateModified` d'une fiche ; les adresses, échappées pour
    XML."""
    pages = [
        (site.home, max((project.updated_at for project in projects), default=None)),
        *((site.project_url(project.slug), project.updated_at) for project in projects),
    ]
    urls = "".join(
        f"<url><loc>{escape(loc)}</loc>"
        + ("" if updated_at is None else f"<lastmod>{updated_at.isoformat()}</lastmod>")
        + "</url>\n"
        for loc, updated_at in pages
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="{SITEMAP_NS}">\n{urls}</urlset>\n'
    )


def serve(
    request: HttpRequest,
    name: str,
    content_type: str,
    write: Callable[[Site, list[Project]], str],
) -> HttpResponseBase:
    """Le fichier `name` que `write` tire de l'identité du site et des projets publiés, par slug —
    l'ordre de l'API publique —, gardé dans l'espace du contenu sous l'empreinte du gabarit : un
    déploiement qui change l'identité n'est jamais servi depuis l'entrée d'avant.

    Raises:
        LinkPreviewTemplateError: le gabarit est illisible, mal marqué ou sans l'identité du site
            (`read_template`).
    """
    template = read_template(settings.LINK_PREVIEW_TEMPLATE)

    def render() -> HttpResponse:
        projects = list(published_projects().prefetch_related(None))
        return HttpResponse(write(template.site, projects), content_type=content_type)

    return cached_response(request, f"{name}:{template.digest}", render)


# `no-cache` et `require_safe`, comme la fiche (`content/link_preview.py`) : revalidé à chaque
# visite, l'en-tête reposé sur la réponse que sert le cache ; `405` à toute méthode qui ne lit pas.
@require_safe
@cache_control(no_cache=True)
def sitemap(request: HttpRequest) -> HttpResponseBase:
    """`GET /sitemap.xml` : le plan du site (`sitemap_xml`)."""
    return serve(request, "sitemap", "application/xml; charset=utf-8", sitemap_xml)
