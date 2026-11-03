"""L'espace du cache du contenu : les réponses de l'API publique, gardées telles que rendues, et
vidées à chaque écriture du contenu (ADR 0006, rôle 1 ; brief de #11, décisions 3 et 8 à 10).

Vider l'espace, c'est changer de génération : chaque clé porte la génération courante, et en poser
une neuve rend toutes les entrées précédentes injoignables ; elles expirent à leur durée de vie
(`CACHES`, `TIMEOUT`). Ni `cache.clear()`, qui viderait la base Redis que partage la file du
broker, ni un effacement par motif, que le cache en mémoire de la suite n'a pas.
"""

from collections.abc import Callable
from functools import wraps
from uuid import uuid4

from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase

# Le préfixe de chaque clé de l'espace, puis la clé de sa génération courante.
SPACE = "contenu"
GENERATION = f"{SPACE}:generation"

type View = Callable[..., HttpResponseBase]


def new_generation() -> str:
    """Une génération neuve : aléatoire, jamais un compteur, qu'une génération expirée ferait
    repartir sur une valeur déjà servie — et sur ses entrées périmées."""
    return uuid4().hex


def content_key(request: HttpRequest, name: str) -> str:
    """La clé de la réponse `name` servie à l'origine de `request`, sous la génération courante.

    L'origine — schéma et hôte — en fait partie : le corps porte des adresses absolues construites
    sur elle (`absolute_url`, `content/schemas.py`). La génération est lue ici, avant que la vue ne
    lise la base : une réponse lue avant une écriture se range sous l'ancienne génération, que plus
    rien ne lit une fois la purge passée.

    Args:
        request: la requête servie.
        name: le nom de la réponse dans l'espace — `projets` pour la liste.

    Returns:
        La clé, par exemple `contenu:<génération>:projets:http://testserver` sous le client de test.
    """
    generation = cache.get_or_set(GENERATION, new_generation)
    return f"{SPACE}:{generation}:{name}:{request.scheme}://{request.get_host()}"


def cached(name: str) -> Callable[[View], View]:
    """Décorateur de vue : sert depuis le cache la réponse `name` qu'une vue a déjà rendue avec
    succès ; sinon la vue la rend, et sa réponse `200` est gardée sous `content_key`.

    Le cache garde le corps rendu et son type, jamais des objets : la réponse servie depuis le cache
    est celle de la base, octet pour octet, donc de même `ETag` (`ConditionalGetMiddleware`). Rien
    d'autre : un en-tête que la vue poserait elle-même manquerait à la réponse du cache ; ceux des
    décorateurs extérieurs (`cache_control`) se reposent à chaque appel. Posé sur une opération
    django-ninja, il enveloppe aussi ses contrôles — authentification, limite de débit — qu'un
    succès du cache ne joue pas : il ne sert qu'une opération publique qui n'en a aucun.

    Args:
        name: le nom de la réponse dans l'espace (`content_key`).
    """

    def decorate(view: View) -> View:
        @wraps(view)
        def serve(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponseBase:
            key = content_key(request, name)
            stored: tuple[bytes, str] | None = cache.get(key)
            if stored is not None:
                content, content_type = stored
                return HttpResponse(content, content_type=content_type)
            response = view(request, *args, **kwargs)
            if isinstance(response, HttpResponse) and response.status_code == 200:
                cache.set(key, (response.content, response["Content-Type"]))
            return response

        return serve

    return decorate


def purge() -> None:
    """Vide l'espace : pose une génération neuve.

    Appelée une fois l'écriture du contenu validée, jamais avant : une requête qui lirait la base
    entre la purge et la validation remettrait l'ancien contenu en cache (décision 3).
    """
    cache.set(GENERATION, new_generation())


def purge_after_commit(**signal: object) -> None:
    """Récepteur de `post_save` et `post_delete` des modèles de contenu (`ContentConfig.ready`) :
    vide l'espace une fois la transaction en cours validée — aussitôt hors de toute transaction ;
    jamais si elle est annulée (doc Django, « Performing actions after commit »).

    `robust`, comme les autres rappels après validation du contenu : l'écriture est déjà validée,
    une purge qui échoue est journalisée (`django.db.backends.base`) sans la faire échouer.

    Args:
        signal: les arguments du signal, sans effet.
    """
    transaction.on_commit(purge, robust=True)
