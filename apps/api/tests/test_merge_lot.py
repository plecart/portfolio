"""Tests du script de merge d'une PR de lot (`.claude/skills/cycle-pr/scripts/merge-lot.py`).

Le script est la seule voie qui merge sans « go » humain, et seulement **hors du trunk** : c'est
pourquoi chaque refus est un cas de ce module, et le merge un cas à part, qui doit nommer
`--match-head-commit`. Le script parle à `gh` et à `git` par une seule fonction, `run`, que ces
tests remplacent par une forge témoin : les réponses de `gh` sont celles d'une PR réelle (formes
relevées le 2026-10-17 sur la PR #109 par `gh pr view --json …`), et l'appel `gh pr merge` n'est
jamais passé à la vraie forge. Le comportement du vrai `gh` est éprouvé une fois, sur une PR jetable
mergée dans une branche d'intégration jetable — relevé daté dans la PR #117.

La forge ne répond qu'à la **commande complète** attendue, arguments compris, et toute autre lève :
la passe 1 de la relecture de la PR #117 a mesuré 7 mutations d'arguments restées VERTES quand elle
répondait sur les deux ou trois premiers mots — un `--head` retiré qualifiait n'importe quelle base
(mutations M1 à M9 de cette passe).
"""

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from skill_scripts import REPOSITORY_ROOT, load_script

merge_lot = load_script("cycle-pr", "merge-lot")

TETE = "a" * 40
AUTRE_TETE = "b" * 40
INTEGRATION = "feat/sessions-liees"
VERDICT = f"Verdict d'avant-go ({TETE}) : rien à corriger"
PR_INTEGRATION = {
    "body": "En vol pour #107 (intégration, 4 lots)\n\nCloses #107",
    "isCrossRepository": False,
}

Run = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

