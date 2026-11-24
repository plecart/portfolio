"""Les projets reçoivent leurs positions dans l'ordre que la table affichait avant elles (D77, qui
remplace D48 ; issue #288).

L'ordre d'avant est celui que calculait le front (`compareProjects`, `apps/web/src/table/cards.ts`,
avec `datedOn` et `compareText`), recopié ici tel qu'il était — le front le retire, la migration
le garde — et appliqué à tous les projets, brouillons compris : positions 1 à N. Au lendemain de la
migration, la table du site est inchangée, et un brouillon a déjà son rang quand il est publié.

Le retour ne défait rien : la colonne disparaît avec la migration qui la pose.
"""

from typing import Any

from django.db import migrations


def table_order(project: Any) -> tuple[bool, bool, int, str]:
    """La clé de l'ordre d'avant : la vitrine, puis les projets terminés et archivés ensemble, puis
    les projets en cours ; chaque groupe du plus récent au plus ancien — la date de fin, à défaut
    celle du début —, et à date égale par slug croissant.

    Le front comparait les slugs par unités de code UTF-16 ; un slug n'a que des caractères ASCII
    (`content_project_slug_valid`), où Python compare de même.
    """
    dated_on = project.finished_on or project.started_on
    return (not project.showcase, project.status == "ongoing", -dated_on.toordinal(), project.slug)


def number_projects(apps: Any, schema_editor: Any) -> None:
    """Numérote tous les projets de 1 à N dans l'ordre d'avant."""
    project_model = apps.get_model("content", "Project")
    projects = sorted(project_model.objects.all(), key=table_order)
    for position, project in enumerate(projects, start=1):
        project.position = position
    project_model.objects.bulk_update(projects, ["position"])


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0007_project_position"),
    ]

    operations = [
        migrations.RunPython(number_projects, migrations.RunPython.noop),
    ]
