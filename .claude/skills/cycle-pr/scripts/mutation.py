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
# Le libellé peut contenir un `:` — `format:check` en est un, et un `[^:]+?` le rendait
# introuvable alors que sa ligne existe. Ce qui sépare le libellé de la commande est l'espace
# **avant** le deux-points, que l'alignement du fichier garantit.
COMMAND_LINE = re.compile(r"^- (?P<label>.+?)\s+:\s(?P<command>.+)$")
# Un commentaire de fin de ligne, aligné sur au moins deux espaces — pas un `#` dans une
# commande, qui serait tronquée.
TRAILING_COMMENT = re.compile(r"\s{2,}#.*$")
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
        bare = TRAILING_COMMENT.sub("", found.group("command"))
        command = PLACEHOLDER.sub("", bare).strip()
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

# Chemins dont le contenu *est* un réglage de sécurité. Recensés sur ce dépôt le 2026-10-09,
# après qu'une relecture en a mesuré 12 formes réelles non couvertes par les trois premiers
# motifs. Un projet qui range ses réglages ailleurs ajoute son motif ici.
SECURITY_PATHS = {
    "exception de scanner": re.compile(r"(^|/)\.trivyignore|pip-audit-exceptions"),
    "porte de CI": re.compile(r"(^|/)\.github/(workflows|actions)/"),
    "configuration de Dependabot": re.compile(r"(^|/)\.github/dependabot\.ya?ml$"),
    "propriétaires du code": re.compile(r"(^|/)CODEOWNERS$"),
    "permission d'agent": re.compile(r"(^|/)settings(\.local)?\.json$|(^|/)\.claude/settings"),
    "serveurs MCP": re.compile(r"(^|/)\.mcp\.json$"),
    "hooks de pré-commit": re.compile(r"(^|/)\.pre-commit-config\.ya?ml$"),
    "en-têtes du serveur web": re.compile(r"(^|/)Caddyfile$"),
    "composition de production": re.compile(r"(^|/)compose([.-][\w.-]+)?\.ya?ml$"),
    "réglages de l'application": re.compile(r"(^|/)config/settings\.py$"),
}

# Motifs de **contenu**, cherchés dans `old` et `new` — mais seulement dans un fichier de
# configuration. Appliqués partout, ils refusaient des mutations parfaitement ordinaires :
# mesuré en relecture, 5 cas sur 6, dont le propre recueil de ce script, son propre test de
# refus, et deux épingles de digest dans des modules de support de test. Un refus qui mord sur
# le travail ordinaire est un refus qu'on apprend à contourner.
SECURITY_CONTENTS = {
    "option de blocage d'un scanner": re.compile(
        r"--ignore-unfixed|--exit-code|--severity|--fail-on|--no-verify|--skip-"
    ),
    "épingle d'empreinte": re.compile(r"@sha256:[0-9a-f]{64}"),
    "règle de permission": re.compile(r'"(allow|deny|ask)"\s*:'),
}

# Ce qui compte comme fichier de configuration, pour borner les motifs de contenu ci-dessus.
CONFIGURATION_SUFFIXES = (".yml", ".yaml", ".toml", ".json", ".cfg", ".ini", ".sh", ".ps1", ".env")
CONFIGURATION_NAMES = ("Makefile", "justfile", "Dockerfile", "Caddyfile", "crontab")

ALTERNATIVE = (
    "écrire la garde en fonction sur du texte et la voir rouge sur un recueil de formes "
    "fautives construites en mémoire, à côté du test qui l'applique au dépôt (modèle "
    "`WORKFLOW_FORMS` de `test_supply_chain.py`) — le dépôt n'est jamais affaibli"
)


def is_configuration(target: str) -> bool:
    """Le chemin désigne-t-il un fichier de configuration, au sens des motifs de contenu ?"""
    name = target.rsplit("/", 1)[-1]
    return name.startswith(CONFIGURATION_NAMES) or name.endswith(CONFIGURATION_SUFFIXES)


def security_refusal(mutation: Mapping[str, Any]) -> str | None:
    """Pourquoi cette mutation est refusée, ou `None` si elle est ordinaire.

    **Une heuristique, pas une frontière.** Elle ne peut pas être complète : le même
    affaiblissement s'obtient par un point de contrôle équivalent qu'aucun motif ne décrit —
    retirer la dépendance d'une cible `make` qui charge les images à scanner affaiblit le scan
    sans qu'aucune option de scanner apparaisse dans le diff. Son office est d'arrêter les
    formes courantes et de **renvoyer à la forme qui prouve autant sans toucher au dépôt** ;
    l'auteur reste responsable de reconnaître les autres. Un refus présenté comme une garantie
    serait plus nuisible que son absence.

    Args:
        mutation: l'entrée `{name, file, old, new, …}` du fichier de mutations.

    Returns:
        Le motif du refus, suivi de la forme à employer à la place, ou `None`.
    """
    target = str(mutation.get("file", "")).replace("\\", "/")
    fired = [label for label, pattern in SECURITY_PATHS.items() if pattern.search(target)]
    if is_configuration(target):
        texts = f"{mutation.get('old', '')}\n{mutation.get('new', '')}"
        fired += [label for label, pattern in SECURITY_CONTENTS.items() if pattern.search(texts)]
    if not fired:
        return None
    return f"refus — réglage de sécurité ({', '.join(fired)}) ; à la place : {ALTERNATIVE}"


