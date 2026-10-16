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
from PIL import Image, ImageCms, UnidentifiedImageError

# Orientation EXIF « pivoter de 90° dans le sens horaire pour afficher » (étiquette 0x0112).
EXIF_ORIENTATION = 0x0112
ROTATE_90_CLOCKWISE = 6

# Un profil ICC valide, celui que Pillow sait créer ; `createProfile` n'est pas typé.
SRGB = ImageCms.createProfile("sRGB")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
SRGB_PROFILE: bytes = ImageCms.ImageCmsProfile(SRGB).tobytes()  # pyright: ignore[reportUnknownArgumentType]

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


def multi_frame_jpeg() -> bytes:
    """Un JPEG à deux images, que Pillow nomme « MPO » — bien des photos de téléphone."""
    first, second = Image.new("RGB", (300, 300)), Image.new("RGB", (300, 300))
    return encoded(first, "MPO", save_all=True, append_images=[second])


# Les formes d'un original que les trois décodeurs ouvrent (`DECODERS`), mesurées par sonde à la
# relecture du lot 3a : seize, dont celles-ci, chacune avec le mode de sa variante — RGBA pour
# toute transparence, palette ou couleur clé comprises, RGB pour tout le reste. Le PNG gris de
# 16 bits a son test.
MODES = [
    ("PNG transparent", encoded(Image.new("RGBA", (300, 300))), "RGBA"),
    ("PNG en palette transparente", encoded(Image.new("P", (300, 300)), transparency=0), "RGBA"),
    ("PNG à couleur clé", encoded(Image.new("RGB", (300, 300)), transparency=(0, 0, 0)), "RGBA"),
    ("PNG gris transparent", encoded(Image.new("LA", (300, 300))), "RGBA"),
    ("WebP transparent", encoded(Image.new("RGBA", (300, 300)), "WEBP"), "RGBA"),
    ("PNG opaque", encoded(Image.new("RGB", (300, 300))), "RGB"),
    ("PNG en niveaux de gris", encoded(Image.new("L", (300, 300))), "RGB"),
    ("JPEG", encoded(Image.new("RGB", (300, 300)), "JPEG"), "RGB"),
    ("JPEG CMYK", encoded(Image.new("CMYK", (300, 300)), "JPEG"), "RGB"),
    ("JPEG à plusieurs images", multi_frame_jpeg(), "RGB"),
]


@pytest.mark.parametrize(
    ("content", "expected"),
    [(content, expected) for _, content, expected in MODES],
    ids=[form for form, _, _ in MODES],
)
def test_une_variante_garde_la_transparence_de_l_original_et_rien_d_autre(
    content: bytes, expected: str
) -> None:
    """RGBA si l'original porte une transparence, sous quelque forme que ce soit ; RGB sinon
    (décision 6)."""
    (variant,) = make_variants(default_storage, stored_original(content))

    assert written(variant).mode == expected


# Les originaux dont le profil ICC suit les variantes, et ceux dont il ne suit pas : la forme,
# l'original encodé avec un profil, et si la variante le porte.
PROFILES = [
    ("JPEG RGB", encoded(Image.new("RGB", (300, 300)), "JPEG", icc_profile=SRGB_PROFILE), True),
    (
        "PNG en palette transparente",
        encoded(Image.new("P", (300, 300)), transparency=0, icc_profile=SRGB_PROFILE),
        True,
    ),
    ("JPEG CMYK", encoded(Image.new("CMYK", (300, 300)), "JPEG", icc_profile=SRGB_PROFILE), False),
    (
        "PNG en niveaux de gris",
        encoded(Image.new("L", (300, 300)), icc_profile=SRGB_PROFILE),
        False,
    ),
]


