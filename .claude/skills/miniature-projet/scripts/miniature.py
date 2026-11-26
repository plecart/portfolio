"""Valide la description d'une miniature de projet, `docs/miniature/miniature.json`, et porte la
palette, les compositions et les propositions de ses deux gabarits.

Usage :
    python miniature.py [<description>]

Lancé depuis la racine du dépôt du projet : `<description>` vaut par défaut
`docs/miniature/miniature.json`.

La validation se fait en **une passe** qui rend **toutes** les erreurs, avec les outils de
`schema-architecture/scripts/description.py`, importé par son chemin. La forme — toute clé absente
de cette liste est une erreur, celle de l'autre gabarit comprise, comme toute clé répétée dans un
même objet :

- `gabarit` : `chantier` ou `mise-en-scene` ;
- `icones` (« chantier » seulement, requis) : une liste de `NOMBRE_D_ICONES` noms distincts,
  chacun une icône du dossier d'icônes de `schema-architecture` — le nom sans extension d'un SVG de
  Lucide ou de Simple Icons ;
- `premierPlan` (« mise en scène » seulement, requis) : un objet — `type`, l'un de
  `TYPES_DE_PREMIER_PLAN` ; `image`, le chemin d'un fichier relatif au répertoire courant, la
  racine du projet, qui n'en sort pas (`dans_le_depot`) — ni chemin absolu, ni `..` qui remonte
  au-dessus —, et qui est un PNG ou un JPEG, reconnu à ses premiers octets (`type_d_image`),
  jamais à son extension ;
- `teinte` et `composition` (optionnels) : le choix du mainteneur, présents ensemble ou absents
  ensemble — `teinte`, un nom de `PALETTE` ; `composition`, un nom des `COMPOSITIONS` du gabarit.

Un gabarit absent ou inconnu porte son erreur : les clés des deux gabarits sont alors permises,
aucune requise, et une `composition` ne se vérifie que d'être une chaîne non vide. Chaque erreur
porte le chemin du champ en forme d'accès JSON — `icones[3]`, `premierPlan.image` — et un message
qui nomme la valeur fautive, en JSON, quand il y en a une.

Sortie : 0 et la ligne « valide » ; 1 et une ligne `<chemin> : <message>` par erreur, sur la
sortie standard ; 2 et son motif en une ligne sur la sortie d'erreur, fichier illisible, JSON mal
formé ou nom d'icône présent dans les deux jeux — ou appel mal formé. Python 3.11 ou plus,
bibliothèque standard seule.
"""

import argparse
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

# Les scripts de `schema-architecture`, que ce module réutilise sans copie (#290, décision 7).
# Aucun script de ce dossier ne porte le nom de l'un des leurs — `description`, `export`,
# `icones` : le premier trouvé sur `sys.path`, ou déjà en cache dans `sys.modules`, masquerait
# l'autre.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "schema-architecture" / "scripts"))

from description import (
    LISTE,
    TEXTE,
    Erreur,
    Passe,
    champ,
    est_objet,
    sorties_en_utf_8,
    verifier_fichier,
)
from export import SIGNATURE_PNG

DESCRIPTION = Path("docs/miniature/miniature.json")
NOMBRE_D_ICONES = 3
NOMBRE_DE_PROPOSITIONS = 4
TYPES_DE_PREMIER_PLAN = ("telephone", "capture", "schema")
# Les clés de la racine communes aux deux gabarits, chacune requise ou non.
COMMUNES = {"gabarit": True, "teinte": False, "composition": False}
PREMIER_PLAN = {"type": True, "image": True}
# Le type MIME de chaque format d'image permis au premier plan, et ses premiers octets : la
# signature d'un PNG (PNG, 3e édition, § 5.2) ; le marqueur SOI d'un JPEG, `FF D8`, puis l'octet
# `FF` qui ouvre tout marqueur suivant (ITU-T T.81, annexe B). Le type sert au rendu, qui pose
# l'image en URL `data:`.
SIGNATURES = {"image/png": SIGNATURE_PNG, "image/jpeg": bytes((0xFF, 0xD8, 0xFF))}

