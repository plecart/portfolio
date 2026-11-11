"""Les aperçus de lien des fiches projet, `/projets/<slug>` sur l'hôte du site : une page HTML, que
l'API publique ne rend jamais (ADR 0008, 0009 et 0011 ; brief de #14, décision 7).

Caddy relaie `/projets/*` vers `api`. Pour un projet publié, la vue rend le gabarit du front —
l'`index.html` compilé, `LINK_PREVIEW_TEMPLATE`, lu par `content/site.py` — et en remplit les trois
paires marquées : le bloc d'aperçu `meta` de ses cinq balises, celles que lit un robot d'aperçu
(D53, ADR 0011) ; la paire `page` de son adresse canonique et de son JSON-LD ; la paire `root`,
dans `#root`, de la fiche pré-rendue, masquée à l'œil, qu'un robot lit sans JavaScript (#265). Un
navigateur y charge le site, qui remplace `#root` et affiche la fiche. Toute autre adresse redirige
vers l'accueil (décision 1). La CSP et les en-têtes de sécurité restent ceux de Caddy (décision 5).

La page porte aussi un en-tête `Link` qui précharge l'image de tête de la galerie (`preload_link`,
#27) : le navigateur la demande dès la page reçue, sans attendre le JS ni la liste des projets.
Un en-tête, et non une balise : le bloc d'aperçu s'en tient à ses cinq balises.
"""

import hashlib
import json

from django.conf import settings
from django.core.validators import slug_re
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.utils.html import escape
from django.utils.http import quote_etag
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

from content.cache import cached_response
from content.models import Project, TechnologyKind
from content.schemas import variant_url
from content.site import JSON_LD, Site, read_template

# Le gabarit est en UTF-8, et la page en reprend les octets tels quels.
CONTENT_TYPE = "text/html; charset=utf-8"

# La classe qui masque la fiche pré-rendue à l'œil (`apps/web/src/index.css`) : un robot la lit, un
# visiteur voit la fiche du site, qui la remplace au montage (#265).
PRERENDER_CLASS = "prerender"

# Ce qui fermerait le script d'un JSON-LD ou y ouvrirait un commentaire, échappé dans le JSON en
# séquence Unicode — `chr(92)` est l'antislash — comme le fait `django.utils.html.json_script`
# (`_json_script_escapes`, Django 6.1) : le JSON relu reste le même.
JSON_SCRIPT_ESCAPES = {ord(char): f"{chr(92)}u{ord(char):04X}" for char in "<>&"}

# La largeur de la variante de l'`og:image`, 1200 px (spec §1.11, ADR 0011) : un barreau de
# l'échelle des variantes (`VARIANT_WIDTHS`), découplé du dernier (ADR 0028).
OG_IMAGE_WIDTH = 1200

# L'attribut `sizes` des images de la galerie, recopié de `GALLERY_SIZES`
# (`apps/web/src/project/project.ts`) et épinglé par `apps/web/tests/project.test.ts` : le
# préchargement choisit sa variante dans les mêmes sources, à la même taille, que l'image du site.
GALLERY_SIZES = (
    "(min-width: 600px) min(100vh - 96px, 660px, (100vw - 92px) / 2), calc(100vw - 16px)"
)


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


def preload_link(request: HttpRequest, project: Project) -> str | None:
    """L'en-tête `Link` qui précharge l'image de tête de la galerie de `project` : la première
    image prête, celle que le site montre en premier (`readyImages`,
    `apps/web/src/project/project.ts`) ; `None` sans image prête.

    Prête veut dire qui a des variantes, comme pour le site : une image en attente ou en échec plus
    tôt dans la galerie cède la tête à la suivante — à l'inverse de la couverture (`cover_url`).
    Les sources sont celles que le site lui donne (`imageSources`, `apps/web/src/table/cards.ts`) :
    la première variante, puis chacune dans l'ordre stocké avec sa largeur, aux adresses de l'API
    publique (`variant_url`) — l'image que le site demande ensuite est celle déjà reçue.

    Args:
        request: la requête servie, dont l'origine complète une adresse relative.
        project: le projet de la page.

    Returns:
        L'en-tête, par exemple `<http://testserver/media/images/x/320.webp>; rel=preload; as=image;
        fetchpriority=high; imagesrcset="http://testserver/media/images/x/320.webp 320w, …";
        imagesizes="<GALLERY_SIZES>"` sous le client de test.
    """
    image = project.gallery.exclude(variants=[]).first()
    if image is None:
        return None
    urls = [variant_url({"request": request}, image, variant) for variant in image.variants]
    srcset = ", ".join(
        f"{url} {variant['width']}w" for url, variant in zip(urls, image.variants, strict=True)
    )
    return (
        f"<{urls[0]}>; rel=preload; as=image; fetchpriority=high; "
        f'imagesrcset="{srcset}"; imagesizes="{GALLERY_SIZES}"'
    )


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


def json_ld_script(data: dict[str, object]) -> str:
    """Le script JSON-LD de `data`, `<`, `>` et `&` échappés dans le JSON (`JSON_SCRIPT_ESCAPES`) :
    un `</script>` saisi dans un champ ne clôt pas le script."""
    text = json.dumps(data, ensure_ascii=False).translate(JSON_SCRIPT_ESCAPES)
    return f'<script type="{JSON_LD}">{text}</script>'


