"""Validateurs des fichiers téléversés dans l'admin."""

from pathlib import PurePath
from xml.etree import ElementTree

from config import strings
from django.core.exceptions import ValidationError
from django.core.files import File

# La racine d'un document SVG : `svg`, dans l'espace de noms SVG. Sans lui, un navigateur
# n'affiche rien dans un `<img>`.
SVG_ROOT = "{http://www.w3.org/2000/svg}svg"


def validate_svg(file: File[bytes]) -> None:
    """Refuse tout fichier qui n'est pas un document SVG : extension `.svg`, racine `svg`.

    L'extension compte autant que le contenu : c'est d'elle que le serveur de fichiers tire le
    type `image/svg+xml`, sans lequel le navigateur n'affiche pas l'icône. Le contenu est lu par
    la bibliothèque standard (décision 11 du brief de #7) : son analyseur ne résout aucune entité
    externe, et l'expat qu'il embarque (2.7.1 mesuré, 2.4.1 au moins) écarte les expansions
    d'entités en chaîne — documentation Python, « XML vulnerabilities ».

    Args:
        file: le fichier du champ, téléversé ou déjà enregistré.

    Raises:
        ValidationError: code `icon_not_svg`, message du catalogue.
    """
    if PurePath(file.name or "").suffix.lower() != ".svg" or _root_tag(file) != SVG_ROOT:
        raise ValidationError(strings.ICON_NOT_SVG, code="icon_not_svg")


def _root_tag(file: File[bytes]) -> str | None:
    """La balise racine de `file`, ou `None` s'il ne se lit pas comme du XML.

    Lu d'un bloc — une icône pèse quelques kilo-octets —, puis rembobiné : le fichier est
    enregistré après la validation.
    """
    try:
        root = ElementTree.fromstring(file.read())
    except (ElementTree.ParseError, OSError):
        return None
    file.seek(0)
    return root.tag
