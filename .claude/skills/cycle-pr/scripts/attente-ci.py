"""Attend la CI du SHA de tête d'une PR et rend son verdict.

Usage :
    python attente-ci.py <PR> [--delai <secondes>] [--intervalle <secondes>]

`cycle-pr` Étape 5, « Avant de sortir du draft, lire le run du SHA de tête » : `gh pr ready` ne
déclenche aucun run (ADR 0017), la preuve d'une PR prête est le run de son dernier push. La
session lance ce script en fond, et sa fin la réveille. `--delai` borne l'attente, 1800 s par
défaut ; `--intervalle` espace les lectures, 30 s par défaut — les valeurs de l'intérim du lot 3
de #134, `timeout 1800 gh run watch <id> --exit-status -i 30`, décidé par le mainteneur. Deux
entiers positifs.

Jusqu'à un verdict ou au délai, chaque tour relit la tête (`gh pr view <PR> --json headRefOid`),
puis les runs de ce SHA, `{owner}/{repo}` remplis par `gh` depuis le dépôt courant :

    gh api "repos/{owner}/{repo}/actions/runs?head_sha=<sha>&event=pull_request"

Il en garde le workflow `CI` et prend le plus récent par `created_at`, trié ici — l'ordre de la
réponse n'est pas lu —, l'identifiant départageant deux créations à la même seconde. Chaque
lecture décode ses octets en UTF-8 explicitement, jamais par la page de code de la console
(obs 108). Puis :

- aucun run : relire toutes les `intervalle` secondes — le run d'un push peut n'apparaître
  qu'après la première lecture ; au délai, **aucun run** ;
- run pas terminé : `gh run watch <id> --exit-status -i <intervalle>`, tué au délai, sa sortie
  jetée et son code ignoré — il sort en 1 sur `failure` comme sur `skipped` (mesuré le
  2026-10-21, gh 2.94.0) —, puis relire ; au moins `intervalle` secondes entre deux lectures d'un
  run qui tourne, sauf la dernière, qui tombe au délai. Délai atteint, run en cours : **délai
  dépassé** ;
- `success` : **vert** ;
- `cancelled` : relire la tête — `concurrency` annule le run d'une PR quand un push arrive. Changée,
  la boucle suit la nouvelle ; inchangée : **annulé sans remplaçant** ;
- `skipped` : **sauté** — l'ouverture d'une draft, que le garde du job `api` saute ;
- toute autre conclusion : **rouge**, avec ses jobs en échec, nom et conclusion
  (`gh run view <id> --json jobs`) — ni `success`, ni `skipped`, ni `cancelled`, ni `neutral`,
  la règle d'`erreurs-ci.py`, vers qui la ligne renvoie.

Une seule ligne sur la sortie standard, `<verdict> — run <id> sur <SHA court>[, détail] →
<suite>`, la suite nommant le paragraphe de `cycle-pr` à suivre : vert, sortir du draft (Étape 5) ;
rouge, `erreurs-ci.py <id>` puis Étape 6, « Trier un rouge » ; aucun run, sauté, annulé sans
remplaçant, Étape 5, « Si aucun run n'apparaît » ; délai dépassé, Étape 6, « CI qui ne démarre
pas ».

**Ce qu'il ne couvre pas.** Les autres workflows et les autres événements que `pull_request`. Ce
que le run a combiné : la référence de fusion, calculée à son push, se lit à l'Étape 7. La page
d'état de GitHub et la réouverture de la PR, qui restent à la session et au mainteneur (Étape 5,
« Si aucun run n'apparaît »). Un run relancé : l'API rend sa dernière tentative et garde son
`created_at` — 39559119382, relancé une fois, y porte `run_attempt` 2 et le `run_started_at` de la
tentative 2, dans la liste par `head_sha` comme seul (mesuré le 2026-10-21) ; relancé quand un run
plus récent existe sur le même SHA, il ne décide pas.

Sortie : 0 vert ; 1 rouge, ou refus (« refus — ») — une lecture `gh` qui ne se lance pas, échoue,
ne rend pas du JSON UTF-8 ou pas la forme attendue —, motif en une ligne ; 2 appel mal formé,
usage sur la sortie d'erreur ; 3 aucun run, sauté, ou annulé sans remplaçant ; 124 délai dépassé,
le code de `timeout`. Python 3.11 ou plus, bibliothèque standard seule ; `gh` authentifié, lancé
depuis le dépôt.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

Run = Callable[[Sequence[str], float | None], subprocess.CompletedProcess[bytes]]
Clock = Callable[[], float]
Sleep = Callable[[float], None]

WORKFLOW = "CI"
# `str.isdigit` accepte « ² » : le numéro, qui entre dans une commande, se lit en ASCII.
NUMBER = re.compile(r"[0-9]+")
# La tête entre dans la requête des runs : un SHA hexadécimal, rien d'autre.
SHA = re.compile(r"[0-9a-f]{40}")
# La forme que l'API rend, mesurée ; seule, elle se trie comme le temps qu'elle écrit.
CREATED_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
NOT_FAILED = frozenset({"success", "skipped", "cancelled", "neutral"})
NO_RUN = "cycle-pr Étape 5, « Si aucun run n'apparaît »"


class Refusal(Exception):
    """Une lecture de la forge inutilisable ; le message est le motif, en une ligne."""


class WorkflowRun(NamedTuple):
    """Un run, tel que l'API des runs le rend ; `conclusion` est nulle tant qu'il tourne."""

    id: int
    name: str
    status: str
    conclusion: str | None
    created_at: str


class Verdict(NamedTuple):
    """La ligne rendue et le code de sortie."""

    line: str
    code: int


def default_run(cmd: Sequence[str], timeout: float | None) -> subprocess.CompletedProcess[bytes]:
    """Lance `cmd` et capture ses sorties **en octets** (obs 108). `timeout` passé, le processus
    est tué, puis `subprocess.TimeoutExpired` levée."""
    return subprocess.run(list(cmd), capture_output=True, check=False, timeout=timeout)


def launch(
    run: Run, args: Sequence[str], timeout: float | None = None
) -> subprocess.CompletedProcess[bytes]:
    """`gh <args>`, son code de sortie non lu.

    Raises:
        Refusal: `gh` ne se lance pas.
        subprocess.TimeoutExpired: `timeout` passé.
    """
    try:
        return run(("gh", *args), timeout)
    except OSError as error:
        raise Refusal(f"`gh` ne se lance pas : {error}") from error


def read_json(run: Run, parse: Callable[[Any], Any], *args: str) -> Any:
    """Ce que `parse` tire du JSON que rend `gh <args>`, décodé en UTF-8 explicitement (obs 108).

    Args:
        parse: tire du document les champs attendus ; un champ absent, d'un autre type ou d'une
            autre forme y lève `KeyError`, `TypeError` ou `ValueError`.

    Raises:
        Refusal: la commande ne se lance pas, sort autrement qu'en 0, ne rend pas du JSON UTF-8,
            ou pas la forme que `parse` attend.
    """
    command = " ".join(("gh", *args))
    done = launch(run, args)
    if done.returncode != 0:
        motif = " ".join(done.stderr.decode("utf-8", "replace").split())
        raise Refusal(f"`{command}` a échoué ({done.returncode}) : {motif}")
    try:
        document = json.loads(done.stdout.decode("utf-8"))
    except ValueError as error:
        raise Refusal(f"`{command}` ne rend pas du JSON UTF-8 : {error}") from error
    try:
        return parse(document)
    except (KeyError, TypeError, ValueError) as error:
        raise Refusal(
            f"`{command}` ne rend pas la forme attendue : {type(error).__name__} {error}"
        ) from error


def field(document: Any, name: str, kind: type[object]) -> Any:
    """Le champ `name` de `document`, exactement de type `kind` — un booléen n'est pas un entier.

    Raises:
        KeyError, TypeError: `document` n'est pas un objet, n'a pas le champ, ou le champ est
            d'un autre type.
    """
    value = document[name]
    if type(value) is not kind:
        raise TypeError(f"`{name}` de type {type(value).__name__}")
    return value


def head_of(document: Any) -> str:
    """La tête que rend `gh pr view --json headRefOid`.

    Raises:
        KeyError, TypeError, ValueError: comme `field`, ou une tête qui n'est pas un SHA.
    """
    sha = field(document, "headRefOid", str)
    if not SHA.fullmatch(sha):
        raise ValueError(f"`headRefOid` n'est pas un SHA : {sha!r}")
    return sha


def workflow_run(document: Any) -> WorkflowRun:
    """Un run de l'API des runs ; ses cinq champs lus, gardés en présence, type et forme.

    Raises:
        KeyError, TypeError, ValueError: comme `field`, un `created_at` hors de sa forme, ou un
            run terminé sans conclusion.
    """
    status = field(document, "status", str)
    running = document["conclusion"] is None and status != "completed"
    created_at = field(document, "created_at", str)
    if not CREATED_AT.fullmatch(created_at):
        raise ValueError(f"`created_at` hors de la forme AAAA-MM-JJTHH:MM:SSZ : {created_at!r}")
    return WorkflowRun(
        field(document, "id", int),
        field(document, "name", str),
        status,
        None if running else field(document, "conclusion", str),
        created_at,
    )


def ci_runs(document: Any) -> list[WorkflowRun]:
    """Les runs du workflow `CI` que rend l'API des runs."""
    runs: list[Any] = field(document, "workflow_runs", list)
    return [ci for ci in map(workflow_run, runs) if ci.name == WORKFLOW]


