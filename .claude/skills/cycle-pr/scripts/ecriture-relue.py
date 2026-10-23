"""Écriture distante relue : écrit un texte de la forge, puis le relit en entier.

Usage :
    python ecriture-relue.py label <N> --remove <label>
    python ecriture-relue.py checkbox patch <N> --case <ancre> [--case <ancre> …]
    python ecriture-relue.py brief patch <N> --case <ancre> [--case <ancre> …]
    python ecriture-relue.py brief write <N> --body-file <fichier>
    python ecriture-relue.py issue edit <N> (--append | --body-file) <fichier>
    python ecriture-relue.py issue create --title <titre> --body-file <fichier> [--label <label> …]
    python ecriture-relue.py comment <N> --body-file <fichier>

La règle « Écritures sur un artefact distant » de `contraintes.md` veut que toute écriture sur la
forge se relise ; ce script tient cette relecture pour les gestes de `cycle-pr` Étape 8, le
commentaire de répercussion de son Étape 6 et la création d'une issue (#134, lots 4a, 4b et 6a1).
Chaque sous-commande lit par `gh api` — octets décodés en UTF-8, jamais le mode texte, qui traduit
les fins de ligne, ni la page de code de la console (obs 87, 106, 108, 116) —, écrit, puis relit
par le même canal. Un texte s'écrit par `gh api -X PATCH <chemin> --input -` — `-X POST` pour
publier un commentaire ou créer une issue —, la charge JSON sur l'entrée standard, et sa
relecture compare le **texte entier** à l'attendu : une forme réduite, longueur ou ancre, ne voit
pas une conversion qui la préserve (obs 106).
`{owner}/{repo}` sont remplis par `gh` depuis le dépôt courant.

- `label` retire un label de l'issue ou de la PR `<N>`, puis relit ses labels ;
- `checkbox patch` coche des cases du corps de `<N>`, `brief patch` celles de son commentaire de
  brief — le seul qui s'ouvre par `## Brief d'agent` (`triage/brief-agent.md`). Une ancre est un
  extrait du texte qui suit le marqueur d'une seule ligne de case, `- [ ] …` ou `- [x] …` (`[X]`
  compris), indentation permise ; cocher ne change pas ce texte, et le rejeu rend le verdict du
  premier appel ;
- `brief write` publie un fichier UTF-8, lu en octets, en commentaire de brief de `<N>`, ou édite
  en place le seul qui existe — jamais un second brief concurrent. Un fichier qui ne s'ouvre pas
  par `## Brief d'agent`, dès son premier caractère, est refusé avant tout appel : `brief patch`
  ne le reconnaîtrait plus ;
- `issue edit --append` ajoute un fichier UTF-8, lu en octets, en fin de corps de `<N>`, séparé
  de son dernier contenu par une ligne vide au moins — celles qui terminent déjà le corps
  restent —, aucune sur un corps vide. Le corps d'une PR passe par le même chemin : pour l'API
  REST, une PR est une issue ;
- `issue edit --body-file` substitue un fichier UTF-8, lu en octets, au corps entier de `<N>` ;
  `--append` et `--body-file` s'excluent, et l'un des deux est requis ;
- `issue create` crée une issue de titre `--title` et de corps le fichier `--body-file`, UTF-8 lu
  en octets, avec ses labels `--label` dans la **même** requête : une issue n'existe jamais sans
  ses labels, même un instant. Chaque label doit exister dans le dépôt — apparié sans la casse,
  il part sous le nom que le dépôt lui donne —, lu sur toutes ses pages. La relecture compare le
  corps entier, le titre exact et l'ensemble des labels — sans droit d'écriture sur le dépôt,
  l'API REST ignore en silence les labels d'une création (« Create an issue ») ; la ligne de
  sortie porte le numéro de l'issue, créée ou déjà là ;
- `comment` publie un fichier UTF-8, lu en octets, en commentaire de `<N>`, puis relit le
  commentaire sous l'`id` que la publication rend. Une PR se commente par le même chemin.

Il refuse, sans rien écrire : une ancre introuvable ou ambiguë — toutes sont validées avant la
première écriture —, zéro brief à cocher, plusieurs briefs, un label inconnu du dépôt — chacun
nommé ; `CLAUDE.md` interdit de deviner un label, et la référence REST de « Create an issue » ne
dit pas ce qu'elle fait d'un label inconnu —, un fichier illisible, non UTF-8 ou sans ligne non
vide — lu avant tout appel à la forge —, une lecture `gh` qui échoue, ne rend pas du JSON, ou rend
un JSON sans un champ attendu ou d'un autre type. Après l'écriture — sa réponse comprise, dont un
commentaire publié tire son `id` et une issue créée son numéro —, c'est une relecture non
conforme : le texte a pu partir. Une case déjà cochée, un label déjà absent, un fichier qui
termine déjà le corps ou qui l'est déjà tout entier, un commentaire de `<N>` qui porte déjà le
fichier pour corps, une issue ouverte — pas une PR — qui porte déjà ce titre et ce corps : rien à
écrire, et la sortie le dit — un rejeu après une relecture tombée n'écrit donc pas une seconde
fois.

**Ce qu'il ne prouve pas.** Il ne choisit pas les cases : la session PR les nomme. Il ne
verrouille rien : une édition faite par un tiers entre sa lecture et son écriture est écrasée, et
la relecture ne la voit pas — elle compare à ce que le script a écrit ; un même commentaire publié
entre la lecture des commentaires et la publication fait un doublon, une même issue créée entre la
lecture des issues ouvertes et la création aussi. Le commentaire déjà publié se reconnaît à son
corps seul, l'issue déjà créée à son titre et à son corps — ses labels n'y comptent pas, et une
issue fermée n'est pas vue —, **quel qu'en soit l'auteur**. Le fichier se reconnaît à
l'identique, fins de ligne comprises, en fin de corps comme en corps de commentaire ou d'issue :
sur une forge qui le stocke transformé — relecture non conforme dès le premier appel —, un rejeu
l'ajoute, le réécrit, le publie ou crée l'issue une seconde fois. Une relecture conforme atteste
ce que l'API rend, pas ce que l'interface web affiche. Le chemin d'un label encodé, l'écriture
du corps d'une PR, la publication d'un commentaire sur une PR par l'endpoint `issues` et la
création d'une issue ne sont pas mesurés sur la vraie forge.

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
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple, TypeVar
from urllib.parse import quote

Run = Callable[[Sequence[str], bytes | None], subprocess.CompletedProcess[bytes]]
T = TypeVar("T")

REPO = "repos/{owner}/{repo}"
# Les issues du dépôt, et ses PR : pour l'API REST, une PR est une issue.
ISSUES = f"{REPO}/issues"
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


def read_json(run: Run, parse: Callable[[Any], Any], *args: str, stdin: bytes | None = None) -> Any:
    """Ce que `parse` tire de la réponse JSON de `gh api <args>`, décodée en UTF-8 explicitement
    (obs 108). La présence et le type des champs s'y gardent pour chaque site qui lit un document
    de la forge — lecture, réponse d'une écriture, relecture —, dénombrés par
    `test_une_reponse_d_une_autre_forme_sort_en_1_en_une_ligne`.

    Args:
        parse: tire du document les champs attendus ; un champ absent ou d'un autre type y lève
            `KeyError` ou `TypeError`.
        stdin: la charge d'une écriture, que `gh` lit sur son entrée standard.

    Raises:
        Refusal: la commande échoue, ne rend pas du JSON en UTF-8, ou pas la forme que `parse`
            attend.
    """
    try:
        document = json.loads(gh_api(run, *args, stdin=stdin).decode("utf-8"))
    except ValueError as error:
        raise Refusal(f"`gh api {' '.join(args)}` ne rend pas du JSON UTF-8 : {error}") from error
    try:
        return parse(document)
    except (KeyError, TypeError) as error:
        raise Refusal(
            f"`gh api {' '.join(args)}` ne rend pas la forme attendue : "
            f"{type(error).__name__} {error}"
        ) from error


@contextmanager
def writing() -> Generator[None, None, None]:
    """Le bloc qui lance une écriture puis la relit : un refus y devient une divergence.

    Raises:
        Divergence: une commande du bloc échoue, ou un document lu n'a pas la forme attendue —
            l'écriture a pu partir, ce qu'un refus ferait croire impossible.
    """
    try:
        yield
    except Refusal as error:
        raise Divergence(str(error)) from error


def write_then_reread(
    run: Run, write: Sequence[str], stdin: bytes | None, path: str, parse: Callable[[Any], Any]
) -> Any:
    """Lance l'écriture `gh api <write>`, puis rend ce que `parse` tire du document relu sous
    `path` ; un échec est une divergence (`writing`)."""
    with writing():
        gh_api(run, *write, stdin=stdin)
        return read_json(run, parse, path)


def body_of(document: Any) -> str:
    """Le champ `body` d'un document de la forge ; `null` vaut le texte vide.

    Raises:
        KeyError, TypeError: pas de champ `body`, ou ni texte ni `null` — `read_json` en fait le
            motif.
    """
    body = document["body"]
    if not isinstance(body, str | None):
        raise TypeError(f"`body` de type {type(body).__name__}")
    return body or ""


# `def typed[T]` demande Python 3.12 ; le script tient 3.11 (docstring du module).
def typed(document: Any, field: str, kind: type[T]) -> T:  # noqa: UP047
    """Le champ `field` d'un document de la forge, exactement du type `kind`.

    Raises:
        KeyError, TypeError: pas de champ `field`, ou d'un autre type — un booléen JSON compris,
            que Python tient pour un entier.
    """
    value = document[field]
    if type(value) is not kind:
        raise TypeError(f"`{field}` de type {type(value).__name__}")
    return value


def comment_id(comment: Any) -> int:
    """L'`id` d'un commentaire de la forge, entier : il entre dans un chemin d'API.

    Raises:
        KeyError, TypeError: voir `typed`.
    """
    return typed(comment, "id", int)


def measure(text: str) -> str:
    """Octets UTF-8 et `\\r` : ce que change la conversion de toutes les fins de ligne LF ↔ CRLF."""
    carriage_returns = text.count("\r")
    return f"{len(text.encode())} octets et {carriage_returns} \\r"


def json_payload(**fields: Any) -> bytes:
    """La charge d'une écriture — `{"body": …}` pour un texte —, en JSON UTF-8 brut, pour
    `--input -`."""
    return json.dumps(fields, ensure_ascii=False).encode("utf-8")


def check_reread(expected: str, reread: str, anchors: Sequence[str]) -> None:
    """Compare le texte relu à l'attendu, **entier** : une forme réduite, longueur ou ancre, ne
    voit pas une conversion qui la préserve (obs 106).

    Args:
        anchors: ce que la relecture doit contenir — nommé dans le motif s'il manque.

    Raises:
        Divergence: `reread` n'est pas `expected` ; le motif nomme chaque ancre absente, puis les
            octets et les `\\r` attendus et relus.
    """
    if reread != expected:
        missing = [f"ancre absente : {anchor}" for anchor in anchors if anchor not in reread]
        raise Divergence(
            " ; ".join([*missing, f"attendu {measure(expected)}, relu {measure(reread)}"])
        )


def write_body(run: Run, text: Text, expected: str, anchors: Sequence[str]) -> None:
    """Écrit `expected` comme corps de `text`, le relit, et compare le texte entier.

    Raises:
        Divergence: écriture ou relecture en échec, ou texte relu autre que `expected` — voir
            `check_reread`.
    """
    # ponytail: pas de verrou — une édition concurrente entre lecture et écriture est écrasée ;
    # une requête conditionnelle si la forge en accepte une.
    write = ("-X", "PATCH", text.path, "--input", "-")
    reread = write_then_reread(run, write, json_payload(body=expected), text.path, body_of)
    check_reread(expected, reread, anchors)


def resolve_anchors(candidates: Mapping[int, str], anchors: Sequence[str]) -> dict[str, int]:
    """L'indice de la seule ligne candidate qui porte chaque ancre.

    Args:
        candidates: indice → texte cherché, pour les seules lignes de case du texte.

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
    ligne ressortent telles qu'elles sont entrées. L'ancre se cherche dans le texte qui suit le
    marqueur `- [ ] `, que cocher ne change pas : le rejeu rend le verdict du premier appel.

    Returns:
        Le corps coché, les lignes cochées (sans indentation ni `\\r`, ancres de la relecture),
        et les ancres dont la case l'était déjà.

    Raises:
        Refusal: voir `resolve_anchors` ; rien n'est coché.
    """
    lines = body.split("\n")
    boxes = {i: box for i, line in enumerate(lines) if (box := CHECKBOX.match(line))}
    targets = resolve_anchors({i: lines[i][box.end() :] for i, box in boxes.items()}, anchors)
    already = [anchor for anchor, i in targets.items() if boxes[i].group(1) != " "]
    checked: list[str] = []
    for i in sorted({i for i in targets.values() if boxes[i].group(1) == " "}):
        lines[i] = lines[i][: boxes[i].start(1)] + "x" + lines[i][boxes[i].end(1) :]
        checked.append(lines[i].strip())
    return "\n".join(lines), checked, already


def issue_path(number: str) -> str:
    """Le chemin `gh api` de l'issue `number` — d'une PR aussi : pour l'API REST, une PR est une
    issue."""
    return f"{ISSUES}/{number}"


def issue_body(run: Run, number: str) -> Text:
    """Le corps de l'issue ou de la PR `number` ; `null` vaut le texte vide."""
    path = issue_path(number)
    return Text(path, read_json(run, body_of, path), f"corps de #{number}")


