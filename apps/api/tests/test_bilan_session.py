"""Tests du bilan de session `.claude/skills/cycle-pr/scripts/bilan-session.py`.

C'est la seule mesure qui dise si un changement de la pipeline a marché, et elle n'avait aucun
test : ses défauts sont des **classements silencieux**, qui vont tous dans le même sens — ils
chargent le mainteneur du temps des sous-agents, donc ils cachent le gain qu'on veut mesurer
(obs 41). Le transcript synthétique ci-dessous porte une occurrence de chaque forme de message
que le script classe, **plus les pièges** : un `prompt_snapshot` qui cite la chaîne d'une
notification dans le texte du prompt système, et une commande Bash de fond dont la notification
ressemble à celle d'un sous-agent.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from skill_scripts import load_script

bilan = load_script("cycle-pr", "bilan-session")

AGENT_CALL = "toolu_agent0000000000000001"
BASH_CALL = "toolu_bash00000000000000002"
AGENT_TOKENS = 177864
AGENT_NAME = 'Agent "Relecture 4.2 passe 1 #5" finished'


def at(clock: str) -> str:
    """Un horodatage du transcript, en UTC, le jour de la mesure d'obs 41."""
    return f"2026-09-27T{clock}.000Z"


def assistant(clock: str, *uses: tuple[str, str]) -> dict[str, Any]:
    """Un tour de l'agent, avec les appels d'outils qu'il lance."""
    content: list[dict[str, Any]] = [{"type": "text", "text": "…"}]
    content += [{"type": "tool_use", "id": call, "name": tool} for call, tool in uses]
    return {"type": "assistant", "timestamp": at(clock), "message": {"content": content}}


def said(clock: str, text: str) -> dict[str, Any]:
    """Un message dans le rôle `user` : humain, de pair, ou injecté par le harnais."""
    return {
        "type": "user",
        "timestamp": at(clock),
        "message": {"content": [{"type": "text", "text": text}]},
    }


def notification(
    clock: str, call: str, task: str, usage: str = "", status: str = "completed"
) -> dict[str, Any]:
    """La notification de fin d'une tâche de fond, telle que le harnais l'injecte.

    Forme mesurée le 2026-10-09 sur un transcript réel : une pièce jointe `queued_command` dont
    le `commandMode` vaut `task-notification`, et dont le texte porte le `<tool-use-id>` de
    l'appel qui a lancé la tâche — l'appariement exact, indépendant du préfixe du `task-id`.
    """
    return {
        "type": "attachment",
        "timestamp": at(clock),
        "attachment": {
            "type": "queued_command",
            "commandMode": "task-notification",
            "prompt": (
                f"<task-notification>\n<task-id>{task}</task-id>\n"
                f"<tool-use-id>{call}</tool-use-id>\n<status>{status}</status>\n"
                f"<summary>{AGENT_NAME}</summary>\n{usage}</task-notification>"
            ),
        },
    }


# Le piège : le texte du prompt système cite la chaîne d'une notification. Un test sur la ligne
# entière — `"<task-notification" in line` — le compte comme une fin de sous-agent.
SNAPSHOT_TRAP: dict[str, Any] = {
    "type": "attachment",
    "timestamp": at("10:01:00"),
    "attachment": {
        "type": "prompt_snapshot",
        "systemPrompt": ["… A <task-notification> fires each time this agent stops …"],
    },
}

# Le second piège, celui qui éprouve la garde du `commandMode` : une pièce jointe
# `queued_command` — donc porteuse d'un `prompt` — qui **cite** une notification complète, avec
# son `<tool-use-id>` et son `<status>completed</status>`. Sans la garde, elle fermerait la
# fenêtre de l'agent 17 minutes trop tôt, avec un compte de jetons inventé.
QUEUED_TRAP: dict[str, Any] = {
    "type": "attachment",
    "timestamp": at("10:03:00"),
    "attachment": {
        "type": "queued_command",
        "commandMode": "user",
        "prompt": (
            "regarde ce que le harnais m'a envoyé :\n<task-notification>\n"
            f"<tool-use-id>{AGENT_CALL}</tool-use-id>\n<status>completed</status>\n"
            '<summary>Agent "autre chose" finished</summary>\n'
            "<usage><subagent_tokens>999</subagent_tokens></usage>\n</task-notification>"
        ),
    },
}

