"""Écriture distante relue : écrit un texte de la forge, puis le relit en entier.

Usage :
    python ecriture-relue.py label <N> --remove <label>
    python ecriture-relue.py checkbox patch <N> --case <ancre> [--case <ancre> …]
    python ecriture-relue.py brief patch <N> --case <ancre> [--case <ancre> …]
    python ecriture-relue.py issue edit <N> --append <fichier>

La règle « Écritures sur un artefact distant » de `contraintes.md` veut que toute écriture sur la
forge se relise ; ce script tient cette relecture pour les gestes de `cycle-pr` Étape 8 (#134,
lot 4a). Chaque sous-commande lit le texte par `gh api` — octets décodés en UTF-8, jamais le mode
texte, qui traduit les fins de ligne, ni la page de code de la console (obs 87, 106, 108, 116) —,
le modifie en mémoire, l'écrit par `gh api -X PATCH <chemin> --input -` avec la charge JSON sur
l'entrée standard, puis le relit par le même canal et compare le **texte entier** à l'attendu :
une forme réduite, longueur ou ancre, ne voit pas une conversion qui la préserve (obs 106).
`{owner}/{repo}` sont remplis par `gh` depuis le dépôt courant.

- `label` retire un label de l'issue ou de la PR `<N>`, puis relit ses labels ;
- `checkbox patch` coche des cases du corps de `<N>`, `brief patch` celles de son commentaire de
  brief — le seul qui s'ouvre par `## Brief d'agent` (`triage/brief-agent.md`). Une ancre est un
  extrait de texte d'une seule ligne de case, `- [ ] …` ou `- [x] …` (`[X]` compris), indentation
  permise ;
- `issue edit --append` ajoute un fichier UTF-8, lu en octets, en fin de corps de `<N>`, séparé
  par une ligne vide. Le corps d'une PR passe par le même chemin : pour l'API REST, une PR est une
  issue.

Il refuse, sans rien écrire : une ancre introuvable ou ambiguë — toutes sont validées avant la
première écriture —, zéro ou plusieurs commentaires de brief, un fichier illisible, non UTF-8 ou
sans ligne non vide, une lecture `gh` qui échoue ou ne rend pas du JSON. Une case déjà cochée, un
label déjà absent, un fichier qui termine déjà le corps : rien à écrire, et la sortie le dit — un
rejeu après une relecture tombée n'écrit donc pas une seconde fois.

**Ce qu'il ne prouve pas.** Il ne choisit pas les cases : la session PR les nomme. Il ne
verrouille rien : une édition faite par un tiers entre sa lecture et son écriture est écrasée, et
la relecture ne la voit pas — elle compare à ce que le script a écrit. Le fichier se reconnaît en
fin de corps à l'identique, fins de ligne comprises : sur une forge qui le stocke transformé —
relecture non conforme dès le premier appel —, un rejeu l'ajoute une seconde fois. Une relecture
conforme atteste ce que l'API rend, pas ce que l'interface web affiche. Le chemin d'un label
encodé et l'écriture du corps d'une PR par l'endpoint `issues` ne sont pas mesurés sur la vraie
forge.

Sortie : 0 écrit et relu conforme, ou rien à écrire ; 1 refus (« refus — »), ou écriture lancée et
relecture non conforme ou impossible (« relecture non conforme — ») — motif en une ligne sur la
sortie standard ; 2 appel mal formé, usage sur la sortie d'erreur. Python 3.11 ou plus,
bibliothèque standard seule ; `gh` authentifié, lancé depuis le dépôt.
"""

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote

Run = Callable[[Sequence[str], bytes | None], subprocess.CompletedProcess[bytes]]

REPO = "repos/{owner}/{repo}"
BRIEF_MARK = "## Brief d'agent"
# Une ligne de case Markdown ; le groupe est l'état de la case. `[X]` vaut coché pour GitHub.
CHECKBOX = re.compile(r"[ \t]*- \[([ xX])\] ")
# `str.isdigit` accepte « ² » : le numéro, qui entre dans un chemin d'API, se lit en ASCII.
NUMBER = re.compile(r"[0-9]+")


