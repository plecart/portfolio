"""La tâche du worker d'images : produire les variantes d'un original, puis écrire l'état de son
image (ADR 0015 ; brief de #12, décisions 7 et 8).

Le worker la trouve par `app.autodiscover_tasks()` (`config/celery.py`), qui importe le module
`tasks` de chaque application ; `GalleryImage.save` l'enfile après la validation de la
transaction qui crée l'image ou remplace son original.
"""

from functools import partial

from celery import Task, shared_task
from django.core.files.storage import default_storage
from django.db import transaction

from content.models import GalleryImage, ProcessingState
from content.variants import make_variants

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
    écrites sont supprimées, le nouveau fichier n'est pas touché, et la tâche se termine.

    Toute erreur est réessayée `MAX_RETRIES` fois. Une erreur de la conversion, au dernier essai,
    fait passer l'image à « échec » par la même écriture conditionnelle ; une erreur de la base —
    lecture de la ligne, écriture du résultat — n'écrit rien, et l'image reste « en attente »
    (ADR 0015 : « échec » s'écrit « si la base est joignable »). L'erreur du dernier essai sort de
    la tâche : le worker la journalise (Sentry la recevra avec #17).

    Limites connues, levées par le lot 3c de #12 : une erreur de l'écriture du résultat laisse les
    variantes de l'essai ; une suppression refusée par le stockage laisse son fichier, et, à zéro
    ligne, fait réessayer la tâche sans supprimer les variantes suivantes.

    Args:
        self: la tâche, liée (`bind`) : son contexte d'exécution dit le numéro de l'essai.
        image_id: l'identifiant de l'image.
        original_name: le nom de stockage de l'original que la sauvegarde a enfilé.

    Raises:
        Exception: l'erreur du dernier essai — « échec » écrit si elle vient de la conversion.
    """
    image = GalleryImage.objects.filter(pk=image_id, original=original_name)
    if not image.exists():
        return
    try:
        variants = make_variants(default_storage, original_name)
    except Exception:
        if self.request.retries >= MAX_RETRIES:
            image.update(state=ProcessingState.FAILED)
        raise
    if not image.update(state=ProcessingState.READY, variants=variants):
        for variant in variants:
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
