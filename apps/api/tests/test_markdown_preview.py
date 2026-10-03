"""Tests de l'aperçu Markdown de l'admin : le rendu (`markdown-it-py` puis `nh3`, brief de #8,
décision 8), la vue qui le sert (décision 2), les aperçus de l'écran Projet (décision 1) — et la
frontière : l'aperçu seul atteint les deux bibliothèques (ADR 0010, D51)."""

import ast
import inspect
import re
from collections.abc import Callable, Iterator, Sequence
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from config import strings
from content.preview import FIELD_CLASS, PREVIEW_CLASS, render_markdown
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from factories import saved, section, technology
from test_project_admin import saved_project

# Le dossier de l'application, et celui de ses tests : tout le reste est ce qu'une route peut
# atteindre, paquet ajouté plus tard compris (l'API publique de #10).
APPLICATION = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent

# Le nom de la route de l'aperçu, que le script appelle, et ce qu'il lui envoie.
PREVIEW = "markdown_preview"
SENT = {"text": "Un *mot*."}

# Le script qui rafraîchit les aperçus pendant la saisie.
PREVIEW_SCRIPT = "content/admin/markdown_preview.js"

# Un champ Markdown tel que l'écran le rend : son bloc et ses données, sa zone de texte, puis son
# aperçu légendé.
MARKDOWN_FIELD = re.compile(
    rf'<div class="{FIELD_CLASS}" data-preview-url="(?P<url>[^"]*)" '
    rf'data-preview-failed="(?P<failed>[^"]*)"><textarea name="(?P<name>[^"]+)".*?</textarea>'
    rf"<figure><figcaption>(?P<caption>[^<]*)</figcaption>"
    rf'<div class="{PREVIEW_CLASS}">(?P<preview>.*?)</div></figure></div>',
    re.DOTALL,
)

# La liste blanche de l'aperçu (brief de #8, décision 8), écrite ici sans la lire dans le module :
# paragraphes, listes, emphases, code, citations, sauts de ligne, titres et liens.
ALLOWED_TAGS = {
    "p",
    "ul",
    "ol",
    "li",
    "em",
    "strong",
    "code",
    "pre",
    "blockquote",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "a",
}
# Les attributs d'un lien : sa cible, et les deux que l'aperçu impose.
LINK_ATTRIBUTES = {"href", "rel", "target"}
# Ceux qu'un lien de l'aperçu porte toujours : il s'ouvre à part, sans accès à l'admin.
FORCED_LINK_ATTRIBUTES = {"rel": "noopener noreferrer", "target": "_blank"}

# Toutes les constructions de CommonMark, HTML brut compris.
EVERY_CONSTRUCT = """\
# Titre

Sous-titre
----------

Paragraphe *emphase* **forte** `code` et [lien](https://example.org/ "titre").
Ligne coupée\\
après.

> Citation

***

![schéma](https://example.org/schema.png)

```python
print(1)
```

    bloc indenté

3. trois
4. quatre

<https://example.org/auto> <b onclick="alert(1)">gras</b>

<div style="color: red">bloc</div>
"""


class _Tags(HTMLParser):
    """Les balises ouvrantes d'un fragment HTML, chacune avec ses attributs."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.found.append((tag, dict(attrs)))


def tags(fragment: str) -> list[tuple[str, dict[str, str | None]]]:
    """Les balises de `fragment`, dans l'ordre, avec leurs attributs."""
    parser = _Tags()
    parser.feed(fragment)
    parser.close()
    return parser.found


def imported_names(path: Path) -> set[str]:
    """Les modules que le fichier `path` importe, lus dans sa syntaxe : `import a.b` donne `a.b`,
    `from a import b` donne `a` et `a.b` — `b` peut être un module ; un import relatif se lit
    depuis le paquet du fichier."""
    package = path.relative_to(APPLICATION).parent.parts
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else ()
            module = ".".join([*base, *([node.module] if node.module else [])])
            names |= {module} | {f"{module}.{alias.name}" for alias in node.names}
    return names


def importers(target: str) -> set[str]:
    """Les modules de l'application, tests exclus, qui importent `target` ou l'un de ses
    sous-modules."""
    found: set[str] = set()
    for path in APPLICATION.rglob("*.py"):
        if path.is_relative_to(TESTS):
            continue
        names = imported_names(path)
        if any(name == target or name.startswith(f"{target}.") for name in names):
            found.add(".".join(path.relative_to(APPLICATION).with_suffix("").parts))
    return found