class Refusal(Exception):
    """Rien n'est écrit : une condition du geste n'est pas tenue ; le message est le motif."""


class Divergence(Exception):
    """L'écriture est lancée, et la relecture ne rend pas l'attendu ou n'a pas pu se faire."""


class Text(NamedTuple):
    """Un texte de la forge : où l'écrire et le relire, ce qu'il vaut, comment le nommer."""

    path: str
    body: str
    name: str


def default_run(cmd: Sequence[str], stdin: bytes | None) -> subprocess.CompletedProcess[bytes]:
    """Lance `cmd` avec `stdin` sur son entrée standard et capture ses sorties **en octets** : ni
    le mode texte ni la page de code de la console ne touchent ce qui entre ou sort."""
    return subprocess.run(list(cmd), input=stdin, capture_output=True, check=False)


def gh_api(run: Run, *args: str, stdin: bytes | None = None) -> bytes:
    """La sortie de `gh api <args>`, ou un refus si la commande échoue ou ne se lance pas : une
    sortie vide d'une commande en échec ne se lit jamais comme une réponse."""
    cmd = ("gh", "api", *args)
    try:
        done = run(cmd, stdin)
    except OSError as error:
        raise Refusal(f"`gh` ne se lance pas : {error}") from error
    if done.returncode != 0:
        motif = " ".join(done.stderr.decode("utf-8", "replace").split())
        raise Refusal(f"`{' '.join(cmd)}` a échoué ({done.returncode}) : {motif}")
    return done.stdout


def read_json(run: Run, *args: str) -> Any:
    """La réponse JSON de `gh api <args>`, décodée en UTF-8 explicitement (obs 108).

    Raises:
        Refusal: la commande échoue, ou ne rend pas du JSON en UTF-8.
    """
    try:
        return json.loads(gh_api(run, *args).decode("utf-8"))
    except ValueError as error:
        raise Refusal(f"`gh api {' '.join(args)}` ne rend pas du JSON UTF-8 : {error}") from error


def write_then_reread(run: Run, write: Sequence[str], stdin: bytes | None, path: str) -> Any:
    """Lance l'écriture `gh api <write>`, puis rend le document relu sous `path`.

    Raises:
        Divergence: l'une des deux commandes échoue — l'écriture a pu partir, ce qu'un refus
            ferait croire impossible.
    """
    try:
        gh_api(run, *write, stdin=stdin)
        return read_json(run, path)
    except Refusal as error:
        raise Divergence(str(error)) from error


def measure(text: str) -> str:
    """Les deux grandeurs qu'une conversion de fins de ligne change : octets UTF-8 et `\\r`."""
    carriage_returns = text.count("\r")
    return f"{len(text.encode())} octets et {carriage_returns} \\r"


def write_body(run: Run, text: Text, expected: str, anchors: Sequence[str]) -> None:
    """Écrit `expected` comme corps de `text`, le relit, et compare le texte entier.

    Args:
        anchors: ce que la relecture doit contenir — nommé dans le motif s'il manque.

    Raises:
        Divergence: écriture ou relecture en échec, ou texte relu autre que `expected` ; le
            motif nomme chaque ancre absente, puis les octets et les `\\r` attendus et relus.
    """
    # ponytail: pas de verrou — une édition concurrente entre lecture et écriture est écrasée ;
    # une requête conditionnelle si la forge en accepte une.
    payload = json.dumps({"body": expected}, ensure_ascii=False).encode("utf-8")
    write = ("-X", "PATCH", text.path, "--input", "-")
    reread = write_then_reread(run, write, payload, text.path)["body"] or ""
    if reread != expected:
        missing = [f"ancre absente : {anchor}" for anchor in anchors if anchor not in reread]
        raise Divergence(
            " ; ".join([*missing, f"attendu {measure(expected)}, relu {measure(reread)}"])
        )


