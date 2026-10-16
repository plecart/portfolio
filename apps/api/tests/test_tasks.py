"""Tests du worker d'images : la tâche enfilée après la validation de la transaction qui crée une
image ou remplace son original, ses réessais, son écriture conditionnelle (brief de #12,
décisions 5, 7 et 8). Les tâches s'exécutent dans le processus de test (`conftest`,
`synchronous_tasks`) : un rappel `on_commit` exécuté par le test enfile, donc traite, aussitôt."""

from collections.abc import Callable
from typing import Any

import pytest
from config.celery import app as celery_app
from content import tasks
from content.models import GalleryImage, ProcessingState, Project, Variant
from content.tasks import process_image
from content.variants import make_variants
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.db import transaction
from factories import gallery_image, image_upload, project, saved
from kombu.exceptions import OperationalError
from PIL import UnidentifiedImageError
from pytest_django import DjangoCaptureOnCommitCallbacks

# Les largeurs des variantes d'un carré de 1200 px, l'image de la fabrique (décision 6).
SQUARE_WIDTHS = [320, 480, 720, 960, 1200]


@pytest.fixture
def portfolio() -> Project:
    """Le projet de la fabrique, enregistré."""
    return saved(project())


def variant_files(made: GalleryImage) -> list[str]:
    """Les fichiers que le stockage tient dans le dossier de l'original de `made`, original
    exclu."""
    folder = (made.original.name or "").rsplit("/", 1)[0]
    _, files = default_storage.listdir(folder)
    return sorted(name for name in files if not name.startswith("original."))


