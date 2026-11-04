"""Tests du croisement des fichiers mergés avec les branches en vol
(`.claude/skills/pr-paralleles/scripts/croisement-fichiers.py`).

Le script lit la forge par `gh` et le dépôt par `git`, les deux par une seule fonction, `run`. Ces
tests remplacent `gh`, la frontière réseau, par une forge témoin qui lève sur toute commande
qu'elle n'attend pas ; `git` passe au vrai lanceur du script, dans un dépôt jetable dont les
commits portent chaque état : le merge de la PR 127 sur `origin/main`, une branche en conflit avec
lui, une qui le prolonge, une qui touche ailleurs. Les réponses de `gh` ont la forme que la session
PR du lot 4b de #134 a mesurée (gh 2.94.0, le 2026-10-21), réduites aux champs que le script lit.
Les cas s'écrivent en littéraux, jamais dérivés des constantes du script (`cycle-pr` 3.1).
"""

import subprocess
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from command_doubles import Reply, failure, json_success, stdout_lines, success
from conftest import git_temoin, load_script, run_in_pipe

croisement = load_script("pr-paralleles", "croisement-fichiers")

PR = "127"
VUE = ("gh", "pr", "view", "127", "--json", "state,mergeCommit,baseRefName")
DIFF = ("gh", "pr", "diff", "127", "--name-only")
# Le commit de merge réel de la PR 142, pour les cas qui refusent avant de le chercher.
MERGE_142 = "5767944848b8adbc8657377998e00f4483c6e976"


def mergee(oid: str, base: str = "main") -> dict[str, Any]:
    """Ce que rend `gh pr view --json state,mergeCommit,baseRefName` pour une PR mergée sur `oid`
    dans la branche `base`, nom nu (mesuré le 2026-10-21 sur les PR 127 et 142)."""
    return {"baseRefName": base, "mergeCommit": {"oid": oid}, "state": "MERGED"}


# Les fichiers que la PR 127 a mergés, tels que `gh pr diff --name-only` les rend.
FICHIERS_MERGES = success(b"f.txt\ng.txt\n")


class Depot(NamedTuple):
    """Le dépôt jetable : son chemin, le commit de merge de la PR 127 — la tête d'`origin/main` —
    et la tête de la branche `ailleurs`, qu'`origin/main` ne contient pas."""

    chemin: Path
    merge: str
    ailleurs: str


def commit(depot: Path, message: str, fichiers: dict[str, str]) -> str:
    """Écrit `fichiers` dans `depot`, les commite sur la branche courante, et rend le SHA."""
    for nom, contenu in fichiers.items():
        (depot / nom).write_text(contenu, encoding="utf-8")
    git_temoin("add", *fichiers, cwd=depot)
    git_temoin("commit", "-qm", message, cwd=depot)
    return git_temoin("rev-parse", "HEAD", cwd=depot).strip()


@pytest.fixture(scope="module")
def depot(tmp_path_factory: pytest.TempPathFactory) -> Depot:
    """Trois fichiers, puis le merge de la PR 127, qui touche `f.txt` et `g.txt`, sur `main` —
    `origin/main` y pointe. Trois branches : `conflit`, partie d'avant le merge, réécrit les deux
    mêmes lignes ; `propre` prolonge le merge sur `g.txt` ; `ailleurs`, partie d'avant le merge,
    ne touche que `k.txt` — un diff à deux points lui prêterait aussi `f.txt` et `g.txt`."""
    chemin = tmp_path_factory.mktemp("croisement")
    git_temoin("init", "-q", "-b", "main", cwd=chemin)
    commit(chemin, "base", {"f.txt": "base\n", "g.txt": "base\n", "k.txt": "base\n"})
    git_temoin("branch", "conflit", cwd=chemin)
    git_temoin("branch", "ailleurs", cwd=chemin)
    merge = commit(chemin, "PR 127", {"f.txt": "merge\n", "g.txt": "merge\n"})
    git_temoin("update-ref", "refs/remotes/origin/main", merge, cwd=chemin)
    git_temoin("checkout", "-q", "-b", "propre", cwd=chemin)
    commit(chemin, "suite", {"g.txt": "suite\n"})
    git_temoin("checkout", "-q", "conflit", cwd=chemin)
    commit(chemin, "autre", {"f.txt": "autre\n", "g.txt": "autre\n"})
    git_temoin("checkout", "-q", "ailleurs", cwd=chemin)
    ailleurs = commit(chemin, "ailleurs", {"k.txt": "ailleurs\n"})
    git_temoin("checkout", "-q", "main", cwd=chemin)
    return Depot(chemin, merge, ailleurs)


