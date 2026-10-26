"""Tests de la famille « écriture distante relue »
(`.claude/skills/cycle-pr/scripts/ecriture-relue.py`).

Le script écrit sur la forge puis relit en entier ce qu'il y a écrit : chaque cas éprouve l'une
des deux moitiés — ce qui part (la charge du `PATCH` ou du `POST`, lue sur l'entrée standard de
`gh`), ou ce que la relecture voit. Il parle à `gh` par une seule fonction, `run`, que ces tests
remplacent par une forge témoin : elle garde les documents en mémoire, applique chaque écriture
par la fonction `stocke` — l'identité, ou la transformation qu'un cas veut lui faire subir — et
ne répond qu'aux **commandes complètes** attendues, arguments compris ; toute autre lève. La vraie
forge n'est jamais appelée. Les cas s'écrivent en littéraux, jamais dérivés des constantes du
script (`cycle-pr` 3.1, « la table de cas est dérivée de l'artefact sous test »).
"""

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from command_doubles import json_success
from skill_scripts import load_script, run_in_pipe
from test_agent_skills import PLAN_QA_CASE_FORMS

ecriture_relue = load_script("cycle-pr", "ecriture-relue")

ISSUES = "repos/{owner}/{repo}/issues"
CORPS_42 = "repos/{owner}/{repo}/issues/42"
COMMENTAIRES_42 = "repos/{owner}/{repo}/issues/42/comments"
# Le commentaire 13, brief de l'issue 42 dans chaque forge qui en porte un.
BRIEF_DE_42 = "repos/{owner}/{repo}/issues/comments/13"
MILESTONES = "repos/{owner}/{repo}/milestones"
# Les listes que `gh api --paginate --slurp` lit, 100 par page — le maximum de l'API REST.
ISSUES_OUVERTES = "repos/{owner}/{repo}/issues?per_page=100"
LISTE_COMMENTAIRES_42 = "repos/{owner}/{repo}/issues/42/comments?per_page=100"
LABELS_DU_DEPOT = "repos/{owner}/{repo}/labels?per_page=100"
THEMES = "repos/{owner}/{repo}/milestones?state=all&per_page=100"
# Les seuls retraits de label auxquels la forge répond : chemin encodé → nom du label.
RETRAITS = {
    "repos/{owner}/{repo}/issues/42/labels/ready-for-agent": "ready-for-agent",
    "repos/{owner}/{repo}/issues/42/labels/Ready-for-agent": "Ready-for-agent",
    "repos/{owner}/{repo}/issues/42/labels/en%20attente": "en attente",
    "repos/{owner}/{repo}/issues/42/labels/zone%2Fapi": "zone/api",
    "repos/{owner}/{repo}/issues/42/labels/needs-triage": "needs-triage",
}


class Forge:
    """Une forge témoin : des documents en mémoire, chacun sous son chemin `gh api`.

    Args:
        documents: chemin → document JSON, tel que l'API REST le rend ; un `PATCH` y écrit chaque
            champ de sa charge.
        stocke: ce que la forge fait d'un corps reçu par `PATCH` avant de le garder — l'identité
            par défaut ; `None` vaut un corps effacé, que l'API rend `null`.
        pages: les commentaires de l'issue 42, page par page, tels que
            `gh api --paginate --slurp` les rend ; chacun est aussi un document sous son chemin
            `issues/comments/<id>`, le même objet — une écriture se voit donc dans la liste. Un
            commentaire publié par `POST` y entre sur une page de plus, gardé par `stocke`, sous
            l'`id` 900 + n pour le n-ième texte que la forge reçoit.
        issues: les issues ouvertes du dépôt, page par page, de même, chacune aussi sous son
            chemin `issues/<numéro>`. Une issue créée par `POST` y entre sur une page de plus, son
            corps gardé par `stocke`, sous le numéro 900 + n.
        labels_du_depot: les noms des labels du dépôt, page par page. Un label posé par `POST`
            s'ajoute à ceux de l'issue 42.
        milestones: les milestones du dépôt, page par page, de même, chacun aussi sous son chemin
            `milestones/<numéro>` ; un milestone créé par `POST` y entre sous le numéro 900 + n, et
            un `PATCH` `{"milestone": <numéro>}` pose sur l'issue le milestone de ce numéro.
        garde_les_labels: le retrait d'un label répond sans l'ôter de l'issue.
    """

    def __init__(
        self,
        documents: dict[str, dict[str, Any]],
        *,
        stocke: Callable[[str], str | None] = lambda corps: corps,
        pages: list[list[dict[str, Any]]] | None = None,
        issues: list[list[dict[str, Any]]] | None = None,
        labels_du_depot: list[list[str]] | None = None,
        milestones: list[list[dict[str, Any]]] | None = None,
        garde_les_labels: bool = False,
    ) -> None:
        self.documents = documents
        self.stocke = stocke
        self.garde_les_labels = garde_les_labels
        self.pages = pages or []
        for page in self.pages:
            for commentaire in page:
                self.indexe(commentaire)
        self.issues = issues or []
        self.milestones = milestones or []
        for chemin, liste in ((ISSUES, self.issues), (MILESTONES, self.milestones)):
            for page in liste:
                for document in page:
                    self.documents[f"{chemin}/{document['number']}"] = document
        # Chaque liste que `gh api --paginate --slurp` lit, sous son chemin.
        self.listes = {
            LISTE_COMMENTAIRES_42: self.pages,
            ISSUES_OUVERTES: self.issues,
            LABELS_DU_DEPOT: [[{"name": nom} for nom in page] for page in labels_du_depot or []],
            THEMES: self.milestones,
        }
        self.appels: list[tuple[str, ...]] = []
        self.charges: list[bytes] = []

    def indexe(self, commentaire: dict[str, Any]) -> None:
        """Rend `commentaire` lisible sous son chemin `issues/comments/<id>`."""
        chemin = f"repos/{{owner}}/{{repo}}/issues/comments/{commentaire['id']}"
        self.documents[chemin] = commentaire

    def __call__(
        self, cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        cmd = tuple(cmd)
        self.appels.append(cmd)
        match cmd:
            case ("gh", "api", chemin) if chemin in self.documents and stdin is None:
                return json_success(self.documents[chemin])
            case ("gh", "api", "-X", "PATCH", chemin, "--input", "-") if (
                chemin in self.documents and stdin is not None
            ):
                self.charges.append(stdin)
                charge = json.loads(stdin)
                self.documents[chemin].update(charge)
                if "body" in charge:
                    self.documents[chemin]["body"] = self.stocke(charge["body"])
                if "milestone" in charge:
                    milestone = self.documents[f"{MILESTONES}/{charge['milestone']}"]
                    self.documents[chemin]["milestone"] = milestone
                return json_success(self.documents[chemin])
            case ("gh", "api", "--paginate", "--slurp", chemin) if chemin in self.listes:
                return json_success(self.listes[chemin])
            case ("gh", "api", "-X", "POST", chemin, "--input", "-") if (
                chemin == ISSUES and stdin is not None
            ):
                self.charges.append(stdin)
                charge = json.loads(stdin)
                issue = {
                    "number": 900 + len(self.charges),
                    "title": charge["title"],
                    "body": self.stocke(charge["body"]),
                    "labels": [{"name": nom} for nom in charge["labels"]],
                }
                self.issues.append([issue])
                self.documents[f"{ISSUES}/{issue['number']}"] = issue
                return json_success(issue)
            case ("gh", "api", "-X", "POST", chemin, "--input", "-") if (
                chemin == COMMENTAIRES_42 and stdin is not None
            ):
                self.charges.append(stdin)
                corps = self.stocke(json.loads(stdin)["body"])
                commentaire = {"id": 900 + len(self.charges), "body": corps}
                self.pages.append([commentaire])
                self.indexe(commentaire)
                return json_success(commentaire)
            case ("gh", "api", "-X", "POST", chemin, "--input", "-") if (
                chemin == f"{CORPS_42}/labels" and stdin is not None
            ):
                self.charges.append(stdin)
                labels = self.documents[CORPS_42]["labels"]
                labels.extend({"name": nom} for nom in json.loads(stdin)["labels"])
                return json_success(labels)
            case ("gh", "api", "-X", "POST", chemin, "--input", "-") if (
                chemin == MILESTONES and stdin is not None
            ):
                self.charges.append(stdin)
                milestone = {
                    "number": 900 + len(self.charges),
                    **json.loads(stdin),
                    "open_issues": 0,
                }
                self.milestones.append([milestone])
                self.documents[f"{MILESTONES}/{milestone['number']}"] = milestone
                return json_success(milestone)
            case ("gh", "api", "-X", "DELETE", chemin) if chemin in RETRAITS and stdin is None:
                labels = self.documents[CORPS_42]["labels"]
                if not self.garde_les_labels:
                    labels[:] = [label for label in labels if label["name"] != RETRAITS[chemin]]
                return json_success(labels)
            case _:
                raise AssertionError(f"commande inattendue : {cmd}")


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
    # Cherchée après le marqueur : au rejeu, la case cochée ne porterait plus `- [ ] `.
    "ancre-qui-inclut-le-marqueur": (
        ("--case", "- [ ] Critère A"),
        "case introuvable : - [ ] Critère A",
    ),
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


def crlf(corps: str) -> str:
    """Une forge qui stocke le texte reçu avec ses fins de ligne converties LF → CRLF."""
    return corps.replace("\n", "\r\n")


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
        crlf,
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
    assert ("gh", "api", "-X", "PATCH", BRIEF_DE_42, "--input", "-") in forge.appels


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


def remplace(forge: Forge, tmp_path: Path, paires: str, texte: str = "checkbox") -> int:
    """`<texte> patch 42 --paires` d'un fichier de paires de ce contenu, écrit en octets UTF-8."""
    fichier = tmp_path / "paires.txt"
    fichier.write_bytes(paires.encode())
    return lance(forge, texte, "patch", "42", "--paires", str(fichier))


# Un plan de QA : un titre, trois cases, dont une citée.
PLAN = "## Phase 1\n\n- [ ] Critère A\n- [ ] Critère B\n> - [ ] Critère cité\n"

# Le recueil du format d'un fichier de paires, côté valide (obs 138) : (fichier, corps écrit quand
# on l'applique à `PLAN`). Une paire est une ligne ouverte par « < » puis une ligne ouverte par
# « > », chacun suivi d'un espace, sans échappement ; une ligne vide ou de blancs s'ignore, et
# chaque ligne du fichier perd son retour chariot final.
PAIRES_VALIDES = {
    "une-paire": (
        "< - [ ] Critère A\n> - [x] Critère A — passé, 2026-10-26\n",
        "## Phase 1\n\n- [x] Critère A — passé, 2026-10-26\n- [ ] Critère B\n> - [ ] Critère cité\n",
    ),
    "paires-separees-de-lignes-vides": (
        (
            "\n< - [ ] Critère A\n\n  \n> - [x] Critère A — N/A : hors périmètre\n\n"
            "< - [ ] Critère B\n> - [ ] Critère B — BLOQUÉ : base absente\n\n"
        ),
        (
            "## Phase 1\n\n- [x] Critère A — N/A : hors périmètre\n"
            "- [ ] Critère B — BLOQUÉ : base absente\n> - [ ] Critère cité\n"
        ),
    ),
    "fichier-crlf": (
        "< - [ ] Critère B\r\n> - [x] Critère B — passé\r\n",
        "## Phase 1\n\n- [ ] Critère A\n- [x] Critère B — passé\n> - [ ] Critère cité\n",
    ),
    "sans-fin-de-ligne-finale": (
        "< - [ ] Critère A\n> - [x] Critère A",
        "## Phase 1\n\n- [x] Critère A\n- [ ] Critère B\n> - [ ] Critère cité\n",
    ),
    "chevrons-sans-echappement": (
        "< > - [ ] Critère cité\n> > - [x] Critère cité — 3 < 4\n",
        "## Phase 1\n\n- [ ] Critère A\n- [ ] Critère B\n> - [x] Critère cité — 3 < 4\n",
    ),
}


@pytest.mark.parametrize(("paires", "corps"), PAIRES_VALIDES.values(), ids=PAIRES_VALIDES.keys())
def test_checkbox_patch_paires_remplace_chaque_ancienne_ligne_par_sa_nouvelle(
    paires: str, corps: str, tmp_path: Path
) -> None:
    """Le témoin positif, et l'ordre : lire, écrire, relire le corps entier."""
    forge = Forge({CORPS_42: {"body": PLAN}})

    assert remplace(forge, tmp_path, paires) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [corps]
    patch = ("gh", "api", "-X", "PATCH", CORPS_42, "--input", "-")
    assert forge.appels == [("gh", "api", CORPS_42), patch, ("gh", "api", CORPS_42)]


# Le recueil, côté refusé : (fichier, motif qui suit « refus — <fichier> : »). Chaque défaut porte
# le numéro de sa ligne dans le fichier, et tous sont nommés en une ligne.
PAIRES_REFUSEES = {
    "ligne-ni-vide-ni-paire": (
        "< - [ ] Critère A\n> - [x] Critère A\nnote libre\n",
        "ligne 3 : ni vide, ni « < … », ni « > … »",
    ),
    "chevrons-sans-espace": (
        "<- [ ] Critère A\n>- [x] Critère A\n",
        (
            "ligne 1 : ni vide, ni « < … », ni « > … » ; ligne 2 : ni vide, ni « < … », ni « > … »"
            " ; aucune paire dans le fichier"
        ),
    ),
    "ancienne-suivie-d-une-ancienne": (
        "< - [ ] Critère A\n< - [ ] Critère B\n> - [x] Critère B\n",
        "ligne 1 : « < » sans « > » qui le suit",
    ),
    "ancienne-en-fin-de-fichier": (
        "< - [ ] Critère A\n> - [x] Critère A\n< - [ ] Critère B\n",
        "ligne 3 : « < » sans « > » qui le suit",
    ),
    "nouvelle-sans-ancienne": (
        "< - [ ] Critère A\n> - [x] Critère A\n> - [x] Critère B\n",
        "ligne 3 : « > » sans « < » qui le précède",
    ),
    "ancienne-vide": ("< \n> - [x] Critère A\n", "ligne 1 : ancienne ligne vide"),
    "nouvelle-de-blancs": ("< - [ ] Critère A\n>    \n", "ligne 2 : nouvelle ligne vide"),
    "paire-sans-changement": (
        "< - [ ] Critère A\n> - [ ] Critère A\n",
        "ligne 1 : ancienne et nouvelle lignes égales",
    ),
    "meme-ancienne-deux-fois": (
        "< - [ ] Critère A\n> - [x] Critère A\n< - [ ] Critère A\n> - [x] Critère A — passé\n",
        "ligne 3 : ancienne ligne déjà nommée ligne 1",
    ),
    "meme-nouvelle-deux-fois": (
        "< - [ ] Critère A\n> - [x] Critère\n< - [ ] Critère B\n> - [x] Critère\n",
        "ligne 4 : nouvelle ligne déjà nommée ligne 2",
    ),
    # Chaînées, les paires casseraient le rejeu : la nouvelle ligne de l'une y serait remplacée
    # par l'autre.
    "ancienne-qui-est-une-nouvelle-plus-haut": (
        "< - [ ] Critère A\n> - [x] Critère A\n< - [x] Critère A\n> - [x] Critère A — passé\n",
        "ligne 3 : ancienne ligne qui est la nouvelle de la ligne 2",
    ),
    "nouvelle-qui-est-une-ancienne-plus-haut": (
        "< - [x] Critère A\n> - [x] Critère A — passé\n< - [ ] Critère A\n> - [x] Critère A\n",
        "ligne 4 : nouvelle ligne qui est l'ancienne de la ligne 1",
    ),
    "fichier-vide": ("", "aucune paire dans le fichier"),
    "lignes-de-blancs-seules": ("\n  \r\n", "aucune paire dans le fichier"),
    "tous-nommes-dans-l-ordre-du-fichier": (
        "note libre\n< - [ ] Critère A\n> - [ ] Critère A\n> - [x] Critère B\n",
        (
            "ligne 1 : ni vide, ni « < … », ni « > … » ; ligne 2 : ancienne et nouvelle lignes"
            " égales ; ligne 4 : « > » sans « < » qui le précède"
        ),
    ),
}


@pytest.mark.parametrize(("paires", "motif"), PAIRES_REFUSEES.values(), ids=PAIRES_REFUSEES.keys())
def test_un_fichier_de_paires_mal_forme_est_refuse_avant_tout_appel(
    paires: str, motif: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: {"body": PLAN}})

    assert remplace(forge, tmp_path, paires) == 1
    assert forge.appels == []
    assert sortie_d_echec(capsys, "refus") == f"refus — {tmp_path / 'paires.txt'} : {motif}"


