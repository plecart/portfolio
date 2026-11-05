"""Valide la description d'un schéma d'architecture, `docs/schema/architecture.json`.

Usage :
    python description.py <chemin du JSON>

La description dit ce que le rendu dessine ; ce script la vérifie avant tout dessin, en **une
passe** qui rend **toutes** les erreurs : chaque champ pour sa présence et son type, puis les
contraintes qui lient les champs. Une erreur de type d'un nœud n'empêche pas de lire ses frères.

La forme — toute clé absente de cette liste est une erreur, à tout niveau, comme toute clé
répétée dans un même objet :

- racine : `intro`, chaîne non vide ; `columns`, entier ≥ 1, le nombre de colonnes de la grille ;
  `secretManager` (optionnel), `{"name": chaîne non vide, "icon": icône}`, le gestionnaire de
  secrets dont le logo marque les cartes à `secret` ; `zones`, liste non vide d'entrées ;
  `links` (optionnel, vide permis), liste de liens ;
- entrée : une zone, ou une liste non vide de zones posées côte à côte ;
- zone : `label`, chaîne non vide ; `color`, l'une de `COULEURS` ; `icon` (optionnel), icône ;
  `span` (optionnel, requis pour une zone côte à côte), `[premier, dernier]`, deux entiers,
  `0 ≤ premier ≤ dernier ≤ columns - 1` — les spans de zones côte à côte ne se chevauchent
  pas ; `rows` (optionnel), liste de rangées, chacune une liste non vide de cartes ; `zones`
  (optionnel), liste d'entrées ; `rows` ou `zones` non vide, l'un au moins ;
- carte : `id`, chaîne non vide, unique dans la description ; `name`, chaîne non vide ; `icon`,
  icône ; `column`, nombre multiple de 0,5, dans la grille `[0, columns - 1]` et dans le span de
  sa zone ; `secret` (optionnel), chaîne non vide, qui demande un `secretManager` ;
- lien : `from` et `to`, deux `id` de cartes existantes, différents ; `route` (optionnel), l'une
  de `ROUTES`.

Une icône est le nom, sans extension, d'un SVG de `icones/simple-icons/` ou de `icones/lucide/`,
dans le dossier du skill — d'un seul des deux : le rendu n'a jamais à choisir. Les bornes de la
grille ne se vérifient que sur un `columns` valide : invalide, il porte déjà son erreur.

Chaque erreur porte le chemin du champ en forme d'accès JSON — `zones[2][1].rows[0][1].column`,
`links[3].to` — et un message qui nomme la valeur fautive, en JSON, quand il y en a une ; une clé
en double, le chemin de son objet et le nom de la clé.

Le fichier se lit en UTF-8, un BOM en tête permis. Sortie : 0 et la ligne « valide » ; 1 et une
ligne `<chemin> : <message>` par erreur, sur la sortie standard ; 2 et son motif en une ligne sur
la sortie d'erreur, fichier illisible, JSON mal formé ou nom d'icône présent dans les deux jeux —
ou appel mal formé. Python 3.11 ou plus, bibliothèque standard seule.
"""

import argparse
import io
import json
import sys
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeGuard, TypeVar

ICONES = Path(__file__).resolve().parent.parent / "icones"
JEUX_D_ICONES = ("simple-icons", "lucide")
COULEURS = ("gold", "blue", "orange", "red", "green", "grey", "lane")
ROUTES = ("left", "right", "under")
# Les clés de chaque objet de la description, chacune requise ou non.
RACINE = {"intro": True, "columns": True, "secretManager": False, "zones": True, "links": False}
GESTIONNAIRE = {"name": True, "icon": True}
ZONE = {"label": True, "color": True, "icon": False, "span": False, "rows": False, "zones": False}
CARTE = {"id": True, "name": True, "icon": True, "column": True, "secret": False}
LIEN = {"from": True, "to": True, "route": False}

T = TypeVar("T")
# Un intervalle de colonnes, bornes comprises : la grille, ou le span d'une zone.
Bornes = tuple[int, int]