@pytest.mark.parametrize(
    ("content", "kept"),
    [(content, kept) for _, content, kept in PROFILES],
    ids=[form for form, _, _ in PROFILES],
)
def test_le_profil_de_couleur_d_un_original_rgb_suit_ses_variantes_et_aucun_autre(
    content: bytes, kept: bool
) -> None:
    """Sans son profil ICC, une photo de téléphone en Display P3 serait lue en sRGB, ses couleurs
    ternies : Pillow ne reprend pas le profil de lui-même à l'écriture d'un WebP. Une palette est
    en RGB ; un profil CMYK ou gris décrirait mal une variante RGB, qui n'en porte alors aucun."""
    (variant,) = make_variants(default_storage, stored_original(content))

    assert written(variant).info.get("icc_profile") == (SRGB_PROFILE if kept else None)


def test_un_original_tres_allonge_garde_une_hauteur_d_un_pixel() -> None:
    """5000 × 3 : la hauteur en proportion s'arrondit à zéro, que Pillow refuse ; elle vaut un
    pixel au moins."""
    original = stored_original(encoded(Image.new("RGB", (5000, 3))))

    variants = make_variants(default_storage, original)

    assert [(v["width"], v["height"]) for v in variants] == [
        (320, 1),
        (480, 1),
        (720, 1),
        (960, 1),
        (1200, 1),
    ]


def test_un_original_d_un_autre_format_n_est_pas_decode() -> None:
    """Seuls les trois décodeurs de l'original (`DECODERS`) l'ouvrent, comme au téléversement :
    un GIF rangé sous un nom d'original n'est pas converti."""
    original = stored_original(encoded(Image.new("RGB", (300, 300)), "GIF"))

    with pytest.raises(UnidentifiedImageError):
        make_variants(default_storage, original)


def test_le_nom_d_une_variante_est_celui_que_le_stockage_retient() -> None:
    """Un nom déjà pris — un essai précédent — n'est pas écrasé par le stockage sur disque : la
    variante porte le nom qu'il a choisi, et l'ancien fichier reste ce qu'il était."""
    original = stored_original(encoded(Image.new("RGB", (300, 300))))
    taken = default_storage.save(f"{original.rsplit('/', 1)[0]}/300.webp", ContentFile(b"ancien"))

    (variant,) = make_variants(default_storage, original)

    assert variant["name"] != taken
    assert (written(variant).format, written(variant).size) == ("WEBP", (300, 300))
    with default_storage.open(taken) as file:
        assert file.read() == b"ancien"


def test_un_png_de_16_bits_garde_ses_niveaux_de_gris() -> None:
    """Pillow ouvre un PNG gris de 16 bits en entiers (`I;16`) et les écrête à 255 en passant en
    RGB (mesuré : 30 000 devenait blanc) ; la variante garde le gris de l'original, 30 000 / 256,
    à la perte du WebP près."""
    original = stored_original(encoded(Image.new("I;16", (300, 300), 30000)))

    (variant,) = make_variants(default_storage, original)

    level = written(variant).convert("L").getpixel((150, 150))
    assert isinstance(level, int) and abs(level - 117) <= 2, level


def test_l_original_est_identique_a_l_octet_apres_la_conversion() -> None:
    """Lu, jamais réécrit (spec §1.11)."""
    content = encoded(Image.new("RGB", (1300, 1300)))
    original = stored_original(content)

    make_variants(default_storage, original)

    with default_storage.open(original) as file:
        assert file.read() == content


def folder_files(storage: FileSystemStorage) -> list[str]:
    """Les fichiers du dossier `images/abc` de `storage`, triés : `listdir` les rend dans l'ordre du
    système de fichiers — trié sous NTFS, pas sous ext4 (rouge en CI seulement, mesuré)."""
    folders, files = storage.listdir("images/abc")
    assert folders == []
    return sorted(files)


class Interrupted(BaseException):
    """Une interruption qui n'est pas une `Exception` — l'arrêt du worker, par exemple."""