def comments_path(number: str) -> str:
    """Le chemin `gh api` des commentaires de l'issue ou de la PR `number`."""
    return f"{issue_path(number)}/comments"


def comment_path(identifier: int) -> str:
    """Le chemin `gh api` du commentaire `identifier`, d'une issue ou d'une PR."""
    return f"{ISSUES}/comments/{identifier}"


def kept_comments(pages: Any, keep: Callable[[str], bool]) -> list[tuple[int, str]]:
    """L'`id` et le corps de chaque commentaire dont le corps satisfait `keep`, sur les pages que
    `gh api --paginate --slurp` rend.

    Raises:
        KeyError, TypeError: des pages qui ne sont pas des listes de commentaires, un commentaire
            sans corps, ou un commentaire retenu sans `id` entier (`comment_id`).
    """
    return [
        (comment_id(comment), body)
        for page in pages
        for comment in page
        if keep(body := body_of(comment))
    ]


def issue_comments(run: Run, number: str, keep: Callable[[str], bool]) -> list[tuple[int, str]]:
    """Les commentaires de l'issue ou de la PR `number` que `keep` retient, lus sur toutes les
    pages (`kept_comments`)."""
    path = comments_path(number)
    return read_json(run, lambda pages: kept_comments(pages, keep), "--paginate", "--slurp", path)