@pytest.fixture(autouse=True)
def dans_le_depot(depot: Depot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le script lit le dépôt courant : chaque test part du dépôt jetable."""
    monkeypatch.chdir(depot.chemin)


class Forge:
    """La forge témoin : elle rend `vue` à `gh pr view` et `diff` à `gh pr diff` — une `OSError`
    levée comme un `gh` introuvable —, passe `git` au lanceur par défaut du script, et garde
    chaque commande reçue."""

    def __init__(self, vue: Reply | dict[str, Any], diff: Reply = FICHIERS_MERGES) -> None:
        self.reponses = {VUE: json_success(vue) if isinstance(vue, dict) else vue, DIFF: diff}
        self.appels: list[tuple[str, ...]] = []

    def __call__(self, cmd: Any) -> subprocess.CompletedProcess[bytes]:
        cmd = tuple(cmd)
        self.appels.append(cmd)
        if cmd[0] == "git":
            return croisement.default_run(cmd)
        assert cmd in self.reponses, f"commande inattendue : {cmd}"
        reponse = self.reponses[cmd]
        if isinstance(reponse, OSError):
            raise reponse
        return reponse


def lance(forge: Forge, *args: str) -> int:
    """Le script, appelé avec `args` sur la forge témoin."""
    return croisement.main(list(args), forge)


def test_un_conflit_fabrique_rend_merge_tree_1_et_nomme_ses_fichiers(
    depot: Depot, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le critère 2 du bloc : `conflit` réécrit les lignes que le merge a réécrites."""
    assert lance(Forge(mergee(depot.merge)), PR, "conflit") == 0
    assert stdout_lines(capsys) == [
        "f.txt → conflit",
        "g.txt → conflit",
        "conflit : merge-tree 1 — conflit : f.txt, g.txt",
    ]


def test_une_branche_sans_conflit_qui_touche_un_fichier_merge_entre_dans_la_table(
    depot: Depot, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance(Forge(mergee(depot.merge)), PR, "propre") == 0
    assert stdout_lines(capsys) == ["g.txt → propre", "propre : merge-tree 0 — sans conflit"]


@pytest.mark.parametrize(
    ("branches", "attendu"),
    [
        (
            ("ailleurs",),
            [
                "aucun fichier mergé par #127 n'est touché par une branche en vol",
                "ailleurs : merge-tree 0 — sans conflit",
            ],
        ),
        (
            ("ailleurs", "propre"),
            [
                "g.txt → propre",
                "ailleurs : merge-tree 0 — sans conflit",
                "propre : merge-tree 0 — sans conflit",
            ],
        ),
    ],
    ids=["seule", "avec-une-branche-qui-recouvre"],
)
def test_une_branche_qui_ne_touche_rien_du_merge_est_absente_de_la_table_mais_garde_sa_ligne(
    depot: Depot,
    branches: tuple[str, ...],
    attendu: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lance(Forge(mergee(depot.merge)), PR, *branches) == 0
    assert stdout_lines(capsys) == attendu


def test_la_table_nomme_chaque_branche_qui_touche_chaque_fichier_merge(
    depot: Depot, capsys: pytest.CaptureFixture[str]
) -> None:
    """La ligne de `g.txt` porte deux branches, celle de `f.txt` une seule : retirer une branche à
    la fois du filtre, ou de la jonction, rougit."""
    assert lance(Forge(mergee(depot.merge)), PR, "conflit", "propre", "ailleurs") == 0
    assert stdout_lines(capsys) == [
        "f.txt → conflit",
        "g.txt → conflit, propre",
        "conflit : merge-tree 1 — conflit : f.txt, g.txt",
        "propre : merge-tree 0 — sans conflit",
        "ailleurs : merge-tree 0 — sans conflit",
    ]


# `git merge-tree` sort en 1 sur une référence qu'il ne peut pas fusionner comme sur un conflit
# (mesuré le 2026-10-21, git 2.47.1, et épinglé par `FRESHNESS_GATE_FORMS` de
# `test_agent_skills.py`) : chaque référence se valide avant. Un cas par position — une branche,
# la base — et par forme mesurée : un nom absent, un objet qui n'est pas un commit.
REFERENCES_INCONNUES = {
    "branche-absente": (("propre", "nope"), "nope"),
    "base-absente": (("propre", "--base", "origin/absente"), "origin/absente"),
    "arbre-et-non-commit": (("main^{tree}",), "main^{tree}"),
}


@pytest.mark.parametrize(
    ("args", "reference"), REFERENCES_INCONNUES.values(), ids=REFERENCES_INCONNUES.keys()
)
def test_une_reference_inconnue_est_refusee_avant_tout_merge_tree(
    depot: Depot, args: tuple[str, ...], reference: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Seules les résolutions ont tourné — ni la forge, ni `merge-tree`. Cette absence s'assère
    d'abord : sans la validation, `propre` passerait son `merge-tree` avant que `nope` ne fasse
    échouer son diff."""
    forge = Forge(mergee(depot.merge))

    code = lance(forge, PR, *args)

    assert {cmd[:2] for cmd in forge.appels} == {("git", "rev-parse")}, forge.appels
    assert code == 1
    assert stdout_lines(capsys) == [f"refus — référence introuvable : `{reference}`"]


@pytest.mark.parametrize("etat", ["OPEN", "CLOSED"])
def test_une_pr_non_mergee_est_refusee(etat: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Le croisement suit un merge : une PR ouverte ou fermée sans merge n'a rien livré, et
    `gh` rend alors `mergeCommit` nul (mesuré le 2026-10-21 sur la PR 144, ouverte, et la 138,
    fermée)."""
    forge = Forge({"baseRefName": "main", "mergeCommit": None, "state": etat})

    assert lance(forge, PR, "propre") == 1
    assert stdout_lines(capsys) == [
        (
            f"refus — la PR #127 n'est pas mergée ({etat}) : le croisement suit un merge,"
            " `pr-paralleles` §7"
        )
    ]


def test_une_base_qui_ne_contient_pas_le_merge_renvoie_a_git_fetch(
    depot: Depot, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le commit de merge existe dans le dépôt, hors de la base : `--is-ancestor` sort en 1. La
    base nommée est celle par défaut, `origin/main`."""
    forge = Forge(mergee(depot.ailleurs))

    assert lance(forge, PR, "propre") == 1
    assert stdout_lines(capsys) == [
        (
            f"refus — `origin/main` ne contient pas le merge de #127 ({depot.ailleurs[:7]}),"
            " mergée dans `main` : `git fetch origin`, ou `--base origin/main`"
        )
    ]


def test_un_merge_absent_du_depot_renvoie_a_git_fetch(capsys: pytest.CaptureFixture[str]) -> None:
    """Le cas d'un `fetch` oublié : le commit de merge n'est pas dans le dépôt local, et
    `--is-ancestor` y sortirait en 128 (mesuré le 2026-10-21, git 2.47.1)."""
    forge = Forge(mergee("0123456789abcdef0123456789abcdef01234567"))

    assert lance(forge, PR, "propre") == 1
    assert stdout_lines(capsys) == [
        (
            "refus — `origin/main` ne contient pas le merge de #127 (0123456), mergée dans `main` :"
            " `git fetch origin`, ou `--base origin/main`"
        )
    ]


def test_une_pr_mergee_dans_une_autre_base_nomme_cette_base_en_remede(
    depot: Depot, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le cas de la PR 142, mergée dans `feat/contexte-court` et croisée sans `--base` (mesuré le
    2026-10-21) : `git fetch origin` seul ne la ferait jamais entrer dans `origin/main`."""
    forge = Forge(mergee(depot.ailleurs, base="feat/x"))

    assert lance(forge, PR, "propre") == 1
    assert stdout_lines(capsys) == [
        (
            f"refus — `origin/main` ne contient pas le merge de #127 ({depot.ailleurs[:7]}),"
            " mergée dans `feat/x` : `git fetch origin`, ou `--base origin/feat/x`"
        )
    ]


# Chaque lecture de `gh` qui ne rend pas de réponse : (vue, diff, début du motif) — `None` garde
# la réponse nominale.
REFUS: dict[str, tuple[Reply | None, Reply | None, str]] = {
    "vue-en-panne": (
        failure(b"HTTP 502: Bad Gateway (https://api.github.com/graphql)\n"),
        None,
        "`gh pr view 127 --json state,mergeCommit,baseRefName` a échoué (1) : HTTP 502: Bad Gateway",
    ),
    "gh-absent": (
        FileNotFoundError("gh introuvable"),
        None,
        "`gh` ne se lance pas : gh introuvable",
    ),
    "vue-non-json": (
        success(b"<html>"),
        None,
        "`gh pr view 127 --json state,mergeCommit,baseRefName` ne rend pas du JSON",
    ),
    # Un JSON valide, mais en cp1252 : décodé par la page de code du poste, il passerait (obs 108).
    "vue-hors-utf-8": (
        success('{"state": "MERGED", "titre": "Déploiement"}'.encode("cp1252")),
        None,
        "`gh pr view 127 --json state,mergeCommit,baseRefName` ne rend pas de l'UTF-8",
    ),
    "diff-en-panne": (
        None,
        failure(b"HTTP 404: Not Found\n"),
        "`gh pr diff 127 --name-only` a échoué (1) : HTTP 404: Not Found",
    ),
    "diff-hors-utf-8": (
        None,
        success("déploiement.txt\n".encode("cp1252")),
        "`gh pr diff 127 --name-only` ne rend pas de l'UTF-8",
    ),
}


@pytest.mark.parametrize(("vue", "diff", "motif"), REFUS.values(), ids=REFUS.keys())
def test_une_lecture_gh_en_echec_est_refusee_en_une_ligne(
    depot: Depot,
    vue: Reply | None,
    diff: Reply | None,
    motif: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge(vue or mergee(depot.merge), diff or FICHIERS_MERGES)

    assert lance(forge, PR, "propre") == 1
    (ligne,) = stdout_lines(capsys)
    assert ligne.startswith(f"refus — {motif}"), ligne


# Chaque champ que le script lit de `gh pr view`, absent puis d'un autre type. Dénombré avant le
# code : 4 champs — `state`, `baseRefName`, `mergeCommit` et son `oid` —, plus le document et
# `mergeCommit` qui ne sont pas des objets, un `mergeCommit` nul sur une PR mergée, et un `oid` du
# bon type hors de sa forme : une référence que git résoudrait, et qui passerait donc pour un
# commit de merge. Chaque document porte les autres champs dans leur forme juste : le cas ne
# rougit que sur le sien.
FORMES: dict[str, Any] = {
    "vue-hors-objet": ["MERGED"],
    "state-absent": {"baseRefName": "main", "mergeCommit": {"oid": MERGE_142}},
    "state-non-textuel": {"baseRefName": "main", "mergeCommit": {"oid": MERGE_142}, "state": None},
    "baseRefName-absent": {"mergeCommit": {"oid": MERGE_142}, "state": "MERGED"},
    "baseRefName-non-textuel": {
        "baseRefName": None,
        "mergeCommit": {"oid": MERGE_142},
        "state": "MERGED",
    },
    "mergeCommit-absent": {"baseRefName": "main", "state": "MERGED"},
    "mergeCommit-nul": {"baseRefName": "main", "mergeCommit": None, "state": "MERGED"},
    "mergeCommit-hors-objet": {"baseRefName": "main", "mergeCommit": MERGE_142, "state": "MERGED"},
    "oid-absent": {"baseRefName": "main", "mergeCommit": {}, "state": "MERGED"},
    "oid-non-textuel": {"baseRefName": "main", "mergeCommit": {"oid": 5767944}, "state": "MERGED"},
    "oid-hors-sha": {
        "baseRefName": "main",
        "mergeCommit": {"oid": "origin/main"},
        "state": "MERGED",
    },
}


@pytest.mark.parametrize("vue", FORMES.values(), ids=FORMES.keys())
def test_une_vue_d_une_autre_forme_est_refusee_en_une_ligne(
    vue: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge(json_success(vue))

    assert lance(forge, PR, "propre") == 1
    (ligne,) = stdout_lines(capsys)
    assert ligne.startswith(
        "refus — `gh pr view 127 --json state,mergeCommit,baseRefName` ne rend pas la forme attendue"
    ), ligne


def test_un_git_qui_ne_repond_ni_0_ni_1_est_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Hors de tout dépôt, `git rev-parse` sort en 128 : ni « résolue », ni « introuvable »."""
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "aucun-depot"))

    assert lance(Forge(mergee(MERGE_142)), PR, "propre") == 1
    (ligne,) = stdout_lines(capsys)
    assert ligne.startswith(
        "refus — `git rev-parse --verify --quiet propre^{commit}` a échoué (128) : fatal:"
    ), ligne


# Chaque argument de l'appel, absent puis hors de sa forme : le numéro, en chiffres ASCII ; au
# moins une branche ; chaque référence non vide, et sans `-` de tête — elle entre en position
# d'argument dans `git merge-tree`, où elle se lirait comme une option.
APPELS_MAL_FORMES = {
    "sans-argument": (),
    "lettres": ("abc", "propre"),
    "chiffre-unicode": ("²", "propre"),
    "sans-branche": (PR,),
    "branche-vide": (PR, ""),
    "branche-en-option": (PR, "--", "-x"),
    "base-vide": (PR, "propre", "--base", ""),
    "base-en-option": (PR, "propre", "--base=-x"),
}


@pytest.mark.parametrize("args", APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys())
def test_un_appel_mal_forme_sort_en_2_sans_rien_lancer(
    depot: Depot, args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge(mergee(depot.merge))

    assert lance(forge, *args) == 2
    assert forge.appels == []
    assert "usage" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("args", "code", "flux", "texte"),
    [
        (["--help"], 0, "stdout", "Croise les fichiers qu'une PR a mergés"),
        (["²", "propre"], 2, "stderr", "numéro de PR attendu, pas '²'"),
    ],
    ids=["aide-sur-stdout", "usage-sur-stderr"],
)
def test_la_sortie_du_script_lance_en_tube_est_en_utf_8(
    args: list[str], code: int, flux: str, texte: str
) -> None:
    """Le lead lit le script par un tube, où Python écrit dans la page de code du poste, cp1252,
    que `run_in_pipe` impose (`pipeline.config.md`, « Qualité ») — l'erreur d'argparse
    comprise, qui part sur la sortie d'erreur."""
    done = run_in_pipe("pr-paralleles", "croisement-fichiers", *args)

    assert done.returncode == code
    assert texte in getattr(done, flux).decode("utf-8")
