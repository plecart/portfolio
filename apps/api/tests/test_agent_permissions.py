"""Tests des règles de permission de l'agent (`.claude/settings.json`).

La garde native de Claude Code, `Read(.env)`, couvre l'outil Read et les commandes de lecture
qu'elle reconnaît (`cat`, `head`, `tail`, `sed`, `tee`). Mais le hook RTK du poste réécrit ces
commandes avant l'évaluation des permissions — `cat .env` devient `rtk read .env`, `grep X .env`
devient `rtk grep X .env` — et ces formes-là, la garde native ne les reconnaît pas. Des règles
`allow` du même fichier les autorisent en bloc (`Bash(rtk read *)`, `Bash(rtk grep *)`) : sans un
`deny` évalué avant elles, `.env` se lit sans permission.

Ce module émule l'appariement des règles Bash — `*` vaut n'importe quel texte, y compris vide
(doc « Configure permissions », § Wildcard patterns) — et épingle le dénombrement : chaque forme
réécrite qui affiche le contenu de `.env` tombe sur un `deny`, et une lecture ordinaire n'en
touche aucun. Une première version des règles fermait `rtk read .env` seul ; la relecture de la
PR #54 a mesuré trois contournements (guillemets, glob, `grep`) — d'où la liste.
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

# Des lectures que les `allow` doivent continuer de couvrir sans qu'un `deny` les attrape.
HARMLESS_COMMANDS = [
    "rtk read README.md",
    "rtk grep SECRET_KEY README.md",
    "rtk read infra/compose.dev.yml",
]

BASH_RULE = re.compile(r"^Bash\((?P<pattern>.*)\)$")


def bash_deny_patterns() -> list[re.Pattern[str]]:
    """Les règles `deny` Bash du projet, traduites en expressions régulières.

    Returns:
        Une expression par règle `Bash(...)` de `permissions.deny`, où chaque `*` devient `.*`
        et tout le reste est pris au pied de la lettre — l'émulation de l'appariement documenté,
        pas l'appariement lui-même : elle ignore la frontière de mot que Claude Code applique
        après un espace, ce qui ne change rien aux formes testées ici.
    """
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    patterns: list[re.Pattern[str]] = []
    for rule in settings["permissions"]["deny"]:
        if match := BASH_RULE.match(rule):
            parts = match.group("pattern").split("*")
            patterns.append(re.compile(".*".join(re.escape(part) for part in parts)))
    return patterns


@pytest.mark.parametrize("command", LEAKING_COMMANDS)
def test_chaque_lecture_reecrite_de_env_tombe_sur_un_deny(command: str) -> None:
    """Un `deny` se lit avant tout `allow` : c'est la seule règle qui ferme ces formes."""
    assert any(pattern.fullmatch(command) for pattern in bash_deny_patterns()), (
        f"« {command} » n'est arrêté par aucun `deny` — `.env` se lirait sans permission"
    )


@pytest.mark.parametrize("command", HARMLESS_COMMANDS)
def test_une_lecture_ordinaire_ne_tombe_sur_aucun_deny(command: str) -> None:
    """Le témoin : une garde qui attrape tout n'attrape rien de particulier."""
    assert not any(pattern.fullmatch(command) for pattern in bash_deny_patterns()), (
        f"« {command} » est arrêté par un `deny` — la garde déborde sur les lectures ordinaires"
    )
