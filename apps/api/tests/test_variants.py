"""Tests du module de conversion : l'original d'une image de galerie converti en variantes WebP,
aux largeurs de l'échelle (brief de #12, décision 6)."""

from io import BytesIO
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

import pytest
from content.models import Variant
from content.variants import make_variants
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from PIL import Image

# Orientation EXIF « pivoter de 90° dans le sens horaire pour afficher » (étiquette 0x0112).
EXIF_ORIENTATION = 0x0112
ROTATE_90_CLOCKWISE = 6

# Les entrées nommées de la décision 6, écrites en littéraux : la taille de l'original, puis la
# taille de chaque variante attendue, dans l'ordre de l'échelle.
NAMED_ENTRIES = [
    ((1300, 1300), [(320, 320), (480, 480), (720, 720), (960, 960), (1200, 1200)]),
    ((800, 600), [(320, 240), (480, 360), (720, 540), (800, 600)]),
    ((2000, 1000), [(320, 160), (480, 240), (720, 360), (960, 480), (1200, 600)]),
    ((300, 300), [(300, 300)]),
    # La couverture minimale (spec §1.11) garde sa variante d'aperçu de lien.
    ((1200, 1200), [(320, 320), (480, 480), (720, 720), (960, 960), (1200, 1200)]),
]


def encoded(image: Image.Image, image_format: str = "PNG", **options: object) -> bytes:
    """`image` encodée au format `image_format`."""
    content = BytesIO()
    image.save(content, image_format, **options)
    return content.getvalue()


def stored_original(content: bytes, extension: str = "png") -> str:
    """Enregistre `content` comme le fait l'original d'une image (décision 7 de #9) ; rend son nom
    de stockage."""
    return default_storage.save(f"images/{uuid4().hex}/original.{extension}", ContentFile(content))


def written(variant: Variant) -> Image.Image:
    """La variante telle que le stockage la tient, décodée par Pillow."""
    with default_storage.open(variant["name"]) as file:
        image = Image.open(file)
        image.load()
    return image


@pytest.mark.parametrize(
    ("size", "expected"),
    NAMED_ENTRIES,
    ids=[f"{width}x{height}" for (width, height), _ in NAMED_ENTRIES],
)
def test_l_original_donne_les_variantes_de_l_echelle_sans_agrandissement(
    size: tuple[int, int], expected: list[tuple[int, int]]
) -> None:
    """Une variante par barreau inférieur ou égal à la largeur de l'original, plus une à sa largeur
    sous 1200 px ; hauteur en proportion ; chacune un fichier WebP de ces dimensions, rangé dans le
    dossier de l'original sous sa largeur."""
    original = stored_original(encoded(Image.new("RGB", size)))
    folder = original.rsplit("/", 1)[0]

    variants = make_variants(default_storage, original)

    assert variants == [
        {"name": f"{folder}/{width}.webp", "width": width, "height": height}
        for width, height in expected
    ]
    assert [(image.format, image.size) for image in map(written, variants)] == [
        ("WEBP", dimensions) for dimensions in expected
    ]


def test_les_variantes_appliquent_l_orientation_exif_de_l_original() -> None:
    """Un JPEG de 1600 × 1200 pixels que son EXIF fait pivoter de 90° s'affiche en portrait,
    1200 × 1600 : ses variantes aussi (#9 stocke les pixels sans l'orientation)."""
    exif = Image.Exif()
    exif[EXIF_ORIENTATION] = ROTATE_90_CLOCKWISE
    original = stored_original(encoded(Image.new("RGB", (1600, 1200)), "JPEG", exif=exif), "jpg")

    variants = make_variants(default_storage, original)

    assert [(v["width"], v["height"]) for v in variants] == [
        (320, 427),
        (480, 640),
        (720, 960),
        (960, 1280),
        (1200, 1600),
    ]
    assert written(variants[-1]).size == (1200, 1600)


@pytest.mark.parametrize(
    ("mode", "image_format", "expected"),
    [("RGBA", "PNG", "RGBA"), ("RGB", "PNG", "RGB"), ("L", "PNG", "RGB"), ("RGB", "JPEG", "RGB")],
    ids=["PNG transparent", "PNG opaque", "PNG en niveaux de gris", "JPEG"],
)
def test_une_variante_garde_la_transparence_de_l_original_et_rien_d_autre(
    mode: str, image_format: str, expected: str
) -> None:
    original = stored_original(encoded(Image.new(mode, (300, 300)), image_format))

    (variant,) = make_variants(default_storage, original)

    assert written(variant).mode == expected


def test_l_original_est_identique_a_l_octet_apres_la_conversion() -> None:
    """Lu, jamais réécrit (spec §1.11)."""
    content = encoded(Image.new("RGB", (1300, 1300)))
    original = stored_original(content)

    make_variants(default_storage, original)

    with default_storage.open(original) as file:
        assert file.read() == content


class FailingStorage(FileSystemStorage):
    """Le stockage sur disque de Django, qui refuse d'enregistrer un fichier à partir du
    `failing`-ième."""

    def __init__(self, location: str, failing: int) -> None:
        super().__init__(location)
        self.remaining = failing - 1

    def save(self, name: str | None, content: IO[Any], max_length: int | None = None) -> str:
        if self.remaining == 0:
            raise OSError("stockage plein")
        self.remaining -= 1
        return super().save(name, content, max_length)


def test_une_conversion_qui_echoue_supprime_les_variantes_deja_ecrites(
    tmp_path: Path,
) -> None:
    """L'erreur sort telle quelle, et l'essai ne laisse aucun fichier : le suivant repart de rien."""
    storage = FailingStorage(str(tmp_path), failing=3)
    original = storage.save(
        "images/abc/original.png", ContentFile(encoded(Image.new("RGB", (1300, 1300))))
    )

    with pytest.raises(OSError, match="stockage plein"):
        make_variants(storage, original)

    assert storage.listdir("images/abc") == ([], ["original.png"])