def is_brief(body: str) -> bool:
    """Un brief d'agent s'ouvre par `## Brief d'agent`, dès son premier caractère."""
    return body.startswith(BRIEF_MARK)


def brief_comments(run: Run, number: str) -> list[Text]:
    """Les commentaires de brief de l'issue `number` (`is_brief`), cherchés sur toutes les
    pages."""
    return [
        Text(comment_path(identifier), body, f"brief de #{number}")
        for identifier, body in issue_comments(run, number, is_brief)
    ]


def brief_comment(run: Run, number: str) -> Text:
    """Le seul commentaire de brief de l'issue `number` (`brief_comments`).

    Raises:
        Refusal: aucun commentaire ne s'ouvre par `## Brief d'agent`, ou plusieurs.
    """
    briefs = brief_comments(run, number)
    if len(briefs) != 1:
        raise Refusal(
            f"il faut un seul commentaire de brief sur #{number}, il y en a {len(briefs)}"
        )
    return briefs[0]


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


def names_of(labels: Any) -> list[str]:
    """Les noms d'une liste de labels — d'une issue ou du dépôt —, telle que l'API REST la rend.

    Raises:
        KeyError, TypeError: pas une liste de labels, ou un label sans nom textuel (`typed`).
    """
    return [typed(label, "name", str) for label in labels]


