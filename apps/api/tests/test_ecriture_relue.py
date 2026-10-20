"""Tests de la famille « écriture distante relue »
(`.claude/skills/cycle-pr/scripts/ecriture-relue.py`).

Le script écrit un texte de la forge puis le relit en entier : chaque cas éprouve l'une des deux
moitiés — ce qui part (la charge du `PATCH`, lue sur l'entrée standard de `gh`), ou ce que la
relecture voit. Il parle à `gh` par une seule fonction, `run`, que ces tests remplacent par une
forge témoin : elle garde les documents en mémoire, applique chaque écriture par la fonction
`stocke` — l'identité, ou la transformation qu'un cas veut lui faire subir — et ne répond qu'aux
**commandes complètes** attendues, arguments compris ; toute autre lève. La vraie forge n'est
jamais appelée. Les cas s'écrivent en littéraux, jamais dérivés des constantes du script
(`cycle-pr` 3.1, « la table de cas est dérivée de l'artefact sous test »).
"""

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from skill_scripts import REPOSITORY_ROOT, load_script

ecriture_relue = load_script("cycle-pr", "ecriture-relue")

CORPS_42 = "repos/{owner}/{repo}/issues/42"
# Les seuls retraits de label auxquels la forge répond : chemin encodé → nom du label.
RETRAITS = {
    "repos/{owner}/{repo}/issues/42/labels/ready-for-agent": "ready-for-agent",
    "repos/{owner}/{repo}/issues/42/labels/en%20attente": "en attente",
    "repos/{owner}/{repo}/issues/42/labels/zone%2Fapi": "zone/api",
}


