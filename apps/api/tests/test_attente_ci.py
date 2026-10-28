"""Tests de l'attente de la CI du SHA de tête (`.claude/skills/cycle-pr/scripts/attente-ci.py`).

Le script lit la forge par une seule fonction, `run`, et le temps par deux, l'horloge monotone et
l'attente : ces tests les remplacent par une forge et une horloge témoins, et ne dorment jamais.
La forge rend l'état d'une PR à l'instant de son horloge — sa tête et son état draft, les runs de
chaque SHA, apparus, en cours ou terminés — et lève sur toute commande qu'elle n'attend pas.
`gh run watch` y avance l'horloge jusqu'à la fin du run, ou jusqu'au `timeout` reçu qu'il lève
alors, comme `subprocess.run` : le processus tué, puis `TimeoutExpired`. Les réponses ont la forme
que la session PR du lot 4b de #134 a mesurée (gh 2.94.0, le 2026-10-21), réduites aux champs que
le script lit. Les cas s'écrivent en littéraux, jamais dérivés des constantes du script
(`cycle-pr` 3.1).
"""

import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

import pytest
from command_doubles import ABSENT, Reply, altered, failure, json_success, stdout_lines, success
from skill_scripts import load_script, run_in_pipe

attente_ci = load_script("cycle-pr", "attente-ci")

PR = "144"
SHA = "9fb8d6a3cbaa52cea6ab0f36bd93891a3e6eb0ca"
AUTRE_SHA = "c7a23ca5d1e0f9b8a7c6d5e4f3a2b1c0d9e8f7a6"
RUNS_DU_SHA = "repos/{owner}/{repo}/actions/runs?head_sha="
EVENEMENT = "&event=pull_request"
# Au-delà, la forge témoin tient le script pour une boucle serrée : il la relit sans attendre.
LIMITE_D_APPELS = 500


class Horloge:
    """L'horloge monotone et l'attente du script : `dort` avance le temps sans dormir."""

    def __init__(self) -> None:
        self.maintenant = 0.0
        self.attentes: list[float] = []

    def __call__(self) -> float:
        return self.maintenant

    def dort(self, secondes: float) -> None:
        self.attentes.append(secondes)
        self.maintenant += secondes


class RunCi(NamedTuple):
    """Un run de la forge témoin sur le SHA `sha` : absent de l'API avant `apparait`, en cours
    jusqu'à `fin` — toujours, pour `None` —, puis terminé sur `conclusion`. Un job est
    (nom, conclusion)."""

    id: int
    sha: str = SHA
    created_at: str = "2026-10-21T07:57:43Z"
    conclusion: str = "success"
    apparait: float = 0.0
    fin: float | None = 0.0
    name: str = "CI"
    jobs: tuple[tuple[str, str], ...] = ()


class Appel(NamedTuple):
    """Une commande reçue par la forge témoin, à l'instant de son horloge."""

    instant: float
    cmd: tuple[str, ...]
    timeout: float | None