def label_names(document: Any) -> list[str]:
    """Les noms des labels d'une issue, telle que l'API REST la rend.

    Raises:
        KeyError, TypeError: pas de liste `labels`, ou un label sans nom textuel.
    """
    return names_of(document["labels"])


def carried_label(names: Sequence[str], wanted: str) -> str | None:
    """Le nom sous lequel `names` — les labels d'une issue ou du dépôt — porte le label `wanted` :
    `wanted` lui-même s'il y est, sinon le premier qui lui est égal sans la casse ; `None` si
    aucun."""
    if wanted in names:
        return wanted
    return next((name for name in names if name.casefold() == wanted.casefold()), None)


def label_remove(run: Run, args: argparse.Namespace) -> str:
    """`label --remove` : retire le label s'il est posé, casse ignorée, puis relit les labels de
    l'issue. Le retrait et la relecture visent le nom que l'issue porte, encodé en un seul segment
    de chemin : rien ne dit la forge insensible à la casse."""
    path = issue_path(args.number)
    name = carried_label(read_json(run, label_names, path), args.label)
    if name is None:
        return f"rien à écrire — label {args.label} absent de #{args.number}"
    delete = ("-X", "DELETE", f"{path}/labels/{quote(name, safe='')}")
    if name in write_then_reread(run, delete, None, path, label_names):
        raise Divergence(f"le label {name} est encore sur #{args.number}")
    return f"retiré et relu — label {name} de #{args.number}"


