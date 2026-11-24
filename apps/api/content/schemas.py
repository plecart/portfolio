"""Le contrat de l'API publique : ce que `GET /api/projets` livre de chaque projet (brief de #10,
décisions 2 à 5).

Des données brutes, jamais de présentation (ADR 0010) : Markdown tel que saisi, valeurs stockées
en anglais, dates ISO 8601, chaque fichier par son adresse absolue. L'ordre de chaque liste est
celui de l'admin, et le projet expose sa `position`, sur laquelle le front range les cartes (D77) ;
le front calcule le reste — libellés, technologies de carte.

Ce qui n'est pas exposé l'est par omission, champ par champ : `published` (toujours vrai ici), les
horodatages, l'`id`, la `position` d'une ligne de liste — technologie, image, section — (l'ordre
est celui de la liste), `Technology.website` (glossaire) et `GalleryImage.original` (le site sert
les variantes). La couverture n'a pas de clé : c'est `gallery[0]` (décision 3).

Un résolveur qui déclare `context` reçoit la requête dans le contexte de validation que
django-ninja passe à pydantic (`context["request"]`, « What's new in Django Ninja 1.0 ») : c'est
d'elle que viennent le schéma et l'hôte d'une adresse relative.
"""

from datetime import date
from typing import Any

from django.http import HttpRequest
from ninja import Schema

from content.models import (
    GalleryImage,
    ProcessingState,
    Project,
    ProjectKind,
    ProjectStatus,
    Section,
    Technology,
    TechnologyKind,
    Variant,
)


def absolute_url(context: dict[str, Any], url: str) -> str:
    """L'adresse absolue d'un fichier dont le stockage a rendu l'adresse `url`.

    Le stockage disque rend une adresse relative (`/media/…`), que la requête complète de son
    schéma et de son hôte ; une adresse que le stockage rend déjà absolue (R2) reste telle
    quelle — `build_absolute_uri` garde le schéma et l'hôte d'une adresse qui les porte, à
    l'encodage IRI près, sans effet sur l'adresse déjà encodée que rend un stockage.

    Args:
        context: le contexte de validation, qui porte la requête en cours sous `request`.
        url: l'adresse que le stockage rend pour le fichier (`Storage.url`, `FieldFile.url`).

    Returns:
        L'adresse, par exemple `http://testserver/media/images/x/800.webp` sous le client de test.
    """
    request: HttpRequest = context["request"]
    return request.build_absolute_uri(url)


def variant_url(context: dict[str, Any], image: GalleryImage, variant: Variant) -> str:
    """L'adresse absolue de la variante `variant` de `image`, sur le stockage de son original :
    celle que sert l'API publique, et que reprend l'aperçu de lien (`content/link_preview.py`).

    Args:
        context: le contexte de validation, qui porte la requête en cours sous `request`.
        image: l'image de la galerie.
        variant: une variante de `image`.
    """
    return absolute_url(context, image.original.storage.url(variant["name"]))


class TechnologyOut(Schema):
    """Une technologie qu'un projet emploie : son nom, son type et l'adresse de son icône SVG,
    que le site charge en `<img>` (décision 5) — jamais le SVG lui-même."""

    name: str
    kind: TechnologyKind
    icon: str

    @staticmethod
    def resolve_icon(technology: Technology, context: dict[str, Any]) -> str:
        return absolute_url(context, technology.icon.url)


class VariantOut(Schema):
    """Une variante d'une image prête : son adresse à la place de son nom de stockage."""

    url: str
    width: int
    height: int


class GalleryImageOut(Schema):
    """Une image de la galerie. Une image en attente ou en échec est exposée avec son état et
    sans variante (décision 4) : le front décide ce qu'il dessine."""

    caption: str
    width: int
    height: int
    state: ProcessingState
    variants: list[VariantOut]

    @staticmethod
    def resolve_variants(image: GalleryImage, context: dict[str, Any]) -> list[VariantOut]:
        return [
            VariantOut(
                url=variant_url(context, image, variant),
                width=variant["width"],
                height=variant["height"],
            )
            for variant in image.variants
        ]


class SectionOut(Schema):
    """Une section de la fiche technique : titre, ancre et corps Markdown."""

    title: str
    anchor: str
    body: str


class ProjectOut(Schema):
    """Un projet publié, complet : ses faits, ses technologies, sa galerie — dont la première
    image est la couverture — et les sections de sa fiche, chaque liste dans l'ordre de l'admin.

    `finished_on` vaut `null` tant que le projet est en cours ; un lien absent est une chaîne
    vide, comme stocké. `position` est son rang dans la table, choisi dans l'admin : la liste suit
    les positions, puis l'ordre de saisie à position égale.
    """

    slug: str
    title: str
    summary: str
    description: str
    kind: ProjectKind
    status: ProjectStatus
    started_on: date
    finished_on: date | None
    client: str
    repository_url: str
    demo_url: str
    showcase: bool
    position: int
    technologies: list[TechnologyOut]
    gallery: list[GalleryImageOut]
    sections: list[SectionOut]

    @staticmethod
    def resolve_technologies(project: Project) -> list[Technology]:
        return [line.technology for line in project.projecttechnology_set.all()]

    @staticmethod
    def resolve_sections(project: Project) -> list[Section]:
        return list(project.section_set.all())
