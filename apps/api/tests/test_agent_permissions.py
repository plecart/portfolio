"""Tests des règles de permission de l'agent (`.claude/settings.json`).

La garde native de Claude Code, `Read(.env)`, couvre l'outil Read et les commandes de lecture
qu'elle reconnaît (`cat`, `head`, `tail`, `sed`, `tee`). Mais le hook RTK du poste réécrit ces
commandes avant l'évaluation des permissions — `cat .env` devient `rtk read .env`, `grep X .env`
devient `rtk grep X .env` — et ces formes-là, la garde native ne les reconnaît pas. Des règles
`allow` du même fichier les autorisent en bloc (`Bash(rtk read *)`, `Bash(rtk grep *)`) : sans un
`deny` évalué avant elles, `.env` se lit sans permission. Même logique pour le force-push, que
`.claude/rules/contraintes.md` interdit : seul un `deny` en fait une porte du harnais.

Ce module émule l'appariement des règles Bash — `*` vaut n'importe quel texte, y compris vide
(doc « Configure permissions », § Wildcard patterns) — et épingle le dénombrement : chaque forme
à refuser tombe sur un `deny`, chaque témoin ordinaire n'en touche aucun. Une première version
des règles fermait `rtk read .env` seul ; la relecture de la PR #54 a mesuré trois contournements
(guillemets, glob, `grep`) — d'où la liste.
"""

import json
import re
from pathlib import Path

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

# Des commandes que les `allow` doivent continuer de couvrir sans qu'un `deny` les attrape.
HARMLESS_COMMANDS = [
    "rtk read README.md",
    "rtk grep SECRET_KEY README.md",
    "rtk read infra/compose.dev.yml",
    "git push -u origin feat/x",
    "git push origin main --follow-tags",
]

BASH_RULE = re.compile(r"^Bash\((?P<pattern>.*)\)$")


def bash_deny_patterns() -> list[re.Pattern[str]]:
    """Les règles `deny` Bash du projet, traduites en expressions régulières.

    Returns:
        Une expression par règle `Bash(...)` de `permissions.deny`, où chaque `*` devient `.*`
        et tout le reste est pris au pied de la lettre — l'émulation de l'appariement documenté,
        pas l'appariement lui-même. Elle ne découpe pas les commandes composées (`;`, `&&`, `|`),
        n'applique ni la règle du ` *` final qui accepte aussi la commande nue, ni le retrait des
        enveloppes (`timeout`, `FOO=1`) : les listes de ce module ne contiennent donc que des
        formes simples, sans séparateur.
    """
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    patterns: list[re.Pattern[str]] = []
    for rule in settings["permissions"]["deny"]:
        if match := BASH_RULE.match(rule):
            parts = match.group("pattern").split("*")
            patterns.append(re.compile(".*".join(re.escape(part) for part in parts)))
    return patterns


@pytest.mark.parametrize("command", LEAKING_COMMANDS + ACCEPTED_COLLATERAL + FORCE_PUSHES)
def test_chaque_forme_a_refuser_tombe_sur_un_deny(command: str) -> None:
    """Un `deny` se lit avant tout `allow` : c'est la seule règle qui ferme ces formes."""
    assert any(pattern.fullmatch(command) for pattern in bash_deny_patterns()), (
        f"« {command} » n'est arrêté par aucun `deny` — la garde a rétréci"
    )


@pytest.mark.parametrize("command", HARMLESS_COMMANDS)
def test_une_commande_ordinaire_ne_tombe_sur_aucun_deny(command: str) -> None:
    """Le témoin : une garde qui attrape tout n'attrape rien de particulier."""
    assert not any(pattern.fullmatch(command) for pattern in bash_deny_patterns()), (
        f"« {command} » est arrêté par un `deny` — la garde déborde sur l'ordinaire"
    )