def page_tags(project: Project, site: Site, image: str | None) -> bytes:
    """La paire `page` d'une fiche (#265) : son adresse canonique, sous celle de l'accueil, puis son
    JSON-LD — `SoftwareSourceCode` s'il a un dépôt, `CreativeWork` sinon —, son auteur par renvoi
    au `Person` du gabarit et ses technologies en mots-clés.

    Args:
        project: le projet de la page.
        site: l'identité du site, qui donne l'adresse de l'accueil et l'auteur.
        image: l'adresse de l'`og:image` (`cover_url`), ou `None` pour l'omettre.

    Returns:
        Les balises, en UTF-8.
    """
    url = site.project_url(project.slug)
    # Les technologies, puis les outils, chaque groupe dans l'ordre de l'admin — l'ordre de la
    # fiche (`splitStack`, `apps/web/src/project/project.ts`) : le tri est stable.
    technologies = sorted(
        (line.technology for line in project.projecttechnology_set.select_related("technology")),
        key=lambda technology: technology.kind == TechnologyKind.TOOL.value,
    )
    data: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "SoftwareSourceCode" if project.repository_url else "CreativeWork",
        "@id": url,
        "url": url,
        "name": project.title,
        "author": {"@id": site.person},
        "dateCreated": project.started_on.isoformat(),
        "dateModified": project.updated_at.isoformat(),
        "keywords": [technology.name for technology in technologies],
    }
    if image is not None:
        data["image"] = image
    if project.repository_url:
        data["codeRepository"] = project.repository_url
    return f'<link rel="canonical" href="{escape(url)}" />{json_ld_script(data)}'.encode()


def prerender(project: Project) -> bytes:
    """La paire `root` d'une fiche (#265) : la fiche pré-rendue, qu'un robot lit sans JavaScript,
    sous `PRERENDER_CLASS` — le titre en `<h2>`, le résumé, la description, puis chaque section non
    vide, son titre en `<h3>` suivi de son texte, dans l'ordre de l'admin. Le texte est le Markdown
    source échappé, jamais rendu en HTML (ADR 0010).

    Args:
        project: le projet de la page.

    Returns:
        La fiche, en UTF-8.
    """
    # Une section au corps blanc n'est pas montrée, comme sur le site (`visibleSections`).
    # ponytail: `strip()` pour le `trim()` de JS ; ils divergent sur U+FEFF, U+001C à U+001F et
    # U+0085, dont aucun corps saisi n'est fait seul ; une liste commune le jour où l'un l'est.
    sections = [section for section in project.section_set.all() if section.body.strip()]
    texts = [
        f"<h2>{escape(project.title)}</h2>",
        f"<p>{escape(project.summary)}</p>",
        f"<p>{escape(project.description)}</p>",
        *(f"<h3>{escape(section.title)}</h3><p>{escape(section.body)}</p>" for section in sections),
    ]
    return f'<article class="{PRERENDER_CLASS}">{"".join(texts)}</article>'.encode()


# `no-cache`, comme l'`index.html` que Caddy sert : la page cite les fichiers hachés de la
# compilation du moment (décision 5). Autour de la réponse en cache, comme pour la liste
# (`content/api.py`) : l'en-tête se repose sur la page que sert le cache. `require_safe` : la page
# se lit, `405` à toute autre méthode.
@require_safe
@cache_control(no_cache=True)
def link_preview(request: HttpRequest, slug: str) -> HttpResponseBase:
    """`GET /projets/<slug>` : le gabarit, ses paires marquées remplies pour le projet publié
    `slug` — balises d'aperçu (`meta_tags`), adresse canonique et JSON-LD (`page_tags`), fiche
    pré-rendue (`prerender`) —, et l'en-tête qui précharge son image de tête s'il en a une
    (`preload_link`) ; `302 Found` vers `/` sans projet publié à cette adresse (décision 1).

    `slug` est tout ce qui suit `projets/`, une barre finale ôtée : `/projets/<slug>/` est la même
    fiche, comme pour le site (`PROJECT_PATH`, `apps/web/src/project/project.ts`). Ce qui n'a pas
    alors la forme d'un slug (`slug_re`, celle que valide le champ) redirige sans lire ni le
    gabarit ni la base. La page `200`, en-têtes compris, est gardée
    dans l'espace du contenu, vidé à chaque écriture du contenu, sous une clé qui distingue le
    slug, l'origine et l'empreinte du gabarit (décision 4) ; une redirection ne l'est jamais.

    Raises:
        LinkPreviewTemplateError: le gabarit est illisible, mal marqué ou sans l'identité du site
            (`read_template`).
    """
    slug = slug.removesuffix("/")
    if not slug_re.match(slug):
        return HttpResponseRedirect("/")
    template = read_template(settings.LINK_PREVIEW_TEMPLATE)

    def render() -> HttpResponseBase:
        project = Project.objects.filter(slug=slug, published=True).first()
        if project is None:
            return HttpResponseRedirect("/")
        image = cover_url(request, project)
        page = template.fill(
            {
                "meta": meta_tags(project, image),
                "page": page_tags(project, template.site, image),
                "root": prerender(project),
            }
        )
        response = HttpResponse(page, content_type=CONTENT_TYPE)
        if (link := preload_link(request, project)) is not None:
            response["Link"] = link
            # L'`ETag` que poserait `ConditionalGetMiddleware` n'emprunte qu'au corps : un `Link`
            # changé sous un corps inchangé serait validé par un `304`, et le navigateur garderait
            # l'ancien. Le middleware garde un `ETag` déjà posé.
            response["ETag"] = quote_etag(
                hashlib.md5(response.content + link.encode(), usedforsecurity=False).hexdigest()
            )
        return response

    return cached_response(request, f"apercu:{slug}:{template.digest}", render)