TIMELINE: list[dict[str, Any]] = [
    said("10:00:00", "démarre le lot"),
    assistant("10:00:30", (AGENT_CALL, "Agent")),
    assistant("10:00:40", (BASH_CALL, "Bash")),
    SNAPSHOT_TRAP,
    notification("10:02:00", BASH_CALL, "b1uc6odr8"),
    QUEUED_TRAP,
    # La même tâche peut notifier plusieurs fois — le harnais le dit dans sa propre note. Seule
    # une notification `completed` ferme la fenêtre ; celle-ci la fermerait 10 minutes trop tôt.
    notification("10:10:00", AGENT_CALL, "a25bc5b33dbf83cd2", status="in_progress"),
    notification(
        "10:20:00",
        AGENT_CALL,
        "a25bc5b33dbf83cd2",
        f"<usage><subagent_tokens>{AGENT_TOKENS}</subagent_tokens></usage>\n",
    ),
    said("10:25:10", "Base directory for this skill: E:\\Projets\\Portfolio\\.claude\\skills\\x"),
    said("10:30:00", "Another Claude session sent a message: <cross-session-message from='lead'>"),
    said("10:35:00", "ok"),
    assistant("10:35:30"),
    said("12:00:00", "reprends"),
]
RELAY: list[dict[str, Any]] = [said("12:30:00", "je relaie"), assistant("12:40:00")]


def write_transcript(path: Path, records: list[dict[str, Any]]) -> Path:
    """Écrit un transcript JSONL — une ligne par enregistrement, comme le harnais le fait."""
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def read(tmp_path: Path) -> list[Any]:
    """Les deux transcripts de la session : le premier, puis son relais."""
    return bilan.read_events(
        [
            write_transcript(tmp_path / "session.jsonl", TIMELINE),
            write_transcript(tmp_path / "relais.jsonl", RELAY),
        ]
    )


def kinds(events: list[Any]) -> dict[str, int]:
    """Le dénombrement par classe, pour épingler chaque classement d'un coup."""
    counted: dict[str, int] = {}
    for event in events:
        kind = event.kind
        counted[kind] = counted.get(kind, 0) + 1
    return counted


def test_chaque_forme_de_message_est_classee_dans_sa_categorie(tmp_path: Path) -> None:
    """Les trois classements qu'obs 41 a mesurés faux, et le piège du `prompt_snapshot`.

    Un message de pair **commence** par « Another Claude session sent a message: », donc un test
    `startswith("<cross-session-message")` le classe humain ; un chargement de skill est un
    texte injecté dans le rôle `user`, donc il borne une fenêtre d'attente qui n'existe pas.
    """
    counted = kinds(read(tmp_path))

    assert counted["human"] == 4, "les 4 vrais messages du mainteneur, et eux seuls"
    assert counted["peer"] == 1
    assert counted["system"] == 1
    assert counted["notification"] == 2, "les deux vraies notifications, pas le prompt_snapshot"


def test_la_fenetre_d_un_sous_agent_est_bornee_par_l_identifiant_de_son_appel(
    tmp_path: Path,
) -> None:
    """Appariement par `<tool-use-id>`, pas par ordre d'arrivée ni par préfixe de `task-id`.

    Le transcript place exprès, entre le lancement de l'`Agent` et sa fin, deux candidats plus
    proches : un `prompt_snapshot` qui cite la chaîne, puis la notification d'une commande Bash
    de fond. « La première notification non attribuée » rendrait 30 s ou 1 min 30 au lieu de
    19 min 30 — l'erreur va toujours dans le sens qui masque le coût des sous-agents.
    """
    events = read(tmp_path)
    windows = bilan.subagent_windows(events, bilan.tool_calls(events))

    assert [bilan.total([window]) for window in windows] == [timedelta(minutes=19, seconds=30)]


def test_l_attente_du_mainteneur_exclut_le_temps_des_sous_agents(tmp_path: Path) -> None:
    """Sinon le mainteneur est facturé du temps qu'il n'a pas fait attendre (obs 41).

    Deux attentes réelles ici : 14 min 50 après le dernier tour de l'agent, et 1 h 24 min 30
    ensuite. Le chargement de skill de 10:25:10 n'en borne aucune.
    """
    events = read(tmp_path)
    blocked = bilan.blocked_windows(events, bilan.tool_calls(events))

    assert [bilan.total([window]) for window in blocked] == [
        timedelta(minutes=15),
        timedelta(hours=1, minutes=24, seconds=30),
    ]


