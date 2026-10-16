"""La tâche du worker d'images : produire les variantes d'un original, puis écrire l'état de son
image (ADR 0015 ; brief de #12, décisions 7 et 8).

Le worker la trouve par `app.autodiscover_tasks()` (`config/celery.py`), qui importe le module
`tasks` de chaque application ; `GalleryImage.save` l'enfile après la validation de la
transaction qui crée l'image ou remplace son original.
"""

from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

from celery import Task, shared_task
from django.core.files.storage import default_storage
from django.db import transaction

from content.models import GalleryImage, ProcessingState, Variant
from content.variants import make_variants

if TYPE_CHECKING:
    from django.db.models import QuerySet

# Les réessais d'un traitement en erreur (décision 8) : quatre essais en tout, séparés de 1, 2 puis
# 4 s (`retry_backoff`, sans l'aléa que Celery y met par défaut).
MAX_RETRIES = 3


# L'annotation de `self` est une chaîne : `Task` n'est générique que dans les stubs de
# celery-types, pas à l'exécution.
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=MAX_RETRIES,
    retry_backoff=True,
    retry_jitter=False,
)
def process_image(self: "Task[[int, str], None]", image_id: int, original_name: str) -> None:
    """Produit les variantes de l'original `original_name` de l'image `image_id`, puis pose
    ensemble l'état « prêt » et leur liste.

    Toute écriture est conditionnée à l'original traité (décision 7) : une seule requête, sur
    l'identifiant **et** le nom de l'original, jamais `GalleryImage.save` — qui décrit les
    écritures de l'auteur. Une image supprimée, ou dont l'original a été remplacé, avant le
    traitement : rien n'est fait. Pendant le traitement : zéro ligne mise à jour, les variantes
    écrites sont supprimées, le nouveau fichier n'est pas touché, et la tâche se termine. Une
    écriture du résultat qui échoue, ou qu'une interruption coupe, supprime aussi les variantes de
    l'essai avant de sortir.

    Toute erreur est réessayée `MAX_RETRIES` fois. Réessais épuisés, quelle que soit l'origine de
    l'erreur, l'image passe à « échec » par la même écriture conditionnelle, si la base est
    joignable ; sinon elle reste « en attente » (ADR 0015 § Décision, « Échecs » ; `mark_failed`).
    L'erreur du dernier essai sort de la tâche : le worker la journalise (Sentry la recevra avec
    #17). Aucun essai ne laisse de fichier que la ligne ne nomme pas, sauf celui qu'une
    suppression refuse (`make_variants`, `discard`).

    Args:
        self: la tâche, liée (`bind`) : son contexte d'exécution dit le numéro de l'essai.
        image_id: l'identifiant de l'image.
        original_name: le nom de stockage de l'original que la sauvegarde a enfilé.

    Raises:
        Exception: l'erreur du dernier essai, « échec » écrit si la base l'a permis.
    """
    image = GalleryImage.objects.filter(pk=image_id, original=original_name)
    try:
        attempt(image, original_name)
    except Exception:
        if self.request.retries >= MAX_RETRIES:
            mark_failed(image)
        raise


def attempt(image: "QuerySet[GalleryImage]", original_name: str) -> None:
    """Un essai du traitement : rien si la ligne ne porte plus l'original ; sinon ses variantes,
    puis « prêt » et leur liste, posés ensemble par une requête conditionnelle (décision 7).

    Args:
        image: la ligne de l'image, filtrée sur son identifiant et l'original traité.
        original_name: le nom de stockage de cet original.

    Raises:
        Exception: une erreur de la conversion, du stockage ou de la base ; les variantes de
            l'essai sont alors supprimées.
    """
    if not image.exists():
        return
    variants = make_variants(default_storage, original_name)
    try:
        written = image.update(state=ProcessingState.READY, variants=variants)
    except BaseException:
        discard(variants)
        raise
    if not written:
        discard(variants)


def mark_failed(image: "QuerySet[GalleryImage]") -> None:
    """Pose l'état « échec » sur la ligne `image` — sans variante, la ligne étant « en attente » —,
    si la base le permet : une écriture qui échoue à son tour laisse l'image « en attente », sans
    masquer l'erreur d'origine, celle que le worker doit journaliser (ADR 0015 § Décision,
    « Échecs »).

    Args:
        image: la ligne de l'image, filtrée sur son identifiant et l'original traité.
    """
    with suppress(Exception):
        image.update(state=ProcessingState.FAILED)


def discard(variants: list[Variant]) -> None:
    """Supprime du stockage les fichiers de `variants`, qu'aucune ligne ne nomme : chaque
    suppression qui échoue laisse son fichier, sans arrêter les suivantes ni masquer l'erreur en
    cours.

    Args:
        variants: les variantes que la tâche vient d'écrire.
    """
    for variant in variants:
        with suppress(Exception):
            default_storage.delete(variant["name"])


def process_after_commit(image_id: int, original_name: str) -> None:
    """Enfile le traitement de l'original `original_name` de l'image `image_id` une fois la
    transaction en cours validée — aussitôt hors de toute transaction ; jamais si elle est annulée
    (décision 5, doc Django, « Performing actions after commit »).

    `robust`, comme `delete_after_commit` : la ligne est déjà validée quand le rappel s'exécute. Un
    broker injoignable est journalisé (`django.db.backends.base`) sans faire échouer
    l'enregistrement ; l'image reste « en attente », et remplacer son fichier relance.

    Args:
        image_id: l'identifiant de l'image enregistrée.
        original_name: le nom de stockage de l'original qu'elle référence désormais.
    """
    transaction.on_commit(partial(process_image.delay, image_id, original_name), robust=True)