class Abandon(Exception):
    """Ce qui empêche la validation de commencer — fichier illisible, JSON mal formé, nom d'icône
    présent dans les deux jeux —, avec son motif en une ligne."""


class Objet(dict[str, object]):
    """Un objet JSON lu par `lire_description` : ses champs, et `doublons`, les clés qu'il porte
    plus d'une fois — `json.loads` n'en garderait que la dernière valeur, sans rien dire.

    Args:
        paires: les champs dans l'ordre du texte, tels que les passe `object_pairs_hook`.
    """

    def __init__(self, paires: Iterable[tuple[str, object]]) -> None:
        paires = list(paires)
        super().__init__(paires)
        comptes = Counter(cle for cle, _ in paires)
        self.doublons = [cle for cle, nombre in comptes.items() if nombre > 1]


@dataclass(frozen=True)
class Erreur:
    """Un champ fautif : son chemin d'accès JSON — vide pour la racine — et ce qui ne va pas."""

    chemin: str
    message: str

    def __str__(self) -> str:
        return f"{self.chemin or '(racine)'} : {self.message}"


def est_objet(valeur: object) -> TypeGuard[dict[str, object]]:
    """Un objet JSON, dont les clés sont toujours des chaînes."""
    return isinstance(valeur, dict)


def est_texte(valeur: object) -> TypeGuard[str]:
    """Une chaîne non vide."""
    return isinstance(valeur, str) and valeur != ""


def est_entier(valeur: object) -> TypeGuard[int]:
    """Un entier, pas un booléen — que Python range parmi les entiers."""
    return isinstance(valeur, int) and not isinstance(valeur, bool)


def est_entier_positif(valeur: object) -> TypeGuard[int]:
    """Un entier ≥ 1."""
    return est_entier(valeur) and valeur >= 1


def est_nombre(valeur: object) -> TypeGuard[int | float]:
    """Un entier ou un flottant, pas un booléen."""
    return est_entier(valeur) or isinstance(valeur, float)


def est_liste(valeur: object) -> TypeGuard[list[object]]:
    """Une liste, vide permise."""
    return isinstance(valeur, list)


def est_liste_non_vide(valeur: object) -> TypeGuard[list[object]]:
    """Une liste d'un élément au moins."""
    return est_liste(valeur) and valeur != []


def est_span(valeur: object) -> TypeGuard[list[int]]:
    """Deux entiers dans une liste."""
    return est_liste(valeur) and len(valeur) == 2 and all(map(est_entier, valeur))


# `class Attendu[T]` demande Python 3.12 ; le script tient 3.11 (docstring du module).
@dataclass(frozen=True)
class Attendu(Generic[T]):  # noqa: UP046
    """Ce qu'une valeur doit être : la garde qui le vérifie, et ce qu'en dit l'erreur."""

    garde: Callable[[object], TypeGuard[T]]
    texte: str


OBJET = Attendu(est_objet, "un objet")
TEXTE = Attendu(est_texte, "une chaîne non vide")
ENTIER_POSITIF = Attendu(est_entier_positif, "un entier ≥ 1")
NOMBRE = Attendu(est_nombre, "un nombre")
LISTE = Attendu(est_liste, "une liste")
LISTE_NON_VIDE = Attendu(est_liste_non_vide, "une liste non vide")
SPAN = Attendu(est_span, "[premier, dernier], deux entiers")


def champ(chemin: str, cle: str) -> str:
    """Le chemin de la clé `cle` de l'objet au chemin `chemin`."""
    return f"{chemin}.{cle}" if chemin else cle


def dans(valeur: float, bornes: Bornes) -> bool:
    """`valeur` est-elle dans `bornes`, bornes comprises ?"""
    return bornes[0] <= valeur <= bornes[1]


