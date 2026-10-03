"""L'aperçu Markdown de l'admin (brief de #8, décisions 1, 2 et 8) : sous chaque champ Markdown
d'un écran, le rendu du texte, rafraîchi pendant la saisie, sans enregistrer.

Un écran — ou un tableau en ligne — déclare ses champs Markdown (`MarkdownFieldsAdmin`) ; chacun y
reçoit une zone de texte suivie de son aperçu (`MarkdownTextarea`), rendu avec la page.
`markdown_preview.js` le rafraîchit ensuite par la vue `preview`, que `config/urls.py` ne sert que
dans l'admin.

Indicatif : le rendu de référence est celui du site, en éléments React (ADR 0010). `markdown-it-py`
et `nh3` ne servent qu'ici.
"""

from typing import Any, ClassVar

import nh3
from config import strings
from django.contrib.admin.options import BaseModelAdmin
from django.contrib.admin.widgets import AdminTextareaWidget
from django.db.models import Field, Model
from django.forms import Field as FormField
from django.forms.renderers import BaseRenderer
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from django.views.decorators.http import require_POST
from markdown_it import MarkdownIt

# Le nom de la route de la vue, que le bloc de chaque champ donne au script.
PREVIEW_ROUTE = "markdown_preview"

# Les prises que `markdown_preview.js` lit : le bloc qui réunit une zone de texte et son aperçu, et
# l'aperçu.
FIELD_CLASS = "markdown-field"
PREVIEW_CLASS = "markdown-preview"

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
    # Une adresse relative n'a pas de schéma : `nh3` la laisserait passer (`pass_through` par
    # défaut, nh3 0.3.7), `//hôte` compris.
    url_relative="deny",
    link_rel="noopener noreferrer",
    set_tag_attribute_values={"a": {"target": "_blank"}},
)


def render_markdown(text: str) -> str:
    """Le HTML de l'aperçu de `text`, un texte Markdown.

    `markdown-it-py` le rend, puis `nh3` n'en garde que la liste blanche. Une construction hors
    liste perd sa balise et garde son texte ; une image disparaît, faute de texte.

    Args:
        text: le Markdown saisi, tel quel ; vide, l'aperçu est vide.

    Returns:
        Un fragment HTML sûr à insérer dans une page de l'admin.
    """
    return _cleaner.clean(_markdown.render(text))


@require_POST
def preview(request: HttpRequest) -> HttpResponse:
    """L'aperçu du texte que le script envoie pendant la saisie, sans rien enregistrer.

    La route l'enveloppe par `admin_view` : utilisateur de l'admin connecté — un anonyme est
    renvoyé vers la connexion —, jeton CSRF exigé, réponse jamais mise en cache.

    Args:
        request: une requête POST dont le champ `text` porte le Markdown ; absent, l'aperçu est
            vide.

    Returns:
        Le fragment HTML de `render_markdown`, en `text/html`. Une autre méthode que POST reçoit
        un 405.
    """
    return HttpResponse(render_markdown(request.POST.get("text", "")))


class MarkdownTextarea(AdminTextareaWidget):
    """La zone de texte d'un champ Markdown de l'admin, suivie de son aperçu légendé.

    L'aperçu de la valeur est rendu avec la page : rien à demander au chargement, et un écran
    revenu en erreur montre celui du texte renvoyé. Le bloc porte l'adresse de la vue et le message
    d'échec : le script n'écrit en dur ni route ni texte. La ligne modèle d'un tableau en ligne
    porte aussi son bloc, que Django recopie dans chaque ligne ajoutée.
    """

    class Media:
        css: ClassVar[dict[str, tuple[str, ...]]] = {"all": ("content/admin/markdown_preview.css",)}
        js = ("content/admin/markdown_preview.js",)

    def render(
        self,
        name: str,
        value: Any,
        attrs: dict[str, Any] | None = None,
        renderer: BaseRenderer | None = None,
    ) -> SafeString:
        """La zone de texte de Django, puis l'aperçu de `value`, dans un même bloc."""
        return format_html(
            '<div class="{field}" data-preview-url="{url}" data-preview-failed="{failed}">'
            "{textarea}<figure><figcaption>{caption}</figcaption>"
            '<div class="{preview}">{rendered}</div></figure></div>',
            field=FIELD_CLASS,
            url=reverse(PREVIEW_ROUTE),
            failed=strings.MARKDOWN_PREVIEW_FAILED,
            textarea=super().render(name, value, attrs, renderer),
            caption=strings.MARKDOWN_PREVIEW,
            preview=PREVIEW_CLASS,
            # Assaini par `nh3` : rien à échapper.
            rendered=mark_safe(render_markdown(self.format_value(value) or "")),
        )


class MarkdownFieldsAdmin[ModelT: Model](BaseModelAdmin[ModelT]):
    """Un écran d'admin, ou un tableau en ligne, dont des champs texte sont en Markdown.

    Chaque champ nommé dans `markdown_fields` reçoit son aperçu (`MarkdownTextarea`) et garde son
    texte tel que saisi : en Markdown, une ligne de tête indentée est un bloc de code, que Django
    retaillerait (`CharField.strip`).
    """

    markdown_fields: ClassVar[tuple[str, ...]] = ()

    def formfield_for_dbfield(
        self, db_field: Field[Any, Any], request: HttpRequest, **kwargs: Any
    ) -> FormField | None:
        """Le champ de formulaire de `db_field` : celui de Django, avec aperçu et texte gardé tel
        que saisi s'il est en Markdown."""
        if db_field.name in self.markdown_fields:
            kwargs.update(widget=MarkdownTextarea, strip=False)
        return super().formfield_for_dbfield(db_field, request, **kwargs)
