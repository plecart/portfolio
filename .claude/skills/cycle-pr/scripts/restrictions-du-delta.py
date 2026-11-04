"""Rend chaque ligne restrictive qu'un delta retire de la prose normative de la pipeline.

Usage :
    python restrictions-du-delta.py <base>

La passe « restrictions du delta » de la relecture (`cycle-pr/references/session-relecture.md`,
« Réveil ») : une restriction retirée d'une règle — « Ne jamais interrompre pour le journal »
devenu « Interrompre rarement pour le journal » — ne fait rougir aucun test ; elle se lit sur le
diff, et chaque ligne rendue reçoit sa réponse dans le message de constats. Dans cet ordre :

1. la gauche du delta, `git merge-base <base> HEAD` — celle de `git diff <base>...HEAD` ;
2. `git diff -U0 --find-renames <gauche> HEAD`, restreint à `.claude/**/*.md`, `CLAUDE.md` et
   `CONTRIBUTING.md`, chemins pris à la racine du dépôt quel que soit le dossier courant ;
3. chaque ligne retirée — une ligne modifiée y est retirée, puis ajoutée — qui porte une marque de
   `MARQUES_RESTRICTIVES`, en mot entier, sans la casse ;
4. sa section : le dernier titre Markdown au-dessus d'elle dans la version de gauche du fichier
   (`git cat-file blob <gauche>:<fichier>`), hors des blocs de code clôturés ; `—` sans titre.

Sur la sortie standard, une ligne par ligne retenue, `<fichier> § <section> : <ligne retirée>`,
le fichier sous son chemin de gauche ; rien si aucune ligne marquée n'est retirée. Les clés de
configuration qui changent ce que `git diff` rend — `color.ui`, `diff.external`, `diff.relative`,
`diff.noprefix`, `diff.renames`, `core.quotePath` — sont neutralisées par ses options (mesuré le
2026-11-04, git 2.47.1). Chaque lecture décode ses octets en UTF-8 explicitement, jamais par la page de code
de la console (obs 108).

**Ce qu'il ne couvre pas.** Une restriction affaiblie sans ligne marquée retirée — une marque
ajoutée ailleurs qui la contredit, un mot hors de la table. Une ligne déplacée, que le diff rend
retirée ou non selon son alignement. La prose hors de ces chemins. La réponse à chaque ligne :
le script la donne à la relecture, il ne juge pas.

Sortie : 0 dès que `git` répond, ligne rendue ou non ; 2 `git` en échec — base inconnue, hors
d'un dépôt, `git` introuvable —, motif sur la sortie d'erreur, ou appel mal formé. Python 3.11
ou plus, bibliothèque standard seule ; `git`, lancé depuis le dépôt.
"""

import argparse
import io
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence

PATHSPECS = (":(top,glob).claude/**/*.md", ":(top)CLAUDE.md", ":(top)CONTRIBUTING.md")
# Toutes sauf `-U0` neutralisent une clé : `color.ui`, `diff.external`, `diff.relative`, les
# préfixes, `diff.renames`.
DIFF_OPTIONS = (
    "--no-color",
    "--no-ext-diff",
    "--no-relative",
    "--no-prefix",
    "-U0",
    "--find-renames",
)
# Les marques d'une moitié restrictive, en mots entiers : « ne … pas » comme « ne … que » s'y
# lisent par « ne » ou « n' ».
MARQUES_RESTRICTIVES = (
    "jamais",
    "seule",
    "seul",
    "seulement",
    "reste à",
    "ne",
    "n'",
    "ni",
    "sans",
    "aucun",
    "aucune",
)
MARQUE_RESTRICTIVE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(marque) + ("" if marque.endswith("'") else r"(?!\w)")
        for marque in sorted(MARQUES_RESTRICTIVES, key=len, reverse=True)
    )
    + ")",
    re.IGNORECASE,
)
# `@@ -<début>[,<nombre>] +… @@` : la place des lignes retirées dans la version de gauche.
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? ")
HEADING = re.compile(r" {0,3}#{1,6}[ \t]+(.+)")
FENCE = re.compile(r" {0,3}(?:```|~~~)")


class GitError(Exception):
    """`git` n'a pas répondu ; le message est le motif, en une ligne."""


def git(*args: str) -> str:
    """La sortie standard de `git <args>`, décodée en UTF-8."""
    try:
        done = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args], capture_output=True, check=False
        )
    except OSError as error:
        raise GitError(f"git introuvable : {error}") from error
    if done.returncode:
        motif = done.stderr.decode("utf-8", "replace").strip()
        raise GitError(motif or f"git {args[0]} sort en {done.returncode}")
    return done.stdout.decode("utf-8", "replace")


def removed_lines(diff: str) -> Iterator[tuple[str, int, str]]:
    """Chaque ligne retirée d'un diff `-U0 --no-prefix` : son fichier et son numéro à gauche, son
    texte. Une ligne retirée qui commence par `-- ` se lit `--- ` : seul le compte de l'en-tête
    de bloc la distingue de l'en-tête de fichier."""
    path, number, pending = "", 0, 0
    for line in diff.split("\n"):
        if pending and line.startswith("-"):
            yield path, number, line[1:]
            number += 1
            pending -= 1
        elif line.startswith("--- "):
            # Un chemin à espace se termine par une tabulation (mesuré le 2026-11-04).
            path = line[4:].rstrip()
        elif hunk := HUNK.match(line):
            number, pending = int(hunk[1]), int(hunk[2] or 1)


def section(lines: Sequence[str], number: int) -> str:
    """Le dernier titre Markdown au-dessus de la ligne `number` (1 pour la première), hors des
    blocs de code clôturés ; `—` sans titre."""
    title, fenced = "—", False
    for line in lines[: number - 1]:
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (heading := HEADING.match(line)):
            title = heading[1].strip()
    return title


def restrictions(base: str) -> list[str]:
    """Les lignes marquées que `HEAD` retire depuis sa base commune avec `base`, rendues."""
    left = git("merge-base", base, "HEAD").strip()
    diff = git("diff", *DIFF_OPTIONS, left, "HEAD", "--", *PATHSPECS)
    texts: dict[str, list[str]] = {}
    found: list[str] = []
    for path, number, text in removed_lines(diff):
        if MARQUE_RESTRICTIVE.search(text):
            if path not in texts:
                texts[path] = git("cat-file", "blob", f"{left}:{path}").split("\n")
            found.append(f"{path} § {section(texts[path], number)} : {text.strip()}")
    return found


def main(argv: Sequence[str]) -> int:
    """Point d'entrée ; voir le module pour les sorties."""
    parser = argparse.ArgumentParser(
        prog="restrictions-du-delta.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("base", help="le début de la plage relue, une référence git")
    args = parser.parse_args(argv)
    try:
        lines = restrictions(args.base)
    except GitError as error:
        print(f"git en échec — {error}", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    # Sur un poste dont la page de code est cp1252, Python écrit un tube dans cet encodage : les
    # lignes, accentuées, arriveraient illisibles à la relecture (`pipeline.config.md`, « Qualité »).
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
