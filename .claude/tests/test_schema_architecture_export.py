"""Tests de l'export du schéma d'architecture et de la planche d'aperçu de ses propositions
(`.claude/skills/schema-architecture/scripts/export.py`).

La capture passe par une frontière, `subprocess.run`, que ces tests remplacent par un témoin
(`Capture`) : il note la commande, et écrit au dernier chemin qu'elle nomme un PNG témoin construit
ici octet par octet — par défaut à la taille que demande la commande, sa fenêtre au facteur
d'échelle 2. Un navigateur n'entre pas dans la suite : l'export réel se joue sur le poste. Les cas
s'écrivent en littéraux, jamais tirés des constantes du script (`cycle-pr/references/tests.md`,
« Le rouge se constate, il ne se suppose pas »).
"""

import base64
import json
import re
import shutil
import struct
import subprocess
import zlib
from itertools import pairwise
from pathlib import Path
from typing import cast
from urllib.request import urlopen

import pytest
from conftest import REPOSITORY_ROOT, load_script, run_in_pipe

export = load_script("schema-architecture", "export")
description = load_script("schema-architecture", "description")

PACOME_DEV = REPOSITORY_ROOT / "docs" / "schema" / "architecture.json"
SKILL = REPOSITORY_ROOT / ".claude" / "skills" / "schema-architecture"
PREREQUIS = "uv run --no-project --with playwright==1.64.1 playwright install chromium"


def png_temoin(largeur: int, hauteur: int) -> bytes:
    """Le début d'un PNG de `largeur` × `hauteur` px : sa signature, puis son bloc IHDR, CRC
    compris (PNG, 3e édition, § 5.2, § 5.3 et § 11.2.1) — le script n'en lit pas plus."""
    bloc = b"IHDR" + struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0)
    signature = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))
    return signature + struct.pack(">I", len(bloc) - 4) + bloc + struct.pack(">I", zlib.crc32(bloc))


def fenetre(commande: list[str]) -> str:
    """La fenêtre que demande la commande de capture `commande`, `largeur,hauteur`."""
    return dict(pairwise(commande))["--viewport-size"]


