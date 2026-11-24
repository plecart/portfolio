"""Tests de la porte de merge vers le trunk (`.claude/skills/cycle-pr/scripts/porte-merge.py`).

Le script lit `gh` et `git` par une seule fonction, `run`, que ces tests remplacent par une forge
témoin : elle ne répond qu'aux commandes complètes attendues, écrites en littéraux, jamais dérivées
du script, et lève sur toute autre (`cycle-pr` 3.1). Le run est le 40769309165 de la PR #185 :
ses jobs sont ceux de `gh run view 40769309165 --json status,headSha,jobs`, réduits aux champs
lus, noms et conclusions réels (gh 2.94.0, relevé le 2026-10-29) ; son `GITHUB_SHA`, la référence
de fusion `009f459` qu'il a extraite, a pour parents `3e24919` puis la tête `8d0200c`
(`gh api repos/{owner}/{repo}/commits/009f459…`, relevé le 2026-11-08), réduit au champ lu. Sa
ligne de fusion est écrite ici sur la forme que fixe l'ADR 0029, relevée telle sur le run
42515735475 (docstring de la porte) — le pas de `ci.yml` qui l'écrit est joué sur un dépôt témoin,
et la porte lit sa ligne — ; le journal d'avant la fusion explicite est un extrait réel de
`gh run view 40769309165 --log` — même relevé du 2026-10-29 : lignes 101, 109 à 111 et 128 du job
Back, 613, 621 à 623 et 640 du job Infra. La conversation est celle de la PR #94
(`gh pr view 94 --json body,comments,reviews`, relevée le 2026-10-29) : son commentaire, réduit à
ses trois premières lignes et aux champs lus ; son body, écrit ici, ne porte que les lignes de
relevé de chaque cas.
"""

import copy
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from command_doubles import (
    ABSENT,
    Reply,
    altered,
    failure,
    json_success,
    sortie_d_echec,
    stdout_lines,
    success,
)
from conftest import (
    REPOSITORY_ROOT,
    bash_de_ce_systeme,
    git_temoin,
    isole_git,
    load_script,
    run_in_pipe,
)

porte_merge = load_script("cycle-pr", "porte-merge")

RUN = "40769309165"
TETE = "8d0200c26697fb8feeddb5c04b0962c9ab1527ed"
# Une autre tête que celle du run — poussée après lui, celle que la porte passerait à
# `--match-head-commit`.
AUTRE_TETE = "f" * 40
TRUNK_FUSIONNE = "3e249191535972bb22dd506ee71d56d9b2b08247"
MAIN_AU_GO = "155b355b0ea3332b2f79d3e49291e4e3b1a653d1"
# Le `GITHUB_SHA` du run, dont il a lu la définition du workflow, et un autre.
WORKFLOW = "009f4593fbf06d8ebb28fff5b78b437131042629"
AUTRE_WORKFLOW = "e" * 40
# Le commit que chaque job construit : un SHA de test par job, deux fusions n'ayant pas la même date.
COMMIT_BACK = "bac0" * 10
COMMIT_INFRA = "1f4a" * 10
BACK = "Back — audit, lint, format, types, tests"
INFRA = "Infra — configuration Compose, images, tests des images, scan"
# Le step sous lequel le journal témoin range chaque ligne : la porte lit par job, quel que soit
# son step.
STEP = "Run actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
WORKFLOWS_INCHANGES = "définition à jour, `.github/workflows/` inchangé jusqu'à origin/main"
WORKFLOWS_CHANGES = (
    "le trunk a changé `.github/workflows/` depuis le déclenchement : `gh run rerun` rejouerait"
    " l'ancienne définition — relancer par fermeture-réouverture"
)

RUN_JSON = ("gh", "run", "view", RUN, "--json", "status,headSha,jobs")
RUN_LOG = ("gh", "run", "view", RUN, "--log")
COMMIT_JSON = (
    "gh",
    "api",
    "repos/{owner}/{repo}/commits/009f4593fbf06d8ebb28fff5b78b437131042629",
)
REV_PARSE = ("git", "rev-parse", "--verify", "refs/remotes/origin/main")
PR_VIEW = ("gh", "pr", "view", "94", "--json", "body,comments,reviews")


def diff_des_workflows(origin: str) -> tuple[str, ...]:
    """`git diff` de `.github/workflows/`, du trunk du déclenchement à `origin`."""
    return ("git", "diff", "--quiet", TRUNK_FUSIONNE, origin, "--", ".github/workflows/")


# `git diff --quiet` sur des workflows changés : 1, sans rien écrire.
DIFF_NON_VIDE = failure(b"")

# Le checkout de la tête, un commit nu — la forme que `git checkout <sha>` écrit —, que la porte ne
# lit pas.
COMMIT_NU = (
    "2026-10-28T21:07:49.3773653Z HEAD is now at 8d0200c feat(pipeline): lit la trace du run"
)


def ligne_de_fusion(
    commit: str, trunk: str = TRUNK_FUSIONNE, tete: str = TETE, workflow: str = WORKFLOW
) -> str:
    """La ligne de fusion d'un job, horodatée."""
    return (
        f"2026-10-28T21:07:52.1043722Z Fusion explicite : {commit} Merge {tete} into {trunk}"
        f" (workflow {workflow})"
    )


