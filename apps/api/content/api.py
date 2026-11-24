"""L'API publique de la phase 1 : une seule opération, la liste des projets publiés (brief de #10,
décision 1), montée sous `/api/` par la table de routage.

Lecture seule, sans authentification : aucune opération n'en déclare. Les docs interactives et le
schéma en ligne sont désactivés (`openapi_url=None`, décision 10) : rien ne les consomme ; le schéma est
exporté dans `apps/api/openapi.json` par `make openapi`. Titre et version sont fixés pour que ce
fichier ne bouge pas d'un export à l'autre.
"""

from django.db.models import Prefetch, QuerySet
from django.http import HttpRequest
from django.views.decorators.cache import cache_control
from ninja import NinjaAPI
from ninja.decorators import decorate_view

from content.cache import cached
from content.models import Project, ProjectTechnology
from content.schemas import ProjectOut

api = NinjaAPI(title="Portfolio", version="1", openapi_url=None, docs_url=None)


def published_projects() -> QuerySet[Project]:
    """Les projets publiés, chacun avec ses technologies, sa galerie et ses sections.

    Un nombre de requêtes indépendant du nombre de projets (décision 12) : celle des projets, puis
    une par liste préchargée — les technologies jointes à leurs lignes de projet.

    Les projets suivent l'ordre de leur modèle (`position`, puis `id`), celui des cartes de la table
    choisi dans l'admin (D77), et chaque liste préchargée celui du sien, l'ordre de l'admin. Des
    ordres totaux : un même contenu rend toujours le même corps, dont l'`ETag` du lot 2 est
    l'empreinte (décision 6), là où, sans ordre, Postgres peut rendre les lignes dans un ordre ou un
    autre.
    """
    return Project.objects.filter(published=True).prefetch_related(
        Prefetch(
            "projecttechnology_set",
            queryset=ProjectTechnology.objects.select_related("technology"),
        ),
        "gallery",
        "section_set",
    )


# La docstring de l'opération est la `description` de son schéma OpenAPI : elle parle au
# consommateur du contrat, et tout changement se régénère (`make openapi`). Le reste se dit ici.
# `Cache-Control: no-cache` (décision 7) : le navigateur stocke la réponse et la revalide à chaque
# visite par son `ETag`, que `ConditionalGetMiddleware` pose (décision 6). Un décorateur de vue
# Django ne s'applique à une opération ninja que par `decorate_view` (doc django-ninja, « Using
# @decorate_view ») : posé directement, il envelopperait le résultat avant sa sérialisation. Le plus
# bas enveloppe l'opération au plus près : `cached` garde la réponse que ninja a rendue, et
# `cache_control` repose son en-tête sur celle que le cache sert (`content/cache.py`, #11). Ni
# session ni CSRF : aucun cookie (décision 9).
@api.get("/projets", response=list[ProjectOut])
@decorate_view(cache_control(no_cache=True))
@decorate_view(cached("projets"))
def projects(request: HttpRequest) -> QuerySet[Project]:
    """`GET /api/projets` : la liste nue des projets publiés, `[]` s'il n'y en a aucun.

    Sans cookie. `Cache-Control: no-cache` et `ETag` : la réponse se revalide à chaque visite par
    `If-None-Match`, `304` tant que rien n'a changé.
    """
    return published_projects()