@pytest.mark.parametrize(
    ("contenu", "motif"),
    [("été".encode("cp1252"), "{fichier} n'est pas en UTF-8"), (None, "fichier illisible")],
    ids=["non-utf-8", "fichier-absent"],
)
def test_un_fichier_de_paires_illisible_est_refuse_avant_tout_appel(
    contenu: bytes | None, motif: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fichier = tmp_path / "paires.txt"
    if contenu is not None:
        fichier.write_bytes(contenu)
    forge = Forge({CORPS_42: {"body": PLAN}})

    assert lance(forge, "checkbox", "patch", "42", "--paires", str(fichier)) == 1
    assert forge.appels == []
    assert sortie_d_echec(capsys, "refus").startswith(f"refus — {motif.format(fichier=fichier)}")


def test_checkbox_patch_paires_garde_le_retour_chariot_de_chaque_ligne_remplacee(
    tmp_path: Path,
) -> None:
    """Une ligne du corps se compare sans son retour chariot final, qui reste à l'écriture : les
    fins de ligne ressortent telles qu'elles sont entrées, ligne par ligne (obs 87, 106)."""
    forge = Forge({CORPS_42: {"body": "Intro\r\n- [ ] Critère A\n- [ ] Critère B\r\n"}})
    paires = "< - [ ] Critère A\n> - [x] Critère A — passé\n< - [ ] Critère B\n> - [x] Critère B\n"

    assert remplace(forge, tmp_path, paires) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        "Intro\r\n- [x] Critère A — passé\n- [x] Critère B\r\n"
    ]


@pytest.mark.parametrize(
    ("corps", "ecrit", "sortie"),
    [
        (
            "- [x] Critère A — passé\n- [ ] Critère B\n",
            ["- [x] Critère A — passé\n- [x] Critère B — passé\n"],
            (
                "déjà appliquée : - [ ] Critère A\n"
                "écrit et relu — corps de #42 : 1 ligne(s) remplacée(s)\n"
            ),
        ),
        (
            "- [x] Critère A — passé\n- [x] Critère B — passé\n",
            [],
            (
                "déjà appliquée : - [ ] Critère A\ndéjà appliquée : - [ ] Critère B\n"
                "rien à écrire — corps de #42 : toutes les paires déjà appliquées\n"
            ),
        ),
    ],
    ids=["une-neuve-une-deja-appliquee", "toutes-deja-appliquees"],
)
def test_une_paire_deja_appliquee_ne_se_reecrit_pas_et_le_dit(
    corps: str, ecrit: list[str], sortie: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le rejeu d'un fichier déjà poussé n'écrit rien : l'ancienne ligne absente et la nouvelle
    seule dans le corps, la paire est déjà appliquée."""
    forge = Forge({CORPS_42: {"body": corps}})
    paires = (
        "< - [ ] Critère A\n> - [x] Critère A — passé\n"
        "< - [ ] Critère B\n> - [x] Critère B — passé\n"
    )

    assert remplace(forge, tmp_path, paires) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == ecrit
    assert capsys.readouterr().out == sortie


# Un plan où chaque refus d'application trouve sa ligne : une ligne proche de l'ancienne, une
# ancienne en double, une nouvelle en double, et une case qu'une paire valide remplacerait.
CORPS_EDITE = (
    "## Phase 1\n\n"
    "- [ ] L'utilisateur A liste ses ressources\n"
    "- [ ] Le service répond\n"
    "- [ ] Le service répond\n"
    "- [x] La console reste propre\n"
    "- [x] La console reste propre\n"
    "- [ ] Le bouton se désactive\n"
)

# Une paire qui ne s'applique pas au corps lu : (fichier, motif exact). Tout ou rien — rien n'est
# écrit, même quand d'autres paires s'appliquaient, et chaque paire en défaut est nommée.
REFUS_D_APPLICATION = {
    "ligne-introuvable-la-plus-proche-nommee": (
        "< - [ ] L'utilisateur A liste ses propres ressources\n> - [x] Liste — 200\n",
        (
            "ligne introuvable : - [ ] L'utilisateur A liste ses propres ressources"
            " (la plus proche : - [ ] L'utilisateur A liste ses ressources)"
        ),
    ),
    "ligne-introuvable-sans-ligne-proche": (
        "< Rien de commun, zzz\n> Rien\n",
        "ligne introuvable : Rien de commun, zzz (aucune ligne proche)",
    ),
    "ancienne-en-double": (
        "< - [ ] Le service répond\n> - [x] Le service répond\n",
        "ligne en double (2) : - [ ] Le service répond",
    ),
    "nouvelle-en-double": (
        "< - [ ] La console reste propre\n> - [x] La console reste propre\n",
        "ligne en double (2) : - [x] La console reste propre",
    ),
    "un-refus-parmi-des-paires-valides": (
        (
            "< - [ ] Le bouton se désactive\n> - [x] Le bouton se désactive\n"
            "< Rien de commun, zzz\n> Rien\n"
        ),
        "ligne introuvable : Rien de commun, zzz (aucune ligne proche)",
    ),
    "deux-refus-tous-deux-nommes": (
        "< Rien de commun, zzz\n> Rien\n< - [ ] Le service répond\n> - [x] Le service répond\n",
        (
            "ligne introuvable : Rien de commun, zzz (aucune ligne proche)"
            " ; ligne en double (2) : - [ ] Le service répond"
        ),
    ),
}


@pytest.mark.parametrize(
    ("paires", "motif"), REFUS_D_APPLICATION.values(), ids=REFUS_D_APPLICATION.keys()
)
def test_une_paire_qui_ne_s_applique_pas_refuse_tout_l_appel_sans_rien_ecrire(
    paires: str, motif: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: {"body": CORPS_EDITE}})

    assert remplace(forge, tmp_path, paires) == 1
    assert forge.charges == [], "un PATCH est parti malgré le refus"
    assert sortie_d_echec(capsys, "refus") == f"refus — {motif}"


def test_une_paire_dont_la_nouvelle_ligne_existe_deja_s_applique_puis_son_rejeu_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Borne du contrat de `--paires` : la nouvelle ligne déjà ailleurs dans le corps, la paire
    s'applique — l'ancienne est seule —, mais le rejeu y trouve la nouvelle en double et refuse
    au lieu de la dire déjà appliquée ; il n'écrit pas une seconde fois."""
    forge = Forge({CORPS_42: {"body": "- [ ] Critère A\n- [x] Critère A\n"}})
    paires = "< - [ ] Critère A\n> - [x] Critère A\n"

    assert remplace(forge, tmp_path, paires) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        "- [x] Critère A\n- [x] Critère A\n"
    ]
    capsys.readouterr()

    assert remplace(forge, tmp_path, paires) == 1
    assert len(forge.charges) == 1, "le rejeu a écrit une seconde fois"
    assert sortie_d_echec(capsys, "refus") == "refus — ligne en double (2) : - [x] Critère A"


def test_brief_patch_paires_remplace_dans_le_commentaire_de_brief(tmp_path: Path) -> None:
    """Le brief est le seul commentaire ouvert par `## Brief d'agent` : ni la citation qui le
    nomme, ni le corps de l'issue ne sont touchés."""
    pages = [[CITATION], [{"id": 13, "body": BRIEF}]]
    forge = Forge({CORPS_42: {"body": "- [ ] Critère A\n"}}, pages=pages)

    assert remplace(forge, tmp_path, "< - [ ] Critère A\n> - [x] Critère A — fait\n", "brief") == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        "## Brief d'agent\n\n**Critères d'acceptation :**\n- [x] Critère A — fait\n- [ ] Critère B\n"
    ]
    assert ecritures(forge) == [("gh", "api", "-X", "PATCH", BRIEF_DE_42, "--input", "-")]


