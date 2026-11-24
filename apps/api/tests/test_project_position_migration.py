"""Test de la migration qui numérote les projets dans l'ordre de la table d'avant D77
(`content/migrations/0008_number_projects.py`, issue #288) : elle tourne sur une base de test
ramenée à l'état d'avant la position, garnie par les modèles historiques de cet état."""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from factories import historical_project

BEFORE = [("content", "0006_cover_to_gallery")]
AFTER = [("content", "0008_number_projects")]

# Un projet tel que la migration le lit : slug, vitrine, statut, début, fin, publié.
type Row = tuple[str, bool, str, date, date | None, bool]

# Des projets dans l'ordre de leur saisie, puis leurs slugs dans l'ordre des positions que la
# migration leur donne. L'entrée du critère de #288 : la vitrine en tête, en cours ou non ; puis
# les projets terminés et archivés ensemble, brouillon compris, du plus récent au plus ancien ;
# puis les projets en cours.
TABLES: dict[str, tuple[list[Row], list[str]]] = {
    "entrée du critère": (
        [
            ("a", True, "ongoing", date(2024, 1, 1), None, True),
            ("b", False, "finished", date(2023, 1, 1), date(2023, 6, 1), True),
            ("c", False, "archived", date(2024, 6, 1), date(2025, 2, 1), True),
            ("d", False, "ongoing", date(2026, 3, 1), None, True),
            ("e", False, "finished", date(2024, 1, 1), date(2024, 9, 1), False),
        ],
        ["a", "c", "e", "b", "d"],
    ),
    "date égale, par slug": (
        [
            ("y", False, "finished", date(2024, 1, 1), date(2024, 9, 1), True),
            ("x", False, "archived", date(2023, 1, 1), date(2024, 9, 1), True),
        ],
        ["x", "y"],
    ),
}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("rows", "expected"), TABLES.values(), ids=TABLES.keys())
def test_la_migration_numerote_les_projets_dans_l_ordre_de_la_table_d_avant(
    migrate: Callable[[list[tuple[str, str]]], Any], rows: list[Row], expected: list[str]
) -> None:
    """Positions 1 à N pour tous les projets, brouillons compris (`compareProjects`, le
    comparateur du front d'avant D77) : au lendemain de la migration, la table du site est
    inchangée, et un brouillon a déjà son rang quand il est publié."""
    # L'ordre de saisie, celui des clés, ne donne jamais l'ordre attendu : une migration qui
    # numéroterait par clé rougit.
    assert [slug for slug, *_ in rows] != expected
    before = migrate(BEFORE)
    for slug, showcase, status, started_on, finished_on, published in rows:
        historical_project(
            before,
            slug=slug,
            status=status,
            started_on=started_on,
            finished_on=finished_on,
            showcase=showcase,
            published=published,
        )

    after = migrate(AFTER)

    stored = after.get_model("content", "Project").objects.order_by("position")
    assert [(project.slug, project.position) for project in stored] == [
        (slug, position) for position, slug in enumerate(expected, start=1)
    ]