class Forge:
    """Une forge témoin : des documents en mémoire, chacun sous son chemin `gh api`.

    Args:
        documents: chemin → document JSON, tel que l'API REST le rend.
        stocke: ce que la forge fait d'un corps reçu par `PATCH` avant de le garder — l'identité
            par défaut ; `None` vaut un corps effacé, que l'API rend `null`.
        pages: les commentaires de l'issue 42, page par page, tels que
            `gh api --paginate --slurp` les rend ; chacun est aussi un document sous son chemin
            `issues/comments/<id>`, le même objet — une écriture se voit donc dans la liste.
    """

    def __init__(
        self,
        documents: dict[str, dict[str, Any]],
        *,
        stocke: Callable[[str], str | None] = lambda corps: corps,
        pages: list[list[dict[str, Any]]] | None = None,
        garde_les_labels: bool = False,
    ) -> None:
        self.documents = documents
        self.stocke = stocke
        self.garde_les_labels = garde_les_labels
        self.pages = pages or []
        for page in self.pages:
            for commentaire in page:
                self.documents[f"repos/{{owner}}/{{repo}}/issues/comments/{commentaire['id']}"] = (
                    commentaire
                )
        self.appels: list[tuple[str, ...]] = []
        self.charges: list[bytes] = []

    def __call__(
        self, cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        cmd = tuple(cmd)
        self.appels.append(cmd)
        match cmd:
            case ("gh", "api", chemin) if chemin in self.documents and stdin is None:
                return reponse(self.documents[chemin])
            case ("gh", "api", "-X", "PATCH", chemin, "--input", "-") if (
                chemin in self.documents and stdin is not None
            ):
                self.charges.append(stdin)
                self.documents[chemin]["body"] = self.stocke(json.loads(stdin)["body"])
                return reponse(self.documents[chemin])
            case ("gh", "api", "--paginate", "--slurp", "repos/{owner}/{repo}/issues/42/comments"):
                return reponse(self.pages)
            case ("gh", "api", "-X", "DELETE", chemin) if chemin in RETRAITS and stdin is None:
                labels = self.documents[CORPS_42]["labels"]
                if not self.garde_les_labels:
                    labels[:] = [label for label in labels if label["name"] != RETRAITS[chemin]]
                return reponse(labels)
            case _:
                raise AssertionError(f"commande inattendue : {cmd}")


def reponse(document: Any) -> subprocess.CompletedProcess[bytes]:
    """La sortie de `gh api` : le JSON brut, en UTF-8 — accents compris, comme l'API les rend."""
    return subprocess.CompletedProcess(
        [], 0, stdout=json.dumps(document, ensure_ascii=False).encode()
    )


def lance(forge: Forge, *args: str) -> int:
    """Le script tel que la session l'appelle."""
    return ecriture_relue.main(list(args), run=forge)


def sortie_d_echec(capsys: pytest.CaptureFixture[str], issue: str) -> str:
    """La sortie d'un échec : une seule ligne, ouverte par son issue — « refus » quand rien n'est
    écrit, « relecture non conforme » quand l'écriture est lancée."""
    sortie = capsys.readouterr().out.strip()
    assert sortie.startswith(f"{issue} — "), sortie
    assert "\n" not in sortie, f"la sortie tient en plus d'une ligne : {sortie!r}"
    return sortie


def test_checkbox_patch_coche_les_cases_nommees_et_relit_le_corps_entier() -> None:
    """Le témoin positif, et l'ordre : lire, écrire, relire. La charge est comparée octet pour
    octet — accents en UTF-8 brut, fins de ligne intactes."""
    forge = Forge(
        {CORPS_42: {"body": "## Critères\n\n- [ ] Critère A\n- [ ] Critère B\n- [ ] Z\n"}}
    )

    assert lance(forge, "checkbox", "patch", "42", "--case", "Critère A", "--case", "Z") == 0
    assert forge.charges == [
        '{"body": "## Critères\\n\\n- [x] Critère A\\n- [ ] Critère B\\n- [x] Z\\n"}'.encode()
    ]
    patch = ("gh", "api", "-X", "PATCH", CORPS_42, "--input", "-")
    assert forge.appels == [("gh", "api", CORPS_42), patch, ("gh", "api", CORPS_42)]


def test_checkbox_patch_garde_les_fins_de_ligne_crlf_du_corps() -> None:
    """Un texte distant n'a pas de fin de ligne par défaut : un corps en CRLF part avec ses CRLF,
    et la relecture compare à ce texte-là (obs 87, 106, 116)."""
    forge = Forge({CORPS_42: {"body": "Intro\r\n- [ ] Critère A\r\n- [ ] Critère B\r\n"}})

    assert lance(forge, "checkbox", "patch", "42", "--case", "Critère B") == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        "Intro\r\n- [ ] Critère A\r\n- [x] Critère B\r\n"
    ]


# Chaque forme de ligne de case : décochée, indentée d'espaces ou d'une tabulation, cochée en
# minuscule ou en majuscule — GitHub tient `[X]` pour coché.
CORPS_A_CASES = (
    "- [ ] Critère A\n"
    "- [ ] Critère B\n"
    "  - [ ] Sous-critère B\n"
    "\t- [ ] Autre sous-critère B\n"
    "- [x] Critère C\n"
    "- [X] Critère D\n"
)

# Un refus par ancre en défaut : la sortie nomme l'ancre et sa raison, et rien n'est écrit — même
# quand d'autres ancres de l'appel étaient valides (toutes sont validées avant la première
# écriture).
REFUS_D_ANCRE = {
    "ancre-inconnue-parmi-des-valides": (
        ("--case", "Critère A", "--case", "Critère inconnu", "--case", "Critère C"),
        "case introuvable : Critère inconnu",
    ),
    "ancre-ambigue": (
        ("--case", "Critère A", "--case", "ritère B"),
        "case ambiguë : ritère B (3 lignes)",
    ),
    "ancre-hors-de-toute-case": (("--case", "Intro"), "case introuvable : Intro"),
    "deux-ancres-en-defaut-toutes-deux-nommees": (
        ("--case", "Critère inconnu", "--case", "ritère B"),
        "case introuvable : Critère inconnu ; case ambiguë : ritère B (3 lignes)",
    ),
}