def test_checkbox_patch_paires_sort_en_1_si_la_ligne_ecrite_manque_a_la_relecture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """La relecture cherche chaque nouvelle ligne écrite, et compare le corps entier."""
    forge = Forge(
        {CORPS_42: {"body": "- [ ] Critère A\n- [ ] Critère B\n"}},
        stocke=lambda corps: corps.replace("- [x] Critère A — passé\n", ""),
    )

    assert remplace(forge, tmp_path, "< - [ ] Critère A\n> - [x] Critère A — passé\n") == 1
    ecart = (
        "ancre absente : - [x] Critère A — passé ; attendu 45 octets et 0 \\r,"
        " relu 17 octets et 0 \\r"
    )
    assert capsys.readouterr().out == f"relecture non conforme — {ecart}\n"


# Les états d'une ligne de case de plan de QA (`execution-qa/SKILL.md` §3, §4, §6 et « Passe
# finale », et `execution-qa/references/standard-correction-bug.md`, étape 10), population
# entière, faux positifs compris (obs 138) : (ligne, en attente). Une case laissée `[ ]` n'attend
# plus quand sa ligne porte un échec (`🔴`), un blocage (` — BLOQUÉ`) ou une acceptation
# (` — accepté`) — une annotation de §3, étape 4, s'écrit ` — <marque>` ; « bloqué », « BLOQUÉ »
# ou « accepté » dans le texte d'une case n'en est pas une.
ETATS_DE_CASE = {
    "nue": ("- [ ] Le service répond", True),
    "passee": ("- [x] Le service répond — 200, 2026-10-26", False),
    "cochee-en-majuscule": ("- [X] Le service répond", False),
    "passee-avec-decision": ("- [x] Le tri — Décision : par date, 2026-10-26", False),
    "non-applicable": ("- [x] L'export — N/A : hors périmètre", False),
    "corrigee-en-session": ("- [x] L'envoi — corrigé en session, 9b3153f, 2026-10-26", False),
    "bloquee": ("- [ ] La sauvegarde — BLOQUÉ : base absente", False),
    "en-echec": ("- [ ] L'envoi 🔴 needs-issue — 500 au POST", False),
    "bug-depose": ("- [ ] L'envoi 🔴 BUG #12", False),
    "bloque-dans-le-texte": ("- [ ] Le bouton est bloqué pendant l'envoi", True),
    "bloque-en-majuscules-dans-le-texte": ("- [ ] Le badge BLOQUÉ s'affiche", True),
    "acceptee": ("- [ ] La purge — accepté : purge manuelle, 2026-10-26", False),
    "accepte-dans-le-texte": ("- [ ] **Commande** — `curl -X POST $API/jobs` → 201 accepté", True),
    # Un blanc entre les crochets, une tabulation comprise, vaut non coché (GFM §5.3).
    "tabulation-entre-crochets": ("- [\t] Le service répond", True),
}


@pytest.mark.parametrize(("ligne", "en_attente"), ETATS_DE_CASE.values(), ids=ETATS_DE_CASE.keys())
def test_checkbox_next_rend_la_case_en_attente_sans_rien_ecrire(
    ligne: str, en_attente: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: {"body": f"## Phase 1\n\n{ligne}\n"}})

    assert lance(forge, "checkbox", "next", "42") == 0
    assert forge.appels == [("gh", "api", CORPS_42)]
    sortie = f"Phase 1\n{ligne}\n" if en_attente else "aucune case en attente — corps de #42\n"
    assert capsys.readouterr().out == sortie


