"""Tests de la porte de merge vers le trunk (`.claude/skills/cycle-pr/scripts/porte-merge.py`).

Le script lit `gh` et `git` par une seule fonction, `run`, que ces tests remplacent par une forge
témoin : elle ne répond qu'aux commandes complètes attendues, écrites en littéraux, jamais dérivées
du script, et lève sur toute autre (`cycle-pr` 3.1). La trace est un extrait réel de
`gh run view 40769309165 --log` — PR #185, gh 2.94.0, relevé le 2026-10-29 : lignes 101, 109 à 111
et 128 du job Back, 613, 621 à 623 et 640 du job Infra — et ses jobs ceux de
`gh run view 40769309165 --json status,headSha,jobs`, réduits aux champs lus, noms et conclusions
réels. La conversation est celle de la PR #94 (`gh pr view 94 --json body,comments,reviews`,
même date) : son commentaire, réduit à ses trois premières lignes et aux champs lus ; son body,
écrit ici, ne porte que les lignes de relevé de chaque cas.
"""

import copy
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

import pytest
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
from conftest import load_script, run_in_pipe

porte_merge = load_script("cycle-pr", "porte-merge")

RUN = "40769309165"
TETE = "8d0200c26697fb8feeddb5c04b0962c9ab1527ed"
# Une autre tête que celle du run — poussée après lui, celle que la porte passerait à
# `--match-head-commit`.
AUTRE_TETE = "f" * 40
TRUNK_EXTRAIT = "3e249191535972bb22dd506ee71d56d9b2b08247"
MAIN_AU_GO = "155b355b0ea3332b2f79d3e49291e4e3b1a653d1"
BACK = "Back — audit, lint, format, types, tests"
INFRA = "Infra — configuration Compose, images, tests des images, scan"
CHECKOUT = "Run actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"

RUN_JSON = ("gh", "run", "view", RUN, "--json", "status,headSha,jobs")
RUN_LOG = ("gh", "run", "view", RUN, "--log")
REV_PARSE = ("git", "rev-parse", "--verify", "refs/remotes/origin/main")
PR_VIEW = ("gh", "pr", "view", "94", "--json", "body,comments,reviews")

