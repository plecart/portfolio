"""Porte de merge vers le trunk : le trunk que le run a réellement extrait, et la conversation de
la PR depuis le relevé du verdict d'avant-go.

Usage :
    python porte-merge.py trunk <run> <base> <tête>
    python porte-merge.py conversation <PR> [--releve]

`cycle-pr` Étape 7, « Le go, puis le merge » : en vague, une PR change pendant l'attente du go,
entre autres par le trunk et par la conversation (#197). Chaque sous-commande est un **prédicat** :
son code de sortie porte la condition, et `&&` la rend bloquante (`references/merge.md`, « Une
porte est une commande dont le code de sortie porte la condition »). `gh` et `git` sont lus en
octets, décodés en UTF-8 explicitement, jamais par la page de code de la console (obs 108).

Sortie, commune aux sous-commandes : 0 à jour / inchangée ; 1 périmé / changée ; 2 refus,
« refus — <motif> » en une ligne sur la sortie standard, appel mal formé, usage sur la sortie
d'erreur, ou aide demandée — l'aide n'est pas un verdict : `… --help && gh pr merge …` ne merge pas.

**Les entrées que l'appelant tape**, et ce qui lie chacune à l'artefact qu'elle désigne. Une
entrée que rien ne lie fait passer la porte sur une valeur mal tapée ou périmée : c'est la classe
du constat I1 de la passe 1 de relecture du bloc 1 de #197 (PR #200). Dénombrées avant son
correctif, sur `8a6332a`, dans l'usage des deux sous-commandes : 6 entrées, 4 liées à rien —
`trunk <run>`, dont le `headSha` n'était comparé qu'à sa propre trace, jamais à la tête que la
porte merge ; `-h` de chaque sous-commande, qui sortait en 0 ; `--releve`, qui sort en 0 sans
juger. Depuis, 7 :

- `trunk <run>` : son `headSha` doit égaler `<tête>` ;
- `trunk <tête>` : 40 hexadécimaux, la valeur même que la porte passe à `--match-head-commit` — ce
  dernier lien est à l'appelant, qui passe le même SHA à `trunk` puis à `gh pr merge` (`cycle-pr`
  Étape 7) ;
- `trunk <base>` : `origin/<base>` doit égaler le trunk que chaque job a fusionné ; son nom n'est
  pas confronté à la base de la PR, qu'aucun des 17 champs de `gh run view --json` ne rend
  (gh 2.94.0, relevé le 2026-10-29) ;
- `conversation <PR>` : le relevé se lit dans le body de cette même PR ;
- `-h` de chaque sous-commande, comme du script : sort en 2 ;
- `conversation --releve` : un mode, pas un verdict, qui sort en 0 sans juger — liée à rien, à
  dessein : elle ne se chaîne jamais par `&&`.

La table `ENTREES` d'`.claude/tests/test_porte_merge.py` tient un cas par entrée, et rougit
quand l'usage d'une sous-commande en gagne une sans cas.

**`trunk <run> <base> <tête>`** — le trunk que le run a extrait sur la tête visée. Il lit `gh run
view <run> --json status,headSha,jobs`, puis `gh run view <run> --log`, une ligne
`<job>\\t<step>\\t<horodatage> <texte>` par ligne de journal — les 2 358 lignes du run 40769309165
ont cette forme (relevé le 2026-10-29, gh 2.94.0) —, et `git rev-parse --verify
refs/remotes/origin/<base>`. La référence de suivi se nomme en entier : `origin/<base>` nu
désignerait d'abord une étiquette ou une branche locale du même nom s'il en existait
(gitrevisions(7), « <refname> », git 2.47.1). Il refuse un run qui n'est pas `completed`, dont le
`headSha` n'est pas `<tête>` — un run sur la tête A ne prouve rien d'un merge de la tête B, poussée
depuis —, ou dont aucun job n'a tourné. Pour chaque job dont la conclusion n'est pas `skipped`, il
cherche dans son journal la ligne de checkout, dont la forme est relevée sur le run 40769309165 de
la PR #185 (job Back, ligne 128 du `--log`, le 2026-10-29) :

    HEAD is now at 009f459 Merge 8d0200c26697fb8feeddb5c04b0962c9ab1527ed into 3e249191535972bb22dd506ee71d56d9b2b08247

— le commit extrait fusionne la tête de la PR au trunk, et son premier parent, le `<trunk>` du
message, est le trunk éprouvé : `gh api repos/plecart/portfolio/commits/009f459…` rend les parents
`3e24919…` puis `8d0200c…` (relevé le 2026-10-29). La ligne se cherche par job, quel que soit son
step : `gh` range le journal entier d'un job sous `UNKNOWN STEP` quand il ne sait pas l'associer à
ses steps (`erreurs-ci.py`, « Le journal entier d'un job »). Il refuse un job qui a tourné sans
ligne `HEAD is now at`, ou avec plusieurs — un run `push` n'en écrit aucune, son checkout étant
`git checkout --progress --force -B main refs/remotes/origin/main` puis `Switched to a new branch
'main'` (run 40934348730, 0 ligne sur 5 982, relevé le 2026-10-29) ; un checkout d'une autre
forme que `Merge … into …`, celui d'un commit nu ; une tête du message autre que le `headSha` du
run. Sinon 0 si le trunk de chaque job égale `origin/<base>`, 1 sinon, trunks différents entre jobs
compris. Il rend une ligne par job, `<job> : extrait <court>, trunk <sha> — à jour|périmé`, puis
`trunk éprouvé <sha> — run <run>, extrait <court> : à jour|périmé (origin/<base> = <sha>)`, qui
nomme chaque valeur distincte quand les jobs divergent.

**`conversation <PR> [--releve]`** — la conversation n'a pas bougé depuis le relevé. Il lit
`gh pr view <PR> --json body,comments,reviews` et compte chaque commentaire, daté par `createdAt`,
et chaque revue **soumise**, datée par `submittedAt` : `gh` exporte chaque revue, en attente
comprise, `submittedAt` alors à `null`, et pagine les deux listes (cli/cli v2.94.0, lu le
2026-10-29 : `api/export_pr.go`, champ `reviews` ; `api/queries_pr_review.go`,
`SubmittedAt *time.Time`, et `DisplayableReviews`, qui écarte les `PENDING` de l'affichage
seulement ; `pkg/cmd/pr/shared/finder.go`, `preloadPrComments` et `preloadPrReviews`). Un
horodatage a la forme que GitHub rend, `2026-10-14T17:52:41Z` — PR #94, relevée le 2026-10-29 —,
fraction de seconde admise ; il se compare en `datetime`, jamais en chaîne.

`--releve` imprime la ligne de relevé, et sort en 0 :

    Conversation : <k> commentaires et revues, dernier <horodatage le plus récent | aucun>

C'est cette ligne, copiée telle quelle aux Notes du body, que la porte relit : même règle de compte
des deux côtés. Sans `--releve`, il lit la **dernière** ligne du body qui s'ouvre par `Conversation
: ` — des verdicts successifs s'y empilent —, et refuse si elle manque ou n'a pas cette forme. 1 si
le compte actuel diffère de `<k>` ou si un élément est postérieur à `dernier`, chacun nommé, du plus
ancien au plus récent, `commentaire|revue de <login> à <horodatage> : <première ligne>` — une revue
de commentaires en ligne n'a pas de texte, et sa ligne renvoie alors à `gh api --paginate
repos/{owner}/{repo}/pulls/<n>/comments`, qui les porte (PR #199 : 10 revues sans texte, 10
commentaires en ligne de 10 revues distinctes, relevé le 2026-10-29) ; 0 sinon. Puis `PR <n> :
inchangée|changée depuis « <relevé> » — actuel : <k> commentaires et revues, dernier <horodatage |
aucun>`.

Le relevé se lit dans l'artefact, jamais dans un argument retapé : une lecture suivie d'une
seconde commande n'est pas une porte (`references/merge.md`, même section), et la valeur retapée
serait celle que la session croit, pas celle que le verdict a vue. L'incident d'origine (obs 88,
89) : PR #94, verdict d'avant-go vers 17:35 UTC à 0 commentaire ; à 17:52:41 UTC, la passe
`repercussions` du merge de #92 y dépose un « à ajuster » ; merge à 17:58:31 UTC derrière
`git merge-base --is-ancestor … && gh pr merge …`, qui ne le voyait pas — le texte contesté est
entré dans `main`.

**Ce qu'il ne prouve pas.** `trunk` ne relance rien, et ne récupère pas `origin/<base>` : il
compare à la référence de suivi que le dernier `git fetch origin` a laissée, à lancer d'abord
(`cycle-pr` Étape 7). Un `gh run rerun` réutilise le commit enregistré au déclenchement (obs 83) :
il ne change pas ce que le run extrait. La référence de fusion que porte la forge, relue avant ou
après une relance, ne dit pas ce que le run a extrait (`cycle-pr` Étape 7, « Rejouer les
vérifications périmées », qui cite les runs mesurés). `conversation` ne juge pas ce que dit un
commentaire — un écart renvoie à sa lecture —, ne lit d'un élément que sa date de création ou de
soumission, si bien que l'édition d'un commentaire existant lui échappe, et ne prouve pas que le
relevé a été pris à l'heure du verdict, seulement qu'il est inscrit.

Python 3.11 ou plus, bibliothèque standard seule ; `gh` authentifié et `git`, lancé depuis le
dépôt.
"""

