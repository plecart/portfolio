"""L'original d'une image de projet : le fichier que l'auteur téléverse, gardé tel quel.

Seul module de l'application, tests exclus, qui importe Pillow (brief de #9, décision 12 ; tenu
par `tests/test_images.py`). L'original y est reconnu à son contenu, jamais à son nom
(décision 6), nommé par l'application (décision 7), jamais relu une fois stocké (décision 9), et
retiré du stockage après la transaction qui le remplace ou supprime son image (décision 10).
"""

from collections.abc import Iterable
from functools import partial
from typing import TYPE_CHECKING, Any, Self, overload
from uuid import uuid4

from config import strings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.storage import Storage
from django.db import models, transaction
from django.db.models.fields.files import ImageFieldFile, ImageFileDescriptor
from PIL import Image, UnidentifiedImageError

# Les décodeurs qu'ouvre Pillow, au nom de leur greffon : ceux des formats qu'accepte un original
# — un `<img>` de l'admin les affiche, et le worker de #12 les convertit (décision 6).
DECODERS = ("JPEG", "PNG", "WEBP")

# L'extension de chaque format que ces décodeurs reconnaissent. Le décodeur JPEG rend « MPO » pour
# un JPEG à plusieurs images — une photo de téléphone, souvent : un fichier JPEG, dont la première
# image est l'image principale.
EXTENSIONS = {"JPEG": "jpg", "MPO": "jpg", "PNG": "png", "WEBP": "webp"}

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


def original_extension(file: File[Any]) -> str:
    """L'extension du format de `file`, reconnu à son contenu : `jpg`, `png` ou `webp`.

    Pillow ne lit que l'en-tête, avec les seuls décodeurs des trois formats (`formats` de
    `Image.open`) : une image d'un autre format n'est pas reconnue, quel que soit son nom. Puis
    le fichier est rembobiné : `Storage.save`, qui suit la validation, attend un fichier « ready
    to be read from the beginning » (`django/core/files/storage/base.py`).

    La restriction vaut pour cette lecture seulement : Django lit les dimensions d'un
    téléversement (`get_image_dimensions`) et le champ de formulaire de l'admin l'ouvre
    (`forms.ImageField`) avec tous les décodeurs de Pillow — limite connue de la décision 6.

    Args:
        file: le fichier téléversé, lisible depuis le début.

    Returns:
        L'extension, sans point.

    Raises:
        ValidationError: code `image_format_unsupported` pour un fichier que ces décodeurs ne
            reconnaissent pas, ou dans un format qui n'a pas d'extension ici ;
            `image_too_many_pixels` pour une image dont l'en-tête annonce plus de pixels que
            Pillow n'accepte d'en décoder (`DecompressionBombError`, deux fois
            `Image.MAX_IMAGE_PIXELS`) — une bombe de décompression, qu'un fichier de quelques
            kilo-octets suffit à porter. Messages du catalogue.
    """
    try:
        with Image.open(file, formats=DECODERS) as image:
            extension = EXTENSIONS.get(str(image.format))
    except UnidentifiedImageError as error:
        raise unsupported() from error
    except Image.DecompressionBombError as error:
        raise ValidationError(
            strings.IMAGE_TOO_MANY_PIXELS, code="image_too_many_pixels"
        ) from error
    finally:
        file.seek(0)
    if extension is None:
        raise unsupported()
    return extension


def unsupported() -> ValidationError:
    """Le refus d'un fichier qui n'est pas une image JPEG, PNG ou WebP."""
    return ValidationError(strings.IMAGE_FORMAT_UNSUPPORTED, code="image_format_unsupported")


