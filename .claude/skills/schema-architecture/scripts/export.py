"""Exporte le schéma d'architecture d'un projet en image PNG carrée de 2400 × 2400 px — ou ses
propositions, de 2 à 4 variantes de sa mise en page, et leur planche d'aperçu.

Usage :
    python export.py [<description> [<png>]]
    python export.py --propositions <description> <description> [...] [--dossier <dossier>]

Lancé depuis la racine du dépôt du projet décrit : `<description>` vaut par défaut
`docs/schema/architecture.json`, `<png>` `docs/schema/architecture.png`, `<dossier>`
`docs/schema/propositions`.

Trois temps, chacun arrêté par un échec :

1. **valider** la description (`description.py`) contre le dossier d'icônes du skill. Des
   erreurs : elles sortent toutes, et aucun navigateur ne démarre ;
2. **assembler** une page autonome dans un dossier temporaire : le gabarit `rendu/page.html`,
   rough.js et la description en ligne, les polices en `data:` (base64), les icônes que nomme la
   description en SVG en ligne, chaque logo peint à sa couleur (`couleurs.json`), et le nom de
   l'attribut qu'elle pose une fois rendue (`PRET`). La page ne fait aucune requête, ni réseau
   ni fichier voisin ;
3. **capturer** la page par la CLI de Playwright, le paquet Python à la version `PLAYWRIGHT`,
   lancé par `uv run --no-project --with`, hors de tout projet : Chromium sans fenêtre —
   `screenshot` le lance ainsi —, fenêtre de 1200 × 1200 px (`FENETRE`) au facteur d'échelle 2
   (`FACTEUR`) du descripteur « Desktop Chrome HiDPI » (`APPAREIL`), schéma clair, capture après
   cet attribut, `DELAI` au plus par attente. Le descripteur fixe le facteur, `--viewport-size`
   remplace sa fenêtre : le dessin garde la mise en page de 1200 px et double sa finesse
   (Playwright 1.64.1, `launchContext` du pilote, `driver/package/lib/coreBundle.js` : le
   descripteur copié, puis sa fenêtre remplacée par celle de `--viewport-size` ; son facteur
   n'est remplacé que sous une fenêtre de navigateur, que `screenshot` n'ouvre pas ; le
   descripteur à `deviceScaleFactor: 2` ; lus le 2026-11-08). Mesuré le 2026-11-08 sur le
   poste : un PNG de 2400 × 2400, où un carré de 600 px CSS occupe 1200 px. Puis la taille se
   relit dans l'en-tête IHDR du PNG : le côté ne dépend ni du zoom ni de l'écran du poste.

L'image n'est écrite à `<png>` qu'à la fin, à la bonne taille.

**Propositions** (`--propositions`) : de 2 à 4 descriptions (`NOMBRE_DE_PROPOSITIONS`), les
variantes de mise en page d'une même liste. Toutes se valident d'abord, en une passe : une seule
fautive, et rien n'est capturé ni écrit. Puis chacune s'exporte, dans l'ordre des arguments, en
`<dossier>/proposition-<k>.png` (k = 1…), et la planche d'aperçu (`planche`) les montre en
`<dossier>/planche.png` : le gabarit `rendu/planche.html`, chaque proposition en URL `data:`,
numérotée, dans le cadre d'une carte polaroid simple desktop puis mobile (spec UX §4.1), sur le
fond de page clair puis sombre (§2.1) ; capturée de même, dans une fenêtre de 2000 × 840 px
(`FENETRE_PLANCHE`) au même facteur. Les propositions et la planche d'un lancement précédent
sont d'abord retirées du dossier, le reste y demeure ; puis la première capture en échec arrête
l'export, les propositions déjà écrites restant.

Prérequis, une fois par poste : `uv`, puis Chromium pour cette version de Playwright,
`uv run --no-project --with playwright==<PLAYWRIGHT> playwright install chromium`.

Sortie : 0 et une ligne `<fichier> : <largeur> × <hauteur>` par image écrite — `<png>`, de
2400 × 2400, ou chaque proposition puis la planche, de 4000 × 1680 ; 1 et une ligne
`<chemin> : <message>` par erreur de la description, sur la sortie standard, ou le motif en une
ligne sur la sortie d'erreur — prérequis absent, capture en échec ou d'une autre taille ; 2 et
son motif en une ligne sur la sortie d'erreur, description ou fichier des couleurs illisible ou
mal formé, nom d'icône présent dans les deux jeux, marqueur du gabarit sans ressource — ou appel
mal formé, nombre de propositions compris. En propositions, chaque erreur et chaque motif d'une
description ou d'une image est préfixé de son fichier, `<fichier> : `. Python 3.11 ou plus,
bibliothèque standard seule : aucun `import playwright`.
"""

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from description import (
    ICONES,
    Abandon,
    est_liste,
    est_objet,
    lire_couleurs,
    sorties_en_utf_8,
    verifier_fichier,
)