def resolve_anchors(candidates: Mapping[int, str], anchors: Sequence[str]) -> dict[str, int]:
    """L'indice de la seule ligne candidate qui porte chaque ancre.

    Args:
        candidates: indice → ligne, pour les seules lignes de case du texte.

    Raises:
        Refusal: une ancre n'apparaît dans aucune ligne de case, ou dans plusieurs — chaque ancre
            en défaut est nommée, pas seulement la première.
    """
    targets: dict[str, int] = {}
    motifs: list[str] = []
    for anchor in anchors:
        hits = [i for i, line in candidates.items() if anchor in line]
        if not hits:
            motifs.append(f"case introuvable : {anchor}")
        elif len(hits) > 1:
            motifs.append(f"case ambiguë : {anchor} ({len(hits)} lignes)")
        else:
            targets[anchor] = hits[0]
    if motifs:
        raise Refusal(" ; ".join(motifs))
    return targets


def check_boxes(body: str, anchors: Sequence[str]) -> tuple[str, list[str], list[str]]:
    """Coche, dans `body`, la ligne de case que désigne chaque ancre — toutes, ou aucune.

    Une ligne est un segment entre deux `\\n` : un `\\r` final reste sur sa ligne, les fins de
    ligne ressortent telles qu'elles sont entrées.

    Returns:
        Le corps coché, les lignes cochées (sans indentation ni `\\r`, ancres de la relecture),
        et les ancres dont la case l'était déjà.

    Raises:
        Refusal: voir `resolve_anchors` ; rien n'est coché.
    """
    lines = body.split("\n")
    boxes = {i: box for i, line in enumerate(lines) if (box := CHECKBOX.match(line))}
    targets = resolve_anchors({i: lines[i] for i in boxes}, anchors)
    already = [anchor for anchor, i in targets.items() if boxes[i].group(1) != " "]
    checked: list[str] = []
    for i in sorted({i for i in targets.values() if boxes[i].group(1) == " "}):
        lines[i] = lines[i][: boxes[i].start(1)] + "x" + lines[i][boxes[i].end(1) :]
        checked.append(lines[i].strip())
    return "\n".join(lines), checked, already


def issue_path(number: str) -> str:
    """Le chemin `gh api` de l'issue `number` — d'une PR aussi : pour l'API REST, une PR est une
    issue."""
    return f"{REPO}/issues/{number}"


def issue_body(run: Run, number: str) -> Text:
    """Le corps de l'issue ou de la PR `number` ; `null` vaut le texte vide."""
    path = issue_path(number)
    return Text(path, read_json(run, path)["body"] or "", f"corps de #{number}")


def brief_comment(run: Run, number: str) -> Text:
    """Le commentaire de brief de l'issue `number`, cherché sur toutes les pages.

    Raises:
        Refusal: aucun commentaire ne s'ouvre par `## Brief d'agent`, ou plusieurs.
    """
    pages = read_json(run, "--paginate", "--slurp", f"{issue_path(number)}/comments")
    briefs = [c for page in pages for c in page if (c["body"] or "").startswith(BRIEF_MARK)]
    if len(briefs) != 1:
        raise Refusal(
            f"il faut un seul commentaire de brief sur #{number}, il y en a {len(briefs)}"
        )
    brief = briefs[0]
    return Text(f"{REPO}/issues/comments/{brief['id']}", brief["body"], f"brief de #{number}")


def patch_boxes(run: Run, args: argparse.Namespace) -> str:
    """`checkbox patch` et `brief patch` : coche les ancres dans le texte que `args.locate`
    désigne, et n'écrit que si une case change."""
    text = args.locate(run, args.number)
    expected, checked, already = check_boxes(text.body, args.anchors)
    report = [f"déjà cochée : {anchor}" for anchor in already]
    if checked:
        write_body(run, text, expected, checked)
        report.append(f"écrit et relu — {text.name} : {len(checked)} case(s) cochée(s)")
    else:
        report.append(f"rien à écrire — {text.name} : aucune case à cocher")
    return "\n".join(report)


def label_names(document: Any) -> list[str]:
    """Les noms des labels d'une issue, telle que l'API REST la rend."""
    return [label["name"] for label in document["labels"]]


