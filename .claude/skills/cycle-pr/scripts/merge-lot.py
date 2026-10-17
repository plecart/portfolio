"""Merge une PR de lot dans sa branche d'intégration, sans « go » humain — jamais dans le trunk.

Usage : python merge-lot.py <PR> <SHA de tête vérifié> <base attendue>

C'est la seule voie de merge que `.claude/settings.json` autorise sans invite : `gh pr merge`
reste en `ask`, et ce script le lance lui-même, une fois chaque condition tenue (#107, décision 13
du brief ; `cycle-pr` Étape 7, « Le go, puis le merge »). Il refuse, dans cet ordre :

1. une base attendue égale au trunk — le merge dans le trunk attend toujours un go humain — ou
   qui n'est la tête d'aucune PR d'intégration ouverte vers le trunk, au corps ouvert par « En vol
   pour #N (intégration, n lots) » : une autre branche n'est pas une branche d'intégration ;
2. une PR dont la base n'est pas la base attendue, qui n'est plus ouverte, ou encore en draft — le
   passage en ready suit la fermeture de la boucle du relecteur (`cycle-pr` Étapes 4 et 5) ;
3. une tête autre que le SHA vérifié ;
4. une CI qui n'est pas entièrement verte sur cette tête ;
5. un body sans la ligne « Verdict d'avant-go (<SHA de tête>) : rien à corriger » ;
6. une référence de fusion qui ne combine pas cette tête, ou dont le premier parent — la base
   éprouvée par la CI — n'est plus la tête de la base : la base a avancé depuis le dernier run.

Puis `gh pr merge <PR> --rebase --match-head-commit <SHA>`, que la forge refuse si la tête a bougé
entre-temps.

**Ce qu'il ne prouve pas.** La ligne de verdict est écrite par la session qui l'appelle : le script
exige qu'elle soit inscrite, pour ce SHA, là où `cycle-pr` Étape 7 la fait écrire ; il ne prouve pas
que le vérificateur a tourné. Et le draft levé atteste l'ordre des étapes, pas le contenu de la
relecture.

Sortie : 0 mergé ; 1 refusé, motif en une ligne sur la sortie standard ; 2 appel mal formé.
Python 3.11 ou plus, bibliothèque standard seule ; `gh` authentifié et `git`, lancé depuis le
dépôt.
"""

import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Any

Run = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

FULL_SHA = re.compile(r"[0-9a-f]{40}")
# `str.isdigit` accepte « ² » : le numéro se lit en chiffres ASCII seulement.
PR_NUMBER = re.compile(r"[0-9]+")
# La première ligne du corps d'une PR d'intégration (#107, brief, « Corps de PR »).
INTEGRATION_MARK = re.compile(r"En vol pour #\d+ \(intégration, \d+ lots\)")
# Une ligne de `statusCheckRollup` est verte sur l'une de ces conclusions. `SKIPPED` : les jobs de
# publication et de déploiement, gardés par `if:`, le rendent sur chaque PR (relevé sur la PR #109).
GREEN_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}


class Refusal(Exception):
    """Une condition du merge n'est pas tenue ; le message est le motif, en une ligne."""


def default_run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Lance une commande en capturant ses sorties, décodées en UTF-8 — jamais l'encodage de la
    console, qui lit un body accentué de travers sous Windows (obs 108)."""
    return subprocess.run(list(cmd), capture_output=True, text=True, encoding="utf-8", check=False)


def output(run: Run, *cmd: str) -> str:
    """La sortie standard de la commande, ou un refus si elle échoue : une sortie vide d'une
    commande en échec ne se lit jamais comme une réponse."""
    done = run(cmd)
    if done.returncode != 0:
        raise Refusal(f"`{' '.join(cmd[:3])}` a échoué ({done.returncode}) : {done.stderr.strip()}")
    return done.stdout.strip()


def is_green(check: dict[str, Any]) -> bool:
    """Une ligne de `statusCheckRollup` verte : un `CheckRun` porte sa `conclusion`, vide tant
    qu'il tourne. Un `StatusContext` n'en a pas, donc ne passe jamais — refus du côté sûr ; ce dépôt
    n'en émet aucun (relevé sur la PR #109)."""
    return check.get("conclusion") in GREEN_CONCLUSIONS


