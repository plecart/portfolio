"""Le gabarit du site — l'`index.html` compilé du front, `LINK_PREVIEW_TEMPLATE` — et l'identité
du site qu'il porte, seule source (#265).

Trois paires de marqueurs le découpent, dans l'ordre de `SLOTS` (`docs/frontend-outillage.md`
§2.4) : `meta`, le bloc d'aperçu (D53, ADR 0011) ; `page`, ce qui est propre à la page dans le
`<head>` ; `root`, le contenu de `#root`. Une vue de l'hôte du site remplace le contenu d'une paire
et en garde les marqueurs (`Template.fill`).

L'identité du site (`Site`) se lit dans le même fichier, que le front tient : l'adresse de l'accueil
dans le `canonical` de la paire `page`, sa description dans la paire `meta`, et l'auteur dans le
`Person` du JSON-LD qui, hors des paires, reste sur chaque page.
"""

import hashlib
import json
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple, cast
from urllib.parse import urljoin

# Les paires de marqueurs du gabarit, dans l'ordre où elles s'y suivent : une paire de plus est une
# entrée de plus.
SLOTS = ("meta", "page", "root")

# Le type d'un script JSON-LD : celui de l'identité du site, et celui d'une fiche.
JSON_LD = "application/ld+json"


class LinkPreviewTemplateError(RuntimeError):
    """Le gabarit est illisible, n'a pas les marqueurs de chaque paire une fois chacun dans l'ordre,
    ou pas l'identité du site (décision 8 de #14, #265). Levée par la vue, journalisée par Django
    (`django.request`) avec sa trace et rendue en `500` : jamais une page servie sans les balises
    du projet."""


class Site(NamedTuple):
    """L'identité du site, telle que le gabarit la porte."""

    home: str
    """L'adresse de l'accueil, le `canonical` de la paire `page` : `https://pacome.dev/`."""
    person: str
    """L'`@id` du `Person`, auquel renvoie l'auteur d'une fiche."""
    name: str
    """Le nom du `Person`."""
    same_as: tuple[str, ...]
    """Ses profils (`sameAs`), dans l'ordre du gabarit."""
    description: str
    """La description de l'accueil, celle de la paire `meta`."""

    def project_url(self, slug: str) -> str:
        """L'adresse canonique de la fiche `slug`, sous celle de l'accueil :
        `https://pacome.dev/projets/<slug>`."""
        return urljoin(self.home, f"projets/{slug}")


class Template(NamedTuple):
    """Le gabarit, découpé autour du contenu de ses paires : octets tels quels, aucun décodage,
    aucune fin de ligne réécrite."""

    outside: tuple[bytes, ...]
    """Ce qui entoure le contenu des paires : jusqu'au premier marqueur de début compris, puis
    d'un marqueur de fin au marqueur de début suivant, marqueurs compris, puis la fin du fichier."""
    inside: dict[str, bytes]
    """Le contenu de chaque paire, entre ses marqueurs, par nom."""
    digest: str
    """L'empreinte SHA-256 du fichier entier."""
    site: Site
    """L'identité du site."""

    def fill(self, blocks: Mapping[str, bytes]) -> bytes:
        """Le gabarit, le contenu de chaque paire nommée dans `blocks` remplacé ; une autre paire
        garde le sien.

        Args:
            blocks: le contenu de paires, par nom de `SLOTS`, par exemple `{"meta": b"<title>…"}`.
        """
        pieces = [self.outside[0]]
        for name, rest in zip(SLOTS, self.outside[1:], strict=True):
            pieces += [blocks.get(name, self.inside[name]), rest]
        return b"".join(pieces)


class _Elements(HTMLParser):
    """Les balises d'un fragment HTML, avec leurs attributs, et le texte de chacun de ses scripts
    JSON-LD."""

    def __init__(self, fragment: str) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.json_ld: list[str] = []
        self._script: list[str] | None = None
        self.feed(fragment)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "script" and attributes.get("type") == JSON_LD:
            self._script = []

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script is not None:
            self.json_ld.append("".join(self._script))
            self._script = None

    def values(self, tag: str, key: str, value: str, attribute: str) -> list[str]:
        """L'attribut `attribute` de chaque `<tag>` dont l'attribut `key` vaut `value`, quand il
        porte une valeur : `values("link", "rel", "canonical", "href")`."""
        return [
            found
            for name, attributes in self.tags
            if name == tag
            and attributes.get(key) == value
            and isinstance(found := attributes.get(attribute), str)
        ]


