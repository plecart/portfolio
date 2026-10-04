"""Fabriques minimales des tests : un objet valide, dont chaque test ne change qu'un champ.

Le motif que le PRD fixe aux tests du back (« fabriques minimales, un test par règle ») : l'échec
attendu ne peut venir que du champ que le test remplace.
"""

from datetime import date
from io import BytesIO

from content.models import (
    Project,
    ProjectKind,
    ProjectStatus,
    Section,
    Technology,
    TechnologyKind,
)
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Model
from PIL import Image

# Le plus petit document SVG qu'un navigateur affiche : une racine `svg` dans son espace de noms.
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>'

# Le début du projet de la fabrique : les tests de dates se placent par rapport à lui.
STARTED_ON = date(2026, 9, 1)

# Un texte fait d'espaces seulement — espace, retour à la ligne, tabulation : vide pour l'auteur
# comme pour le site (décision 7 du brief de #8).
BLANK = " \n\t "


def saved[M: Model](instance: M) -> M:
    """`instance`, enregistré : les fabriques rendent des objets non enregistrés, un test qui a
    besoin d'une ligne en base le dit par cet appel."""
    instance.save()
    return instance


def url_of_length(length: int) -> str:
    """Une adresse valide de `length` caractères, pour éprouver une borne des deux côtés."""
    base = "https://exemple.fr/"
    return base + "a" * (length - len(base))


def svg_icon(name: str = "icone.svg", content: bytes = SVG) -> SimpleUploadedFile:
    """Un fichier téléversé, tel que l'admin le reçoit."""
    return SimpleUploadedFile(name, content, content_type="image/svg+xml")


def image_upload(
    name: str = "image.png",
    size: tuple[int, int] = (1200, 1200),
    image_format: str = "PNG",
    padding: int = 0,
) -> SimpleUploadedFile:
    """Une image téléversée, fabriquée en mémoire par Pillow : `size` en pixels, au format
    `image_format`, sous le nom `name` — qui peut mentir sur le format.

    Par défaut, un carré de 1200 px : une couverture valide, et une image de galerie aussi.
    `padding` octets nuls suivent l'image, que ses lecteurs ignorent : un poids s'atteint sans
    fabriquer une grande image.
    """
    content = BytesIO()
    Image.new("RGB", size).save(content, image_format)
    return SimpleUploadedFile(name, content.getvalue() + bytes(padding))


def technology(**fields: object) -> Technology:
    """Une technologie valide, non enregistrée ; `fields` en remplace des champs."""
    return Technology(
        **{"name": "Django", "kind": TechnologyKind.FRAMEWORK, "icon": svg_icon(), **fields}
    )


def project(**fields: object) -> Project:
    """Un projet valide, en cours, non enregistré ; `fields` en remplace des champs."""
    return Project(
        **{
            "title": "Portfolio",
            "slug": "portfolio",
            "summary": "Le site qui présente mes projets.",
            "description": "Une table de projets et leurs fiches.",
            "kind": ProjectKind.PERSONAL,
            "status": ProjectStatus.ONGOING,
            "started_on": STARTED_ON,
            **fields,
        }
    )


def section(owner: Project, **fields: object) -> Section:
    """Une section valide de `owner`, non enregistrée, à la première place ; `fields` en remplace
    des champs."""
    return Section(
        **{
            "project": owner,
            "title": "Contexte et objectif",
            "anchor": "contexte-et-objectif",
            "body": "Pourquoi ce projet.",
            "position": 1,
            **fields,
        }
    )