PLAYWRIGHT = "1.64.1"
# Une fenêtre de capture, largeur et hauteur en px CSS : la mise en page de la page capturée.
Fenetre = tuple[int, int]
# La fenêtre du schéma : la mise en page du dessin.
FENETRE: Fenetre = (1200, 1200)
# La fenêtre de la planche d'aperçu (`rendu/planche.html`) : une bande claire sur une sombre,
# 420 px chacune ; dans chaque bande, jusqu'à quatre propositions côte à côte, chacune son
# numéro au-dessus de ses deux cartes, 436 × 322 px, 48 px entre deux — 1888 px pour quatre
# (calculé sur le CSS du gabarit). Mesuré le 2026-11-25 sur le poste, quatre propositions, aux
# pixels de la planche de 4000 × 1680 : cartes de 240 × 282 et 176 × 216 px CSS, 56 de marge.
FENETRE_PLANCHE: Fenetre = (2000, 840)
# Le descripteur de la capture, et le facteur d'échelle qu'il fixe (docstring, temps 3).
APPAREIL = "Desktop Chrome HiDPI"
FACTEUR = 2
# Le nombre de propositions que montre une planche, bornes comprises.
NOMBRE_DE_PROPOSITIONS = (2, 4)
PREREQUIS = f"uv run --no-project --with playwright=={PLAYWRIGHT} playwright install chromium"
RENDU = Path(__file__).resolve().parent.parent / "rendu"
POLICES = RENDU / "polices"
MANROPE = POLICES / "manrope-latin.woff2"
# Les chemins par défaut, depuis la racine du projet décrit.
DESCRIPTION = Path("docs/schema/architecture.json")
IMAGE = Path("docs/schema/architecture.png")
DOSSIER = Path("docs/schema/propositions")
# Le nom de la k-ième proposition d'un dossier ; `*` les désigne toutes.
PROPOSITION = "proposition-{}.png"
# L'attribut que la page pose sur `<body>` une fois rendue, polices chargées : l'export l'injecte
# dans le gabarit (`/*PRET*/`) et attend `MARQUEUR` avant de capturer — une seule source.
PRET = "data-rendu-pret"
MARQUEUR = f"body[{PRET}]"
# Le délai de chaque attente de la capture, en millisecondes : la CLI n'en a aucun par défaut
# (`--timeout`), et une page qui ne poserait pas son marqueur l'attendrait sans fin.
DELAI = 30_000
# Le début de la sortie d'erreur de la CLI quand Chromium manque (mesuré le 2026-11-05 sous
# `PLAYWRIGHT_BROWSERS_PATH` vide : sortie 1).
CHROMIUM_ABSENT = "Executable doesn't exist"
# Les huit premiers octets de tout PNG (PNG, 3e édition, § 5.2).
SIGNATURE_PNG = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))


def icones_utilisees(noeud: object) -> set[str]:
    """Les icônes que nomme la description, à tout niveau : chaque valeur d'une clé `icon`."""
    if est_objet(noeud):
        icone = noeud.get("icon")
        propres = {icone} if isinstance(icone, str) else set[str]()
        return propres.union(*map(icones_utilisees, noeud.values()))
    if est_liste(noeud):
        return set[str]().union(*map(icones_utilisees, noeud))
    return set()


def en_js(valeur: object) -> str:
    """`valeur` en littéral JavaScript, à poser dans un `<script>` : du JSON dont chaque `<` est
    échappé — aucune séquence `</script` ni `<!--` ne peut y naître."""
    return json.dumps(valeur, ensure_ascii=False).replace("<", "\\u003c")