def failed_jobs(document: Any) -> list[str]:
    """Les jobs en échec que rend `gh run view --json jobs`, `<nom> (<conclusion>)` chacun, dans
    l'ordre du JSON : ni `success`, ni `skipped`, ni `cancelled`, ni `neutral`.

    Raises:
        KeyError, TypeError: comme `field`, pour un job.
    """
    jobs: list[Any] = field(document, "jobs", list)
    named = [(field(job, "name", str), field(job, "conclusion", str)) for job in jobs]
    return [f"{name} ({conclusion})" for name, conclusion in named if conclusion not in NOT_FAILED]


def head(run: Run, pr: str) -> str:
    """Le SHA de tête de la PR `pr`."""
    return read_json(run, head_of, "pr", "view", pr, "--json", "headRefOid")


def latest(run: Run, sha: str) -> WorkflowRun | None:
    """Le run `CI` le plus récent du SHA `sha` par `created_at`, l'identifiant départageant deux
    créations à la même seconde — l'ordre de la réponse n'est pas lu ; `None` sans run."""
    # ponytail: la première page seule, 30 runs par défaut — elle porte le plus récent tant que
    # l'API rend du plus récent au plus ancien (mesuré les 2026-10-20 et 2026-10-21) ;
    # `&per_page=100` le jour où un SHA dépasse 30 runs `pull_request`.
    path = f"repos/{{owner}}/{{repo}}/actions/runs?head_sha={sha}&event=pull_request"
    runs: list[WorkflowRun] = read_json(run, ci_runs, "api", path)
    return max(runs, key=lambda ci: (ci.created_at, ci.id), default=None)


