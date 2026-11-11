"""Tests des fichiers de découverte du site (`content/discovery.py`, ADR 0030, #265) :
`/sitemap.xml` liste l'accueil et chaque fiche publiée. Chaque fichier tire l'identité du site du
seul gabarit, suit la base sans rien vider à la main, et est gardé dans l'espace du cache du
contenu sous l'empreinte du gabarit.

Le gabarit est le fichier de fixture de test (`process_environment.py`) : d'autres valeurs que
celles du front.
"""

from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

import pytest
from content.models import Project
from content.site import LinkPreviewTemplateError
from django.test import Client
from factories import project, saved
from pytest_django import DjangoAssertNumQueries, DjangoCaptureOnCommitCallbacks
from test_link_preview import BROKEN_TEMPLATES, UNSAFE_METHODS
from test_site import CANONICAL, SITE, TEMPLATE

SITEMAP = "/sitemap.xml"

# Chaque fichier de découverte : son adresse, puis son type.
DISCOVERY_FILES = {"plan du site": (SITEMAP, "application/xml; charset=utf-8")}
DISCOVERY_PATHS = [path for path, _ in DISCOVERY_FILES.values()]

# Une fiche que chaque fichier liste par son adresse canonique, sous l'accueil du gabarit.
LISTED_SLUG = "listee"
LISTED = f"{SITE.home}projets/{LISTED_SLUG}"

# L'espace de noms du protocole sitemaps 0.9.
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Deux dates de modification, et leur forme W3C : la seconde est la plus récente.
EARLIER = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 3, 8, 30, 15, 500000, tzinfo=UTC)
EARLIER_W3C = "2026-11-01T10:00:00+00:00"
LATER_W3C = "2026-11-03T08:30:15.500000+00:00"


def modified(slug: str, published: bool, updated_at: datetime) -> None:
    """Un projet enregistré sous `slug`, sa date de modification posée à `updated_at` par
    `QuerySet.update`, que `auto_now` ne réécrit pas."""
    saved(
        project(slug=slug, title=slug.capitalize(), summary=f"Résumé {slug}.", published=published)
    )
    Project.objects.filter(slug=slug).update(updated_at=updated_at)


def served(client: Client, path: str) -> tuple[object, ...]:
    """Ce que `client` reçoit du fichier `path` : statut, en-têtes de contenu et de cache, corps."""
    response = client.get(path)
    return (
        response.status_code,
        response["Content-Type"],
        response["Cache-Control"],
        response.content,
    )