def svg_en_ligne(chemin: Path, couleur: str | None) -> str:
    """Le SVG du fichier `chemin`, peint à `couleur` si c'est un logo ; une icône neutre garde
    son trait `currentColor`, l'encre du texte."""
    svg = chemin.read_text(encoding="utf-8")
    return svg.replace("<svg", f'<svg fill="{couleur}"', 1) if couleur else svg


def en_data(chemin: Path, type_mime: str) -> str:
    """Le fichier `chemin` en URL `data:`, encodé en base64."""
    return f"data:{type_mime};base64,{base64.b64encode(chemin.read_bytes()).decode('ascii')}"


def remplir(gabarit: Path, ressources: Mapping[str, str]) -> str:
    """La page autonome du gabarit `gabarit` : chaque marqueur `/*NOM*/` remplacé par sa
    ressource, `/*PRET*/` compris — le nom de l'attribut que la page pose sur `<body>` une fois
    rendue, et que la capture attend (`capturer`).

    Args:
        gabarit: le fichier HTML du gabarit.
        ressources: le texte de chaque marqueur, par son nom ; un `PRET` y est ignoré.

    Raises:
        Abandon: un marqueur du gabarit n'a pas de ressource — le motif nomme le premier.
    """
    toutes = {**ressources, "PRET": en_js(PRET)}

    def ressource(marqueur: re.Match[str]) -> str:
        if marqueur[1] not in toutes:
            raise Abandon(f"{gabarit} : marqueur {marqueur[0]} sans ressource")
        return toutes[marqueur[1]]

    # Une seule passe : une ressource qui porterait un `/*NOM*/` n'est pas relue.
    return re.sub("/[*]([A-Z_]+)[*]/", ressource, gabarit.read_text(encoding="utf-8"))


def assembler(description: object, icones: Mapping[str, Path]) -> str:
    """La page autonome qui dessine `description` : le gabarit `rendu/page.html` rempli
    (`remplir`).

    Args:
        description: la description validée.
        icones: le fichier de chaque icône disponible — `icones_disponibles()`.

    Raises:
        Abandon: le fichier des couleurs des logos est illisible (`lire_couleurs`), ou un
            marqueur du gabarit est sans ressource (`remplir`).
    """
    couleurs = lire_couleurs(ICONES)
    return remplir(
        RENDU / "page.html",
        {
            "MANROPE": en_data(MANROPE, "font/woff2"),
            "SHANTELL_SANS": en_data(
                POLICES / "shantell-sans-latin-wght-normal.woff2", "font/woff2"
            ),
            "ROUGH": (RENDU / "rough.js").read_text(encoding="utf-8"),
            "DESCRIPTION": en_js(description),
            "ICONES": en_js(
                {
                    nom: svg_en_ligne(icones[nom], couleurs.get(nom))
                    for nom in sorted(icones_utilisees(description))
                }
            ),
        },
    )


def assembler_planche(images: Sequence[Path]) -> str:
    """La page autonome de la planche d'aperçu : le gabarit `rendu/planche.html` rempli
    (`remplir`), Manrope et chaque image de `images` en URL `data:` — la page numérote les images
    par leur rang, à partir de 1.

    Raises:
        OSError: une image est illisible.
        Abandon: un marqueur du gabarit est sans ressource (`remplir`).
    """
    return remplir(
        RENDU / "planche.html",
        {
            "MANROPE": en_data(MANROPE, "font/woff2"),
            "IMAGES": en_js([en_data(image, "image/png") for image in images]),
        },
    )


def lancer_capture(page: Path, png: Path, fenetre: Fenetre) -> str | None:
    """Lance la CLI de Playwright, qui capture le fichier `page` dans `png`, fenêtre `fenetre` ;
    le motif de l'échec en une ligne, `None` si elle aboutit."""
    uv = shutil.which("uv")
    if uv is None:
        return f"uv introuvable — prérequis : installer uv, puis {PREREQUIS}"
    fait = subprocess.run(
        [
            uv,
            "run",
            "--no-project",
            "--with",
            f"playwright=={PLAYWRIGHT}",
            "playwright",
            "screenshot",
            "--browser",
            "chromium",
            "--device",
            APPAREIL,
            "--viewport-size",
            f"{fenetre[0]},{fenetre[1]}",
            "--color-scheme",
            "light",
            "--wait-for-selector",
            MARQUEUR,
            "--timeout",
            str(DELAI),
            page.as_uri(),
            str(png),
        ],
        capture_output=True,
        check=False,
    )
    if fait.returncode == 0:
        return None
    sortie = fait.stderr.decode("utf-8", errors="replace").strip()
    if CHROMIUM_ABSENT in sortie:
        return f"Chromium absent pour Playwright {PLAYWRIGHT} — prérequis : {PREREQUIS}"
    return f"capture en échec, sortie {fait.returncode} — {(sortie.splitlines() or [''])[0]}"