class Forge:
    """Une forge témoin, lue à l'instant de son horloge.

    Elle rend la tête de la PR 144 — le dernier SHA de `tetes` dont l'instant est passé — et son
    état `draft`, les runs visibles d'un SHA dans l'ordre de `runs`, et les jobs d'un run. Chaque
    lecture avance l'horloge de `cout`. `gh run watch` attend la fin du run, ou lève
    `TimeoutExpired` au bout du `timeout` ; il rend 0 sur `success` et 1 sinon, comme
    `--exit-status` — mesuré sur `success`, `failure` et `skipped` —, sauf `code_watch`, et rend
    la main tout de suite en 1 avec `watch_immediat`.

    Args:
        intervalle: l'intervalle attendu dans `gh run watch -i`.
        remplace: la réponse d'un genre de commande — `tete`, `runs`, `watch` ou `jobs` —, une
            `OSError` levée comme un `gh` introuvable.
        retouche: ce qu'un genre de commande fait de son document avant de le rendre.
    """

    def __init__(
        self,
        *runs: RunCi,
        tetes: Sequence[tuple[float, str]] = ((0.0, SHA),),
        draft: bool = False,
        intervalle: str = "30",
        cout: float = 0.0,
        code_watch: int | None = None,
        watch_immediat: bool = False,
        remplace: Mapping[str, Reply] | None = None,
        retouche: Mapping[str, Callable[[Any], Any]] | None = None,
    ) -> None:
        self.horloge = Horloge()
        self.runs = runs
        self.tetes = tetes
        self.draft = draft
        self.intervalle = intervalle
        self.cout = cout
        self.code_watch = code_watch
        self.watch_immediat = watch_immediat
        self.remplace = remplace or {}
        self.retouche = retouche or {}
        self.appels: list[Appel] = []

    def __call__(
        self, cmd: Sequence[str], timeout: float | None
    ) -> subprocess.CompletedProcess[bytes]:
        cmd = tuple(cmd)
        self.appels.append(Appel(self.horloge(), cmd, timeout))
        assert len(self.appels) <= LIMITE_D_APPELS, "boucle serrée : la forge relue sans attendre"
        genre = self.genre(cmd)
        reponse = self.remplace.get(genre)
        if isinstance(reponse, OSError):
            raise reponse
        if reponse is not None:
            return reponse
        if genre == "watch":
            return self.watch(cmd, timeout)
        contenu = self.contenu(genre, cmd)
        self.horloge.maintenant += self.cout
        return json_success(self.retouche.get(genre, lambda brut: brut)(contenu))

    def genre(self, cmd: tuple[str, ...]) -> str:
        """Le genre d'une commande attendue ; toute autre lève."""
        match cmd:
            case ("gh", "pr", "view", "144", "--json", "headRefOid,isDraft"):
                return "tete"
            case ("gh", "api", chemin) if chemin.startswith(RUNS_DU_SHA) and chemin.endswith(
                EVENEMENT
            ):
                return "runs"
            case ("gh", "run", "watch", _, "--exit-status", "-i", intervalle) if (
                intervalle == self.intervalle
            ):
                return "watch"
            case ("gh", "run", "view", _, "--json", "jobs"):
                return "jobs"
            case _:
                raise AssertionError(f"commande inattendue : {cmd}")

    def tete(self) -> str:
        """Le dernier SHA de `tetes` dont l'instant est passé."""
        return [sha for instant, sha in self.tetes if instant <= self.horloge()][-1]

    def run(self, identifiant: str) -> RunCi:
        """Le run de la forge qui porte cet identifiant."""
        return next(run for run in self.runs if str(run.id) == identifiant)

    def etat(self, run: RunCi) -> dict[str, Any]:
        """Un run tel que l'API le rend à cet instant, réduit aux champs que le script lit."""
        termine = run.fin is not None and run.fin <= self.horloge()
        return {
            "id": run.id,
            "name": run.name,
            "status": "completed" if termine else "in_progress",
            "conclusion": run.conclusion if termine else None,
            "created_at": run.created_at,
        }

    def contenu(self, genre: str, cmd: tuple[str, ...]) -> Any:
        """Le document qu'une lecture rend à cet instant, avant toute retouche."""
        if genre == "tete":
            return {"headRefOid": self.tete(), "isDraft": self.draft}
        if genre == "runs":
            sha = cmd[2].removeprefix(RUNS_DU_SHA).removesuffix(EVENEMENT)
            visibles = [
                self.etat(run)
                for run in self.runs
                if run.sha == sha and run.apparait <= self.horloge()
            ]
            return {"total_count": len(visibles), "workflow_runs": visibles}
        jobs = self.run(cmd[3]).jobs
        return {"jobs": [{"name": nom, "conclusion": fin} for nom, fin in jobs]}

    def watch(
        self, cmd: tuple[str, ...], timeout: float | None
    ) -> subprocess.CompletedProcess[bytes]:
        """`gh run watch` : la fin du run, ou `TimeoutExpired` au bout du `timeout` reçu."""
        if self.watch_immediat:
            return failure(b"HTTP 502: Bad Gateway\n")
        assert timeout is not None, "`gh run watch` sans timeout"
        run = self.run(cmd[3])
        if run.fin is None or run.fin > self.horloge() + timeout:
            self.horloge.maintenant += timeout
            raise subprocess.TimeoutExpired(list(cmd), timeout)
        self.horloge.maintenant = max(self.horloge(), run.fin)
        code = self.code_watch
        if code is None:
            code = 0 if run.conclusion == "success" else 1
        fin = f"Run CI ({run.id}) has already completed with '{run.conclusion}'\n"
        return subprocess.CompletedProcess(list(cmd), code, stdout=fin.encode(), stderr=b"")

    def appels_de(self, genre: str) -> list[Appel]:
        """Les commandes reçues de ce genre, dans l'ordre."""
        return [appel for appel in self.appels if self.genre(appel.cmd) == genre]

    def instants(self, genre: str) -> list[float]:
        """Les instants des commandes de ce genre, dans l'ordre."""
        return [appel.instant for appel in self.appels_de(genre)]