def pr_refusal(pr: dict[str, Any], sha: str, base: str) -> str | None:
    """Le motif qui interdit de merger cette PR, ou `None` — conditions 2 à 5 du module.

    Args:
        pr: la PR telle que `gh pr view --json` la rend (`baseRefName`, `headRefOid`, `isDraft`,
            `state`, `body`, `statusCheckRollup`).
        sha: le SHA complet de tête que la vérification d'avant-go a vu.
        base: la branche d'intégration attendue.
    """
    if pr["baseRefName"] != base:
        return f"la base de la PR est `{pr['baseRefName']}`, pas `{base}`"
    if pr["state"] != "OPEN":
        return f"la PR n'est pas ouverte ({pr['state']})"
    if pr["isDraft"]:
        return "la PR est encore en draft : la boucle du relecteur n'est pas fermée"
    if pr["headRefOid"] != sha:
        return f"la tête de la PR est {pr['headRefOid']}, pas le SHA vérifié {sha}"
    # ponytail: toutes les lignes du rollup, runs anciens compris — un rouge déjà rejoué par un
    # autre événement refuse encore ; ne garder que la dernière par nom si ce cas se présente.
    checks = pr["statusCheckRollup"]
    if not checks or not all(is_green(check) for check in checks):
        return "la CI n'est pas entièrement verte sur cette tête"
    if f"Verdict d'avant-go ({sha}) : rien à corriger" not in pr["body"]:
        return f"le body ne porte pas le verdict d'avant-go « rien à corriger » pour {sha}"
    return None


def merge(number: str, sha: str, base: str, run: Run) -> None:
    """Vérifie chaque condition du module, dans l'ordre, puis merge.

    Raises:
        Refusal: la première condition non tenue, ou une commande `gh` / `git` en échec.
    """
    trunk = output(
        run, "gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"
    )
    if base == trunk:
        raise Refusal(
            f"`{base}` est le trunk : son merge attend le go humain de `cycle-pr` Étape 7"
        )
    listed = output(
        run,
        "gh",
        "pr",
        "list",
        "--base",
        trunk,
        "--head",
        base,
        "--state",
        "open",
        "--json",
        "body",
    )
    first_lines = [(pr["body"].splitlines() or [""])[0].strip() for pr in json.loads(listed)]
    if not any(INTEGRATION_MARK.fullmatch(line) for line in first_lines):
        raise Refusal(f"`{base}` n'est la tête d'aucune PR d'intégration ouverte vers `{trunk}`")
    fields = "baseRefName,headRefOid,isDraft,state,body,statusCheckRollup"
    pr = json.loads(output(run, "gh", "pr", "view", number, "--json", fields))
    if motif := pr_refusal(pr, sha, base):
        raise Refusal(motif)

    output(run, "git", "fetch", "origin", base)
    reference = output(
        run,
        "gh",
        "api",
        f"repos/{{owner}}/{{repo}}/git/ref/pull/{number}/merge",
        "--jq",
        ".object.sha",
    )
    parents = output(
        run, "gh", "api", f"repos/{{owner}}/{{repo}}/commits/{reference}", "--jq", ".parents[].sha"
    ).split()
    if len(parents) != 2 or parents[1] != sha:
        raise Refusal(
            f"la référence de fusion {reference} ne combine pas la tête {sha} : relancer la CI"
        )
    # `--is-ancestor` sort en 1 pour « non », et au-delà (128) quand il ne peut pas répondre.
    gate = run(["git", "merge-base", "--is-ancestor", f"origin/{base}", parents[0]])
    if gate.returncode == 1:
        raise Refusal(f"`{base}` a avancé depuis la base éprouvée {parents[0]} : relancer la CI")
    if gate.returncode != 0:
        raise Refusal(
            f"porte de fraîcheur sans réponse ({gate.returncode}) : {gate.stderr.strip()}"
        )

    output(run, "gh", "pr", "merge", number, "--rebase", "--match-head-commit", sha)


def main(argv: Sequence[str], run: Run = default_run) -> int:
    """Point d'entrée : `<PR> <SHA de tête vérifié> <base attendue>` ; voir le module."""
    if len(argv) != 3 or not PR_NUMBER.fullmatch(argv[0]) or not FULL_SHA.fullmatch(argv[1]):
        print(__doc__.split("\n\n")[1])
        return 2
    number, sha, base = argv
    try:
        merge(number, sha, base, run)
    except Refusal as refusal:
        print(f"refus — {refusal}")
        return 1
    print(f"mergé — PR #{number} dans `{base}`, tête {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