def taille_png(chemin: Path) -> tuple[int, int] | None:
    """La largeur et la hauteur que porte l'en-tête du PNG `chemin` — son premier bloc, IHDR
    (PNG, 3e édition, § 5.3 et § 11.2.1) ; `None` pour un fichier absent, ou qui ne commence pas
    par la signature PNG suivie de ce bloc."""
    try:
        with chemin.open("rb") as fichier:
            tete = fichier.read(24)
    except OSError:
        return None
    if tete[:8] != SIGNATURE_PNG or tete[12:16] != b"IHDR":
        return None
    return int.from_bytes(tete[16:20], "big"), int.from_bytes(tete[20:24], "big")


def taille_attendue(fenetre: Fenetre) -> tuple[int, int]:
    """La taille en pixels de la capture d'une fenêtre `fenetre`, au facteur `FACTEUR`."""
    return fenetre[0] * FACTEUR, fenetre[1] * FACTEUR


def en_texte(taille: tuple[int, int]) -> str:
    """`taille`, largeur et hauteur, en texte : `2400 × 2400`."""
    return f"{taille[0]} × {taille[1]}"


def capturer(html: str, png: Path, fenetre: Fenetre = FENETRE) -> str | None:
    """Capture la page autonome `html` — son texte, rempli par `remplir` — dans une fenêtre de
    `fenetre` px CSS, et l'écrit à `png` ; le motif de l'échec en une ligne, `None` si elle
    aboutit. `png` n'est écrit qu'à la fin, à la taille `taille_attendue(fenetre)` relue dans
    l'en-tête du PNG."""
    attendue = taille_attendue(fenetre)
    with tempfile.TemporaryDirectory() as dossier:
        page, capture = Path(dossier) / "page.html", Path(dossier) / "capture.png"
        page.write_text(html, encoding="utf-8")
        motif = lancer_capture(page, capture, fenetre)
        if motif:
            return motif
        taille = taille_png(capture)
        if taille is None:
            return "capture illisible : pas un PNG"
        if taille != attendue:
            return f"capture de {en_texte(taille)} px, attendu {en_texte(attendue)}"
        png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(capture, png)
    return None


def refus_du_nombre(nombre: int) -> str | None:
    """Le motif du refus de `nombre` propositions, `None` s'il est dans les bornes
    `NOMBRE_DE_PROPOSITIONS`."""
    minimum, maximum = NOMBRE_DE_PROPOSITIONS
    if minimum <= nombre <= maximum:
        return None
    return f"de {minimum} à {maximum} propositions, reçu {nombre}"


def planche(images: Sequence[Path], sortie: Path) -> str | None:
    """Capture la planche d'aperçu des propositions `images` (`assembler_planche`), et l'écrit à
    `sortie`.

    Args:
        images: de 2 à 4 PNG carrés (`NOMBRE_DE_PROPOSITIONS`), numérotés par leur rang.
        sortie: le PNG de la planche, écrit seulement si la capture aboutit à sa taille
            (`capturer`, fenêtre `FENETRE_PLANCHE`).

    Returns:
        Le motif de l'échec en une ligne — nombre d'images refusé, capture impossible ou d'une
        autre taille —, `None` si la planche est écrite.

    Raises:
        OSError: une image est illisible.
        Abandon: un marqueur du gabarit est sans ressource (`remplir`).
    """
    motif = refus_du_nombre(len(images))
    if motif:
        return motif
    return capturer(assembler_planche(images), sortie, FENETRE_PLANCHE)


def signaler(motif: str | None, png: Path, fenetre: Fenetre, prefixe: str) -> int:
    """Écrit l'issue de la capture de `png` dans `fenetre` : le motif de l'échec, après
    `prefixe`, sur la sortie d'erreur, ou la ligne `<png> : <largeur> × <hauteur>` ; rend son
    code de sortie, 1 ou 0."""
    if motif:
        print(f"{prefixe}{motif}", file=sys.stderr)
        return 1
    print(f"{png} : {en_texte(taille_attendue(fenetre))}")
    return 0


