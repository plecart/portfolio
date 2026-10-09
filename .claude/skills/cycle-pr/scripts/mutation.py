"""Éprouve des tests par mutation : témoin d'abord, puis chaque mutation, fichier restauré octet
pour octet. Le verdict se lit dans le **rapport structuré** du lanceur, jamais dans son code de
sortie — un code de sortie ne nomme pas le test qui a rougi.

Usage : python mutation.py <racine du dépôt> <mutations.json>

`mutations.json` :

    {
      "targets": ["apps/api/tests/test_x.py"],
      "reporter": "junit",
      "label": "test ciblé",
      "stack": "Back",
      "mutations": [
        {"name": "garde retirée", "file": "apps/api/x.py", "old": "if n < 0:", "new": "if False:",
         "expect": ["test_refuse_un_negatif"]}
      ]
    }

- `targets` : ce que la commande reçoit en arguments — le **fichier de test visé**, pas la suite.
- `reporter` : `junit` (pytest), `vitest` ou `playwright` ; défaut `junit`. Les commandes du
  projet sont des cibles `make`, donc le lanceur se nomme ici au lieu d'être deviné.
- `label` et `stack` : la ligne de « Commandes du projet » à lire ; défauts `test ciblé` / `Back`.
- `old` s'écrit en LF : les fins de ligne du fichier muté lui sont appliquées à la lecture.

Tout tient dans ce fichier, racine mise à part : un harnais paramétré par sa ligne de commande
n'est pas transmissible tel quel, et c'est ce qui a fait le réécrire sept fois (obs 37).

Verdict par mutation : `ROUGE` (tous les attendus ont rougi), `VERT` (au moins un attendu est
resté vert — le test ne tient pas), `PANNE` (`old` absent ou multiple, rapport illisible, refus).

Python 3.11 ou plus, bibliothèque standard seule.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree

# Une pile de « Commandes du projet » : `**Back (`apps/api/`)** — vérifiées le …`.
STACK_HEADING = re.compile(r"^\*\*(?P<stack>\w+) \(")
# Une ligne de commande : `- test ciblé   : uv run pytest <chemin|motif>     # commentaire`.
COMMAND_LINE = re.compile(r"^- (?P<label>[^:]+?)\s*:\s(?P<command>.+)$")
# Un gabarit à remplir par l'appelant : `<chemin|motif>`.
PLACEHOLDER = re.compile(r"\s*<[^>]+>")
COMMANDS_SECTION = "## Commandes du projet"
UNAVAILABLE = "n/a"


def project_command(config: Path, label: str, stack: str = "Back") -> str:
    """La commande que « Commandes du projet » associe à un libellé, dans une pile donnée.

    Les libellés se répètent d'une pile à l'autre — « test ciblé » existe pour le back, l'infra
    et le front —, donc la pile fait partie de la clé. La recherche est bornée à la section :
    un libellé homonyme ailleurs dans le fichier ne doit pas pouvoir répondre à sa place.

    Args:
        config: le `pipeline.config.md` à lire.
        label: le libellé exact de la ligne, sans ses espaces d'alignement.
        stack: le nom de la pile, tel que son titre en gras le porte.

    Returns:
        La commande, commentaire retiré et gabarits `<…>` ôtés — l'appelant ajoute ses cibles.

    Raises:
        LookupError: aucune ligne pour ce couple, ou une ligne marquée `n/a` — l'étape est
            absente du projet, et la deviner vaudrait moins que s'arrêter.
    """
    inside = False
    current = ""
    for line in config.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == COMMANDS_SECTION
            continue
        if not inside:
            continue
        heading = STACK_HEADING.match(line)
        if heading:
            current = heading.group("stack")
            continue
        found = COMMAND_LINE.match(line)
        if not found or current != stack or found.group("label").strip() != label:
            continue
        command = PLACEHOLDER.sub("", found.group("command").split("#")[0]).strip()
        if command == UNAVAILABLE:
            raise LookupError(f"« {label} » vaut `n/a` pour la pile {stack} : étape absente")
        return command
    raise LookupError(f"aucune commande « {label} » pour la pile {stack} dans {config}")


# --- Les rapporteurs : demander un rapport structuré, puis le lire ----------------------------
#
# Un code de sortie dit qu'« un » test a rougi, jamais lequel : une mutation neutralisée par
# l'outil muté lui-même a déjà compté comme preuve parce qu'un *autre* test échouait (obs 37,
# complément du 2026-10-04). D'où la lecture d'un rapport, et la recherche du nom attendu dedans.
#
# Chaque lanceur se nomme dans le fichier de mutations : les commandes du projet sont des cibles
# `make`, donc « make test » ne contient aucun indice de son lanceur, et le renifler serait une
# supposition de plus. Ajouter un lanceur = ajouter une entrée ici, rien d'autre.


def junit_outcomes(text: str) -> dict[str, str]:
    """Les états d'un rapport JUnit (`pytest --junitxml`), par `classname::name`.

    L'identifiant n'est jamais découpé : un test paramétré porte son cas entre crochets, espaces
    et deux-points compris, et le tronquer à la première espace rendait seize rouges « VERT ».
    """
    outcomes: dict[str, str] = {}
    for case in ElementTree.fromstring(text).iter("testcase"):
        state = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                state = "failed"
            elif child.tag == "skipped":
                state = "skipped"
        outcomes[f"{case.get('classname', '')}::{case.get('name', '')}"] = state
    return outcomes


def vitest_outcomes(text: str) -> dict[str, str]:
    """Les états d'un rapport Vitest (`--reporter=json`), par `fullName`.

    Forme mesurée le 2026-10-09 sur le lanceur du dépôt :
    `{"testResults": [{"assertionResults": [{"fullName", "status"}]}]}`.
    """
    report = cast(dict[str, Any], json.loads(text))
    return {
        str(assertion["fullName"]): str(assertion["status"])
        for suite in cast(list[dict[str, Any]], report.get("testResults") or [])
        for assertion in cast(list[dict[str, Any]], suite.get("assertionResults") or [])
    }


# `expected` / `unexpected` est le vocabulaire d'un `test` Playwright, distinct du
# `passed` / `failed` de ses `results`. `flaky` n'est volontairement pas traduit en `failed` : un
# test qui n'a rougi qu'à un essai sur deux n'a pas *attrapé* la mutation, et le compter rouge
# ferait mentir le harnais dans le sens qui l'arrange.
PLAYWRIGHT_STATES = {"expected": "passed", "unexpected": "failed"}


def playwright_specs(suite: Mapping[str, Any], path: str = "") -> Iterator[tuple[str, str]]:
    """Parcourt les `suites` imbriquées d'un rapport Playwright et rend (nom, état) par essai.

    Le nom porte le chemin complet des groupes, puis le nom du projet quand la spec a tourné
    sur plusieurs : les deux projets du dépôt jouent chaque spec, et une clé sans projet en
    perdrait la moitié en silence.
    """
    here = f"{path} > {suite['title']}" if path else str(suite.get("title", ""))
    for spec in cast(list[dict[str, Any]], suite.get("specs") or []):
        tests = cast(list[dict[str, Any]], spec.get("tests") or [])
        for test in tests:
            project = str(test.get("projectName") or "")
            suffix = f" [{project}]" if project and len(tests) > 1 else ""
            state = str(test.get("status", ""))
            yield f"{here} > {spec['title']}{suffix}", PLAYWRIGHT_STATES.get(state, state)
    for nested in cast(list[dict[str, Any]], suite.get("suites") or []):
        yield from playwright_specs(nested, here)


def playwright_outcomes(text: str) -> dict[str, str]:
    """Les états d'un rapport Playwright (`--reporter=json`), par chemin de spec.

    Forme mesurée le 2026-10-09 sur le lanceur du dépôt : `{"suites": [{"title", "specs": [
    {"title", "ok", "tests": [{"projectName", "status", "results": [{"status"}]}]}], "suites"}]}`.
    """
    report = cast(dict[str, Any], json.loads(text))
    return dict(
        pair
        for suite in cast(list[dict[str, Any]], report.get("suites") or [])
        for pair in playwright_specs(suite)
    )


@dataclass(frozen=True)
class Reporter:
    """Comment obtenir d'un lanceur un rapport lisible, et comment l'interpréter.

    Attributes:
        flags: à ajouter à la commande ; `{report}` y vaut le chemin du rapport.
        outcomes: lit le texte du rapport et rend un état par test.
        env: variables d'environnement à poser, `{report}` substitué de même — Playwright ne
            prend pas le chemin de son rapport JSON en option.
    """

    flags: str
    outcomes: Callable[[str], dict[str, str]]
    env: Mapping[str, str] = field(default_factory=dict)


REPORTERS = {
    "junit": Reporter(' --junitxml="{report}"', junit_outcomes),
    "vitest": Reporter(' --reporter=json --outputFile="{report}"', vitest_outcomes),
    "playwright": Reporter(
        " --reporter=json",
        playwright_outcomes,
        {"PLAYWRIGHT_JSON_OUTPUT_NAME": "{report}"},
    ),
}


# --- Le refus de muter un réglage de sécurité (obs 53) ----------------------------------------
#
# Le classifieur du mode auto refuse de lancer une suite sur une configuration de sécurité
# affaiblie, et le refus vaut pour toute voie de contournement : un autre outil, un sous-agent,
# un tour ultérieur. La procédure ne peut donc pas aboutir pour la classe de gardes où elle
# compte le plus — celles qui protègent un réglage de sécurité. Le harnais ne tente rien : il
# refuse, et renvoie à la forme qui prouve autant sans toucher au dépôt.

SECURITY_PATHS = {
    "exception de scanner": re.compile(r"(^|/)\.trivyignore|pip-audit-exceptions"),
    "porte de CI": re.compile(r"(^|/)\.github/(workflows|actions)/"),
    "permission d'agent": re.compile(r"(^|/)settings\.json$"),
}
SECURITY_CONTENTS = {
    "option de blocage d'un scanner": re.compile(
        r"--ignore-unfixed|--exit-code|--severity|--fail-on|--no-verify|--skip-"
    ),
    "épingle d'empreinte": re.compile(r"@sha256:[0-9a-f]{64}"),
    "règle de permission": re.compile(r'"(allow|deny|ask)"\s*:'),
}
ALTERNATIVE = (
    "écrire la garde en fonction sur du texte et la voir rouge sur un recueil de formes "
    "fautives construites en mémoire, à côté du test qui l'applique au dépôt (modèle "
    "`WORKFLOW_FORMS` de `test_supply_chain.py`) — le dépôt n'est jamais affaibli"
)


def security_refusal(mutation: Mapping[str, Any]) -> str | None:
    """Pourquoi cette mutation est refusée, ou `None` si elle est ordinaire.

    Args:
        mutation: l'entrée `{name, file, old, new, …}` du fichier de mutations.

    Returns:
        Le motif du refus, suivi de la forme à employer à la place, ou `None`.
    """
    target = str(mutation.get("file", "")).replace("\\", "/")
    texts = f"{mutation.get('old', '')}\n{mutation.get('new', '')}"
    fired = [label for label, pattern in SECURITY_PATHS.items() if pattern.search(target)]
    fired += [label for label, pattern in SECURITY_CONTENTS.items() if pattern.search(texts)]
    if not fired:
        return None
    return f"refus — réglage de sécurité ({', '.join(fired)}) ; à la place : {ALTERNATIVE}"


# --- La boucle : témoin, mutation, restauration, verdict ---------------------------------------

RED = "failed"
CONFIG = Path(".claude") / "pipeline.config.md"


class Unusable(Exception):
    """Une mutation qu'on ne peut pas jouer, avec son motif — jamais un verdict sur le test.

    `old` absent ou trouvé plusieurs fois, aucun rouge attendu nommé, rapport illisible, refus
    d'un réglage de sécurité : dans tous ces cas le test visé n'a rien prouvé ni rien infirmé,
    et les confondre avec un VERT ferait condamner un test que personne n'a éprouvé.
    """


@dataclass(frozen=True)
class Verdict:
    """Le résultat d'une mutation : `ROUGE`, `VERT` ou `PANNE`, et de quoi le relire."""

    verdict: str
    name: str
    detail: str

    def __str__(self) -> str:
        return f"{self.verdict:<6} {self.name} : {self.detail}"


