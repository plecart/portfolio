"""Le code d'un script ou d'une feuille de l'admin, tel que le lisent les tests des prises qu'il
attend dans la page : ces fichiers n'ont pas de test de navigateur (ADR 0013)."""

import re
from pathlib import Path

from django.contrib.staticfiles import finders


def code(asset: str) -> str:
    """Le code du fichier statique `asset`, trouvé là où Django le sert, sans ses commentaires :
    une prise que seul un commentaire nomme encore ne tient rien."""
    found = finders.find(asset)
    assert isinstance(found, str)
    source = Path(found).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)