import argparse
import io
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Any, NamedTuple

Run = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]
# Ce que rend une sous-commande : la condition tenue ou non, et les lignes à imprimer.
Verdict = tuple[bool, list[str]]

# `str.isdigit` accepte « ² » : un numéro, qui entre dans une commande, se lit en ASCII.
NUMBER = re.compile(r"[0-9]+")
# La forme que la forge rend d'un `headSha`, et que `--match-head-commit` reçoit.
FULL_SHA = re.compile(r"[0-9a-f]{40}")
CHECKOUT = "HEAD is now at "
# La ligne de checkout d'un run de PR (voir le module) : `<court> Merge <tête> into <trunk>`.
MERGE_CHECKOUT = re.compile(
    r"HEAD is now at ([0-9a-f]{4,40}) Merge ([0-9a-f]{40}) into ([0-9a-f]{40})"
)
FRESHNESS = {True: "à jour", False: "périmé"}
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z")
RECORD = "Conversation : "
NO_ELEMENT = "aucun"
RECORD_LINE = re.compile(
    rf"{RECORD}([0-9]+) commentaires et revues, dernier ({NO_ELEMENT}|{STAMP.pattern})"
)
STABILITY = {True: "inchangée", False: "changée"}


class Refusal(Exception):
    """Une sortie de `gh` ou de `git` inutilisable, ou une condition qui ne se juge pas ; le message
    est le motif, en une ligne."""