def appended(body: str, addition: str) -> str:
    """`addition` à la suite de `body`, séparée de son dernier contenu par une ligne vide au
    moins : les fins de ligne — `\\n` ou `\\r\\n` — qui terminent déjà `body` comptent, et des
    `\\n` les complètent jusqu'à deux. Un corps vide n'a pas de séparateur ; `body` n'est jamais
    réécrit, seulement prolongé — plusieurs lignes vides qui le terminent restent."""
    if not body:
        return addition
    line_ends = body[len(body.rstrip("\r\n")) :].count("\n")
    return body + "\n" * max(0, 2 - line_ends) + addition


def read_text_file(path: Path) -> tuple[str, str]:
    """Le texte d'un fichier UTF-8, lu en octets — ses fins de ligne restent (obs 87) —, et sa
    première ligne non vide, ancre de la relecture.

    Raises:
        Refusal: fichier illisible, non UTF-8, ou sans ligne non vide.
    """
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError as error:
        raise Refusal(f"fichier illisible : {error}") from error
    except UnicodeDecodeError as error:
        raise Refusal(f"{path} n'est pas en UTF-8 : {error}") from error
    anchor = next((line.strip() for line in text.splitlines() if line.strip()), None)
    if anchor is None:
        raise Refusal(f"{path} n'a aucune ligne non vide")
    return text, anchor


def issue_append(run: Run, args: argparse.Namespace) -> str:
    """`issue edit --append` : ajoute le fichier en fin de corps, sauf s'il le termine déjà. Le
    fichier est lu avant tout appel à la forge."""
    addition, anchor = read_text_file(args.append)
    text = issue_body(run, args.number)
    if text.body.endswith(addition):
        return f"rien à écrire — {text.name} : {args.append} déjà en fin de corps"
    write_body(run, text, appended(text.body, addition), [anchor])
    return f"écrit et relu — {text.name} : {args.append} ajouté"


def replace_text(run: Run, text: Text, body: str, anchor: str, file: Path) -> str:
    """Substitue `body`, le texte du fichier `file`, au texte entier de `text`, sauf s'il l'est
    déjà ; `anchor` est l'ancre de la relecture (`write_body`)."""
    if text.body == body:
        return f"rien à écrire — {text.name} : déjà {file}"
    write_body(run, text, body, [anchor])
    return f"écrit et relu — {text.name} : remplacé par {file}"


