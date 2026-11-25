"""Tests de la description d'une miniature de projet
(`.claude/skills/miniature-projet/scripts/miniature.py`) : sa validation, sa palette, ses
compositions, ses propositions et sa CLI.

Le validateur reçoit les icônes disponibles en paramètre : les cas s'éprouvent sur un jeu témoin
écrit ici ; seule la CLI lit le dossier d'icônes réel de `schema-architecture`. Les images du
premier plan se lisent depuis le répertoire courant : chaque test qui en lit une s'y place, dans
un projet témoin sous `tmp_path` (`projet_temoin`), et rien ne s'écrit dans le dépôt. Les cas
s'écrivent en littéraux, jamais dérivés des constantes du script (`cycle-pr/references/tests.md`,
« Le rouge se constate, il ne se suppose pas »).
"""

import copy
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from conftest import load_script, run_in_pipe

miniature = load_script("miniature-projet", "miniature")

# Les icônes disponibles des cas : celles des témoins, rien d'autre — toutes aussi présentes
# dans le dossier réel du skill, que lit la CLI.
ICONES_TEMOINS = frozenset({"globe", "vault", "cable", "docker", "archive"})
# Le début d'un PNG — sa signature (PNG, 3e édition, § 5.2) — et d'un JPEG — le marqueur SOI
# puis l'octet qui ouvre le marqueur suivant (ITU-T T.81, annexe B) —, suivis d'octets
# quelconques.
PNG = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 0))
JPEG = bytes((0xFF, 0xD8, 0xFF, 0xE0, 0, 0, 0, 0))

CHANTIER: dict[str, Any] = {
    "gabarit": "chantier",
    "icones": ["globe", "vault", "cable", "docker"],
    "teinte": "sauge",
    "composition": "centre",
}
SCENE: dict[str, Any] = {
    "gabarit": "mise-en-scene",
    "premierPlan": {"type": "capture", "image": "captures/accueil.png"},
    "teinte": "prune",
    "composition": "grand-disque",
}


def projet_temoin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Se place à la racine d'un projet témoin : un PNG, un JPEG, un PNG sans extension, un texte
    à l'extension d'un PNG et un dossier, sous `captures/`."""
    monkeypatch.chdir(tmp_path)
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / "accueil.png").write_bytes(PNG)
    (captures / "mobile.jpg").write_bytes(JPEG)
    (captures / "schema").write_bytes(PNG)
    (captures / "notes.png").write_bytes(b"pas une image")
    (captures / "dossier.png").mkdir()


# La valeur d'un cas qui retire la clé au lieu de la remplacer.
RETIREE = object()


def modifiee(base: dict[str, Any], chemin: str, valeur: object) -> object:
    """`base`, la valeur au bout de `chemin` — des clés séparées par des points — remplacée par
    `valeur`, retirée sous `RETIREE` ; `valeur` elle-même au chemin vide, la racine."""
    if not chemin:
        return valeur
    racine = copy.deepcopy(base)
    *parents, derniere = chemin.split(".")
    noeud = racine
    for cle in parents:
        noeud = noeud[cle]
    if valeur is RETIREE:
        del noeud[derniere]
    else:
        noeud[derniere] = valeur
    return racine


class Cas(NamedTuple):
    """Une forme d'erreur : la valeur posée au chemin `pose` de `base`, ce que le message de
    l'erreur rendue nomme — `None` quand il n'y a rien à nommer —, et le chemin qu'elle porte —
    `pose` s'il est omis."""

    pose: str
    valeur: object
    fragment: str | None
    chemin: str | None = None
    base: dict[str, Any] = CHANTIER


QUATRE_ICONES = ["globe", "vault", "cable", "docker"]