def ecrire_propositions(pages: Sequence[str], dossier: Path) -> int:
    """Capture chaque page de `pages` en proposition `<dossier>/proposition-<k>.png`, k = 1…,
    puis leur planche `<dossier>/planche.png` ; la première capture en échec arrête, chaque
    motif préfixé de son fichier. Les propositions et la planche d'un lancement précédent sont
    d'abord retirées — deux après quatre n'en laissent pas d'anciennes —, le reste du dossier
    demeure. Rend le code de sortie, 0 ou 1."""
    sortie = dossier / "planche.png"
    for perimee in [*dossier.glob(PROPOSITION.format("*")), sortie]:
        perimee.unlink(missing_ok=True)
    images = [dossier / PROPOSITION.format(numero) for numero in range(1, len(pages) + 1)]
    for page, image in zip(pages, images, strict=True):
        if signaler(capturer(page, image), image, FENETRE, f"{image} : "):
            return 1
    return signaler(planche(images, sortie), sortie, FENETRE_PLANCHE, f"{sortie} : ")


def assembler_fichiers(chemins: Sequence[Path]) -> tuple[int, list[str]]:
    """Valide chaque description de `chemins`, toutes d'abord, puis les assemble ; à plusieurs
    descriptions, chaque erreur et chaque motif est préfixé de son fichier. Rend le code de
    sortie de la validation ou de l'assemblage — voir le module — et les pages, aucune sur un
    code non nul."""

    def prefixe(chemin: Path) -> str:
        return f"{chemin} : " if len(chemins) > 1 else ""

    verifiees = [verifier_fichier(chemin, prefixe(chemin)) for chemin in chemins]
    code = max(code for code, _, _ in verifiees)
    if code:
        return code, []
    try:
        return 0, [assembler(description, icones) for _, description, icones in verifiees]
    except Abandon as abandon:
        print(abandon, file=sys.stderr)
        return 2, []


def exporter(description: Path, png: Path) -> int:
    """Exporte la description `description` à l'image `png` ; rend le code de sortie."""
    code, pages = assembler_fichiers([description])
    return code or signaler(capturer(pages[0], png), png, FENETRE, "")


def exporter_propositions(descriptions: Sequence[Path], dossier: Path) -> int:
    """Exporte chaque description de `descriptions` en proposition de `dossier`, puis leur
    planche (`ecrire_propositions`) ; rend le code de sortie."""
    code, pages = assembler_fichiers(descriptions)
    return code or ecrire_propositions(pages, dossier)


def main(argv: Sequence[str]) -> int:
    """Point d'entrée ; voir le module pour les sorties."""
    minimum, maximum = NOMBRE_DE_PROPOSITIONS
    parser = argparse.ArgumentParser(
        prog="export.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "description",
        type=Path,
        nargs="?",
        help=f"le fichier JSON de la description (défaut : {DESCRIPTION})",
    )
    parser.add_argument("png", type=Path, nargs="?", help=f"l'image à écrire (défaut : {IMAGE})")
    parser.add_argument(
        "--propositions",
        type=Path,
        nargs="+",
        metavar="DESCRIPTION",
        help=f"de {minimum} à {maximum} descriptions, chacune exportée en proposition, puis leur "
        "planche",
    )
    parser.add_argument(
        "--dossier",
        type=Path,
        help=f"le dossier des propositions et de leur planche (défaut : {DOSSIER})",
    )
    arguments = parser.parse_args(argv)
    if arguments.propositions is None:
        if arguments.dossier is not None:
            parser.error("--dossier ne vaut qu'avec --propositions")
        return exporter(arguments.description or DESCRIPTION, arguments.png or IMAGE)
    if arguments.description is not None:
        parser.error("--propositions ne prend ni <description> ni <png>")
    motif = refus_du_nombre(len(arguments.propositions))
    if motif:
        parser.error(motif)
    return exporter_propositions(arguments.propositions, arguments.dossier or DOSSIER)


if __name__ == "__main__":
    sorties_en_utf_8()
    sys.exit(main(sys.argv[1:]))