class Capture:
    """`subprocess.run` remplacé : note chaque commande et le texte de la page qu'elle capture,
    lu à son URL pendant la capture — l'export la jette ensuite —, et rend `code` avec `erreur`
    sur la sortie d'erreur ; sur un code 0, écrit au chemin que la commande nomme en dernier
    `png`, ou sans `png` le témoin de la taille qu'elle demande, sa fenêtre au facteur
    d'échelle 2."""

    def __init__(self, png: bytes | None = None, code: int = 0, erreur: bytes = b"") -> None:
        self.png, self.code, self.erreur = png, code, erreur
        self.commandes: list[list[str]] = []
        self.pages: list[str] = []

    def __call__(self, commande: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        self.commandes.append(commande)
        with urlopen(commande[-2]) as page:
            self.pages.append(page.read().decode("utf-8"))
        if self.code == 0:
            largeur, hauteur = (2 * int(cote) for cote in fenetre(commande).split(","))
            Path(commande[-1]).write_bytes(self.png or png_temoin(largeur, hauteur))
        return subprocess.CompletedProcess(commande, self.code, b"", self.erreur)


def remplacer(monkeypatch: pytest.MonkeyPatch, capture: Capture, uv: str | None = "uv") -> None:
    """La capture remplacée par `capture`, et `uv` trouvé au chemin `uv` — introuvable sous
    `None`."""

    def trouver(_: str) -> str | None:
        return uv

    monkeypatch.setattr(subprocess, "run", capture)
    monkeypatch.setattr(shutil, "which", trouver)


def lancer(
    monkeypatch: pytest.MonkeyPatch,
    capture: Capture,
    lue: Path,
    png: Path,
    uv: str | None = "uv",
) -> int:
    """`export.main` sur la description `lue` et l'image `png`, la capture remplacée (`remplacer`)."""
    remplacer(monkeypatch, capture, uv)
    return export.main([str(lue), str(png)])


def pacome_dev_fautive(tmp_path: Path, cible: str) -> tuple[Path, int]:
    """La description de pacome.dev, un lien de plus vers la carte d'id `cible`, absente : son
    chemin, `<cible>.json`, et l'index de ce lien, que la description réelle déplace à chaque lien
    ajouté."""
    fautive = json.loads(PACOME_DEV.read_text(encoding="utf-8"))
    fautive["links"].append({"from": "api", "to": cible})
    chemin = tmp_path / f"{cible}.json"
    chemin.write_text(json.dumps(fautive, ensure_ascii=False), encoding="utf-8")
    return chemin, len(fautive["links"]) - 1


def chaines(noeud: object) -> list[str]:
    """Chaque chaîne de la valeur JSON `noeud`, à tout niveau, dans l'ordre du texte, chaque clé
    devant sa valeur."""
    if isinstance(noeud, dict):
        objet = cast(dict[str, object], noeud)
        return [chaine for cle, valeur in objet.items() for chaine in [cle, *chaines(valeur)]]
    if isinstance(noeud, list):
        return [chaine for valeur in cast(list[object], noeud) for chaine in chaines(valeur)]
    return [noeud] if isinstance(noeud, str) else []


def page_de_pacome_dev() -> str:
    """La page que l'export assemble pour la description committée."""
    lue = json.loads(PACOME_DEV.read_text(encoding="utf-8"))
    return export.assembler(lue, description.icones_disponibles())


def test_la_page_assemblee_ne_charge_rien_hors_d_elle() -> None:
    """Aucune URL hors de l'espace de noms XML de SVG, les deux polices en `data:`, rough.js en
    ligne, et chaque marqueur du gabarit remplacé."""
    page = page_de_pacome_dev()

    assert set(re.findall("https?://[-./a-zA-Z0-9]+", page)) == {"http://www.w3.org/2000/svg"}
    assert page.count('url("data:font/woff2;base64,') == 2
    assert (SKILL / "rendu" / "rough.js").read_text(encoding="utf-8") in page
    assert re.search("/[*][A-Z_]+[*]/", page) is None


def test_la_page_assemblee_echappe_chaque_chevron_de_la_description() -> None:
    """Un `</script>` ou un `<!--` dans un texte de la description ne ferme ni n'ouvre rien : la
    page n'en porte que ceux de son gabarit."""
    gabarit = (SKILL / "rendu" / "page.html").read_text(encoding="utf-8")

    page = export.assembler({"zones": [{"label": "</script><!--"}]}, {})

    assert (page.count("</script"), page.count("<!--")) == (
        gabarit.count("</script"),
        gabarit.count("<!--"),
    )


def test_la_page_assemblee_porte_la_description_et_ses_icones() -> None:
    """Chaque chaîne de la description ; chaque icône qu'elle nomme, en SVG, un logo à sa
    couleur."""
    page = page_de_pacome_dev()
    lue = json.loads(PACOME_DEV.read_text(encoding="utf-8"))
    couleurs = json.loads(
        (SKILL / "icones" / "simple-icons" / "couleurs.json").read_text(encoding="utf-8")
    )
    # Chaque valeur d'une clé `icon` : la chaîne qui la suit.
    nommees = {valeur for cle, valeur in pairwise(chaines(lue)) if cle == "icon"}

    assert [chaine for chaine in chaines(lue) if chaine not in page] == []
    assert [nom for nom in nommees if couleurs.get(nom, f"lucide lucide-{nom}") not in page] == []


# Le PNG témoin d'une proposition, et celui de la planche : leur fenêtre au facteur d'échelle 2.
CARRE = png_temoin(2400, 2400)
PLANCHE = png_temoin(4000, 1680)

TAILLES = {
    "carre-de-2400": (CARRE, 0, "architecture.png : 2400 × 2400"),
    # La fenêtre sans le facteur d'échelle du descripteur.
    "carre-de-1200": (png_temoin(1200, 1200), 1, "1200 × 1200"),
    "autre-taille": (png_temoin(2400, 1800), 1, "2400 × 1800"),
    "signature-fausse": (b"GIF89a" + CARRE[6:], 1, "pas un PNG"),
    "premier-bloc-pas-ihdr": (CARRE.replace(b"IHDR", b"IDAT"), 1, "pas un PNG"),
}


@pytest.mark.parametrize(("capturee", "code", "fragment"), TAILLES.values(), ids=TAILLES.keys())
def test_la_taille_se_relit_dans_l_en_tete_du_png(
    capturee: bytes,
    code: int,
    fragment: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """2400 × 2400 : l'image est écrite, sortie 0. Une autre taille — la fenêtre de 1200 sans son
    facteur d'échelle comprise — ou un fichier qui n'est pas un PNG : sortie 1, le motif nomme ce
    qui a été lu, et rien n'est écrit."""
    png = tmp_path / "docs" / "architecture.png"

    rendu = lancer(monkeypatch, Capture(png=capturee), PACOME_DEV, png)

    sortie = capsys.readouterr()
    assert rendu == code
    assert fragment in (sortie.err if code else sortie.out)
    assert (png.read_bytes() if png.exists() else None) == (None if code else capturee)


def test_une_description_invalide_sort_en_1_sans_capture_ni_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valider d'abord : les erreurs sortent, aucun navigateur ne démarre, aucune image."""
    capture = Capture()
    png = tmp_path / "architecture.png"

    fautive, index = pacome_dev_fautive(tmp_path, "fantome")

    rendu = lancer(monkeypatch, capture, fautive, png)

    assert rendu == 1
    assert capsys.readouterr().out.splitlines() == [
        f'links[{index}].to : aucune carte ne porte cet id, reçu "fantome"'
    ]
    assert (capture.commandes, png.exists()) == ([], False)


def test_une_description_illisible_sort_en_2_sans_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fichier absent : sortie 2, son motif en une ligne sur la sortie d'erreur."""
    capture = Capture()

    rendu = lancer(monkeypatch, capture, tmp_path / "absente.json", tmp_path / "a.png")

    assert (rendu, len(capsys.readouterr().err.splitlines()), capture.commandes) == (2, 1, [])


def test_la_capture_est_la_cli_de_playwright_epinglee_hors_de_tout_projet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`uv run --no-project --with playwright==1.64.1`, Chromium, fenêtre de 1200 × 1200 px au
    facteur d'échelle du descripteur « Desktop Chrome HiDPI », schéma clair, capture après le
    marqueur que pose la page (test suivant), 30 s au plus par attente."""
    capture = Capture()

    lancer(monkeypatch, capture, PACOME_DEV, tmp_path / "architecture.png")

    [commande] = capture.commandes
    options = dict(pairwise(commande))
    assert commande[:7] == [
        "uv",
        "run",
        "--no-project",
        "--with",
        "playwright==1.64.1",
        "playwright",
        "screenshot",
    ]
    assert {
        "--browser": "chromium",
        "--device": "Desktop Chrome HiDPI",
        "--viewport-size": "1200,1200",
        "--color-scheme": "light",
        "--wait-for-selector": "body[data-rendu-pret]",
        "--timeout": "30000",
    }.items() <= options.items()


def test_la_page_assemblee_pose_le_marqueur_qu_attend_la_capture_une_fois_rendue() -> None:
    """Le rendu fait, la page pose sur `<body>` l'attribut que la capture attend (test
    précédent) ; l'export l'injecte dans le gabarit, qui n'en porte aucun en propre."""
    page = page_de_pacome_dev()

    assert page.count("""render(); document.body.setAttribute("data-rendu-pret", '');""") == 1


ERREUR_CHROMIUM = b"""Error: Executable doesn't exist at /x/chromium_headless_shell-1248/headless_shell
Looks like Playwright was just installed or updated."""
ERREUR_ATTENTE = b"""TimeoutError: page.waitForSelector: Timeout 30000ms exceeded.
Call log:"""
# Ce que rend la capture → ce que dit le motif. `uv` introuvable : rien n'est lancé.
ECHECS = {
    "uv-introuvable": (None, 0, b"", PREREQUIS),
    "chromium-absent": ("uv", 1, ERREUR_CHROMIUM, PREREQUIS),
    "capture-en-echec": ("uv", 1, ERREUR_ATTENTE, "Timeout 30000ms exceeded."),
}


@pytest.mark.parametrize(("uv", "code", "erreur", "fragment"), ECHECS.values(), ids=ECHECS.keys())
def test_une_capture_impossible_sort_en_1_avec_son_motif_en_une_ligne(
    uv: str | None,
    code: int,
    erreur: bytes,
    fragment: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prérequis absent : le motif donne la commande qui l'installe. Autre échec : la première
    ligne de la CLI. Aucune image dans les deux cas."""
    png = tmp_path / "architecture.png"

    rendu = lancer(monkeypatch, Capture(code=code, erreur=erreur), PACOME_DEV, png, uv)

    lignes = capsys.readouterr().err.splitlines()
    assert (rendu, len(lignes), png.exists()) == (1, 1, False)
    assert fragment in lignes[0]


def test_un_fichier_des_couleurs_illisible_sort_en_2_sans_capture_ni_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le fichier des couleurs des logos se lit avant toute capture : mal formé, sortie 2, son
    motif en une ligne qui le nomme, aucun navigateur, aucune image (formes du fichier : le test
    d'`icones.py`, même lecteur)."""
    (tmp_path / "simple-icons").mkdir()
    (tmp_path / "simple-icons" / "couleurs.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(export, "ICONES", tmp_path)
    capture = Capture()
    png = tmp_path / "architecture.png"

    rendu = lancer(monkeypatch, capture, PACOME_DEV, png)

    lignes = capsys.readouterr().err.splitlines()
    assert (rendu, len(lignes), capture.commandes, png.exists()) == (2, 1, [], False)
    assert "couleurs.json" in lignes[0]


def test_la_cli_rend_ses_erreurs_en_utf_8_dans_un_tube(tmp_path: Path) -> None:
    """Le script lancé comme la session le lit, flux de l'enfant en cp1252 (`run_in_pipe`) :
    sortie 1, la ligne d'erreur lisible en UTF-8, aucune image."""
    png = tmp_path / "architecture.png"

    fautive, index = pacome_dev_fautive(tmp_path, "fantôme")

    done = run_in_pipe("schema-architecture", "export", str(fautive), str(png))

    assert done.returncode == 1
    assert done.stdout.decode("utf-8").splitlines() == [
        f'links[{index}].to : aucune carte ne porte cet id, reçu "fantôme"'
    ]
    assert not png.exists()


def propositions(dossier: Path, nombre: int) -> list[Path]:
    """`nombre` PNG témoins de 2400 × 2400 px, `1.png`, `2.png`… dans `dossier`, chacun distinct
    par un octet de plus après son en-tête."""
    images = [dossier / f"{numero}.png" for numero in range(1, nombre + 1)]
    for numero, image in enumerate(images, 1):
        image.write_bytes(CARRE + bytes([numero]))
    return images


def test_la_planche_assemblee_ne_charge_rien_hors_d_elle(tmp_path: Path) -> None:
    """Aucune URL, Manrope en `data:`, et chaque marqueur du gabarit remplacé."""
    page = export.assembler_planche(propositions(tmp_path, 2))

    assert re.findall("https?://[-./a-zA-Z0-9]+", page) == []
    assert page.count('url("data:font/woff2;base64,') == 1
    assert re.search("/[*][A-Z_]+[*]/", page) is None


@pytest.mark.parametrize("nombre", [2, 3, 4])
def test_la_planche_assemblee_porte_chaque_proposition_au_rang_de_son_numero(
    nombre: int, tmp_path: Path
) -> None:
    """Chaque image en URL `data:`, une seule fois, dans l'ordre de ses numéros : la page numérote
    les propositions par leur rang."""
    images = propositions(tmp_path, nombre)

    page = export.assembler_planche(images)

    assert re.findall("data:image/png;base64,[A-Za-z0-9+/=]*", page) == [
        f"data:image/png;base64,{base64.b64encode(image.read_bytes()).decode('ascii')}"
        for image in images
    ]


def test_la_planche_assemblee_pose_le_marqueur_qu_attend_la_capture(tmp_path: Path) -> None:
    """Le marqueur de fin de rendu, que l'export injecte comme dans la page du schéma."""
    page = export.assembler_planche(propositions(tmp_path, 2))

    assert page.count("""document.body.setAttribute("data-rendu-pret", '')""") == 1


@pytest.mark.parametrize("nombre", [1, 5])
def test_la_planche_refuse_moins_de_2_ou_plus_de_4_propositions(
    nombre: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le motif du refus, aucune capture, rien d'écrit."""
    capture = Capture()
    remplacer(monkeypatch, capture)
    sortie = tmp_path / "planche.png"

    motif = export.planche(propositions(tmp_path, nombre), sortie)

    assert (motif, capture.commandes, sortie.exists()) == (
        f"de 2 à 4 propositions, reçu {nombre}",
        [],
        False,
    )


def test_la_planche_se_capture_dans_sa_fenetre_et_s_ecrit_a_sa_taille(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une fenêtre de 2000 × 840 px au facteur d'échelle 2 : la planche de 4000 × 1680 px est
    écrite, sans motif."""
    capture = Capture()
    remplacer(monkeypatch, capture)
    sortie = tmp_path / "planche.png"

    motif = export.planche(propositions(tmp_path, 2), sortie)

    assert ([fenetre(commande) for commande in capture.commandes], motif, sortie.read_bytes()) == (
        ["2000,840"],
        None,
        PLANCHE,
    )


ECHECS_DE_PLANCHE = {
    "carre-d-une-proposition": (CARRE, 0, "capture de 2400 × 2400 px, attendu 4000 × 1680"),
    "capture-en-echec": (None, 1, "Timeout 30000ms exceeded."),
}


@pytest.mark.parametrize(
    ("png", "code", "fragment"), ECHECS_DE_PLANCHE.values(), ids=ECHECS_DE_PLANCHE.keys()
)
def test_une_planche_d_une_autre_taille_ou_en_echec_n_ecrit_rien(
    png: bytes | None, code: int, fragment: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le motif en une ligne, et rien d'écrit à la sortie."""
    remplacer(monkeypatch, Capture(png=png, code=code, erreur=ERREUR_ATTENTE))
    sortie = tmp_path / "planche.png"

    motif = export.planche(propositions(tmp_path, 2), sortie)

    assert (fragment in (motif or ""), sortie.exists()) == (True, False)


def variantes(dossier: Path, nombre: int) -> list[str]:
    """`nombre` descriptions valides, `variante-<k>.json` dans `dossier` : celle de pacome.dev,
    son `intro` « variante <k> »."""
    lue = json.loads(PACOME_DEV.read_text(encoding="utf-8"))
    chemins = [dossier / f"variante-{numero}.json" for numero in range(1, nombre + 1)]
    for numero, chemin in enumerate(chemins, 1):
        chemin.write_text(json.dumps({**lue, "intro": f"variante {numero}"}), encoding="utf-8")
    return [str(chemin) for chemin in chemins]


@pytest.mark.parametrize("nombre", [2, 3, 4])
def test_le_mode_propositions_ecrit_chaque_proposition_puis_leur_planche(
    nombre: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dans le dossier par défaut : `proposition-<k>.png`, la description de rang k, puis
    `planche.png` ; une ligne par fichier écrit, chaque capture à la taille de sa fenêtre."""
    descriptions = variantes(tmp_path, nombre)
    monkeypatch.chdir(tmp_path)
    capture = Capture()
    remplacer(monkeypatch, capture)
    dossier = Path("docs/schema/propositions")
    ecrites = [f"proposition-{numero}.png" for numero in range(1, nombre + 1)]

    rendu = export.main(["--propositions", *descriptions])

    assert (rendu, capsys.readouterr().out.splitlines()) == (
        0,
        [
            *(f"{dossier / nom} : 2400 × 2400" for nom in ecrites),
            f"{dossier / 'planche.png'} : 4000 × 1680",
        ],
    )
    assert [fenetre(commande) for commande in capture.commandes] == ["1200,1200"] * nombre + [
        "2000,840"
    ]
    assert [re.findall('"intro": "(variante [0-9])"', page) for page in capture.pages] == [
        *([f"variante {numero}"] for numero in range(1, nombre + 1)),
        [],
    ]
    assert {fichier.name: fichier.read_bytes() for fichier in dossier.iterdir()} == {
        **dict.fromkeys(ecrites, CARRE),
        "planche.png": PLANCHE,
    }


def test_une_description_invalide_parmi_les_propositions_sort_en_1_sans_capture_ni_fichier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Toutes les descriptions se valident d'abord, en une passe : chaque erreur sort, préfixée de
    son fichier ; aucune capture, aucun fichier."""
    capture = Capture()
    remplacer(monkeypatch, capture)
    dossier = tmp_path / "propositions"
    fantome, index_fantome = pacome_dev_fautive(tmp_path, "fantome")
    spectre, index_spectre = pacome_dev_fautive(tmp_path, "spectre")

    rendu = export.main(
        ["--propositions", str(fantome), str(PACOME_DEV), str(spectre), "--dossier", str(dossier)]
    )

    assert (rendu, capsys.readouterr().out.splitlines()) == (
        1,
        [
            f'{fantome} : links[{index_fantome}].to : aucune carte ne porte cet id, reçu "fantome"',
            f'{spectre} : links[{index_spectre}].to : aucune carte ne porte cet id, reçu "spectre"',
        ],
    )
    assert (capture.commandes, dossier.exists()) == ([], False)


def test_une_description_illisible_parmi_les_propositions_sort_en_2_sans_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fichier absent : sortie 2, son motif en une ligne préfixée de son fichier ; aucune capture,
    aucun fichier."""
    capture = Capture()
    remplacer(monkeypatch, capture)
    absente, dossier = tmp_path / "absente.json", tmp_path / "propositions"

    rendu = export.main(
        ["--propositions", str(PACOME_DEV), str(absente), "--dossier", str(dossier)]
    )

    lignes = capsys.readouterr().err.splitlines()
    assert (rendu, len(lignes), capture.commandes, dossier.exists()) == (2, 1, [], False)
    assert lignes[0].startswith(f"{absente} : fichier illisible")


ECHECS_DES_PROPOSITIONS: dict[str, tuple[bytes, int, list[str], str]] = {
    # La première proposition à la taille de la planche : rien d'écrit, rien d'autre de capturé.
    "proposition-de-4000-sur-1680": (
        PLANCHE,
        1,
        [],
        "proposition-1.png : capture de 4000 × 1680 px, attendu 2400 × 2400",
    ),
    # Les propositions écrites, puis la planche à leur taille : pas de planche.
    "planche-de-2400-sur-2400": (
        CARRE,
        3,
        ["proposition-1.png", "proposition-2.png"],
        "planche.png : capture de 2400 × 2400 px, attendu 4000 × 1680",
    ),
}


@pytest.mark.parametrize(
    ("png", "captures", "ecrites", "fragment"),
    ECHECS_DES_PROPOSITIONS.values(),
    ids=ECHECS_DES_PROPOSITIONS.keys(),
)
def test_le_mode_propositions_s_arrete_a_la_premiere_capture_d_une_autre_taille(
    png: bytes,
    captures: int,
    ecrites: list[str],
    fragment: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sortie 1, le motif en une ligne qui nomme le fichier ; rien n'est écrit à sa place."""
    capture = Capture(png=png)
    remplacer(monkeypatch, capture)
    dossier = tmp_path / "propositions"

    rendu = export.main(["--propositions", *[str(PACOME_DEV)] * 2, "--dossier", str(dossier)])

    lignes = capsys.readouterr().err.splitlines()
    assert (rendu, len(capture.commandes), sorted(ecrit.name for ecrit in dossier.glob("*"))) == (
        1,
        captures,
        ecrites,
    )
    assert len(lignes) == 1
    assert fragment in lignes[0]


APPELS_MAL_FORMES = {
    "une-proposition": (["--propositions", "a.json"], "de 2 à 4 propositions, reçu 1"),
    "cinq-propositions": (["--propositions", *["a.json"] * 5], "de 2 à 4 propositions, reçu 5"),
    "dossier-sans-propositions": (
        ["a.json", "--dossier", "d"],
        "--dossier ne vaut qu'avec --propositions",
    ),
    "description-et-propositions": (
        ["a.json", "--propositions", "b.json", "c.json"],
        "--propositions ne prend ni <description> ni <png>",
    ),
}


@pytest.mark.parametrize(
    ("argv", "fragment"), APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys()
)
def test_un_appel_mal_forme_sort_en_2_sans_rien_lire_ni_capturer(
    argv: list[str],
    fragment: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le motif sur la sortie d'erreur, avant toute lecture : les descriptions nommées n'existent
    pas."""
    monkeypatch.chdir(tmp_path)
    capture = Capture()
    remplacer(monkeypatch, capture)

    with pytest.raises(SystemExit) as sortie:
        export.main(argv)

    assert (sortie.value.code, capture.commandes) == (2, [])
    assert fragment in capsys.readouterr().err
