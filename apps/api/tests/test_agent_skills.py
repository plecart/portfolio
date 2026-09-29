"""Tests des skills de l'agent (`.claude/skills/*/SKILL.md`).

Claude Code lit le frontmatter YAML de chaque skill ; s'il ne parse pas, « the skill still loads
with no fields set » (doc « Extend Claude with skills ») : le skill reste invocable par `/<nom>`,
mais sa `description` ne sert plus au déclenchement automatique et son `argument-hint` disparaît —
sans erreur, nulle part. Mesuré le 2026-09-29 : trois skills maison sur treize étaient dans cet
état depuis leur création, listés par leur titre H1 au lieu de leur description, parce qu'un
« Déclencheurs : » sans guillemets fait d'un scalaire une clé de mapping.
"""

import re
from pathlib import Path
from typing import cast

import pytest
import yaml

# `test_agent_skills.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SKILLS = sorted(REPOSITORY_ROOT.glob(".claude/skills/*/SKILL.md"))

# Le bloc entre les deux `---` de tête, quelle que soit la fin de ligne de la copie de travail.
FRONTMATTER = re.compile(r"\A---\r?\n(?P<yaml>.*?)\r?\n---\r?\n", re.DOTALL)

# Le champ sans lequel un skill ne se déclenche pas sur sa description — `name` est optionnel et
# vaut par défaut le nom du dossier.
REQUIRED_FIELDS = {"description"}


def frontmatter(skill: Path) -> dict[str, object]:
    """Le frontmatter d'un skill, tel que Claude Code le lira.

    Args:
        skill: le `SKILL.md` à lire.

    Returns:
        Les champs du frontmatter, par nom.

    Raises:
        AssertionError: bloc absent, YAML illisible, ou frontmatter qui n'est pas un mapping —
            les trois états où Claude Code charge le skill sans aucun champ.
    """
    match = FRONTMATTER.match(skill.read_text(encoding="utf-8-sig"))
    assert match, f"{skill.parent.name} : aucun frontmatter en tête du fichier"
    try:
        fields: object = yaml.safe_load(match.group("yaml"))
    except yaml.YAMLError as error:
        raise AssertionError(f"{skill.parent.name} : frontmatter illisible — {error}") from error
    assert isinstance(fields, dict), f"{skill.parent.name} : le frontmatter n'est pas un mapping"
    return cast(dict[str, object], fields)


def test_le_dossier_des_skills_n_est_pas_vide() -> None:
    """Un motif qui n'apparie plus rien laisserait le test paramétré vert par absence."""
    assert SKILLS, (
        "aucun `SKILL.md` trouvé sous `.claude/skills/` — le motif a-t-il cessé de mordre ?"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=[skill.parent.name for skill in SKILLS])
def test_le_frontmatter_de_chaque_skill_parse_et_porte_ses_champs(skill: Path) -> None:
    """Un frontmatter illisible ne fait rougir aucune porte : le skill charge quand même, muet."""
    fields = frontmatter(skill)

    missing = REQUIRED_FIELDS - fields.keys()
    assert not missing, f"{skill.parent.name} : champs manquants {sorted(missing)}"
    description = fields.get("description")
    assert isinstance(description, str) and description.strip(), (
        f"{skill.parent.name} : description absente, vide ou non textuelle — Claude Code la jette"
    )