@dataclass(frozen=True)
class Suite:
    """La suite à relancer entre deux mutations : sa commande, ses cibles, son rapporteur."""

    root: Path
    command: str
    reporter: Reporter
    targets: Sequence[str]

    @classmethod
    def from_spec(cls, root: Path, spec: Mapping[str, Any]) -> "Suite":
        """Construit la suite d'un fichier de mutations, commande lue dans la configuration."""
        return cls(
            root,
            project_command(
                root / CONFIG, str(spec.get("label", "test ciblé")), str(spec.get("stack", "Back"))
            ),
            REPORTERS[str(spec.get("reporter", "junit"))],
            cast(list[str], spec.get("targets") or []),
        )

    def outcomes(self) -> dict[str, str]:
        """Lance la suite et rend un état par test.

        La commande passe par le shell : celles du projet en sont (`cd apps/web && npm test`,
        `make test`), et les découper en arguments les casserait.

        Raises:
            Unusable: le lanceur n'a produit aucun rapport — sans rapport, aucun verdict ne peut
                nommer le test qui a rougi, et un code de sortie n'y suffit pas.
        """
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report"
            quoted = "".join(f' "{target}"' for target in self.targets)
            environment = dict(os.environ) | {
                name: value.format(report=report) for name, value in self.reporter.env.items()
            }
            subprocess.run(
                self.command + self.reporter.flags.format(report=report) + quoted,
                cwd=self.root,
                shell=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            if not report.is_file():
                raise Unusable(f"aucun rapport produit par « {self.command} »")
            return self.reporter.outcomes(report.read_text(encoding="utf-8"))


def mutated_bytes(path: Path, old: str, new: str) -> tuple[bytes, bytes]:
    """Rend (contenu d'origine, contenu muté), en octets de bout en bout.

    Les fins de ligne du fichier muté commandent celles du motif : les worktrees sont extraits
    en CRLF et l'arbre de l'auteur en LF, donc un `old` écrit en LF n'y serait jamais trouvé.
    Tout passe par des octets — décoder pour remplacer réécrirait le fichier dans un autre
    encodage et changerait ce qu'on prétend n'avoir pas touché.

    Raises:
        Unusable: `old` n'apparaît pas exactement une fois ; le remplacement porterait alors
            sur autre chose que ce que la mutation annonce.
    """
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    pattern = old.replace("\n", newline).encode("utf-8")
    count = original.count(pattern)
    if count != 1:
        raise Unusable(f"`old` trouvé {count} fois dans {path.name}, il en faut exactement une")
    return original, original.replace(pattern, new.replace("\n", newline).encode("utf-8"))


def judge(suite: Suite, entry: Mapping[str, Any]) -> Verdict:
    """Joue une mutation et rend son verdict, le fichier restauré octet pour octet.

    Args:
        suite: la suite à relancer sous la mutation.
        entry: l'entrée `{name, file, old, new, expect}` du fichier de mutations.

    Returns:
        `ROUGE` si **tous** les noms de `expect` figurent parmi les rouges, `VERT` si l'un d'eux
        est resté vert, `PANNE` si la mutation n'a pas pu être jouée.
    """
    name = str(entry.get("name", "?"))
    try:
        refusal = security_refusal(entry)
        if refusal:
            raise Unusable(refusal)
        expected = cast(list[str], entry.get("expect") or [])
        if not expected:
            raise Unusable("aucun rouge attendu nommé dans `expect`")
        path = suite.root / str(entry["file"])
        original, mutated = mutated_bytes(path, str(entry["old"]), str(entry["new"]))
        try:
            path.write_bytes(mutated)
            outcomes = suite.outcomes()
        finally:
            path.write_bytes(original)
    except Unusable as reason:
        return Verdict("PANNE", name, str(reason))

    red = sorted(test for test, state in outcomes.items() if state == RED)
    missing = [fragment for fragment in expected if not any(fragment in test for test in red)]
    detail = f"rouges : {red}"
    return Verdict(
        "VERT" if missing else "ROUGE",
        name,
        f"attendus restés verts : {missing} ; {detail}" if missing else detail,
    )


def play(root: Path, spec: Mapping[str, Any]) -> list[Verdict]:
    """Joue toutes les mutations d'un fichier de mutations et rend un verdict par mutation.

    Dans l'ordre : les refus de sécurité, qui n'exécutent rien ; le témoin sur l'arbre propre,
    dont le vert est exigé — un rouge déjà présent ferait passer pour attrapée une mutation que
    rien n'a vue ; puis chaque mutation.

    Args:
        root: la racine du dépôt muté.
        spec: `{targets, mutations, reporter?, label?, stack?}`.

    Returns:
        Un `Verdict` par mutation, dans l'ordre du fichier.
    """
    mutations = cast(list[dict[str, Any]], spec["mutations"])
    names = [str(entry.get("name", "?")) for entry in mutations]
    refusals = [security_refusal(entry) for entry in mutations]
    if mutations and all(refusals):
        return [Verdict("PANNE", name, str(why)) for name, why in zip(names, refusals)]

    suite = Suite.from_spec(root, spec)
    try:
        witness = suite.outcomes()
        already = sorted(test for test, state in witness.items() if state == RED)
        if already:
            raise Unusable(f"rouges déjà présents avant toute mutation : {already}")
    except Unusable as reason:
        return [Verdict("PANNE", name, f"témoin : {reason}") for name in names]

    return [judge(suite, entry) for entry in mutations]


def main(argv: Sequence[str]) -> int:
    """Point d'entrée : rend 0 si *toutes* les mutations sont ROUGE, 1 sinon.

    Un seul VERT ou une seule PANNE fait rendre 1 : le harnais est une porte, et une preuve
    partielle n'est pas une preuve.
    """
    if len(argv) != 2:
        print(__doc__)
        return 2
    verdicts = play(Path(argv[0]), json.loads(Path(argv[1]).read_text(encoding="utf-8")))
    for verdict in verdicts:
        print(verdict)
    caught = sum(1 for verdict in verdicts if verdict.verdict == "ROUGE")
    print(f"\n{caught}/{len(verdicts)} mutations attrapées")
    return 0 if verdicts and caught == len(verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