# --- La boucle : témoin, mutation, restauration, verdict ---------------------------------------

RED = "failed"
CONFIG = Path(".claude") / "pipeline.config.md"
# Une mutation fabrique des boucles sans fin : la condition d'arrêt est ce qu'on vient de casser.
DEFAULT_TIMEOUT = 900


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


def tail(text: str, lines: int = 6) -> str:
    """Les dernières lignes non vides d'une sortie, pour qu'une PANNE dise ce qui a échoué."""
    kept = [line for line in (text or "").splitlines() if line.strip()][-lines:]
    return " / ".join(kept) if kept else "(vide)"


@dataclass(frozen=True)
class Suite:
    """La suite à relancer entre deux mutations : sa commande, ses cibles, son rapporteur."""

    root: Path
    command: str
    reporter: Reporter
    targets: Sequence[str]
    timeout: int = DEFAULT_TIMEOUT

    @classmethod
    def from_spec(cls, root: Path, spec: Mapping[str, Any]) -> "Suite":
        """Construit la suite d'un fichier de mutations, commande lue dans la configuration.

        Raises:
            Unusable: le rapporteur nommé n'existe pas. Une clé inconnue doit rendre un verdict,
                pas une `KeyError` nue sur une entrée écrite à la main.
            LookupError: propagé par `project_command` — le libellé n'existe pas pour cette
                pile, ou la ligne y vaut `n/a`. `play` traduit les deux en PANNE de témoin.
        """
        name = str(spec.get("reporter", "junit"))
        if name not in REPORTERS:
            raise Unusable(f"rapporteur « {name} » inconnu ; connus : {sorted(REPORTERS)}")
        return cls(
            root,
            project_command(
                root / CONFIG, str(spec.get("label", "test ciblé")), str(spec.get("stack", "Back"))
            ),
            REPORTERS[name],
            cast(list[str], spec.get("targets") or []),
            int(spec.get("timeout", DEFAULT_TIMEOUT)),
        )

    def outcomes(self) -> dict[str, str]:
        """Lance la suite et rend un état par test.

        La commande passe par le shell : celles du projet en sont (`cd apps/web && npm test`,
        `make test`), et les découper en arguments les casserait.

        Raises:
            Unusable: le lanceur n'a produit aucun rapport, a dépassé le délai, ou a produit un
                rapport illisible. Sans rapport exploitable, aucun verdict ne peut nommer le
                test qui a rougi, et un code de sortie n'y suffit pas. **Jamais une exception
                nue** : une mutation au milieu d'un lot abandonnerait les suivantes sur une
                trace au lieu d'un verdict.
        """
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report"
            quoted = "".join(f' "{target}"' for target in self.targets)
            environment = dict(os.environ) | {
                name: value.format(report=report) for name, value in self.reporter.env.items()
            }
            command = self.command + self.reporter.flags.format(report=report) + quoted
            try:
                finished = subprocess.run(
                    command,
                    cwd=self.root,
                    shell=True,
                    capture_output=True,
                    check=False,
                    text=True,
                    errors="replace",
                    env=environment,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired as expired:
                # Une mutation est précisément ce qui fabrique une boucle sans fin : la
                # condition d'arrêt est ce qu'on vient de casser. Sans délai, le harnais se
                # bloque le fichier muté, et un arrêt brutal laisserait le dépôt dans cet état.
                raise Unusable(f"délai de {self.timeout} s dépassé par « {command} »") from expired
            if not report.is_file():
                raise Unusable(
                    f"aucun rapport produit par « {command} » — le libellé doit nommer une ligne "
                    f"qui **invoque le lanceur directement** : les options du rapport sont "
                    f"ajoutées à la commande, et une cible `make` ou `just` les refuse. "
                    f"Fin de sa sortie d'erreur : {tail(finished.stderr)}"
                )
            try:
                return self.reporter.outcomes(report.read_text(encoding="utf-8"))
            # Large à dessein : trois lecteurs, trois familles d'erreur (`ParseError`,
            # `JSONDecodeError`, `KeyError`), et un rapport tronqué par un lanceur tué en produit
            # d'autres. Ce qui compte est qu'aucune ne s'échappe en abandonnant le lot.
            except Exception as unreadable:
                raise Unusable(f"rapport illisible : {unreadable!r}") from unreadable


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


def resolve(expected: Sequence[str], known: Mapping[str, str]) -> list[str]:
    """Résout chaque fragment de `expect` en **un** nom de test de la suite témoin.

    C'est la symétrie de l'unicité exigée de `old` : le motif muté doit désigner un seul
    endroit, le rouge attendu doit désigner un seul test. Sans elle, l'appariement se fait en
    sous-chaîne sur le nom complet, et deux formes banales rendent ROUGE sans que le test visé
    ait rougi — un frère de préfixe (`…_negatif` apparié par `…_negatif_et_double_le_reste`) et
    le nom du module, qui est une partie de chaque clé. C'est le défaut mesuré le 2026-10-04,
    déplacé du code de sortie vers le nom : un nom ambigu ne nomme rien.

    Args:
        expected: les fragments de `expect`, tels que le fichier de mutations les écrit.
        known: les tests de la suite témoin, par nom complet.

    Returns:
        Un nom complet par fragment, dans l'ordre.

    Raises:
        Unusable: un fragment apparie zéro test — faute de frappe, ou identifiant que le
            lanceur échappe (pytest échappe les non-ASCII des cas paramétrés) — ou plusieurs.
    """
    resolved: list[str] = []
    for fragment in expected:
        matches = sorted(name for name in known if fragment in name)
        if len(matches) != 1:
            raise Unusable(
                f"« {fragment} » apparie {len(matches)} tests de la suite témoin, il en faut "
                f"exactement un{' : ' + str(matches[:3]) if matches else ''}"
            )
        resolved.append(matches[0])
    return resolved


def within(root: Path, declared: str) -> Path:
    """Le fichier à muter, à condition qu'il soit **sous** la racine désignée.

    Un `file` absolu, ou qui remonte par `..`, fait muter — et restaurer — hors du worktree
    isolé : dans le clone principal où l'auteur travaille au même moment, voire dans la
    configuration du poste. C'est la rupture d'isolation que la vérification de
    `git rev-parse --show-toplevel` existe pour empêcher, et elle contourne au passage le refus
    de sécurité, qui n'apparie que le chemin déclaré. `Path` ne borne rien : joint à un chemin
    absolu, il le rend tel quel.

    Raises:
        Unusable: le chemin sort de la racine, ou ne désigne aucun fichier.
    """
    base = root.resolve()
    path = (base / declared).resolve()
    if not path.is_relative_to(base):
        raise Unusable(f"« {declared} » sort de la racine {base} — mutation refusée")
    if not path.is_file():
        raise Unusable(f"« {declared} » ne désigne aucun fichier sous {base}")
    return path


def judge(suite: Suite, entry: Mapping[str, Any], witness: Mapping[str, str]) -> Verdict:
    """Joue une mutation et rend son verdict, le fichier restauré octet pour octet.

    Args:
        suite: la suite à relancer sous la mutation.
        entry: l'entrée `{name, file, old, new, expect}` du fichier de mutations.
        witness: les tests de la suite témoin, par nom complet — ce contre quoi `expect` se
            résout, et ce qui rend le verdict opposable à un nom précis.

    Returns:
        `ROUGE` si **tous** les tests résolus depuis `expect` ont rougi, `VERT` si l'un d'eux est
        resté vert — sauté et instable compris, qui ne sont pas des rouges —, `PANNE` si la
        mutation n'a pas pu être jouée.
    """
    name = str(entry.get("name", "?"))
    try:
        refusal = security_refusal(entry)
        if refusal:
            raise Unusable(refusal)
        expected = cast(list[str], entry.get("expect") or [])
        if not expected:
            raise Unusable("aucun rouge attendu nommé dans `expect`")
        aimed = resolve(expected, witness)
        path = within(suite.root, str(entry["file"]))
        original, mutated = mutated_bytes(path, str(entry["old"]), str(entry["new"]))
        try:
            path.write_bytes(mutated)
            outcomes = suite.outcomes()
        finally:
            path.write_bytes(original)
    except Unusable as reason:
        return Verdict("PANNE", name, str(reason))

    red = sorted(test for test, state in outcomes.items() if state == RED)
    survivors = [test for test in aimed if test not in red]
    detail = f"rouges : {red}"
    return Verdict(
        "VERT" if survivors else "ROUGE",
        name,
        f"attendus restés verts : {survivors} ; {detail}" if survivors else detail,
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
    mutations = cast(list[dict[str, Any]], spec.get("mutations") or [])
    names = [str(entry.get("name", "?")) for entry in mutations]
    if not mutations:
        return [Verdict("PANNE", "—", "aucune mutation dans le fichier de mutations")]

    try:
        suite = Suite.from_spec(root, spec)
        witness = suite.outcomes()
        already = sorted(test for test, state in witness.items() if state == RED)
        if already:
            raise Unusable(f"rouges déjà présents avant toute mutation : {already}")
    except (Unusable, LookupError) as reason:
        return [Verdict("PANNE", name, f"témoin : {reason}") for name in names]

    # Le refus de sécurité vit dans `judge`, et là seulement. Un court-circuit ici — « si tout
    # est refusé, ne pas lancer le témoin » — épargnait un lancement, mais les deux gardes se
    # masquaient mutuellement : retirer l'une laissait l'autre rendre le même verdict, donc
    # aucun test ne pouvait épingler ni l'une ni l'autre. Mesuré en relecture : les deux
    # mutations correspondantes rendaient VERT. Une seule garde, éprouvable.
    return [judge(suite, entry, witness) for entry in mutations]


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
