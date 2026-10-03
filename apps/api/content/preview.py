"""L'aperçu Markdown de l'admin : son rendu (brief de #8, décision 8).

Indicatif : le rendu de référence est celui du site, en éléments React (ADR 0010). `markdown-it-py`
et `nh3` ne servent qu'ici.
"""

import nh3
from markdown_it import MarkdownIt

# CommonMark, comme le site (ADR 0010), HTML brut désactivé : il est montré comme du texte, comme
# sur le site.
_markdown = MarkdownIt("commonmark", {"html": False})

# Puis une liste blanche fermée (décision 8) : paragraphes, listes, emphases, code, citations,
# sauts de ligne, titres et liens — ni image, ni HTML brut. Un lien ne garde que sa cible, en
# `http`, `https` ou `mailto` ; il s'ouvre dans un nouvel onglet, sans accès à l'admin : un clic
# dans l'aperçu ne quitte pas le formulaire qu'on n'a pas encore enregistré.
_cleaner = nh3.Cleaner(
    tags={
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
    },
    # `"*"` vide : sans lui, `nh3` garde partout `title` et `lang`, ses attributs génériques par
    # défaut (mesuré, nh3 0.3.7).
    attributes={"a": {"href"}, "*": set()},
    url_schemes={"http", "https", "mailto"},
    link_rel="noopener noreferrer",
    set_tag_attribute_values={"a": {"target": "_blank"}},
)


def render(text: str) -> str:
    """Le HTML de l'aperçu de `text`, un texte Markdown.

    `markdown-it-py` le rend, puis `nh3` n'en garde que la liste blanche. Une construction hors
    liste perd sa balise et garde son texte ; une image disparaît, faute de texte.

    Args:
        text: le Markdown saisi, tel quel ; vide, l'aperçu est vide.

    Returns:
        Un fragment HTML sûr à insérer dans une page de l'admin.
    """
    return _cleaner.clean(_markdown.render(text))