def _error(path: Path, problem: str) -> LinkPreviewTemplateError:
    """L'erreur du gabarit `path`, que le message nomme."""
    return LinkPreviewTemplateError(f"le gabarit des aperçus de lien {path} {problem}")


def _one[T](path: Path, found: list[T], what: str) -> T:
    """Le seul élément de `found`, `what` dans le gabarit `path`."""
    if len(found) != 1:
        raise _error(path, f"doit porter {what} une fois ; il en porte {len(found)}")
    return found[0]


def _cut(path: Path, content: bytes) -> tuple[tuple[bytes, ...], dict[str, bytes]]:
    """Le gabarit `content` découpé autour du contenu de ses paires (`Template.outside` et
    `Template.inside`) ; `LinkPreviewTemplateError` qui nomme la paire dont les marqueurs ne
    sont pas une fois chacun, le début avant la fin, après la paire précédente."""
    outside: list[bytes] = []
    inside: dict[str, bytes] = {}
    rest = content
    for name in SLOTS:
        start, end = f"<!--{name}:start-->".encode(), f"<!--{name}:end-->".encode()
        counts = content.count(start), content.count(end)
        before, opened, after = rest.partition(start)
        block, closed, following = after.partition(end)
        if counts != (1, 1) or not (opened and closed):
            raise _error(
                path,
                f"doit porter {start.decode()} puis {end.decode()}, une fois chacun, après la "
                f"paire précédente ; il en porte {counts[0]} et {counts[1]}",
            )
        outside.append(before + start)
        inside[name] = block
        rest = end + following
    return (*outside, rest), inside


def _graph(path: Path, text: str) -> list[dict[str, object]]:
    """Les nœuds du JSON-LD `text` du gabarit `path`, ceux de son `@graph`."""
    try:
        data: object = json.loads(text)
    except ValueError as error:
        raise _error(path, "porte un JSON-LD qui ne se lit pas") from error
    graph = cast("dict[str, object]", data).get("@graph") if isinstance(data, dict) else None
    if not isinstance(graph, list):
        raise _error(path, "porte un JSON-LD sans liste `@graph`")
    nodes = cast("list[object]", graph)
    return [cast("dict[str, object]", node) for node in nodes if isinstance(node, dict)]


def _texts(value: object) -> tuple[str, ...] | None:
    """`value` en tuple, si c'est une liste de textes ; `None` sinon."""
    if not isinstance(value, list):
        return None
    items = cast("list[object]", value)
    texts = tuple(item for item in items if isinstance(item, str))
    return texts if len(texts) == len(items) else None


def _site(path: Path, outside: tuple[bytes, ...], inside: dict[str, bytes]) -> Site:
    """L'identité du site dans le gabarit `path`, découpé par `_cut`."""
    try:
        meta, page, rest = (
            _Elements(text.decode()) for text in (inside["meta"], inside["page"], b"".join(outside))
        )
    except UnicodeDecodeError as error:
        raise _error(path, "n'est pas en UTF-8") from error
    home = _one(path, page.values("link", "rel", "canonical", "href"), "un `canonical` dans `page`")
    description = _one(
        path, meta.values("meta", "name", "description", "content"), "une `description` dans `meta`"
    )
    persons = [
        node
        for text in rest.json_ld
        for node in _graph(path, text)
        if node.get("@type") == "Person"
    ]
    person = _one(path, persons, "un `Person` en JSON-LD hors des paires")
    match person.get("@id"), person.get("name"), _texts(person.get("sameAs")):
        case str() as person_id, str() as name, tuple() as same_as:
            return Site(home, person_id, name, same_as, description)
        case _:
            raise _error(
                path,
                "doit porter un `Person` à `@id` et `name` en texte, à `sameAs` en liste de textes",
            )


def read_template(path: Path) -> Template:
    """Lit le gabarit `path`, relu à chaque appel : rien ne garde un gabarit qu'un déploiement a
    remplacé.

    Args:
        path: le gabarit, `LINK_PREVIEW_TEMPLATE`.

    Raises:
        LinkPreviewTemplateError: le fichier ne se lit pas, n'a pas les deux marqueurs de chaque
            paire une fois chacun, dans l'ordre de `SLOTS`, ou n'a pas l'identité du site (`Site`)
            une fois, de ses types ; le message nomme le fichier, et la paire ou l'élément en défaut.
    """
    try:
        content = path.read_bytes()
    except OSError as error:
        raise LinkPreviewTemplateError(f"gabarit des aperçus de lien illisible : {path}") from error
    outside, inside = _cut(path, content)
    return Template(
        outside, inside, hashlib.sha256(content).hexdigest(), _site(path, outside, inside)
    )