# Les lignes du journal de chaque job, sans leurs deux premiers champs ; la ligne de fusion est la
# dernière.
TRACE_BACK = (COMMIT_NU, ligne_de_fusion(COMMIT_BACK))
TRACE_INFRA = (COMMIT_NU, ligne_de_fusion(COMMIT_INFRA))
# Après un `gh run rerun` sur `main` avancé : chaque job fusionne `155b355`.
RELANCE_BACK = (COMMIT_NU, ligne_de_fusion(COMMIT_BACK, trunk=MAIN_AU_GO))
RELANCE_INFRA = (COMMIT_NU, ligne_de_fusion(COMMIT_INFRA, trunk=MAIN_AU_GO))
# Le checkout d'un run `push`, sans fusion : les deux lignes que relevait la docstring de la porte
# (run 40934348730, le 2026-10-29), préfixe `[command]` et horodatages écrits ici.
TRACE_PUSH = (
    (
        "2026-10-29T08:12:03.5512346Z [command]/usr/bin/git checkout --progress --force -B main"
        " refs/remotes/origin/main"
    ),
    "2026-10-29T08:12:03.5871102Z Switched to a new branch 'main'",
)

# Le journal d'avant la fusion explicite, extrait réel : la ligne de checkout de la forge, la
# dernière, et aucune ligne de fusion.
TRACE_BACK_AVANT_249 = (
    (
        "2026-10-28T21:07:48.3485583Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags"
        " --prune --no-recurse-submodules --depth=2 origin"
        " +009f4593fbf06d8ebb28fff5b78b437131042629:refs/remotes/pull/185/merge"
    ),
    "2026-10-28T21:07:49.3396899Z ##[group]Checking out the ref",
    (
        "2026-10-28T21:07:49.3399505Z [command]/usr/bin/git checkout --progress --force"
        " refs/remotes/pull/185/merge"
    ),
    "2026-10-28T21:07:49.3722602Z Note: switching to 'refs/remotes/pull/185/merge'.",
    (
        "2026-10-28T21:07:49.3773653Z HEAD is now at 009f459 Merge"
        " 8d0200c26697fb8feeddb5c04b0962c9ab1527ed into 3e249191535972bb22dd506ee71d56d9b2b08247"
    ),
)
TRACE_INFRA_AVANT_249 = (
    (
        "2026-10-28T21:11:29.3280419Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags"
        " --prune --no-recurse-submodules --depth=1 origin"
        " +009f4593fbf06d8ebb28fff5b78b437131042629:refs/remotes/pull/185/merge"
    ),
    "2026-10-28T21:11:30.0443428Z ##[group]Checking out the ref",
    (
        "2026-10-28T21:11:30.0444491Z [command]/usr/bin/git checkout --progress --force"
        " refs/remotes/pull/185/merge"
    ),
    "2026-10-28T21:11:30.0689710Z Note: switching to 'refs/remotes/pull/185/merge'.",
    (
        "2026-10-28T21:11:30.0709772Z HEAD is now at 009f459 Merge"
        " 8d0200c26697fb8feeddb5c04b0962c9ab1527ed into 3e249191535972bb22dd506ee71d56d9b2b08247"
    ),
)


def journal(back: Sequence[str] = TRACE_BACK, infra: Sequence[str] = TRACE_INFRA) -> bytes:
    """La sortie de `gh run view --log` : une ligne `<job>\\t<step>\\t<texte>` par texte."""
    lignes = [(BACK, texte) for texte in back] + [(INFRA, texte) for texte in infra]
    return "".join(f"{job}\t{STEP}\t{texte}\n" for job, texte in lignes).encode()


def jobs_du_run() -> dict[str, Any]:
    """`gh run view 40769309165 --json status,headSha,jobs`, réduit aux champs lus."""
    return {
        "status": "completed",
        "headSha": TETE,
        "jobs": [
            {"name": BACK, "conclusion": "success"},
            {"name": INFRA, "conclusion": "success"},
            {
                "name": "Front — lint, types, tests, build, e2e, lighthouse, audit",
                "conclusion": "skipped",
            },
            {"name": "Publication — images sur GHCR", "conclusion": "skipped"},
            {"name": "Déploiement — production par SSH", "conclusion": "skipped"},
        ],
    }


