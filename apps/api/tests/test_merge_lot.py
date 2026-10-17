"""Tests du script de merge d'une PR de lot (`.claude/skills/cycle-pr/scripts/merge-lot.py`).

Le script est la seule voie qui merge sans « go » humain, et seulement **hors du trunk** : c'est
pourquoi chaque refus est un cas de ce module, et le merge un cas à part, qui doit nommer
`--match-head-commit`. Le script parle à `gh` et à `git` par une seule fonction, `run`, que ces
tests remplacent par une forge témoin : les réponses de `gh` sont celles d'une PR réelle (formes
relevées le 2026-10-17 sur la PR #109 par `gh pr view --json …`), et l'appel `gh pr merge` n'est
jamais passé à la vraie forge. Le comportement du vrai `gh` est éprouvé une fois, sur une PR jetable
mergée dans une branche d'intégration jetable — relevé daté dans la PR #117.
"""

import json
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from skill_scripts import REPOSITORY_ROOT, load_script

merge_lot = load_script("cycle-pr", "merge-lot")

TETE = "a" * 40
AUTRE_TETE = "b" * 40
REFERENCE_DE_FUSION = "c" * 40
BASE_EPROUVEE = "d" * 40
INTEGRATION = "feat/sessions-liees"
VERDICT = f"Verdict d'avant-go ({TETE}) : rien à corriger"

Run = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def check(name: str, conclusion: str, status: str = "COMPLETED") -> dict[str, str]:
    """Une ligne de `statusCheckRollup`, sous la forme que `gh pr view` la rend."""
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


def pr_verte(**changes: Any) -> dict[str, Any]:
    """Une PR de lot prête : base d'intégration, tête vérifiée, sortie du draft, CI verte, verdict
    du vérificateur inscrit pour cette tête. Chaque cas de refus en change **un** champ."""
    pr: dict[str, Any] = {
        "baseRefName": INTEGRATION,
        "headRefOid": TETE,
        "isDraft": False,
        "state": "OPEN",
        "body": f"En vol pour #107 (lot 3/4)\n\n## Notes\n{VERDICT}\n",
        "statusCheckRollup": [check("Back", "SUCCESS"), check("Publication", "SKIPPED")],
    }
    pr.update(changes)
    return pr