def routes(
    patterns: Sequence[URLPattern | URLResolver], prefix: str = ""
) -> Iterator[tuple[str, Callable[..., Any]]]:
    """Chaque route de `patterns`, avec la vue qu'elle appelle, dégagée de ses enveloppes."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from routes(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), inspect.unwrap(pattern.callback)


@pytest.mark.parametrize("library", ["markdown_it", "nh3"])
def test_seul_l_apercu_importe_markdown_it_py_et_nh3(library: str) -> None:
    """Les deux bibliothèques ne servent qu'à l'aperçu de l'admin (ADR 0010, D51) : aucun autre
    module de l'application ne les importe."""
    assert importers(library) == {"content.preview"}


def test_seules_des_routes_de_l_admin_atteignent_l_apercu() -> None:
    """Aucune vue publique n'appelle les bibliothèques de l'aperçu (critère du corps de #8) : seuls
    l'admin et la table de routage importent son module, et la seule route qui mène à sa vue est
    sous `admin/`."""
    reaching = {
        route
        for route, view in routes(get_resolver().url_patterns)
        if view.__module__ == "content.preview"
    }

    assert importers("content.preview") <= {"content.admin", "config.urls"}
    assert reaching == {"admin/markdown-preview/"}


@pytest.mark.django_db
def test_la_vue_d_apercu_rend_le_texte_recu(admin_client: Client) -> None:
    """Le script envoie le texte saisi ; la vue en rend l'aperçu, sans rien enregistrer (brief de
    #8, décision 2)."""
    response = admin_client.post(reverse(PREVIEW), SENT)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response.content.decode() == "<p>Un <em>mot</em>.</p>\n"


def test_un_anonyme_est_renvoye_de_l_apercu_vers_la_connexion(client: Client) -> None:
    """L'aperçu est réservé à l'utilisateur connecté de l'admin (décision 2)."""
    response = client.post(reverse(PREVIEW), SENT)

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("admin:login"))


@pytest.mark.django_db
def test_l_apercu_exige_le_jeton_csrf_du_formulaire(admin_user: User) -> None:
    """Refusé sans jeton CSRF, rendu avec celui que le script lit dans le formulaire de l'écran et
    envoie en en-tête. Le client de test de Django saute ce contrôle ; celui-ci l'exige, comme un
    navigateur."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    page = client.get(reverse("admin:content_project_add")).content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)
    assert token is not None

    refused = client.post(reverse(PREVIEW), SENT)
    accepted = client.post(reverse(PREVIEW), SENT, headers={"X-CSRFToken": token.group(1)})

    assert (refused.status_code, accepted.status_code) == (403, 200)


@pytest.mark.django_db
def test_l_apercu_ne_repond_qu_en_post(admin_client: Client) -> None:
    """Le texte voyage dans le corps de la requête, jamais dans l'adresse (décision 2)."""
    assert admin_client.get(reverse(PREVIEW), SENT).status_code == 405


@pytest.mark.django_db
def test_l_apercu_n_est_jamais_mis_en_cache(admin_client: Client) -> None:
    """Chaque aperçu est celui du texte du moment (décision 2)."""
    response = admin_client.post(reverse(PREVIEW), SENT)

    assert "no-store" in response["Cache-Control"]


def test_l_apercu_rend_les_paragraphes_et_les_listes() -> None:
    """Ce que la fiche prévoit dans une section : des paragraphes et des listes (spec §7)."""
    rendered = render_markdown("Un paragraphe.\n\n- un\n- deux\n\n1. premier")

    assert rendered == (
        "<p>Un paragraphe.</p>\n"
        "<ul>\n<li>un</li>\n<li>deux</li>\n</ul>\n"
        "<ol>\n<li>premier</li>\n</ol>\n"
    )


@pytest.mark.parametrize(
    "text",
    ["<script>alert(1)</script>", "Un mot <script>alert(1)</script> dans la phrase."],
    ids=["en bloc", "dans une ligne"],
)
def test_une_balise_script_du_corps_n_apparait_pas_dans_l_apercu(text: str) -> None:
    """Le HTML brut du Markdown est montré comme du texte, jamais interprété (critère du corps de
    #8)."""
    rendered = render_markdown(text)

    assert "<script" not in rendered
    assert "&lt;script&gt;" in rendered


def test_l_apercu_ne_garde_que_les_balises_et_les_attributs_de_sa_liste_blanche() -> None:
    """Liste blanche fermée (décision 8) : quoi que produise `markdown-it-py`, l'aperçu ne garde
    que ses balises, et seul un lien porte des attributs."""
    found = tags(render_markdown(EVERY_CONSTRUCT))

    assert {tag for tag, _ in found} <= ALLOWED_TAGS
    assert [(tag, attrs) for tag, attrs in found if attrs and tag != "a"] == []
    assert {name for tag, attrs in found if tag == "a" for name in attrs} <= LINK_ATTRIBUTES


def test_une_image_n_apparait_pas_dans_l_apercu() -> None:
    """Ni image ni aperçu des images (brief de #8, critère et « Hors périmètre ») : spec §7 ne
    prévoit que paragraphes et listes."""
    found = tags(render_markdown("![un schéma](https://example.org/schema.png)"))

    assert "img" not in {tag for tag, _ in found}