FORMES: dict[str, dict[str, Cas]] = {
    "champ requis manquant": {
        "gabarit-manquant": Cas("gabarit", RETIREE, None),
        "icones-manquant": Cas("icones", RETIREE, None),
        "premier-plan-manquant": Cas("premierPlan", RETIREE, None, base=SCENE),
        "type-manquant": Cas("premierPlan.type", RETIREE, None, base=SCENE),
        "image-manquant": Cas("premierPlan.image", RETIREE, None, base=SCENE),
    },
    "choix incomplet": {
        "teinte-sans-composition": Cas("composition", RETIREE, "teinte"),
        "composition-sans-teinte": Cas("teinte", RETIREE, "composition"),
    },
    "champ d'un autre type": {
        "racine-liste": Cas("", [], "[]"),
        "gabarit-nombre": Cas("gabarit", 7, "7"),
        "icones-chaine": Cas("icones", "globe", '"globe"'),
        "icone-nombre": Cas("icones", ["globe", "vault", "cable", 7], "7", "icones[3]"),
        "premier-plan-chaine": Cas("premierPlan", "x.png", '"x.png"', base=SCENE),
        "type-nombre": Cas("premierPlan.type", 7, "7", base=SCENE),
        "image-nombre": Cas("premierPlan.image", 7, "7", base=SCENE),
        "teinte-nombre": Cas("teinte", 7, "7"),
        "composition-nombre": Cas("composition", 7, "7"),
    },
    "valeur vide": {
        "image-vide": Cas("premierPlan.image", "", '""', base=SCENE),
    },
    "valeur hors de son ensemble": {
        "gabarit-inconnu": Cas("gabarit", "affiche", '"affiche"'),
        "type-inconnu": Cas("premierPlan.type", "video", '"video"', base=SCENE),
        "teinte-hors-palette": Cas("teinte", "fuchsia", '"fuchsia"'),
        "composition-inconnue": Cas("composition", "spirale", '"spirale"'),
        "composition-d-un-autre-gabarit": Cas("composition", "grand-disque", '"grand-disque"'),
    },
    "icônes": {
        "trois-icones": Cas("icones", ["globe", "vault", "cable"], '["globe", "vault", "cable"]'),
        "cinq-icones": Cas("icones", [*QUATRE_ICONES, "archive"], '"archive"]'),
        "icone-absente": Cas("icones", ["globe", "vault", "cable", "x"], '"x"', "icones[3]"),
        "icone-repetee": Cas(
            "icones", ["globe", "vault", "globe", "docker"], "icones[0]", "icones[2]"
        ),
    },
    "image illisible ou d'un autre format": {
        "image-absente": Cas("premierPlan.image", "captures/x.png", '"captures/x.png"', base=SCENE),
        "image-dossier": Cas(
            "premierPlan.image", "captures/dossier.png", '"captures/dossier.png"', base=SCENE
        ),
        "image-ni-png-ni-jpeg": Cas(
            "premierPlan.image", "captures/notes.png", '"captures/notes.png"', base=SCENE
        ),
        # Un nom de fichier que `open` refuse avant tout accès au disque : `ValueError`, pas
        # `OSError`.
        "image-caractere-nul": Cas(
            "premierPlan.image", "captures/accueil.png" + chr(0), "captures/accueil.png", base=SCENE
        ),
    },
    # Le message nomme la borne, pas l'absence : aucun des deux fichiers n'existe.
    "image hors du dépôt": {
        "image-chemin-absolu": Cas(
            "premierPlan.image",
            "/captures/accueil.png",
            'reste dans le dépôt, reçu "/captures/accueil.png"',
            base=SCENE,
        ),
        "image-hors-de-la-racine": Cas(
            "premierPlan.image",
            "../captures/accueil.png",
            'reste dans le dépôt, reçu "../captures/accueil.png"',
            base=SCENE,
        ),
    },
    "clé inconnue": {
        "racine-cle-inconnue": Cas("titre", "x", '"titre"'),
        "cle-de-mise-en-scene-dans-chantier": Cas(
            "premierPlan", SCENE["premierPlan"], '"premierPlan"'
        ),
        "cle-de-chantier-dans-mise-en-scene": Cas("icones", QUATRE_ICONES, '"icones"', base=SCENE),
        "premier-plan-cle-inconnue": Cas("premierPlan.cadre", "noir", '"cadre"', base=SCENE),
    },
}
CAS = {nom: cas for groupe in FORMES.values() for nom, cas in groupe.items()}