class Forge:
    """Une forge témoin : rend les sorties de `gh` et de `git` qu'un cas fixe, et note chaque
    appel — le test lit ensuite si `gh pr merge` est parti, et avec quels arguments."""

    def __init__(
        self,
        pr: dict[str, Any],
        *,
        trunk: str = "main",
        parents: Sequence[str] = (BASE_EPROUVEE, TETE),
        code_de_la_porte: int = 0,
        integration: Sequence[str] = ("En vol pour #107 (intégration, 4 lots)\n\nCloses #107",),
    ) -> None:
        self.pr = pr
        self.trunk = trunk
        self.parents = parents
        self.code_de_la_porte = code_de_la_porte
        self.integration = integration
        self.appels: list[list[str]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        cmd = list(cmd)
        self.appels.append(cmd)
        sortie, code = self.reponse(cmd)
        return subprocess.CompletedProcess(cmd, code, stdout=sortie, stderr="")

    def reponse(self, cmd: list[str]) -> tuple[str, int]:
        if cmd[:3] == ["gh", "repo", "view"]:
            return self.trunk + "\n", 0
        if cmd[:3] == ["gh", "pr", "view"]:
            return json.dumps(self.pr), 0
        if cmd[:3] == ["gh", "pr", "list"]:
            return json.dumps([{"body": body} for body in self.integration]), 0
        if cmd[:2] == ["git", "fetch"]:
            return "", 0
        if cmd[:2] == ["gh", "api"] and cmd[2].endswith("/merge"):
            return REFERENCE_DE_FUSION + "\n", 0
        if cmd[:2] == ["gh", "api"] and cmd[2].endswith(f"/commits/{REFERENCE_DE_FUSION}"):
            return "".join(f"{sha}\n" for sha in self.parents), 0
        if cmd[:3] == ["git", "merge-base", "--is-ancestor"]:
            return "", self.code_de_la_porte
        if cmd[:3] == ["gh", "pr", "merge"]:
            return "", 0
        raise AssertionError(f"appel inattendu : {cmd}")

    @property
    def merges(self) -> list[list[str]]:
        return [cmd for cmd in self.appels if cmd[:3] == ["gh", "pr", "merge"]]


def lance(forge: Run, *args: str) -> int:
    """Le script tel que la session l'appelle : `<PR> <SHA de tête vérifié> <base attendue>`."""
    return merge_lot.main(list(args or ("42", TETE, INTEGRATION)), run=forge)


def test_une_pr_de_lot_verte_vers_sa_branche_d_integration_est_mergee() -> None:
    """Le témoin positif : sans lui, chaque refus ci-dessous pourrait venir d'un script qui
    refuse tout."""
    forge = Forge(pr_verte())

    assert lance(forge) == 0
    assert forge.merges == [["gh", "pr", "merge", "42", "--rebase", "--match-head-commit", TETE]]


# Un cas par condition du merge sans « go » (#107, décision 13 du brief) — chacun change une
# seule chose à une PR verte, et la sortie doit nommer **cette** condition : un refus qui tiendrait
# pour une autre raison laisserait la garde visée disparaître sans rougir (`cycle-pr` 3.1,
# « l'assertion ne distingue pas quelle branche a mordu »).
REFUS: dict[str, tuple[dict[str, Any], dict[str, Any], tuple[str, ...], str]] = {
    "base-egale-au-trunk": ({"baseRefName": "main"}, {}, ("42", TETE, "main"), "trunk"),
    "base-de-la-pr-autre-que-l-attendue": (
        {"baseRefName": "feat/autre"},
        {},
        (),
        "la base de la PR",
    ),
    "base-sans-pr-d-integration": ({}, {"integration": ()}, (), "PR d'intégration"),
    "base-tete-d-une-pr-de-lot": (
        {},
        {"integration": ("En vol pour #107 (lot 2a/4)\n\nCorps",)},
        (),
        "PR d'intégration",
    ),
    "tete-differente-du-sha-verifie": ({"headRefOid": AUTRE_TETE}, {}, (), "tête"),
    "pr-encore-en-draft": ({"isDraft": True}, {}, (), "draft"),
    "pr-deja-fermee": ({"state": "MERGED"}, {}, (), "ouverte"),
    "ci-rouge": (
        {"statusCheckRollup": [check("Back", "SUCCESS"), check("Front", "FAILURE")]},
        {},
        (),
        "CI",
    ),
    "ci-en-cours": (
        {"statusCheckRollup": [check("Back", "", status="IN_PROGRESS")]},
        {},
        (),
        "CI",
    ),
    "ci-absente": ({"statusCheckRollup": []}, {}, (), "CI"),
    "ci-toute-sautee": (
        {"statusCheckRollup": [check("Back", "SKIPPED"), check("Publication", "SKIPPED")]},
        {},
        (),
        "CI",
    ),
    "verdict-absent": ({"body": "En vol pour #107 (lot 3/4)\n"}, {}, (), "verdict"),
    "verdict-pour-une-autre-tete": (
        {"body": f"Verdict d'avant-go ({AUTRE_TETE}) : rien à corriger"},
        {},
        (),
        "verdict",
    ),
    "reference-de-fusion-sur-une-autre-tete": (
        {},
        {"parents": (BASE_EPROUVEE, AUTRE_TETE)},
        (),
        "référence de fusion",
    ),
    "base-avancee-depuis-le-dernier-run": (
        {},
        {"code_de_la_porte": 1},
        (),
        "avancé",
    ),
    "porte-de-fraicheur-sans-reponse": ({}, {"code_de_la_porte": 128}, (), "sans réponse"),
}


@pytest.mark.parametrize(("pr", "forge", "args", "motif"), REFUS.values(), ids=REFUS.keys())
def test_chaque_condition_manquante_refuse_le_merge_et_se_nomme(
    pr: dict[str, Any],
    forge: dict[str, Any],
    args: tuple[str, ...],
    motif: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    temoin = Forge(pr_verte(**pr), **forge)

    assert lance(temoin, *args) == 1
    assert temoin.merges == [], "le merge est parti malgré le refus"
    sortie = capsys.readouterr().out.strip()
    assert sortie.startswith("refus — "), sortie
    assert motif in sortie, f"le refus ne nomme pas « {motif} » : {sortie}"
    assert "\n" not in sortie, f"le refus tient en plus d'une ligne : {sortie!r}"


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("42", TETE),
        ("42", "abc", INTEGRATION),
        ("quarante-deux", TETE, INTEGRATION),
        ("4²", TETE, INTEGRATION),
    ],
    ids=["sans-argument", "base-manquante", "sha-abrege", "numero-non-entier", "chiffre-unicode"],
)
def test_un_appel_mal_forme_sort_en_2_sans_toucher_a_la_forge(args: tuple[str, ...]) -> None:
    """Un SHA abrégé passerait `--match-head-commit` par préfixe : seul le SHA complet que la
    vérification a vu est accepté."""
    forge = Forge(pr_verte())

    assert merge_lot.main(list(args), run=forge) == 2
    assert forge.appels == []


def test_la_ligne_de_verdict_que_cycle_pr_prescrit_est_celle_que_le_script_lit() -> None:
    """La session écrit la ligne depuis `cycle-pr` Étape 7, le script la lit dans sa propre
    chaîne : deux textes qui divergeraient refuseraient chaque merge de lot, en silence côté
    prose. Le gabarit est un littéral ici, pour que chacun des deux côtés rougisse seul."""
    skill = (REPOSITORY_ROOT / ".claude/skills/cycle-pr/SKILL.md").read_text(encoding="utf-8-sig")
    gabarit = "Verdict d'avant-go (<SHA complet de tête>) : rien à corriger"

    assert gabarit in skill, "`cycle-pr` Étape 7 ne prescrit plus cette ligne de verdict"
    corps = gabarit.replace("<SHA complet de tête>", TETE)
    assert merge_lot.pr_refusal(pr_verte(body=corps), TETE, INTEGRATION) is None


def test_un_appel_de_la_forge_en_echec_refuse_au_lieu_de_conclure() -> None:
    """Une commande `gh` qui échoue (réseau, jeton) n'est pas une PR verte : sa sortie vide ne
    doit pas être lue comme une réponse."""

    def forge_en_panne(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(cmd), 1, stdout="", stderr="HTTP 502")

    assert lance(forge_en_panne) == 1