@pytest.mark.parametrize(
    ("corps", "sortie"),
    [
        (
            "# Plan\n\n## Phase 0\n- [x] A — ok\n\n## Phase 1\n### Bloc #12 — envoi\n- [ ] B\n- [ ] C\n",
            "Bloc #12 — envoi\n- [ ] B\n",
        ),
        ("Intro\n- [ ] B\n## Phase 2\n", "(sans titre)\n- [ ] B\n"),
        ("## Phase 1\r\n\r\n  - [ ] B\r\n", "Phase 1\n  - [ ] B\n"),
    ],
    ids=["dernier-titre-au-dessus", "sans-titre-au-dessus", "corps-crlf"],
)
def test_checkbox_next_rend_le_dernier_titre_au_dessus_de_la_case(
    corps: str, sortie: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """La première case en attente, sous le dernier titre qui la précède, rendu sans ses `#` ; un
    titre plus bas ne compte pas, et aucun retour chariot ne ressort (obs 87, 106)."""
    forge = Forge({CORPS_42: {"body": corps}})

    assert lance(forge, "checkbox", "next", "42") == 0
    assert capsys.readouterr().out == sortie


@pytest.mark.parametrize(
    ("ligne", "est_une_case"),
    [(ligne, est_une_case) for ligne, est_une_case, _ in PLAN_QA_CASE_FORMS.values()],
    ids=PLAN_QA_CASE_FORMS.keys(),
)
def test_checkbox_next_reconnait_les_cases_du_plan_de_qa(ligne: str, est_une_case: bool) -> None:
    """D'accord avec `PLAN_QA_CASE` (`test_agent_skills.py`, lot 7a) sur son recueil, des deux
    côtés : une case que `plan-qa` écrit est une case que `next` voit, et rien d'autre."""
    assert bool(ecriture_relue.PLAN_CASE.match(ligne)) is est_une_case


def ecrit_brief(forge: Forge, tmp_path: Path, contenu: str) -> int:
    """`brief write 42` d'un fichier de ce contenu, écrit en octets UTF-8."""
    brief = tmp_path / "brief.md"
    brief.write_bytes(contenu.encode())
    return lance(forge, "brief", "write", "42", "--body-file", str(brief))


NOUVEAU_BRIEF = "## Brief d'agent\r\n\r\n- [ ] Critère révisé\r\n"


@pytest.mark.parametrize(
    ("pages", "ecriture", "sortie"),
    [
        (
            [[CITATION]],
            ("POST", COMMENTAIRES_42),
            "publié et relu — brief de #42 : commentaire 901",
        ),
        (
            [[CITATION], [{"id": 13, "body": BRIEF}]],
            ("PATCH", BRIEF_DE_42),
            "écrit et relu — brief de #42 : remplacé par {fichier}",
        ),
    ],
    ids=["publie-le-premier", "edite-en-place"],
)
def test_brief_write_publie_le_brief_ou_edite_en_place_celui_qui_existe(
    pages: list[list[dict[str, Any]]],
    ecriture: tuple[str, str],
    sortie: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sans brief, il est publié puis relu sous l'`id` rendu ; avec un, il est édité en place —
    jamais un second brief concurrent. Une citation qui le nomme plus loin n'en est pas un."""
    forge = Forge({}, pages=pages)

    assert ecrit_brief(forge, tmp_path, NOUVEAU_BRIEF) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [NOUVEAU_BRIEF]
    assert ecritures(forge) == [("gh", "api", "-X", *ecriture, "--input", "-")]
    sortie = sortie.format(fichier=tmp_path / "brief.md")
    assert capsys.readouterr().out == f"{sortie}\n"


@pytest.mark.parametrize(
    ("contenu", "pages", "lectures", "motif"),
    [
        ("Brief d'agent\n", [], 0, "{fichier} ne s'ouvre pas par ## Brief d'agent"),
        ("\n## Brief d'agent\n", [], 0, "{fichier} ne s'ouvre pas par ## Brief d'agent"),
        (
            "## Brief d'agent\n",
            [[{"id": 13, "body": BRIEF}], [{"id": 14, "body": BRIEF}]],
            1,
            "2 commentaires de brief sur #42 : aucun ne s'édite en place",
        ),
    ],
    ids=["sans-marque", "marque-apres-une-ligne-vide", "deux-briefs"],
)
def test_brief_write_refuse_sans_rien_ecrire(
    contenu: str,
    pages: list[list[dict[str, Any]]],
    lectures: int,
    motif: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un fichier qui ne s'ouvre pas par la marque, même après une ligne vide, ne serait plus
    reconnu par `brief patch` : refusé avant tout appel. Plusieurs briefs : `brief-agent.md` veut
    l'édition en place, « jamais un second brief concurrent »."""
    forge = Forge({}, pages=pages)

    assert ecrit_brief(forge, tmp_path, contenu) == 1
    assert len(forge.appels) == lectures
    assert ecritures(forge) == []
    assert motif.format(fichier=tmp_path / "brief.md") in sortie_d_echec(capsys, "refus")


@pytest.mark.parametrize("pages", [[], [[{"id": 13, "body": BRIEF}]]], ids=["publie", "edite"])
def test_brief_write_sort_en_1_si_le_brief_relu_n_est_pas_le_fichier(
    pages: list[list[dict[str, Any]]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({}, pages=pages, stocke=crlf)

    assert ecrit_brief(forge, tmp_path, "## Brief d'agent\n\nCritère.\n") == 1
    ecart = "attendu 28 octets et 0 \\r, relu 31 octets et 3 \\r"
    assert capsys.readouterr().out == f"relecture non conforme — {ecart}\n"


def etiquetee(*noms: str) -> dict[str, Any]:
    """Une issue qui porte ces labels, sous la forme que l'API REST les rend."""
    return {"body": "", "labels": [{"name": nom} for nom in noms]}


def ecritures(forge: Forge) -> list[tuple[str, ...]]:
    """Les écritures que la forge a reçues — `PATCH` ou `DELETE`, tout appel `-X`."""
    return [appel for appel in forge.appels if "-X" in appel]


def relue_autrement(
    forge: Forge, chemin: str, retouche: Callable[[Any], Any]
) -> Callable[[Sequence[str], bytes | None], subprocess.CompletedProcess[bytes]]:
    """La forge, sauf la lecture de `chemin` après une écriture — la relecture —, que `retouche`
    transforme : la forge ne garde pas ce qu'on lui a écrit."""

    def forge_qui_relit_autre_chose(
        cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        rendu = forge(cmd, stdin)
        if ecritures(forge) and tuple(cmd) == ("gh", "api", chemin):
            return json_success(retouche(json.loads(rendu.stdout)))
        return rendu

    return forge_qui_relit_autre_chose


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
    assert len(ecritures(forge)) == 1
    assert forge.appels[-1] == ("gh", "api", CORPS_42), "le retrait n'est pas relu"
    assert forge.documents[CORPS_42]["labels"] == [{"name": "enhancement"}]


@pytest.mark.parametrize(
    ("portes", "retire"),
    [
        (("ready-for-agent", "enhancement"), "ready-for-agent"),
        (("ready-for-agent", "Ready-for-agent"), "Ready-for-agent"),
    ],
    ids=["casse-differente", "nom-exact-d-abord"],
)
def test_label_remove_apparie_sans_la_casse_et_retire_le_nom_que_l_issue_porte(
    portes: tuple[str, ...], retire: str
) -> None:
    """`--remove Ready-for-agent` désigne le `ready-for-agent` que l'issue porte, et le `DELETE`
    part sous ce nom-là : rien ne dit la forge insensible à la casse. Un label du nom exact passe
    avant un homonyme de casse — le `DELETE` attendu se compare chemin compris."""
    forge = Forge({CORPS_42: etiquetee(*portes)})

    assert lance(forge, "label", "42", "--remove", "Ready-for-agent") == 0
    assert ecritures(forge) == [("gh", "api", "-X", "DELETE", f"{CORPS_42}/labels/{retire}")]
    assert {"name": retire} not in forge.documents[CORPS_42]["labels"]


def test_label_remove_ne_retire_rien_d_un_label_deja_absent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({CORPS_42: etiquetee("enhancement")})

    assert lance(forge, "label", "42", "--remove", "ready-for-agent") == 0
    assert ecritures(forge) == []
    assert "rien à écrire" in capsys.readouterr().out


@pytest.mark.parametrize("argument", ["ready-for-agent", "Ready-for-agent"], ids=["exact", "casse"])
def test_label_remove_sort_en_1_si_la_relecture_porte_encore_le_label(
    argument: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """La relecture cherche le nom que l'issue porte, pas celui de l'argument."""
    forge = Forge({CORPS_42: etiquetee("ready-for-agent")}, garde_les_labels=True)

    assert lance(forge, "label", "42", "--remove", argument) == 1
    assert "le label ready-for-agent est encore sur #42" in sortie_d_echec(
        capsys, "relecture non conforme"
    )


TRANSITION = ("label", "42", "--remove", "needs-triage", "--add", "needs-interrogation")


def test_label_fait_une_transition_d_etat_en_un_appel_puis_relit_les_labels(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le témoin positif, et l'ordre : le label à poser se valide contre le dépôt, se pose
    **avant** le retrait — l'issue ne reste jamais sans label d'état, même un instant —, puis les
    labels de l'issue se relisent une fois."""
    forge = Forge(
        {CORPS_42: etiquetee("needs-triage", "enhancement")},
        labels_du_depot=[["needs-triage", "needs-interrogation"]],
    )

    assert lance(forge, *TRANSITION) == 0
    assert forge.appels == [
        ("gh", "api", "--paginate", "--slurp", LABELS_DU_DEPOT),
        ("gh", "api", CORPS_42),
        ("gh", "api", "-X", "POST", f"{CORPS_42}/labels", "--input", "-"),
        ("gh", "api", "-X", "DELETE", f"{CORPS_42}/labels/needs-triage"),
        ("gh", "api", CORPS_42),
    ]
    assert [json.loads(charge) for charge in forge.charges] == [{"labels": ["needs-interrogation"]}]
    assert forge.documents[CORPS_42]["labels"] == [
        {"name": "enhancement"},
        {"name": "needs-interrogation"},
    ]
    assert capsys.readouterr().out == (
        "écrit et relu — labels de #42 : ajouté needs-interrogation ; retiré needs-triage\n"
    )


def test_label_add_pose_le_nom_que_le_depot_donne_au_label() -> None:
    """`--add Needs-Info` désigne le `needs-info` que le dépôt porte sur sa seconde page, comme le
    `--label` d'`issue create`."""
    forge = Forge({CORPS_42: etiquetee()}, labels_du_depot=[["bug"], ["needs-info"]])

    assert lance(forge, "label", "42", "--add", "Needs-Info") == 0
    assert [json.loads(charge) for charge in forge.charges] == [{"labels": ["needs-info"]}]


def test_label_add_refuse_un_label_inconnu_du_depot_sans_rien_ecrire(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Chaque label inconnu est nommé, et rien ne part — pas même le retrait demandé dans le même
    appel."""
    forge = Forge({CORPS_42: etiquetee("needs-triage")}, labels_du_depot=[["needs-triage"]])

    args = ("label", "42", "--remove", "needs-triage", "--add", "bogue", "--add", "zone/api")
    assert lance(forge, *args) == 1
    assert ecritures(forge) == []
    assert "label inconnu du dépôt : bogue ; label inconnu du dépôt : zone/api" in sortie_d_echec(
        capsys, "refus"
    )


def test_label_n_ecrit_rien_quand_la_transition_est_deja_faite(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge(
        {CORPS_42: etiquetee("needs-interrogation")},
        labels_du_depot=[["needs-triage", "needs-interrogation"]],
    )

    assert lance(forge, *TRANSITION) == 0
    assert ecritures(forge) == []
    assert capsys.readouterr().out == (
        "rien à écrire — labels de #42 : needs-interrogation déjà posé ; needs-triage déjà absent\n"
    )


@pytest.mark.parametrize(
    ("corps", "avant_l_ajout"),
    [
        ("Corps de la PR", "Corps de la PR\n\n"),
        ("Corps de la PR\n", "Corps de la PR\n\n"),
        ("Corps de la PR\r\n\r\n", "Corps de la PR\r\n\r\n"),
        ("Corps de la PR\n\n\n", "Corps de la PR\n\n\n"),
        (None, ""),
    ],
    ids=["sans-fin-de-ligne", "fin-de-ligne", "ligne-vide-deja-la-crlf", "vides-gardees", "null"],
)
def test_issue_edit_ajoute_le_fichier_en_fin_de_corps_octet_pour_octet(
    corps: str | None, avant_l_ajout: str, tmp_path: Path
) -> None:
    """Le fichier est lu en octets : ses CRLF partent tels quels — `read_text` les aurait
    traduits en LF (obs 87). Une ligne vide au moins le sépare du dernier contenu du corps : les
    fins de ligne qui terminent déjà le corps comptent, CRLF compris, et aucune n'est retirée. Un
    corps `null` vaut le texte vide — ni « None », ni séparateur."""
    ajout = tmp_path / "rattachement.md"
    ajout.write_bytes(b"*Rattachement a posteriori : lot 1/3.*\r\n\r\nCloses #7\r\n")
    forge = Forge({CORPS_42: {"body": corps}})

    assert lance(forge, "issue", "edit", "42", "--append", str(ajout)) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        f"{avant_l_ajout}*Rattachement a posteriori : lot 1/3.*\r\n\r\nCloses #7\r\n"
    ]


@pytest.mark.parametrize(
    "appel",
    [
        ("issue", "edit", "42", "--append"),
        ("comment", "42", "--body-file"),
        ("issue", "create", "--title", "Titre", "--body-file"),
        ("issue", "edit", "42", "--body-file"),
        ("brief", "write", "42", "--body-file"),
    ],
    ids=["issue-edit-append", "comment", "issue-create", "issue-edit-body-file", "brief-write"],
)
@pytest.mark.parametrize(
    ("contenu", "motif"),
    [
        ("été".encode("cp1252"), "{fichier} n'est pas en UTF-8"),
        (b"\n  \r\n", "{fichier} n'a aucune ligne non vide"),
        (None, "fichier illisible"),
    ],
    ids=["non-utf-8", "sans-ligne-non-vide", "fichier-absent"],
)
def test_un_fichier_inutilisable_est_refuse_avant_tout_appel(
    appel: tuple[str, ...],
    contenu: bytes | None,
    motif: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le motif ouvre la ligne de refus. Les sous-commandes qui lisent un fichier en partagent la
    lecture : son motif ne nomme l'action d'aucune — « rien à ajouter » était faux pour `comment`
    (vu rouge par mutation)."""
    ajout = tmp_path / "ajout.md"
    if contenu is not None:
        ajout.write_bytes(contenu)
    forge = Forge({CORPS_42: {"body": "Corps"}})

    assert lance(forge, *appel, str(ajout)) == 1
    assert forge.appels == []
    assert sortie_d_echec(capsys, "refus").startswith(f"refus — {motif.format(fichier=ajout)}")


@pytest.mark.parametrize("option", ["--append", "--body-file"])
def test_issue_edit_sort_en_1_sur_une_relecture_tronquee(
    option: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ajout = tmp_path / "rattachement.md"
    ajout.write_bytes(b"\n*Rattachement a posteriori.*\n\nCloses #7\n")
    forge = Forge({CORPS_42: {"body": "Corps"}}, stocke=lambda corps: corps[:8])

    assert lance(forge, "issue", "edit", "42", option, str(ajout)) == 1
    sortie = sortie_d_echec(capsys, "relecture non conforme")
    assert "ancre absente : *Rattachement a posteriori.*" in sortie, sortie


def test_issue_edit_body_file_remplace_le_corps_entier_octet_pour_octet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lire, écrire, relire : le fichier devient le corps entier, CRLF et accents compris."""
    corps = tmp_path / "corps.md"
    corps.write_bytes("## Brief révisé\r\n\r\n- [ ] Critère A\r\n".encode())
    forge = Forge({CORPS_42: {"body": "Ancien corps\n- [x] Critère A\n"}})

    assert lance(forge, "issue", "edit", "42", "--body-file", str(corps)) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        "## Brief révisé\r\n\r\n- [ ] Critère A\r\n"
    ]
    patch = ("gh", "api", "-X", "PATCH", CORPS_42, "--input", "-")
    assert forge.appels == [("gh", "api", CORPS_42), patch, ("gh", "api", CORPS_42)]
    assert capsys.readouterr().out == f"écrit et relu — corps de #42 : remplacé par {corps}\n"


def test_comment_publie_le_fichier_octet_pour_octet_puis_relit_le_commentaire_publie(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le témoin positif, et l'ordre : lire les commentaires, publier, relire le commentaire sous
    l'`id` que rend la publication. Le fichier part tel qu'il est lu en octets — accents, CRLF —,
    et un autre commentaire déjà là ne compte pas pour un rejeu."""
    signalement = tmp_path / "signalement.md"
    signalement.write_bytes("> *Généré par IA — répercussion.*\r\n\r\n**Bloquant**\r\n".encode())
    forge = Forge({}, pages=[[{"id": 11, "body": "Un autre commentaire"}]])

    assert lance(forge, "comment", "42", "--body-file", str(signalement)) == 0
    assert [json.loads(charge)["body"] for charge in forge.charges] == [
        "> *Généré par IA — répercussion.*\r\n\r\n**Bloquant**\r\n"
    ]
    assert forge.appels == [
        ("gh", "api", "--paginate", "--slurp", LISTE_COMMENTAIRES_42),
        ("gh", "api", "-X", "POST", COMMENTAIRES_42, "--input", "-"),
        ("gh", "api", "repos/{owner}/{repo}/issues/comments/901"),
    ]
    assert capsys.readouterr().out == "publié et relu — commentaire 901 sur #42\n"


# Ce que la forge garde du commentaire publié, quand ce n'est pas le fichier : (stockage, écart
# **exact** que la sortie en dit).
COMMENTAIRES_RELUS_NON_CONFORMES: dict[str, tuple[Callable[[str], str], str]] = {
    "lf-converti-en-crlf": (crlf, "attendu 39 octets et 0 \\r, relu 43 octets et 4 \\r"),
    "tronque": (
        lambda corps: corps[:9],
        (
            "ancre absente : **Répercussion bloquante** ; attendu 39 octets et 0 \\r, "
            "relu 10 octets et 0 \\r"
        ),
    ),
}


@pytest.mark.parametrize(
    ("stocke", "ecart"),
    COMMENTAIRES_RELUS_NON_CONFORMES.values(),
    ids=COMMENTAIRES_RELUS_NON_CONFORMES.keys(),
)
def test_comment_sort_en_1_si_le_commentaire_relu_n_est_pas_le_fichier(
    stocke: Callable[[str], str], ecart: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le commentaire relu se compare au fichier entier : une conversion des fins de ligne garde
    l'ancre et se voit aux octets et aux `\\r` (obs 106) ; une troncature nomme l'ancre perdue."""
    signalement = tmp_path / "signalement.md"
    signalement.write_bytes("\n**Répercussion bloquante**\n\nDétail.\n".encode())
    forge = Forge({}, stocke=stocke)

    assert lance(forge, "comment", "42", "--body-file", str(signalement)) == 1
    assert capsys.readouterr().out == f"relecture non conforme — {ecart}\n"


PROBLEME = "## Problème\r\n\r\nLa file déborde.\r\n"


def creation(tmp_path: Path, *labels: str, titre: str = "Titre") -> list[str]:
    """L'appel `issue create` titré `titre`, un `--label` par label, d'un corps `PROBLEME` écrit
    en octets — CRLF et accents."""
    corps = tmp_path / "prd.md"
    corps.write_bytes(PROBLEME.encode())
    options = [option for label in labels for option in ("--label", label)]
    return ["issue", "create", "--title", titre, "--body-file", str(corps), *options]


def test_issue_create_cree_l_issue_et_ses_labels_en_une_requete_puis_la_relit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le témoin positif, et l'ordre : lire les labels du dépôt et les issues ouvertes, créer,
    relire l'issue sous le numéro que rend la création. Titre, corps et labels partent dans la
    **même** requête — un PRD n'existe jamais sans son label —, le fichier tel qu'il est lu en
    octets ; le numéro se lit sur la ligne de sortie."""
    forge = Forge({}, labels_du_depot=[["prd", "enhancement", "bug"]])

    assert lance(forge, *creation(tmp_path, "prd", "enhancement", titre="Réécrire la file")) == 0
    assert [json.loads(charge) for charge in forge.charges] == [
        {
            "title": "Réécrire la file",
            "body": PROBLEME,
            "labels": ["prd", "enhancement"],
        }
    ]
    assert forge.appels == [
        ("gh", "api", "--paginate", "--slurp", LABELS_DU_DEPOT),
        ("gh", "api", "--paginate", "--slurp", ISSUES_OUVERTES),
        ("gh", "api", "-X", "POST", ISSUES, "--input", "-"),
        ("gh", "api", "repos/{owner}/{repo}/issues/901"),
    ]
    assert capsys.readouterr().out == "créée et relue — issue #901\n"


def test_issue_create_apparie_les_labels_sans_la_casse_sur_toutes_les_pages(
    tmp_path: Path,
) -> None:
    """`--label PRD` désigne le `prd` que le dépôt porte sur sa seconde page, et la création part
    sous ce nom-là, comme le retrait d'un label (`label --remove`) ; nommé deux fois, il ne part
    qu'une, à sa première place."""
    forge = Forge({}, labels_du_depot=[["enhancement"], ["prd", "Bug"]])

    assert lance(forge, *creation(tmp_path, "PRD", "bug", "prd")) == 0
    assert json.loads(forge.charges[0])["labels"] == ["prd", "Bug"]


def test_issue_create_refuse_un_label_inconnu_du_depot_sans_rien_ecrire(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Chaque label inconnu est nommé, et rien ne part : `CLAUDE.md` interdit de deviner un
    label, et rien ne garantit qu'un `POST` le refuserait plutôt que de le créer."""
    forge = Forge({}, labels_du_depot=[["prd"]])

    assert lance(forge, *creation(tmp_path, "prd", "bogue", "zone/api")) == 1
    assert ecritures(forge) == []
    assert "label inconnu du dépôt : bogue ; label inconnu du dépôt : zone/api" in sortie_d_echec(
        capsys, "refus"
    )


@pytest.mark.parametrize(
    "pr", [{}, {"pull_request": None}], ids=["sans-pull-request", "pull-request-nul"]
)
def test_issue_create_ne_cree_rien_quand_une_issue_ouverte_porte_deja_ce_titre_et_ce_corps(
    pr: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """L'issue identique, sur la seconde page, est nommée sur la ligne de sortie. Sans `--label`,
    les labels du dépôt ne se lisent pas : la lecture des issues ouvertes est le seul appel. Une
    issue se distingue d'une PR par l'absence de sa clé `pull_request` (« List repository
    issues ») ; une clé `null` n'en fait pas une PR."""
    forge = Forge(
        {},
        issues=[
            [{"number": 5, "title": "Autre titre", "body": PROBLEME, "labels": []}],
            [{"number": 7, "title": "Titre", "body": PROBLEME, "labels": [], **pr}],
        ],
    )

    assert lance(forge, *creation(tmp_path)) == 0
    assert forge.appels == [("gh", "api", "--paginate", "--slurp", ISSUES_OUVERTES)]
    assert capsys.readouterr().out == "rien à écrire — #7 existe déjà\n"


@pytest.mark.parametrize(
    ("portes", "ecart"),
    [
        ((), "labels attendus ['prd'], relus [] — à réparer par `label 7 --add prd`"),
        (
            ("prd", "en attente"),
            (
                "labels attendus ['prd'], relus ['en attente', 'prd'] — "
                "#7 porte en plus ['en attente'] : l'issue a pu vivre depuis sa création"
            ),
        ),
        (
            ("en attente",),
            (
                "labels attendus ['prd'], relus ['en attente'] — "
                "à réparer par `label 7 --add prd` ; "
                "#7 porte en plus ['en attente'] : l'issue a pu vivre depuis sa création"
            ),
        ),
    ],
    ids=["labels-ignores", "label-en-trop", "label-manquant-et-label-en-trop"],
)
def test_issue_create_rejouee_sur_l_issue_sous_d_autres_labels_refuse_et_nomme_la_reparation(
    portes: tuple[str, ...], ecart: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Au rejeu, l'issue de même titre et de même corps se compare comme une relecture, labels
    compris. Sans droit d'écriture, la forge a ignoré les labels de la création, et le premier
    appel est sorti en 1 : le rejeu ne les pose pas, il nomme l'écart et l'appel de `label` qui
    pose les manquants — nom cité pour le shell —, sans rien écrire. Un label en plus n'a pas
    cette cause : l'issue a pu être triée depuis, et le retirer défairait le tri ; il est nommé
    sans réparation."""
    ouverte = {**etiquetee(*portes), "number": 7, "title": "Titre", "body": PROBLEME}
    forge = Forge({}, issues=[[ouverte]], labels_du_depot=[["prd", "en attente"]])

    assert lance(forge, *creation(tmp_path, "PRD")) == 1
    assert ecritures(forge) == []
    assert capsys.readouterr().out == f"refus — #7 existe déjà ; {ecart}\n"


@pytest.mark.parametrize(
    "ouverte",
    [
        {"number": 7, "title": "Titre", "body": PROBLEME, "pull_request": {"url": "…/pulls/7"}},
        {"number": 7, "title": "Titre", "body": "## Problème\n\nLa file déborde.\n"},
        {"number": 7, "title": "Titre voisin", "body": PROBLEME},
    ],
    ids=["pr-identique", "meme-titre-autre-corps", "meme-corps-autre-titre"],
)
def test_issue_create_ne_tient_pour_existante_qu_une_issue_de_meme_titre_et_meme_corps(
    ouverte: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pour l'API REST une PR est une issue — son champ `pull_request` l'en distingue ; titre et
    corps se comparent à l'identique, fins de ligne comprises."""
    forge = Forge({}, issues=[[ouverte]])

    assert lance(forge, *creation(tmp_path)) == 0
    assert capsys.readouterr().out == "créée et relue — issue #901\n"


# Ce que la relecture rend de l'issue créée, quand ce n'est pas ce qui est parti : (retouche du
# document relu, écart **exact** que la sortie en dit). Une retouche par champ écrit, les labels
# dans les deux sens : manquants, et en plus.
ISSUES_RELUES_NON_CONFORMES: dict[str, tuple[Callable[[dict[str, Any]], dict[str, Any]], str]] = {
    "corps-tronque": (
        lambda issue: {**issue, "body": issue["body"][:9]},
        "ancre absente : ## Problème ; attendu 35 octets et 3 \\r, relu 10 octets et 0 \\r",
    ),
    "titre-retouche": (
        lambda issue: {**issue, "title": "Titre (copie)"},
        "titre attendu 'Titre', relu 'Titre (copie)'",
    ),
    # Sans droit d'écriture sur le dépôt, l'API ignore les labels d'une création en silence.
    "labels-ignores": (
        lambda issue: {**issue, "labels": []},
        "labels attendus ['prd'], relus [] — à réparer par `label 901 --add prd`",
    ),
    # Un label posé par un tiers entre la création et la relecture ne se retire pas d'office.
    "label-en-plus": (
        lambda issue: {**issue, "labels": [*issue["labels"], {"name": "needs-triage"}]},
        (
            "labels attendus ['prd'], relus ['needs-triage', 'prd'] — "
            "#901 porte en plus ['needs-triage'] : l'issue a pu vivre depuis sa création"
        ),
    ),
}


@pytest.mark.parametrize(
    ("retouche", "ecart"),
    ISSUES_RELUES_NON_CONFORMES.values(),
    ids=ISSUES_RELUES_NON_CONFORMES.keys(),
)
def test_issue_create_sort_en_1_si_l_issue_relue_n_est_pas_celle_creee(
    retouche: Callable[[dict[str, Any]], dict[str, Any]],
    ecart: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({}, labels_du_depot=[["prd"]])

    args = creation(tmp_path, "prd")
    assert ecriture_relue.main(args, run=relue_autrement(forge, f"{ISSUES}/901", retouche)) == 1
    assert capsys.readouterr().out == f"relecture non conforme — {ecart}\n"


@pytest.mark.parametrize(
    ("options", "raison"),
    [((), "completed"), (("--reason", "not_planned"), "not_planned")],
    ids=["completed-par-defaut", "not-planned"],
)
def test_issue_close_ferme_l_issue_avec_sa_raison_puis_relit_l_une_et_l_autre(
    options: tuple[str, ...], raison: str, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: {"state": "open", "state_reason": None}})

    assert lance(forge, "issue", "close", "42", *options) == 0
    assert [json.loads(charge) for charge in forge.charges] == [
        {"state": "closed", "state_reason": raison}
    ]
    assert forge.appels[-1] == ("gh", "api", CORPS_42), "la fermeture n'est pas relue"
    assert capsys.readouterr().out == f"fermée et relue — #42 ({raison})\n"


def test_issue_close_ne_reecrit_pas_une_fermeture_d_une_autre_raison(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """L'API REST ignore `state_reason` quand `state` ne change pas (« Update an issue ») : une
    issue déjà fermée ne se referme pas sous une autre raison."""
    forge = Forge({CORPS_42: {"state": "closed", "state_reason": "not_planned"}})

    assert lance(forge, "issue", "close", "42") == 1
    assert ecritures(forge) == []
    assert "#42 déjà fermée (not_planned), pas en completed" in sortie_d_echec(capsys, "refus")


def theme(numero: int, titre: str, etat: str = "open", ouvertes: int = 0) -> dict[str, Any]:
    """Un milestone, sous la forme que l'API REST le liste."""
    return {"number": numero, "title": titre, "state": etat, "open_issues": ouvertes}


def test_milestone_attach_rattache_au_theme_de_ce_titre_exact_et_nomme_l_ancien(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le titre se compare à l'identique, sur toutes les pages des milestones ouverts et fermés ;
    le rattachement remplace l'ancien — la fusion de thèmes de `triage/themes-milestones.md` —, et
    la sortie le nomme."""
    forge = Forge(
        {CORPS_42: {"milestone": theme(1, "Ancien")}},
        milestones=[[theme(2, "authentification")], [theme(3, "Authentification")]],
    )

    assert lance(forge, "milestone", "attach", "42", "--title", "Authentification") == 0
    assert [json.loads(charge) for charge in forge.charges] == [{"milestone": 3}]
    assert forge.appels == [
        ("gh", "api", CORPS_42),
        ("gh", "api", "--paginate", "--slurp", THEMES),
        ("gh", "api", "-X", "PATCH", CORPS_42, "--input", "-"),
        ("gh", "api", CORPS_42),
    ]
    assert capsys.readouterr().out == (
        "écrit et relu — #42 rattachée à Authentification, à la place de Ancien\n"
    )


def test_milestone_attach_cree_le_theme_absent_avec_sa_description_puis_rattache(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({CORPS_42: {"milestone": None}})

    args = ("milestone", "attach", "42", "--title", "Facturation", "--description", "Paiements")
    assert lance(forge, *args) == 0
    assert [json.loads(charge) for charge in forge.charges] == [
        {"title": "Facturation", "description": "Paiements", "state": "open"},
        {"milestone": 901},
    ]
    assert forge.appels[-1] == ("gh", "api", CORPS_42), "le rattachement n'est pas relu"
    assert capsys.readouterr().out == (
        "écrit et relu — milestone Facturation créé (901) ; #42 rattachée à Facturation\n"
    )


def test_milestone_close_ferme_le_theme_vide_puis_relit_son_etat(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({}, milestones=[[theme(3, "Archives", ouvertes=0)]])

    assert lance(forge, "milestone", "close", "--title", "Archives") == 0
    assert [json.loads(charge) for charge in forge.charges] == [{"state": "closed"}]
    assert forge.appels[-1] == ("gh", "api", f"{MILESTONES}/3"), "la fermeture n'est pas relue"
    assert capsys.readouterr().out == "fermé et relu — milestone Archives\n"


# Chaque refus de `milestone`, avant toute écriture : (appel, milestones du dépôt, motif).
REFUS_DE_THEME: dict[str, tuple[tuple[str, ...], list[list[dict[str, Any]]], str]] = {
    "attach-theme-ferme": (
        ("milestone", "attach", "42", "--title", "Archives", "--description", "Vieux"),
        [[theme(3, "Archives", "closed")]],
        "le milestone Archives est fermé",
    ),
    "attach-absent-sans-description": (
        ("milestone", "attach", "42", "--title", "Archives"),
        [[theme(3, "archives")]],
        "aucun milestone Archives, et pas de --description pour le créer",
    ),
    "close-absent": (
        ("milestone", "close", "--title", "Archives"),
        [[theme(3, "Archives (2025)")]],
        "aucun milestone Archives",
    ),
    "close-non-vide": (
        ("milestone", "close", "--title", "Archives"),
        [[theme(3, "Archives", ouvertes=2)]],
        "le milestone Archives porte encore 2 issue(s) ouverte(s)",
    ),
}


@pytest.mark.parametrize(
    ("args", "pages", "motif"), REFUS_DE_THEME.values(), ids=REFUS_DE_THEME.keys()
)
def test_milestone_refuse_sans_rien_ecrire(
    args: tuple[str, ...],
    pages: list[list[dict[str, Any]]],
    motif: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge({CORPS_42: {"milestone": None}}, milestones=pages)

    assert lance(forge, *args) == 1
    assert ecritures(forge) == []
    assert motif in sortie_d_echec(capsys, "refus")


@pytest.fixture
def ajout_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Les fichiers `ajout.md`, `brief.md` et `paires.txt` que citent les appels nommés
    ci-dessous, dans un répertoire courant neuf."""
    monkeypatch.chdir(tmp_path)
    Path("ajout.md").write_bytes(b"*Rattachement.*\n")
    Path("brief.md").write_bytes("## Brief d'agent\n\n- [ ] Critère révisé\n".encode())
    Path("paires.txt").write_bytes("< - [ ] Critère A\n> - [x] Critère A — passé\n".encode())


def forge_temoin(**options: Any) -> Forge:
    """La forge des tables partagées : l'issue 42 — ouverte, un corps à une case, le label
    `ready-for-agent`, sans milestone —, son brief, une autre issue ouverte, les labels du dépôt
    et deux thèmes vides."""
    return Forge(
        {
            CORPS_42: {
                "body": "Corps\n- [ ] Critère A\n",
                "labels": [{"name": "ready-for-agent"}],
                "state": "open",
                "state_reason": None,
                "milestone": None,
            }
        },
        pages=[[{"id": 13, "body": BRIEF}]],
        issues=[[{"number": 7, "title": "Autre titre", "body": "Autre corps\n", "labels": []}]],
        labels_du_depot=[["ready-for-agent", "needs-info", "needs-interrogation", "prd"]],
        milestones=[[theme(3, "Authentification"), theme(4, "Archives")]],
        **options,
    )


RETIRE_LABEL = ("label", "42", "--remove", "ready-for-agent")
AJOUTE_LABEL = ("label", "42", "--add", "needs-info")
FERME_ISSUE = ("issue", "close", "42")
RATTACHE_THEME = ("milestone", "attach", "42", "--title", "Authentification")
CREE_THEME = ("milestone", "attach", "42", "--title", "Facturation", "--description", "Paiements")
FERME_THEME = ("milestone", "close", "--title", "Archives")
COCHE_CORPS = ("checkbox", "patch", "42", "--case", "Critère A")
COCHE_BRIEF = ("brief", "patch", "42", "--case", "Critère A")
ANNOTE_CORPS = ("checkbox", "patch", "42", "--paires", "paires.txt")
ANNOTE_BRIEF = ("brief", "patch", "42", "--paires", "paires.txt")
AJOUTE_FICHIER = ("issue", "edit", "42", "--append", "ajout.md")
PUBLIE_COMMENTAIRE = ("comment", "42", "--body-file", "ajout.md")
REMPLACE_CORPS = ("issue", "edit", "42", "--body-file", "ajout.md")
ECRIT_BRIEF = ("brief", "write", "42", "--body-file", "brief.md")
CREE_ISSUE = ("issue", "create", "--title", "Titre", "--body-file", "ajout.md")
CREE_ISSUE_ETIQUETEE = (*CREE_ISSUE, "--label", "prd")
# (appel, ce que la forge fait du texte reçu — `None` le garde tel quel —, sortie du premier appel)
REJEUX = [
    pytest.param(RETIRE_LABEL, None, 0, id="label-remove"),
    pytest.param(AJOUTE_LABEL, None, 0, id="label-add"),
    pytest.param(FERME_ISSUE, None, 0, id="issue-close"),
    pytest.param(RATTACHE_THEME, None, 0, id="milestone-attach"),
    pytest.param(FERME_THEME, None, 0, id="milestone-close"),
    pytest.param(COCHE_CORPS, None, 0, id="checkbox-patch"),
    pytest.param(COCHE_BRIEF, None, 0, id="brief-patch"),
    pytest.param(ANNOTE_CORPS, None, 0, id="checkbox-patch-paires"),
    pytest.param(ANNOTE_BRIEF, None, 0, id="brief-patch-paires"),
    pytest.param(AJOUTE_FICHIER, None, 0, id="issue-edit-append"),
    pytest.param(PUBLIE_COMMENTAIRE, None, 0, id="comment"),
    pytest.param(CREE_ISSUE_ETIQUETEE, None, 0, id="issue-create"),
    pytest.param(REMPLACE_CORPS, None, 0, id="issue-edit-body-file"),
    pytest.param(ECRIT_BRIEF, None, 0, id="brief-write"),
    pytest.param(COCHE_CORPS, crlf, 1, id="checkbox-patch-forge-crlf"),
    pytest.param(COCHE_BRIEF, crlf, 1, id="brief-patch-forge-crlf"),
    pytest.param(ANNOTE_CORPS, crlf, 1, id="checkbox-patch-paires-forge-crlf"),
    pytest.param(ANNOTE_BRIEF, crlf, 1, id="brief-patch-paires-forge-crlf"),
    pytest.param(
        AJOUTE_FICHIER,
        crlf,
        1,
        id="issue-edit-append-forge-crlf",
        marks=pytest.mark.xfail(
            strict=True, raises=AssertionError, reason="fin de corps comparée à l'identique"
        ),
    ),
    pytest.param(
        PUBLIE_COMMENTAIRE,
        crlf,
        1,
        id="comment-forge-crlf",
        marks=pytest.mark.xfail(
            strict=True, raises=AssertionError, reason="corps comparé à l'identique"
        ),
    ),
    pytest.param(
        CREE_ISSUE,
        crlf,
        1,
        id="issue-create-forge-crlf",
        marks=pytest.mark.xfail(
            strict=True, raises=AssertionError, reason="corps comparé à l'identique"
        ),
    ),
    pytest.param(
        REMPLACE_CORPS,
        crlf,
        1,
        id="issue-edit-body-file-forge-crlf",
        marks=pytest.mark.xfail(
            strict=True, raises=AssertionError, reason="corps comparé à l'identique"
        ),
    ),
    pytest.param(
        ECRIT_BRIEF,
        crlf,
        1,
        id="brief-write-forge-crlf",
        marks=pytest.mark.xfail(
            strict=True, raises=AssertionError, reason="corps comparé à l'identique"
        ),
    ),
]


@pytest.mark.usefixtures("ajout_md")
@pytest.mark.parametrize(("args", "stocke", "premier"), REJEUX)
def test_une_sous_commande_rejouee_a_l_identique_n_ecrit_rien_la_seconde_fois(
    args: tuple[str, ...],
    stocke: Callable[[str], str] | None,
    premier: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cliquet de la classe « une sous-commande rejouée à l'identique écrit une seconde fois »
    (`cycle-pr` 4.2, « Le cliquet »), dénombré avant le correctif. Un rejeu suit une relecture
    tombée — écriture acceptée, `GET` en 502, sortie 1 — ou une Étape 8 rejouée après une
    passation ; dans les deux cas, la forge porte déjà ce que le premier appel a écrit. Le premier
    appel écrit une fois ; le second sort en 0 sans **aucune** écriture, ni `PATCH`, ni `DELETE`,
    ni `POST`.

    Population : les 14 appels des 10 sous-commandes qui écrivent, sur une forge qui garde le texte
    reçu ; puis, cherchée hors de cette liste, une forge qui le garde transformé (LF → CRLF : le
    premier appel sort alors en 1, relecture non conforme) — pour les neuf qui écrivent un texte,
    un label ou un état n'en a pas. 23 formes recensées. Au lot 4a, sur les 7 d'alors, 2 fuyaient :

    - `issue-edit-append` — le bloc s'ajoutait une seconde fois ; corrigé : un corps qui finit
      déjà par le fichier n'est pas réécrit ;
    - `issue-edit-append-forge-crlf` — fuit encore, `xfail` strict : la fin du corps se compare
      au fichier à l'identique, fins de ligne comprises ; une comparaison modulo les fins de ligne
      serait une forme réduite, celle qu'obs 106 écarte de la relecture. Le premier appel y a déjà
      rendu la sortie 1, octets et `\\r` relus à l'appui.

    Au lot 4b, `comment` naît avec sa garde — un commentaire de corps identique en tient lieu —,
    vue rouge garde retirée ; `comment-forge-crlf` fuit, `xfail` strict, pour la même raison
    qu'`issue-edit-append-forge-crlf` : le corps se compare au fichier à l'identique.

    Au lot 6a1, `issue create` naît avec sa garde — une issue ouverte de même titre et de même
    corps en tient lieu, ses labels comparés depuis la relecture de la PR #150 —, vue rouge garde
    retirée ; `issue-create-forge-crlf` fuit, `xfail` strict, pour la même raison, et la fuite y
    est une seconde issue ; de même pour `issue edit --body-file` et `brief write`, où elle
    réécrit le même texte. Le rejeu de `brief write` part d'un brief à éditer : après une
    publication, il rejoint le même cas — un brief, égal au fichier. `label --add` naît avec sa
    garde — un label déjà posé ne se repose pas —, `issue close` aussi — une issue déjà fermée
    avec cette raison ne se referme pas —, et `milestone attach` et `close` — une issue déjà
    rattachée, un thème déjà fermé —, chacune vue rouge garde retirée ; le rejeu d'une création
    de thème a son propre test, sa première passe écrivant deux fois.

    Au lot 7b, `checkbox patch --paires` et `brief patch --paires` naissent avec leur garde — une
    paire dont l'ancienne ligne manque et dont la nouvelle est seule dans le texte est déjà
    appliquée —, vue rouge garde retirée, sur les deux forges : la ligne se compare sans son
    retour chariot final, et la forge qui convertit en CRLF n'y fuit pas.

    Les cases se relisent cochées, les lignes remplacées, le label absent ou posé, l'issue fermée,
    rattachée, le thème fermé, le commentaire publié, l'issue créée, le corps remplacé, le brief
    écrit : les 18 autres n'écrivent rien au rejeu.
    """
    forge = forge_temoin() if stocke is None else forge_temoin(stocke=stocke)

    assert lance(forge, *args) == premier
    assert len(ecritures(forge)) == 1, "le premier appel n'a pas écrit une seule fois"
    capsys.readouterr()

    assert lance(forge, *args) == 0
    assert len(ecritures(forge)) == 1, "le rejeu a écrit une seconde fois"
    assert "rien à écrire" in capsys.readouterr().out


def test_milestone_attach_rejoue_apres_creation_du_theme_n_ecrit_rien(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = forge_temoin()

    assert lance(forge, *CREE_THEME) == 0
    capsys.readouterr()
    assert lance(forge, *CREE_THEME) == 0
    assert len(ecritures(forge)) == 2, "le rejeu a écrit une seconde fois"
    assert "rien à écrire" in capsys.readouterr().out


ISSUE_7 = "repos/{owner}/{repo}/issues/7"
# Le thème que crée `CREE_THEME`, champ par champ.
THEME_CREE = {"title": "Facturation", "description": "Paiements", "state": "open"}
# Une forme par champ écrit, seul resté à écrire : (appel, champs retouchés de la forge témoin,
# chemin par chemin, sortie — 0 écrit, 1 refusé). Un texte resté à écrire est un voisin de
# l'attendu, que tiendrait pour égal une garde réduite — contenu, début ou fin au lieu du texte
# entier, une case nommée sur deux.
CHAMPS_RESTES_A_ECRIRE: dict[str, tuple[tuple[str, ...], dict[str, dict[str, Any]], int]] = {
    "label-pose": (TRANSITION, {CORPS_42: {"labels": []}}, 0),
    "label-retrait": (TRANSITION, {CORPS_42: etiquetee("needs-interrogation", "needs-triage")}, 0),
    "checkbox-patch-case": (
        (*COCHE_CORPS, "--case", "Critère B"),
        {CORPS_42: {"body": "Corps\n- [x] Critère A\n- [ ] Critère B\n"}},
        0,
    ),
    "brief-patch-case": (
        (*COCHE_BRIEF, "--case", "Critère B"),
        {BRIEF_DE_42: {"body": BRIEF.replace("- [ ] Critère A", "- [x] Critère A")}},
        0,
    ),
    "issue-edit-append-fin-de-corps": (
        AJOUTE_FICHIER,
        {CORPS_42: {"body": "*Rattachement.*\n\nSuite\n"}},
        0,
    ),
    "issue-edit-body-file-corps": (
        REMPLACE_CORPS,
        {CORPS_42: {"body": "Avant\n*Rattachement.*\n"}},
        0,
    ),
    "comment-corps": (PUBLIE_COMMENTAIRE, {BRIEF_DE_42: {"body": "Avant\n*Rattachement.*\n"}}, 0),
    "brief-write-corps": (
        ECRIT_BRIEF,
        {BRIEF_DE_42: {"body": "## Brief d'agent\n\n- [ ] Critère révisé\n\nSuite\n"}},
        0,
    ),
    "issue-create-titre": (CREE_ISSUE, {ISSUE_7: {"body": "*Rattachement.*\n"}}, 0),
    "issue-create-corps": (CREE_ISSUE, {ISSUE_7: {"title": "Titre"}}, 0),
    # Sans droit d'écriture sur le dépôt, l'API ignore les labels d'une création en silence.
    "issue-create-labels-ignores": (
        CREE_ISSUE_ETIQUETEE,
        {ISSUE_7: {"title": "Titre", "body": "*Rattachement.*\n"}},
        1,
    ),
    "issue-close-etat": (
        FERME_ISSUE,
        {CORPS_42: {"state": "open", "state_reason": "completed"}},
        0,
    ),
    "issue-close-raison": (
        FERME_ISSUE,
        {CORPS_42: {"state": "closed", "state_reason": "not_planned"}},
        1,
    ),
    "milestone-attach": (RATTACHE_THEME, {CORPS_42: {"milestone": theme(4, "Archives")}}, 0),
    # Le thème 4 tient lieu du thème créé, sauf un champ.
    "milestone-attach-creation-titre": (
        CREE_THEME,
        {f"{MILESTONES}/4": {**THEME_CREE, "title": "facturation"}},
        0,
    ),
    "milestone-attach-creation-etat": (
        CREE_THEME,
        {f"{MILESTONES}/4": {**THEME_CREE, "state": "closed"}},
        1,
    ),
    "milestone-close": (FERME_THEME, {f"{MILESTONES}/4": {"state": "open"}}, 0),
}
# Les fuites assumées de la classe, `xfail` strict : chacune rougit le jour où sa garde naît.
FUITES_ASSUMEES = {
    "milestone-attach-creation-description": pytest.param(
        CREE_THEME,
        {f"{MILESTONES}/4": {**THEME_CREE, "description": "Autre"}},
        1,
        marks=pytest.mark.xfail(
            strict=True,
            raises=AssertionError,
            reason="la description d'un thème trouvé ne se relit pas : elle a pu évoluer",
        ),
    ),
}


@pytest.mark.parametrize(
    ("args", "etat", "sortie"),
    [*CHAMPS_RESTES_A_ECRIRE.values(), *FUITES_ASSUMEES.values()],
    ids=[*CHAMPS_RESTES_A_ECRIRE, *FUITES_ASSUMEES],
)
@pytest.mark.usefixtures("ajout_md")
def test_un_rejeu_ne_dit_rien_a_ecrire_tant_qu_un_champ_ecrit_differe(
    args: tuple[str, ...],
    etat: dict[str, dict[str, Any]],
    sortie: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cliquet de la classe « l'identité de rejeu d'une sous-commande omet un champ qu'elle
    écrit » (`cycle-pr` 4.2, « Le cliquet ») : un rejeu ne tient un champ pour écrit qu'une fois
    relu égal à l'attendu — il l'écrit, ou refuse ; jamais « rien à écrire », ni une sortie 0 qui
    le laisse autre. Une issue fermée sous une autre raison est un refus ; une issue de même titre
    et de même corps, sous d'autres labels, aussi.

    Dénombré par **requête d'écriture**, pas par geste nommé, à la passe 2 de relecture de la PR
    #150 : 12 sous-commandes, 14 requêtes, 18 champs, une forme chacun. `label --add` : le `POST`
    des labels posés ; `label --remove` : un `DELETE` par label retiré ; `checkbox patch` et
    `brief patch` : le `PATCH` des cases nommées ; `issue edit --append` : celui de la fin du
    corps ; `issue edit --body-file` : celui du corps ; `brief write` : le corps du brief, par le
    `POST` qui le publie ou le `PATCH` qui l'édite — 2 requêtes, 1 champ ; `comment` : le `POST`
    du corps ; `issue create` : le `POST` du titre, du corps et des labels ; `issue close` : le
    `PATCH` de l'état et de la raison ; `milestone attach` : le `POST` du thème absent — titre,
    description, état —, puis le `PATCH` du milestone de l'issue ; `milestone close` : le `PATCH`
    de l'état du thème.

    2 sous-commandes fuyaient, 1 champ chacune — 2 omis sur 18 :

    - les labels d'`issue create`, que le rejeu ne comparait pas — « #N existe déjà », sortie 0,
      sur une issue restée sans eux ; corrigé à la passe 1 ;
    - la description du thème que crée `milestone attach` — fuit encore, assumée, `xfail` strict
      (`milestone-attach-creation-description`) : le rejeu qui trouve le thème y rattache l'issue
      et sort en 0 sans relire sa description. Il ne se distingue pas d'un premier rattachement
      à un thème déjà là, dont la description a pu évoluer : la comparer refuserait celui-là.

    Chaque forme vue rouge : les 15 premières au lot 6a1 et à la passe 1, avant leur code ou par
    mutation de leur garde — l'ancien rejeu d'`issue create` remis compris ; le titre et l'état du
    thème créé à la passe 2, par mutation. Le dénombrement d'avant — 15 champs, 1 fuite — tenait
    le thème créé hors de `milestone attach`."""
    forge = forge_temoin()
    for chemin, champs in etat.items():
        forge.documents[chemin].update(champs)

    assert lance(forge, *args) == sortie
    assert "rien à écrire" not in capsys.readouterr().out


# Ce que la relecture rend d'un état écrit, quand ce n'est pas ce qui est parti : (appel, chemin
# relu, retouche du document relu, écart **exact** que la sortie en dit). Une retouche par champ
# écrit.
ETATS_RELUS_NON_CONFORMES: dict[str, tuple[tuple[str, ...], str, Callable[[Any], Any], str]] = {
    "label-ajoute-absent": (
        AJOUTE_LABEL,
        CORPS_42,
        lambda issue: {**issue, "labels": []},
        "le label needs-info n'est pas sur #42",
    ),
    "issue-close-etat": (
        FERME_ISSUE,
        CORPS_42,
        lambda issue: {**issue, "state": "open"},
        "#42 relue open (completed), attendue closed (completed)",
    ),
    "issue-close-raison": (
        FERME_ISSUE,
        CORPS_42,
        lambda issue: {**issue, "state_reason": None},
        "#42 relue closed (None), attendue closed (completed)",
    ),
    # Sans droit d'écriture, l'API ignore en silence un changement de milestone.
    "milestone-attach-ignore": (
        RATTACHE_THEME,
        CORPS_42,
        lambda issue: {**issue, "milestone": None},
        "#42 relue dans le milestone None, attendue dans Authentification",
    ),
    "milestone-cree-titre": (
        CREE_THEME,
        f"{MILESTONES}/901",
        lambda theme: {**theme, "title": "facturation"},
        (
            "milestone 901 relu ('facturation', 'Paiements', 'open'), "
            "attendu ('Facturation', 'Paiements', 'open')"
        ),
    ),
    "milestone-cree-description": (
        CREE_THEME,
        f"{MILESTONES}/901",
        lambda theme: {**theme, "description": None},
        (
            "milestone 901 relu ('Facturation', None, 'open'), "
            "attendu ('Facturation', 'Paiements', 'open')"
        ),
    ),
    "milestone-cree-etat": (
        CREE_THEME,
        f"{MILESTONES}/901",
        lambda theme: {**theme, "state": "closed"},
        (
            "milestone 901 relu ('Facturation', 'Paiements', 'closed'), "
            "attendu ('Facturation', 'Paiements', 'open')"
        ),
    ),
    "milestone-close-etat": (
        FERME_THEME,
        f"{MILESTONES}/4",
        lambda theme: {**theme, "state": "open"},
        "milestone Archives relu open, attendu closed",
    ),
}


@pytest.mark.parametrize(
    ("args", "chemin", "retouche", "ecart"),
    ETATS_RELUS_NON_CONFORMES.values(),
    ids=ETATS_RELUS_NON_CONFORMES.keys(),
)
def test_un_etat_relu_autre_que_l_etat_ecrit_sort_en_1_et_dit_l_ecart(
    args: tuple[str, ...],
    chemin: str,
    retouche: Callable[[Any], Any],
    ecart: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = relue_autrement(forge_temoin(), chemin, retouche)

    assert ecriture_relue.main(list(args), run=run) == 1
    assert capsys.readouterr().out == f"relecture non conforme — {ecart}\n"


# Chaque champ que l'appelant saisit, balayé en une passe pour la présence et la forme : le numéro
# entre dans un chemin d'API, l'ancre et le label dans une ligne de sortie.
APPELS_MAL_FORMES = {
    "sans-argument": (),
    "sous-commande-inconnue": ("commente", "42"),
    "action-manquante": ("checkbox", "42", "--case", "A"),
    "action-inconnue": ("brief", "edit", "42", "--case", "A"),
    "case-manquante": ("checkbox", "patch", "42"),
    "brief-ni-case-ni-paires": ("brief", "patch", "42"),
    "case-et-paires": ("checkbox", "patch", "42", "--case", "A", "--paires", "x.txt"),
    "paires-sans-fichier": ("brief", "patch", "42", "--paires"),
    "next-sans-numero": ("checkbox", "next"),
    "next-numero-non-entier": ("checkbox", "next", "#42"),
    "numero-manquant": ("checkbox", "patch", "--case", "A"),
    "numero-non-entier": ("checkbox", "patch", "quarante-deux", "--case", "A"),
    "chiffre-unicode": ("brief", "patch", "4²", "--case", "A"),
    "chemin-dans-le-numero": ("checkbox", "patch", "42/comments", "--case", "A"),
    "ancre-vide": ("checkbox", "patch", "42", "--case", " "),
    "ancre-sur-deux-lignes": ("brief", "patch", "42", "--case", "A\nB"),
    "ancre-a-retour-chariot": ("checkbox", "patch", "42", "--case", "A\rB"),
    "label-manquant": ("label", "42"),
    "label-vide": ("label", "42", "--remove", ""),
    "label-a-poser-vide": ("label", "42", "--add", " "),
    "label-pose-et-retire": ("label", "42", "--add", "bug", "--remove", "Bug"),
    "label-retire-deux-fois": ("label", "42", "--remove", "bug", "--remove", "bug"),
    "label-numero-non-entier": ("label", "#42", "--remove", "ready-for-agent"),
    "fichier-manquant": ("issue", "edit", "42"),
    "issue-numero-non-entier": ("issue", "edit", "4 2", "--append", "x.md"),
    "ajout-et-remplacement": ("issue", "edit", "42", "--append", "x.md", "--body-file", "x.md"),
    "brief-sans-fichier": ("brief", "write", "42"),
    "commentaire-sans-fichier": ("comment", "42"),
    "commentaire-numero-non-ascii": ("comment", "４２", "--body-file", "x.md"),
    "creation-sans-titre": ("issue", "create", "--body-file", "x.md"),
    "creation-titre-vide": ("issue", "create", "--title", " ", "--body-file", "x.md"),
    "creation-titre-sur-deux-lignes": ("issue", "create", "--title", "A\nB", "--body-file", "x.md"),
    "creation-sans-fichier": ("issue", "create", "--title", "Titre"),
    "fermeture-sans-numero": ("issue", "close"),
    "fermeture-raison-inconnue": ("issue", "close", "42", "--reason", "duplicate"),
    "theme-action-inconnue": ("milestone", "rename", "--title", "A"),
    "theme-sans-titre": ("milestone", "attach", "42"),
    "theme-sans-numero": ("milestone", "attach", "--title", "A"),
    "theme-titre-vide": ("milestone", "close", "--title", " "),
    "theme-description-sur-deux-lignes": (*RATTACHE_THEME, "--description", "a\nb"),
    "creation-label-vide": (
        "issue",
        "create",
        "--title",
        "T",
        "--body-file",
        "x.md",
        "--label",
        "",
    ),
}


@pytest.mark.parametrize("args", APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys())
def test_un_appel_mal_forme_sort_en_2_sans_toucher_a_la_forge(
    args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge({CORPS_42: etiquetee("ready-for-agent")})

    assert lance(forge, *args) == 2
    assert forge.appels == []
    assert "usage" in capsys.readouterr().err


# Les appels que la forge fait tomber dès leur première lecture, chacun sous son identifiant.
PREMIERES_LECTURES = {
    "checkbox-patch": COCHE_CORPS,
    "checkbox-next": ("checkbox", "next", "42"),
    "comment": PUBLIE_COMMENTAIRE,
    "issue-create": CREE_ISSUE,
    "issue-create-label": CREE_ISSUE_ETIQUETEE,
    "label-add": AJOUTE_LABEL,
    "issue-close": FERME_ISSUE,
    "milestone-attach": RATTACHE_THEME,
    "milestone-close": FERME_THEME,
}


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
@pytest.mark.parametrize("args", PREMIERES_LECTURES.values(), ids=PREMIERES_LECTURES.keys())
@pytest.mark.usefixtures("ajout_md")
def test_une_forge_en_panne_a_la_lecture_refuse_en_une_ligne(
    args: tuple[str, ...],
    panne: Exception | subprocess.CompletedProcess[bytes],
    motif: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Une commande qui échoue, ne se lance pas ou ne rend pas du JSON n'est pas un texte lu."""

    def forge_en_panne(
        cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        if isinstance(panne, Exception):
            raise panne
        return panne

    assert ecriture_relue.main(list(args), run=forge_en_panne) == 1
    assert motif in sortie_d_echec(capsys, "refus")


# Les appels dont l'écriture tombe, chacun avec la méthode de cette écriture, sous son identifiant.
ECRITURES_EN_PANNE = {
    "patch": (COCHE_CORPS, "PATCH"),
    "delete": (RETIRE_LABEL, "DELETE"),
    "post": (PUBLIE_COMMENTAIRE, "POST"),
    "post-issue": (CREE_ISSUE, "POST"),
    "post-label": (AJOUTE_LABEL, "POST"),
    "patch-fermeture": (FERME_ISSUE, "PATCH"),
    "patch-rattachement": (RATTACHE_THEME, "PATCH"),
    "post-theme": (CREE_THEME, "POST"),
    "patch-theme": (FERME_THEME, "PATCH"),
}


@pytest.mark.parametrize(
    ("args", "methode"), ECRITURES_EN_PANNE.values(), ids=ECRITURES_EN_PANNE.keys()
)
@pytest.mark.usefixtures("ajout_md")
def test_une_ecriture_en_panne_sort_en_1_sans_se_dire_refus(
    args: tuple[str, ...], methode: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """L'écriture a pu partir avant l'échec : « refus » ferait croire que rien n'est écrit."""
    forge = forge_temoin()

    def forge_qui_tombe_a_l_ecriture(
        cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        if methode in cmd:
            return subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"HTTP 502")
        return forge(cmd, stdin)

    assert ecriture_relue.main(list(args), run=forge_qui_tombe_a_l_ecriture) == 1
    assert "a échoué (1) : HTTP 502" in sortie_d_echec(capsys, "relecture non conforme")


# (appel, réponse JSON valide mais d'une autre forme, site qui la rend : « lecture » avant toute
# écriture, « écriture » en réponse à l'écriture, « relecture » après elle)
REPONSES_D_UNE_AUTRE_FORME: dict[str, tuple[tuple[str, ...], Any, str]] = {
    "corps-lu-sans-body": (COCHE_CORPS, {"message": "Not Found"}, "lecture"),
    "corps-lu-non-textuel": (COCHE_CORPS, {"body": 5}, "lecture"),
    "commentaires-hors-pages": (COCHE_BRIEF, {"message": "Not Found"}, "lecture"),
    "commentaire-sans-body": (COCHE_BRIEF, [[{"id": 12}]], "lecture"),
    "brief-sans-id": (COCHE_BRIEF, [[{"body": BRIEF}]], "lecture"),
    "brief-id-non-entier": (COCHE_BRIEF, [[{"id": "13/reactions", "body": BRIEF}]], "lecture"),
    "labels-lus-absents": (RETIRE_LABEL, {"body": ""}, "lecture"),
    "nom-de-label-non-textuel": (RETIRE_LABEL, {"labels": [{"name": 5}]}, "lecture"),
    "commentaires-a-publier-hors-pages": (PUBLIE_COMMENTAIRE, {"message": "Not Found"}, "lecture"),
    "commentaire-identique-id-non-entier": (
        PUBLIE_COMMENTAIRE,
        [[{"id": "11", "body": "*Rattachement.*\n"}]],
        "lecture",
    ),
    "commentaire-publie-sans-id": (PUBLIE_COMMENTAIRE, {"body": "*Rattachement.*\n"}, "écriture"),
    "commentaire-publie-id-booleen": (PUBLIE_COMMENTAIRE, {"id": True}, "écriture"),
    "labels-du-depot-hors-pages": (CREE_ISSUE_ETIQUETEE, {"message": "Not Found"}, "lecture"),
    "label-du-depot-non-textuel": (CREE_ISSUE_ETIQUETEE, [[{"name": 5}]], "lecture"),
    "issues-ouvertes-hors-pages": (CREE_ISSUE, {"message": "Not Found"}, "lecture"),
    "issue-ouverte-sans-titre": (
        CREE_ISSUE,
        [[{"number": 7, "body": "*Rattachement.*\n"}]],
        "lecture",
    ),
    "issue-identique-numero-non-entier": (
        CREE_ISSUE,
        [[{"number": "7", "title": "Titre", "body": "*Rattachement.*\n", "labels": []}]],
        "lecture",
    ),
    "issue-identique-sans-labels": (
        CREE_ISSUE,
        [[{"number": 7, "title": "Titre", "body": "*Rattachement.*\n"}]],
        "lecture",
    ),
    "issue-creee-sans-numero": (CREE_ISSUE, {"title": "Titre"}, "écriture"),
    "issue-creee-numero-booleen": (CREE_ISSUE, {"number": True}, "écriture"),
    "etat-lu-absent": (FERME_ISSUE, {"body": ""}, "lecture"),
    "raison-lue-non-textuelle": (FERME_ISSUE, {"state": "closed", "state_reason": 5}, "lecture"),
    "milestone-de-l-issue-absent": (RATTACHE_THEME, {"body": ""}, "lecture"),
    "milestone-de-l-issue-non-objet": (RATTACHE_THEME, {"milestone": 5}, "lecture"),
    "themes-hors-pages": (FERME_THEME, {"message": "Not Found"}, "lecture"),
    "theme-numero-non-entier": (
        FERME_THEME,
        [[{"title": "Archives", "number": "4", "state": "open", "open_issues": 0}]],
        "lecture",
    ),
    "theme-cree-sans-numero": (CREE_THEME, {"title": "Facturation"}, "écriture"),
    "theme-cree-numero-booleen": (CREE_THEME, {"number": True}, "écriture"),
    "corps-relu-sans-body": (COCHE_CORPS, {"message": "Not Found"}, "relecture"),
    "labels-relus-absents": (RETIRE_LABEL, {"message": "Not Found"}, "relecture"),
    "commentaire-relu-sans-body": (PUBLIE_COMMENTAIRE, {"message": "Not Found"}, "relecture"),
    "etat-relu-absent": (FERME_ISSUE, {"message": "Not Found"}, "relecture"),
    "theme-cree-relu-sans-titre": (CREE_THEME, {"message": "Not Found"}, "relecture"),
    "rattachement-relu-titre-non-textuel": (
        RATTACHE_THEME,
        {"milestone": {"title": 5}},
        "relecture",
    ),
    "theme-ferme-relu-sans-etat": (FERME_THEME, {"message": "Not Found"}, "relecture"),
    "issue-relue-sans-titre": (
        CREE_ISSUE,
        {"number": 901, "body": "*Rattachement.*\n", "labels": []},
        "relecture",
    ),
}


@pytest.mark.parametrize(
    ("args", "document", "site"),
    REPONSES_D_UNE_AUTRE_FORME.values(),
    ids=REPONSES_D_UNE_AUTRE_FORME.keys(),
)
@pytest.mark.usefixtures("ajout_md")
def test_une_reponse_d_une_autre_forme_sort_en_1_en_une_ligne(
    args: tuple[str, ...],
    document: Any,
    site: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un JSON valide sans le champ attendu, ou d'un autre type, n'est pas une trace Python : à la
    lecture, un refus sans écriture ; en réponse à l'écriture ou à la relecture, l'écriture est
    partie, relecture non conforme. Dénombré avant le correctif, au lot 4a : 6 sites lisent un
    champ de la forge — le corps lu (`checkbox patch`, `issue edit`), les commentaires lus page par
    page, l'`id` du brief, qui entre dans un chemin d'API, les labels lus, le corps relu, les
    labels relus —, et les 6 étaient sans garde, le `null` d'un corps seul étant couvert : une
    trace remontait (`KeyError`, `TypeError`, `AttributeError`), et un `id` non entier faisait
    partir le `PATCH` vers un autre chemin. Le lot 4b en ajoute 3, ceux de `comment`, gardés dès
    l'écriture : les commentaires lus, la réponse de la publication, dont l'`id` entre dans le
    chemin de la relecture, le commentaire relu — 9 sites. Le lot 6a1 en ajoute 4, ceux
    d'`issue create`, gardés dès l'écriture : les labels du dépôt, les issues ouvertes, dont le
    numéro de l'issue identique entre dans la ligne de sortie, la réponse de la création, dont le
    numéro entre dans le chemin de la relecture, l'issue relue — 13 sites ; puis 2, ceux
    d'`issue close`, gardés dès l'écriture : l'état et la raison lus, puis relus — 15 sites, la
    réponse de la fermeture n'étant pas lue ; puis 6, ceux de `milestone` : le milestone de
    l'issue, les thèmes du dépôt, dont le numéro entre dans un chemin, la réponse de la création
    d'un thème, de même, le thème créé relu, le rattachement relu, le thème fermé relu — 21 sites.
    Chaque site a sa ligne ; ceux de lecture et la réponse d'une création en ont une seconde, de
    forme ou de type, les issues ouvertes une troisième et une quatrième, le numéro et les labels
    de l'issue identique — 36 lignes ; les relectures passent par les mêmes lecteurs que la
    lecture."""
    forge = forge_temoin()

    def forge_d_une_autre_forme(
        cmd: Sequence[str], stdin: bytes | None
    ) -> subprocess.CompletedProcess[bytes]:
        moment = "écriture" if "-X" in cmd else "relecture" if ecritures(forge) else "lecture"
        rendu = forge(cmd, stdin)
        return json_success(document) if moment == site else rendu

    assert ecriture_relue.main(list(args), run=forge_d_une_autre_forme) == 1
    assert len(ecritures(forge)) == int(site != "lecture")
    issue = "refus" if site == "lecture" else "relecture non conforme"
    assert "ne rend pas la forme attendue" in sortie_d_echec(capsys, issue)


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
    """La session lit le script par un tube, où Python écrit dans la page de code du poste,
    cp1252, que `run_in_pipe` impose (`pipeline.config.md`, « Qualité ») — l'erreur
    d'argparse comprise, qui part sur la sortie d'erreur."""
    done = run_in_pipe("cycle-pr", "ecriture-relue", *args)

    assert done.returncode == code
    assert texte in getattr(done, flux).decode("utf-8")
