"""Tests des règles de permission de l'agent (`.claude/settings.json`).

La garde native de Claude Code, `Read(.env)`, couvre l'outil Read et les commandes de lecture
qu'elle reconnaît (`cat`, `head`, `tail`, `sed`, `tee`). Mais le hook RTK du poste réécrit ces
commandes avant l'évaluation des permissions — `cat .env` devient `rtk read .env`, `grep X .env`
devient `rtk grep X .env` — et ces formes-là, la garde native ne les reconnaît pas. Des règles
`allow` du même fichier les autorisent en bloc (`Bash(rtk read *)`, `Bash(rtk grep *)`) : sans un
`deny` évalué avant elles, `.env` se lit sans permission. Même logique pour le force-push, que
`.claude/rules/contraintes.md` interdit : seul un `deny` en fait une porte du harnais. Et pour le
merge d'une PR, que la même règle réserve à un « go » humain : seul un `ask` — évalué avant tout
`allow`, y compris celui que le hook renvoie — en fait une porte, sous chaque outil qui peut le
lancer (`Bash`, où RTK réécrit, et `PowerShell`, qu'il ne touche pas).

Ce module émule l'appariement des règles — `*` vaut n'importe quel texte, y compris vide (doc
« Configure permissions », § Wildcard patterns) — et épingle le dénombrement : chaque forme à
refuser tombe sur un `deny`, chaque merge tombe sur un `ask`, chaque témoin ordinaire ne touche ni
l'un ni l'autre. Une première version des règles fermait `rtk read .env` seul ; la relecture de la
PR #54 a mesuré trois contournements (guillemets, glob, `grep`) — d'où la liste.
"""

import json
import re
from pathlib import Path
from typing import Literal

import pytest

# `test_agent_permissions.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SETTINGS = REPOSITORY_ROOT / ".claude" / "settings.json"

# Les formes que RTK produit pour `cat`, `head -N`, `tail -N` et `grep` sur `.env`, mesurées le
# 2026-09-29 avec `rtk hook claude`, plus les variantes de citation et de glob qui ont contourné
# la première version des règles.
LEAKING_COMMANDS = [
    "rtk read .env",
    "rtk read ./.env",
    "rtk read '.env'",
    'rtk read ".env"',
    "rtk read .env*",
    "rtk read .env --max-lines 5",
    "rtk read .env --tail-lines 5",
    "rtk grep SECRET_KEY .env",
    "rtk grep -n SECRET .env",
]

# Le collatéral **accepté** de `rtk read *.env*` et `rtk grep *.env*` : des lectures légitimes
# que le motif attrape aussi, parce qu'aucune forme plus étroite ne ferme à la fois les
# guillemets, les globs et les chemins absolus. L'outil Grep et `git grep` (non réécrit par RTK)
# restent libres pour ces cas — `.claude/pipeline.config.md`, paragraphe RTK. Une entrée qui
# cesserait d'être refusée signalerait un motif rétréci en silence.
ACCEPTED_COLLATERAL = [
    "rtk read .env.example",
    "rtk read infra/dev.env",
    'rtk grep -rn "os.environ" apps/api',
]

# Le force-push sous toutes les positions du drapeau que `git` accepte, drapeaux groupés compris.
FORCE_PUSHES = [
    "git push --force",
    "git push -f",
    "git push origin main --force",
    "git push origin main -f",
    "git push origin +main",
    "git push -uf origin main",
    "git push origin main -uf",
    "git push --force-with-lease origin main",
]

# Le merge d'une PR, par chaque outil et sous chaque forme qui peut le lancer : celle que Claude
# écrit, celle que RTK lui substitue, le passage brut par `rtk proxy`, et l'outil PowerShell que le
# hook RTK ne voit pas (son matcher ne vise que `Bash`). Et `update-branch --rebase`, qui réécrit la
# branche d'une PR ouverte — le « rebase explicitement demandé » de `contraintes.md`.
GATED_CALLS = [
    ("Bash", "gh pr merge 54 --rebase --delete-branch"),
    ("Bash", "rtk gh pr merge 54 --rebase --delete-branch"),
    ("Bash", "rtk proxy gh pr merge 54 --rebase"),
    ("PowerShell", "gh pr merge 54 --rebase --delete-branch"),
    ("Bash", "gh pr update-branch 56 --rebase"),
    ("Bash", "rtk gh pr update-branch 56 --rebase"),
    ("Bash", "rtk proxy gh pr update-branch 56 --rebase"),
    ("PowerShell", "gh pr update-branch 56 --rebase"),
]

