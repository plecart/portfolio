"""Tests de `.claude/skills/pr-paralleles/scripts/fin-transcript.py`.

Le script sert exactement une fois par incident : une session équipière est morte sans passation,
et son transcript est le seul récit de l'étape qu'elle avait atteinte (obs 54). Il doit donc être
juste **la première fois**, sur un transcript qu'on ne reverra pas — d'où ces témoins.

Deux classes de défaut le rendraient silencieusement faux, et ce sont celles que les cas ci-dessous
épinglent : classer un texte injecté par le harnais comme une décision du mainteneur (ou l'inverse,
plus grave : perdre un « go » que le harnais avait préfixé d'un bloc de contexte), et rendre un
sous-agent sans dire qu'il est mort avant d'avoir rien rendu.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from skill_scripts import load_script

fin = load_script("pr-paralleles", "fin-transcript")

HORODATAGE = "2026-10-13T10:00:00.000Z"


def tour(role: str, contenu: str, horodatage: str = HORODATAGE) -> dict[str, Any]:
    """Un enregistrement de transcript, tel que Claude Code l'écrit."""
    return {
        "type": role,
        "timestamp": horodatage,
        "message": {"content": [{"type": "text", "text": contenu}]},
    }


def ecrire(chemin: Path, enregistrements: list[dict[str, Any]]) -> Path:
    """Écrit un transcript JSONL et rend son chemin."""
    chemin.write_text(
        "".join(f"{json.dumps(e, ensure_ascii=False)}\n" for e in enregistrements), encoding="utf-8"
    )
    return chemin


# Le recueil de la classe « d'où vient ce texte du rôle `user` ? ». Les clés sont en **ASCII**
# parce qu'elles deviennent des identifiants de cas pytest, et qu'un `expect` de `mutation.py` doit
# apparier exactement un test. Chaque cas porte l'**orthographe réelle** du harnais, pas un
# représentant commode : le cas qui compte le plus est le quatrième, où le texte humain est
# *précédé* d'un bloc au lieu d'être seul — s'arrêter à la tête du message le perdait.
PROVENANCES = {
    "texte-tape-nu": ("go, merge", True),
    "bloc-injecte-seul": ("<task-notification>fini</task-notification>", False),
    "deux-blocs-injectes": (
        "<command-message>a</command-message><system-reminder>b</system-reminder>",
        False,
    ),
    "bloc-de-contexte-puis-texte-humain": ("<ide_opened_file>x.py</ide_opened_file>oui go", True),
    "message-de-pair": ("Another Claude session sent a message: fais X", False),
    "chargement-de-skill": ("Base directory for this skill: E:/x", False),
    "contenu-colle-par-le-mainteneur": (
        '<pasted_content id="7">un plan collé</pasted_content>',
        True,
    ),
}


@pytest.mark.parametrize(("brut", "attendu"), PROVENANCES.values(), ids=PROVENANCES.keys())
def test_chaque_provenance_d_un_texte_user_est_classee(brut: str, attendu: bool) -> None:
    """Un texte injecté compté comme une décision rend la passation fausse ; un « go » perdu la
    rend incomplète, ce qui est pire — c'est la seule matière du transcript qui ne se re-dérive
    pas des artefacts."""
    assert fin.de_la_main_du_mainteneur(brut) is attendu


def test_le_rapport_ne_garde_que_les_derniers_tours_dans_l_ordre(tmp_path: Path) -> None:
    """La fenêtre est la **fin** du transcript : c'est là que vit l'étape atteinte."""
    transcript = ecrire(
        tmp_path / "s.jsonl",
        [tour("assistant", f"tour {n}") for n in range(10)],
    )

    lignes = fin.rapport(transcript, 3)

    assert "## Derniers tours (3 sur les 3 demandés)" in lignes
    gardes = [ligne for ligne in lignes if "tour " in ligne]
    assert [ligne.split("tour ")[1] for ligne in gardes] == ["7", "8", "9"]


def test_les_messages_du_mainteneur_sont_rendus_sans_les_blocs_du_harnais(tmp_path: Path) -> None:
    """Le rapport se lit : un bloc de contexte collé devant un « go » le rendrait illisible."""
    transcript = ecrire(
        tmp_path / "s.jsonl",
        [
            tour("user", "<command-message>cycle-pr</command-message>"),
            tour("user", "<ide_opened_file>x.py</ide_opened_file>oui go"),
            tour("assistant", "ok"),
        ],
    )

    lignes = fin.rapport(transcript, 5)

    assert "## Messages du mainteneur (1)" in lignes
    assert any(ligne.endswith("oui go") for ligne in lignes), lignes