def watch(run: Run, ci: WorkflowRun, interval: int, timeout: float) -> None:
    """Attend la fin du run `ci` par `gh run watch`, au plus `timeout` secondes. Sa sortie est
    jetée et son code ignoré : il ne distingue pas un rouge d'un saut, l'API en décide."""
    try:
        launch(run, ("run", "watch", str(ci.id), "--exit-status", "-i", str(interval)), timeout)
    except subprocess.TimeoutExpired:
        pass


def verdict(run: Run, ci: WorkflowRun, sha: str) -> Verdict:
    """Le verdict d'un run terminé sur le SHA `sha`."""
    subject = f"run {ci.id} sur {sha[:7]}"
    if ci.conclusion == "success":
        return Verdict(f"vert — {subject} → sortir du draft, cycle-pr Étape 5", 0)
    if ci.conclusion == "skipped":
        return Verdict(f"sauté — {subject} → {NO_RUN}", 3)
    if ci.conclusion == "cancelled":
        return Verdict(f"annulé sans remplaçant — {subject} → {NO_RUN}", 3)
    failed: list[str] = read_json(run, failed_jobs, "run", "view", str(ci.id), "--json", "jobs")
    return Verdict(
        f"rouge — {subject}, conclusion {ci.conclusion}, jobs en échec :"
        f" {', '.join(failed) or 'aucun'}"
        f" → erreurs-ci.py {ci.id}, puis cycle-pr Étape 6, « Trier un rouge »",
        1,
    )


def wait(run: Run, pr: str, delay: int, interval: int, clock: Clock, sleep: Sleep) -> Verdict:
    """Attend un verdict sur la tête de la PR `pr`, au plus `delay` secondes (voir le module)."""
    deadline = clock() + delay
    while True:
        sha = head(run, pr)
        ci = latest(run, sha)
        remaining = deadline - clock()
        if ci is None:
            if remaining <= 0:
                return Verdict(f"aucun run — aucun run CI sur {sha[:7]} en {delay} s → {NO_RUN}", 3)
            sleep(min(interval, remaining))
        elif ci.status != "completed":
            if remaining <= 0:
                return Verdict(
                    f"délai dépassé — run {ci.id} sur {sha[:7]} encore {ci.status} après {delay} s"
                    " → cycle-pr Étape 6, « CI qui ne démarre pas »",
                    124,
                )
            started = clock()
            watch(run, ci, interval, remaining)
            pause = min(started + interval, deadline) - clock()
            if pause > 0:
                sleep(pause)
        elif ci.conclusion != "cancelled" or head(run, pr) == sha:
            return verdict(run, ci, sha)


def pr_number(value: str) -> str:
    """Type argparse : un numéro de PR, chiffres ASCII seulement."""
    if not NUMBER.fullmatch(value):
        raise argparse.ArgumentTypeError(f"numéro de PR attendu, pas {value!r}")
    return value


def seconds(value: str) -> int:
    """Type argparse : un nombre entier de secondes, positif — `int` lève sur un texte qui n'en est
    pas un, et argparse en fait une erreur d'usage."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"entier positif de secondes attendu, pas {value!r}")
    return number


def build_parser() -> argparse.ArgumentParser:
    """La PR, puis le délai et l'intervalle, en secondes."""
    parser = argparse.ArgumentParser(
        prog="attente-ci.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pr", type=pr_number)
    parser.add_argument("--delai", type=seconds, default=1800)
    parser.add_argument("--intervalle", type=seconds, default=30)
    return parser


def main(
    argv: Sequence[str],
    run: Run = default_run,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> int:
    """Point d'entrée ; voir le module pour les sorties."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2
    try:
        line, code = wait(run, args.pr, args.delai, args.intervalle, clock, sleep)
    except Refusal as refusal:
        line, code = f"refus — {refusal}", 1
    print(line)
    return code


if __name__ == "__main__":
    # Sur un poste dont la page de code est cp1252, Python écrit un tube dans cet encodage : un
    # verdict accentué arriverait illisible à la session qui le lit — l'erreur d'argparse, sur la
    # sortie d'erreur, comprise (`pipeline.config.md`, « Qualité »).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
