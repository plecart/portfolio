"""Tests de l'export de la miniature d'un projet
(`.claude/skills/miniature-projet/scripts/exporter.py`) et de la page qu'il assemble
(`rendu/miniature.html`).

La capture passe par la frontière de l'export du schéma, `subprocess.run`, que ces tests
remplacent par son témoin (`Capture`, `test_schema_architecture_export.py`) : un navigateur
n'entre pas dans la suite. Chaque test se place à la racine du projet témoin des tests de la
description (`projet`, `test_miniature_projet.py`), où vivent la description et les images du
premier plan — leur début seul, que le rendu ne décode pas ici. Les cas s'écrivent en littéraux,
jamais tirés des constantes des scripts (`cycle-pr/references/tests.md`, « Le rouge se constate,
il ne se suppose pas »).
"""

import base64
import json
import re
from pathlib import Path
from typing import Any

import pytest
from conftest import load_script, run_in_pipe
from test_miniature_projet import FOND, JPEG, PNG, premier_plan, projet_temoin
from test_schema_architecture_export import (
    CARRE,
    ERREUR_ATTENTE,
    PLANCHE,
    Capture,
    fenetre,
    png_temoin,
    remplacer,
)

exporter = load_script("miniature-projet", "exporter")
description = load_script("schema-architecture", "description")

# Deux logos, puis une icône neutre, tous du dossier d'icônes de `schema-architecture`.
CHANTIER: dict[str, Any] = {"gabarit": "chantier", "icones": ["django", "docker", "globe"]}

DESCRIPTIONS = {
    "chantier": CHANTIER,
    "telephone": premier_plan("telephone", "captures/mobile.jpg"),
    "capture": premier_plan("capture"),
    "schema": premier_plan("schema"),
}
DESCRIPTION = Path("docs/miniature/miniature.json")
DOSSIER = Path("docs/miniature/propositions")
IMAGE = Path("docs/miniature/miniature.png")

# L'accent de chaque teinte de la palette, et les quatre compositions de chaque gabarit, dans
# l'ordre des propositions : la première calquée sur la couverture en ligne du gabarit.
ACCENTS = {
    "terracotta": "#EBDBCE",
    "sauge": "#D5E2CF",
    "ardoise": "#D7DFE9",
    "prune": "#E8D9E6",
    "ocre": "#E9DDBE",
    "sarcelle": "#CCE2E2",
}
COMPOSITIONS: dict[str, dict[str, dict[str, Any]]] = {
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


def projet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decrite: dict[str, Any]) -> None:
    """Se place à la racine du projet témoin (`projet_temoin`) — ses images, dont
    `captures/accueil.png` et `captures/mobile.jpg` —, et y écrit la description `decrite` à son
    chemin par défaut."""
    projet_temoin(tmp_path, monkeypatch)
    DESCRIPTION.parent.mkdir(parents=True)
    DESCRIPTION.write_text(json.dumps(decrite), encoding="utf-8")


def page(decrite: dict[str, Any], teinte: str, composition: str) -> str:
    """La page que l'export assemble pour `decrite`, dans cette teinte et cette composition."""
    return exporter.assembler(decrite, description.icones_disponibles(), teinte, composition)


def injectee(rendue: str) -> dict[str, Any]:
    """La miniature que dessine la page `rendue` : l'objet que l'export injecte à son marqueur,
    seul sur sa ligne — la page capturée se relit avec les fins de ligne du poste."""
    prefixe = "const MINIATURE = "
    [ligne] = [ligne for ligne in rendue.splitlines() if ligne.startswith(prefixe)]
    return json.loads(ligne.removeprefix(prefixe).removesuffix(";"))


def en_data(image: bytes, type_mime: str) -> str:
    """`image` en URL `data:`."""
    return f"data:{type_mime};base64,{base64.b64encode(image).decode('ascii')}"