def test_un_sous_agent_mort_avant_de_rendre_est_nomme_comme_tel(tmp_path: Path) -> None:
    """Un sous-agent lancé en fond avant l'arrêt est perdu : le dire est l'information utile.

    Un rapport qui l'omet fait croire au lead qu'aucun travail n'était en vol, et c'est
    exactement l'état qu'obs 54 a dû reconstituer à la main — une seconde passe de relecture
    lancée six minutes avant l'arrêt, morte sans rapport.
    """
    transcript = ecrire(tmp_path / "s.jsonl", [tour("assistant", "je lance la relecture")])
    agents = tmp_path / "s" / "subagents"
    agents.mkdir(parents=True)
    ecrire(agents / "agent-a1.jsonl", [tour("user", "relis ce diff")])
    (agents / "agent-a1.meta.json").write_text(
        json.dumps({"agentType": "relecteur", "description": "Relecture 4.2"}), encoding="utf-8"
    )
    ecrire(agents / "agent-a2.jsonl", [tour("assistant", "rapport : 2 constats")])

    lignes = fin.rapport(transcript, 5)

    assert "## Sous-agents (2)" in lignes
    assert "- **relecteur — Relecture 4.2**" in lignes
    assert "  **aucun texte** — mort avant de rendre" in lignes
    assert any("rapport : 2 constats" in ligne for ligne in lignes), lignes


def test_un_sous_agent_sans_meta_est_nomme_par_son_fichier(tmp_path: Path) -> None:
    """Le `.meta.json` d'un sous-agent peut manquer — transcript tronqué, version d'outil
    différente. L'identité se replie alors sur le nom du fichier au lieu de lever : un rapport
    d'incident qui s'arrête sur un fichier absent ne sert à rien le jour où on en a besoin."""
    transcript = ecrire(tmp_path / "s.jsonl", [tour("assistant", "x")])
    agents = tmp_path / "s" / "subagents"
    agents.mkdir(parents=True)
    ecrire(agents / "agent-a2.jsonl", [tour("assistant", "rendu")])

    assert "- **agent-a2**" in fin.rapport(transcript, 5)


def test_une_ligne_illisible_ne_fait_pas_perdre_le_reste(tmp_path: Path) -> None:
    """Un transcript tronqué par l'arrêt de l'application finit souvent sur une ligne partielle —
    c'est le cas normal de cet outil, pas un cas limite."""
    chemin = tmp_path / "s.jsonl"
    chemin.write_text(f"{json.dumps(tour('assistant', 'avant'))}\n{{ tronqué\n", encoding="utf-8")

    lignes = fin.rapport(chemin, 5)

    assert any("avant" in ligne for ligne in lignes), lignes


def test_une_session_sans_sous_agent_le_dit(tmp_path: Path) -> None:
    """Le cas normal : pas de dossier `subagents/`, et surtout pas d'erreur."""
    transcript = ecrire(tmp_path / "s.jsonl", [tour("assistant", "seule")])

    lignes = fin.rapport(transcript, 5)

    assert "## Sous-agents (0)" in lignes
    assert "- aucun" in lignes


# Les sorties de la ligne de commande : chaque refus porte **son** code, et aucun ne vaut 0.
# Un script de reprise d'incident qui sort en 0 sur un chemin faux fait conclure « transcript
# vide » au lieu de « mauvais chemin ».
SORTIES: dict[str, tuple[list[str], int]] = {
    "sans-argument": ([], 2),
    "aide-demandee": (["--help"], 2),
    "transcript-introuvable": (["absent.jsonl"], 1),
    "nombre-de-tours-nul": (["__TRANSCRIPT__", "0"], 2),
    "nombre-de-tours-negatif": (["__TRANSCRIPT__", "-3"], 2),
}


@pytest.mark.parametrize("arguments,attendu", SORTIES.values(), ids=SORTIES.keys())
def test_chaque_refus_de_la_ligne_de_commande_porte_son_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arguments: list[str], attendu: int
) -> None:
    """Le code de sortie porte la condition — c'est la doctrine des portes de `cycle-pr` Étape 7
    appliquée à un script : un refus qui sort en 0 n'est pas un refus."""
    transcript = ecrire(tmp_path / "s.jsonl", [tour("assistant", "x")])
    monkeypatch.chdir(tmp_path)
    resolus = [str(transcript) if a == "__TRANSCRIPT__" else a for a in arguments]

    assert fin.main(resolus) == attendu
