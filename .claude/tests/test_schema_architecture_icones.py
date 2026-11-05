"""Tests du script d'icônes du schéma d'architecture
(`.claude/skills/schema-architecture/scripts/icones.py`).

Le réseau passe par une frontière, `urlopen`, que ces tests remplacent par un CDN témoin
(`Cdn`) ; le dossier d'icônes, par un dossier temporaire. Les URL s'écrivent en littéraux : elles
éprouvent aussi les versions épinglées (`cycle-pr/references/tests.md`, « Le rouge se constate, il
ne se suppose pas »).
"""

import io
import json
from email.message import Message
from pathlib import Path

import pytest
from conftest import REPOSITORY_ROOT, load_script, run_in_pipe

icones = load_script("schema-architecture", "icones")

SVG_LOGO = "https://cdn.jsdelivr.net/npm/simple-icons@15.0.0/icons/{}.svg"
SVG_LUCIDE = "https://cdn.jsdelivr.net/npm/lucide-static@0.460.0/icons/{}.svg"
DONNEES = "https://cdn.jsdelivr.net/npm/simple-icons@15.0.0/data/simple-icons.json"
# Un logo au slug déclaré, un logo au slug tiré de son titre — `.` et `+` remplacés, l'accent
# décomposé puis ôté.
LOGOS = [
    {"title": "Hetzner Cloud", "hex": "D50C2D", "slug": "hetzner"},
    {"title": "Nodé.js+", "hex": "5FA04E"},
]
# Le `couleurs.json` du dossier témoin, au format du dossier du skill.
COULEURS_TEMOINS = """{
  "caddy": "#1F88C0",
  "redis": "#FF4438"
}
"""


class Cdn:
    """`urlopen` remplacé : rend le contenu de chaque URL connue, 404 pour les autres, ou lève
    `panne` à chaque requête ; note chaque URL demandée."""

    def __init__(self, contenus: dict[str, bytes], panne: OSError | None = None) -> None:
        self.contenus, self.panne = contenus, panne
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> io.BytesIO:
        self.urls.append(url)
        if self.panne:
            raise self.panne
        if url not in self.contenus:
            raise icones.HTTPError(url, 404, "Not Found", Message(), None)
        return io.BytesIO(self.contenus[url])


def dossier_temoin(tmp_path: Path, couleurs: bytes | None) -> Path:
    """Un dossier d'icônes : un logo, une icône neutre, et le fichier des couleurs de contenu
    `couleurs`, absent sous `None`."""
    for jeu, nom in (("simple-icons", "caddy"), ("lucide", "globe")):
        (tmp_path / jeu).mkdir()
        (tmp_path / jeu / f"{nom}.svg").write_text("<svg/>", encoding="utf-8")
    if couleurs is not None:
        (tmp_path / "simple-icons" / "couleurs.json").write_bytes(couleurs)
    return tmp_path


def lancer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cdn: Cdn,
    *args: str,
    couleurs: bytes | None = COULEURS_TEMOINS.encode(),
) -> int:
    """`icones.main(args)` sur le dossier témoin, son fichier des couleurs de contenu `couleurs`
    — celui du logo témoin par défaut —, le réseau remplacé par `cdn`."""
    monkeypatch.setattr(icones, "ICONES", dossier_temoin(tmp_path, couleurs))
    monkeypatch.setattr(icones, "urlopen", cdn)
    return icones.main(list(args))