# Le fond fixe des deux gabarits, le `--bg` clair de la spec UX — mesuré `#F2EDE3` sur les
# couvertures en ligne de Spell Army et de Badge Mie, 2400 px, le 2026-11-26 (#290, décision 3 bis).
FOND = "#F3EDE4"
# Les six teintes de la palette, par nom, dans l'ordre où les propositions les prennent : chacune
# n'est que le trait d'accent — le cône de « chantier », l'anneau de « mise en scène » — à peine
# plus soutenu que `FOND`. Terracotta est le cône des couvertures en ligne, mesuré `#EBDBCE` ; les
# cinq autres, d'une autre teinte, ont sa luminance relative à 0,5 % près (calculé par `luminance`
# le 2026-11-26). Chacune contraste de 1,10:1 à 1,30:1 avec le fond (#290, critère 6), vérifié
# par les tests de la miniature.
PALETTE = {
    "terracotta": "#EBDBCE",
    "sauge": "#D5E2CF",
    "ardoise": "#D7DFE9",
    "prune": "#E8D9E6",
    "ocre": "#E9DDBE",
    "sarcelle": "#CCE2E2",
}

# Les quatre compositions de chaque gabarit, par nom, dans l'ordre où les propositions les
# prennent : des paramètres que le rendu lit tels quels, sans connaître les noms, en fractions du
# côté de l'image. La première calque la couverture en ligne du gabarit (mesurée le 2026-11-26) ;
# les trois autres s'en distinguent sur la carte de 160 px, ce dont la planche d'aperçu juge.
#
# « chantier » (Spell Army, l'assistant IA) : `cone`, le centre et le côté du carré où s'inscrit le
# `traffic-cone` de Lucide, qui peut sortir de l'image ; `icones`, le côté du carré de chaque
# icône et le centre de chacune, en triangle, qui reste dans l'image. « mise en scène » (Badge
# Mie) : `anneau`, son centre, son diamètre extérieur et son épaisseur ; `plan`, le premier plan,
# le milieu de son haut, sa largeur — celle du téléphone, que le rendu élargit pour une capture ou
# un schéma —, et son angle en degrés, tourné autour de ce milieu.
COMPOSITIONS = {
    "chantier": {
        "modele": {
            "cone": {"x": 0.5, "y": 0.474, "taille": 1.02},
            "icones": {"taille": 0.34, "places": [[0.5, 0.33], [0.265, 0.655], [0.735, 0.655]]},
        },
        "cone-a-gauche": {
            "cone": {"x": 0.36, "y": 0.5, "taille": 1.02},
            "icones": {"taille": 0.32, "places": [[0.6, 0.3], [0.4, 0.68], [0.78, 0.64]]},
        },
        "cone-a-droite": {
            "cone": {"x": 0.64, "y": 0.5, "taille": 1.02},
            "icones": {"taille": 0.32, "places": [[0.4, 0.3], [0.22, 0.64], [0.6, 0.68]]},
        },
        "grand-cone": {
            "cone": {"x": 0.5, "y": 0.62, "taille": 1.4},
            "icones": {"taille": 0.3, "places": [[0.5, 0.4], [0.27, 0.72], [0.73, 0.72]]},
        },
    },
    "mise-en-scene": {
        "modele": {
            "anneau": {"x": 0.5, "y": 0.585, "diametre": 0.896, "epaisseur": 0.02},
            "plan": {"x": 0.5, "haut": 0.114, "largeur": 0.606, "angle": -3},
        },
        "plan-a-gauche": {
            "anneau": {"x": 0.62, "y": 0.5, "diametre": 0.9, "epaisseur": 0.02},
            "plan": {"x": 0.42, "haut": 0.14, "largeur": 0.6, "angle": -4},
        },
        "plan-a-droite": {
            "anneau": {"x": 0.38, "y": 0.5, "diametre": 0.9, "epaisseur": 0.02},
            "plan": {"x": 0.58, "haut": 0.14, "largeur": 0.6, "angle": 4},
        },
        "grand-anneau": {
            "anneau": {"x": 0.5, "y": 0.5, "diametre": 1.2, "epaisseur": 0.03},
            "plan": {"x": 0.5, "haut": 0.2, "largeur": 0.66, "angle": 0},
        },
    },
}

# La lecture d'un champ propre à un gabarit : la passe, sa valeur et son chemin.
Lecture = Callable[[Passe, object, str], None]


def type_d_image(chemin: Path) -> str | None:
    """Le type MIME de l'image `chemin`, reconnu à ses premiers octets (`SIGNATURES`) ; `None`
    pour un fichier d'un autre format.

    Raises:
        OSError: le fichier est absent ou illisible — un dossier compris.
        ValueError: le chemin porte un caractère nul, que `open` refuse.
    """
    with chemin.open("rb") as fichier:
        tete = fichier.read(max(map(len, SIGNATURES.values())))
    return next((mime for mime, debut in SIGNATURES.items() if tete.startswith(debut)), None)


