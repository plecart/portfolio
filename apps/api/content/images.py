"""L'original d'une image de projet : le fichier que l'auteur téléverse, gardé tel quel.

Seul module du dépôt qui importe Pillow (brief de #9, décision 12) : l'original y est reconnu à
son contenu, jamais à son nom (décision 6), et nommé par l'application (décision 7).
"""

from os import PathLike
from uuid import uuid4

from config import strings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models
from PIL import Image, UnidentifiedImageError

# Les formats qu'accepte un original, au nom que leur donne Pillow, et l'extension de chacun : un
# `<img>` de l'admin les affiche, et le worker de #12 les convertit (décision 6).
EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

# Borne technique, qu'aucune source ne fixe (décision 6) : 10 Mo de 1 024² octets, ceux
# qu'affiche `filesizeformat` de Django.
MAX_SIZE = 10 * 1024 * 1024


def validate_original(file: File[bytes]) -> None:
    """Refuse un original de plus de 10 Mo, ou qui n'est pas une image JPEG, PNG ou WebP.

    Le poids d'abord : un fichier trop lourd n'est pas ouvert.

    Args:
        file: le fichier téléversé, lisible depuis le début ; il le reste après la validation.

    Raises:
        ValidationError: code `image_too_large` ou `image_format_unsupported`, message du
            catalogue.
    """
    if file.size > MAX_SIZE:
        raise ValidationError(strings.IMAGE_TOO_LARGE, code="image_too_large")
    original_extension(file)


def original_extension(file: File[bytes]) -> str:
    """L'extension du format de `file`, reconnu à son contenu : `jpg`, `png` ou `webp`.

    Pillow ne lit que l'en-tête, avec les seuls décodeurs des trois formats (`formats` de
    `Image.open`) : une image d'un autre format n'est pas reconnue, quel que soit son nom. Puis
    le fichier est rembobiné : `Storage.save`, qui suit la validation, attend un fichier « ready
    to be read from the beginning » (`django/core/files/storage/base.py`).

    Args:
        file: le fichier téléversé, lisible depuis le début.

    Returns:
        L'extension, sans point.

    Raises:
        ValidationError: code `image_format_unsupported`, message du catalogue.
    """
    try:
        with Image.open(file, formats=tuple(EXTENSIONS)) as image:
            # Reconnue par l'un des trois décodeurs, l'image en porte le nom.
            return EXTENSIONS[str(image.format)]
    except UnidentifiedImageError as error:
        raise ValidationError(
            strings.IMAGE_FORMAT_UNSUPPORTED, code="image_format_unsupported"
        ) from error
    finally:
        file.seek(0)


class OriginalField(models.ImageField):
    """Le champ de l'original d'une image : `ImageField`, nommé par ce module.

    Son nom de stockage ne reprend rien de celui de l'auteur (décision 7, `generate_filename`).
    Les dimensions restent remplies par Django (`width_field`, `height_field`, décision 8).
    """

    def generate_filename(self, instance: models.Model, filename: str | PathLike[str]) -> str:
        """`images/<identifiant aléatoire>/original.<extension du format reconnu>`.

        Le nom de l'auteur est ignoré : `django-storages` écrase par défaut un objet de même nom,
        l'extension donne son type au fichier servi, et un nom neuf à chaque téléversement donne
        une adresse dont le contenu ne change jamais, qui se met en cache sans purge. Le worker de
        #12 range ses variantes où il le décide — le dossier de l'original s'y prête.

        Args:
            instance: l'image dont le téléversement s'enregistre ; son champ porte le fichier.
            filename: le nom que l'auteur a donné au fichier, ignoré.

        Returns:
            Le nom sous lequel le stockage enregistre l'original.

        Raises:
            ValidationError: code `image_format_unsupported`, pour un fichier qui n'est pas une
                image JPEG, PNG ou WebP enregistré sans validation : sans format, pas de nom, et
                rien n'est stocké.
        """
        extension = original_extension(getattr(instance, self.attname))
        return super().generate_filename(instance, f"images/{uuid4().hex}/original.{extension}")