@pytest.mark.django_db
def test_une_image_creee_dans_une_transaction_validee_est_traitee(
    portfolio: Project, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """L'état « prêt » et les variantes de l'original, posés ensemble ; chaque variante nommée
    existe dans le stockage."""
    with django_capture_on_commit_callbacks(execute=True):
        made = saved(gallery_image(portfolio))

    made.refresh_from_db()
    assert made.state == ProcessingState.READY
    assert [variant["width"] for variant in made.variants] == SQUARE_WIDTHS
    assert all(default_storage.exists(variant["name"]) for variant in made.variants)


@pytest.mark.django_db
def test_une_image_dont_l_original_est_remplace_est_traitee_sur_le_nouveau(
    portfolio: Project, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """Les variantes décrivent le nouvel original, rangées dans son dossier."""
    made = saved(gallery_image(portfolio))
    made.original = image_upload("nouvelle.png", size=(800, 600))

    with django_capture_on_commit_callbacks(execute=True):
        made.save()

    made.refresh_from_db()
    assert made.state == ProcessingState.READY
    assert [(v["width"], v["height"]) for v in made.variants] == [
        (320, 240),
        (480, 360),
        (720, 540),
        (800, 600),
    ]
    assert variant_files(made) == ["320.webp", "480.webp", "720.webp", "800.webp"]


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Les traitements enfilés pendant le test, sans les exécuter : chacun `(image, original)`."""
    calls: list[tuple[int, str]] = []

    def delay(image_id: int, original_name: str) -> None:
        calls.append((image_id, original_name))

    monkeypatch.setattr(process_image, "delay", delay)
    return calls


class Rollback(Exception):
    """Annule la transaction d'un test, comme une erreur après l'écriture."""


@pytest.mark.django_db
def test_une_transaction_annulee_n_enfile_aucun_traitement(
    portfolio: Project,
    enqueued: list[tuple[int, str]],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(Rollback),
        transaction.atomic(),
    ):
        saved(gallery_image(portfolio))
        raise Rollback

    assert enqueued == []


@pytest.mark.django_db
def test_une_sauvegarde_enfile_l_identifiant_et_l_original_qu_elle_ecrit(
    portfolio: Project,
    enqueued: list[tuple[int, str]],
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Une création, puis un remplacement : un traitement chacun, sur l'original que la ligne
    référence désormais."""
    with django_capture_on_commit_callbacks(execute=True):
        made = saved(gallery_image(portfolio))
    first = made.original.name
    made.original = image_upload("nouvelle.png")
    with django_capture_on_commit_callbacks(execute=True):
        made.save()

    assert enqueued == [(made.pk, first), (made.pk, made.original.name)]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "update_fields",
    [None, ["caption"]],
    ids=["enregistrement complet", "enregistrement partiel sans l'original"],
)
def test_une_sauvegarde_qui_ne_remplace_pas_l_original_n_enfile_rien(
    portfolio: Project,
    enqueued: list[tuple[int, str]],
    update_fields: list[str] | None,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Une légende retouchée ne touche pas l'original ; un enregistrement partiel qui ne l'écrit
    pas non plus, même un nouveau fichier affecté au champ."""
    made = saved(gallery_image(portfolio))
    made.caption = "Une autre légende."
    if update_fields:
        made.original = image_upload("nouvelle.png")

    with django_capture_on_commit_callbacks(execute=True):
        made.save(update_fields=update_fields)

    assert enqueued == []


@pytest.mark.django_db
def test_un_broker_injoignable_laisse_l_image_en_attente_sans_faire_echouer_l_enregistrement(
    portfolio: Project,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Le témoin lève à l'enfilement, comme Redis injoignable : l'erreur est journalisée, et
    l'image, enregistrée, attend."""

    def unreachable(*arguments: object) -> None:
        raise OperationalError("Redis injoignable")

    monkeypatch.setattr(process_image, "delay", unreachable)

    with django_capture_on_commit_callbacks(execute=True):
        made = saved(gallery_image(portfolio))

    made.refresh_from_db()
    assert made.state == ProcessingState.PENDING
    assert "Redis injoignable" in caplog.text


def during_processing(monkeypatch: pytest.MonkeyPatch, change: Callable[[], object]) -> None:
    """Fait jouer `change` pendant le traitement : après la lecture de l'original et la production
    de ses variantes, avant l'écriture du résultat."""

    def changing(storage: Storage, original_name: str) -> list[Variant]:
        variants = make_variants(storage, original_name)
        change()
        return variants

    monkeypatch.setattr(tasks, "make_variants", changing)


@pytest.mark.django_db
def test_un_original_remplace_pendant_le_traitement_ne_recoit_rien_de_l_ancien(
    portfolio: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deux écrivains (décision 7) : la ligne reste celle du nouveau fichier, en attente et sans
    variante ; les variantes de l'ancien ne sont ni en base ni dans le stockage."""
    made = saved(gallery_image(portfolio))
    old = made.original.name or ""
    replacing = GalleryImage.objects.get(pk=made.pk)
    replacing.original = image_upload("nouvelle.png")
    during_processing(monkeypatch, replacing.save)

    process_image.delay(made.pk, old)

    row = GalleryImage.objects.get(pk=made.pk)
    assert (row.original.name, row.state, row.variants) == (
        replacing.original.name,
        ProcessingState.PENDING,
        [],
    )
    assert variant_files(made) == []


@pytest.mark.django_db
def test_une_image_supprimee_pendant_le_traitement_ne_laisse_aucune_variante(
    portfolio: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aucune erreur ; l'original, lui, sort du stockage avec la transaction qui supprime son
    image (`delete_image_files`)."""
    made = saved(gallery_image(portfolio))
    during_processing(monkeypatch, GalleryImage.objects.get(pk=made.pk).delete)

    process_image.delay(made.pk, made.original.name or "")

    assert variant_files(made) == []


@pytest.mark.django_db
@pytest.mark.parametrize("how", ["supprimée", "remplacée"])
def test_une_tache_dont_l_image_a_change_avant_le_traitement_ne_fait_rien(
    portfolio: Project, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    """La ligne ne porte plus l'original enfilé : rien n'est lu, rien n'est écrit, aucune erreur
    — un fichier déjà supprimé ne ferait pas réessayer quatre fois."""
    made = saved(gallery_image(portfolio))
    enqueued_name = made.original.name or ""
    if how == "supprimée":
        GalleryImage.objects.filter(pk=made.pk).delete()
    else:
        made.original = image_upload("nouvelle.png")
        made.save()
    calls: list[str] = []

    def converting(storage: Storage, original_name: str) -> list[Variant]:
        calls.append(original_name)
        return []

    monkeypatch.setattr(tasks, "make_variants", converting)

    process_image.delay(made.pk, enqueued_name)

    assert calls == []


@pytest.mark.django_db
def test_une_erreur_de_traitement_est_reessayee_trois_fois_puis_l_image_passe_en_echec(
    portfolio: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un original devenu illisible : quatre essais, chacun sur une image encore en attente, à
    délai croissant (1, 2 puis 4 s) ; puis « échec » sans variante, aucun fichier produit, et
    l'erreur sort de la tâche — son issue est l'échec, l'exception son résultat, ce que le worker
    journalise.

    La propagation du mode synchrone est coupée le temps du test : Celery 5.6.3 y relance le
    `Retry` dès la première erreur (`on_error` de `celery/app/trace.py`), et aucun réessai ne se
    rejouerait."""
    monkeypatch.setitem(celery_app.conf, "task_eager_propagates", False)
    made = saved(gallery_image(portfolio))
    name = made.original.name or ""
    default_storage.delete(name)
    default_storage.save(name, ContentFile(b"Plus une image."))
    states: list[str] = []
    countdowns: list[int] = []

    def counted(storage: Storage, original_name: str) -> list[Variant]:
        states.append(GalleryImage.objects.get(pk=made.pk).state)
        return make_variants(storage, original_name)

    def retry(**options: Any) -> object:
        countdowns.append(options["countdown"])
        return task_retry(**options)

    task_retry = process_image.retry
    monkeypatch.setattr(tasks, "make_variants", counted)
    monkeypatch.setattr(process_image, "retry", retry)

    result = process_image.delay(made.pk, name)

    assert result.state == "FAILURE"
    assert isinstance(result.result, UnidentifiedImageError)
    assert states == [ProcessingState.PENDING] * 4
    # Le quatrième appel de `retry` ne réessaie pas : il relance l'erreur, le plafond atteint.
    assert countdowns[:3] == [1, 2, 4]
    row = GalleryImage.objects.get(pk=made.pk)
    assert (row.state, row.variants) == (ProcessingState.FAILED, [])
    assert variant_files(made) == []
