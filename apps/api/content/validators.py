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
    externe, et l'expat de l'image, où l'admin tourne (2.8.3, mesuré le 2026-09-26), dépasse le
    seuil de 2.7.2 sous lequel la documentation Python le dit exposé aux expansions d'entités
    (« XML security »).

    Un fichier déjà stocké n'est pas relu : il a été validé à son arrivée, et sur R2 chaque lecture
    serait un téléchargement — un objet absent du bucket refuserait une modification sans rapport.

    Args:
        file: le fichier du champ : validé s'il est téléversé, ignoré s'il est déjà stocké.

    Raises:
        ValidationError: code `icon_not_svg`, message du catalogue.
    """
    # `_committed`, posé par `FieldFile` : vrai pour le fichier que le stockage tient déjà, faux
    # pour un téléversement, absent d'un fichier hors de tout champ — le concept de
    # `OriginalFile.stored` (`content/images.py`).
    if getattr(file, "_committed", False):
        return
    if PurePath(file.name or "").suffix.lower() != ".svg" or _root_tag(file) != SVG_ROOT:
        raise ValidationError(strings.ICON_NOT_SVG, code="icon_not_svg")


def _root_tag(file: File[bytes]) -> str | None:
    """La balise racine de `file`, ou `None` s'il ne se lit pas comme du XML.

    Lu d'un bloc, sans borne de taille : seul le compte de l'admin téléverse, et une icône pèse
    quelques kilo-octets. Puis rembobiné : `Storage.save`, qui suit la validation, attend un
    fichier « ready to be read from the beginning » (`django/core/files/storage/base.py`) — le
    stockage sur disque le tolère, un autre stockage n'y est pas tenu.
    """
    try:
        root = ElementTree.fromstring(file.read())
    except (ElementTree.ParseError, OSError):
        return None
    file.seek(0)
    return root.tag
