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

Ce module émule l'appariement des règles — `*` vaut n'importe quel texte, y compris vide, et un
` *` final, seule étoile du motif, accepte aussi la commande nue (doc « Configure permissions »,
§ Wildcard patterns) — et épingle le dénombrement : chaque forme à refuser tombe sur un `deny`,
chaque merge ou `update-branch` sur un `ask`, chaque script autorisé sur un `allow` qui ne couvre
que lui, chaque témoin ordinaire ni sur l'un ni sur l'autre. Le harnais de mutation refuse de muter
un réglage de sécurité (obs 53) : l'affaiblissement de ce que #198 ajoute se voit sur un recueil de
formes fautives construites en mémoire (`FAULTY_SETTINGS`). Une première version des règles fermait
`rtk read .env` seul ; la relecture de la PR #54 a mesuré trois contournements (guillemets, glob,
`grep`) — d'où la liste.
"""

import json
import re
from pathlib import Path
from typing import Any, Literal

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

# Chaque outil et chaque forme qui peuvent lancer une commande : celle que Claude écrit, celle que
# RTK lui substitue, le passage brut par `rtk proxy`, et l'outil PowerShell que le hook RTK ne voit
# pas (son matcher ne vise que `Bash`).
CALL_FORMS = [("Bash", ""), ("Bash", "rtk "), ("Bash", "rtk proxy "), ("PowerShell", "")]

# Le merge d'une PR, et `update-branch`, qui réécrit la branche d'une PR ouverte : avec `--rebase`,
# le « rebase explicitement demandé » de `contraintes.md` ; sans, un commit de fusion de la base
# (`gh pr update-branch --help`, gh 2.94.0), que `cycle-pr` Étape 6 interdit (#198, D-2). Chaque
# forme d'`update-branch` avec et sans argument, avec et sans `--rebase` : la règle ` *` qui a
# remplacé `*--rebase*` se prouve sur chacune des quatre entrées qu'elle remplace.
GATED_COMMANDS = [
    "gh pr merge 54 --rebase --delete-branch",
    "gh pr update-branch",
    "gh pr update-branch --rebase",
    "gh pr update-branch 56",
    "gh pr update-branch 56 --rebase",
]
GATED_CALLS = [
    (tool, prefix + command) for command in GATED_COMMANDS for tool, prefix in CALL_FORMS
]

# Les scripts autorisés sans invite, chacun sous une forme unique : RTK ne réécrit pas `python …`
# (`rtk rewrite` sort en 1 sans rien rendre, mesuré le 2026-11-03). `merge-lot.py` est la seule voie
# de merge sans invite — un lot dans sa branche d'intégration, le trunk refusé par le script lui-même
# (#107 lot 2a) ; `porte-merge.py` ne fait que lire `gh` et `git` (#198, D-3). Une règle
# `Bash(cmd *)` n'approuve pas `cmd && autre` : Claude Code apparie chaque sous-commande séparément
# (doc « Configure permissions », § Compound commands, lue le 2026-10-17) — d'où une seule forme
# simple ici, comme dans tout ce module. Une redirection (`… > fichier`) n'est pas couverte par la
# règle non plus : sa cible se contrôle contre les règles `Edit`, « A rule such as
# `Bash(git commit *)` allows the command, not the target » (même doc, § Redirections, même date).
MERGE_LOT = "python .claude/skills/cycle-pr/scripts/merge-lot.py"
PORTE_MERGE = "python .claude/skills/cycle-pr/scripts/porte-merge.py"
ALLOWED_SCRIPT_CALLS = {
    "merge-lot": ("Bash", f"{MERGE_LOT} 118 {'a' * 40} feat/sessions-liees"),
    "porte-merge-trunk": ("Bash", f"{PORTE_MERGE} trunk 40963627023 main {'a' * 40}"),
    "porte-merge-conversation": ("Bash", f"{PORTE_MERGE} conversation 200 --releve"),
}

# Ce que les entrées des scripts ne doivent pas autoriser en passant : un autre script du même
# dossier, Python en général, et un script appelé par un autre chemin, que la règle n'apparie pas —
# il retombe alors sur le régime ordinaire (invite, ou classifieur en mode auto), jamais sur cette
# autorisation.
SIBLING_SCRIPT = ("Bash", "python .claude/skills/cycle-pr/scripts/mutation.py . m.json")
NOT_ALLOWED_BY_THE_SCRIPT_RULES = [
    SIBLING_SCRIPT,
    ("Bash", "python -c print(1)"),
    ("Bash", f"python ./.claude/skills/cycle-pr/scripts/merge-lot.py 118 {'a' * 40} main"),
    ("Bash", "python ./.claude/skills/cycle-pr/scripts/porte-merge.py conversation 200"),
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
    ("PowerShell", "gh pr view 54"),
]

Section = Literal["allow", "ask", "deny"]
RULE = re.compile(r"^(?P<tool>[A-Za-z]+)\((?P<pattern>.*)\)$")


def rule_patterns(
    section: Section, tool: str, settings: dict[str, Any] | None = None
) -> list[re.Pattern[str]]:
    """Les règles d'un outil dans une section de `permissions`, traduites en expressions régulières.

    Args:
        section: `allow`, `ask` ou `deny` — absente du fichier, elle vaut la liste vide.
        tool: le nom d'outil qui préfixe la règle (`Bash`, `PowerShell`…).
        settings: des réglages construits en mémoire ; à défaut, ceux du dépôt.

    Returns:
        Une expression par règle `<tool>(...)` de la section (`rule_regex`) — l'émulation de
        l'appariement documenté, pas l'appariement lui-même. Elle ne découpe pas les commandes
        composées (`;`, `&&`, `|`) et n'applique pas le retrait des enveloppes (`timeout`,
        `FOO=1`) : les listes de ce module ne contiennent donc que des formes simples, sans
        séparateur.
    """
    loaded: dict[str, Any] = (
        json.loads(SETTINGS.read_text(encoding="utf-8")) if settings is None else settings
    )
    rules: list[str] = loaded["permissions"].get(section, [])
    return [
        rule_regex(match.group("pattern"))
        for rule in rules
        if (match := RULE.match(rule)) and match.group("tool") == tool
    ]


def rule_regex(pattern: str) -> re.Pattern[str]:
    """Le motif d'une règle en expression régulière : chaque `*` vaut n'importe quel texte, le
    reste se prend au pied de la lettre, et un ` *` final qui est la seule étoile du motif accepte
    aussi la commande nue — « A `*` at the end, with a space before it, also matches the bare
    command. […] That holds only when the trailing `*` is the rule's only wildcard » (doc
    « Configure permissions », § Wildcard patterns, lue le 2026-11-03)."""
    parts = pattern.split("*")
    if len(parts) == 2 and parts[0].endswith(" ") and not parts[1]:
        return re.compile(f"{re.escape(parts[0][:-1])}(?: .*)?")
    return re.compile(".*".join(re.escape(part) for part in parts))


def matches_a_rule(
    command: str, section: Section, tool: str = "Bash", settings: dict[str, Any] | None = None
) -> bool:
    """Vrai si une règle de la section, pour cet outil, apparie la commande entière."""
    return any(pattern.fullmatch(command) for pattern in rule_patterns(section, tool, settings))


def settings_with(old: str, new: str) -> dict[str, Any]:
    """Les réglages du dépôt, une règle remplacée en mémoire : le fichier n'est jamais affaibli."""
    text = SETTINGS.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"« {old} » n'apparaît pas une seule fois dans les réglages"
    return json.loads(text.replace(old, new))