@pytest.mark.parametrize(("nom", "hexa"), [("hetzner", "#D50C2D"), ("nodedotjsplus", "#5FA04E")])
def test_un_logo_s_ecrit_tel_quel_avec_sa_couleur_parmi_les_cles_triees(
    nom: str, hexa: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le SVG octet pour octet ; la couleur lue au slug du logo — déclaré, ou tiré du titre
    comme le fait Simple Icons —, ajoutée à `couleurs.json` au format du dossier."""
    svg = b'<svg role="img"><path d="M0 0h24"/></svg>'
    cdn = Cdn({SVG_LOGO.format(nom): svg, DONNEES: json.dumps(LOGOS).encode()})

    assert lancer(monkeypatch, tmp_path, cdn, nom, "--simple-icons") == 0

    assert (tmp_path / "simple-icons" / f"{nom}.svg").read_bytes() == svg
    assert (
        (tmp_path / "simple-icons" / "couleurs.json").read_bytes()
        == f"""{{
  "caddy": "#1F88C0",
  "{nom}": "{hexa}",
  "redis": "#FF4438"
}}
""".encode()
    )


def test_une_icone_neutre_s_ecrit_sans_toucher_aux_couleurs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le SVG Lucide octet pour octet ; ni les données des logos ni `couleurs.json`."""
    svg = b"<!-- @license lucide-static v0.460.0 - ISC --><svg/>"
    cdn = Cdn({SVG_LUCIDE.format("vault"): svg})

    assert lancer(monkeypatch, tmp_path, cdn, "vault", "--lucide") == 0

    assert (tmp_path / "lucide" / "vault.svg").read_bytes() == svg
    assert cdn.urls == [SVG_LUCIDE.format("vault")]
    assert (tmp_path / "simple-icons" / "couleurs.json").read_text() == COULEURS_TEMOINS


def test_une_icone_deja_presente_sort_en_0_sans_requete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le script le dit, sur la sortie standard, et ne tire rien."""
    cdn = Cdn({})

    assert lancer(monkeypatch, tmp_path, cdn, "caddy", "--simple-icons") == 0

    assert "déjà présente" in capsys.readouterr().out
    assert cdn.urls == []


# Ce que rend le CDN → ce que nomme le motif. Le nom déjà pris par l'autre jeu ne tire rien.
ECHECS = {
    "nom-inconnu-404": ("fantome", "--lucide", Cdn({}), "HTTP 404"),
    "reseau-en-echec": (
        "vault",
        "--lucide",
        Cdn({}, icones.URLError("hôte injoignable")),
        "réseau",
    ),
    "logo-absent-des-donnees": (
        "fantome",
        "--simple-icons",
        Cdn({SVG_LOGO.format("fantome"): b"<svg/>", DONNEES: json.dumps(LOGOS).encode()}),
        "aucun logo",
    ),
    "nom-pris-par-l-autre-jeu": ("globe", "--simple-icons", Cdn({}), "lucide"),
    "donnees-illisibles": (
        "hetzner",
        "--simple-icons",
        Cdn({SVG_LOGO.format("hetzner"): b"<svg/>", DONNEES: b"<!doctype html>"}),
        "illisibles",
    ),
}


@pytest.mark.parametrize(("nom", "jeu", "cdn", "fragment"), ECHECS.values(), ids=ECHECS.keys())
def test_un_echec_sort_en_1_avec_son_motif_en_une_ligne_sans_rien_ecrire(
    nom: str,
    jeu: str,
    cdn: Cdn,
    fragment: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sortie 1, une ligne sur la sortie d'erreur, et le dossier d'icônes inchangé."""
    rendu = lancer(monkeypatch, tmp_path, cdn, nom, jeu)

    lignes = capsys.readouterr().err.splitlines()
    assert (rendu, len(lignes)) == (1, 1)
    assert fragment in lignes[0]
    assert sorted(chemin.name for chemin in tmp_path.rglob("*")) == [
        "caddy.svg",
        "couleurs.json",
        "globe.svg",
        "lucide",
        "simple-icons",
    ]


# Le contenu du `couleurs.json` du dossier témoin → ce qui le rend illisible ; `None` : absent.
COULEURS_ILLISIBLES = {
    "json-mal-forme": b'{"caddy": "#1F88C0",',
    "pas-en-utf-8": b'{"caddy": "#1F88C0", "\xe9": "#000000"}',
    "absent": None,
    "pas-un-objet": b'["#1F88C0"]',
    "couleur-d-un-autre-type": b'{"caddy": 7}',
    # Le `hex` de Simple Icons, recopié sans son `#`.
    "couleur-qui-n-est-pas-rrggbb": b'{"caddy": "1F88C0"}',
}


@pytest.mark.parametrize("contenu", COULEURS_ILLISIBLES.values(), ids=COULEURS_ILLISIBLES.keys())
def test_un_fichier_des_couleurs_illisible_sort_en_2_avant_toute_ecriture(
    contenu: bytes | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le fichier des couleurs se lit avant que le logo s'écrive : illisible, sortie 2, son motif
    en une ligne qui le nomme, et aucune des deux écritures — ni le SVG, ni les couleurs."""
    cdn = Cdn({SVG_LOGO.format("hetzner"): b"<svg/>", DONNEES: json.dumps(LOGOS).encode()})

    rendu = lancer(monkeypatch, tmp_path, cdn, "hetzner", "--simple-icons", couleurs=contenu)

    lignes = capsys.readouterr().err.splitlines()
    assert (rendu, len(lignes)) == (2, 1)
    assert "couleurs.json" in lignes[0]
    couleurs = tmp_path / "simple-icons" / "couleurs.json"
    assert not (tmp_path / "simple-icons" / "hetzner.svg").exists()
    assert (couleurs.read_bytes() if couleurs.exists() else None) == contenu


def test_un_nom_qui_sortirait_du_dossier_est_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le nom devient un chemin et une URL : minuscules, chiffres et tirets seulement."""
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, tmp_path, Cdn({}), "../caddy", "--lucide")

    assert sortie.value.code == 2


def test_les_couleurs_du_skill_couvrent_exactement_ses_logos() -> None:
    """Le dossier des logos du skill : une couleur par SVG, aucune de plus — un logo sans couleur
    se peindrait en noir, une couleur sans logo ne sert à rien."""
    logos = REPOSITORY_ROOT / ".claude/skills/schema-architecture/icones/simple-icons"
    couleurs = json.loads((logos / "couleurs.json").read_text(encoding="utf-8"))

    assert sorted(couleurs) == sorted(chemin.stem for chemin in logos.glob("*.svg"))


def test_la_cli_ecrit_en_utf_8_dans_un_tube() -> None:
    """Le script lancé comme la session le lit, flux de l'enfant en cp1252 (`run_in_pipe`), sur
    un nom refusé avant toute lecture — ni réseau ni écriture : le motif accentué, lisible en
    UTF-8."""
    done = run_in_pipe("schema-architecture", "icones", "../caddy", "--lucide")

    assert done.returncode == 2
    assert "nom d'icône invalide" in done.stderr.decode("utf-8")
