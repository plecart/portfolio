"""Exporte la miniature d'un projet en image PNG carrée de 2400 × 2400 px — ou ses quatre
propositions et leur planche d'aperçu.

Usage :
    python exporter.py [<description>] [--teintes <a,b,c,d>] [--dossier <dossier>]
    python exporter.py [<description>] [--png <png>]

Lancé depuis la racine du dépôt du projet : `<description>` vaut par défaut
`docs/miniature/miniature.json`, `<dossier>` `docs/miniature/propositions`, `<png>`
`docs/miniature/miniature.png`.

Trois temps, chacun arrêté par un échec :

1. **valider** la description (`miniature.py`). Des erreurs : elles sortent toutes, aucun
   navigateur ne démarre, et rien ne s'écrit ;
2. **assembler** une page autonome par image : le gabarit `rendu/miniature.html` rempli
   (`remplir` de l'export du schéma) — le gabarit de la description, le fond fixe et l'accent
   de la teinte, les paramètres de la composition, puis pour « chantier » le SVG du cône et ceux
   des trois icônes en ligne, chaque logo peint à sa couleur (`couleurs.json`), pour « mise en
   scène » le type du premier plan et son image en URL `data:`. La page ne fait aucune requête ;
3. **capturer** chaque page par `capturer` de l'export du schéma — fenêtre de 1200 × 1200 px au
   facteur d'échelle 2, la taille relue dans l'en-tête du PNG, l'image écrite seulement à cette
   taille.

Le mode suit la description :

- **sans choix** — ni `teinte` ni `composition` : les quatre propositions de
  `miniature.propositions`, la k-ième teinte de la palette, ou de `--teintes`, avec la k-ième
  composition du gabarit, en `<dossier>/proposition-<k>.png`, puis leur planche
  `<dossier>/planche.png` (`ecrire_propositions` de l'export du schéma, qui retire d'abord
  celles d'un lancement précédent) ;
- **avec choix** : l'image de cette teinte et de cette composition, seule, à `<png>`.

`--teintes` et `--dossier` ne valent que sans choix, `--png` qu'avec.

Prérequis : ceux de l'export du schéma, `uv` et Chromium pour sa version de Playwright.

Sortie : 0 et une ligne `<fichier> : <largeur> × <hauteur>` par image écrite — `<png>`, ou chaque
proposition, de 2400 × 2400, puis la planche, de 4000 × 1680 ; 1 et une ligne
`<chemin> : <message>` par erreur de la description, sur la sortie standard, ou le motif en une
ligne sur la sortie d'erreur — prérequis absent, capture en échec ou d'une autre taille,
préfixé du fichier en propositions ; 2 et son motif sur la sortie d'erreur, description ou
fichier des couleurs illisible ou mal formé, nom d'icône présent dans les deux jeux, image du
premier plan qui n'est plus un PNG ni un JPEG depuis sa validation, marqueur du gabarit sans
ressource — ou appel mal formé, une option hors de son mode ou des teintes qui ne font pas
quatre noms distincts de la palette compris, lu une fois la description validée.
Python 3.11 ou plus, bibliothèque standard seule : aucun `import playwright`.
"""

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

# Les scripts de `schema-architecture`, réutilisés sans copie (#290, décision 7) ; voir
# `miniature.py` pour les noms qu'aucun script de ce dossier ne doit porter.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "schema-architecture" / "scripts"))

from description import Abandon, sorties_en_utf_8, verifier_fichier
from export import (
    ecrire_image,
    ecrire_propositions,
    en_data,
    en_js,
    icones_en_ligne,
    remplir,
    svg_en_ligne,
)
from miniature import (
    COMPOSITIONS,
    DESCRIPTION,
    FOND,
    PALETTE,
    propositions,
    type_d_image,
    valider,
)

GABARIT = Path(__file__).resolve().parents[1] / "rendu" / "miniature.html"
# Les chemins par défaut, depuis la racine du projet ; celui de la description, `DESCRIPTION`,
# est celui de `miniature.py`.
DOSSIER = Path("docs/miniature/propositions")
IMAGE = Path("docs/miniature/miniature.png")
# L'icône Lucide dessinée derrière les icônes de « chantier ».
CONE = "traffic-cone"


def chantier(description: Mapping[str, Any], icones: Mapping[str, Path]) -> dict[str, object]:
    """Ce que « chantier » dessine en propre : le SVG du cône, puis ceux des trois icônes —
    distinctes, validées — dans l'ordre de la description, chaque logo peint à sa couleur.

    Raises:
        Abandon: le fichier des couleurs des logos est illisible (`icones_en_ligne`).
    """
    return {
        "cone": svg_en_ligne(icones[CONE], None),
        "icones": list(icones_en_ligne(description["icones"], icones).values()),
    }