def test_les_attentes_se_scindent_en_reactivite_et_absences(tmp_path: Path) -> None:
    """Deux phénomènes, deux remèdes : la réactivité relève de la pipeline, l'absence du
    calendrier. Les additionner sous un seul chiffre a fait lire la mesure comme un défaut
    alors que les changements avaient marché (obs 43)."""
    events = read(tmp_path)
    blocked = bilan.blocked_windows(events, bilan.tool_calls(events))
    reactivity, absences = bilan.split_waits(blocked)

    assert [bilan.total([window]) for window in reactivity] == [timedelta(minutes=15)]
    assert [bilan.total([window]) for window in absences] == [
        timedelta(hours=1, minutes=24, seconds=30)
    ]


def test_chaque_agent_porte_son_nom_et_ses_jetons(tmp_path: Path) -> None:
    """Les jetons par agent se lisent dans la notification elle-même, pas par `rglob`."""
    events = read(tmp_path)
    runs = bilan.agent_runs(events, bilan.tool_calls(events))

    assert [(run.name, run.tokens) for run in runs] == [("Relecture 4.2 passe 1 #5", AGENT_TOKENS)]


def test_le_rapport_porte_les_lignes_que_le_mainteneur_lit(tmp_path: Path) -> None:
    """Le pourcentage **hors absences** en tête, l'agrégat brut en second (obs 43), le nombre de
    transcripts et l'heure du relais (obs 40), et une ligne par agent.

    Le nombre de sessions n'est pas un paramètre : il se **déduit** des événements, qui portent
    chacun le rang de leur transcript. Un compte passé à côté des données peut être faux.
    """
    events = read(tmp_path)
    report = bilan.report(events, bilan.Usage(), bilan.Usage())

    assert "réactivité" in report
    assert "absences" in report
    assert "sessions : 2" in report
    assert "relais à" in report
    assert "Relecture 4.2 passe 1 #5" in report
    assert "177" in report, "les jetons de l'agent, en milliers"
    # L'attente hors absences se lit avant l'agrégat : 14 min 50 sur 2 h 40 de session.
    assert report.index("réactivité") < report.index("absences")


def test_un_transcript_vide_ou_illisible_ne_rend_pas_un_bilan_faux(tmp_path: Path) -> None:
    """Un bilan sur zéro événement vaudrait mieux ne pas exister que valoir zéro partout."""
    empty = write_transcript(tmp_path / "vide.jsonl", [])
    broken = tmp_path / "casse.jsonl"
    broken.write_text("{ceci n'est pas du json}\n", encoding="utf-8")

    assert bilan.read_events([empty]) == []
    assert bilan.read_events([broken]) == []


def test_les_transcripts_sont_fusionnes_dans_l_ordre_du_temps(tmp_path: Path) -> None:
    """Un cycle qui a rempli un contexte a plusieurs transcripts, donnés dans n'importe quel ordre.

    Les chemins sont passés **à l'envers** à dessein : c'est le seul montage où l'ordre des
    arguments et l'ordre du temps diffèrent, donc le seul qui éprouve le tri.
    """
    events = bilan.read_events(
        [
            write_transcript(tmp_path / "relais.jsonl", RELAY),
            write_transcript(tmp_path / "session.jsonl", TIMELINE),
        ]
    )

    moments = [event.when for event in events]
    assert moments == sorted(moments)
    assert moments[-1] == datetime.fromisoformat(at("12:40:00"))


def test_un_sous_agent_sans_notification_de_fin_est_denombre(tmp_path: Path) -> None:
    """Un agent encore en cours, ou mort sans notifier, n'a pas de fenêtre — et serait écarté
    sans trace. L'écart entre les lancements et les fins se lit dans le rapport.

    Mesuré en écrivant ce script : le bilan de la session qui l'écrivait annonçait « workflows
    0 / 0 » alors qu'un relecteur tournait.
    """
    lonely: list[dict[str, Any]] = [
        said("09:00:00", "lance"),
        assistant("09:00:10", ("toolu_jamais_fini0000000001", "Agent")),
        assistant("09:30:00"),
    ]
    events = bilan.read_events([write_transcript(tmp_path / "seul.jsonl", lonely)])
    calls = bilan.tool_calls(events)

    assert "sans notification de fin : 1" in bilan.report(events, bilan.Usage(), bilan.Usage())
    assert bilan.agent_runs(events, calls) == []
    assert len(bilan.launched_subagents(events, calls)) == 1