def lance(forge: Forge, *args: str) -> int:
    """Le script tel que la session l'appelle, sur la forge et l'horloge témoins."""
    return attente_ci.main(list(args), run=forge, clock=forge.horloge, sleep=forge.horloge.dort)


def test_un_run_vert_rend_vert_en_sortie_0(capsys: pytest.CaptureFixture[str]) -> None:
    forge = Forge(RunCi(39565701629))

    assert lance(forge, PR) == 0
    assert stdout_lines(capsys) == ["vert — run 39565701629 sur 9fb8d6a → cycle-pr Étape 6"]


# Les jobs d'un run rouge, un par conclusion de l'API REST (« Workflow jobs », schéma `job`), plus
# `startup_failure`, hors de l'énumération.
JOBS_DU_ROUGE = (
    ("Back — audit, lint, format, types, tests", "failure"),
    ("Front — lint, types, tests, build, e2e, lighthouse, audit", "success"),
    ("Infra — configuration Compose, images, tests des images, scan", "timed_out"),
    ("Publication — images sur GHCR", "skipped"),
    ("Déploiement — production par SSH", "cancelled"),
    ("Docs", "neutral"),
    ("Revue", "action_required"),
    ("Démarrage", "startup_failure"),
)


def test_un_run_rouge_nomme_ses_jobs_en_echec_et_renvoie_a_erreurs_ci(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un job est en échec quand sa conclusion n'est ni `success`, ni `skipped`, ni `cancelled`,
    ni `neutral` — la règle d'`erreurs-ci.py`, vers qui la ligne renvoie ; une conclusion hors de
    l'énumération de l'API compte en échec, jamais en silence."""
    forge = Forge(RunCi(4242, conclusion="failure", jobs=JOBS_DU_ROUGE))

    assert lance(forge, PR) == 1
    assert stdout_lines(capsys) == [
        (
            "rouge — run 4242 sur 9fb8d6a, conclusion failure, jobs en échec :"
            " Back — audit, lint, format, types, tests (failure),"
            " Infra — configuration Compose, images, tests des images, scan (timed_out),"
            " Revue (action_required), Démarrage (startup_failure)"
            " → erreurs-ci.py 4242, puis cycle-pr Étape 6, « Trier un rouge »"
        )
    ]


@pytest.mark.parametrize(
    "conclusion", ["failure", "timed_out", "startup_failure", "action_required", "neutral", "stale"]
)
def test_toute_conclusion_autre_que_vert_saute_ou_annule_est_un_rouge(
    conclusion: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Les conclusions d'un run que l'API REST énumère (« Workflow runs », paramètre `status`),
    `success`, `skipped` et `cancelled` exceptées, et `startup_failure`, qu'elle n'énumère pas ;
    un run sans job en échec le dit."""
    forge = Forge(RunCi(4242, conclusion=conclusion))

    assert lance(forge, PR) == 1
    assert stdout_lines(capsys) == [
        (
            f"rouge — run 4242 sur 9fb8d6a, conclusion {conclusion}, jobs en échec : aucun"
            " → erreurs-ci.py 4242, puis cycle-pr Étape 6, « Trier un rouge »"
        )
    ]


def test_une_pr_encore_en_draft_rend_draft_en_sortie_3_sans_lire_les_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Une draft n'a aucun run (ADR 0019) : l'attendre jusqu'au délai ne servirait à rien, même
    avec un run vert d'avant un retour en draft. L'appel qui lit la tête le dit, et le script
    renvoie à `gh pr ready` sans lire les runs."""
    forge = Forge(RunCi(4242), draft=True)

    assert lance(forge, PR) == 3
    assert stdout_lines(capsys) == [
        "draft — PR 144 encore en draft sur 9fb8d6a → gh pr ready 144 d'abord, cycle-pr Étape 5"
    ]
    assert forge.appels_de("runs") == []


def test_le_run_saute_d_un_push_en_draft_fait_attendre_celui_du_passage_en_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """La course au passage en ready : sitôt `gh pr ready`, le run le plus récent du SHA est
    encore le `skipped` d'un push en draft, et celui de `ready_for_review` n'apparaît qu'après.
    Le script relit le saut comme « aucun run », puis attend le nouveau jusqu'à son verdict."""
    forge = Forge(
        RunCi(4242, created_at="2026-10-21T07:57:43Z", conclusion="skipped"),
        RunCi(4343, created_at="2026-10-21T08:12:05Z", apparait=45.0, fin=100.0),
    )

    assert lance(forge, PR) == 0
    assert stdout_lines(capsys) == ["vert — run 4343 sur 9fb8d6a → cycle-pr Étape 6"]
    assert forge.instants("runs") == [0.0, 30.0, 60.0, 100.0]


def test_un_run_saute_jusqu_au_delai_rend_saute_en_sortie_3(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """La draft jamais repoussée : la PR est sortie du draft, mais son seul run reste le `skipped`
    d'un push en draft, sans run du passage en ready. Relu comme « aucun run » toutes les
    `intervalle` secondes, il rend « sauté » au délai, et la session suit « Si aucun run
    n'apparaît »."""
    forge = Forge(RunCi(39565701629, conclusion="skipped"))

    assert lance(forge, PR, "--delai", "75") == 3
    assert stdout_lines(capsys) == [
        (
            "sauté — run 39565701629 sur 9fb8d6a, aucun run du passage en ready en 75 s"
            " → cycle-pr Étape 5, « Si aucun run n'apparaît »"
        )
    ]
    assert forge.instants("runs") == [0.0, 30.0, 60.0, 75.0]


def test_un_run_annule_sans_nouvelle_tete_rend_annule_sans_remplacant(
    capsys: pytest.CaptureFixture[str],
) -> None:
    forge = Forge(RunCi(4242, conclusion="cancelled"))

    assert lance(forge, PR) == 3
    assert stdout_lines(capsys) == [
        (
            "annulé sans remplaçant — run 4242 sur 9fb8d6a"
            " → cycle-pr Étape 5, « Si aucun run n'apparaît »"
        )
    ]


def test_un_run_annule_par_un_nouveau_push_fait_suivre_la_nouvelle_tete(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`concurrency` annule le run d'une PR quand un push arrive. Ici, le push tombe entre la
    lecture de la tête et celle des runs — chaque lecture dure une seconde : le run lu est
    annulé, la tête relue a changé, et la boucle suit la nouvelle tête jusqu'à son verdict."""
    forge = Forge(
        RunCi(4242, conclusion="cancelled", fin=0.5),
        RunCi(4343, sha=AUTRE_SHA, created_at="2026-10-21T07:58:01Z", apparait=0.5, fin=0.5),
        tetes=((0.0, SHA), (0.5, AUTRE_SHA)),
        cout=1.0,
    )

    assert lance(forge, PR) == 0
    assert stdout_lines(capsys) == ["vert — run 4343 sur c7a23ca → cycle-pr Étape 6"]


def test_aucun_run_jusqu_au_delai_rend_aucun_run_en_sortie_3(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un run apparaît quelques secondes après son événement, push ou passage en ready : sans run,
    le script relit toutes les `intervalle` secondes, la dernière attente raccourcie pour tomber au
    délai, où il rend son verdict — un événement émis pendant une panne d'Actions n'est pas
    rejoué."""
    forge = Forge()

    assert lance(forge, PR, "--delai", "75") == 3
    assert stdout_lines(capsys) == [
        (
            "aucun run — aucun run CI sur 9fb8d6a en 75 s"
            " → cycle-pr Étape 5, « Si aucun run n'apparaît »"
        )
    ]
    assert forge.instants("runs") == [0.0, 30.0, 60.0, 75.0]


def test_un_run_qui_apparait_puis_tourne_est_attendu_jusqu_a_son_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sans run, le script relit toutes les `--intervalle` secondes ; un run qui tourne, il
    l'attend par `gh run watch`, au même intervalle, borné par le temps qui reste, puis relit."""
    forge = Forge(RunCi(4242, apparait=25.0, fin=100.0), intervalle="10")

    assert lance(forge, PR, "--intervalle", "10") == 0
    assert stdout_lines(capsys) == ["vert — run 4242 sur 9fb8d6a → cycle-pr Étape 6"]
    assert forge.horloge.attentes == [10.0, 10.0, 10.0]
    assert forge.appels_de("watch") == [
        Appel(30.0, ("gh", "run", "watch", "4242", "--exit-status", "-i", "10"), 1770.0)
    ]


def test_un_run_qui_tourne_jusqu_au_delai_sort_en_124(capsys: pytest.CaptureFixture[str]) -> None:
    """`gh run watch` reçoit pour `timeout` le temps qui reste — ici 596 s, chaque lecture durant
    deux secondes — et le processus est tué au délai ; la relecture qui suit trouve le run encore
    en cours : délai dépassé, Étape 6, « CI qui ne démarre pas »."""
    forge = Forge(RunCi(4242, fin=None), cout=2.0)

    assert lance(forge, PR, "--delai", "600") == 124
    assert stdout_lines(capsys) == [
        (
            "délai dépassé — run 4242 sur 9fb8d6a encore in_progress après 600 s"
            " → cycle-pr Étape 6, « CI qui ne démarre pas »"
        )
    ]
    assert [appel.timeout for appel in forge.appels_de("watch")] == [596.0]


def test_le_code_de_sortie_de_watch_ne_decide_pas_du_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Mesuré le 2026-10-21 (gh 2.94.0) : `gh run watch --exit-status` sort en 1 sur `failure`
    comme sur `skipped`, son code ne distingue pas un rouge d'un saut. Le verdict se lit dans
    l'API : un `watch` qui sort en 1 sur un run devenu vert rend vert."""
    forge = Forge(RunCi(4242, fin=50.0), code_watch=1)

    assert lance(forge, PR) == 0
    assert stdout_lines(capsys) == ["vert — run 4242 sur 9fb8d6a → cycle-pr Étape 6"]


def test_un_watch_qui_rend_la_main_tout_de_suite_ne_fait_pas_relire_sans_attendre(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un `gh run watch` en échec — ici un 502 — rend la main sans attendre le run : au moins
    `intervalle` secondes séparent encore deux lectures d'un run qui tourne, sauf la dernière,
    qui tombe au délai."""
    forge = Forge(RunCi(4242, fin=None), watch_immediat=True)

    assert lance(forge, PR, "--delai", "75") == 124
    assert forge.instants("runs") == [0.0, 30.0, 60.0, 75.0]
    assert stdout_lines(capsys) == [
        (
            "délai dépassé — run 4242 sur 9fb8d6a encore in_progress après 75 s"
            " → cycle-pr Étape 6, « CI qui ne démarre pas »"
        )
    ]


# Le passage en ready ajoute un run sur la même tête : le run sauté d'un push en draft, puis le run
# vert de `ready_for_review`. L'identifiant du plus récent est ici le plus petit — c'est
# `created_at` qui décide.
SAUTE_EN_DRAFT = RunCi(4343, created_at="2026-10-21T07:57:43Z", conclusion="skipped")
VERT_AU_READY = RunCi(4242, created_at="2026-10-21T08:12:05Z")
ORDRES_DE_L_API = {
    "plus-recent-d-abord": (VERT_AU_READY, SAUTE_EN_DRAFT),
    "plus-ancien-d-abord": (SAUTE_EN_DRAFT, VERT_AU_READY),
}


@pytest.mark.parametrize("runs", ORDRES_DE_L_API.values(), ids=ORDRES_DE_L_API.keys())
def test_le_run_le_plus_recent_par_created_at_decide_quel_que_soit_l_ordre_de_l_api(
    runs: tuple[RunCi, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance(Forge(*runs), PR) == 0
    assert stdout_lines(capsys) == ["vert — run 4242 sur 9fb8d6a → cycle-pr Étape 6"]


# `created_at` est à la seconde : deux runs créés dans la même seconde se départagent par
# l'identifiant, le plus grand tenu pour le plus récent. Que GitHub les attribue en croissant n'est
# pas documenté : c'est le cas des quatre runs de ce dépôt relevés le 2026-10-21, de 39165399343,
# créé le 18, à 39590091961, créé le 21.
CREES_A_LA_MEME_SECONDE = {
    "plus-grand-d-abord": (RunCi(4343), RunCi(4242, conclusion="skipped")),
    "plus-petit-d-abord": (RunCi(4242, conclusion="skipped"), RunCi(4343)),
}


@pytest.mark.parametrize(
    "runs", CREES_A_LA_MEME_SECONDE.values(), ids=CREES_A_LA_MEME_SECONDE.keys()
)
def test_deux_runs_crees_a_la_meme_seconde_sont_departages_par_l_identifiant(
    runs: tuple[RunCi, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance(Forge(*runs), PR) == 0
    assert stdout_lines(capsys) == ["vert — run 4343 sur 9fb8d6a → cycle-pr Étape 6"]


def test_un_run_d_un_autre_workflow_est_ignore(capsys: pytest.CaptureFixture[str]) -> None:
    forge = Forge(
        RunCi(4242, created_at="2026-10-21T07:57:43Z"),
        RunCi(4343, created_at="2026-10-21T07:58:01Z", conclusion="failure", name="Revue"),
    )

    assert lance(forge, PR) == 0
    assert stdout_lines(capsys) == ["vert — run 4242 sur 9fb8d6a → cycle-pr Étape 6"]


def test_sans_option_le_delai_vaut_1800_s_et_l_intervalle_30_s(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Les valeurs de l'intérim du lot 3, décidé par le mainteneur :
    `timeout 1800 gh run watch <id> --exit-status -i 30`."""
    forge = Forge()

    assert lance(forge, PR) == 3
    assert stdout_lines(capsys) == [
        (
            "aucun run — aucun run CI sur 9fb8d6a en 1800 s"
            " → cycle-pr Étape 5, « Si aucun run n'apparaît »"
        )
    ]
    assert forge.horloge.attentes == [30.0] * 60


# (réponses remplacées par genre de commande, runs de la forge, motif attendu)
REFUS: dict[str, tuple[dict[str, Reply], tuple[RunCi, ...], str]] = {
    "tete-en-panne": (
        {"tete": failure(b"GraphQL: Could not resolve to a PullRequest with the number of 144.\n")},
        (),
        (
            "`gh pr view 144 --json headRefOid,isDraft` a échoué (1) :"
            " GraphQL: Could not resolve to a PullRequest with the number of 144."
        ),
    ),
    "runs-en-panne": (
        {"runs": failure(b"HTTP 502: Bad Gateway\n(https://api.github.com/...)\n")},
        (),
        (
            "`gh api repos/{owner}/{repo}/actions/runs"
            "?head_sha=9fb8d6a3cbaa52cea6ab0f36bd93891a3e6eb0ca&event=pull_request` a échoué (1) :"
            " HTTP 502: Bad Gateway (https://api.github.com/...)"
        ),
    ),
    "jobs-en-panne": (
        {"jobs": failure(b"HTTP 404: Not Found\n")},
        (RunCi(4242, conclusion="failure"),),
        "`gh run view 4242 --json jobs` a échoué (1) : HTTP 404: Not Found",
    ),
    "gh-absent": (
        {"tete": FileNotFoundError("gh introuvable")},
        (),
        "`gh` ne se lance pas : gh introuvable",
    ),
    "watch-ne-se-lance-pas": (
        {"watch": FileNotFoundError("gh introuvable")},
        (RunCi(4242, fin=None),),
        "`gh` ne se lance pas : gh introuvable",
    ),
    "reponse-non-json": (
        {"tete": success(b"<html>")},
        (),
        "`gh pr view 144 --json headRefOid,isDraft` ne rend pas du JSON UTF-8",
    ),
    # Un JSON valide, mais en cp1252 : décodé par la page de code du poste, il passerait (obs 108).
    "reponse-hors-utf-8": (
        {
            "jobs": success(
                '{"jobs": [{"name": "Déploiement", "conclusion": "failure"}]}'.encode("cp1252")
            )
        },
        (RunCi(4242, conclusion="failure"),),
        "`gh run view 4242 --json jobs` ne rend pas du JSON UTF-8",
    ),
}


@pytest.mark.parametrize(("remplace", "runs", "motif"), REFUS.values(), ids=REFUS.keys())
def test_une_lecture_gh_en_echec_sort_en_1_en_une_ligne(
    remplace: dict[str, Reply],
    runs: tuple[RunCi, ...],
    motif: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lance(Forge(*runs, remplace=remplace), PR) == 1
    (ligne,) = stdout_lines(capsys)
    assert ligne.startswith(f"refus — {motif}"), ligne


# Chaque champ que le script lit, absent puis d'un autre type : (genre de la lecture, chemin du
# champ, valeur qui le remplace — `ABSENT` le retire). Dénombré avant le code : 10 champs —
# `headRefOid` de la tête ; `workflow_runs`, puis `id`, `name`, `status`, `conclusion` et
# `created_at` d'un run ; `jobs`, puis `name` et `conclusion` d'un job —, 11 depuis que l'appel
# qui lit la tête lit aussi `isDraft` (ADR 0019) ; un texte `"false"` y serait vrai pour un
# `bool(…)`, d'où sa forme non booléenne. Plus trois documents, un run et un job qui ne sont pas
# des objets, et trois valeurs du bon type hors de leur forme : une tête qui n'est pas un SHA —
# elle entre dans la requête —, un `created_at` qui ne se trie pas, un run terminé sans conclusion.
# Une liste remplacée par un objet vide : un objet non vide ou un texte donneraient, à
# l'itération, des éléments qui lèvent déjà — ils ne verraient jamais rouge la garde de type.
FORMES: dict[str, tuple[str, tuple[str | int, ...], Any]] = {
    "tete-hors-objet": ("tete", (), [SHA]),
    "headRefOid-absent": ("tete", ("headRefOid",), ABSENT),
    "headRefOid-non-textuel": ("tete", ("headRefOid",), None),
    "headRefOid-hors-sha": ("tete", ("headRefOid",), "9fb8d6a&event=push"),
    "isDraft-absent": ("tete", ("isDraft",), ABSENT),
    "isDraft-non-booleen": ("tete", ("isDraft",), "false"),
    "runs-hors-objet": ("runs", (), []),
    "workflow_runs-absent": ("runs", ("workflow_runs",), ABSENT),
    "workflow_runs-hors-liste": ("runs", ("workflow_runs",), {}),
    "run-hors-objet": ("runs", ("workflow_runs", 0), "CI"),
    "id-absent": ("runs", ("workflow_runs", 0, "id"), ABSENT),
    "id-non-entier": ("runs", ("workflow_runs", 0, "id"), "4242"),
    "id-booleen": ("runs", ("workflow_runs", 0, "id"), True),
    "name-absent": ("runs", ("workflow_runs", 0, "name"), ABSENT),
    "name-non-textuel": ("runs", ("workflow_runs", 0, "name"), None),
    "status-absent": ("runs", ("workflow_runs", 0, "status"), ABSENT),
    "status-non-textuel": ("runs", ("workflow_runs", 0, "status"), 1),
    "conclusion-absente": ("runs", ("workflow_runs", 0, "conclusion"), ABSENT),
    "conclusion-non-textuelle": ("runs", ("workflow_runs", 0, "conclusion"), 0),
    "conclusion-nulle-sur-un-run-termine": ("runs", ("workflow_runs", 0, "conclusion"), None),
    "created_at-absent": ("runs", ("workflow_runs", 0, "created_at"), ABSENT),
    "created_at-non-textuel": ("runs", ("workflow_runs", 0, "created_at"), 1792999063),
    "created_at-hors-format": ("runs", ("workflow_runs", 0, "created_at"), "2026-10-21 07:57:43"),
    "jobs-hors-objet": ("jobs", (), []),
    "jobs-absents": ("jobs", ("jobs",), ABSENT),
    "jobs-hors-liste": ("jobs", ("jobs",), {}),
    "job-hors-objet": ("jobs", ("jobs", 0), "Back"),
    "nom-de-job-absent": ("jobs", ("jobs", 0, "name"), ABSENT),
    "nom-de-job-non-textuel": ("jobs", ("jobs", 0, "name"), 7),
    "conclusion-de-job-absente": ("jobs", ("jobs", 0, "conclusion"), ABSENT),
    "conclusion-de-job-non-textuelle": ("jobs", ("jobs", 0, "conclusion"), ["failure"]),
}

# La commande que nomme le refus, par genre de lecture.
COMMANDES = {
    "tete": "gh pr view 144 --json headRefOid,isDraft",
    "runs": (
        "gh api repos/{owner}/{repo}/actions/runs"
        "?head_sha=9fb8d6a3cbaa52cea6ab0f36bd93891a3e6eb0ca&event=pull_request"
    ),
    "jobs": "gh run view 4242 --json jobs",
}


@pytest.mark.parametrize(("genre", "chemin", "valeur"), FORMES.values(), ids=FORMES.keys())
def test_une_reponse_d_une_autre_forme_sort_en_1_en_une_ligne(
    genre: str, chemin: tuple[str | int, ...], valeur: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge(
        RunCi(
            4242,
            conclusion="failure" if genre == "jobs" else "success",
            jobs=(("Back", "failure"),),
        ),
        retouche={genre: lambda contenu: altered(contenu, chemin, valeur)},
    )

    assert lance(forge, PR) == 1
    (ligne,) = stdout_lines(capsys)
    assert ligne.startswith(f"refus — `{COMMANDES[genre]}` ne rend pas la forme attendue"), ligne


APPELS_MAL_FORMES = {
    "lettres": ("abc",),
    "chiffre-unicode": ("²",),
    "argument-absent": (),
    "delai-nul": (PR, "--delai", "0"),
    "intervalle-negatif": (PR, "--intervalle", "-30"),
    "delai-decimal": (PR, "--delai", "1.5"),
}


@pytest.mark.parametrize("args", APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys())
def test_un_appel_mal_forme_sort_en_2_sans_appeler_gh(
    args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    forge = Forge(RunCi(4242))

    assert lance(forge, *args) == 2
    assert forge.appels == []
    assert "usage" in capsys.readouterr().err


def test_le_lanceur_par_defaut_rend_les_octets_tels_quels() -> None:
    """Le défaut réel du lanceur, que la forge témoin remplace partout ailleurs : ni le mode texte
    ni la page de code de la console ne touchent ce qui sort (obs 108)."""
    octets = "Déploiement › A\r\n".encode()
    ecrit = f"import sys; sys.stdout.buffer.write({octets!r})"

    assert attente_ci.default_run([sys.executable, "-c", ecrit], None).stdout == octets


def test_le_lanceur_par_defaut_tue_la_commande_au_bout_de_son_timeout() -> None:
    """Le délai du script ne tient que si `gh run watch` est tué au bout du temps qui reste :
    `subprocess.run` tue le processus, puis lève `TimeoutExpired` (CPython, `subprocess.run`,
    lu le 2026-10-21 sur 3.12.10). La commande dormirait dix secondes ; elle est tuée en 0,2 s."""
    with pytest.raises(subprocess.TimeoutExpired):
        attente_ci.default_run([sys.executable, "-c", "import time; time.sleep(10)"], 0.2)


@pytest.mark.parametrize(
    ("args", "code", "flux", "texte"),
    [
        (["--help"], 0, "stdout", "Attend la CI du SHA de tête"),
        (["²"], 2, "stderr", "numéro de PR attendu, pas '²'"),
    ],
    ids=["aide-sur-stdout", "usage-sur-stderr"],
)
def test_la_sortie_du_script_lance_en_tube_est_en_utf_8(
    args: list[str], code: int, flux: str, texte: str
) -> None:
    """La session lit le script par un tube, où Python écrit dans la page de code du poste,
    cp1252, que `run_in_pipe` impose (`pipeline.config.md`, « Qualité ») — l'erreur
    d'argparse comprise, qui part sur la sortie d'erreur."""
    done = run_in_pipe("cycle-pr", "attente-ci", *args)

    assert done.returncode == code
    assert texte in getattr(done, flux).decode("utf-8")