def issue_edit(run: Run, args: argparse.Namespace) -> str:
    """`issue edit` : `--append` ajoute le fichier en fin de corps (`issue_append`),
    `--body-file` le substitue au corps entier (`replace_text`). Le fichier est lu avant tout
    appel à la forge."""
    if args.append:
        return issue_append(run, args)
    body, anchor = read_text_file(args.body_file)
    return replace_text(run, issue_body(run, args.number), body, anchor, args.body_file)


def publish_comment(run: Run, number: str, expected: str, anchor: str) -> int:
    """Publie `expected` en commentaire de `number`, puis le relit sous l'`id` que rend la
    publication, et rend cet `id`.

    Raises:
        Divergence: publication ou relecture en échec, ou commentaire relu autre que `expected`
            (`check_reread`, ancre `anchor`).
    """
    publish = ("-X", "POST", comments_path(number), "--input", "-")
    with writing():
        identifier = read_json(run, comment_id, *publish, stdin=json_payload(body=expected))
        reread = read_json(run, body_of, comment_path(identifier))
    check_reread(expected, reread, [anchor])
    return identifier


def comment_publish(run: Run, args: argparse.Namespace) -> str:
    """`comment` : publie le fichier en commentaire, sauf si un commentaire porte déjà ce texte
    exactement, puis relit le commentaire sous l'`id` que rend la publication. Le fichier est lu
    avant tout appel à la forge."""
    expected, anchor = read_text_file(args.file)
    # ponytail: pas de verrou — un même texte publié entre la lecture et la publication fait un
    # doublon ; relire les commentaires après la publication si un doublon se constate.
    same = issue_comments(run, args.number, lambda body: body == expected)
    if same:
        identifier, _ = same[0]
        return f"rien à écrire — #{args.number} porte déjà ce commentaire ({identifier})"
    identifier = publish_comment(run, args.number, expected, anchor)
    return f"publié et relu — commentaire {identifier} sur #{args.number}"


def brief_write(run: Run, args: argparse.Namespace) -> str:
    """`brief write` : publie le fichier en commentaire de brief de `<N>` (`publish_comment`), ou
    édite en place le seul qui existe (`replace_text`) — « jamais un second brief concurrent »
    (`triage/brief-agent.md`). Le fichier est lu, et sa marque vérifiée, avant tout appel.

    Raises:
        Refusal: fichier inutilisable, fichier qui ne s'ouvre pas par `## Brief d'agent` —
            `brief patch` ne le reconnaîtrait plus (`is_brief`) —, ou plusieurs briefs.
    """
    body, anchor = read_text_file(args.file)
    if not is_brief(body):
        raise Refusal(f"{args.file} ne s'ouvre pas par {BRIEF_MARK}")
    briefs = brief_comments(run, args.number)
    if len(briefs) > 1:
        raise Refusal(
            f"{len(briefs)} commentaires de brief sur #{args.number} : aucun ne s'édite en place"
        )
    if briefs:
        return replace_text(run, briefs[0], body, anchor, args.file)
    identifier = publish_comment(run, args.number, body, anchor)
    return f"publié et relu — brief de #{args.number} : commentaire {identifier}"


def repo_labels(run: Run, wanted: Sequence[str]) -> list[str]:
    """Le nom que le dépôt donne à chaque label de `wanted`, apparié comme `carried_label`, sur
    toutes les pages de ses labels.

    Raises:
        Refusal: un label de `wanted` n'existe pas dans le dépôt — chacun est nommé.
    """
    if not wanted:
        return []
    known = read_json(
        run,
        lambda pages: [name for page in pages for name in names_of(page)],
        "--paginate",
        "--slurp",
        f"{REPO}/labels",
    )
    found = {label: carried_label(known, label) for label in wanted}
    missing = [f"label inconnu du dépôt : {label}" for label, name in found.items() if name is None]
    if missing:
        raise Refusal(" ; ".join(missing))
    return [name for name in found.values() if name is not None]


