"""Tests des aperçus de lien des fiches projet : `/projets/<slug>` rend le gabarit du front, son
bloc marqué remplacé par les balises du projet publié, ou redirige vers l'accueil ; la page rendue
est gardée dans l'espace du cache du contenu ; un gabarit défectueux est une erreur, jamais une page
sans balises ; et l'API publique ne répond jamais en HTML (brief de #14, décisions 1 à 8).

Le gabarit est un fichier de fixture de test, que désigne l'environnement de test
(`process_environment.py`) — jamais l'`index.html` du front.
"""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from content.api import api
from content.link_preview import LinkPreviewTemplateError, meta_tags
from content.models import ProcessingState, Project
from django.test import Client, override_settings
from factories import gallery_image, project, saved
from pytest_django import DjangoAssertNumQueries, DjangoCaptureOnCommitCallbacks
from test_cache import OTHER_ORIGINS
from test_markdown_preview import tags

# Le gabarit de fixture de test : la forme de l'`index.html` compilé du front.
TEMPLATE = Path(__file__).with_name("gabarit-apercu.html").read_bytes()

# Les deux fins de ligne qu'un gabarit peut porter : LF, celle du dépôt, et CRLF, celle d'une copie
# de travail Windows sous `core.autocrlf` (`.gitattributes`).
LINE_ENDINGS = {"LF": b"\n", "CRLF": b"\r\n"}

# Le gabarit d'une autre compilation : d'autres octets hors du bloc marqué.
DEPLOYED = TEMPLATE + b"<!-- La compilation suivante. -->"

# Les deux marqueurs du bloc, écrits ici sans les lire dans le module de la vue.
START = b"<!--meta:start-->"
END = b"<!--meta:end-->"

# Le projet publié du brief : un titre qui casserait le HTML sans échappement, puis tel qu'échappé.
SLUG = "portfolio"
PAGE = f"/projets/{SLUG}"
TITLE = 'A <b> & "c"'
ESCAPED_TITLE = "A &lt;b&gt; &amp; &quot;c&quot;"
SUMMARY = "R"

# Une valeur qui casse le HTML sans échappement, texte comme attribut ; puis chaque valeur injectée
# qui la porte : les champs du projet, puis l'adresse de l'image.
HOSTILE = 'x <b> & "y"'
INJECTED: dict[str, tuple[dict[str, str], str | None]] = {
    "titre": ({"title": HOSTILE}, None),
    "résumé": ({"summary": HOSTILE}, None),
    "image": ({}, HOSTILE),
}

# La couverture prête : ses variantes telles que le worker les écrit, par largeur croissante, puis
# le chemin de celle de 1200 px, et son adresse absolue sous le client de test.
COVER_VARIANTS = [
    {"name": "images/couverture/960.webp", "width": 960, "height": 960},
    {"name": "images/couverture/1200.webp", "width": 1200, "height": 1200},
]
COVER_PATH = "/media/images/couverture/1200.webp"
COVER_URL = f"http://testserver{COVER_PATH}"

# Les quatre balises de tout aperçu, puis l'`og:image` d'une couverture prête, telles que les lit
# l'analyseur HTML : valeurs déséchappées.
FOUR_TAGS: list[tuple[str, dict[str, str | None]]] = [
    ("title", {}),
    ("meta", {"name": "description", "content": SUMMARY}),
    ("meta", {"property": "og:title", "content": TITLE}),
    ("meta", {"property": "og:description", "content": SUMMARY}),
]
OG_IMAGE: tuple[str, dict[str, str | None]] = (
    "meta",
    {"property": "og:image", "content": COVER_URL},
)

# Les adresses de `/projets/*` sans projet publié (décision 1). Le projet publié du brief existe :
# une adresse qui commence par son slug ne doit pas le servir.
REDIRECTED = {
    "slug inconnu": "/projets/inconnu",
    "projet dépublié": "/projets/brouillon",
    "sans slug": "/projets/",
    "deux segments": "/projets/a/b",
    "slug hors du motif": "/projets/a%20b",
    "slug suivi de deux barres": f"{PAGE}//",
    "slug suivi d'un retour à la ligne": f"{PAGE}%0A",
}

# Les méthodes qui ne lisent pas la page : `405`, sans corps. `POST` en est, mais le middleware CSRF
# le refuse avant la vue.
UNSAFE_METHODS = ["PUT", "PATCH", "DELETE", "OPTIONS"]