class Checkout(NamedTuple):
    """Ce qu'un job a extrait : le commit, abrégé comme la trace l'écrit, et son premier parent."""

    job: str
    short: str
    trunk: str


class Element(NamedTuple):
    """Un commentaire ou une revue soumise de la PR."""

    kind: str
    login: str
    stamp: str
    at: datetime
    first_line: str


def default_run(cmd: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    """Lance `cmd` et capture ses sorties **en octets** : ni le mode texte ni la page de code de
    la console ne touchent ce qui sort (obs 108)."""
    return subprocess.run(list(cmd), capture_output=True, check=False)


def output(run: Run, *cmd: str) -> str:
    """La sortie standard de `cmd`, décodée en UTF-8.

    Raises:
        Refusal: la commande ne se lance pas, ou sort autrement qu'en 0 — sa sortie d'erreur fait
            le motif, ramenée à une ligne.
    """
    try:
        done = run(cmd)
    except OSError as error:
        raise Refusal(f"`{cmd[0]}` ne se lance pas : {error}") from error
    if done.returncode != 0:
        motif = " ".join(done.stderr.decode("utf-8", "replace").split())
        raise Refusal(f"`{' '.join(cmd)}` a échoué ({done.returncode}) : {motif}")
    return done.stdout.decode("utf-8", "replace")


def json_output(run: Run, *cmd: str) -> Any:
    """La sortie JSON de `cmd`.

    Raises:
        Refusal: comme `output`, ou une sortie qui n'est pas du JSON.
    """
    try:
        return json.loads(output(run, *cmd))
    except json.JSONDecodeError as error:
        raise Refusal(f"`{' '.join(cmd)}` ne rend pas du JSON : {error}") from error


def shape_refusal(cmd: Sequence[str], error: Exception) -> Refusal:
    """Le refus d'une réponse JSON qui n'a pas la forme lue."""
    return Refusal(
        f"`{' '.join(cmd)}` ne rend pas la forme attendue : {type(error).__name__} {error}"
    )


def distinct(values: Iterable[str]) -> str:
    """Les valeurs distinctes, dans leur ordre d'arrivée."""
    return ", ".join(dict.fromkeys(values))


def read_run(run: Run, run_id: str) -> tuple[str, str, list[str]]:
    """Le statut du run, son `headSha`, et le nom de chacun de ses jobs qui a tourné.

    Raises:
        Refusal: `gh` en échec, ou une réponse d'une autre forme.
    """
    cmd = ("gh", "run", "view", run_id, "--json", "status,headSha,jobs")
    document = json_output(run, *cmd)
    try:
        ran = [job["name"] for job in document["jobs"] if job["conclusion"] != "skipped"]
        return document["status"], document["headSha"], ran
    except (KeyError, TypeError) as error:
        raise shape_refusal(cmd, error) from error


def checkout_lines(log: str) -> dict[str, list[str]]:
    """Les lignes `HEAD is now at` de `gh run view --log`, horodatage ôté, rangées par job."""
    found: dict[str, list[str]] = {}
    for line in log.split("\n"):
        job, _, rest = line.partition("\t")
        text = rest.partition("\t")[2].partition(" ")[2].strip()
        if text.startswith(CHECKOUT):
            found.setdefault(job, []).append(text)
    return found


def checkout(job: str, lines: Sequence[str], head: str) -> Checkout:
    """Ce que `job` a extrait, lu sur sa ligne de checkout.

    Raises:
        Refusal: aucune ligne ou plusieurs, une ligne d'une autre forme que `Merge … into …`, ou
            une tête fusionnée autre que `head`.
    """
    if len(lines) != 1:
        raise Refusal(f"job « {job} » : {len(lines)} lignes `{CHECKOUT}…` au journal, une attendue")
    match = MERGE_CHECKOUT.fullmatch(lines[0])
    if match is None:
        raise Refusal(
            f"job « {job} » : checkout hors de la forme `Merge <tête> into <trunk>` — {lines[0]}"
        )
    short, merged, trunk = match.groups()
    if merged != head:
        raise Refusal(f"job « {job} » : extrait la tête {merged}, pas le headSha du run {head}")
    return Checkout(job, short, trunk)


def trunk(run: Run, args: argparse.Namespace) -> Verdict:
    """`trunk <run> <base> <tête>` : le trunk que chaque job du run a extrait sur `<tête>`, comparé
    à `origin/<base>`.

    Raises:
        Refusal: voir le module.
    """
    run_id, base = args.run, args.base
    status, head, jobs = read_run(run, run_id)
    if status != "completed":
        raise Refusal(
            f"run {run_id} pas terminé (status {status}) : l'attendre par `attente-ci.py`"
        )
    if head != args.head:
        raise Refusal(
            f"le run {run_id} a éprouvé la tête {head}, pas la tête visée {args.head} : "
            "lire le dernier run de la tête visée"
        )
    if not jobs:
        raise Refusal(f"aucun job du run {run_id} n'a tourné : il n'a rien extrait")
    found = checkout_lines(output(run, "gh", "run", "view", run_id, "--log"))
    checkouts = [checkout(job, found.get(job, []), head) for job in jobs]
    origin = output(run, "git", "rev-parse", "--verify", f"refs/remotes/origin/{base}").strip()
    lines = [
        f"{seen.job} : extrait {seen.short}, trunk {seen.trunk} — {FRESHNESS[seen.trunk == origin]}"
        for seen in checkouts
    ]
    fresh = all(seen.trunk == origin for seen in checkouts)
    lines.append(
        f"trunk éprouvé {distinct(seen.trunk for seen in checkouts)} — run {run_id}, extrait "
        f"{distinct(seen.short for seen in checkouts)} : {FRESHNESS[fresh]} "
        f"(origin/{base} = {origin})"
    )
    return fresh, lines


def moment(stamp: str) -> datetime:
    """L'instant d'un horodatage de la forme que GitHub rend (`STAMP`).

    Raises:
        TypeError, ValueError: autre chose qu'une chaîne de cette forme, ou une date impossible.
    """
    if not STAMP.fullmatch(stamp):
        raise ValueError(f"horodatage hors de la forme AAAA-MM-JJTHH:MM:SSZ : {stamp!r}")
    return datetime.fromisoformat(stamp)


def element(kind: str, item: Any, stamp: Any) -> Element:
    """Un commentaire ou une revue de `gh pr view --json`, daté par `stamp`."""
    first_line = (item["body"].strip().splitlines() or [""])[0]
    return Element(kind, item["author"]["login"], stamp, moment(stamp), first_line)


def read_pr(run: Run, number: str) -> tuple[str, list[Element]]:
    """Le body de la PR, et ses commentaires et revues soumises, du plus ancien au plus récent.

    Raises:
        Refusal: `gh` en échec, ou une réponse d'une autre forme.
    """
    cmd = ("gh", "pr", "view", number, "--json", "body,comments,reviews")
    pr = json_output(run, *cmd)
    try:
        items = [element("commentaire", item, item["createdAt"]) for item in pr["comments"]]
        items += [
            element("revue", item, item["submittedAt"])
            for item in pr["reviews"]
            if item["submittedAt"] is not None
        ]
        body = pr["body"]
        if not isinstance(body, str):
            raise TypeError(f"body de type {type(body).__name__}")
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise shape_refusal(cmd, error) from error
    return body, sorted(items, key=lambda item: item.at)


def record_line(items: Sequence[Element]) -> str:
    """La ligne de relevé (voir le module) ; `items` va du plus ancien au plus récent."""
    last = items[-1].stamp if items else NO_ELEMENT
    return f"{RECORD}{len(items)} commentaires et revues, dernier {last}"


def recorded(body: str) -> tuple[int, datetime | None, str]:
    """Le compte et l'instant du dernier élément que porte la dernière ligne de relevé du body, et
    cette ligne.

    Raises:
        Refusal: aucune ligne de relevé, ou la dernière mal formée.
    """
    lines = [line.strip() for line in body.splitlines() if line.strip().startswith(RECORD)]
    if not lines:
        raise Refusal(
            f"le body ne porte aucune ligne « {RECORD}… » : la relever par "
            "`porte-merge.py conversation <PR> --releve`"
        )
    match = RECORD_LINE.fullmatch(lines[-1])
    try:
        if match is None:
            raise ValueError(lines[-1])
        return int(match[1]), None if match[2] == NO_ELEMENT else moment(match[2]), lines[-1]
    except ValueError as error:
        raise Refusal(f"dernière ligne de relevé mal formée : {lines[-1]}") from error


def conversation(run: Run, args: argparse.Namespace) -> Verdict:
    """`conversation <PR> [--releve]` : le relevé de la conversation, ou sa comparaison au dernier
    relevé du body.

    Raises:
        Refusal: voir le module.
    """
    body, items = read_pr(run, args.pr)
    current = record_line(items)
    if args.releve:
        return True, [current]
    count, last, line = recorded(body)
    later = [item for item in items if last is None or item.at > last]
    unchanged = not later and len(items) == count
    # Une revue sans texte — de commentaires en ligne, ou une approbation nue — renvoie à ses
    # commentaires en ligne, s'il y en a.
    inline = (
        "sans texte — ses commentaires en ligne, s'il y en a : "
        f"gh api --paginate repos/{{owner}}/{{repo}}/pulls/{args.pr}/comments"
    )
    lines = [
        f"{item.kind} de {item.login} à {item.stamp} : {item.first_line or inline}"
        for item in later
    ]
    lines.append(
        f"PR {args.pr} : {STABILITY[unchanged]} depuis « {line} » — actuel : "
        f"{current.removeprefix(RECORD)}"
    )
    return unchanged, lines


def matching(pattern: re.Pattern[str], expected: str) -> Callable[[str], str]:
    """Type argparse : une valeur qui a tout entière la forme `pattern` ; l'erreur nomme
    `expected`."""

    def check(value: str) -> str:
        if not pattern.fullmatch(value):
            raise argparse.ArgumentTypeError(f"{expected} attendu, pas {value!r}")
        return value

    return check


def build_parser() -> argparse.ArgumentParser:
    """Les deux sous-commandes ; chacune pose sa porte, `gate`. Les métavariables font l'usage
    que dénombre le module (« Les entrées que l'appelant tape »)."""
    parser = argparse.ArgumentParser(
        prog="porte-merge.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    trunk_parser = commands.add_parser("trunk")
    trunk_parser.add_argument("run", metavar="<run>", type=matching(NUMBER, "numéro"))
    trunk_parser.add_argument("base", metavar="<base>")
    trunk_parser.add_argument(
        "head", metavar="<tête>", type=matching(FULL_SHA, "SHA complet de 40 hexadécimaux")
    )
    trunk_parser.set_defaults(gate=trunk)
    conversation_parser = commands.add_parser("conversation")
    conversation_parser.add_argument("pr", metavar="<PR>", type=matching(NUMBER, "numéro"))
    conversation_parser.add_argument("--releve", action="store_true")
    conversation_parser.set_defaults(gate=conversation)
    return parser


def main(argv: Sequence[str], run: Run = default_run) -> int:
    """Point d'entrée ; voir le module pour les sous-commandes et les sorties."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit:
        # L'aide sort en 2 comme un appel mal formé : en 0, `… --help && gh pr merge …` mergerait.
        return 2
    try:
        held, lines = args.gate(run, args)
    except Refusal as refusal:
        print(f"refus — {refusal}")
        return 2
    print("\n".join(lines))
    return 0 if held else 1


if __name__ == "__main__":
    # Sur un poste dont la page de code est cp1252, Python écrit un tube dans cet encodage : un
    # nom de job ou un commentaire accentué arriverait illisible à la session qui le lit —
    # l'erreur d'argparse, sur la sortie d'erreur, comprise (`pipeline.config.md`, « Qualité »).
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
