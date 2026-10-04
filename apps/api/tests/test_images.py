"""Tests de ce que la couverture et l'image de galerie ont en commun : l'original — le fichier que
l'auteur téléverse — et sa validation."""

import pytest
from config import strings
from content.images import validate_original
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from factories import SVG, image_upload

# La borne technique du poids (brief de #9, décision 6), écrite ici et non lue dans le code, pour
# qu'une borne changée fasse rougir ce fichier : 10 Mo de 1 024² octets.
MAX_SIZE = 10 * 1024 * 1024

# Ce qu'un original accepte : les trois formats, reconnus à leur contenu, quel que soit le nom
# que l'auteur a donné au fichier (décision 6, « jamais à son extension »).
ACCEPTED = [
    ("JPEG", image_upload("photo.jpg", image_format="JPEG")),
    ("PNG", image_upload("image.png", image_format="PNG")),
    ("WebP", image_upload("image.webp", image_format="WEBP")),
    ("PNG nommé .jpg", image_upload("image.jpg", image_format="PNG")),
    ("JPEG sans extension", image_upload("photo", image_format="JPEG")),
]

# Les formes d'un fichier qui n'est pas une image JPEG, PNG ou WebP — c'est le dénombrement qui
# compte : un fichier qui n'est pas une image, des images d'autres formats sous une extension
# admise, et un document SVG, qu'un `<img>` afficherait mais que le worker de #12 ne convertit pas.
NOT_ACCEPTED = [
    ("texte", SimpleUploadedFile("notes.png", b"Pas une image.")),
    ("GIF nommé .png", image_upload("image.png", image_format="GIF")),
    ("BMP nommé .jpg", image_upload("image.jpg", image_format="BMP")),
    ("TIFF nommé .webp", image_upload("image.webp", image_format="TIFF")),
    ("SVG nommé .png", SimpleUploadedFile("icone.png", SVG)),
]


@pytest.mark.parametrize(
    "upload", [upload for _, upload in ACCEPTED], ids=[form for form, _ in ACCEPTED]
)
def test_un_original_jpeg_png_ou_webp_est_accepte(upload: SimpleUploadedFile) -> None:
    validate_original(upload)


@pytest.mark.parametrize(
    "upload", [upload for _, upload in NOT_ACCEPTED], ids=[form for form, _ in NOT_ACCEPTED]
)
def test_un_original_qui_n_est_pas_une_image_jpeg_png_ou_webp_est_refuse(
    upload: SimpleUploadedFile,
) -> None:
    with pytest.raises(ValidationError) as refusal:
        validate_original(upload)

    assert (refusal.value.code, refusal.value.message) == (
        "image_format_unsupported",
        strings.IMAGE_FORMAT_UNSUPPORTED,
    )


def upload_of_size(size: int) -> SimpleUploadedFile:
    """Une image valide de `size` octets exactement."""
    return image_upload(padding=size - len(image_upload()))


def test_un_original_de_10_mo_est_accepte() -> None:
    validate_original(upload_of_size(MAX_SIZE))


def test_un_original_de_plus_de_10_mo_est_refuse() -> None:
    with pytest.raises(ValidationError) as refusal:
        validate_original(upload_of_size(MAX_SIZE + 1))

    assert (refusal.value.code, refusal.value.message) == (
        "image_too_large",
        strings.IMAGE_TOO_LARGE,
    )


def test_un_original_valide_reste_pret_a_etre_lu_depuis_le_debut() -> None:
    """`Storage.save` attend un fichier « ready to be read from the beginning »
    (`django/core/files/storage/base.py`) : la validation, qui lit son en-tête, le rend rembobiné.
    Le stockage sur disque rembobine de lui-même ; un autre stockage n'y est pas tenu."""
    upload = image_upload()

    validate_original(upload)

    assert upload.tell() == 0