def dans_le_depot(chemin: Path) -> bool:
    """`chemin` est-il relatif — sans racine ni lecteur — et reste-t-il dans le répertoire
    courant, la racine du projet, ses `..` et ses liens résolus ?

    Raises:
        OSError: le chemin ne se résout pas.
        ValueError: le chemin porte un caractère nul.
    """
    return not chemin.anchor and chemin.resolve().is_relative_to(Path.cwd().resolve())


def lire_icones(passe: Passe, valeur: object, chemin: str) -> None:
    """Lit les icônes de « chantier » : `NOMBRE_D_ICONES` noms distincts du dossier d'icônes —
    chaque nom lu même quand leur nombre est faux."""
    noms = passe.verifier(valeur, chemin, LISTE)
    if noms is None:
        return
    if len(noms) != NOMBRE_D_ICONES:
        passe.refuser(chemin, f"attendu {NOMBRE_D_ICONES} icônes", noms)
    # Chaque nom lu, avec le chemin qui le porte le premier.
    vus: dict[str, str] = {}
    for i, nom in enumerate(noms):
        sous = f"{chemin}[{i}]"
        nom = passe.verifier(nom, sous, TEXTE)
        if nom is None:
            continue
        if nom in vus:
            passe.refuser(sous, f"icône déjà nommée par {vus[nom]}", nom)
            continue
        vus[nom] = sous
        if nom not in passe.icones:
            passe.refuser(sous, "attendu une icône du dossier d'icônes", nom)


def lire_premier_plan(passe: Passe, valeur: object, chemin: str) -> None:
    """Lit le premier plan de « mise en scène » : son type, et son image, lue sur le disque."""
    plan = passe.ouvrir(valeur, chemin, PREMIER_PLAN)
    if plan is None:
        return
    types = ", ".join(TYPES_DE_PREMIER_PLAN)
    passe.parmi(plan, chemin, "type", TYPES_DE_PREMIER_PLAN, f"l'un des types {types}")
    image = passe.lire(plan, chemin, "image", TEXTE)
    if image is None:
        return
    fichier, sous = Path(image), champ(chemin, "image")
    try:
        if not dans_le_depot(fichier):
            passe.refuser(sous, "attendu un chemin relatif qui reste dans le dépôt", image)
            return
        format_reconnu = type_d_image(fichier) is not None
    except (OSError, ValueError):
        passe.refuser(sous, "aucun fichier lisible à ce chemin", image)
        return
    if not format_reconnu:
        passe.refuser(sous, "attendu une image PNG ou JPEG", image)


# Les champs propres à chaque gabarit, tous requis par lui, chacun avec sa lecture.
PROPRES: dict[str, dict[str, Lecture]] = {
    "chantier": {"icones": lire_icones},
    "mise-en-scene": {"premierPlan": lire_premier_plan},
}


def gabarit_de(description: object) -> str | None:
    """Le gabarit que nomme `description`, s'il est connu ; `None` sinon."""
    gabarit = description.get("gabarit") if est_objet(description) else None
    return gabarit if isinstance(gabarit, str) and gabarit in PROPRES else None


def champs_propres(gabarit: str | None) -> dict[str, Lecture]:
    """Les champs propres à `gabarit`, avec leur lecture ; ceux des deux gabarits sous un gabarit
    absent ou inconnu."""
    if gabarit is not None:
        return PROPRES[gabarit]
    return {cle: lecture for champs in PROPRES.values() for cle, lecture in champs.items()}


def lire_choix(passe: Passe, racine: Mapping[str, object], gabarit: str | None) -> None:
    """Lit le choix du mainteneur : `teinte` et `composition`, ensemble ou ni l'une ni l'autre ;
    la composition parmi celles de `gabarit`, s'il est connu."""
    for cle, autre in (("teinte", "composition"), ("composition", "teinte")):
        if cle in racine and autre not in racine:
            passe.signaler(autre, f"champ requis avec {cle}")
    passe.parmi(racine, "", "teinte", PALETTE, f"l'une des teintes {', '.join(PALETTE)}")
    if gabarit is None:
        passe.lire(racine, "", "composition", TEXTE)
        return
    noms = ", ".join(COMPOSITIONS[gabarit])
    quoi = f"l'une des compositions du gabarit {gabarit} : {noms}"
    passe.parmi(racine, "", "composition", COMPOSITIONS[gabarit], quoi)