def label_remove(run: Run, args: argparse.Namespace) -> str:
    """`label --remove` : retire le label s'il est posé — son nom encodé en un seul segment de
    chemin —, puis relit les labels de l'issue."""
    path = issue_path(args.number)
    if args.label not in label_names(read_json(run, path)):
        return f"rien à écrire — label {args.label} absent de #{args.number}"
    delete = ("-X", "DELETE", f"{path}/labels/{quote(args.label, safe='')}")
    if args.label in label_names(write_then_reread(run, delete, None, path)):
        raise Divergence(f"le label {args.label} est encore sur #{args.number}")
    return f"retiré et relu — label {args.label} de #{args.number}"


def issue_append(run: Run, args: argparse.Namespace) -> str:
    """`issue edit --append` : ajoute le fichier en fin de corps, sauf s'il le termine déjà ; l'ancre
    de la relecture est sa première ligne non vide. Le fichier est lu avant tout appel à la forge."""
    try:
        addition = args.file.read_bytes().decode("utf-8")
    except OSError as error:
        raise Refusal(f"fichier illisible : {error}") from error
    except UnicodeDecodeError as error:
        raise Refusal(f"{args.file} n'est pas en UTF-8 : {error}") from error
    anchor = next((line.strip() for line in addition.splitlines() if line.strip()), None)
    if anchor is None:
        raise Refusal(f"rien à ajouter : {args.file} n'a aucune ligne non vide")
    text = issue_body(run, args.number)
    if text.body.endswith(addition):
        return f"rien à écrire — {text.name} : {args.file} déjà en fin de corps"
    write_body(run, text, f"{text.body}\n\n{addition}", [anchor])
    return f"écrit et relu — {text.name} : {args.file} ajouté"


def issue_number(value: str) -> str:
    """Type argparse : un numéro d'issue ou de PR, chiffres ASCII seulement."""
    if not NUMBER.fullmatch(value):
        raise argparse.ArgumentTypeError(f"numéro d'issue ou de PR attendu, pas {value!r}")
    return value


def one_line(value: str) -> str:
    """Type argparse : un texte non vide sur une ligne — il ressort dans une ligne de motif."""
    if not value.strip() or "\n" in value or "\r" in value:
        raise argparse.ArgumentTypeError(f"texte non vide sur une seule ligne attendu : {value!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Les quatre sous-commandes du module ; chacune pose son `handler`."""
    parser = argparse.ArgumentParser(
        prog="ecriture-relue.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    label = commands.add_parser("label")
    label.add_argument("number", type=issue_number)
    label.add_argument("--remove", dest="label", type=one_line, required=True)
    label.set_defaults(handler=label_remove)
    for name, locate in (("checkbox", issue_body), ("brief", brief_comment)):
        actions = commands.add_parser(name).add_subparsers(dest="action", required=True)
        boxes = actions.add_parser("patch")
        boxes.add_argument("number", type=issue_number)
        boxes.add_argument("--case", dest="anchors", type=one_line, action="append", required=True)
        boxes.set_defaults(handler=patch_boxes, locate=locate)
    actions = commands.add_parser("issue").add_subparsers(dest="action", required=True)
    edit = actions.add_parser("edit")
    edit.add_argument("number", type=issue_number)
    edit.add_argument("--append", dest="file", type=Path, required=True)
    edit.set_defaults(handler=issue_append)
    return parser


def main(argv: Sequence[str], run: Run = default_run) -> int:
    """Point d'entrée ; voir le module pour les sous-commandes et les sorties."""
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2
    try:
        print(args.handler(run, args))
    except Refusal as refusal:
        print(f"refus — {refusal}")
        return 1
    except Divergence as divergence:
        print(f"relecture non conforme — {divergence}")
        return 1
    return 0


if __name__ == "__main__":
    # Sur un poste dont la page de code est cp1252, Python écrit un tube dans cet encodage : un
    # motif accentué arriverait illisible à la session qui le lit — l'erreur d'argparse, sur la
    # sortie d'erreur, comprise (`pipeline.config.md`, « Qualité »).
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