class FailingStorage(FileSystemStorage):
    """Le stockage sur disque de Django, dont le `failing`-ième enregistrement échoue comme
    `failure` le dit, et qui refuse de supprimer les noms de `undeletable`."""

    def __init__(
        self, location: str, failing: int, failure: str, undeletable: frozenset[str] = frozenset()
    ) -> None:
        super().__init__(location)
        self.remaining = failing - 1
        self.failure = failure
        self.undeletable = undeletable

    def save(self, name: str | None, content: IO[Any], max_length: int | None = None) -> str:
        if self.remaining:
            self.remaining -= 1
            return super().save(name, content, max_length)
        if self.failure == "avant l'écriture":
            raise OSError("stockage plein")
        if self.failure == "interruption":
            raise Interrupted
        super().save(name, content, max_length)  # le fichier est écrit, son nom n'est pas rendu
        raise OSError("stockage plein")

    def delete(self, name: str) -> None:
        if name in self.undeletable:
            raise OSError("suppression refusée")
        super().delete(name)


# Les chemins par lesquels un essai qui échoue après avoir écrit pourrait laisser un fichier —
# recensés à la relecture du lot 3a, avant le correctif : cinq, dont trois fuyaient (l'écriture
# qui échoue après avoir créé son fichier, la suppression qui échoue pendant le nettoyage, une
# interruption qui n'est pas une `Exception`) ; la relance en a rendu un sixième, l'écriture qui
# échoue sous un nom déjà pris — un orphelin qu'une suppression a refusé. Une erreur avant toute
# écriture — lecture, décodage — n'écrit rien : `test_un_original_d_un_autre_format_n_est_pas_decode`.
# Reste ouvert, et le seul : un écrivain concurrent qui prend le nom réservé entre la réservation
# et l'écriture, exclu par la concurrence 1 du worker et un dossier par original (décision 9).
# Chaque forme : le chemin, l'échec, le rang de l'enregistrement qui échoue — l'original est le
# premier —, le nom déjà pris dans le dossier, et l'erreur attendue.
FAILURES: list[tuple[str, str, int, str | None, type[BaseException]]] = [
    ("enregistrement refusé avant l'écriture", "avant l'écriture", 4, None, OSError),
    ("enregistrement qui échoue après l'écriture", "après l'écriture", 4, None, OSError),
    ("interruption", "interruption", 4, None, Interrupted),
    ("échec après l'écriture sous un nom déjà pris", "après l'écriture", 3, "320.webp", OSError),
]


@pytest.mark.parametrize(
    ("failure", "failing", "taken", "error"),
    [(failure, failing, taken, error) for _, failure, failing, taken, error in FAILURES],
    ids=[path for path, *_ in FAILURES],
)
def test_une_conversion_qui_echoue_ne_laisse_aucune_variante(
    tmp_path: Path, failure: str, failing: int, taken: str | None, error: type[BaseException]
) -> None:
    """L'erreur sort telle quelle, et l'essai ne laisse aucun fichier : le suivant repart de rien.
    Un fichier qui était là avant l'essai reste, intact."""
    storage = FailingStorage(str(tmp_path), failing=failing, failure=failure)
    original = storage.save(
        "images/abc/original.png", ContentFile(encoded(Image.new("RGB", (1300, 1300))))
    )
    kept = [taken] if taken else []
    for name in kept:
        storage.save(f"images/abc/{name}", ContentFile(b"ancien"))

    with pytest.raises(error):
        make_variants(storage, original)

    assert folder_files(storage) == sorted([*kept, "original.png"])
    for name in kept:
        with storage.open(f"images/abc/{name}") as file:
            assert file.read() == b"ancien"


def test_une_suppression_qui_echoue_n_empeche_pas_les_autres_ni_ne_masque_l_erreur(
    tmp_path: Path,
) -> None:
    """Le nettoyage ne se laisse arrêter par aucune suppression : la variante qui résiste reste,
    les autres sortent, et l'erreur qui sort est celle de la conversion."""
    storage = FailingStorage(
        str(tmp_path),
        failing=4,
        failure="avant l'écriture",
        undeletable=frozenset({"images/abc/320.webp"}),
    )
    original = storage.save(
        "images/abc/original.png", ContentFile(encoded(Image.new("RGB", (1300, 1300))))
    )

    with pytest.raises(OSError, match="stockage plein"):
        make_variants(storage, original)

    assert folder_files(storage) == ["320.webp", "original.png"]
