"""Tests du retrait des fichiers stockés (`content/stored_files.py`) : un fichier qu'une ligne ne
nomme plus — la ligne supprimée, ou son fichier remplacé — sort du stockage une fois la transaction
validée, pour chaque champ fichier du projet.

L'icône d'une technologie y est éprouvée en entier ; l'image de galerie, qui retire le dossier de
son original et remet l'image en attente, l'est dans `test_images.py` et `test_tasks.py`.
"""

from collections.abc import Callable
from pathlib import PurePosixPath

import pytest
from content.models import GalleryImage, ProjectTechnology, Technology
from django.apps import apps
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models, transaction
from django.db.models import ProtectedError
from django.db.models.fields.files import FieldFile
from factories import gallery_image, project, saved, svg_icon, technology
from pytest_django import DjangoCaptureOnCommitCallbacks
from test_tasks import Rollback

# Chaque champ fichier du projet, recensé à chaque exécution parmi les champs de tous les modèles :
# un champ ajouté entre de lui-même dans les tests qui le parcourent.
FILE_FIELDS = [
    (model, field.name)
    for model in apps.get_models()
    for field in model._meta.get_fields()
    if isinstance(field, models.FileField)
]

# Une ligne enregistrée et valide de chaque modèle qui porte un fichier, faite par sa fabrique.
ROWS: dict[type[models.Model], Callable[[], models.Model]] = {
    Technology: lambda: saved(technology()),
    GalleryImage: lambda: saved(gallery_image(saved(project()))),
}


def file_of(row: models.Model, field: str) -> FieldFile:
    """Le fichier que `row` tient dans son champ `field`."""
    file: FieldFile = getattr(row, field)
    return file


def stored(file: FieldFile) -> bool:
    """Si le stockage de `file` le tient."""
    return file.storage.exists(file.name or "")


def delete_row(row: models.Model, field: str) -> None:
    """Supprime `row` : son fichier `field` n'est plus nommé."""
    row.delete()


def replace_file(row: models.Model, field: str) -> None:
    """Remplace le fichier `field` de `row` par un téléversement de même contenu, puis l'enregistre :
    le fichier remplacé n'est plus nommé. Le contenu est relu dans le stockage : celui que la
    fabrique y a mis, valide pour le champ."""
    file = file_of(row, field)
    with file.storage.open(file.name or "") as content:
        upload = SimpleUploadedFile(PurePosixPath(file.name or "").name, content.read())
    setattr(row, field, upload)
    row.save()


def test_chaque_modele_qui_porte_un_fichier_a_sa_ligne_de_fabrique() -> None:
    """Le recensement des champs fichier n'est jamais vide, et chaque modèle qui en porte un a sa
    ligne de fabrique : sans elle, son retrait ne serait pas éprouvé."""
    assert {model for model, _ in FILE_FIELDS} == set(ROWS)


@pytest.mark.django_db
@pytest.mark.parametrize("withdraw", [delete_row, replace_file], ids=["supprimé", "remplacé"])
@pytest.mark.parametrize(
    ("model", "field"),
    FILE_FIELDS,
    ids=[f"{model._meta.label}.{field}" for model, field in FILE_FIELDS],
)
def test_un_fichier_qu_une_ligne_ne_nomme_plus_sort_du_stockage(
    model: type[models.Model],
    field: str,
    withdraw: Callable[[models.Model, str], None],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Chaque champ fichier du projet, éprouvé par ce qu'il fait — sa ligne supprimée, son fichier
    remplacé —, jamais par la classe du modèle : un champ ajouté sans son retrait rougit ici."""
    row = ROWS[model]()
    withdrawn = file_of(row, field)

    with django_capture_on_commit_callbacks(execute=True):
        withdraw(row, field)

    assert not stored(withdrawn)


@pytest.mark.django_db
def test_supprimer_une_technologie_retire_son_icone_du_stockage_apres_la_transaction(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Le bucket des icônes est public (ADR 0004) : une icône retirée resterait servie."""
    made = saved(technology())

    with django_capture_on_commit_callbacks(execute=True):
        made.delete()
        assert stored(made.icon)

    assert not stored(made.icon)


@pytest.mark.django_db
def test_une_suppression_de_technologie_annulee_garde_son_icone(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    made = saved(technology())

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(Rollback),
        transaction.atomic(),
    ):
        made.delete()
        raise Rollback

    assert stored(made.icon)


@pytest.mark.django_db
def test_une_panne_du_stockage_ne_fait_pas_echouer_la_suppression_d_une_technologie(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La ligne est déjà supprimée quand l'icône sort du stockage : un stockage qui refuse ne fait
    rien remonter à la requête, et la ligne reste supprimée."""
    made = saved(technology())
    attempts: list[str] = []

    def failing_delete(storage: FileSystemStorage, name: str) -> None:
        attempts.append(name)
        raise OSError("panne du stockage")

    monkeypatch.setattr(FileSystemStorage, "delete", failing_delete)

    with django_capture_on_commit_callbacks(execute=True):
        made.delete()

    assert attempts == [made.icon.name]
    assert not Technology.objects.exists()


def replacing_icon(made: Technology) -> Technology:
    """Une instance de la ligne de `made`, lue en base, à qui une nouvelle icône est affectée."""
    loaded = Technology.objects.get(pk=made.pk)
    loaded.icon = svg_icon("nouvelle.svg")
    return loaded


@pytest.mark.django_db
def test_remplacer_l_icone_d_une_technologie_retire_l_ancienne_apres_la_transaction(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    made = saved(technology())
    loaded = replacing_icon(made)

    with django_capture_on_commit_callbacks(execute=True):
        loaded.save()
        assert stored(made.icon)

    assert not stored(made.icon)
    assert stored(loaded.icon)


@pytest.mark.django_db
def test_un_remplacement_d_icone_annule_garde_l_ancienne(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    made = saved(technology())
    loaded = replacing_icon(made)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(Rollback),
        transaction.atomic(),
    ):
        loaded.save()
        raise Rollback

    assert stored(made.icon)


@pytest.mark.django_db
@pytest.mark.parametrize("withdraw", [delete_row, replace_file], ids=["supprimée", "remplacée"])
def test_une_icone_que_nomme_une_autre_technologie_reste_dans_le_stockage(
    withdraw: Callable[[models.Model, str], None],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Deux lignes peuvent nommer un même fichier — un nom affecté, une ligne copiée : celle qui
    ne le nomme plus ne le retire pas à l'autre."""
    made = saved(technology())
    other = saved(technology(name="Flask", icon=made.icon.name))

    with django_capture_on_commit_callbacks(execute=True):
        withdraw(made, "icon")

    assert stored(other.icon)


@pytest.mark.django_db
def test_une_technologie_employee_par_un_projet_garde_son_icone(
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Django refuse la suppression (`PROTECT`) en recensant les lignes à supprimer, avant tout
    signal (`Collector.collect`, puis `Collector.delete`) : aucun retrait n'est enregistré, rien ne
    part une fois la transaction validée."""
    made = saved(technology())
    saved(ProjectTechnology(project=saved(project()), technology=made, position=1))

    with django_capture_on_commit_callbacks(execute=True), pytest.raises(ProtectedError):
        made.delete()

    assert stored(made.icon)