def update_branch_rule(tool: str, prefix: str) -> str:
    """L'entrée `ask` d'`update-branch` sous une forme d'appel (`CALL_FORMS`)."""
    return f'"{tool}({prefix}gh pr update-branch *)"'


# Le recueil des formes fautives de ce que #198 ajoute (D-2, D-3) : le harnais de mutation refuse de
# muter un réglage de sécurité (obs 53), chaque affaiblissement se construit donc en mémoire depuis
# les réglages du dépôt — la règle remplacée, sa remplaçante, puis la section, l'outil et l'appel dont
# le verdict change, et ce verdict fautif. `update-branch` ramené à `*--rebase*` laisse passer l'appel
# sans `--rebase`, retiré il laisse passer `--rebase` : chacune des quatre entrées ` *` couvre ce que
# couvrait celle qu'elle remplace, et le reste.
FAULTY_SETTINGS: dict[str, tuple[str, str, Section, str, str, bool]] = {
    **{
        f"{tool}: {prefix}update-branch ramené à --rebase": (
            update_branch_rule(tool, prefix),
            update_branch_rule(tool, prefix).replace(" *)", " *--rebase*)"),
            "ask",
            tool,
            f"{prefix}gh pr update-branch 56",
            False,
        )
        for tool, prefix in CALL_FORMS
    },
    **{
        f"{tool}: {prefix}update-branch retiré": (
            update_branch_rule(tool, prefix),
            '"Bash(retiré)"',
            "ask",
            tool,
            f"{prefix}gh pr update-branch 56 --rebase",
            False,
        )
        for tool, prefix in CALL_FORMS
    },
    "porte-merge hors allow": (
        f'"Bash({PORTE_MERGE} *)"',
        '"Bash(retiré)"',
        "allow",
        "Bash",
        ALLOWED_SCRIPT_CALLS["porte-merge-trunk"][1],
        False,
    ),
    "porte-merge élargi au dossier": (
        "scripts/porte-merge.py *)",
        "scripts/*)",
        "allow",
        "Bash",
        SIBLING_SCRIPT[1],
        True,
    ),
    "merge hors ask": (
        '"Bash(gh pr merge *)"',
        '"Bash(retiré)"',
        "ask",
        "Bash",
        "gh pr merge 200",
        False,
    ),
}


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
    """« Jamais d'auto-merge », « jamais de force-push sur une PR ouverte sauf rebase demandé »,
    « ni commit de fusion » (`cycle-pr` Étape 6) : le go humain est une invite du harnais, pas une
    consigne."""
    assert matches_a_rule(command, "ask", tool), (
        f"{tool} « {command} » ne tombe sur aucun `ask` — l'appel passerait sans go humain"
    )