def same_issue(pages: Any, title: str, body: str) -> int | None:
    """Le numéro de la première issue — pas une PR, que son champ `pull_request` distingue — qui
    porte exactement `title` et `body`, sur les pages que `gh api --paginate --slurp` rend.

    Raises:
        KeyError, TypeError: une issue sans titre textuel ou sans corps textuel ni `null`, ou
            l'issue retenue sans numéro entier (`typed`).
    """
    return next(
        (
            typed(issue, "number", int)
            for page in pages
            for issue in page
            if "pull_request" not in issue
            and typed(issue, "title", str) == title
            and body_of(issue) == body
        ),
        None,
    )


def issue_create(run: Run, args: argparse.Namespace) -> str:
    """`issue create` : crée l'issue — titre, corps et labels en une seule requête —, sauf si une
    issue ouverte porte déjà ce titre et ce corps — la liste des issues de l'API REST ne rend
    que les ouvertes par défaut —, puis la relit sous le numéro que rend la création. Le fichier
    est lu, et les labels validés, avant toute écriture.

    Raises:
        Refusal: fichier inutilisable (`read_text_file`) ou label inconnu (`repo_labels`).
        Divergence: création ou relecture en échec, ou issue relue autre que celle écrite —
            corps entier (`check_reread`), titre exact, ensemble des labels.
    """
    body, anchor = read_text_file(args.file)
    labels = repo_labels(run, args.labels)
    same = read_json(
        run, lambda pages: same_issue(pages, args.title, body), "--paginate", "--slurp", ISSUES
    )
    if same is not None:
        return f"rien à écrire — #{same} existe déjà"
    # ponytail: pas de verrou — une même issue créée entre la lecture et la création fait un
    # doublon ; relire les issues ouvertes après la création si un doublon se constate.
    create = ("-X", "POST", ISSUES, "--input", "-")
    payload = json_payload(title=args.title, body=body, labels=labels)
    with writing():
        number = read_json(run, lambda issue: typed(issue, "number", int), *create, stdin=payload)
        title, reread, carried = read_json(
            run,
            lambda issue: (typed(issue, "title", str), body_of(issue), label_names(issue)),
            issue_path(str(number)),
        )
    check_reread(body, reread, [anchor])
    if title != args.title:
        raise Divergence(f"titre attendu {args.title!r}, relu {title!r}")
    if set(carried) != set(labels):
        raise Divergence(f"labels attendus {sorted(labels)}, relus {sorted(carried)}")
    return f"créé et relu — issue #{number}"


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
    """Les sous-commandes du module ; chacune pose son `handler`."""
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
    checkbox = commands.add_parser("checkbox").add_subparsers(dest="action", required=True)
    brief = commands.add_parser("brief").add_subparsers(dest="action", required=True)
    for actions, locate in ((checkbox, issue_body), (brief, brief_comment)):
        boxes = actions.add_parser("patch")
        boxes.add_argument("number", type=issue_number)
        boxes.add_argument("--case", dest="anchors", type=one_line, action="append", required=True)
        boxes.set_defaults(handler=patch_boxes, locate=locate)
    write = brief.add_parser("write")
    write.add_argument("number", type=issue_number)
    write.add_argument("--body-file", dest="file", type=Path, required=True)
    write.set_defaults(handler=brief_write)
    actions = commands.add_parser("issue").add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--title", type=one_line, required=True)
    create.add_argument("--body-file", dest="file", type=Path, required=True)
    create.add_argument("--label", dest="labels", type=one_line, action="append", default=[])
    create.set_defaults(handler=issue_create)
    edit = actions.add_parser("edit")
    edit.add_argument("number", type=issue_number)
    source = edit.add_mutually_exclusive_group(required=True)
    source.add_argument("--append", type=Path)
    source.add_argument("--body-file", type=Path)
    edit.set_defaults(handler=issue_edit)
    comment = commands.add_parser("comment")
    comment.add_argument("number", type=issue_number)
    comment.add_argument("--body-file", dest="file", type=Path, required=True)
    comment.set_defaults(handler=comment_publish)
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
