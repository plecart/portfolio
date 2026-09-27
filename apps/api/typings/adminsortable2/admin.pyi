"""Types de la part de `django-admin-sortable2` qu'emploie l'admin du contenu (ADR 0013).

La bibliothèque ne publie pas de types, et pyright strict refuse une base de classe inconnue. Ne
déclare que ce que `content/admin.py` hérite ou appelle ; une classe ou une méthode de plus s'ajoute
avec son premier usage.
"""

from typing import Any

from django.forms import Media

class SortableAdminBase:
    @property
    def media(self) -> Media: ...

class SortableInlineAdminMixin: ...

class CustomInlineFormSetMixin:
    default_order_direction: str | None
    default_order_field: str | None
    def __init__(
        self,
        default_order_direction: str | None = ...,
        default_order_field: str | None = ...,
        **kwargs: Any,
    ) -> None: ...
