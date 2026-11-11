"""Les fichiers de découverte du site, que Caddy relaie vers `api` sur l'hôte du site (ADR 0030,
#265) : `/sitemap.xml`, le plan du site au protocole sitemaps 0.9, et `/llms.txt`, sa présentation
aux modèles de langage au format de llmstxt.org.

Lus dans la base à chaque rendu — une publication s'y voit sans recompilation (ADR 0008) — et dans
l'identité du site que porte le gabarit (`content/site.py`), seule source de l'origine, du nom, de
la description et des profils de l'auteur : jamais un réglage ni la requête, que
`django.contrib.sitemaps` lirait.
"""

from collections.abc import Callable
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

from content.api import published_projects
from content.cache import View, cached_response
from content.models import Project
from content.site import Site, read_template

# L'espace de noms du protocole sitemaps 0.9 (sitemaps.org).
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Ce qui ouvrirait ou fermerait le texte d'un lien Markdown, échappé par un antislash — `chr(92)`.
LINK_TEXT_ESCAPES = {ord(char): chr(92) + char for char in (chr(92), "[", "]")}

# Le nom d'un profil de l'auteur, par hôte sans `www.` ; l'hôte lui-même pour un autre profil.
PROFILE_NAMES = {"github.com": "GitHub", "linkedin.com": "LinkedIn"}


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


def profile_name(url: str) -> str:
    """Le libellé du profil `url` : son nom s'il est connu (`PROFILE_NAMES`), son hôte sinon."""
    host = (urlsplit(url).hostname or url).removeprefix("www.")
    return PROFILE_NAMES.get(host, host)


def llms_txt(site: Site, projects: list[Project]) -> str:
    """La présentation du site au format de llmstxt.org : le nom de l'auteur en titre et la
    description de l'accueil en citation ; sous `## Projets`, un lien Markdown par fiche de
    `projects`, à son adresse canonique, suivi de son résumé — le titre échappé
    (`LINK_TEXT_ESCAPES`) n'ouvre ni ne ferme le texte du lien — ; sous `## Liens`, les profils de
    l'auteur dans l'ordre du gabarit (`profile_name`)."""
    lines = [
        f"# {site.name}",
        "",
        f"> {site.description}",
        "",
        "## Projets",
        "",
        *(
            f"- [{project.title.translate(LINK_TEXT_ESCAPES)}]"
            f"({site.project_url(project.slug)}): {project.summary}"
            for project in projects
        ),
        "",
        "## Liens",
        "",
        *(f"- [{profile_name(url)}]({url})" for url in site.same_as),
    ]
    return "\n".join(lines) + "\n"


def discovery_view(
    name: str, content_type: str, write: Callable[[Site, list[Project]], str]
) -> View:
    """La vue du fichier de découverte `name`, de type `content_type`, que `write` tire de
    l'identité du site et des projets publiés, par slug — l'ordre de l'API publique.

    La réponse est gardée dans l'espace du contenu sous l'empreinte du gabarit : un déploiement qui
    change l'identité n'est jamais servi depuis l'entrée d'avant. `no-cache` et `require_safe`,
    comme la fiche (`content/link_preview.py`) : revalidée à chaque visite, l'en-tête reposé sur la
    réponse que sert le cache ; `405` à toute méthode qui ne lit pas. La vue lève
    `LinkPreviewTemplateError` si le gabarit est illisible, mal marqué ou sans l'identité du site
    (`read_template`).
    """

    @require_safe
    @cache_control(no_cache=True)
    def view(request: HttpRequest) -> HttpResponseBase:
        template = read_template(settings.LINK_PREVIEW_TEMPLATE)

        def render() -> HttpResponse:
            projects = list(published_projects().prefetch_related(None))
            return HttpResponse(write(template.site, projects), content_type=content_type)

        return cached_response(request, f"{name}:{template.digest}", render)

    return view


# `GET /sitemap.xml` et `GET /llms.txt`.
sitemap = discovery_view("sitemap", "application/xml; charset=utf-8", sitemap_xml)
llms = discovery_view("llms", "text/plain; charset=utf-8", llms_txt)