# Les gabarits défectueux (décision 8) : leur contenu, `None` pour un fichier absent.
BROKEN_TEMPLATES: dict[str, bytes | None] = {
    "introuvable": None,
    "sans marqueur": TEMPLATE.replace(START, b"").replace(END, b""),
    "marqueur de début doublé": TEMPLATE.replace(START, START * 2),
    "marqueur de fin doublé": TEMPLATE.replace(END, END * 2),
    "sans marqueur de début": TEMPLATE.replace(START, b""),
    "sans marqueur de fin": TEMPLATE.replace(END, b""),
    "marqueurs inversés": TEMPLATE.replace(START, b"INVERSION")
    .replace(END, START)
    .replace(b"INVERSION", END),
}


def marked_block(document: bytes) -> str:
    """Le bloc marqué de `document`, entre ses deux marqueurs."""
    return document.partition(START)[2].partition(END)[0].decode()


def outside(document: bytes) -> tuple[bytes, bytes]:
    """Ce que `document` porte hors de son bloc marqué : jusqu'au marqueur de début compris, puis
    depuis le marqueur de fin compris."""
    head, _, rest = document.partition(START)
    tail = rest.partition(END)[2]
    return head + START, END + tail


def served(client: Client) -> tuple[object, ...]:
    """Ce que `client` reçoit de la page : statut, en-têtes de contenu et de cache, corps."""
    response = client.get(PAGE)
    return (
        response.status_code,
        response["Content-Type"],
        response["Cache-Control"],
        response.content,
    )


@pytest.fixture
def template(tmp_path: Path) -> Iterator[Path]:
    """Le gabarit que la vue lit le temps du test, à la place de la fixture de test : absent tant
    que le test ne l'écrit pas."""
    path = tmp_path / "index.html"
    with override_settings(LINK_PREVIEW_TEMPLATE=path):
        yield path


@pytest.fixture
def published() -> Project:
    """Le projet publié du brief, sans image."""
    return saved(project(slug=SLUG, title=TITLE, summary=SUMMARY, published=True))


@pytest.fixture
def covered(published: Project) -> Project:
    """Le projet publié du brief, avec une couverture prête."""
    saved(gallery_image(published, state=ProcessingState.READY, variants=COVER_VARIANTS))
    return published


@pytest.mark.django_db
@pytest.mark.usefixtures("covered")
def test_un_projet_publie_rend_ses_cinq_balises_echappees(client: Client) -> None:
    """Le bloc marqué porte exactement les cinq balises (ADR 0011) : le titre dans `<title>` et
    `og:title`, le résumé dans `description` et `og:description`, l'adresse absolue de la variante
    de 1200 px de la couverture dans `og:image`. Chaque valeur est échappée pour son contexte,
    texte comme attribut (décisions 2, 3 et 6)."""
    response = client.get(PAGE)

    block = marked_block(response.content)
    assert (response.status_code, response["Content-Type"]) == (200, "text/html; charset=utf-8")
    assert tags(block) == [*FOUR_TAGS, OG_IMAGE]
    assert f"<title>{ESCAPED_TITLE}</title>" in block
    assert f'content="{ESCAPED_TITLE}"' in block
    assert "b" not in {tag for tag, _ in tags(response.content.decode())}


@pytest.mark.parametrize(("fields", "image"), INJECTED.values(), ids=INJECTED.keys())
def test_chaque_valeur_injectee_est_echappee(fields: dict[str, str], image: str | None) -> None:
    """Le titre, le résumé et l'adresse de l'image, chacun seul porteur d'une valeur hostile : elle
    n'apparaît jamais brute, et l'analyseur HTML la relit intacte dans son attribut (décision 6)."""
    block = meta_tags(project(**fields), image).decode()

    assert HOSTILE not in block
    assert HOSTILE in {attributes.get("content") for _, attributes in tags(block)}


