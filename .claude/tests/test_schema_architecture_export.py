"""Tests de l'export du schéma d'architecture
(`.claude/skills/schema-architecture/scripts/export.py`).

La capture passe par une frontière, `subprocess.run`, que ces tests remplacent par un témoin
(`Capture`) : il note la commande, et écrit au dernier chemin qu'elle nomme un PNG témoin construit
ici octet par octet. Un navigateur n'entre pas dans la suite : l'export réel se joue sur le poste.
Les cas s'écrivent en littéraux, jamais tirés des constantes du script
(`cycle-pr/references/tests.md`, « Le rouge se constate, il ne se suppose pas ») ; seul le PNG
témoin d'une capture réussie, là où la taille n'est pas le cas éprouvé, prend le côté du script
(`CONFORME`).
"""

import json
import re
import shutil
import struct
import subprocess
import zlib
from itertools import pairwise
from pathlib import Path
from typing import cast

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


class Capture:
    """`subprocess.run` remplacé : note chaque commande, et rend `code` avec `erreur` sur la
    sortie d'erreur ; sur un code 0, écrit `png` au chemin que la commande nomme en dernier."""

    def __init__(self, png: bytes = b"", code: int = 0, erreur: bytes = b"") -> None:
        self.png, self.code, self.erreur = png, code, erreur
        self.commandes: list[list[str]] = []

    def __call__(self, commande: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        self.commandes.append(commande)
        if self.code == 0:
            Path(commande[-1]).write_bytes(self.png)
        return subprocess.CompletedProcess(commande, self.code, b"", self.erreur)


def lancer(
    monkeypatch: pytest.MonkeyPatch,
    capture: Capture,
    lue: Path,
    png: Path,
    uv: str | None = "uv",
) -> int:
    """`export.main` sur la description `lue` et l'image `png`, la capture remplacée par
    `capture`, et `uv` trouvé au chemin `uv` — introuvable sous `None`."""

    def trouver(_: str) -> str | None:
        return uv

    monkeypatch.setattr(subprocess, "run", capture)
    monkeypatch.setattr(shutil, "which", trouver)
    return export.main([str(lue), str(png)])


def pacome_dev_fautive(tmp_path: Path, cible: str) -> tuple[Path, int]:
    """La description de pacome.dev, un lien de plus vers la carte d'id `cible`, absente : son
    chemin et l'index de ce lien, que la description réelle déplace à chaque lien ajouté."""
    fautive = json.loads(PACOME_DEV.read_text(encoding="utf-8"))
    fautive["links"].append({"from": "api", "to": cible})
    chemin = tmp_path / "architecture.json"
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


# Le PNG témoin d'une capture réussie, au côté que le script attend.
CONFORME = png_temoin(export.COTE, export.COTE)

TAILLES = {
    "carre-de-2400": (png_temoin(2400, 2400), 0, "architecture.png : 2400 × 2400"),
    # La fenêtre sans le facteur d'échelle du descripteur.
    "carre-de-1200": (png_temoin(1200, 1200), 1, "1200 × 1200"),
    "autre-taille": (png_temoin(2400, 1800), 1, "2400 × 1800"),
    "signature-fausse": (b"GIF89a" + CONFORME[6:], 1, "pas un PNG"),
    "premier-bloc-pas-ihdr": (CONFORME.replace(b"IHDR", b"IDAT"), 1, "pas un PNG"),
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
    capture = Capture(png=CONFORME)
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
    capture = Capture(png=CONFORME)

    rendu = lancer(monkeypatch, capture, tmp_path / "absente.json", tmp_path / "a.png")

    assert (rendu, len(capsys.readouterr().err.splitlines()), capture.commandes) == (2, 1, [])


def test_la_capture_est_la_cli_de_playwright_epinglee_hors_de_tout_projet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`uv run --no-project --with playwright==1.64.1`, Chromium, fenêtre de 1200 × 1200 px au
    facteur d'échelle du descripteur « Desktop Chrome HiDPI », schéma clair, capture après le
    marqueur que pose la page (test suivant), 30 s au plus par attente."""
    capture = Capture(png=CONFORME)

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
    capture = Capture(png=CONFORME)
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