# Les règles d'appariement de la doc (§ Wildcard patterns), sur ses exemples — plus `ls **`, deux
# étoiles dont la seconde finale, que sa règle de la seule étoile refuse à la commande nue (passe 1
# de relecture de la PR #220) : le motif, la commande, et si la règle l'apparie.
WILDCARD_FORMS = {
    "etoile-finale-et-arguments": ("git log *", "git log --oneline", True),
    "etoile-finale-et-commande-nue": ("ls *", "ls", True),
    "espace-avant-l-etoile-finale": ("ls *", "lsof", False),
    "etoile-finale-sans-espace": ("ls*", "lsof", True),
    "deux-etoiles-sans-commande-nue": ("* --help *", "npm --help", False),
    "deux-etoiles-et-argument": ("* --help *", "npm --help x", True),
    "deux-etoiles-consecutives": ("ls **", "ls", False),
}


@pytest.mark.parametrize(
    ("pattern", "command", "matched"), WILDCARD_FORMS.values(), ids=WILDCARD_FORMS.keys()
)
def test_l_emulation_suit_les_regles_d_appariement_documentees(
    pattern: str, command: str, matched: bool
) -> None:
    """Le témoin de l'émulation, des deux côtés : la commande nue n'est acceptée que par un ` *`
    final seule étoile du motif."""
    assert bool(rule_regex(pattern).fullmatch(command)) is matched


@pytest.mark.parametrize(
    ("tool", "command"), HARMLESS_CALLS, ids=[f"{t}: {c}" for t, c in HARMLESS_CALLS]
)
def test_une_commande_ordinaire_ne_tombe_ni_sur_un_deny_ni_sur_un_ask(
    tool: str, command: str
) -> None:
    """Le témoin : une garde qui attrape tout n'attrape rien de particulier."""
    assert not matches_a_rule(command, "deny", tool), f"« {command} » est arrêté par un `deny`"
    assert not matches_a_rule(command, "ask", tool), f"« {command} » déclenche un `ask`"