# Les commandes que le script doit lancer pour `42 <TETE> <INTEGRATION>`, dans l'ordre — écrites en
# littéraux, jamais dérivées du script (`cycle-pr` 3.1, « la table de cas est dérivée de
# l'artefact sous test »).
REPO_VIEW = ("gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name")
PR_LIST = (
    "gh", "pr", "list", "--base", "main", "--head", INTEGRATION, "--state", "open",
    "--json", "body,isCrossRepository",
)  # fmt: skip
PR_VIEW = (
    "gh", "pr", "view", "42", "--json",
    "baseRefName,headRefOid,isDraft,state,body,statusCheckRollup",
)  # fmt: skip
FETCH = (
    "git", "fetch", "origin",
    f"+refs/heads/{INTEGRATION}:refs/remotes/origin/{INTEGRATION}", "pull/42/head",
)  # fmt: skip
GATE = ("git", "merge-base", "--is-ancestor", f"origin/{INTEGRATION}", TETE)
MERGES = ("git", "rev-list", "--merges", f"origin/{INTEGRATION}..{TETE}")
MERGE = ("gh", "pr", "merge", "42", "--rebase", "--match-head-commit", TETE)


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
    """Une forge témoin : rend, pour chaque commande attendue, la sortie qu'un cas fixe, et note
    chaque appel — le test lit ensuite la séquence, et si `gh pr merge` est parti."""

    def __init__(
        self,
        pr: dict[str, Any],
        *,
        trunk: str = "main",
        integration: Sequence[dict[str, Any]] = (PR_INTEGRATION,),
        code_de_la_porte: int = 0,
        merges_du_lot: str = "",
    ) -> None:
        self.reponses: dict[tuple[str, ...], tuple[str, int]] = {
            REPO_VIEW: (trunk + "\n", 0),
            PR_LIST: (json.dumps(list(integration)), 0),
            PR_VIEW: (json.dumps(pr), 0),
            FETCH: ("", 0),
            GATE: ("", code_de_la_porte),
            MERGES: (merges_du_lot, 0),
            MERGE: ("", 0),
        }
        self.appels: list[tuple[str, ...]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        cmd = tuple(cmd)
        self.appels.append(cmd)
        if cmd not in self.reponses:
            raise AssertionError(f"commande inattendue : {cmd}")
        sortie, code = self.reponses[cmd]
        return subprocess.CompletedProcess(list(cmd), code, stdout=sortie, stderr="")

    @property
    def merges(self) -> list[tuple[str, ...]]:
        return [cmd for cmd in self.appels if cmd[:3] == ("gh", "pr", "merge")]


def lance(forge: Run, *args: str) -> int:
    """Le script tel que la session l'appelle : `<PR> <SHA de tête vérifié> <base attendue>`."""
    return merge_lot.main(list(args or ("42", TETE, INTEGRATION)), run=forge)


def test_une_pr_de_lot_verte_vers_sa_branche_d_integration_est_mergee() -> None:
    """Le témoin positif, et l'ordre : la base et la tête sont récupérées **avant** la porte qui
    les compare, la porte passe **avant** le merge. Sans lui, chaque refus ci-dessous pourrait
    venir d'un script qui refuse tout."""
    forge = Forge(pr_verte())

    assert lance(forge) == 0
    assert forge.appels == [REPO_VIEW, PR_LIST, PR_VIEW, FETCH, GATE, MERGES, MERGE]


# Un cas par condition du merge sans « go » (#107, décision 13 du brief) — chacun change une
# seule chose à une PR verte, et la sortie doit nommer **cette** condition : un refus qui tiendrait
# pour une autre raison laisserait la garde visée disparaître sans rougir (`cycle-pr` 3.1,
# « l'assertion ne distingue pas quelle branche a mordu »).
REFUS: dict[str, tuple[dict[str, Any], dict[str, Any], tuple[str, ...], str]] = {
    "base-egale-au-trunk": ({"baseRefName": "main"}, {}, ("42", TETE, "main"), "trunk"),
    "base-sans-pr-d-integration": ({}, {"integration": ()}, (), "PR d'intégration"),
    "base-tete-d-une-pr-de-lot": (
        {},
        {"integration": ({"body": "En vol pour #107 (lot 2a/4)", "isCrossRepository": False},)},
        (),
        "PR d'intégration",
    ),
    "marque-d-integration-hors-de-la-premiere-ligne": (
        {},
        {
            "integration": (
                {
                    "body": "Titre\nEn vol pour #107 (intégration, 4 lots)",
                    "isCrossRepository": False,
                },
            )
        },
        (),
        "PR d'intégration",
    ),
    "marque-d-integration-prefixee": (
        {},
        {
            "integration": (
                {
                    "body": "Pas : En vol pour #107 (intégration, 4 lots)",
                    "isCrossRepository": False,
                },
            )
        },
        (),
        "PR d'intégration",
    ),
    "pr-d-integration-venue-d-un-fork": (
        {},
        {"integration": ({**PR_INTEGRATION, "isCrossRepository": True},)},
        (),
        "PR d'intégration",
    ),
    "base-de-la-pr-autre-que-l-attendue": (
        {"baseRefName": "feat/autre"},
        {},
        (),
        "la base de la PR",
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
        {"statusCheckRollup": [check("Back", "SUCCESS"), check("Infra", "", status="IN_PROGRESS")]},
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
    "tete-qui-ne-contient-pas-la-base": ({}, {"code_de_la_porte": 1}, (), "ne contient pas"),
    "porte-de-fraicheur-sans-reponse": ({}, {"code_de_la_porte": 128}, (), "sans réponse"),
    "lot-avec-commit-de-merge": ({}, {"merges_du_lot": "e" * 40 + "\n"}, (), "commit de merge"),
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
    """Seul le SHA complet que la vérification a vu est accepté : `--match-head-commit` ne doit
    jamais recevoir un préfixe."""
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


def test_la_sortie_du_script_lance_en_tube_est_en_utf_8() -> None:
    """La session lit le motif par un tube. Sous Windows, Python y écrit en cp1252 : « tête »
    arrivait en `t\\xeate`, illisible (mesuré le 2026-10-17 sur la PR jetable #119). Rouge sur le
    poste seulement — un runner Linux écrit en UTF-8 par défaut (`pipeline.config.md`,
    « Qualité »)."""
    script = REPOSITORY_ROOT / ".claude/skills/cycle-pr/scripts/merge-lot.py"
    done = subprocess.run([sys.executable, str(script)], capture_output=True, check=False)

    assert done.returncode == 2
    assert "SHA de tête vérifié" in done.stdout.decode("utf-8")


def test_le_lanceur_par_defaut_decode_la_sortie_en_utf_8() -> None:
    """Le défaut réel du lanceur, que la forge témoin remplace partout ailleurs : décodée à
    l'encodage de la console, la marque « intégration » ne s'apparierait plus, et chaque merge
    serait refusé (mutation `cp1252` restée VERTE à la passe 1 de la relecture)."""
    ecrit = "import sys; sys.stdout.buffer.write('intégration'.encode('utf-8'))"

    assert merge_lot.default_run([sys.executable, "-c", ecrit]).stdout == "intégration"


@pytest.mark.parametrize(
    ("panne", "motif"),
    [
        (FileNotFoundError("gh introuvable"), "ne se lance pas"),
        (subprocess.CompletedProcess([], 1, stdout="", stderr="HTTP 502"), "a échoué"),
        (subprocess.CompletedProcess([], 0, stdout="<html>", stderr=""), "JSON"),
    ],
    ids=["gh-absent", "gh-en-echec", "reponse-non-json"],
)
def test_une_forge_en_panne_refuse_en_une_ligne_au_lieu_de_conclure(
    panne: Exception | subprocess.CompletedProcess[str],
    motif: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Une commande qui échoue, ne se lance pas ou rend autre chose que du JSON n'est pas une PR
    verte : le contrat « 1 refusé, motif en une ligne » tient aussi sur ces chemins."""

    def forge_en_panne(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ("gh", "repo", "view"):
            return subprocess.CompletedProcess(list(cmd), 0, stdout="main\n", stderr="")
        if isinstance(panne, Exception):
            raise panne
        return panne

    assert lance(forge_en_panne) == 1
    sortie = capsys.readouterr().out.strip()
    assert sortie.startswith("refus — "), sortie
    assert motif in sortie, f"le refus ne nomme pas « {motif} » : {sortie}"
