"""L'espace du cache du contenu : les réponses de l'API publique et les pages des aperçus de lien,
gardées telles que rendues, et vidées à chaque écriture du contenu (ADR 0006, rôle 1 ; brief de
#11, décisions 3 et 8 à 10 ; brief de #14, décision 4).

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


def content_key(request: HttpRequest, name: str) -> str | None:
    """La clé de la réponse `name` servie à l'origine de `request`, sous la génération courante ;
    `None` sans génération.

    L'origine — schéma et hôte — en fait partie : le corps porte des adresses absolues construites
    sur elle (`absolute_url`, `content/schemas.py`). La génération est lue ici, avant que la vue ne
    lise la base : une réponse lue avant une écriture se range sous l'ancienne génération, que plus
    rien ne lit une fois la purge passée.

    Une génération absente — jamais posée, expirée, ou Redis qui ne répond pas, que `django-redis`
    rend de même (`IGNORE_EXCEPTIONS`) — est remplacée par une neuve, posée par `add`, qui ne
    recouvre pas celle d'une purge passée entre-temps. Quand elle ne se pose pas — `add` rend faux
    si une autre requête l'a devancée, `None` si Redis ne répond toujours pas —, il n'y a pas de
    clé : un Redis muet ne coûte à la requête que ces deux opérations.

    Args:
        request: la requête servie.
        name: le nom de la réponse dans l'espace — `projets` pour la liste,
            `apercu:<slug>:<empreinte du gabarit>` pour la page d'une fiche
            (`content/link_preview.py`).

    Returns:
        La clé, par exemple `contenu:<génération>:projets:http://testserver` sous le client de
        test ; `None` si aucune génération n'est lue ni posée.
    """
    generation: str | None = cache.get(GENERATION)
    if generation is None:
        generation = new_generation()
        if not cache.add(GENERATION, generation):
            return None
    return f"{SPACE}:{generation}:{name}:{request.scheme}://{request.get_host()}"


def cached_response(
    request: HttpRequest, name: str, render: Callable[[], HttpResponseBase]
) -> HttpResponseBase:
    """La réponse `name` servie à `request` : depuis le cache si elle a déjà été rendue avec
    succès ; sinon celle que rend `render`, gardée sous `content_key` si c'est un `200` — rien
    n'est lu ni gardé sans clé.

    Le cache garde le corps rendu et son type, jamais des objets : la réponse servie depuis le cache
    est celle de la base, octet pour octet, donc de même `ETag` (`ConditionalGetMiddleware`). Rien
    d'autre : un en-tête que `render` poserait lui-même manquerait à la réponse du cache ; ceux des
    décorateurs extérieurs (`cache_control`) se reposent à chaque appel.

    Args:
        request: la requête servie.
        name: le nom de la réponse dans l'espace (`content_key`).
        render: rend la réponse quand le cache ne la tient pas ; appelé après la lecture de la
            génération, jamais avant (`content_key`).
    """
    key = content_key(request, name)
    if key is None:
        return render()
    stored: tuple[bytes, str] | None = cache.get(key)
    if stored is not None:
        content, content_type = stored
        return HttpResponse(content, content_type=content_type)
    response = render()
    if isinstance(response, HttpResponse) and response.status_code == 200:
        cache.set(key, (response.content, response["Content-Type"]))
    return response


def cached(name: str) -> Callable[[View], View]:
    """Décorateur de vue : sa réponse est `cached_response` sous le nom fixe `name`.

    Posé sur une opération django-ninja, il enveloppe aussi ses contrôles — authentification,
    limite de débit — qu'un succès du cache ne joue pas : il ne sert qu'une opération publique qui
    n'en a aucun.

    Args:
        name: le nom de la réponse dans l'espace (`content_key`).
    """

    def decorate(view: View) -> View:
        @wraps(view)
        def serve(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponseBase:
            return cached_response(request, name, lambda: view(request, *args, **kwargs))

        return serve

    return decorate


def purge() -> None:
    """Vide l'espace : pose une génération neuve.

    Appelée une fois l'écriture du contenu validée, jamais avant : une requête qui lirait la base
    entre la purge et la validation remettrait l'ancien contenu en cache (décision 3).
    """
    cache.set(GENERATION, new_generation())


def purge_after_commit(**signal: object) -> None:
    """Vide l'espace une fois la transaction en cours validée — aussitôt hors de toute transaction,
    comme dans le worker ; jamais si elle est annulée (doc Django, « Performing actions after
    commit »). Récepteur de `post_save` et `post_delete` des modèles de contenu
    (`ContentConfig.ready`), et appelée par la tâche d'image après ses écritures, qui échappent
    aux signaux (`content/tasks.py`).

    `robust`, comme les autres rappels après validation du contenu : l'écriture est déjà validée,
    rien n'est à défaire. Une purge qui échoue est journalisée avec sa trace
    (`django.db.backends.base`) sans faire échouer l'écriture — toute erreur, quand `django-redis`
    ne journalise que celles de Redis qu'il ignore (`config/settings.py`).

    Args:
        signal: les arguments du signal, sans effet ; aucun hors d'un signal.
    """
    transaction.on_commit(purge, robust=True)
