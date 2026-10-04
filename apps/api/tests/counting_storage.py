"""Un stockage témoin : le stockage sur disque de Django, qui retient chaque fichier qu'il ouvre."""

from typing import Any

from django.core.files import File
from django.core.files.storage import FileSystemStorage


class CountingStorage(FileSystemStorage):
    """`FileSystemStorage`, plus la liste des noms qu'il a ouverts, dans l'ordre.

    Le témoin de « un fichier inchangé n'est jamais relu » (brief de #9, décision 9) : sur R2,
    chaque ouverture est un téléchargement. Réglé comme stockage par défaut le temps d'un test
    (`STORAGES`), il compte toute lecture que le code fait par le stockage de Django.
    """

    def __init__(self) -> None:
        super().__init__()
        self.opened: list[str] = []

    def open(self, name: str, mode: str = "rb") -> File[Any]:
        self.opened.append(name)
        return super().open(name, mode)