def icones_disponibles(dossier: Path = ICONES) -> dict[str, Path]:
    """Les icônes d'un dossier d'icônes — celui du skill par défaut : le nom sans extension de
    chaque SVG de ses jeux, et son fichier.

    Raises:
        Abandon: un nom est présent dans les deux jeux — le rendu aurait à choisir.
    """
    fichiers = [chemin for jeu in JEUX_D_ICONES for chemin in sorted((dossier / jeu).glob("*.svg"))]
    doublons = sorted(
        nom for nom, nombre in Counter(chemin.stem for chemin in fichiers).items() if nombre > 1
    )
    if doublons:
        raise Abandon(f"icône présente dans les deux jeux de {dossier} : {', '.join(doublons)}")
    return {chemin.stem: chemin for chemin in fichiers}


def lire_description(chemin: Path) -> object:
    """La description du fichier `chemin`, chaque objet lu en `Objet`.

    Raises:
        Abandon: le fichier est illisible ou pas en UTF-8, ou son JSON est mal formé.
    """
    try:
        texte = chemin.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as erreur:
        raise Abandon(f"fichier illisible — {erreur}") from erreur
    try:
        return json.loads(texte, object_pairs_hook=Objet)
    except ValueError as erreur:
        raise Abandon(f"JSON mal formé — {erreur}") from erreur


def valider(description: object, icones: Collection[str]) -> list[Erreur]:
    """Les erreurs de `description`, la description lue du JSON, dans l'ordre de lecture ; une
    liste vide si elle est valide.

    Args:
        description: la valeur rendue par `json.loads`.
        icones: les noms des icônes disponibles — `icones_disponibles()` pour le dossier du skill.
    """
    passe = Passe(icones)
    passe.racine(description)
    return passe.erreurs


