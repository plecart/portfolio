"""Tests de l'aperçu Markdown de l'admin : le rendu (`markdown-it-py` puis `nh3`, brief de #8,
décision 8), et sa frontière — l'aperçu seul atteint les deux bibliothèques (ADR 0010, D51)."""

import ast
from html.parser import HTMLParser
from pathlib import Path

import pytest
from content.preview import render

# Le dossier de l'application et ses paquets : ce qu'une route peut atteindre, tests exclus.
APPLICATION = Path(__file__).resolve().parents[1]
PACKAGES = ("config", "content")

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
    `from a import b` donne `a` et `a.b` — `b` peut être un module."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names |= {node.module} | {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def importers(target: str) -> set[str]:
    """Les modules de l'application qui importent `target` ou l'un de ses sous-modules."""
    found: set[str] = set()
    for package in PACKAGES:
        for path in (APPLICATION / package).rglob("*.py"):
            names = imported_names(path)
            if any(name == target or name.startswith(f"{target}.") for name in names):
                found.add(".".join(path.relative_to(APPLICATION).with_suffix("").parts))
    return found


@pytest.mark.parametrize("library", ["markdown_it", "nh3"])
def test_seul_l_apercu_importe_markdown_it_py_et_nh3(library: str) -> None:
    """Les deux bibliothèques ne servent qu'à l'aperçu de l'admin (ADR 0010, D51) : aucun autre
    module de l'application ne les importe."""
    assert importers(library) == {"content.preview"}


def test_l_apercu_rend_les_paragraphes_et_les_listes() -> None:
    """Ce que la fiche prévoit dans une section : des paragraphes et des listes (spec §7)."""
    rendered = render("Un paragraphe.\n\n- un\n- deux\n\n1. premier")

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
    rendered = render(text)

    assert "<script" not in rendered
    assert "&lt;script&gt;" in rendered


def test_l_apercu_ne_garde_que_les_balises_et_les_attributs_de_sa_liste_blanche() -> None:
    """Liste blanche fermée (décision 8) : quoi que produise `markdown-it-py`, l'aperçu ne garde
    que ses balises, et seul un lien porte des attributs."""
    found = tags(render(EVERY_CONSTRUCT))

    assert {tag for tag, _ in found} <= ALLOWED_TAGS
    assert [(tag, attrs) for tag, attrs in found if attrs and tag != "a"] == []
    assert {name for tag, attrs in found if tag == "a" for name in attrs} <= LINK_ATTRIBUTES


def test_une_image_n_apparait_pas_dans_l_apercu() -> None:
    """Ni image ni aperçu des images (brief de #8, critère et « Hors périmètre ») : spec §7 ne
    prévoit que paragraphes et listes."""
    found = tags(render("![un schéma](https://example.org/schema.png)"))

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
    ],
)
def test_un_lien_hors_http_https_et_mailto_perd_sa_cible(text: str) -> None:
    """Un lien `javascript:` est neutralisé (brief de #8, critère), comme tout schéma hors de
    `http`, `https` et `mailto` (décision 8).

    `markdown-it-py` ne fait pas un lien des schémas qu'il juge dangereux (`validateLink`) ; les
    autres deviennent des liens, dont `nh3` retire la cible."""
    found = tags(render(text))

    assert [attrs for _, attrs in found if "href" in attrs] == []


@pytest.mark.parametrize(
    "url", ["https://example.org/", "http://example.org/", "mailto:auteur@example.org"]
)
def test_un_lien_http_https_ou_mailto_garde_sa_cible_et_s_ouvre_a_part(url: str) -> None:
    """Le lien garde sa cible ; `rel` est imposé (décision 8), et le lien s'ouvre dans un nouvel
    onglet : un clic dans l'aperçu ne quitte pas un formulaire qu'on n'a pas enregistré."""
    found = tags(render(f"[x]({url})"))

    assert found == [("p", {}), ("a", {"href": url, **FORCED_LINK_ATTRIBUTES})]
