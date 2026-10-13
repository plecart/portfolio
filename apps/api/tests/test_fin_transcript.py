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
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from skill_scripts import REPOSITORY_ROOT, load_script

fin = load_script("pr-paralleles", "fin-transcript")
SCRIPT = REPOSITORY_ROOT / ".claude" / "skills" / "pr-paralleles" / "scripts" / "fin-transcript.py"

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
    # Deux blocs de **même balise** autour du texte humain : seule cette forme distingue le retrait
    # non gourmand du gourmand — avec une seule balise, les deux rendent pareil, et une mutation
    # `.*?` → `.*` est restée VERTE (passe 2 du relecteur). Gourmand, `<s>…</s>` avale « oui go ».
    "bloc-texte-bloc-de-meme-balise": (
        "<system-reminder>a</system-reminder>oui go<system-reminder>b</system-reminder>",
        True,
    ),
    # Un cas **littéral** par préfixe injecté, dans l'orthographe réelle du harnais. Pas une
    # dérivation du tuple du script : dérivés, les cas suivaient la mutation — retirer un préfixe
    # du script retirait son cas au lieu de le faire rougir (mesuré, VERT). Une table qui se
    # construit depuis l'artefact qu'elle éprouve est une seule méthode qui conclut.
    "interruption-de-requete": ("[Request interrupted by user]", False),
    "avis-d-inactivite-de-pair": ("[Cross-session idle notice] app-6b est inactive", False),
    "reprise-de-conversation": (
        "This session is being continued from a previous conversation that ran out of context.",
        False,
    ),
}


def test_chaque_prefixe_injecte_du_script_a_son_cas_litteral() -> None:
    """L'autre moitié de la garde des préfixes : un préfixe ajouté au script sans son cas littéral
    rougit ici, et un cas retiré rougit à la mutation. Les deux listes se gardent l'une l'autre ;
    aucune des deux ne se dérive de l'autre."""
    refuses = [brut for brut, attendu in PROVENANCES.values() if attendu is False]

    sans_cas = [p for p in fin.PREFIXES_INJECTES if not any(t.startswith(p) for t in refuses)]

    assert not sans_cas, f"préfixes du script sans cas littéral : {sans_cas}"


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
    ecrire(
        agents / "agent-a2.jsonl",
        [tour("assistant", "je commence"), tour("assistant", "rapport : 2 constats")],
    )

    lignes = fin.rapport(transcript, 5)

    assert "## Sous-agents (2)" in lignes
    assert "- **relecteur — Relecture 4.2**" in lignes
    assert "  **aucun texte** — mort avant de rendre" in lignes
    # Le **dernier** texte, pas le premier : avec un seul message par sous-agent, « dernier »
    # devenu « premier » restait VERT (mesuré, passe 2).
    assert any("rapport : 2 constats" in ligne for ligne in lignes), lignes
    assert not any("je commence" in ligne for ligne in lignes), lignes


def test_un_sous_agent_sans_meta_lisible_est_nomme_par_son_fichier(tmp_path: Path) -> None:
    """Le `.meta.json` d'un sous-agent peut manquer ou être tronqué — arrêt de l'application en
    pleine écriture, version d'outil différente. L'identité se replie alors sur le nom du fichier
    au lieu de lever : un rapport d'incident qui s'arrête sur un fichier absent ou illisible ne
    sert à rien le jour où on en a besoin. Les deux états sont là, parce que retirer le
    `try/except` de l'illisible restait VERT avec le seul absent (mesuré, passe 2)."""
    transcript = ecrire(tmp_path / "s.jsonl", [tour("assistant", "x")])
    agents = tmp_path / "s" / "subagents"
    agents.mkdir(parents=True)
    ecrire(agents / "agent-a2.jsonl", [tour("assistant", "rendu")])
    ecrire(agents / "agent-a3.jsonl", [tour("assistant", "rendu")])
    (agents / "agent-a3.meta.json").write_text("{ tronqué", encoding="utf-8")

    lignes = fin.rapport(transcript, 5)

    assert "- **agent-a2**" in lignes
    assert "- **agent-a3**" in lignes


def test_un_texte_long_est_tronque_a_l_extrait(tmp_path: Path) -> None:
    """Un rapport se lit en une page : un tour de 400 lignes de diff collé par le mainteneur ne
    doit pas l'emporter. La borne est celle du script, lue là, pas recopiée."""
    transcript = ecrire(tmp_path / "s.jsonl", [tour("assistant", "x" * (fin.EXTRAIT + 50))])

    ligne = next(ligne for ligne in fin.rapport(transcript, 5) if "**assistant**" in ligne)

    assert ligne.endswith("…")
    assert "x" * fin.EXTRAIT in ligne
    assert "x" * (fin.EXTRAIT + 1) not in ligne


def test_la_sortie_standard_est_en_utf_8_quelle_que_soit_la_console(tmp_path: Path) -> None:
    """Mesuré sur un vrai transcript de ce poste : un `→` dans un message, console cp1252,
    `UnicodeEncodeError`, rc 1, rien d'imprimé — l'outil d'incident mort à l'incident. Les
    transcripts sont pleins de flèches et d'emojis, et l'outil ne sert que sur ce poste.

    Joué en sous-processus avec `PYTHONIOENCODING=cp1252` forcé, pour reproduire la console du
    poste même sur la CI Linux, dont la sortie est en UTF-8 par défaut. Pas de `-I` ici : il
    implique `-E`, qui ignore précisément la variable qui fait le cas.
    """
    transcript = ecrire(tmp_path / "s.jsonl", [tour("assistant", "a → b")])

    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(transcript), "3"],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        check=False,
    )

    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert "a → b" in done.stdout.decode("utf-8")


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


# Les sorties de la ligne de commande — une **frontière d'entrée saisie à la main**, balayée en une
# passe pour la présence **et** le type de chaque champ (`cleanup-verbatim.md`) : le transcript
# (présence, existence), le nombre de tours (type entier, plage), et rien de plus. Chaque refus
# porte **son** code, et aucun ne vaut 0 : un script de reprise d'incident qui sort en 0 sur un
# chemin faux fait conclure « transcript vide » au lieu de « mauvais chemin » ; et un `abc` qui
# sortait sur une trace `ValueError` en 1 se lisait comme « transcript introuvable » (mesuré,
# passe 2) — d'où le 2 de l'usage, distinct du 1 de l'absence.
SORTIES: dict[str, tuple[list[str], int]] = {
    "sans-argument": ([], 2),
    "aide-demandee": (["--help"], 2),
    "transcript-introuvable": (["absent.jsonl"], 1),
    "nombre-de-tours-nul": (["__TRANSCRIPT__", "0"], 2),
    "nombre-de-tours-negatif": (["__TRANSCRIPT__", "-3"], 2),
    "nombre-de-tours-non-entier": (["__TRANSCRIPT__", "abc"], 2),
    "trop-d-arguments": (["__TRANSCRIPT__", "3", "de-trop"], 2),
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