@pytest.mark.parametrize("decrite", DESCRIPTIONS.values(), ids=DESCRIPTIONS.keys())
def test_la_page_assemblee_ne_charge_rien_hors_d_elle(
    decrite: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chaque gabarit et chaque premier plan : aucune URL hors de l'espace de noms XML de SVG, et
    ni `url()`, ni `src`, ni `href` qui vise autre chose qu'une URL `data:` ou un fragment de la
    page. Un marqueur sans ressource, lui, arrête `remplir`."""
    projet(tmp_path, monkeypatch, decrite)

    rendue = page(decrite, "sauge", "modele")

    assert set(re.findall("https?://[-./a-zA-Z0-9]+", rendue)) <= {"http://www.w3.org/2000/svg"}
    assert re.findall("url[(](?!#)|(?:src|href)=.(?!data:|#)", rendue) == []


def test_la_page_assemblee_pose_le_marqueur_qu_attend_la_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le marqueur de fin de rendu, que l'export injecte comme dans la page du schéma."""
    projet(tmp_path, monkeypatch, CHANTIER)

    rendue = page(CHANTIER, "sauge", "modele")

    assert rendue.count("""document.body.setAttribute("data-rendu-pret", '')""") == 1


# Une description de chaque gabarit, la teinte et la composition qu'elle reçoit.
CHOIX = {
    "chantier": (CHANTIER, "sauge", "cone-a-droite"),
    "mise-en-scene": (premier_plan("capture"), "prune", "plan-a-gauche"),
}


@pytest.mark.parametrize(("decrite", "teinte", "composition"), CHOIX.values(), ids=CHOIX.keys())
def test_la_page_porte_les_couleurs_de_la_teinte_et_les_parametres_de_la_composition(
    decrite: dict[str, Any],
    teinte: str,
    composition: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le fond fixe, l'accent de la teinte et les paramètres de la composition : le rendu reçoit
    des couleurs et des fractions du côté, jamais un nom de teinte ni de composition."""
    projet(tmp_path, monkeypatch, decrite)

    rendue = page(decrite, teinte, composition)

    miniature = injectee(rendue)
    assert (miniature["couleurs"], miniature["composition"]) == (
        {"fond": FOND, "accent": ACCENTS[teinte]},
        COMPOSITIONS[decrite["gabarit"]][composition],
    )
    assert [nom for nom in (teinte, composition) if nom in rendue] == []


def test_la_page_d_un_chantier_porte_ses_trois_icones_dans_l_ordre_et_le_cone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le SVG de chaque icône, dans l'ordre de la description — chaque logo à sa couleur
    (`couleurs.json`), l'icône neutre telle quelle —, et celui du cône de Lucide."""
    projet(tmp_path, monkeypatch, CHANTIER)

    miniature = injectee(page(CHANTIER, "sauge", "modele"))

    premieres = [
        re.search('fill="#[0-9A-F]{6}"|lucide lucide-[a-z-]+', svg) for svg in miniature["icones"]
    ]
    assert [trouvee[0] if trouvee else None for trouvee in premieres] == [
        'fill="#092E20"',
        'fill="#2496ED"',
        "lucide lucide-globe",
    ]
    assert "lucide lucide-traffic-cone" in miniature["cone"]


PREMIERS_PLANS = {
    "telephone-jpeg": ("telephone", "captures/mobile.jpg", en_data(JPEG, "image/jpeg")),
    "capture-png": ("capture", "captures/accueil.png", en_data(PNG, "image/png")),
    "schema-png": ("schema", "captures/accueil.png", en_data(PNG, "image/png")),
}


@pytest.mark.parametrize(
    ("type_", "image", "attendue"), PREMIERS_PLANS.values(), ids=PREMIERS_PLANS.keys()
)
def test_la_page_d_une_mise_en_scene_porte_son_premier_plan_en_ligne(
    type_: str, image: str, attendue: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le type du premier plan, et son image en URL `data:`, du type reconnu à ses octets."""
    decrite = premier_plan(type_, image)
    projet(tmp_path, monkeypatch, decrite)

    miniature = injectee(page(decrite, "sauge", "modele"))

    assert miniature["premierPlan"] == {"type": type_, "image": attendue}


# Une description de chaque gabarit, sans choix.
SANS_CHOIX = {"chantier": CHANTIER, "mise-en-scene": premier_plan("telephone")}


@pytest.mark.parametrize("decrite", SANS_CHOIX.values(), ids=SANS_CHOIX.keys())
def test_sans_choix_l_export_ecrit_quatre_propositions_puis_leur_planche(
    decrite: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Aux chemins par défaut : quatre propositions, la k-ième de la k-ième teinte de la palette
    et de la k-ième composition du gabarit, puis leur planche ; une ligne par fichier écrit,
    chaque capture à la taille de sa fenêtre, et aucune image choisie."""
    projet(tmp_path, monkeypatch, decrite)
    capture = Capture()
    remplacer(monkeypatch, capture)
    ecrites = [f"proposition-{numero}.png" for numero in range(1, 5)]

    rendu = exporter.main([])

    assert (rendu, capsys.readouterr().out.splitlines()) == (
        0,
        [
            *(f"{DOSSIER / nom} : 2400 × 2400" for nom in ecrites),
            f"{DOSSIER / 'planche.png'} : 4000 × 1680",
        ],
    )
    assert [fenetre(commande) for commande in capture.commandes] == ["1200,1200"] * 4 + ["2000,840"]
    teintes = ("terracotta", "sauge", "ardoise", "prune")
    assert [
        (miniature["couleurs"]["accent"], miniature["composition"])
        for miniature in map(injectee, capture.pages[:4])
    ] == [
        (ACCENTS[teinte], composition)
        for teinte, composition in zip(
            teintes, COMPOSITIONS[decrite["gabarit"]].values(), strict=True
        )
    ]
    assert {fichier.name: fichier.read_bytes() for fichier in DOSSIER.iterdir()} == {
        **dict.fromkeys(ecrites, CARRE),
        "planche.png": PLANCHE,
    }
    assert not IMAGE.exists()


# Les quatre mêmes teintes, nommées avec ou sans espace après chaque virgule.
TEINTES_NOMMEES = {
    "serrees": "prune,ocre,sarcelle,ardoise",
    "espacees": "prune, ocre, sarcelle, ardoise",
}


@pytest.mark.parametrize("nommees", TEINTES_NOMMEES.values(), ids=TEINTES_NOMMEES.keys())
def test_les_teintes_nommees_remplacent_celles_par_defaut_dans_leur_ordre(
    nommees: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--teintes` : la k-ième teinte nommée pour la k-ième proposition."""
    projet(tmp_path, monkeypatch, CHANTIER)
    capture = Capture()
    remplacer(monkeypatch, capture)

    rendu = exporter.main(["--teintes", nommees])

    assert rendu == 0
    assert [injectee(rendue)["couleurs"]["accent"] for rendue in capture.pages[:4]] == [
        ACCENTS[teinte] for teinte in ("prune", "ocre", "sarcelle", "ardoise")
    ]


def test_le_choix_de_la_teinte_de_2_et_de_la_composition_de_3_exporte_cette_seule_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """La teinte de la proposition 2 et la composition de la proposition 3, inscrites dans la
    description : une seule capture, exactement ces paramètres, l'image à son chemin par défaut
    et aucune proposition."""
    projet(tmp_path, monkeypatch, {**CHANTIER, "teinte": "sauge", "composition": "cone-a-droite"})
    capture = Capture()
    remplacer(monkeypatch, capture)

    rendu = exporter.main([])

    assert (rendu, capsys.readouterr().out.splitlines()) == (0, [f"{IMAGE} : 2400 × 2400"])
    [miniature] = map(injectee, capture.pages)
    assert (miniature["couleurs"]["accent"], miniature["composition"]) == (
        ACCENTS["sauge"],
        COMPOSITIONS["chantier"]["cone-a-droite"],
    )
    assert [fenetre(commande) for commande in capture.commandes] == ["1200,1200"]
    assert (IMAGE.read_bytes(), DOSSIER.exists()) == (CARRE, False)


def test_l_image_choisie_s_ecrit_au_chemin_nomme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--png` : l'image choisie à ce chemin, et nulle part ailleurs."""
    projet(
        tmp_path, monkeypatch, {**premier_plan("schema"), "teinte": "ocre", "composition": "modele"}
    )
    remplacer(monkeypatch, Capture())
    png = tmp_path / "ailleurs" / "miniature.png"

    rendu = exporter.main(["--png", str(png)])

    assert (rendu, png.read_bytes(), IMAGE.exists()) == (0, CARRE, False)


INVALIDES = {
    "gabarit-inconnu": (
        {**CHANTIER, "gabarit": "affiche"},
        f"gabarit : attendu l'un des gabarits chantier, mise-en-scene, reçu {json.dumps('affiche')}",
    ),
    "teinte-hors-palette": (
        {**CHANTIER, "teinte": "fuchsia", "composition": "modele"},
        (
            "teinte : attendu l'une des teintes terracotta, sauge, ardoise, prune, ocre, sarcelle, "
            'reçu "fuchsia"'
        ),
    ),
    "image-absente": (
        premier_plan("capture", "captures/absente.png"),
        'premierPlan.image : aucun fichier lisible à ce chemin, reçu "captures/absente.png"',
    ),
}


@pytest.mark.parametrize(("decrite", "ligne"), INVALIDES.values(), ids=INVALIDES.keys())
def test_une_description_invalide_sort_en_1_sans_capture_ni_image(
    decrite: dict[str, Any],
    ligne: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valider d'abord : une ligne par erreur, aucun navigateur, ni proposition ni image."""
    projet(tmp_path, monkeypatch, decrite)
    capture = Capture()
    remplacer(monkeypatch, capture)

    rendu = exporter.main([])

    assert (rendu, capsys.readouterr().out.splitlines()) == (1, [ligne])
    assert (capture.commandes, DOSSIER.exists(), IMAGE.exists()) == ([], False, False)


ECHECS = {
    "capture-en-echec": (None, 1, "Timeout 30000ms exceeded."),
    # La fenêtre sans le facteur d'échelle du descripteur.
    "autre-taille": (png_temoin(1200, 1200), 0, "capture de 1200 × 1200 px"),
}


@pytest.mark.parametrize(("png", "code", "fragment"), ECHECS.values(), ids=ECHECS.keys())
def test_une_capture_en_echec_ou_d_une_autre_taille_n_ecrit_rien(
    png: bytes | None,
    code: int,
    fragment: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sortie 1, le motif en une ligne, et rien à la destination."""
    projet(tmp_path, monkeypatch, {**CHANTIER, "teinte": "sauge", "composition": "modele"})
    remplacer(monkeypatch, Capture(png=png, code=code, erreur=ERREUR_ATTENTE))

    rendu = exporter.main([])

    lignes = capsys.readouterr().err.splitlines()
    assert (rendu, len(lignes), IMAGE.exists()) == (1, 1, False)
    assert fragment in lignes[0]


AVEC_CHOIX = {**CHANTIER, "teinte": "sauge", "composition": "modele"}
APPELS_MAL_FORMES = {
    "teintes-avec-choix": (
        AVEC_CHOIX,
        ["--teintes", "prune,ocre,sarcelle,ardoise"],
        "--teintes ne vaut que sans choix dans la description",
    ),
    "dossier-avec-choix": (
        AVEC_CHOIX,
        ["--dossier", "d"],
        "--dossier ne vaut que sans choix dans la description",
    ),
    "png-sans-choix": (
        CHANTIER,
        ["--png", "x.png"],
        "--png ne vaut qu'avec un choix dans la description",
    ),
    "trois-teintes": (
        CHANTIER,
        ["--teintes", "prune,ocre,sarcelle"],
        "attendu 4 teintes distinctes de la palette",
    ),
    "teinte-hors-palette": (
        CHANTIER,
        ["--teintes", "prune,ocre,sarcelle,fuchsia"],
        "attendu 4 teintes distinctes de la palette",
    ),
}


@pytest.mark.parametrize(
    ("decrite", "argv", "fragment"), APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys()
)
def test_un_appel_mal_forme_sort_en_2_sans_capture_ni_fichier(
    decrite: dict[str, Any],
    argv: list[str],
    fragment: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Une option hors de son mode, ou des teintes qui ne font pas quatre noms distincts de la
    palette : le motif sur la sortie d'erreur, rien de capturé ni d'écrit."""
    projet(tmp_path, monkeypatch, decrite)
    capture = Capture()
    remplacer(monkeypatch, capture)

    with pytest.raises(SystemExit) as sortie:
        exporter.main(argv)

    assert (sortie.value.code, capture.commandes) == (2, [])
    assert fragment in capsys.readouterr().err
    assert (DOSSIER.exists(), IMAGE.exists()) == (False, False)


def test_la_cli_rend_ses_erreurs_en_utf_8_dans_un_tube(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le script lancé comme la session le lit, flux de l'enfant en cp1252 (`run_in_pipe`) :
    sortie 1, la ligne d'erreur lisible en UTF-8, aucune image."""
    projet(tmp_path, monkeypatch, premier_plan("capture", "captures/absente-é.png"))

    done = run_in_pipe("miniature-projet", "exporter")

    assert done.returncode == 1
    assert done.stdout.decode("utf-8").splitlines() == [
        'premierPlan.image : aucun fichier lisible à ce chemin, reçu "captures/absente-é.png"'
    ]
    assert not DOSSIER.exists()
