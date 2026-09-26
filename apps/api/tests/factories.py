"""Fabriques minimales des tests : un objet valide, dont chaque test ne change qu'un champ.

Le motif que le PRD fixe aux tests du back (« fabriques minimales, un test par règle ») : l'échec
attendu ne peut venir que du champ que le test remplace.
"""

from content.models import Technology, TechnologyKind
from django.core.files.uploadedfile import SimpleUploadedFile

# Le plus petit document SVG qu'un navigateur affiche : une racine `svg` dans son espace de noms.
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>'


def svg_icon(name: str = "icone.svg", content: bytes = SVG) -> SimpleUploadedFile:
    """Un fichier téléversé, tel que l'admin le reçoit."""
    return SimpleUploadedFile(name, content, content_type="image/svg+xml")


def technology(**fields: object) -> Technology:
    """Une technologie valide, non enregistrée ; `fields` en remplace des champs."""
    return Technology(
        **{"name": "Django", "kind": TechnologyKind.FRAMEWORK, "icon": svg_icon(), **fields}
    )