def mise_en_scene(description: Mapping[str, Any], icones: Mapping[str, Path]) -> dict[str, object]:
    """Ce que « mise en scène » dessine en propre : le type du premier plan, et son image en URL
    `data:`, du type que portent ses premiers octets.

    Raises:
        Abandon: l'image n'est plus un PNG ni un JPEG depuis sa validation.
    """
    plan = description["premierPlan"]
    image = Path(plan["image"])
    type_mime = type_d_image(image)
    if type_mime is None:
        raise Abandon(f"{image} : n'est plus une image PNG ou JPEG")
    return {"premierPlan": {"type": plan["type"], "image": en_data(image, type_mime)}}


# Ce que chaque gabarit dessine en propre, tiré de la description validée et des icônes.
CONTENUS: dict[str, Callable[[Mapping[str, Any], Mapping[str, Path]], dict[str, object]]] = {
    "chantier": chantier,
    "mise-en-scene": mise_en_scene,
}


def assembler(
    description: Mapping[str, Any], icones: Mapping[str, Path], teinte: str, composition: str
) -> str:
    """La page autonome qui dessine `description` dans la teinte `teinte` et la composition
    `composition` de son gabarit : `rendu/miniature.html` rempli (`remplir`). Le rendu reçoit des
    couleurs et des fractions du côté, jamais un nom de teinte ni de composition.

    Args:
        description: une description valide (`miniature.valider`).
        icones: le fichier de chaque icône disponible — `icones_disponibles()`.
        teinte: un nom de `PALETTE`.
        composition: un nom des `COMPOSITIONS` du gabarit.

    Raises:
        Abandon: ce que dessine le gabarit est illisible (`CONTENUS`), ou un marqueur du
            gabarit est sans ressource (`remplir`).
    """
    gabarit = description["gabarit"]
    miniature = {
        "gabarit": gabarit,
        "couleurs": {"fond": FOND, "accent": PALETTE[teinte]},
        "composition": COMPOSITIONS[gabarit][composition],
        **CONTENUS[gabarit](description, icones),
    }
    return remplir(GABARIT, {"MINIATURE": en_js(miniature)})


def teintes(texte: str) -> list[str]:
    """Les noms de `--teintes`, séparés par des virgules, chacun sans les espaces qui le bordent."""
    return [nom.strip() for nom in texte.split(",")]


def analyseur() -> argparse.ArgumentParser:
    """L'analyseur de la ligne de commande ; voir le module."""
    parser = argparse.ArgumentParser(
        prog="exporter.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "description",
        type=Path,
        nargs="?",
        default=DESCRIPTION,
        help=f"le fichier JSON de la description (défaut : {DESCRIPTION})",
    )
    parser.add_argument(
        "--teintes",
        type=teintes,
        help="sans choix : quatre noms distincts de la palette, séparés par des virgules",
    )
    parser.add_argument(
        "--dossier",
        type=Path,
        help=f"sans choix : le dossier des propositions et de leur planche (défaut : {DOSSIER})",
    )
    parser.add_argument(
        "--png", type=Path, help=f"avec choix : l'image à écrire (défaut : {IMAGE})"
    )
    return parser


def main(argv: Sequence[str]) -> int:
    """Point d'entrée ; voir le module pour les sorties."""
    parser = analyseur()
    arguments = parser.parse_args(argv)
    code, lue, icones = verifier_fichier(arguments.description, valider=valider)
    if code:
        return code
    description = cast(Mapping[str, Any], lue)
    choix = "teinte" in description
    # Les options de l'autre mode.
    hors_mode = [
        option
        for option, valeur, avec_choix in (
            ("--teintes", arguments.teintes, False),
            ("--dossier", arguments.dossier, False),
            ("--png", arguments.png, True),
        )
        if valeur is not None and avec_choix != choix
    ]
    if hors_mode:
        mode = "que sans choix" if choix else "qu'avec un choix"
        parser.error(f"{', '.join(hors_mode)} ne vaut {mode} dans la description")
    if choix:
        couples = [(description["teinte"], description["composition"])]
    else:
        try:
            couples = propositions(description, arguments.teintes)
        except ValueError as erreur:
            parser.error(str(erreur))
    try:
        pages = [assembler(description, icones, *couple) for couple in couples]
    except Abandon as abandon:
        print(abandon, file=sys.stderr)
        return 2
    if not choix:
        return ecrire_propositions(pages, arguments.dossier or DOSSIER)
    return ecrire_image(pages[0], arguments.png or IMAGE)


if __name__ == "__main__":
    sorties_en_utf_8()
    sys.exit(main(sys.argv[1:]))