class Forge:
    """Une forge témoin : rend la réponse de chaque commande attendue — une `OSError` y est levée,
    comme un exécutable introuvable —, lève sur toute autre, et note chaque appel."""

    def __init__(self, reponses: dict[tuple[str, ...], Reply]) -> None:
        self.reponses = reponses
        self.appels: list[tuple[str, ...]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        cmd = tuple(cmd)
        self.appels.append(cmd)
        if cmd not in self.reponses:
            raise AssertionError(f"commande inattendue : {cmd}")
        reponse = self.reponses[cmd]
        if isinstance(reponse, OSError):
            raise reponse
        return reponse


def commit_du_workflow() -> dict[str, Any]:
    """`gh api repos/{owner}/{repo}/commits/009f459…`, réduit au champ lu : ses parents, le trunk
    du déclenchement puis la tête."""
    return {"parents": [{"sha": TRUNK_FUSIONNE}, {"sha": TETE}]}


def forge_du_run(
    jobs: Reply | None = None,
    log: Reply | None = None,
    commit: Reply | None = None,
    git: Reply | None = None,
    diff: Reply | None = None,
    origin: str = MAIN_AU_GO,
) -> Forge:
    """La forge du run 40769309165, `origin/main` à `origin`, `.github/workflows/` inchangé depuis
    le déclenchement ; une réponse donnée — `jobs`, `log`, `commit` pour `gh api …/commits`, `git`
    pour `git rev-parse`, `diff` pour `git diff` — remplace la réponse témoin."""
    return Forge(
        {
            COMMIT_JSON: json_success(commit_du_workflow()) if commit is None else commit,
            diff_des_workflows(origin): success(b"") if diff is None else diff,
            RUN_JSON: json_success(jobs_du_run()) if jobs is None else jobs,
            RUN_LOG: success(journal()) if log is None else log,
            REV_PARSE: success(f"{origin}\n".encode()) if git is None else git,
        }
    )


def lance(forge: Forge, *args: str) -> int:
    """Le script tel que la session l'appelle."""
    return porte_merge.main(list(args), run=forge)


# `trunk` tel que la porte l'appelle sur le run 40769309165 : sa tête est la tête visée.
TRUNK = ("trunk", RUN, "main", TETE)


@pytest.mark.parametrize(
    ("origin", "code", "fraicheur"),
    [(MAIN_AU_GO, 1, "périmé"), (TRUNK_FUSIONNE, 0, "à jour")],
    ids=["main-avance-a-155b355", "main-au-trunk-fusionne"],
)
def test_la_ligne_de_fusion_rend_le_trunk_que_chaque_job_a_fusionne(
    origin: str, code: int, fraicheur: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """L'incident de la PR #185 sous la fusion explicite : les deux jobs ont fusionné la tête
    `8d0200c` à `3e24919`, puis `main` a avancé à `155b355`, que le run n'a jamais éprouvé : contre
    lui, la porte sort en 1 ; le témoin, `origin/main` au trunk fusionné, en 0. La définition du
    workflow est à jour dans les deux cas."""
    forge = forge_du_run(origin=origin)

    assert lance(forge, *TRUNK) == code
    assert forge.appels == [RUN_JSON, RUN_LOG, COMMIT_JSON, REV_PARSE, diff_des_workflows(origin)]
    assert stdout_lines(capsys) == [
        f"{BACK} : construit {COMMIT_BACK}, trunk {TRUNK_FUSIONNE} — {fraicheur}",
        f"{INFRA} : construit {COMMIT_INFRA}, trunk {TRUNK_FUSIONNE} — {fraicheur}",
        f"workflow {WORKFLOW}, déclenché sur le trunk {TRUNK_FUSIONNE} : {WORKFLOWS_INCHANGES}",
        (
            f"trunk éprouvé {TRUNK_FUSIONNE} — run {RUN}, workflow {WORKFLOW} : {fraicheur}"
            f" (origin/main = {origin})"
        ),
    ]


def test_un_seul_job_au_trunk_perime_rend_le_run_perime(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Chaque job fusionne le trunk de son propre démarrage : Infra, parti après le merge de
    `155b355`, est à jour, Back non. Un job à jour ne rattrape pas l'autre : le run n'a pas éprouvé
    un état combiné unique."""
    forge = forge_du_run(log=success(journal(infra=RELANCE_INFRA)))

    assert lance(forge, *TRUNK) == 1
    sortie = stdout_lines(capsys)
    assert sortie[:2] == [
        f"{BACK} : construit {COMMIT_BACK}, trunk {TRUNK_FUSIONNE} — périmé",
        f"{INFRA} : construit {COMMIT_INFRA}, trunk {MAIN_AU_GO} — à jour",
    ]
    assert sortie[-1] == (
        f"trunk éprouvé {TRUNK_FUSIONNE}, {MAIN_AU_GO} — run {RUN}, workflow {WORKFLOW} : périmé"
        f" (origin/main = {MAIN_AU_GO})"
    )


@pytest.mark.parametrize(
    ("diff", "code", "definition", "fraicheur"),
    [
        (success(b""), 0, WORKFLOWS_INCHANGES, "à jour"),
        (DIFF_NON_VIDE, 1, WORKFLOWS_CHANGES, "périmé"),
    ],
    ids=["workflows-inchanges", "workflows-changes-par-le-trunk"],
)
def test_un_run_relance_sur_le_trunk_courant_juge_aussi_sa_definition(
    diff: Reply, code: int, definition: str, fraicheur: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un `gh run rerun` refait la fusion sur `155b355`, mais garde le `GITHUB_SHA` du
    déclenchement, donc la définition du workflow lue sur le trunk `3e24919` : si `main` a changé
    `.github/workflows/` depuis, la porte sort en 1, chaque job pourtant à jour, et nomme la
    fermeture-réouverture."""
    forge = forge_du_run(log=success(journal(RELANCE_BACK, RELANCE_INFRA)), diff=diff)

    assert lance(forge, *TRUNK) == code
    assert stdout_lines(capsys) == [
        f"{BACK} : construit {COMMIT_BACK}, trunk {MAIN_AU_GO} — à jour",
        f"{INFRA} : construit {COMMIT_INFRA}, trunk {MAIN_AU_GO} — à jour",
        f"workflow {WORKFLOW}, déclenché sur le trunk {TRUNK_FUSIONNE} : {definition}",
        (
            f"trunk éprouvé {MAIN_AU_GO} — run {RUN}, workflow {WORKFLOW} : {fraicheur}"
            f" (origin/main = {MAIN_AU_GO})"
        ),
    ]


def sans_jobs_qui_tournent() -> dict[str, Any]:
    """Le run, chacun de ses jobs sauté."""
    run = jobs_du_run()
    for job in run["jobs"]:
        job["conclusion"] = "skipped"
    return run


# Le motif d'un job sans ligne de fusion.
SANS_LIGNE = (
    "aucune ligne `Fusion explicite : …` au journal — job arrêté avant sa fusion, run d'un `push`, ou"
    " d'un workflow d'avant la fusion explicite, à relancer par fermeture-réouverture (ADR 0029)"
)
# Une ligne de fusion privée de son workflow.
SANS_WORKFLOW = ligne_de_fusion(COMMIT_BACK).removesuffix(f" (workflow {WORKFLOW})")
# `git diff` sur un objet que le clone n'a pas.
OBJET_INCONNU = subprocess.CompletedProcess(
    [], 128, stdout=b"", stderr=f"fatal: bad object {TRUNK_FUSIONNE}".encode()
)

# Un cas par refus de `trunk` : chacun change une seule chose au run 40769309165, et la sortie doit
# nommer **ce** refus — un refus tenu pour une autre raison laisserait la garde visée disparaître
# sans rougir (`cycle-pr` 3.1).
REFUS_TRUNK: dict[str, tuple[dict[str, Any], str]] = {
    "run-pas-termine": (
        {"jobs": json_success(altered(jobs_du_run(), ("status",), "in_progress"))},
        "pas terminé (status in_progress)",
    ),
    "aucun-job-n-a-tourne": ({"jobs": json_success(sans_jobs_qui_tournent())}, "aucun job"),
    "journal-d-un-push": (
        {"log": success(journal(TRACE_PUSH, TRACE_PUSH))},
        f"job « {BACK} » : {SANS_LIGNE}",
    ),
    "journal-d-avant-la-fusion-explicite": (
        {"log": success(journal(TRACE_BACK_AVANT_249, TRACE_INFRA_AVANT_249))},
        f"job « {BACK} » : {SANS_LIGNE}",
    ),
    "un-job-sans-ligne-de-fusion": (
        {"log": success(journal(infra=TRACE_INFRA[:-1]))},
        f"job « {INFRA} » : {SANS_LIGNE}",
    ),
    "job-a-deux-lignes-de-fusion": (
        {"log": success(journal(back=(*TRACE_BACK, TRACE_BACK[-1])))},
        f"job « {BACK} » : 2 lignes `Fusion explicite : …` au journal, une attendue",
    ),
    "commit-abrege": (
        {"log": success(journal(back=(COMMIT_NU, ligne_de_fusion(COMMIT_BACK[:7]))))},
        f"job « {BACK} » : ligne hors de la forme",
    ),
    "ligne-sans-workflow": (
        {"log": success(journal(back=(COMMIT_NU, SANS_WORKFLOW)))},
        f"job « {BACK} » : ligne hors de la forme",
    ),
    "fusion-d-une-autre-tete-que-celle-du-run": (
        {"log": success(journal(back=(COMMIT_NU, ligne_de_fusion(COMMIT_BACK, tete=AUTRE_TETE))))},
        f"a fusionné la tête {AUTRE_TETE}, pas le headSha du run {TETE}",
    ),
    "jobs-a-deux-workflows": (
        {
            "log": success(
                journal(infra=(COMMIT_NU, ligne_de_fusion(COMMIT_INFRA, workflow=AUTRE_WORKFLOW)))
            )
        },
        f"nomment plusieurs workflows : {WORKFLOW}, {AUTRE_WORKFLOW}",
    ),
    "jobs-hors-json": ({"jobs": success(b"<html>")}, "ne rend pas du JSON"),
    "gh-en-echec": ({"jobs": failure(b"HTTP 502")}, "a échoué (1) : HTTP 502"),
    "gh-absent": ({"jobs": FileNotFoundError("gh introuvable")}, "`gh` ne se lance pas"),
    "journal-en-echec": ({"log": failure(b"log not found")}, "a échoué (1) : log not found"),
    "commit-du-workflow-en-echec": (
        {"commit": failure(b"HTTP 422: No commit found for SHA")},
        "a échoué (1) : HTTP 422: No commit found for SHA",
    ),
    "git-en-echec": (
        {"git": failure(b"fatal: Needed a single revision")},
        "`git rev-parse --verify refs/remotes/origin/main` a échoué (1)",
    ),
    "git-absent": ({"git": FileNotFoundError("git introuvable")}, "`git` ne se lance pas"),
    "diff-des-workflows-en-erreur": (
        {"diff": OBJET_INCONNU},
        f"a échoué (128) : fatal: bad object {TRUNK_FUSIONNE}",
    ),
}


@pytest.mark.parametrize(("forge", "motif"), REFUS_TRUNK.values(), ids=REFUS_TRUNK.keys())
def test_chaque_refus_du_trunk_sort_en_2_et_se_nomme(
    forge: dict[str, Any], motif: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance(forge_du_run(**forge), *TRUNK) == 2
    sortie = sortie_d_echec(capsys, "refus")
    assert motif in sortie, f"le refus ne nomme pas « {motif} » : {sortie}"


def test_un_run_qui_n_a_pas_eprouve_la_tete_visee_refuse_le_merge_en_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le constat I1 de la passe 1 de relecture du bloc 1 de #197 : le run R tourne sur la tête A,
    B est poussée, et `trunk R main && gh pr merge --match-head-commit B` passait — R ne disait
    rien de B. La porte nomme désormais la tête qu'elle merge, et le run doit l'avoir éprouvée ;
    le refus tombe avant la lecture du journal."""
    forge = forge_du_run()

    assert lance(forge, "trunk", RUN, "main", AUTRE_TETE) == 2
    assert forge.appels == [RUN_JSON]
    assert (
        f"le run {RUN} a éprouvé la tête {TETE}, pas la tête visée {AUTRE_TETE}"
        in sortie_d_echec(capsys, "refus")
    )


# Le pas qui écrit la ligne de fusion : celui du job `changes` de `ci.yml`, que les autres jobs de
# la CI reprennent (ADR 0029).
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
PAS_DE_FUSION = "Fusion explicite du trunk"
IDENTITE_GIT = (
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "EMAIL",
)


def pas_de_fusion() -> dict[str, Any]:
    """Le pas de fusion du job `changes` de `ci.yml`, sous sa forme analysée."""
    steps = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["changes"]["steps"]
    (pas,) = [pas for pas in steps if pas.get("name") == PAS_DE_FUSION]
    return pas


def test_la_ligne_qu_ecrit_le_pas_de_fusion_de_la_ci_est_celle_que_la_porte_lit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le contrat de l'émetteur à la porte. Le pas, joué sous le shell d'Actions (`shell: bash`,
    `bash -eo pipefail`, doc GitHub « Workflow syntax ») dans un dépôt témoin — le trunk en
    `refs/remotes/origin/main`, la tête extraite détachée, la configuration git du poste et son
    identité écartées —, écrit une ligne que la porte trouve dans le journal du job, script recopié
    compris, et dont elle rend le commit construit, la tête, le trunk et le `GITHUB_SHA` du run."""
    isole_git(monkeypatch)
    for nom in IDENTITE_GIT:
        monkeypatch.delenv(nom, raising=False)
    for args in (
        ("init", "-b", "main"),
        ("commit", "--allow-empty", "-m", "base"),
        ("checkout", "-b", "pr"),
        ("commit", "--allow-empty", "-m", "tête de la PR"),
        ("checkout", "main"),
        ("commit", "--allow-empty", "-m", "trunk"),
        ("update-ref", "refs/remotes/origin/main", "main"),
    ):
        git_temoin(*args, cwd=tmp_path)
    trunk, tete = git_temoin("rev-parse", "main", "pr", cwd=tmp_path).split()
    git_temoin("checkout", "--detach", tete, cwd=tmp_path)
    pas = pas_de_fusion()

    joue = subprocess.run(
        [bash_de_ce_systeme(), "-eo", "pipefail", "-c", pas["run"]],
        cwd=tmp_path,
        env={**os.environ, "TRUNK": "main", "HEAD_SHA": tete, "GITHUB_SHA": WORKFLOW},
        capture_output=True,
        check=False,
    )

    assert joue.returncode == 0, joue.stderr
    textes = [*pas["run"].splitlines(), *(joue.stdout + joue.stderr).decode().splitlines()]
    log = "".join(f"{BACK}\t{STEP}\t2026-11-08T09:00:00.0000000Z {texte}\n" for texte in textes)
    construit = git_temoin("rev-parse", "HEAD", cwd=tmp_path).strip()
    assert porte_merge.fusion(BACK, porte_merge.fusion_lines(log).get(BACK, []), tete) == (
        porte_merge.Fusion(BACK, construit, trunk, WORKFLOW)
    )


COMMENTAIRE_94 = {
    "author": {"login": "plecart"},
    "body": "> *Généré par IA — répercussion du merge de #92 (lot 2/3 de #23, `b869724`).*\n\n"
    "**À ajuster dans cette PR — la ligne « sécurité » de `.claude/pipeline.config.md`**\n",
    "createdAt": "2026-10-14T17:52:41Z",
}
PREMIERE_LIGNE_94 = "> *Généré par IA — répercussion du merge de #92 (lot 2/3 de #23, `b869724`).*"
RELEVE_AU_VERDICT = "Conversation : 0 commentaires et revues, dernier aucun"
RELEVE_APRES = "Conversation : 1 commentaires et revues, dernier 2026-10-14T17:52:41Z"


def revue(soumise: str | None, texte: str = "") -> dict[str, Any]:
    """Une revue de `gh pr view --json reviews`, réduite aux champs lus ; `None` : en attente."""
    return {"author": {"login": "plecart"}, "body": texte, "submittedAt": soumise}


def pr_94(
    *releves: str, commentaires: Sequence[Any] = (COMMENTAIRE_94,), revues: Sequence[Any] = ()
) -> dict[str, Any]:
    """La PR #94 telle que `gh pr view --json body,comments,reviews` la rend, chaque relevé une
    ligne des Notes du body."""
    notes = "".join(f"{releve}\n" for releve in releves)
    return {
        "body": f"En vol pour #23\n\n## Notes\n{notes}",
        "comments": list(commentaires),
        "reviews": list(revues),
    }


def forge_de_la_pr(pr: Any) -> Forge:
    """La forge qui rend `pr` à `gh pr view 94 --json body,comments,reviews`."""
    return Forge({PR_VIEW: json_success(pr)})


@pytest.mark.parametrize(
    ("releve", "code", "lignes"),
    [
        (
            RELEVE_AU_VERDICT,
            1,
            [
                f"commentaire de plecart à 2026-10-14T17:52:41Z : {PREMIERE_LIGNE_94}",
                (
                    f"PR 94 : changée depuis « {RELEVE_AU_VERDICT} » — actuel : 1 commentaires"
                    " et revues, dernier 2026-10-14T17:52:41Z"
                ),
            ],
        ),
        (
            RELEVE_APRES,
            0,
            [
                (
                    f"PR 94 : inchangée depuis « {RELEVE_APRES} » — actuel : 1 commentaires et"
                    " revues, dernier 2026-10-14T17:52:41Z"
                ),
            ],
        ),
    ],
    ids=["releve-du-verdict-a-0-commentaire", "releve-pris-apres-le-commentaire"],
)
def test_le_commentaire_repercussions_de_la_pr_94_change_la_conversation_du_verdict(
    releve: str, code: int, lignes: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """L'incident d'origine (obs 88, 89) : verdict vers 17:35 UTC à 0 commentaire, « à ajuster »
    de `repercussions` à 17:52:41 UTC, merge à 17:58:31 UTC. Contre ce relevé, la porte sort en
    1 et nomme le commentaire ; le témoin, relevé pris après lui, en 0."""
    assert lance(forge_de_la_pr(pr_94(releve)), "conversation", "94") == code
    assert stdout_lines(capsys) == lignes


# Un cas par règle de compte ou de lecture du relevé : (PR, code attendu, première ligne de la
# sortie).
CONVERSATIONS: dict[str, tuple[dict[str, Any], int, str]] = {
    "revue-soumise-posterieure": (
        pr_94(RELEVE_APRES, revues=[revue("2026-10-14T18:01:07Z", "Approuvé.\nRien à redire.")]),
        1,
        "revue de plecart à 2026-10-14T18:01:07Z : Approuvé.",
    ),
    "revue-en-attente-ignoree": (
        pr_94(RELEVE_APRES, revues=[revue(None, "Brouillon de revue")]),
        0,
        "PR 94 : inchangée",
    ),
    "deux-releves-le-dernier-lu": (pr_94(RELEVE_AU_VERDICT, RELEVE_APRES), 0, "PR 94 : inchangée"),
    "deux-releves-le-dernier-perime": (
        pr_94(RELEVE_APRES, RELEVE_AU_VERDICT),
        1,
        "commentaire de plecart",
    ),
    "compte-different-sans-element-posterieur": (
        pr_94("Conversation : 2 commentaires et revues, dernier 2026-10-14T17:52:41Z"),
        1,
        "PR 94 : changée",
    ),
    "compte-egal-et-element-posterieur": (
        pr_94(RELEVE_APRES, commentaires=[{**COMMENTAIRE_94, "createdAt": "2026-10-14T18:05:00Z"}]),
        1,
        "commentaire de plecart à 2026-10-14T18:05:00Z",
    ),
    "revue-de-commentaires-en-ligne": (
        pr_94(RELEVE_APRES, revues=[revue("2026-10-14T18:01:07Z")]),
        1,
        (
            "revue de plecart à 2026-10-14T18:01:07Z : sans texte — ses commentaires en ligne,"
            " s'il y en a : gh api --paginate repos/{owner}/{repo}/pulls/94/comments"
        ),
    ),
    "posterieur-d-une-fraction-de-seconde": (
        pr_94(
            "Conversation : 1 commentaires et revues, dernier 2026-10-14T17:52:41Z",
            commentaires=[{**COMMENTAIRE_94, "createdAt": "2026-10-14T17:52:41.5Z"}],
        ),
        1,
        "commentaire de plecart à 2026-10-14T17:52:41.5Z",
    ),
    "posterieurs-du-plus-ancien-au-plus-recent": (
        pr_94(RELEVE_AU_VERDICT, revues=[revue("2026-10-14T17:40:00Z", "Plus ancienne.")]),
        1,
        "revue de plecart à 2026-10-14T17:40:00Z : Plus ancienne.",
    ),
}


@pytest.mark.parametrize(
    ("pr", "code", "premiere"), CONVERSATIONS.values(), ids=CONVERSATIONS.keys()
)
def test_la_conversation_se_compte_en_commentaires_et_revues_soumises(
    pr: dict[str, Any], code: int, premiere: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """« Fraction de seconde » : en chaînes, `…41.5Z` passerait avant `…41Z` (`.` précède `Z`) —
    c'est pourquoi les instants se comparent en `datetime`. « Compte égal » : un commentaire
    supprimé, un autre ajouté — le compte seul ne voit rien (constat I2 de la passe 1 de relecture
    du bloc 1 de #197)."""
    assert lance(forge_de_la_pr(pr), "conversation", "94") == code
    sortie = stdout_lines(capsys)
    assert sortie[0].startswith(premiere), sortie


REFUS_CONVERSATION: dict[str, tuple[Reply, str]] = {
    "releve-absent": (json_success(pr_94()), "aucune ligne « Conversation : … »"),
    "releve-mal-forme": (
        json_success(pr_94("Conversation : 0 commentaires, dernier aucun")),
        "mal formée : Conversation : 0 commentaires, dernier aucun",
    ),
    "releve-a-une-date-impossible": (
        json_success(
            pr_94("Conversation : 1 commentaires et revues, dernier 2026-13-14T17:52:41Z")
        ),
        "mal formée",
    ),
    "dernier-releve-mal-forme-apres-un-bon": (
        json_success(pr_94(RELEVE_APRES, "Conversation : <k> commentaires et revues, dernier <…>")),
        "mal formée : Conversation : <k>",
    ),
    "body-hors-chaine": (
        json_success({**pr_94(RELEVE_APRES), "body": None}),
        "ne rend pas la forme attendue : TypeError body de type NoneType",
    ),
    "gh-en-echec": (failure(b"HTTP 502"), "a échoué (1) : HTTP 502"),
}


@pytest.mark.parametrize(
    ("reponse", "motif"), REFUS_CONVERSATION.values(), ids=REFUS_CONVERSATION.keys()
)
def test_un_releve_absent_ou_illisible_refuse_en_2(
    reponse: Reply, motif: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance(Forge({PR_VIEW: reponse}), "conversation", "94") == 2
    sortie = sortie_d_echec(capsys, "refus")
    assert motif in sortie, f"le refus ne nomme pas « {motif} » : {sortie}"


# Chaque champ que le script lit d'une réponse JSON de `gh`, par son chemin et la valeur qui le
# remplace : absent, ou d'une autre forme, il refuse au lieu de conclure — une exception non
# rattrapée sortirait en 1, « périmé » ou « changée ». Chaque exception que l'`except` d'une
# lecture rattrape a au moins un cas : `KeyError` par l'absence, `TypeError`, `ValueError` et
# `AttributeError` par une valeur.
CHAMPS_DU_RUN: dict[str, tuple[tuple[str | int, ...], Any]] = {
    "status": (("status",), ABSENT),
    "headSha": (("headSha",), ABSENT),
    "jobs": (("jobs",), ABSENT),
    "jobs.name": (("jobs", 0, "name"), ABSENT),
    "jobs.conclusion": (("jobs", 0, "conclusion"), ABSENT),
    "jobs-null": (("jobs",), None),
}
# `IndexError` aussi, par une liste vide ; et un parent qui n'est pas un SHA complet, qui entrerait
# dans la commande `git diff`.
CHAMPS_DU_COMMIT: dict[str, tuple[tuple[str | int, ...], Any]] = {
    "parents": (("parents",), ABSENT),
    "parents-vide": (("parents",), []),
    "parents.sha": (("parents", 0, "sha"), ABSENT),
    "parents.sha-null": (("parents", 0, "sha"), None),
    "parents.sha-hors-forme": (("parents", 0, "sha"), "--output=workflows.diff"),
}
CHAMPS_DE_LA_PR: dict[str, tuple[tuple[str | int, ...], Any]] = {
    "body": (("body",), ABSENT),
    "comments": (("comments",), ABSENT),
    "reviews": (("reviews",), ABSENT),
    "comments.createdAt": (("comments", 0, "createdAt"), ABSENT),
    "comments.author": (("comments", 0, "author"), ABSENT),
    "comments.author.login": (("comments", 0, "author", "login"), ABSENT),
    "comments.body": (("comments", 0, "body"), ABSENT),
    "reviews.submittedAt": (("reviews", 0, "submittedAt"), ABSENT),
    "reviews.author": (("reviews", 0, "author"), ABSENT),
    "reviews.author.login": (("reviews", 0, "author", "login"), ABSENT),
    "reviews.body": (("reviews", 0, "body"), ABSENT),
    "comments.createdAt-hors-forme": (("comments", 0, "createdAt"), "hier"),
    "reviews.body-null": (("reviews", 0, "body"), None),
}


@pytest.mark.parametrize(("champ", "valeur"), CHAMPS_DU_RUN.values(), ids=CHAMPS_DU_RUN.keys())
def test_un_champ_lu_du_run_absent_ou_d_une_autre_forme_refuse_en_2(
    champ: tuple[str | int, ...], valeur: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = forge_du_run(jobs=json_success(altered(jobs_du_run(), champ, valeur)))

    assert lance(forge, *TRUNK) == 2
    assert "ne rend pas la forme attendue" in sortie_d_echec(capsys, "refus")


@pytest.mark.parametrize(
    ("champ", "valeur"), CHAMPS_DU_COMMIT.values(), ids=CHAMPS_DU_COMMIT.keys()
)
def test_un_champ_lu_du_commit_du_workflow_absent_ou_d_une_autre_forme_refuse_en_2(
    champ: tuple[str | int, ...], valeur: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = forge_du_run(commit=json_success(altered(commit_du_workflow(), champ, valeur)))

    assert lance(forge, *TRUNK) == 2
    assert "ne rend pas la forme attendue" in sortie_d_echec(capsys, "refus")


@pytest.mark.parametrize(("champ", "valeur"), CHAMPS_DE_LA_PR.values(), ids=CHAMPS_DE_LA_PR.keys())
def test_un_champ_lu_de_la_pr_absent_ou_d_une_autre_forme_refuse_en_2(
    champ: tuple[str | int, ...], valeur: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    pr = copy.deepcopy(pr_94(RELEVE_APRES, revues=[revue("2026-10-14T18:01:07Z", "Approuvé.")]))
    forge = forge_de_la_pr(altered(pr, champ, valeur))

    assert lance(forge, "conversation", "94") == 2
    assert "ne rend pas la forme attendue" in sortie_d_echec(capsys, "refus")


# Le dénombrement de la classe du constat I1 — une entrée tapée que rien ne lie à l'artefact
# qu'elle désigne —, que le module de `porte-merge.py` porte, avant et après son correctif : une
# entrée par élément de l'usage de chaque sous-commande, et l'appel qui fait voir ce qui la lie,
# ou qu'elle n'est liée à rien. Par cas : (sous-commande, entrée de l'usage, forge, appel, code,
# flux, texte attendu).
ENTREES: dict[str, tuple[str, str, Forge, tuple[str, ...], int, str, str]] = {
    "trunk-run": (
        "trunk",
        "<run>",
        forge_du_run(jobs=json_success(altered(jobs_du_run(), ("headSha",), AUTRE_TETE))),
        TRUNK,
        2,
        "out",
        f"a éprouvé la tête {AUTRE_TETE}, pas la tête visée {TETE}",
    ),
    "trunk-tete": (
        "trunk",
        "<tête>",
        Forge({}),
        ("trunk", RUN, "main", TETE[:7]),
        2,
        "err",
        "SHA complet de 40 hexadécimaux attendu, pas '8d0200c'",
    ),
    "trunk-base": ("trunk", "<base>", forge_du_run(), TRUNK, 1, "out", "(origin/main = 155b355"),
    "trunk-aide": ("trunk", "[-h]", Forge({}), ("trunk", "-h"), 2, "out", "usage: porte-merge.py"),
    "conversation-pr": (
        "conversation",
        "<PR>",
        forge_de_la_pr(pr_94()),
        ("conversation", "94"),
        2,
        "out",
        "le body ne porte aucune ligne « Conversation : … »",
    ),
    "conversation-releve": (
        "conversation",
        "[--releve]",
        forge_de_la_pr(pr_94(RELEVE_AU_VERDICT)),
        ("conversation", "94", "--releve"),
        0,
        "out",
        RELEVE_APRES,
    ),
    "conversation-aide": (
        "conversation",
        "[-h]",
        Forge({}),
        ("conversation", "-h"),
        2,
        "out",
        "usage: porte-merge.py",
    ),
}


@pytest.mark.parametrize("commande", ["trunk", "conversation"])
def test_le_denombrement_des_entrees_couvre_l_usage_de_chaque_sous_commande(
    commande: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """La population du dénombrement est l'usage lui-même : une entrée ajoutée à une sous-commande
    sans son cas dans `ENTREES` rougit ici, avant de faire passer une porte."""
    assert lance(Forge({}), commande, "--help") == 2
    usage = stdout_lines(capsys)[0].removeprefix(f"usage: porte-merge.py {commande} ")

    assert sorted(usage.split()) == sorted(
        entree for cible, entree, *_ in ENTREES.values() if cible == commande
    )


@pytest.mark.parametrize(
    ("forge", "appel", "code", "flux", "texte"),
    [cas[2:] for cas in ENTREES.values()],
    ids=ENTREES.keys(),
)
def test_chaque_entree_tapee_est_liee_a_l_artefact_ou_le_dit(
    forge: Forge,
    appel: tuple[str, ...],
    code: int,
    flux: str,
    texte: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`<run>` lié à `<tête>` par le `headSha` ; `<tête>` complète, celle que la porte passe à
    `--match-head-commit` ; `<base>` lié au trunk que chaque job a fusionné et à la définition du
    workflow ; `<PR>` lié au relevé de son propre body ; l'aide en 2. `--releve` sort en 0 sur une
    conversation changée : c'est un mode, liée à rien à dessein, qui ne se chaîne jamais par `&&`."""
    assert lance(forge, *appel) == code
    sortie = getattr(capsys.readouterr(), flux)
    assert texte in sortie, sortie


@pytest.mark.parametrize(
    ("pr", "ligne"),
    [
        (pr_94(commentaires=()), RELEVE_AU_VERDICT),
        (pr_94(), RELEVE_APRES),
        (
            pr_94(
                revues=[
                    revue("2026-10-14T18:10:00Z"),
                    revue(None, "en attente"),
                    revue("2026-10-14T17:00:00Z", "plus ancienne"),
                ]
            ),
            "Conversation : 3 commentaires et revues, dernier 2026-10-14T18:10:00Z",
        ),
    ],
    ids=["pr-94-au-verdict", "pr-94-apres-le-commentaire", "revues-melees-et-en-attente"],
)
def test_le_releve_copie_dans_le_body_rend_la_conversation_inchangee(
    pr: dict[str, Any], ligne: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le `verificateur` copie la ligne de `--releve` telle quelle aux Notes, et la porte la relit :
    même règle de compte des deux côtés. « Dernier » est l'instant le plus récent, pas le dernier
    élément de la liste ; une revue en attente ne compte pas."""
    assert lance(forge_de_la_pr(pr), "conversation", "94", "--releve") == 0
    assert stdout_lines(capsys) == [ligne]

    inscrit = {**pr, "body": f"{pr['body']}{ligne}\n"}
    assert lance(forge_de_la_pr(inscrit), "conversation", "94") == 0


@pytest.mark.parametrize(
    ("args", "code", "flux", "texte"),
    [
        (["--help"], 2, "stdout", "le trunk que le run a réellement fusionné"),
        (["trunk", "²", "main", TETE], 2, "stderr", "numéro attendu, pas '²'"),
    ],
    ids=["aide-sur-stdout", "usage-sur-stderr"],
)
def test_la_sortie_du_script_lance_en_tube_est_en_utf_8(
    args: list[str], code: int, flux: str, texte: str
) -> None:
    """La session lit le script par un tube, où Python écrit dans la page de code du poste,
    cp1252, que `run_in_pipe` impose (`pipeline.config.md`, « Qualité ») — l'erreur d'argparse
    comprise, qui part sur la sortie d'erreur. L'aide sort en 2, comme le script lancé : en 0,
    `porte-merge.py --help && gh pr merge …` mergerait (constat m3 de la passe 1)."""
    done = run_in_pipe("cycle-pr", "porte-merge", *args)

    assert done.returncode == code
    assert texte in getattr(done, flux).decode("utf-8")


def test_le_lanceur_par_defaut_capture_les_sorties_en_octets() -> None:
    """Le défaut réel du lanceur, que la forge témoin remplace partout ailleurs : un nom de job
    accentué passe octet pour octet, sans le mode texte ni la page de code de la console."""
    octets = "Déploiement — production par SSH\n".encode()
    ecrit = f"import sys; sys.stdout.buffer.write({octets!r})"

    assert porte_merge.default_run([sys.executable, "-c", ecrit]).stdout == octets