@pytest.mark.parametrize(("cases", "motif"), REFUS_D_ANCRE.values(), ids=REFUS_D_ANCRE.keys())
def test_une_ancre_en_defaut_refuse_tout_l_appel_sans_rien_ecrire(
    cases: tuple[str, ...], motif: str, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: {"body": "Intro\n" + CORPS_A_CASES}})

    assert lance(forge, "checkbox", "patch", "42", *cases) == 1
    assert forge.charges == [], "un PATCH est parti malgré le refus"
    assert motif in sortie_d_echec(capsys, "refus")


@pytest.mark.parametrize("ancre", ["Critère C", "Critère D"], ids=["x-minuscule", "x-majuscule"])
def test_une_case_deja_cochee_ne_fait_rien_ecrire_et_le_dit(
    ancre: str, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: {"body": CORPS_A_CASES}})

    assert lance(forge, "checkbox", "patch", "42", "--case", ancre) == 0
    assert forge.charges == []
    assert f"déjà cochée : {ancre}" in capsys.readouterr().out


# Ce que la forge garde d'un corps reçu, quand ce n'est pas ce qu'on lui a envoyé : (corps lu,
# corps gardé après qu'on y a coché « Critère A », sortie **exacte**). Chaque forme doit faire
# sortir en 1 — la relecture compare le texte entier, jamais une forme réduite (obs 106) — et la
# sortie ne nomme absente que l'ancre qui l'est vraiment.
RELECTURES_NON_CONFORMES: dict[str, tuple[str, Callable[[str], str | None], str]] = {
    # La ligne cochée n'est pas là : l'ancre se nomme.
    "ligne-cochee-absente": (
        "- [ ] Critère A\n- [ ] Critère B\n",
        lambda corps: corps.replace("- [x] Critère A\n", ""),
        "ancre absente : - [x] Critère A ; attendu 34 octets et 0 \\r, relu 17 octets et 0 \\r",
    ),
    # Le bon texte, converti LF → CRLF : ancres intactes, mais pas les octets ni les `\r`.
    "lf-converti-en-crlf": (
        "- [ ] Critère A\n- [ ] Critère B\n",
        lambda corps: corps.replace("\n", "\r\n"),
        "attendu 34 octets et 0 \\r, relu 36 octets et 2 \\r",
    ),
    # Les fins de ligne permutées : même longueur en caractères comme en octets, même nombre de
    # `\r`, mêmes ancres — seule la comparaison du texte entier la voit. C'est ce cas, pas le
    # précédent, qui garde la classe d'obs 106 : le lecteur en octets garde les `\r`, si bien
    # qu'une comparaison réduite à « ancre + longueur en caractères » voit encore LF → CRLF
    # (mutation jouée au lot 4a : VERTE sur le cas précédent seul, ROUGE sur celui-ci).
    "fins-de-ligne-permutees": (
        "- [ ] Critère A\r\n- [ ] Critère B\n",
        lambda corps: "- [x] Critère A\n- [ ] Critère B\r\n",
        "attendu 35 octets et 1 \\r, relu 35 octets et 1 \\r",
    ),
    # Le corps relu est `null` : un texte vide, pas une panne du script.
    "corps-efface": (
        "- [ ] Critère A\n- [ ] Critère B\n",
        lambda corps: None,
        "ancre absente : - [x] Critère A ; attendu 34 octets et 0 \\r, relu 0 octets et 0 \\r",
    ),
}


