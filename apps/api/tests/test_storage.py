"""Tests du stockage R2 des fichiers téléversés : ce que le domaine attend de `django-storages`.

Le choix du stockage par `MEDIA_STORAGE`, et l'adresse d'un fichier sur chacun, s'éprouvent dans
un processus neuf, comme `settings.py` les pose (`test_django_project.py`). Ici, sans aucun appel
réseau : l'adresse du compte R2 vise `.invalid` (`R2_ENVIRONMENT`), et le client boto3 du stockage
est remplacé par `Stubber` pour chaque opération que le test fait jouer — une opération non prévue
lève, au lieu de partir sur le réseau.
"""

import mimetypes
from io import BytesIO
from typing import Any

import pytest
from botocore.client import BaseClient
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from config.storage import media_storage
from content.variants import make_variants
from django.core.files.storage import Storage, storages
from PIL import Image
from test_env import R2_ENVIRONMENT, build_env, set_variables
from test_variants import encoded

BUCKET = R2_ENVIRONMENT["MEDIA_R2_BUCKET"]


def bucket_client(storage: Storage) -> BaseClient:
    """Le client boto3 par lequel un `S3Storage` joint son bucket, celui que `Stubber` remplace.

    `django-storages` n'est pas typé : l'attribut se lit sur `Any`.
    """
    s3: Any = storage
    return s3.connection.meta.client


def guess_no_type(url: str, strict: bool = True) -> tuple[None, None]:
    """`mimetypes.guess_type` sur une table qui ne connaît aucune extension."""
    return None, None


@pytest.fixture
def r2_storage(monkeypatch: pytest.MonkeyPatch) -> Storage:
    """Le stockage que Django crée pour un environnement R2 complet, aux valeurs factices."""
    set_variables(monkeypatch, R2_ENVIRONMENT)
    return storages.create_storage(media_storage(build_env()))


def test_deux_fichiers_de_meme_nom_ne_s_ecrasent_pas_sur_r2(r2_storage: Storage) -> None:
    """`django-storages` écrase par défaut (`file_overwrite`) : deux technologies dont l'icône
    s'appelle `logo.svg` partageraient un objet, et le nettoyage d'une conversion qui échoue
    (`make_variants`) supprimerait un fichier antérieur de même nom. Un nom pris en rend un autre."""
    with Stubber(bucket_client(r2_storage)) as bucket:
        bucket.add_response("head_object", {}, {"Bucket": BUCKET, "Key": "technologies/logo.svg"})
        bucket.add_client_error(
            "head_object", http_status_code=404, expected_params={"Bucket": BUCKET, "Key": ANY}
        )
        name = r2_storage.get_available_name("technologies/logo.svg")

    assert name != "technologies/logo.svg"


def test_le_dossier_absent_d_une_image_se_liste_vide_sur_r2(r2_storage: Storage) -> None:
    """Un bucket n'a pas de dossiers : `listdir` d'un préfixe sans objet rend deux listes vides, là
    où le disque lève `FileNotFoundError` — `delete_folder` n'a alors rien à supprimer.

    `listdir` appelle `ListObjects` v1 (`list_objects`), que R2 sert : « Improved S3 compatibility
    for ListObjectsV1 » (notes de version de R2, 2023-06-16)."""
    with Stubber(bucket_client(r2_storage)) as bucket:
        bucket.add_response(
            "list_objects",
            {"Name": BUCKET, "Prefix": "images/abc/", "IsTruncated": False},
            {"Bucket": BUCKET, "Delimiter": "/", "Prefix": "images/abc/"},
        )
        listing = r2_storage.listdir("images/abc")

    assert listing == ([], [])


def test_une_variante_arrive_sur_r2_sous_le_type_webp(
    r2_storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2 sert un objet sous le type reçu à l'envoi, que `django-storages` devine d'après le nom
    quand le fichier n'en porte pas (`_get_write_parameters`). Python 3.12 ignore `.webp`, et
    l'image d'`api` n'a pas de table du système (mesuré) : la devinette est neutralisée ici, pour
    que le test dise la même chose sur tout poste."""
    monkeypatch.setattr(mimetypes, "guess_type", guess_no_type)
    original = encoded(Image.new("RGB", (300, 300)))

    with Stubber(bucket_client(r2_storage)) as bucket:
        # L'original : sa présence (`S3File`), sa taille, puis son contenu (s3transfer).
        bucket.add_response("head_object", {"ContentLength": len(original)})
        bucket.add_response("head_object", {"ContentLength": len(original)})
        bucket.add_response("get_object", {"Body": StreamingBody(BytesIO(original), len(original))})
        # Le nom de la variante, libre à sa réservation puis à son enregistrement.
        bucket.add_client_error("head_object", http_status_code=404)
        bucket.add_client_error("head_object", http_status_code=404)
        bucket.add_response(
            "put_object",
            {},
            {
                "Bucket": BUCKET,
                "Key": "images/abc/300.webp",
                "Body": ANY,
                # Ajouté par s3transfer (mesuré) ; hors du sujet de ce test.
                "ChecksumAlgorithm": ANY,
                "ContentType": "image/webp",
            },
        )
        make_variants(r2_storage, "images/abc/original.png")

        bucket.assert_no_pending_responses()
