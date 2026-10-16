"""Les variantes d'une image de galerie : son original converti en WebP aux largeurs de l'échelle.

Second et dernier module de l'application, tests exclus, à importer Pillow, après celui qui lit
l'original au téléversement (`content/images.py`) : une seule chaîne d'image (brief de #12,
décision 1, ADR 0015 ; tenu par `tests/test_images.py`). L'original est lu, jamais réécrit.
"""

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

    L'orientation EXIF est appliquée avant toute mesure (#9 stocke les pixels sans elle) ;
    l'image est convertie en RGB, ou en RGBA si l'original porte une transparence, puis réduite à
    chaque largeur de `variant_widths`, hauteur en proportion arrondie, jamais recadrée (spec
    §1.11). WebP aux réglages par défaut de Pillow (qualité 80). Chaque variante est rangée dans le
    dossier de l'original sous sa largeur, `images/<identifiant>/<largeur>.webp` (décision 6) ;
    son `name` est celui que le stockage a retenu.

    Args:
        storage: le stockage qui tient l'original et recevra les variantes.
        original_name: le nom de stockage de l'original, `images/<identifiant>/original.<ext>`.

    Returns:
        Les variantes écrites, par largeur croissante.

    Raises:
        Exception: toute erreur de lecture, de décodage ou d'écriture, relancée telle quelle,
            après suppression des variantes déjà écrites : un échec ne laisse aucun fichier.
    """
    folder = original_name.rsplit("/", 1)[0]
    variants: list[Variant] = []
    try:
        with storage.open(original_name) as file, Image.open(file, formats=DECODERS) as opened:
            image = ImageOps.exif_transpose(opened)
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        for width in variant_widths(image.width):
            height = round(image.height * width / image.width)
            # `resize` admet aussi un tableau numpy, type que Pillow n'annonce que si numpy est
            # installé — il ne l'est pas : pyright le voit inconnu.
            resized = image.resize(  # pyright: ignore[reportUnknownMemberType]
                (width, height), Image.Resampling.LANCZOS
            )
            content = BytesIO()
            resized.save(content, "WEBP")
            name = storage.save(f"{folder}/{width}.webp", ContentFile(content.getvalue()))
            variants.append({"name": name, "width": width, "height": height})
    except Exception:
        for variant in variants:
            storage.delete(variant["name"])
        raise
    return variants