class OriginalFile(ImageFieldFile):
    """L'original tel que le modèle le tient : un fichier téléversé, ou celui que le stockage
    garde déjà."""

    # Posé par `FieldFile`, absent des annotations de django-stubs.
    _committed: bool

    @property
    def stored(self) -> bool:
        """Vrai si le stockage tient déjà ce fichier — faux pour un téléversement à enregistrer,
        et pour une image sans fichier."""
        return bool(self) and self._committed

    def save(self, name: str, content: File[Any], save: bool = True) -> None:
        """Enregistre `content` sous un nom engendré : `images/<identifiant aléatoire>/original.
        <extension du format reconnu>` (décision 7).

        Le nom de l'auteur, `name`, est ignoré : `django-storages` écrase par défaut un objet de
        même nom, l'extension donne son type au fichier servi, et un nom neuf à chaque
        téléversement donne une adresse dont le contenu ne change jamais, qui se met en cache sans
        purge. Le worker de #12 range ses variantes où il le décide — le dossier de l'original s'y
        prête.

        Le format se lit dans `content`, le fichier qui s'enregistre — jamais dans l'original déjà
        stocké : c'est le chemin de l'enregistrement du modèle (`FileField.pre_save`) comme d'un
        appel direct.

        Args:
            name: le nom que l'auteur a donné au fichier, ignoré.
            content: le fichier à enregistrer, lisible depuis le début.
            save: enregistrer aussi l'image, comme chez Django.

        Raises:
            ValidationError: refus d'`original_extension`, pour un fichier enregistré sans
                validation : sans format, pas de nom, et rien n'est stocké.
        """
        stored_name = f"images/{uuid4().hex}/original.{original_extension(content)}"
        # Django lit les dimensions dans `content`, qu'il tient pour vide sans nom : un
        # `ContentFile` anonyme, l'usage documenté, laisserait la largeur et la hauteur nulles.
        content.name = content.name or stored_name
        super().save(stored_name, content, save)


class OriginalField(models.ImageField):
    """Le champ de l'original d'une image : `ImageField`, nommé par ce module, et qui ne relit
    jamais un fichier stocké.

    Son nom de stockage ne reprend rien de celui de l'auteur (décision 7, `OriginalFile.save`).
    Les dimensions restent remplies par Django (`width_field`, `height_field`, décision 8), depuis
    le téléversement seulement.

    Un fichier stocké n'est jamais relu (décision 9) : sur R2, chaque lecture serait un
    téléchargement. Django, lui, relit l'original stocké à chaque réaffectation du champ — et
    `full_clean()` en fait une, comme le formulaire de l'admin (`Model.clean_fields`,
    `ImageFileDescriptor.__set__`, qui force `update_dimension_fields`). Ici, un fichier stocké
    garde ses colonnes, et ses validateurs ne s'appliquent qu'à un téléversement.
    """

    attr_class = OriginalFile

    if TYPE_CHECKING:
        # Ce que l'attribut du modèle rend, `attr_class` : django-stubs ne le déduit pas d'une
        # sous-classe, et typerait `image.original` en `ImageFieldFile`.
        @overload
        def __get__(self, instance: None, owner: Any) -> ImageFileDescriptor: ...
        @overload
        def __get__(self, instance: models.Model, owner: Any) -> OriginalFile: ...
        @overload
        def __get__(self, instance: Any, owner: Any) -> Self: ...
        def __get__(self, instance: Any, owner: Any) -> Any: ...

    def run_validators(self, value: OriginalFile) -> None:
        """Les validateurs du champ, sur un téléversement seulement : un fichier stocké a été validé
        à son arrivée."""
        if not value.stored:
            super().run_validators(value)

    def update_dimension_fields(
        self, instance: models.Model, force: bool = False, *args: object, **kwargs: object
    ) -> None:
        """Les dimensions de Django, lues dans un téléversement ; celles d'un fichier stocké restent
        celles de ses colonnes. Un champ différé n'est pas lu non plus, comme chez Django."""
        if self.attname in instance.__dict__ and getattr(instance, self.attname).stored:
            return
        super().update_dimension_fields(instance, force, *args, **kwargs)


def delete_after_commit(storage: Storage, names: Iterable[str]) -> None:
    """Supprime `names` de `storage` une fois la transaction en cours validée — aussitôt hors de
    toute transaction ; aucun si elle est annulée (doc Django, « Performing actions after
    commit »).

    Un rappel par fichier, chacun `robust` : la ligne est déjà validée quand il s'exécute, une
    panne du stockage sur un fichier est journalisée (`django.db.backends.base`) sans empêcher les
    suivants ni faire échouer la requête qui a validé.

    Args:
        storage: le stockage qui tient les fichiers.
        names: leurs noms de stockage.
    """
    for name in names:
        transaction.on_commit(partial(storage.delete, name), robust=True)