# Les lignes du journal de chaque job, sans leurs deux premiers champs ; le checkout est la
# dernière.
TRACE_BACK = (
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
TRACE_INFRA = (
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
    return "".join(f"{job}\t{CHECKOUT}\t{texte}\n" for job, texte in lignes).encode()


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


def forge_du_run(
    jobs: Reply | None = None,
    log: Reply | None = None,
    git: Reply | None = None,
    origin: str = MAIN_AU_GO,
) -> Forge:
    """La forge du run 40769309165, `origin/main` à `origin` ; une réponse donnée — `jobs`, `log`,
    ou `git` pour `git rev-parse` — remplace la réponse réelle."""
    return Forge(
        {
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
    [(MAIN_AU_GO, 1, "périmé"), (TRUNK_EXTRAIT, 0, "à jour")],
    ids=["main-avance-a-155b355", "main-au-trunk-extrait"],
)
def test_la_trace_du_run_40769309165_rend_le_trunk_que_ses_jobs_ont_extrait(
    origin: str, code: int, fraicheur: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """L'incident de la PR #185 : la référence relue avait pour parents `155b355` / `8d0200c`,
    mais les deux jobs du run ont extrait `009f459`, fusion de `8d0200c` dans `3e24919`.
    `155b355` n'a jamais été éprouvé : contre lui, la porte sort en 1 ; le témoin, `origin/main`
    au trunk extrait, en 0."""
    forge = forge_du_run(origin=origin)

    assert lance(forge, *TRUNK) == code
    assert forge.appels == [RUN_JSON, RUN_LOG, REV_PARSE]
    assert stdout_lines(capsys) == [
        f"{BACK} : extrait 009f459, trunk {TRUNK_EXTRAIT} — {fraicheur}",
        f"{INFRA} : extrait 009f459, trunk {TRUNK_EXTRAIT} — {fraicheur}",
        (
            f"trunk éprouvé {TRUNK_EXTRAIT} — run {RUN}, extrait 009f459 : {fraicheur}"
            f" (origin/main = {origin})"
        ),
    ]


def test_deux_jobs_aux_trunks_differents_rendent_le_run_perime(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un job à jour ne rattrape pas l'autre : le run n'a pas éprouvé un état combiné unique."""
    autre_base = (
        f"2026-10-28T21:11:30.0709772Z HEAD is now at 1a2b3c4 Merge {TETE} into {MAIN_AU_GO}"
    )
    infra = (*TRACE_INFRA[:-1], autre_base)
    forge = forge_du_run(log=success(journal(infra=infra)))

    assert lance(forge, *TRUNK) == 1
    assert stdout_lines(capsys) == [
        f"{BACK} : extrait 009f459, trunk {TRUNK_EXTRAIT} — périmé",
        f"{INFRA} : extrait 1a2b3c4, trunk {MAIN_AU_GO} — à jour",
        (
            f"trunk éprouvé {TRUNK_EXTRAIT}, {MAIN_AU_GO} — run {RUN}, extrait 009f459, 1a2b3c4 :"
            f" périmé (origin/main = {MAIN_AU_GO})"
        ),
    ]


def sans_jobs_qui_tournent() -> dict[str, Any]:
    """Le run, chacun de ses jobs sauté."""
    run = jobs_du_run()
    for job in run["jobs"]:
        job["conclusion"] = "skipped"
    return run


# Le checkout d'un commit nu, sans fusion : la forme que `git checkout <sha>` écrit.
COMMIT_NU = (
    "2026-10-28T21:07:49.3773653Z HEAD is now at 8d0200c feat(pipeline): lit la trace du run"
)
# Un checkout qui fusionne au trunk une autre tête que celle du run.
CHECKOUT_AUTRE_TETE = (
    f"2026-10-28T21:07:49.3773653Z HEAD is now at 1a2b3c4 Merge {AUTRE_TETE} into {TRUNK_EXTRAIT}"
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
    "job-sans-checkout": (
        {"log": success(journal(infra=TRACE_INFRA[:-1]))},
        f"job « {INFRA} » : 0 lignes",
    ),
    "job-a-deux-checkouts": (
        {"log": success(journal(back=(*TRACE_BACK, TRACE_BACK[-1])))},
        f"job « {BACK} » : 2 lignes",
    ),
    "checkout-d-un-commit-nu": (
        {"log": success(journal(back=(*TRACE_BACK[:-1], COMMIT_NU)))},
        "hors de la forme `Merge <tête> into <trunk>`",
    ),
    "checkout-d-une-autre-tete-que-celle-du-run": (
        {"log": success(journal(back=(*TRACE_BACK[:-1], CHECKOUT_AUTRE_TETE)))},
        f"extrait la tête {AUTRE_TETE}, pas le headSha du run {TETE}",
    ),
    "jobs-hors-json": ({"jobs": success(b"<html>")}, "ne rend pas du JSON"),
    "gh-en-echec": ({"jobs": failure(b"HTTP 502")}, "a échoué (1) : HTTP 502"),
    "gh-absent": ({"jobs": FileNotFoundError("gh introuvable")}, "`gh` ne se lance pas"),
    "journal-en-echec": ({"log": failure(b"log not found")}, "a échoué (1) : log not found"),
    "git-en-echec": (
        {"git": failure(b"fatal: Needed a single revision")},
        "`git rev-parse --verify refs/remotes/origin/main` a échoué (1)",
    ),
    "git-absent": ({"git": FileNotFoundError("git introuvable")}, "`git` ne se lance pas"),
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
    `--match-head-commit` ; `<base>` lié au trunk que chaque job a fusionné ; `<PR>` lié au
    relevé de son propre body ; l'aide en 2. `--releve` sort en 0 sur une conversation changée :
    c'est un mode, liée à rien à dessein, qui ne se chaîne jamais par `&&`."""
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
        (["--help"], 2, "stdout", "le trunk que le run a réellement extrait"),
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
