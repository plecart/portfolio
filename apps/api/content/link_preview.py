"""Les aperçus de lien des fiches projet, `/projets/<slug>` sur l'hôte du site : une page HTML, que
l'API publique ne rend jamais (ADR 0008, 0009 et 0011 ; brief de #14, décision 7).

Caddy relaie `/projets/*` vers `api`. Pour un projet publié, la vue rend le gabarit du front —
l'`index.html` compilé, `LINK_PREVIEW_TEMPLATE` — dont le bloc marqué porte les balises du projet,
celles que lit un robot d'aperçu ; un navigateur y charge le site, qui affiche la fiche. Toute
autre adresse redirige vers l'accueil (décision 1). La CSP et les en-têtes de sécurité restent
ceux de Caddy (décision 5).
"""

import hashlib
from pathlib import Path
from typing import NamedTuple

from django.conf import settings
from django.core.validators import slug_re
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.utils.html import escape
from django.views.decorators.cache import cache_control

from content.cache import cached_response
from content.models import Project
from content.schemas import variant_url
from content.variants import VARIANT_WIDTHS

# Les deux marqueurs du bloc d'aperçu, chacun une fois dans le gabarit compilé
# (`docs/frontend-outillage.md` §2.4) : la vue remplace ce qui est entre eux, et les garde.
START = b"<!--meta:start-->"
END = b"<!--meta:end-->"

# Le gabarit est en UTF-8, et la page en reprend les octets tels quels.
CONTENT_TYPE = "text/html; charset=utf-8"

# La largeur de la variante de l'`og:image` : le dernier barreau de l'échelle, 1200 px (spec §1.11,
# ADR 0011).
OG_IMAGE_WIDTH = VARIANT_WIDTHS[-1]


class LinkPreviewTemplateError(RuntimeError):
    """Le gabarit est illisible, ou n'a pas ses deux marqueurs une fois chacun, dans l'ordre
    (décision 8). Levée par la vue, journalisée par Django (`django.request`) avec sa trace et
    rendue en `500` : jamais une page servie sans les balises du projet."""


class Template(NamedTuple):
    """Le gabarit, découpé autour de son bloc marqué."""

    head: bytes
    """Jusqu'au marqueur de début compris."""
    tail: bytes
    """Depuis le marqueur de fin compris."""
    digest: str
    """L'empreinte SHA-256 du fichier entier."""


def read_template(path: Path) -> Template:
    """Lit et découpe le gabarit `path`, relu à chaque appel : rien ne garde un gabarit qu'un
    déploiement a remplacé.

    Args:
        path: le gabarit, `LINK_PREVIEW_TEMPLATE`.

    Returns:
        Le gabarit découpé, octets tels quels : aucun décodage, aucune fin de ligne réécrite.

    Raises:
        LinkPreviewTemplateError: le fichier ne se lit pas, ou n'a pas exactement un marqueur de
            début suivi d'un marqueur de fin ; le message nomme le fichier.
    """
    try:
        content = path.read_bytes()
    except OSError as error:
        raise LinkPreviewTemplateError(f"gabarit des aperçus de lien illisible : {path}") from error
    starts, ends = content.count(START), content.count(END)
    if (starts, ends) != (1, 1) or content.index(START) > content.index(END):
        raise LinkPreviewTemplateError(
            f"le gabarit des aperçus de lien {path} doit porter {START.decode()} puis "
            f"{END.decode()}, une fois chacun ; il en porte {starts} et {ends}"
        )
    head, _, rest = content.partition(START)
    tail = rest.partition(END)[2]
    return Template(head + START, END + tail, hashlib.sha256(content).hexdigest())


def cover_url(request: HttpRequest, project: Project) -> str | None:
    """L'adresse absolue de la variante de 1200 px de la couverture de `project`, calculée comme
    celles de l'API publique (décision 3) ; `None` sans couverture prête (décision 2).

    La couverture est la première image de la galerie. Seule une image prête a des variantes
    (contrainte `content_galleryimage_variants_ready`) : une première image en attente ou en
    échec n'en a aucune, et une image prête plus loin n'en tient pas lieu.

    Args:
        request: la requête servie, dont l'origine complète une adresse relative.
        project: le projet de la page.

    Returns:
        L'adresse, par exemple `http://testserver/media/images/x/1200.webp` sous le client de
        test ; `None` aussi pour une couverture prête sans variante de 1200 px, que l'admin
        refuse.
    """
    cover = project.gallery.first()
    if cover is None:
        return None
    variant = next((v for v in cover.variants if v["width"] == OG_IMAGE_WIDTH), None)
    if variant is None:
        return None
    return variant_url({"request": request}, cover, variant)


def meta_tags(project: Project, image: str | None) -> bytes:
    """Les balises du bloc marqué (ADR 0011) : le titre dans `<title>` et `og:title`, le résumé
    dans `description` et `og:description`, et l'`og:image` s'il y a une `image`. Chaque valeur
    est échappée pour HTML, texte comme attribut (décision 6).

    Args:
        project: le projet de la page.
        image: l'adresse de l'`og:image` (`cover_url`), ou `None` pour l'omettre.

    Returns:
        Les balises, en UTF-8.
    """
    title, summary = escape(project.title), escape(project.summary)
    tags = [
        f"<title>{title}</title>",
        f'<meta name="description" content="{summary}" />',
        f'<meta property="og:title" content="{title}" />',
        f'<meta property="og:description" content="{summary}" />',
    ]
    if image is not None:
        tags.append(f'<meta property="og:image" content="{escape(image)}" />')
    return "".join(tags).encode()


# `no-cache`, comme l'`index.html` que Caddy sert : la page cite les fichiers hachés de la
# compilation du moment (décision 5). Autour de la réponse en cache, comme pour la liste
# (`content/api.py`) : l'en-tête se repose sur la page que sert le cache.
@cache_control(no_cache=True)
def link_preview(request: HttpRequest, slug: str) -> HttpResponseBase:
    """`GET /projets/<slug>` : le gabarit, son bloc marqué remplacé par les balises du projet
    publié `slug` ; `302 Found` vers `/` sans projet publié à cette adresse (décision 1).

    `slug` est tout ce qui suit `projets/` : ce qui n'a pas la forme d'un slug (`slug_re`, celle
    que valide le champ) redirige sans lire ni le gabarit ni la base. La page `200` est gardée
    dans l'espace du contenu, vidé à chaque écriture du contenu, sous une clé qui distingue le
    slug, l'origine et l'empreinte du gabarit (décision 4) ; une redirection ne l'est jamais.

    Raises:
        LinkPreviewTemplateError: le gabarit est illisible ou mal marqué (`read_template`).
    """
    if not slug_re.match(slug):
        return HttpResponseRedirect("/")
    template = read_template(settings.LINK_PREVIEW_TEMPLATE)

    def render() -> HttpResponseBase:
        project = Project.objects.filter(slug=slug, published=True).first()
        if project is None:
            return HttpResponseRedirect("/")
        block = meta_tags(project, cover_url(request, project))
        return HttpResponse(template.head + block + template.tail, content_type=CONTENT_TYPE)

    return cached_response(request, f"apercu:{slug}:{template.digest}", render)