@pytest.mark.django_db
@pytest.mark.usefixtures("covered")
@pytest.mark.parametrize("newline", LINE_ENDINGS.values(), ids=LINE_ENDINGS.keys())
def test_hors_du_bloc_marque_la_page_est_le_gabarit_octet_pour_octet(
    client: Client, template: Path, newline: bytes
) -> None:
    """Les fichiers hachés de la compilation, le reste du `<head>` et le `<body>` sont ceux du
    gabarit, marqueurs et fins de ligne compris : seul le bloc change."""
    content = TEMPLATE.replace(b"\r\n", b"\n").replace(b"\n", newline)
    template.write_bytes(content)

    assert outside(client.get(PAGE).content) == outside(content)


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
def test_sans_image_l_apercu_n_a_pas_d_og_image(client: Client) -> None:
    """Sans couverture, les quatre autres balises, sans image de repli (décision 2)."""
    assert tags(marked_block(client.get(PAGE).content)) == FOUR_TAGS


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state", [ProcessingState.PENDING, ProcessingState.FAILED], ids=["en attente", "en échec"]
)
def test_une_premiere_image_qui_n_est_pas_prete_n_a_pas_d_og_image(
    client: Client, published: Project, state: ProcessingState
) -> None:
    """La couverture est la première image de la galerie, prête ou non : une image prête plus loin
    n'en tient pas lieu (décision 2)."""
    saved(gallery_image(published, state=state))
    saved(
        gallery_image(published, position=2, state=ProcessingState.READY, variants=COVER_VARIANTS)
    )

    assert tags(marked_block(client.get(PAGE).content)) == FOUR_TAGS


@pytest.mark.django_db
def test_une_couverture_prete_sans_variante_de_1200_px_n_a_pas_d_og_image(
    client: Client, published: Project
) -> None:
    """Un état que l'admin refuse — une couverture de moins de 1200 px de côté — rend la page
    sans `og:image`, jamais une erreur."""
    saved(gallery_image(published, state=ProcessingState.READY, variants=COVER_VARIANTS[:1]))

    assert tags(marked_block(client.get(PAGE).content)) == FOUR_TAGS


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
@pytest.mark.parametrize("address", REDIRECTED.values(), ids=REDIRECTED.keys())
def test_une_adresse_sans_projet_publie_redirige_vers_l_accueil(
    client: Client, address: str
) -> None:
    """`302 Found` vers `/`, jamais une 404 (décision 1, ADR 0009)."""
    saved(project(slug="brouillon", published=False))

    response = client.get(address)

    assert (response.status_code, response["Location"]) == (302, "/")


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
def test_une_barre_finale_rend_la_meme_page(client: Client) -> None:
    """`/projets/<slug>/` est l'adresse de la même fiche, comme pour le site
    (`apps/web/src/project/project.ts`, `PROJECT_PATH`) : Caddy relaie tout `/projets/*` ici."""
    response = client.get(f"{PAGE}/")

    assert (response.status_code, response.content) == (200, client.get(PAGE).content)


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
@pytest.mark.parametrize("method", UNSAFE_METHODS)
def test_une_methode_qui_ne_lit_pas_est_refusee(client: Client, method: str) -> None:
    """Seuls `GET` et `HEAD` lisent la page (`require_safe`)."""
    response = client.generic(method, PAGE)

    assert (response.status_code, response.content) == (405, b"")