# La seule voie de merge sans invite : le script de merge d'un lot dans sa branche d'intégration,
# qui refuse lui-même le trunk (`.claude/skills/cycle-pr/scripts/merge-lot.py`, #107 lot 2a). Une
# règle `Bash(cmd *)` n'approuve pas `cmd && autre` : Claude Code apparie chaque sous-commande
# séparément (doc « Configure permissions », § Compound commands, lue le 2026-10-17) — d'où une
# seule forme simple ici, comme dans tout ce module. Une redirection (`… > fichier`) n'est pas
# couverte par la règle non plus : sa cible se contrôle contre les règles `Edit`, « A rule such as
# `Bash(git commit *)` allows the command, not the target » (même doc, § Redirections, même date).
MERGE_LOT = "python .claude/skills/cycle-pr/scripts/merge-lot.py"
ALLOWED_MERGE = ("Bash", f"{MERGE_LOT} 118 {'a' * 40} feat/sessions-liees")

# Ce que l'entrée du script ne doit pas autoriser en passant : un autre script du même dossier,
# Python en général, et le script appelé par un autre chemin, que la règle n'apparie pas — il
# retombe alors sur l'invite ordinaire, jamais sur une autorisation.
NOT_ALLOWED_BY_THE_MERGE_RULE = [
    ("Bash", "python .claude/skills/cycle-pr/scripts/mutation.py . m.json"),
    ("Bash", "python -c print(1)"),
    ("Bash", f"python ./.claude/skills/cycle-pr/scripts/merge-lot.py 118 {'a' * 40} main"),
]

# Des commandes ordinaires, par outil, qu'aucun `deny` ni `ask` ne doit attraper.
HARMLESS_CALLS = [
    ("Bash", "rtk read README.md"),
    ("Bash", "rtk grep SECRET_KEY README.md"),
    ("Bash", "rtk read infra/compose.dev.yml"),
    ("Bash", "git push -u origin feat/x"),
    ("Bash", "git push origin main --follow-tags"),
    ("Bash", "rtk gh pr view 54"),
    ("Bash", "gh pr ready 54"),
    ("Bash", "gh pr update-branch 56"),
    ("PowerShell", "gh pr view 54"),
]

Section = Literal["allow", "ask", "deny"]
RULE = re.compile(r"^(?P<tool>[A-Za-z]+)\((?P<pattern>.*)\)$")


def rule_patterns(section: Section, tool: str) -> list[re.Pattern[str]]:
    """Les règles d'un outil dans une section de `permissions`, traduites en expressions régulières.

    Args:
        section: `allow`, `ask` ou `deny` — absente du fichier, elle vaut la liste vide.
        tool: le nom d'outil qui préfixe la règle (`Bash`, `PowerShell`…).

    Returns:
        Une expression par règle `<tool>(...)` de la section, où chaque `*` devient `.*` et tout
        le reste est pris au pied de la lettre — l'émulation de l'appariement documenté, pas
        l'appariement lui-même. Elle ne découpe pas les commandes composées (`;`, `&&`, `|`),
        n'applique ni la règle du ` *` final qui accepte aussi la commande nue, ni le retrait des
        enveloppes (`timeout`, `FOO=1`) : les listes de ce module ne contiennent donc que des
        formes simples, sans séparateur.
    """
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    patterns: list[re.Pattern[str]] = []
    for rule in settings["permissions"].get(section, []):
        if (match := RULE.match(rule)) and match.group("tool") == tool:
            parts = match.group("pattern").split("*")
            patterns.append(re.compile(".*".join(re.escape(part) for part in parts)))
    return patterns