@pytest.mark.parametrize(
    ("corps", "stocke", "ecart"),
    RELECTURES_NON_CONFORMES.values(),
    ids=RELECTURES_NON_CONFORMES.keys(),
)
def test_une_relecture_qui_n_est_pas_le_texte_ecrit_sort_en_1_et_dit_l_ecart(
    corps: str,
    stocke: Callable[[str], str | None],
    ecart: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({CORPS_42: {"body": corps}}, stocke=stocke)

    assert lance(forge, "checkbox", "patch", "42", "--case", "Critère A") == 1
    assert capsys.readouterr().out == f"relecture non conforme — {ecart}\n"


BRIEF = "## Brief d'agent\n\n**Critères d'acceptation :**\n- [ ] Critère A\n- [ ] Critère B\n"
CITATION = {"id": 11, "body": "Le ## Brief d'agent plus bas fait foi.\n- [ ] Critère A\n"}


def test_brief_patch_coche_le_commentaire_de_brief_trouve_sur_une_autre_page() -> None:
    """Le brief est le seul commentaire **ouvert** par `## Brief d'agent` : une citation qui le
    nomme plus loin, un commentaire sans corps, et le corps de l'issue ne sont pas touchés."""
    pages = [[CITATION, {"id": 12, "body": None}], [{"id": 13, "body": BRIEF}]]
    forge = Forge({CORPS_42: {"body": "- [ ] Critère A\n"}}, pages=pages)

    assert lance(forge, "brief", "patch", "42", "--case", "Critère A") == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        "## Brief d'agent\n\n**Critères d'acceptation :**\n- [x] Critère A\n- [ ] Critère B\n"
    ]
    brief = "repos/{owner}/{repo}/issues/comments/13"
    assert ("gh", "api", "-X", "PATCH", brief, "--input", "-") in forge.appels


