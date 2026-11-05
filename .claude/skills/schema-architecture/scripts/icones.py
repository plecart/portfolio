"""Tire une icône de la version épinglée de son jeu et la copie dans le dossier d'icônes du skill.

Usage :
    python icones.py <nom> (--simple-icons | --lucide)

`<nom>` est le nom du SVG chez l'amont, sans extension : le slug Simple Icons d'un logo
(`--simple-icons`), le nom Lucide d'une icône neutre (`--lucide`). Le SVG se tire de la version
épinglée par son URL versionnée sur jsDelivr, et s'écrit tel quel dans
`icones/<jeu>/<nom>.svg`. Un logo y ajoute sa couleur, lue dans les données de la même version, à
`icones/simple-icons/couleurs.json`, clés triées. Rien ne s'écrit avant que tout soit lu.

Sortie : 0 et ce qui a été écrit, ou que l'icône est déjà là ; 1 et son motif en une ligne sur la
sortie d'erreur — nom inconnu chez l'amont (404), réseau en échec, logo sans couleur dans les
données, nom déjà pris par l'autre jeu — ; 2 et son motif, appel mal formé ou nom présent dans
les deux jeux. Python 3.11 ou plus, bibliothèque standard seule.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from description import (
    COULEURS_DES_LOGOS,
    ICONES,
    LOGOS,
    Abandon,
    icones_disponibles,
    sorties_en_utf_8,
)

SIMPLE_ICONS = "15.0.0"
LUCIDE = "0.460.0"
CDN = "https://cdn.jsdelivr.net/npm"
# L'URL du SVG d'une icône, par jeu.
SOURCES = {
    LOGOS: f"{CDN}/simple-icons@{SIMPLE_ICONS}/icons/{{}}.svg",
    "lucide": f"{CDN}/lucide-static@{LUCIDE}/icons/{{}}.svg",
}
# Le titre et la couleur de chaque logo ; le `data.json` du matériel de départ n'est pas celui de
# cette version (mesuré au bloc A de #217).
DONNEES = f"{CDN}/simple-icons@{SIMPLE_ICONS}/data/simple-icons.json"
DELAI = 30  # secondes par requête
# `titleToSlug` de Simple Icons (`sdk.mjs` de la 15.0.0) : ces caractères remplacés, puis la
# décomposition NFD, puis tout ce qui n'est ni minuscule ASCII ni chiffre retiré. Rend les
# 3 291 noms de `icons/` de la 15.0.0 pour ses 3 291 logos (mesuré le 2026-11-05).
REMPLACEMENTS = {
    "+": "plus",
    ".": "dot",
    "&": "and",
    "đ": "d",
    "ħ": "h",
    "ı": "i",
    "ĸ": "k",
    "ŀ": "l",
    "ł": "l",
    "ß": "ss",
    "ŧ": "t",
    "ø": "o",
}


def nom_d_icone(texte: str) -> str:
    """`texte` s'il peut nommer un fichier d'icône : minuscules ASCII, chiffres et tirets."""
    if not re.fullmatch("[a-z0-9-]+", texte):
        raise argparse.ArgumentTypeError(f"nom d'icône invalide : {texte!r}")
    return texte


def slug(titre: str) -> str:
    """Le slug d'un logo de titre `titre`, comme le calcule Simple Icons."""
    remplace = "".join(REMPLACEMENTS.get(caractere, caractere) for caractere in titre.lower())
    return re.sub("[^a-z0-9]", "", unicodedata.normalize("NFD", remplace))


def tirer(url: str) -> bytes:
    """Le contenu de `url`.

    Raises:
        URLError: le réseau a échoué ; `HTTPError`, sa sous-classe, si l'amont a répondu une
            erreur, 404 pour un nom inconnu.
    """
    with urlopen(url, timeout=DELAI) as reponse:
        return cast(bytes, reponse.read())


def couleur(nom: str) -> str | None:
    """La couleur du logo de slug `nom`, en `#RRGGBB`, lue dans les données de la version
    épinglée ; `None` s'il n'y figure pas."""
    logos = cast(list[dict[str, str]], json.loads(tirer(DONNEES)))
    for logo in logos:
        if logo.get("slug", slug(logo["title"])) == nom:
            return f"#{logo['hex']}"
    return None


def ajouter_couleur(dossier: Path, nom: str, valeur: str) -> None:
    """Ajoute `nom` et sa couleur `valeur` au fichier des couleurs de `dossier`, clés triées."""
    chemin = dossier / COULEURS_DES_LOGOS
    couleurs = cast(dict[str, str], json.loads(chemin.read_text(encoding="utf-8")))
    couleurs[nom] = valeur
    texte = json.dumps(couleurs, ensure_ascii=False, indent=2, sort_keys=True)
    chemin.write_text(f"{texte}\n", encoding="utf-8", newline="")


def ajouter(nom: str, jeu: str) -> tuple[int, str]:
    """Copie l'icône `nom` du jeu `jeu` dans le dossier d'icônes du skill.

    Returns:
        Le code de sortie et ce qu'il faut en dire, en une ligne.
    """
    presente = icones_disponibles(ICONES).get(nom)
    if presente is not None:
        if presente.parent.name == jeu:
            return 0, f"{nom} : déjà présente, {presente}"
        return 1, f"{nom} : nom déjà pris par le jeu {presente.parent.name}"
    logo = jeu == LOGOS
    try:
        svg = tirer(SOURCES[jeu].format(nom))
        teinte = couleur(nom) if logo else None
    except HTTPError as erreur:
        return 1, f"{nom} : HTTP {erreur.code} sur {erreur.url}"
    except URLError as erreur:
        return 1, f"{nom} : réseau en échec — {erreur.reason}"
    if logo and teinte is None:
        return 1, f"{nom} : aucun logo de ce slug dans {DONNEES}"
    dossier = ICONES / jeu
    (dossier / f"{nom}.svg").write_bytes(svg)
    if teinte is None:
        return 0, f"{nom} : écrite dans {dossier}"
    ajouter_couleur(dossier, nom, teinte)
    return 0, f"{nom} : écrite dans {dossier}, couleur {teinte}"


def main(argv: Sequence[str]) -> int:
    """Point d'entrée ; voir le module pour les sorties."""
    parser = argparse.ArgumentParser(
        prog="icones.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("nom", type=nom_d_icone, help="le nom du SVG chez l'amont, sans extension")
    jeux = parser.add_mutually_exclusive_group(required=True)
    for jeu in SOURCES:
        jeux.add_argument(f"--{jeu}", dest="jeu", action="store_const", const=jeu)
    arguments = parser.parse_args(argv)
    try:
        code, compte_rendu = ajouter(arguments.nom, arguments.jeu)
    except Abandon as motif:
        print(motif, file=sys.stderr)
        return 2
    print(compte_rendu, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sorties_en_utf_8()
    sys.exit(main(sys.argv[1:]))
