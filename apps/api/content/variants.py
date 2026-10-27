"""Les variantes d'une image de galerie : son original converti en WebP aux largeurs de l'échelle.

Second et dernier module de l'application, tests exclus, à importer Pillow, après celui qui lit
l'original au téléversement (`content/images.py`) : une seule chaîne d'image (brief de #12,
décision 1, ADR 0015 ; tenu par `tests/test_images.py`). L'original est lu, jamais réécrit.
"""

from contextlib import suppress
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from PIL import Image, ImageOps

from content.images import DECODERS
from content.models import Variant

# L'échelle des largeurs, en pixels, source unique (décision 6) : la photo de carte de 160 à
# 480 px CSS (spec §4.1), la galerie jusqu'à 660 px (spec §3.2), chaque largeur doublée pour les
# écrans denses, et l'aperçu de lien de 1200 px (spec §1.11, ADR 0011), qui plafonne tout.
VARIANT_WIDTHS = (320, 480, 720, 960, 1200)

# Les modes d'un original dont le profil ICC décrit aussi ses variantes, RGB ou RGBA.
RGB_MODES = ("RGB", "RGBA", "P")


def variant_widths(width: int) -> list[int]:
    """Les largeurs des variantes d'un original large de `width` pixels, croissantes.

    Chaque barreau de l'échelle inférieur ou égal à `width`, plus `width` elle-même si elle est
    sous le dernier barreau sans en être un : jamais d'agrandissement, toujours une variante au
    moins.

    Args:
        width: la largeur de l'original, orientation EXIF appliquée.

    Returns:
        Les largeurs, sans doublon. Exemples : 800 → `[320, 480, 720, 800]` ; 300 → `[300]` ;
        1300 → l'échelle entière.
    """
    widths = [rung for rung in VARIANT_WIDTHS if rung <= width]
    if width < VARIANT_WIDTHS[-1] and width not in widths:
        widths.append(width)
    return widths


def make_variants(storage: Storage, original_name: str) -> list[Variant]:
    """Écrit dans `storage` les variantes WebP de l'original `original_name` ; rend leur liste.

    L'original est lu par `read_original`, puis réduit à chaque largeur de `variant_widths`,
    hauteur en proportion arrondie — un pixel au moins —, jamais recadré (spec §1.11), et encodé
    par `encode_variant`. Chaque variante est rangée dans le dossier de l'original sous sa
    largeur, `images/<identifiant>/<largeur>.webp` (décision 6) ; son `name` est celui que le
    stockage a retenu (`get_available_name`), un autre si le nom est pris — sur le disque comme
    sur R2, réglé pour ne pas écraser (`config/storage.py`) : le nettoyage d'un échec ne vise
    jamais un fichier antérieur.

    Args:
        storage: le stockage qui tient l'original et recevra les variantes.
        original_name: le nom de stockage de l'original, `images/<identifiant>/original.<ext>`.

    Returns:
        Les variantes écrites, par largeur croissante.

    Raises:
        BaseException: toute erreur de lecture, de décodage ou d'écriture — interruption
            comprise —, relancée telle quelle après suppression de chaque fichier que l'essai a
            visé, écrit ou non : un échec ne laisse aucune variante, sauf celle qu'une
            suppression refuse.
    """
    folder = original_name.rsplit("/", 1)[0]
    variants: list[Variant] = []
    attempted: list[str] = []
    try:
        image, profile = read_original(storage, original_name)
        for width in variant_widths(image.width):
            height = max(1, round(image.height * width / image.width))
            # Le nom réservé avant l'écriture : un enregistrement qui échoue après avoir créé son
            # fichier ne rend pas le nom qu'il a pris.
            attempted.append(storage.get_available_name(f"{folder}/{width}.webp"))
            content = ContentFile(encode_variant(image, width, height, profile))
            name = storage.save(attempted[-1], content)
            variants.append({"name": name, "width": width, "height": height})
    except BaseException:
        for name in {*attempted, *(variant["name"] for variant in variants)}:
            # Une suppression qui échoue laisse son fichier, sans masquer l'erreur de l'essai ni
            # arrêter les suivantes.
            with suppress(Exception):
                storage.delete(name)
        raise
    return variants


def read_original(storage: Storage, original_name: str) -> tuple[Image.Image, bytes | None]:
    """L'original `original_name`, lu dans `storage`, prêt à réduire : orienté, en RGB ou RGBA ;
    et le profil ICC de ses couleurs, s'il en porte un qui vaut pour une image RGB.

    Seuls les décodeurs de l'original l'ouvrent (`DECODERS`), comme au téléversement.
    L'orientation EXIF est appliquée avant toute mesure (#9 stocke les pixels sans elle). L'image
    est convertie en RGBA si l'original porte une transparence — canal alpha, palette ou couleur
    clé —, en RGB sinon (décision 6). Le profil ICC suit : Pillow ne le reprend pas de lui-même
    dans un WebP, et sans lui une photo en Display P3 serait lue en sRGB, ternie. Celui d'un
    original CMYK ou gris ne décrirait pas une variante RGB : il est laissé. Ni l'EXIF ni le XMP
    ne suivent (`PIL/WebPImagePlugin.py`, qui ne lit que les options d'écriture).

    Args:
        storage: le stockage qui tient l'original.
        original_name: son nom de stockage.

    Returns:
        L'image, chargée, et le profil, ou `None`.

    Raises:
        Exception: une erreur de lecture du stockage ou de décodage de Pillow.
    """
    with storage.open(original_name) as file, Image.open(file, formats=DECODERS) as opened:
        image = ImageOps.exif_transpose(opened)
    profile = image.info.get("icc_profile") if image.mode in RGB_MODES else None
    if image.mode.startswith("I"):
        # Un PNG gris de 16 bits s'ouvre en entiers, qu'une conversion directe écrête à 255 — en L
        # comme en RGB, Pillow 12.3 mesuré : ramenés d'abord à 0–255 (le mode reste `I`, `point`
        # ignorant le mode cible pour une fonction). `point` admet aussi un tableau numpy, que
        # pyright voit inconnu, numpy n'étant pas installé ; de même pour `resize`.
        image = image.convert("I")
        image = image.point(lambda value: value / 256)  # pyright: ignore[reportUnknownMemberType]
    return image.convert("RGBA" if image.has_transparency_data else "RGB"), profile


def encode_variant(image: Image.Image, width: int, height: int, profile: bytes | None) -> bytes:
    """`image` réduite à `width` × `height` pixels (LANCZOS), encodée en WebP aux réglages par
    défaut de Pillow (qualité 80), avec le profil ICC `profile` s'il y en a un.

    Args:
        image: l'original lu par `read_original`.
        width, height: les dimensions de la variante, en pixels, un au moins chacune.
        profile: le profil ICC à embarquer, ou `None`.

    Returns:
        Le fichier WebP.
    """
    resized = image.resize(  # pyright: ignore[reportUnknownMemberType]
        (width, height), Image.Resampling.LANCZOS
    )
    content = BytesIO()
    resized.save(content, "WEBP", icc_profile=profile)
    return content.getvalue()