def matches_a_rule(command: str, section: Section, tool: str = "Bash") -> bool:
    """Vrai si une règle de la section, pour cet outil, apparie la commande entière."""
    return any(pattern.fullmatch(command) for pattern in rule_patterns(section, tool))


@pytest.mark.parametrize("command", LEAKING_COMMANDS + ACCEPTED_COLLATERAL + FORCE_PUSHES)
def test_chaque_forme_a_refuser_tombe_sur_un_deny(command: str) -> None:
    """Un `deny` se lit avant tout `allow` : c'est la seule règle qui ferme ces formes."""
    assert matches_a_rule(command, "deny"), (
        f"« {command} » n'est arrêté par aucun `deny` — la garde a rétréci"
    )


@pytest.mark.parametrize(
    ("tool", "command"), GATED_CALLS, ids=[f"{t}: {c}" for t, c in GATED_CALLS]
)
def test_le_merge_ou_le_rebase_d_une_pr_demande_une_permission(tool: str, command: str) -> None:
    """« Jamais d'auto-merge », « jamais de force-push sur une PR ouverte sauf rebase demandé » :
    le go humain est une invite du harnais, pas une consigne."""
    assert matches_a_rule(command, "ask", tool), (
        f"{tool} « {command} » ne tombe sur aucun `ask` — l'appel passerait sans go humain"
    )


@pytest.mark.parametrize(
    ("tool", "command"), HARMLESS_CALLS, ids=[f"{t}: {c}" for t, c in HARMLESS_CALLS]
)
def test_une_commande_ordinaire_ne_tombe_ni_sur_un_deny_ni_sur_un_ask(
    tool: str, command: str
) -> None:
    """Le témoin : une garde qui attrape tout n'attrape rien de particulier."""
    assert not matches_a_rule(command, "deny", tool), f"« {command} » est arrêté par un `deny`"
    assert not matches_a_rule(command, "ask", tool), f"« {command} » déclenche un `ask`"


def test_le_script_de_merge_d_un_lot_est_autorise_sans_invite() -> None:
    """« Jamais d'auto-merge dans le trunk » : le merge d'un lot dans sa branche d'intégration
    part sans go humain, par ce script seul — les formes de `GATED_CALLS` restent en `ask`."""
    tool, command = ALLOWED_MERGE

    assert matches_a_rule(command, "allow", tool), f"« {command} » n'est autorisé par aucun `allow`"
    assert not matches_a_rule(command, "ask", tool), f"« {command} » déclenche un `ask`"
    assert not matches_a_rule(command, "deny", tool), f"« {command} » est arrêté par un `deny`"


def test_le_script_de_merge_d_un_lot_ne_s_edite_pas_sans_le_mainteneur() -> None:
    """L'`allow` fait confiance au **contenu** du script : une session qui en retirerait le refus du
    trunk, puis le lancerait, mergerait vers `main` sans invite (`/code-review` de la PR #117).
    Un `deny` `Edit` ferme les outils d'édition, `sed` et les redirections en Bash (doc « Configure
    permissions », lue le 2026-10-17) ; `/` ancre le chemin au dossier de travail principal. Il ne
    ferme pas un sous-processus qui écrirait le fichier lui-même — même doc. Le témoin : un fichier
    voisin du même dossier reste éditable."""
    assert matches_a_rule(f"/{MERGE_LOT.removeprefix('python ')}", "deny", "Edit")
    assert not matches_a_rule("/.claude/skills/cycle-pr/scripts/mutation.py", "deny", "Edit")


@pytest.mark.parametrize(
    ("tool", "command"),
    NOT_ALLOWED_BY_THE_MERGE_RULE,
    ids=[f"{t}: {c}" for t, c in NOT_ALLOWED_BY_THE_MERGE_RULE],
)
def test_l_autorisation_du_script_de_merge_ne_couvre_que_lui(tool: str, command: str) -> None:
    """Une règle élargie à `python *` ou au dossier entier autoriserait sans invite tout ce que
    Python peut lancer, `gh pr merge` compris."""
    assert not matches_a_rule(command, "allow", tool), f"« {command} » est autorisé sans invite"