def sitemap_entries(client: Client) -> list[tuple[str | None, str | None]]:
    """L'adresse et la date de modification de chaque entrée du plan du site, dans son ordre."""
    root = ElementTree.fromstring(client.get(SITEMAP).content)
    assert root.tag == f"{{{SITEMAP_NS}}}urlset"
    return [
        (url.findtext(f"{{{SITEMAP_NS}}}loc"), url.findtext(f"{{{SITEMAP_NS}}}lastmod"))
        for url in root.findall(f"{{{SITEMAP_NS}}}url")
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "content_type"), DISCOVERY_FILES.values(), ids=DISCOVERY_FILES.keys()
)
def test_un_fichier_de_decouverte_se_revalide_a_chaque_visite(
    client: Client, path: str, content_type: str
) -> None:
    """Son type, et `Cache-Control: no-cache`, comme la fiche : il suit la base."""
    response = client.get(path)

    assert (response.status_code, response["Content-Type"], response["Cache-Control"]) == (
        200,
        content_type,
        "no-cache",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("path", DISCOVERY_PATHS)
@pytest.mark.parametrize("method", UNSAFE_METHODS)
def test_une_methode_qui_ne_lit_pas_est_refusee(client: Client, path: str, method: str) -> None:
    """Seuls `GET` et `HEAD` lisent un fichier de découverte (`require_safe`)."""
    response = client.generic(method, path)

    assert (response.status_code, response.content) == (405, b"")


@pytest.mark.django_db
def test_le_plan_du_site_liste_l_accueil_puis_chaque_fiche_publiee(client: Client) -> None:
    """L'accueil, daté de la fiche la plus récente, puis chaque fiche publiée par slug, à son
    adresse canonique sous l'accueil du gabarit et datée de sa dernière modification (W3C) ; un
    brouillon n'y est pas."""
    modified("zeta", True, EARLIER)
    modified("alpha", True, LATER)
    modified("brouillon", False, LATER)

    assert sitemap_entries(client) == [
        (SITE.home, LATER_W3C),
        (f"{SITE.home}projets/alpha", LATER_W3C),
        (f"{SITE.home}projets/zeta", EARLIER_W3C),
    ]


@pytest.mark.django_db
def test_sans_fiche_publiee_l_accueil_n_a_pas_de_date(client: Client) -> None:
    """Rien n'a de date de modification à prêter à l'accueil."""
    modified("brouillon", False, LATER)

    assert sitemap_entries(client) == [(SITE.home, None)]


@pytest.mark.django_db
def test_les_adresses_du_plan_du_site_sont_echappees_pour_xml(
    client: Client, template: Path
) -> None:
    """Une adresse d'accueil à `&`, que le gabarit écrit `&amp;` : le XML se lit, l'adresse
    intacte."""
    template.write_bytes(
        TEMPLATE.replace(
            CANONICAL, b'<link rel="canonical" href="https://site.test/?a=1&amp;b=2" />'
        )
    )

    assert sitemap_entries(client) == [("https://site.test/?a=1&b=2", None)]


@pytest.mark.django_db
@pytest.mark.parametrize("path", DISCOVERY_PATHS)
def test_une_fiche_depubliee_sort_du_fichier_suivant(
    client: Client, path: str, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """Dépublier, une écriture du modèle comme celle de l'admin, vide l'espace du contenu : la
    réponse suivante ne liste plus la fiche, sans recompilation ni rien vider à la main."""
    listed = saved(project(slug=LISTED_SLUG, published=True))
    before = client.get(path).content.decode()

    with django_capture_on_commit_callbacks(execute=True):
        listed.published = False
        listed.save()

    after = client.get(path).content.decode()
    assert (LISTED in before, LISTED in after) == (True, False)


@pytest.mark.django_db
@pytest.mark.parametrize("path", DISCOVERY_PATHS)
def test_la_seconde_requete_est_servie_par_le_cache(
    client: Client, path: str, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    """Gardé dans l'espace du contenu (ADR 0006) : la seconde requête est servie sans une requête
    en base, à l'identique, `no-cache` compris."""
    saved(project(slug=LISTED_SLUG, published=True))
    from_base = served(client, path)

    with django_assert_num_queries(0):
        from_cache = served(client, path)

    assert from_cache == from_base


@pytest.mark.django_db
@pytest.mark.parametrize("path", DISCOVERY_PATHS)
def test_un_gabarit_change_n_est_jamais_servi_depuis_l_entree_de_l_ancien(
    client: Client, template: Path, path: str
) -> None:
    """Même génération, un autre gabarit — un déploiement qui change l'adresse de l'accueil : la
    clé porte l'empreinte du gabarit, et le fichier suit le nouveau."""
    saved(project(slug=LISTED_SLUG, published=True))
    template.write_bytes(TEMPLATE)
    client.get(path)

    template.write_bytes(
        TEMPLATE.replace(CANONICAL, b'<link rel="canonical" href="https://autre.test/" />')
    )

    assert f"https://autre.test/projets/{LISTED_SLUG}" in client.get(path).content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("path", DISCOVERY_PATHS)
@pytest.mark.parametrize("content", BROKEN_TEMPLATES.values(), ids=BROKEN_TEMPLATES.keys())
def test_un_gabarit_defectueux_est_une_erreur_journalisee_jamais_un_fichier(
    template: Path, caplog: pytest.LogCaptureFixture, path: str, content: bytes | None
) -> None:
    """Introuvable, mal marqué ou sans l'identité du site : `500`, comme la fiche, et l'erreur,
    qui nomme le gabarit, est journalisée par Django — jamais une adresse devinée."""
    if content is not None:
        template.write_bytes(content)

    response = Client(raise_request_exception=False).get(path)

    errors = [record.exc_info[1] for record in caplog.records if record.exc_info]
    assert response.status_code == 500
    assert [type(error) for error in errors] == [LinkPreviewTemplateError]
    assert str(template) in str(errors[0])