@pytest.mark.parametrize("cas", CAS.values(), ids=CAS.keys())
def test_une_forme_d_erreur_rend_une_erreur_au_chemin_du_champ_fautif(
    cas: Cas, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Dénombrement des formes, écrit avant le premier correctif** (#290, bloc 2, 2026-11-25).

    Population : la forme verrouillée de la description (docstring du module) — 2 objets (racine,
    `premierPlan`), 7 champs dont 5 requis selon le gabarit (`gabarit`, `icones` en « chantier »,
    `premierPlan` en « mise en scène », `type`, `image`), 1 liste d'icônes, et les contraintes
    qui lient ses champs. **36 formes**, une par cas de `FORMES`, et une 37e, la clé en double,
    éprouvée par la CLI (`test_la_cli_releve_une_cle_en_double_que_json_loads_ecraserait`) :

    - champ requis manquant : 5, un par champ requis ;
    - choix incomplet : 2, `teinte` sans `composition` et l'inverse ;
    - champ d'un autre type : 9 — un par champ (7), un nom d'icône, et la racine ;
    - valeur vide : 1, l'`image`, seule chaîne libre ;
    - valeur hors de son ensemble : 5 — `gabarit`, `type`, `teinte`, `composition` inconnue ou
      d'un autre gabarit ;
    - icônes : 4 — 3 ou 5 noms, un nom absent du dossier, un nom répété ;
    - image illisible ou d'un autre format : 4 — absente, dossier, ni PNG ni JPEG à l'extension
      d'un PNG, caractère nul dans le chemin ;
    - image hors du dépôt : 2 — un chemin absolu, un chemin qui sort de la racine par `..` ;
    - clé inconnue : 4 — à la racine, d'un gabarit dans l'autre (2), dans `premierPlan`.

    Chaque cas rend **une** erreur, au chemin exact, dont le message nomme la valeur fautive.
    """
    projet_temoin(tmp_path, monkeypatch)

    erreurs = miniature.valider(modifiee(cas.base, cas.pose, cas.valeur), ICONES_TEMOINS)

    assert [erreur.chemin for erreur in erreurs] == [cas.chemin or cas.pose]
    assert cas.fragment is None or cas.fragment in erreurs[0].message


def test_les_cas_d_erreur_comptent_les_formes_de_leur_docstring() -> None:
    """Le dénombrement de la docstring ci-dessus, recompté à chaque exécution
    (`.claude/rules/cleanup-verbatim.md`, passe « affirmations ») : un nom de cas répété d'un
    groupe à l'autre en ôterait un de `CAS`."""
    assert {groupe: len(cas) for groupe, cas in FORMES.items()} == {
        "champ requis manquant": 5,
        "choix incomplet": 2,
        "champ d'un autre type": 9,
        "valeur vide": 1,
        "valeur hors de son ensemble": 5,
        "icônes": 4,
        "image illisible ou d'un autre format": 4,
        "image hors du dépôt": 2,
        "clé inconnue": 4,
    }
    assert len(CAS) == 36


def test_les_tables_de_la_forme_comptent_les_champs_de_la_docstring() -> None:
    """« 7 champs dont 5 requis selon le gabarit » (docstring du test paramétré), recompté sur
    les tables du script — les champs propres à un gabarit, tous requis par lui —, et un cas
    « champ requis manquant » par champ requis : un champ requis ajouté sans son cas rougit ici."""
    tables = {**miniature.COMMUNES, **miniature.PREMIER_PLAN}
    propres = [cle for champs in miniature.PROPRES.values() for cle in champs]

    assert (len(tables) + len(propres), sum(tables.values()) + len(propres)) == (7, 5)
    assert len(FORMES["champ requis manquant"]) == 5


PASSES: dict[str, tuple[dict[str, Any], list[str]]] = {
    "chantier": (
        {"gabarit": "chantier", "icones": ["globe", "x", "vault"], "teinte": "fuchsia", "y": 1},
        ["composition", "icones", "icones[1]", "teinte", "y"],
    ),
    # Les deux champs de `premierPlan` : un type fautif n'arrête pas la lecture de l'image.
    "mise-en-scene": (
        {**SCENE, "premierPlan": {"type": "video", "image": "captures/x.png"}},
        ["premierPlan.image", "premierPlan.type"],
    ),
    # Un gabarit inconnu n'arrête pas la lecture des champs de l'un ou de l'autre, ni celle de
    # la composition, qui n'a alors qu'à être une chaîne non vide.
    "gabarit-inconnu": (
        {"gabarit": "affiche", "icones": ["globe", "x"], "teinte": "sauge", "composition": 7},
        ["composition", "gabarit", "icones", "icones[1]"],
    ),
}


@pytest.mark.parametrize(("description", "chemins"), PASSES.values(), ids=PASSES.keys())
def test_une_passe_rend_toutes_les_erreurs(
    description: dict[str, Any],
    chemins: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une erreur n'arrête ni la lecture de ses frères ni celle des autres champs."""
    projet_temoin(tmp_path, monkeypatch)

    erreurs = miniature.valider(description, ICONES_TEMOINS)

    assert sorted(erreur.chemin for erreur in erreurs) == chemins


def premier_plan(type_: str, image: str) -> dict[str, Any]:
    """`SCENE` sans choix, son premier plan remplacé."""
    return {"gabarit": "mise-en-scene", "premierPlan": {"type": type_, "image": image}}


VALIDES: dict[str, dict[str, Any]] = {
    "chantier-choisi": CHANTIER,
    "chantier-sans-choix": {"gabarit": "chantier", "icones": QUATRE_ICONES},
    "mise-en-scene-choisie": SCENE,
    "telephone-jpeg": premier_plan("telephone", "captures/mobile.jpg"),
    "capture-png": premier_plan("capture", "captures/accueil.png"),
    # Reconnu à sa signature, pas à son extension.
    "schema-png-sans-extension": premier_plan("schema", "captures/schema"),
    # Un `..` qui ne sort pas de la racine.
    "capture-par-un-detour-dans-le-depot": premier_plan(
        "capture", "captures/../captures/accueil.png"
    ),
}


@pytest.mark.parametrize("valide", VALIDES.values(), ids=VALIDES.keys())
def test_une_description_de_chaque_gabarit_et_de_chaque_premier_plan_est_valide(
    valide: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chaque gabarit, avec ou sans le choix, et chaque type de premier plan, PNG comme JPEG."""
    projet_temoin(tmp_path, monkeypatch)

    assert miniature.valider(valide, ICONES_TEMOINS) == []


def test_une_image_du_depot_nommee_par_son_chemin_absolu_est_refusee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'image existe et est dans le dépôt, mais la description, versionnée, ne nomme ses
    images que depuis la racine du projet."""
    projet_temoin(tmp_path, monkeypatch)
    absolue = str(tmp_path / "captures" / "accueil.png")

    erreurs = miniature.valider(premier_plan("capture", absolue), ICONES_TEMOINS)

    assert [str(erreur) for erreur in erreurs] == [
        (
            "premierPlan.image : attendu un chemin relatif qui reste dans le dépôt, "
            f"reçu {json.dumps(absolue)}"
        )
    ]


# Les papiers du cadre polaroid, clair et sombre (spec UX, jeton `--paper`).
PAPIERS = {"clair": "#FBF8F2", "sombre": "#2B2724"}
TEINTES = ("terracotta", "sauge", "ardoise", "prune", "ocre", "sarcelle")


def test_la_palette_porte_ses_six_teintes_dans_l_ordre() -> None:
    """L'ordre compte : les propositions prennent les premières teintes par défaut."""
    assert list(miniature.PALETTE) == list(TEINTES)


@pytest.mark.parametrize("teinte", TEINTES)
def test_chaque_teinte_porte_ses_trois_couleurs_en_hexadecimal(teinte: str) -> None:
    """Le fond, le cône de « chantier » et le disque de « mise en scène », `#RRGGBB`."""
    couleurs = miniature.PALETTE[teinte]

    assert sorted(couleurs) == ["cone", "disque", "fond"]
    assert all(re.fullmatch("#[0-9A-F]{6}", couleur) for couleur in couleurs.values())


@pytest.mark.parametrize("papier", PAPIERS.values(), ids=PAPIERS.keys())
@pytest.mark.parametrize("teinte", TEINTES)
def test_le_fond_de_chaque_teinte_contraste_a_3_pour_1_au_moins_avec_le_papier(
    teinte: str, papier: str
) -> None:
    """WCAG 2.2, critère 1.4.11 (contraste non textuel) : la photo contre son cadre polaroid,
    dans les deux modes (#290, décision 3)."""
    assert miniature.contraste(miniature.PALETTE[teinte]["fond"], papier) >= 3


@pytest.mark.parametrize("teinte", TEINTES)
def test_le_cone_de_chaque_teinte_est_plus_clair_que_son_fond(teinte: str) -> None:
    """#290, décision 4 (c) : le cône, « dans un ton plus clair que le fond »."""
    couleurs = miniature.PALETTE[teinte]

    assert miniature.luminance(couleurs["cone"]) > miniature.luminance(couleurs["fond"])


@pytest.mark.parametrize("teinte", TEINTES)
def test_le_cone_et_le_disque_de_chaque_teinte_melent_son_fond_de_blanc(teinte: str) -> None:
    """Le commentaire de `PALETTE`, recompté : le cône est le fond mêlé à 25 % de blanc, le
    disque à 14 % — `round(c + (255 - c) * part)` sur chaque canal."""
    couleurs = miniature.PALETTE[teinte]

    def melee(part: float) -> str:
        canaux = bytes.fromhex(couleurs["fond"][1:])
        return "#" + "".join(f"{round(c + (255 - c) * part):02X}" for c in canaux)

    assert (couleurs["cone"], couleurs["disque"]) == (melee(0.25), melee(0.14))


CONTRASTES = {
    "noir-sur-blanc": ("#000000", "#FFFFFF", 21),
    "blanc-sur-noir": ("#FFFFFF", "#000000", 21),
    # Le gris le plus clair qui tient 4,5:1 sur le blanc : 4,54:1.
    "gris-767676-sur-blanc": ("#767676", "#FFFFFF", 4.54),
    "papier-sur-lui-meme": ("#FBF8F2", "#FBF8F2", 1),
}


@pytest.mark.parametrize(("a", "b", "attendu"), CONTRASTES.values(), ids=CONTRASTES.keys())
def test_le_contraste_suit_la_definition_wcag(a: str, b: str, attendu: float) -> None:
    """WCAG 2.2, définitions « contrast ratio » et « relative luminance » : de 1 à 21, dans un
    sens comme dans l'autre."""
    assert miniature.contraste(a, b) == pytest.approx(attendu, abs=0.005)


def test_chaque_gabarit_porte_quatre_compositions_et_les_parametres_que_le_rendu_lit() -> None:
    """« chantier » : le centre et la taille du cône ; « mise en scène » : le centre et le
    diamètre du disque, et la taille du premier plan, centré sur lui."""
    cone = ["taille", "x", "y"]
    disque = ["diametre", "premierPlan", "x", "y"]

    assert {
        gabarit: {nom: sorted(parametres) for nom, parametres in compositions.items()}
        for gabarit, compositions in miniature.COMPOSITIONS.items()
    } == {
        "chantier": {"centre": cone, "debordant": cone, "bas-droite": cone, "bas-gauche": cone},
        "mise-en-scene": {
            "centre": disque,
            "grand-disque": disque,
            "coin-haut-droit": disque,
            "coin-bas-gauche": disque,
        },
    }


@pytest.mark.parametrize("nom", ["centre", "grand-disque", "coin-haut-droit", "coin-bas-gauche"])
def test_le_premier_plan_de_chaque_composition_tient_dans_l_image(nom: str) -> None:
    """Le carré du premier plan, centré sur le disque, ne sort pas de l'image : le disque peut
    déborder, pas le téléphone ni la capture."""
    composition = miniature.COMPOSITIONS["mise-en-scene"][nom]
    demi = composition["premierPlan"] / 2

    assert 0 <= composition["x"] - demi and composition["x"] + demi <= 1
    assert 0 <= composition["y"] - demi and composition["y"] + demi <= 1


def test_un_chantier_propose_quatre_teintes_et_quatre_compositions_dans_l_ordre() -> None:
    """Quatre teintes distinctes, quatre compositions distinctes, dans l'ordre."""
    assert miniature.propositions(CHANTIER) == [
        ("terracotta", "centre"),
        ("sauge", "debordant"),
        ("ardoise", "bas-droite"),
        ("prune", "bas-gauche"),
    ]


def test_les_propositions_d_une_mise_en_scene_prennent_les_compositions_de_son_gabarit() -> None:
    assert miniature.propositions(SCENE) == [
        ("terracotta", "centre"),
        ("sauge", "grand-disque"),
        ("ardoise", "coin-haut-droit"),
        ("prune", "coin-bas-gauche"),
    ]


def test_les_teintes_nommees_remplacent_celles_par_defaut_dans_leur_ordre() -> None:
    assert miniature.propositions(SCENE, ["ocre", "sarcelle", "terracotta", "sauge"]) == [
        ("ocre", "centre"),
        ("sarcelle", "grand-disque"),
        ("terracotta", "coin-haut-droit"),
        ("sauge", "coin-bas-gauche"),
    ]


# Le motif d'un refus de teintes.
TEINTES_REFUSEES = "attendu 4 teintes distinctes de la palette"
REFUSEES: dict[str, tuple[dict[str, Any], list[str] | None, str]] = {
    "trois-teintes": (CHANTIER, ["ocre", "sauge", "prune"], TEINTES_REFUSEES),
    "cinq-teintes": (CHANTIER, ["ocre", "sauge", "prune", "ardoise", "sarcelle"], TEINTES_REFUSEES),
    "teinte-repetee": (CHANTIER, ["ocre", "ocre", "sauge", "prune"], TEINTES_REFUSEES),
    # Quatre noms distincts de la palette, mais cinq teintes.
    "cinq-dont-une-repetee": (
        CHANTIER,
        ["ocre", "ocre", "sauge", "prune", "ardoise"],
        TEINTES_REFUSEES,
    ),
    "teinte-hors-palette": (CHANTIER, ["ocre", "fuchsia", "sauge", "prune"], TEINTES_REFUSEES),
    "gabarit-inconnu": ({"gabarit": "affiche"}, None, "description sans gabarit connu"),
}


@pytest.mark.parametrize(
    ("description", "teintes", "motif"), REFUSEES.values(), ids=REFUSEES.keys()
)
def test_des_propositions_impossibles_sont_refusees_avec_leur_motif(
    description: dict[str, Any], teintes: list[str] | None, motif: str
) -> None:
    """Les teintes nommées sont 4 noms distincts de la palette, et le gabarit est connu."""
    with pytest.raises(ValueError, match=motif):
        miniature.propositions(description, teintes)


def test_le_choix_de_la_teinte_de_2_et_de_la_composition_de_3_s_ecrit_dans_la_description() -> None:
    """#290, décision 5 : la description garde teinte et composition séparément."""
    sans_choix = {"gabarit": "chantier", "icones": QUATRE_ICONES}
    proposees = miniature.propositions(sans_choix)

    assert miniature.choisir(sans_choix, proposees[1][0], proposees[2][1]) == {
        "gabarit": "chantier",
        "icones": ["globe", "vault", "cable", "docker"],
        "teinte": "sauge",
        "composition": "bas-droite",
    }


def test_le_choix_remplace_celui_de_la_description_sans_la_modifier() -> None:
    """Une fonction pure : la description reçue reste telle quelle."""
    avant = copy.deepcopy(CHANTIER)

    choisie = miniature.choisir(CHANTIER, "ocre", "bas-gauche")

    assert (choisie["teinte"], choisie["composition"], CHANTIER) == ("ocre", "bas-gauche", avant)


def ecrite(chemin: Path, description: object) -> Path:
    """`chemin`, où `description` vient d'être écrite en JSON, ses dossiers créés."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(description, ensure_ascii=False), encoding="utf-8")
    return chemin


def test_la_cli_valide_la_description_qu_on_lui_nomme(tmp_path: Path) -> None:
    """Sortie 0 et la seule ligne « valide », contre le dossier d'icônes réel."""
    done = run_in_pipe("miniature-projet", "miniature", str(ecrite(tmp_path / "m.json", CHANTIER)))

    assert (done.returncode, done.stdout.decode("utf-8").splitlines()) == (0, ["valide"])


def test_la_cli_lit_par_defaut_la_description_du_projet_courant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lancée sans argument à la racine du projet : `docs/miniature/miniature.json`, l'image du
    premier plan lue relativement à cette racine."""
    projet_temoin(tmp_path, monkeypatch)
    ecrite(tmp_path / "docs" / "miniature" / "miniature.json", SCENE)

    done = run_in_pipe("miniature-projet", "miniature")

    assert (done.returncode, done.stdout.decode("utf-8").splitlines()) == (0, ["valide"])


def test_la_cli_rend_une_ligne_par_erreur_en_utf_8_dans_un_tube(tmp_path: Path) -> None:
    """Sortie 1, une ligne `<chemin> : <message>` par erreur, accents lisibles."""
    fautive = modifiee(CHANTIER, "icones", ["globe", "vault", "cable", "fantome"])

    done = run_in_pipe("miniature-projet", "miniature", str(ecrite(tmp_path / "m.json", fautive)))

    assert (done.returncode, done.stdout.decode("utf-8").splitlines()) == (
        1,
        [f"icones[3] : attendu une icône du dossier d'icônes, reçu {json.dumps('fantome')}"],
    )


def test_la_cli_releve_une_cle_en_double_que_json_loads_ecraserait(tmp_path: Path) -> None:
    """Le fichier se lit avec le hook du schéma, qui garde les clés répétées."""
    chemin = tmp_path / "m.json"
    chemin.write_text(json.dumps(CHANTIER).replace("{", '{"teinte": "ocre", ', 1), encoding="utf-8")

    done = run_in_pipe("miniature-projet", "miniature", str(chemin))

    assert (done.returncode, done.stdout.decode("utf-8").splitlines()) == (
        1,
        [f"(racine) : clé en double, reçu {json.dumps('teinte')}"],
    )


@pytest.mark.parametrize(
    ("contenu", "motif"), [(None, "fichier illisible — "), ("{", "JSON mal formé — ")]
)
def test_la_cli_sort_en_2_sur_une_description_illisible_avec_son_motif_en_utf_8(
    tmp_path: Path, contenu: str | None, motif: str
) -> None:
    """Rien sur la sortie standard ; le motif en une ligne sur la sortie d'erreur."""
    chemin = tmp_path / "m.json"
    if contenu is not None:
        chemin.write_text(contenu, encoding="utf-8")

    done = run_in_pipe("miniature-projet", "miniature", str(chemin))
    lignes = done.stderr.decode("utf-8").splitlines()

    assert (done.returncode, done.stdout, len(lignes), lignes[0].startswith(motif)) == (
        2,
        b"",
        1,
        True,
    )


def test_la_cli_sort_en_2_sur_un_appel_mal_forme(tmp_path: Path) -> None:
    """Deux descriptions : argparse refuse l'appel, sans rien lire."""
    done = run_in_pipe("miniature-projet", "miniature", str(tmp_path / "a"), str(tmp_path / "b"))

    assert done.returncode == 2