@pytest.mark.django_db
@pytest.mark.usefixtures("template")
def test_une_adresse_hors_du_motif_redirige_sans_lire_ni_le_gabarit_ni_la_base(
    client: Client, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    """Ce qui n'a pas la forme d'un slug ne peut nommer aucun projet (`validate_slug`) : la
    redirection précède toute lecture — un gabarit introuvable n'y change rien."""
    with django_assert_num_queries(0):
        response = client.get(REDIRECTED["slug hors du motif"])

    assert (response.status_code, response["Location"]) == (302, "/")


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
def test_l_apercu_se_revalide_a_chaque_visite(client: Client) -> None:
    """`Cache-Control: no-cache`, comme l'`index.html` que Caddy sert : la page cite les fichiers
    hachés de la compilation du moment (décision 5)."""
    response = client.get(PAGE)

    assert (response.status_code, response["Cache-Control"]) == (200, "no-cache")


@pytest.mark.django_db
@pytest.mark.usefixtures("covered")
def test_la_seconde_requete_est_servie_par_le_cache(
    client: Client, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    """La page rendue est gardée dans l'espace du contenu (décision 4) : la seconde requête est
    servie sans une requête en base, à l'identique, `no-cache` compris."""
    from_base = served(client)

    with django_assert_num_queries(0):
        from_cache = served(client)

    assert from_cache == from_base


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
def test_la_page_gardee_d_un_projet_n_est_jamais_servie_pour_un_autre(client: Client) -> None:
    """La clé distingue le slug (décision 4)."""
    saved(project(slug="autre", title="Autre", published=True))
    client.get(PAGE)

    assert "<title>Autre</title>" in marked_block(client.get("/projets/autre").content)


@pytest.mark.django_db
@pytest.mark.usefixtures("covered")
@pytest.mark.parametrize(
    ("request_options", "origin"), OTHER_ORIGINS.values(), ids=OTHER_ORIGINS.keys()
)
def test_chaque_origine_recoit_la_page_a_sa_propre_og_image(
    client: Client, request_options: dict[str, Any], origin: str
) -> None:
    """L'`og:image` est une adresse absolue construite sur l'origine de la requête : la page gardée
    pour une origine n'est jamais servie à une autre (décision 4)."""
    client.get(PAGE)

    response = client.get(PAGE, **request_options)

    assert tags(marked_block(response.content))[-1] == (
        "meta",
        {"property": "og:image", "content": f"{origin}{COVER_PATH}"},
    )


@pytest.mark.django_db
def test_une_redirection_n_est_jamais_gardee(client: Client) -> None:
    """Un brouillon publié sans qu'aucun signal parte (`QuerySet.update`), donc sans purge : sa
    page suit aussitôt, faute d'une redirection gardée qui la masquerait (décision 4) — le cache,
    qui ne garde que le corps et son type, la rejouerait en `200` vide."""
    saved(project(slug="brouillon", title="Brouillon", published=False))
    before = client.get("/projets/brouillon")

    Project.objects.filter(slug="brouillon").update(published=True)

    after = client.get("/projets/brouillon")
    assert before.status_code == 302
    assert "<title>Brouillon</title>" in marked_block(after.content)


@pytest.mark.django_db
def test_apres_sauvegarde_du_projet_l_apercu_rend_le_nouveau_titre(
    client: Client,
    published: Project,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """L'écriture validée du projet vide l'espace du contenu, page comprise (brief de #11,
    décision 3)."""
    client.get(PAGE)

    with django_capture_on_commit_callbacks(execute=True):
        published.title = "Nouveau titre"
        published.save()

    assert "<title>Nouveau titre</title>" in marked_block(client.get(PAGE).content)


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
def test_un_gabarit_change_n_est_jamais_servi_depuis_l_entree_de_l_ancien(
    client: Client, template: Path
) -> None:
    """Même slug, même génération, un autre gabarit — un déploiement : la clé porte l'empreinte du
    gabarit, et la page gardée avant ne cite jamais des fichiers que Caddy ne sert plus
    (décision 4)."""
    template.write_bytes(TEMPLATE)
    before = client.get(PAGE).content

    template.write_bytes(DEPLOYED)
    after = client.get(PAGE).content

    assert (outside(before), outside(after)) == (outside(TEMPLATE), outside(DEPLOYED))


@pytest.mark.django_db
@pytest.mark.usefixtures("published")
@pytest.mark.parametrize("content", BROKEN_TEMPLATES.values(), ids=BROKEN_TEMPLATES.keys())
def test_un_gabarit_defectueux_est_une_erreur_journalisee_jamais_une_page(
    template: Path, caplog: pytest.LogCaptureFixture, content: bytes | None
) -> None:
    """Introuvable, ou sans ses deux marqueurs uniques dans l'ordre : `500`, et l'erreur, qui nomme
    le gabarit, est journalisée par Django avec sa trace (décision 8)."""
    if content is not None:
        template.write_bytes(content)

    response = Client(raise_request_exception=False).get(PAGE)

    logged = [
        (record.name, record.levelno, record.exc_info[1])
        for record in caplog.records
        if record.exc_info
    ]
    assert response.status_code == 500
    assert [(name, level, type(error)) for name, level, error in logged] == [
        ("django.request", logging.ERROR, LinkPreviewTemplateError)
    ]
    assert str(template) in str(logged[0][2])


@pytest.mark.django_db
def test_aucune_operation_declaree_de_l_api_publique_ne_repond_en_html(client: Client) -> None:
    """Chaque opération que déclare le schéma de l'API publique, appelée : aucune ne répond en
    `text/html` (décision 7). L'admin, HTML par nature (ADR 0001), en est hors."""
    # `OpenAPISchema` hérite d'un `dict` nu (`ninja/openapi/schema.py`) : ses chemins se typent ici,
    # sinon pyright strict les tient pour en partie inconnus (relevé en CI, run 41946822022).
    paths: dict[str, dict[str, object]] = api.get_openapi_schema()["paths"]
    operations = [(method.upper(), path) for path, methods in paths.items() for method in methods]

    types = {
        operation: client.generic(*operation).get("Content-Type", "") for operation in operations
    }

    assert operations
    # Un chemin paramétré serait appelé accolades comprises, donc sur sa 404 : le jour où une
    # opération en déclare un, ce test doit lui donner une valeur.
    assert [path for _, path in operations if "{" in path] == []
    assert [operation for operation, kind in types.items() if kind.startswith("text/html")] == []