def valider(description: object, icones: Collection[str]) -> list[Erreur]:
    """Les erreurs de `description`, la description lue du JSON, dans l'ordre de lecture ; une
    liste vide si elle est valide. Une image se lit relativement au répertoire courant.

    Args:
        description: la valeur rendue par `json.loads`.
        icones: les noms des icônes disponibles — `icones_disponibles()` de `description.py` pour
            le dossier de `schema-architecture`.
    """
    passe = Passe(icones)
    gabarit = gabarit_de(description)
    propres = champs_propres(gabarit)
    # Un champ propre n'est requis que par un gabarit connu.
    racine = passe.ouvrir(
        description, "", {**COMMUNES, **dict.fromkeys(propres, gabarit is not None)}
    )
    if racine is None:
        return passe.erreurs
    passe.parmi(racine, "", "gabarit", PROPRES, f"l'un des gabarits {', '.join(PROPRES)}")
    for cle, lecture in propres.items():
        if cle in racine:
            lecture(passe, racine[cle], cle)
    lire_choix(passe, racine, gabarit)
    return passe.erreurs


def luminance(couleur: str) -> float:
    """La luminance relative de `couleur`, `#RRGGBB`, de 0 à 1 (WCAG 2.2, définition « relative
    luminance »)."""

    def lineaire(octet: int) -> float:
        valeur = octet / 255
        return valeur / 12.92 if valeur <= 0.04045 else ((valeur + 0.055) / 1.055) ** 2.4

    rouge, vert, bleu = map(lineaire, bytes.fromhex(couleur[1:]))
    return 0.2126 * rouge + 0.7152 * vert + 0.0722 * bleu


def contraste(a: str, b: str) -> float:
    """Le rapport de contraste de deux couleurs `#RRGGBB`, de 1 à 21, dans un sens comme dans
    l'autre (WCAG 2.2, définition « contrast ratio »)."""
    claire, sombre = sorted(map(luminance, (a, b)), reverse=True)
    return (claire + 0.05) / (sombre + 0.05)


def propositions(
    description: object, teintes: Sequence[str] | None = None
) -> list[tuple[str, str]]:
    """Les `NOMBRE_DE_PROPOSITIONS` couples (teinte, composition) d'un lancement sur
    `description` : la k-ième teinte avec la k-ième composition de son gabarit.

    Args:
        description: une description valide.
        teintes: `NOMBRE_DE_PROPOSITIONS` noms distincts de la palette, dans l'ordre des
            propositions — par défaut les premiers de `PALETTE`.

    Raises:
        ValueError: le gabarit de `description` est absent ou inconnu, ou `teintes` n'est pas
            fait de `NOMBRE_DE_PROPOSITIONS` noms distincts de la palette.
    """
    gabarit = gabarit_de(description)
    if gabarit is None:
        raise ValueError("description sans gabarit connu")
    retenues = list(PALETTE)[:NOMBRE_DE_PROPOSITIONS] if teintes is None else list(teintes)
    if not len(retenues) == len(set(retenues) & PALETTE.keys()) == NOMBRE_DE_PROPOSITIONS:
        raise ValueError(
            f"attendu {NOMBRE_DE_PROPOSITIONS} teintes distinctes de la palette "
            f"({', '.join(PALETTE)}), reçu {', '.join(retenues)}"
        )
    return list(zip(retenues, COMPOSITIONS[gabarit], strict=True))


def choisir(description: Mapping[str, object], teinte: str, composition: str) -> dict[str, object]:
    """`description` augmentée du choix du mainteneur — la teinte d'une proposition, la
    composition d'une autre, ou celles d'une seule —, à valider avant de l'écrire ; `description`
    reste telle quelle."""
    return {**description, "teinte": teinte, "composition": composition}


def main(argv: Sequence[str]) -> int:
    """Point d'entrée ; voir le module pour les sorties."""
    parser = argparse.ArgumentParser(
        prog="miniature.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "chemin",
        type=Path,
        nargs="?",
        default=DESCRIPTION,
        help="le fichier JSON de la description",
    )
    code, _, _ = verifier_fichier(parser.parse_args(argv).chemin, valider=valider)
    if code == 0:
        print("valide")
    return code


if __name__ == "__main__":
    sorties_en_utf_8()
    sys.exit(main(sys.argv[1:]))
