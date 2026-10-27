"""Tests du stockage des fichiers téléversés : le disque par défaut, R2 par `MEDIA_STORAGE`.

Sans aucun appel réseau : l'adresse du compte R2 vise `.invalid` (`R2_ENVIRONMENT`), et le client
boto3 du stockage est remplacé par `Stubber` pour chaque opération que le test fait jouer — une
opération non prévue lève, au lieu de partir sur le réseau.
"""

from typing import Any

import pytest
from botocore.client import BaseClient
from botocore.stub import ANY, Stubber
from config.env import Env
from config.storage import media_storage
from django.core.files.storage import FileSystemStorage, Storage, storages
from storages.backends.s3 import S3Storage  # pyright: ignore[reportMissingTypeStubs]
from test_env import R2_ENVIRONMENT, build_env, set_variables

BUCKET = R2_ENVIRONMENT["MEDIA_R2_BUCKET"]


def created_storage(env: Env) -> Storage:
    """Le stockage que Django crée pour l'entrée `default` que `env` désigne."""
    return storages.create_storage(media_storage(env))


def bucket_client(storage: Storage) -> BaseClient:
    """Le client boto3 par lequel un `S3Storage` joint son bucket, celui que `Stubber` remplace.

    `django-storages` n'est pas typé : l'attribut se lit sur `Any`.
    """
    s3: Any = storage
    return s3.connection.meta.client


@pytest.fixture
def r2_storage(monkeypatch: pytest.MonkeyPatch) -> Storage:
    """Le stockage d'un environnement R2 complet, aux valeurs factices."""
    set_variables(monkeypatch, R2_ENVIRONMENT)
    return created_storage(build_env())


def test_le_stockage_par_defaut_est_le_disque() -> None:
    assert isinstance(created_storage(build_env()), FileSystemStorage)


def test_le_stockage_r2_se_charge_sans_appel_reseau(r2_storage: Storage) -> None:
    """`S3Storage` ne joint le bucket qu'au premier fichier : une connexion tentée échouerait sur
    l'adresse `.invalid`."""
    assert isinstance(r2_storage, S3Storage)


def test_l_adresse_d_un_fichier_sur_r2_est_sur_l_hote_des_medias(r2_storage: Storage) -> None:
    """Le CDN devant le bucket public : une adresse sans signature, que l'API reflète (#10)."""
    assert r2_storage.url("images/abc/original.png") == (
        "https://media.example/images/abc/original.png"
    )


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
    où le disque lève `FileNotFoundError` — `delete_folder` n'a alors rien à supprimer."""
    with Stubber(bucket_client(r2_storage)) as bucket:
        bucket.add_response(
            "list_objects",
            {"Name": BUCKET, "Prefix": "images/abc/", "IsTruncated": False},
            {"Bucket": BUCKET, "Delimiter": "/", "Prefix": "images/abc/"},
        )
        listing = r2_storage.listdir("images/abc")

    assert listing == ([], [])