@pytest.mark.parametrize(
    ("tool", "command"), ALLOWED_SCRIPT_CALLS.values(), ids=ALLOWED_SCRIPT_CALLS.keys()
)
def test_chaque_script_autorise_part_sans_invite(tool: str, command: str) -> None:
    """« Jamais d'auto-merge dans le trunk » : le merge d'un lot dans sa branche d'intégration
    part sans go humain, par `merge-lot.py` seul, et `porte-merge.py`, qui lit, ne demande rien —
    les formes de `GATED_CALLS` restent en `ask`."""
    assert matches_a_rule(command, "allow", tool), f"« {command} » n'est autorisé par aucun `allow`"
    assert not matches_a_rule(command, "ask", tool), f"« {command} » déclenche un `ask`"
    assert not matches_a_rule(command, "deny", tool), f"« {command} » est arrêté par un `deny`"


SKILL_DIRECTORY = ("<répertoire de ce skill>", ".claude/skills/cycle-pr")
# Les portes de merge que la prose fait taper, `porte-merge.py` chaîné à `gh … merge` : `cycle-pr`
# Étape 7 (« Le go, puis le merge ») et l'étape 6 de `triage/hors-scope.md`, relevées le 2026-11-03
# par `git grep -n "porte-merge.py conversation <[a-zA-Z]*> &&" -- .claude CLAUDE.md CONTRIBUTING.md
# .github` : 2 sites, un par fichier.
PORTES_DE_MERGE = {
    "cycle-pr-etape-7": ".claude/skills/cycle-pr/SKILL.md",
    "hors-scope-etape-6": ".claude/skills/triage/hors-scope.md",
}
PORTE_DE_MERGE = re.compile(r"python \S*porte-merge\.py conversation <n> && gh [^`\n]*")


@pytest.mark.parametrize("fichier", PORTES_DE_MERGE.values(), ids=PORTES_DE_MERGE.keys())
def test_la_porte_de_merge_garde_l_invite_de_gh_pr_merge(fichier: str) -> None:
    """La porte telle que la prose la fait taper, `<répertoire de ce skill>` lu depuis la racine :
    l'`allow` de `porte-merge.py` n'y approuve pas le merge chaîné, qui reste en `ask` — « Deny and
    ask rules apply when any subcommand matches them » (doc « Configure permissions », § Compound
    commands, lue le 2026-11-03). L'émulation ne découpant pas, le test découpe la porte sur `&&`."""
    texte = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8").replace(*SKILL_DIRECTORY)
    portes = PORTE_DE_MERGE.findall(texte)

    assert len(portes) == 1, f"`{fichier}` porte {len(portes)} portes de merge : {portes}"
    script, merge = portes[0].split(" && ")
    assert matches_a_rule(script, "allow"), f"« {script} » n'est autorisé par aucun `allow`"
    assert matches_a_rule(merge, "ask"), f"« {merge} » ne tombe sur aucun `ask`"


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
    NOT_ALLOWED_BY_THE_SCRIPT_RULES,
    ids=[f"{t}: {c}" for t, c in NOT_ALLOWED_BY_THE_SCRIPT_RULES],
)
def test_l_autorisation_des_scripts_ne_couvre_qu_eux(tool: str, command: str) -> None:
    """Une règle élargie à `python *` ou au dossier entier autoriserait sans invite tout ce que
    Python peut lancer, `gh pr merge` compris."""
    assert not matches_a_rule(command, "allow", tool), f"« {command} » est autorisé sans invite"


@pytest.mark.parametrize(
    ("old", "new", "section", "tool", "command", "faulty"),
    FAULTY_SETTINGS.values(),
    ids=FAULTY_SETTINGS.keys(),
)
def test_chaque_forme_fautive_des_reglages_change_le_verdict_de_sa_garde(
    old: str, new: str, section: Section, tool: str, command: str, faulty: bool
) -> None:
    """Le rouge des gardes ci-dessus, vu en mémoire : sous la forme fautive, l'appel change de
    verdict ; sous les réglages du dépôt, le témoin, il garde le bon."""
    assert matches_a_rule(command, section, tool, settings_with(old, new)) is faulty
    assert matches_a_rule(command, section, tool) is not faulty