@pytest.mark.parametrize(
    ("pages", "motif"),
    [
        ([[CITATION]], "il faut un seul commentaire de brief sur #42, il y en a 0"),
        (
            [[{"id": 13, "body": BRIEF}], [{"id": 14, "body": BRIEF}]],
            "il faut un seul commentaire de brief sur #42, il y en a 2",
        ),
    ],
    ids=["aucun-brief", "deux-briefs"],
)
def test_brief_patch_refuse_sans_un_seul_commentaire_de_brief(
    pages: list[list[dict[str, Any]]], motif: str, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({}, pages=pages)

    assert lance(forge, "brief", "patch", "42", "--case", "Critère A") == 1
    assert forge.charges == []
    assert motif in sortie_d_echec(capsys, "refus")


def etiquetee(*noms: str) -> dict[str, Any]:
    """Une issue qui porte ces labels, sous la forme que l'API REST les rend."""
    return {"body": "", "labels": [{"name": nom} for nom in noms]}


def retraits(forge: Forge) -> list[tuple[str, ...]]:
    """Les appels `DELETE` que la forge a reçus — un par retrait de label tenté."""
    return [appel for appel in forge.appels if appel[2:4] == ("-X", "DELETE")]


@pytest.mark.parametrize(
    "label",
    ["ready-for-agent", "en attente", "zone/api"],
    ids=["simple", "avec-espace", "avec-barre-oblique"],
)
def test_label_remove_retire_le_label_puis_le_relit_absent(label: str) -> None:
    """Le nom part encodé en **un** segment de chemin : la forge ne répond qu'à `en%20attente`
    et `zone%2Fapi` — une barre laissée telle quelle couperait le nom en deux segments."""
    forge = Forge({CORPS_42: etiquetee(label, "enhancement")})

    assert lance(forge, "label", "42", "--remove", label) == 0
    assert len(retraits(forge)) == 1
    assert forge.appels[-1] == ("gh", "api", CORPS_42), "le retrait n'est pas relu"
    assert forge.documents[CORPS_42]["labels"] == [{"name": "enhancement"}]


def test_label_remove_ne_retire_rien_d_un_label_deja_absent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({CORPS_42: etiquetee("enhancement")})

    assert lance(forge, "label", "42", "--remove", "ready-for-agent") == 0
    assert retraits(forge) == []
    assert "rien à écrire" in capsys.readouterr().out


def test_label_remove_sort_en_1_si_la_relecture_porte_encore_le_label(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({CORPS_42: etiquetee("ready-for-agent")}, garde_les_labels=True)

    assert lance(forge, "label", "42", "--remove", "ready-for-agent") == 1
    assert "le label ready-for-agent est encore sur #42" in sortie_d_echec(
        capsys, "relecture non conforme"
    )


@pytest.mark.parametrize(
    ("corps", "debut"), [("Corps de la PR", "Corps de la PR"), (None, "")], ids=["corps", "null"]
)
def test_issue_edit_ajoute_le_fichier_en_fin_de_corps_octet_pour_octet(
    corps: str | None, debut: str, tmp_path: Path
) -> None:
    """Le fichier est lu en octets : ses CRLF partent tels quels — `read_text` les aurait
    traduits en LF (obs 87). Une ligne vide le sépare du corps, qui n'a pas de fin de ligne ; un
    corps `null` vaut le texte vide, jamais « None »."""
    ajout = tmp_path / "rattachement.md"
    ajout.write_bytes(b"*Rattachement a posteriori : lot 1/3.*\r\n\r\nCloses #7\r\n")
    forge = Forge({CORPS_42: {"body": corps}})

    assert lance(forge, "issue", "edit", "42", "--append", str(ajout)) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        f"{debut}\n\n*Rattachement a posteriori : lot 1/3.*\r\n\r\nCloses #7\r\n"
    ]


@pytest.mark.parametrize(
    ("contenu", "motif"),
    [
        ("été".encode("cp1252"), "n'est pas en UTF-8"),
        (b"\n  \r\n", "rien à ajouter"),
        (None, "fichier illisible"),
    ],
    ids=["non-utf-8", "sans-ligne-non-vide", "fichier-absent"],
)
def test_issue_edit_refuse_un_fichier_inutilisable_avant_tout_appel(
    contenu: bytes | None, motif: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ajout = tmp_path / "ajout.md"
    if contenu is not None:
        ajout.write_bytes(contenu)
    forge = Forge({CORPS_42: {"body": "Corps"}})

    assert lance(forge, "issue", "edit", "42", "--append", str(ajout)) == 1
    assert forge.appels == []
    assert motif in sortie_d_echec(capsys, "refus")


def test_issue_edit_sort_en_1_sur_une_relecture_tronquee(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ajout = tmp_path / "rattachement.md"
    ajout.write_bytes(b"\n*Rattachement a posteriori.*\n\nCloses #7\n")
    forge = Forge({CORPS_42: {"body": "Corps"}}, stocke=lambda corps: corps[:8])

    assert lance(forge, "issue", "edit", "42", "--append", str(ajout)) == 1
    sortie = sortie_d_echec(capsys, "relecture non conforme")
    assert "ancre absente : *Rattachement a posteriori.*" in sortie, sortie


# Chaque champ que l'appelant saisit, balayé en une passe pour la présence et la forme : le numéro
# entre dans un chemin d'API, l'ancre et le label dans une ligne de sortie.
APPELS_MAL_FORMES = {
    "sans-argument": (),
    "sous-commande-inconnue": ("comment", "42"),
    "action-manquante": ("checkbox", "42", "--case", "A"),
    "action-inconnue": ("brief", "edit", "42", "--case", "A"),
    "case-manquante": ("checkbox", "patch", "42"),
    "numero-manquant": ("checkbox", "patch", "--case", "A"),
    "numero-non-entier": ("checkbox", "patch", "quarante-deux", "--case", "A"),
    "chiffre-unicode": ("brief", "patch", "4²", "--case", "A"),
    "chemin-dans-le-numero": ("checkbox", "patch", "42/comments", "--case", "A"),
    "ancre-vide": ("checkbox", "patch", "42", "--case", " "),
    "ancre-sur-deux-lignes": ("brief", "patch", "42", "--case", "A\nB"),
    "ancre-a-retour-chariot": ("checkbox", "patch", "42", "--case", "A\rB"),
    "label-manquant": ("label", "42"),
    "label-vide": ("label", "42", "--remove", ""),
    "label-numero-non-entier": ("label", "#42", "--remove", "ready-for-agent"),
    "fichier-manquant": ("issue", "edit", "42"),
    "issue-numero-non-entier": ("issue", "edit", "4 2", "--append", "x.md"),
}


@pytest.mark.parametrize("args", APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys())
def test_un_appel_mal_forme_sort_en_2_sans_toucher_a_la_forge(
    args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: etiquetee("ready-for-agent")})

    assert lance(forge, *args) == 2
    assert forge.appels == []
    assert "usage" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("panne", "motif"),
    [
        (FileNotFoundError("gh introuvable"), "ne se lance pas"),
        (
            subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"HTTP 502\nBad Gateway\n"),
            "a échoué (1) : HTTP 502 Bad Gateway",
        ),
        (
            subprocess.CompletedProcess([], 0, stdout=b"<html>", stderr=b""),
            "ne rend pas du JSON UTF-8",
        ),
    ],
    ids=["gh-absent", "gh-en-echec", "reponse-non-json"],
)
def test_une_forge_en_panne_a_la_lecture_refuse_en_une_ligne(
    panne: Exception | subprocess.CompletedProcess[bytes],
    motif: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Une commande qui échoue, ne se lance pas ou ne rend pas du JSON n'est pas un corps lu."""

    def forge_en_panne(
        cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        if isinstance(panne, Exception):
            raise panne
        return panne

    assert ecriture_relue.main(["checkbox", "patch", "42", "--case", "A"], run=forge_en_panne) == 1
    assert motif in sortie_d_echec(capsys, "refus")


@pytest.mark.parametrize(
    ("args", "methode"),
    [
        (("checkbox", "patch", "42", "--case", "Critère A"), "PATCH"),
        (("label", "42", "--remove", "ready-for-agent"), "DELETE"),
    ],
    ids=["patch", "delete"],
)
def test_une_ecriture_en_panne_sort_en_1_sans_se_dire_refus(
    args: tuple[str, ...], methode: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """L'écriture a pu partir avant l'échec : « refus » ferait croire que rien n'est écrit."""
    forge = Forge(
        {CORPS_42: {"body": "- [ ] Critère A\n", "labels": [{"name": "ready-for-agent"}]}}
    )

    def forge_qui_tombe_a_l_ecriture(
        cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        if methode in cmd:
            return subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"HTTP 502")
        return forge(cmd, stdin)

    assert ecriture_relue.main(list(args), run=forge_qui_tombe_a_l_ecriture) == 1
    assert "a échoué (1) : HTTP 502" in sortie_d_echec(capsys, "relecture non conforme")


def test_le_lanceur_par_defaut_passe_l_entree_et_rend_les_octets_tels_quels() -> None:
    """Le défaut réel du lanceur, que la forge témoin remplace partout ailleurs : ni le mode texte
    ni la page de code de la console ne touchent ce qui entre ou sort (obs 87, 108)."""
    recopie = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"
    octets = "Critère A\r\n- [x] B\n".encode()

    assert ecriture_relue.default_run([sys.executable, "-c", recopie], octets).stdout == octets


@pytest.mark.parametrize(
    ("args", "code", "flux", "texte"),
    [
        (["--help"], 0, "stdout", "Écriture distante relue"),
        (["label", "x", "--remove", "a"], 2, "stderr", "numéro d'issue ou de PR attendu"),
    ],
    ids=["aide-sur-stdout", "usage-sur-stderr"],
)
def test_la_sortie_du_script_lance_en_tube_est_en_utf_8(
    args: list[str], code: int, flux: str, texte: str
) -> None:
    """La session lit le script par un tube. Sur ce poste, dont la page de code est cp1252, Python
    y écrit dans cet encodage (`pipeline.config.md`, « Qualité ») — l'erreur d'argparse comprise,
    qui part sur la sortie d'erreur. Sur un runner Linux, locale en UTF-8, supposé vert même sans
    le correctif — non mesuré."""
    script = REPOSITORY_ROOT / ".claude/skills/cycle-pr/scripts/ecriture-relue.py"
    done = subprocess.run([sys.executable, str(script), *args], capture_output=True, check=False)

    assert done.returncode == code
    assert texte in getattr(done, flux).decode("utf-8")