class Passe:
    """Une lecture de la description : les erreurs relevées, et ce que la suite de la lecture
    doit savoir de ce qui a été lu — la grille, la présence d'un gestionnaire de secrets, les
    `id` déjà vus."""

    def __init__(self, icones: Collection[str]) -> None:
        self.icones = icones
        self.erreurs: list[Erreur] = []
        self.grille: Bornes | None = None
        self.gestionnaire = False
        # Chaque `id` lu, avec le chemin de la carte qui le porte la première.
        self.cartes: dict[str, str] = {}

    def signaler(self, chemin: str, message: str) -> None:
        """Relève une erreur sans valeur à nommer."""
        self.erreurs.append(Erreur(chemin, message))

    def refuser(self, chemin: str, motif: str, valeur: object) -> None:
        """Relève une erreur qui nomme la valeur fautive, telle que la description l'écrit."""
        self.signaler(chemin, f"{motif}, reçu {json.dumps(valeur, ensure_ascii=False)}")

    def verifier(self, valeur: object, chemin: str, attendu: Attendu[T]) -> T | None:
        """`valeur` si elle est ce qu'`attendu` demande ; sinon l'erreur relevée, et `None`."""
        if attendu.garde(valeur):
            return valeur
        self.refuser(chemin, f"attendu {attendu.texte}", valeur)
        return None

    def lire(
        self, objet: Mapping[str, object], chemin: str, cle: str, attendu: Attendu[T]
    ) -> T | None:
        """Le champ `cle` de l'objet au chemin `chemin`, vérifié ; `None` sans erreur s'il est
        absent — `ouvrir` a déjà relevé un champ requis manquant."""
        return self.verifier(objet[cle], champ(chemin, cle), attendu) if cle in objet else None

    def parmi(
        self,
        objet: Mapping[str, object],
        chemin: str,
        cle: str,
        valeurs: Collection[str],
        quoi: str,
    ) -> None:
        """Vérifie que le champ `cle`, s'il est présent, est l'une des chaînes de `valeurs`."""
        valeur = self.lire(objet, chemin, cle, TEXTE)
        if valeur is not None and valeur not in valeurs:
            self.refuser(champ(chemin, cle), f"attendu {quoi}", valeur)

    def icone(self, objet: Mapping[str, object], chemin: str) -> None:
        """Vérifie que le champ `icon`, s'il est présent, nomme une icône disponible."""
        self.parmi(objet, chemin, "icon", self.icones, "une icône du dossier d'icônes")

    def ouvrir(
        self, valeur: object, chemin: str, cles: Mapping[str, bool]
    ) -> dict[str, object] | None:
        """`valeur` si c'est un objet, ses clés en double, ses clés inconnues et ses clés
        requises manquantes relevées ; sinon l'erreur relevée, et `None`."""
        objet = self.verifier(valeur, chemin, OBJET)
        if objet is None:
            return None
        for cle in objet.doublons if isinstance(objet, Objet) else []:
            self.refuser(chemin, "clé en double", cle)
        for cle in objet:
            if cle not in cles:
                self.refuser(champ(chemin, cle), "clé inconnue", cle)
        for cle, requise in cles.items():
            if requise and cle not in objet:
                self.signaler(champ(chemin, cle), "champ requis manquant")
        return objet

    def racine(self, description: object) -> None:
        """Lit la racine, puis ses zones, puis ses liens — qui visent des cartes de toutes les
        zones."""
        racine = self.ouvrir(description, "", RACINE)
        if racine is None:
            return
        self.lire(racine, "", "intro", TEXTE)
        colonnes = self.lire(racine, "", "columns", ENTIER_POSITIF)
        self.grille = None if colonnes is None else (0, colonnes - 1)
        self.gestionnaire = "secretManager" in racine
        if self.gestionnaire:
            gestionnaire = self.ouvrir(racine["secretManager"], "secretManager", GESTIONNAIRE)
            if gestionnaire is not None:
                self.lire(gestionnaire, "secretManager", "name", TEXTE)
                self.icone(gestionnaire, "secretManager")
        self.entrees(self.lire(racine, "", "zones", LISTE_NON_VIDE) or [], "zones")
        for i, lien in enumerate(self.lire(racine, "", "links", LISTE) or []):
            self.lien(lien, f"links[{i}]")

    def entrees(self, entrees: Iterable[object], chemin: str) -> None:
        """Lit chaque entrée de la liste au chemin `chemin` : une zone, ou des zones côte à
        côte."""
        for i, entree in enumerate(entrees):
            if est_liste(entree):
                self.cote_a_cote(entree, f"{chemin}[{i}]")
            else:
                self.zone(entree, f"{chemin}[{i}]", cote_a_cote=False)

    def cote_a_cote(self, zones: object, chemin: str) -> None:
        """Lit des zones côte à côte : une liste non vide, chacune avec un span, et aucun span
        qui en chevauche un autre."""
        vus: list[tuple[str, Bornes]] = []
        for i, zone in enumerate(self.verifier(zones, chemin, LISTE_NON_VIDE) or []):
            sous = f"{chemin}[{i}]"
            span = self.zone(zone, sous, cote_a_cote=True)
            if span is None:
                continue
            for autre, bornes in vus:
                if span[0] <= bornes[1] and bornes[0] <= span[1]:
                    self.refuser(
                        f"{sous}.span", f"chevauche le span {list(bornes)} de {autre}", span
                    )
            vus.append((sous, span))

    def zone(self, valeur: object, chemin: str, cote_a_cote: bool) -> Bornes | None:
        """Lit une zone, ses rangées et ses sous-zones ; rend son span s'il est valide."""
        zone = self.ouvrir(valeur, chemin, ZONE)
        if zone is None:
            return None
        if cote_a_cote and "span" not in zone:
            self.signaler(champ(chemin, "span"), "champ requis manquant pour une zone côte à côte")
        self.lire(zone, chemin, "label", TEXTE)
        self.parmi(zone, chemin, "color", COULEURS, f"l'une des couleurs {', '.join(COULEURS)}")
        self.icone(zone, chemin)
        span = self.span(zone, chemin)
        for i, rangee in enumerate(self.lire(zone, chemin, "rows", LISTE) or []):
            sous = f"{chemin}.rows[{i}]"
            for j, carte in enumerate(self.verifier(rangee, sous, LISTE_NON_VIDE) or []):
                self.carte(carte, f"{sous}[{j}]", span)
        self.entrees(self.lire(zone, chemin, "zones", LISTE) or [], champ(chemin, "zones"))
        if all(zone.get(cle, []) == [] for cle in ("rows", "zones")):
            self.signaler(chemin, "zone sans rows ni zones non vides")
        return span

    def span(self, zone: Mapping[str, object], chemin: str) -> Bornes | None:
        """Le span de la zone au chemin `chemin`, s'il est présent et valide."""
        valeur = self.lire(zone, chemin, "span", SPAN)
        if valeur is None:
            return None
        premier, dernier = valeur
        if premier > dernier:
            motif = "span inversé"
        elif self.grille and not (dans(premier, self.grille) and dans(dernier, self.grille)):
            motif = f"span hors de la grille {list(self.grille)}"
        else:
            return premier, dernier
        self.refuser(champ(chemin, "span"), motif, valeur)
        return None

    def carte(self, valeur: object, chemin: str, span: Bornes | None) -> None:
        """Lit une carte de la zone de span `span` — `None` sans span valide."""
        carte = self.ouvrir(valeur, chemin, CARTE)
        if carte is None:
            return
        identifiant = self.lire(carte, chemin, "id", TEXTE)
        if identifiant in self.cartes:
            self.refuser(
                champ(chemin, "id"), f"id déjà porté par {self.cartes[identifiant]}", identifiant
            )
        elif identifiant is not None:
            self.cartes[identifiant] = chemin
        self.lire(carte, chemin, "name", TEXTE)
        self.icone(carte, chemin)
        self.colonne(carte, chemin, span)
        if self.lire(carte, chemin, "secret", TEXTE) is not None and not self.gestionnaire:
            self.signaler(champ(chemin, "secret"), "secret sans secretManager à la racine")

    def colonne(self, carte: Mapping[str, object], chemin: str, span: Bornes | None) -> None:
        """Vérifie la colonne d'une carte : un multiple de 0,5, dans la grille, dans `span`."""
        colonne = self.lire(carte, chemin, "column", NOMBRE)
        if colonne is None:
            return
        # NaN et l'infini, que `json.loads` accepte, ne sont pas non plus des multiples de 0,5.
        if colonne * 2 % 1 != 0:
            motif = "colonne qui n'est pas un multiple de 0,5"
        elif self.grille and not dans(colonne, self.grille):
            motif = f"colonne hors de la grille {list(self.grille)}"
        elif span and not dans(colonne, span):
            motif = f"colonne hors du span {list(span)} de sa zone"
        else:
            return
        self.refuser(champ(chemin, "column"), motif, colonne)

    def lien(self, valeur: object, chemin: str) -> None:
        """Lit un lien : deux cartes existantes et différentes, une route connue."""
        lien = self.ouvrir(valeur, chemin, LIEN)
        if lien is None:
            return
        bouts = {cle: self.lire(lien, chemin, cle, TEXTE) for cle in ("from", "to")}
        for cle, identifiant in bouts.items():
            if identifiant is not None and identifiant not in self.cartes:
                self.refuser(champ(chemin, cle), "aucune carte ne porte cet id", identifiant)
        if bouts["from"] in self.cartes and bouts["from"] == bouts["to"]:
            self.refuser(champ(chemin, "to"), "lien d'une carte vers elle-même", bouts["to"])
        self.parmi(lien, chemin, "route", ROUTES, f"l'une des routes {', '.join(ROUTES)}")


def main(argv: Sequence[str]) -> int:
    """Point d'entrée ; voir le module pour les sorties."""
    parser = argparse.ArgumentParser(
        prog="description.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("chemin", type=Path, help="le fichier JSON de la description")
    chemin: Path = parser.parse_args(argv).chemin
    try:
        description = lire_description(chemin)
        icones = icones_disponibles()
    except Abandon as motif:
        print(motif, file=sys.stderr)
        return 2
    erreurs = valider(description, icones)
    for erreur in erreurs:
        print(erreur)
    if erreurs:
        return 1
    print("valide")
    return 0


if __name__ == "__main__":
    # Sur un poste dont la page de code est cp1252, Python écrit un tube dans cet encodage : les
    # chemins et les messages, accentués, arriveraient illisibles à la session
    # (`pipeline.config.md`, « Qualité »).
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
