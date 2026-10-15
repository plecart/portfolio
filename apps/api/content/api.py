"""L'API publique de la phase 1 : une seule opération, la liste des projets publiés (brief de #10,
décision 1), montée sous `/api/` par la table de routage.

Lecture seule, sans authentification : aucune opération n'en déclare. Les docs interactives et le
schéma en ligne sont désactivés (`openapi_url=None`, décision 10) : rien ne les consomme ; le schéma est
exporté dans `apps/api/openapi.json` par `make openapi`. Titre et version sont fixés pour que ce
fichier ne bouge pas d'un export à l'autre.
"""

from django.db.models import Prefetch, QuerySet
from django.http import HttpRequest
from ninja import NinjaAPI

from content.models import Project, ProjectTechnology
from content.schemas import ProjectOut

api = NinjaAPI(title="Portfolio", version="1", openapi_url=None, docs_url=None)


def published_projects() -> QuerySet[Project]:
    """Les projets publiés, chacun avec ses technologies, sa galerie et ses sections.

    Un nombre de requêtes indépendant du nombre de projets (décision 12) : celle des projets, puis
    une par liste préchargée — les technologies jointes à leurs lignes de projet. Chaque liste
    préchargée garde l'ordre de son modèle, l'ordre de l'admin (`position`, puis `id`).

    Triés par slug : le front calcule l'ordre des cartes (ADR 0010), mais un même contenu doit
    toujours rendre le même corps — l'`ETag` du lot 2 en est l'empreinte (décision 6), et sans
    ordre Postgres peut rendre les lignes dans un ordre ou un autre.
    """
    return (
        Project.objects.filter(published=True)
        .order_by("slug")
        .prefetch_related(
            Prefetch(
                "projecttechnology_set",
                queryset=ProjectTechnology.objects.select_related("technology"),
            ),
            "gallery",
            "section_set",
        )
    )


@api.get("/projets", response=list[ProjectOut])
def projects(request: HttpRequest) -> QuerySet[Project]:
    """`GET /api/projets` : la liste nue des projets publiés, `[]` s'il n'y en a aucun."""
    return published_projects()