@pytest.mark.parametrize(
    "text",
    [
        "[x](javascript:alert(1))",
        "[x](JaVaScRiPt:alert(1))",
        "<javascript:alert(1)>",
        "[x](data:text/html;base64,PHNjcmlwdD4=)",
        "[x](data:image/png;base64,iVBORw0KGgo=)",
        "[x](ftp://example.org/)",
        "<tel:+33100000000>",
        "[x](/admin/auth/user/)",
        "[x](//example.org/)",
        "[x](?q=1)",
        "[x](#s-contexte)",
    ],
)
def test_un_lien_hors_http_https_et_mailto_perd_sa_cible(text: str) -> None:
    """Un lien `javascript:` est neutralisé (brief de #8, critère), comme tout schéma hors de
    `http`, `https` et `mailto`, et toute adresse relative, qui n'en a pas (décision 8).

    `markdown-it-py` ne fait pas un lien des schémas qu'il juge dangereux (`validateLink`) ; les
    autres deviennent des liens, dont `nh3` retire la cible."""
    found = tags(render_markdown(text))

    assert [attrs for _, attrs in found if "href" in attrs] == []


@pytest.mark.parametrize(
    "url", ["https://example.org/", "http://example.org/", "mailto:auteur@example.org"]
)
def test_un_lien_http_https_ou_mailto_garde_sa_cible_et_s_ouvre_a_part(url: str) -> None:
    """Le lien garde sa cible ; `rel` est imposé (décision 8), et le lien s'ouvre dans un nouvel
    onglet : un clic dans l'aperçu ne quitte pas un formulaire qu'on n'a pas enregistré."""
    found = tags(render_markdown(f"[x]({url})"))

    assert found == [("p", {}), ("a", {"href": url, **FORCED_LINK_ATTRIBUTES})]


@pytest.mark.django_db
def test_l_ecran_projet_montre_l_apercu_sous_la_description_et_sous_chaque_section(
    admin_client: Client,
) -> None:
    """Chaque champ Markdown de l'écran Projet porte son aperçu, rendu avec la page (décision 1) :
    la description, le corps de chaque section — enregistrée ou neuve —, et celui de la ligne
    modèle que le bouton « Ajouter » de Django recopie, pour qu'une ligne ajoutée après le
    chargement ait le sien."""
    portfolio = saved_project(saved(technology(name="Django")), description="Un *mot*.")
    saved(section(portfolio, body="- un"))

    page = admin_client.get(
        reverse("admin:content_project_change", args=[portfolio.pk])
    ).content.decode()

    assert [(field["name"], field["preview"]) for field in MARKDOWN_FIELD.finditer(page)] == [
        ("description", "<p>Un <em>mot</em>.</p>\n"),
        ("section_set-0-body", "<ul>\n<li>un</li>\n</ul>\n"),
        ("section_set-1-body", ""),
        ("section_set-__prefix__-body", ""),
    ]
    assert {
        (field["url"], field["failed"], field["caption"]) for field in MARKDOWN_FIELD.finditer(page)
    } == {(reverse(PREVIEW), strings.MARKDOWN_PREVIEW_FAILED, strings.MARKDOWN_PREVIEW)}


@pytest.mark.django_db
def test_l_ecran_projet_charge_le_script_d_apercu_sans_code_dans_la_page(
    admin_client: Client,
) -> None:
    """Le script d'aperçu est un fichier servi par l'admin, et la page n'écrit aucun script en
    ligne : la CSP stricte de #6 les refusera (brief de #8, critère)."""
    page = admin_client.get(reverse("admin:content_project_add")).content.decode()

    assert f'<script src="{static(PREVIEW_SCRIPT)}">' in page
    assert re.findall(r"<script(?![^>]*\ssrc=)[^>]*>", page) == []


def test_le_script_d_apercu_lit_les_prises_que_l_ecran_lui_livre() -> None:
    """Le script n'a pas de test de navigateur (ADR 0013) : ce test en tient la part serveur. Il lit
    le bloc et l'aperçu que pose le widget, les deux données du bloc, le jeton CSRF du formulaire,
    et envoie le texte dans le champ que lit la vue."""
    found = finders.find(PREVIEW_SCRIPT)
    assert isinstance(found, str)
    # Le code seul : une prise que seul un commentaire nomme encore ne tient rien.
    source = Path(found).read_text(encoding="utf-8")
    script = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)

    for hook in (
        f".{FIELD_CLASS}",
        f".{PREVIEW_CLASS}",
        "dataset.previewUrl",
        "dataset.previewFailed",
        "[name=csrfmiddlewaretoken]",
        '"X-CSRFToken"',
        "{ text: ",
    ):
        assert hook in script
