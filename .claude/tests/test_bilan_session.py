"""Tests du bilan de session `.claude/skills/cycle-pr/scripts/bilan-session.py`.

C'est la seule mesure qui dise si un changement de la pipeline a marché, et elle n'avait aucun
test : ses défauts sont des **classements silencieux**, qui vont tous dans le même sens — ils
chargent le mainteneur du temps des sous-agents, donc ils cachent le gain qu'on veut mesurer
(obs 41). Le transcript synthétique ci-dessous porte une occurrence de chaque forme de message
que le script classe, **plus les pièges** : un `prompt_snapshot` qui cite la chaîne d'une
notification dans le texte du prompt système, et une commande Bash de fond dont la notification
ressemble à celle d'un sous-agent.
"""

import io
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import load_script

bilan = load_script("cycle-pr", "bilan-session")

AGENT_CALL = "toolu_agent0000000000000001"
BASH_CALL = "toolu_bash00000000000000002"
WORKFLOW_CALL = "toolu_workflow000000000003"
AGENT_NAME = 'Agent "Relecture 4.2 passe 1 #5" finished'


def at(clock: str) -> str:
    """Un horodatage du transcript, en UTC, le jour de la mesure d'obs 41 — à la milliseconde,
    sauf si `clock` porte sa propre fraction."""
    return f"2026-09-27T{clock}{'' if '.' in clock else '.000'}Z"


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
# fenêtre de l'agent 17 minutes trop tôt.
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
    assistant("10:05:00", (WORKFLOW_CALL, "Workflow")),
    notification("10:15:00", WORKFLOW_CALL, "w3k9fjz2q", status="completed"),
    # La même tâche peut notifier plusieurs fois — le harnais le dit dans sa propre note. Seule
    # une notification `completed` ferme la fenêtre ; celle-ci la fermerait 10 minutes trop tôt.
    notification("10:10:00", AGENT_CALL, "a25bc5b33dbf83cd2", status="in_progress"),
    notification(
        "10:20:00",
        AGENT_CALL,
        "a25bc5b33dbf83cd2",
        "<usage><subagent_tokens>177864</subagent_tokens></usage>\n",
    ),
    # Reprise puis arrêt : une seconde `completed` du **même** appel. La première l'emporte,
    # donc fenêtre close à 10:20 ; la dernière donnerait 10:22. C'est ce qui épingle la décision
    # verrouillée du critère 3 — la reprise, elle, se lit dans le transcript du sous-agent.
    notification(
        "10:22:00",
        AGENT_CALL,
        "a25bc5b33dbf83cd2",
        "<usage><subagent_tokens>999</subagent_tokens></usage>\n",
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


def ligne(sortie: str, debut: str) -> str:
    """La première ligne du rapport qui commence par `debut`."""
    return next(line for line in sortie.splitlines() if line.startswith(debut))


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
    assert counted["notification"] == 4, "les quatre vraies, pas le prompt_snapshot ni le piège"


def test_la_fenetre_d_un_sous_agent_est_bornee_par_l_identifiant_de_son_appel(
    tmp_path: Path,
) -> None:
    """Appariement par `<tool-use-id>`, pas par ordre d'arrivée ni par préfixe de `task-id`.

    Le transcript place exprès, entre le lancement de l'`Agent` et sa fin, deux candidats plus
    proches : un `prompt_snapshot` qui cite la chaîne, puis la notification d'une commande Bash
    de fond. « La première notification non attribuée » rendrait 30 s ou 1 min 30 au lieu de
    19 min 30 — l'erreur va toujours dans le sens qui masque le coût des sous-agents.
    """
    m = bilan.measure(read(tmp_path))

    assert [bilan.total([window]) for window in m.windows] == [timedelta(minutes=19, seconds=30)]


def test_l_attente_du_mainteneur_exclut_le_temps_des_sous_agents(tmp_path: Path) -> None:
    """Sinon le mainteneur est facturé du temps qu'il n'a pas fait attendre (obs 41).

    Deux attentes réelles ici : 15 min après la fin du sous-agent, et 1 h 54 min 30 ensuite. Le
    chargement de skill de 10:25:10 n'en borne aucune. Chacune court jusqu'au **dernier**
    message qui précède la reprise de l'agent : le message de pair de 10:30 n'a rien déclenché
    avant le « ok » de 10:35, ni le « reprends » de 12:00 avant le relais ouvert à 12:30.
    """
    m = bilan.measure(read(tmp_path))

    assert [bilan.total([window]) for window in m.blocked] == [
        timedelta(minutes=15),
        timedelta(hours=1, minutes=54, seconds=30),
    ]


def test_les_attentes_se_scindent_en_reactivite_et_absences(tmp_path: Path) -> None:
    """Deux phénomènes, deux remèdes : la réactivité relève de la pipeline, l'absence du
    calendrier. Les additionner sous un seul chiffre a fait lire la mesure comme un défaut
    alors que les changements avaient marché (obs 43)."""
    m = bilan.measure(read(tmp_path))

    assert [bilan.total([window]) for window in m.reactivity] == [timedelta(minutes=15)]
    assert [bilan.total([window]) for window in m.absences] == [
        timedelta(hours=1, minutes=54, seconds=30)
    ]


def test_le_rapport_porte_les_lignes_que_le_mainteneur_lit(tmp_path: Path) -> None:
    """Le pourcentage **hors absences** en tête, l'agrégat brut en second (obs 43), le nombre de
    transcripts et l'heure du relais (obs 40). Les lignes par agent ont leur propre test,
    `test_le_rapport_rend_chaque_contact_avec_sa_consommation`.

    Le nombre de sessions n'est pas un paramètre : il se **déduit** des événements, qui portent
    chacun le rang de leur transcript. Un compte passé à côté des données peut être faux.

    Les ancres d'ordre sont les **libellés de ligne**, pas les mots qu'ils contiennent : la ligne
    du dénominateur porte elle-même le mot « absences », et une assertion sur le mot nu la
    trouvait d'abord, donc rougissait sur une mise en page correcte.
    """
    events = read(tmp_path)
    report = bilan.report(events, bilan.Usage(), [])

    assert "réactivité (< 1 h)" in report
    assert "absences (≥ 1 h)" in report
    assert "actif (hors absences)" in report, "le dénominateur doit se lire, pas se deviner"
    assert "sessions : 2" in report
    assert "relais à" in report
    # L'attente hors absences se lit avant l'agrégat : 15 min sur 45 min 30 de temps actif.
    assert report.index("réactivité (< 1 h)") < report.index("absences (≥ 1 h)")


def test_la_reactivite_se_rapporte_au_temps_actif_et_les_absences_a_la_session(
    tmp_path: Path,
) -> None:
    """Deux dénominateurs, et c'est tout le propos du critère « pourcentage hors absences ».

    Sur le transcript synthétique : 2 h 40 de session dont 1 h 54 min 30 d'absence, donc
    **45 min 30 de temps actif**. Les 15 min d'attente valent **33 % du temps actif** et
    seulement 9 % de la session — rapporter la réactivité à la session la dilue
    d'autant que le mainteneur a été absent, et fait croire à un gain que personne n'a obtenu.
    C'est le sens d'erreur d'obs 41, appliqué au dénominateur au lieu du numérateur.
    """
    measures = bilan.measure(read(tmp_path))

    assert measures.active == measures.span - bilan.total(measures.absences)
    assert measures.active < measures.span, "le montage doit porter une absence"

    report = bilan.report(read(tmp_path), bilan.Usage(), [])
    reactivite = ligne(report, "réactivité")
    absences = ligne(report, "absences")
    part_active = bilan.total(measures.reactivity) / measures.active
    part_session = bilan.total(measures.reactivity) / measures.span

    assert f"{part_active:4.0%}" in reactivite
    assert f"{part_session:4.0%}" not in reactivite, "la réactivité est diluée par les absences"
    assert f"{bilan.total(measures.absences) / measures.span:4.0%}" in absences


def test_la_mediane_de_reactivite_arrondit_la_demi_microseconde_au_pair(tmp_path: Path) -> None:
    """Deux attentes de 59,999999 s et 60 s : la médiane vaut 59,9999995 s, que l'arrondi au pair
    porte à 60 s, soit 0 h 01. Une médiane basse, ou un arrondi par troncature, la laisse sous la
    minute — et `hm`, qui tronque à la minute, rend alors 0 h 00."""
    timeline = [
        assistant("10:00:00"),
        said("10:00:59.999999", "ok"),
        assistant("10:10:00"),
        said("10:11:00", "ok"),
    ]
    events = bilan.read_events([write_transcript(tmp_path / "session.jsonl", timeline)])

    report = bilan.report(events, bilan.Usage(), [])

    assert "(2 attentes, médiane 0 h 01)" in ligne(report, "réactivité")


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
    """Un lancement sans notification de fin **ni** transcript de sous-agent n'a pas de fenêtre
    — et serait écarté sans trace. L'écart se lit dans le rapport. Un agent qui a un transcript
    n'y entre pas : le relevé par contact le montre déjà, en cours ou mort.

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

    report = bilan.report(events, bilan.Usage(), [])
    assert "sans notification de fin ni transcript rattaché : 1" in report
    assert bilan.agent_runs(events, calls) == []
    assert len(bilan.launched_subagents(events, calls)) == 1


# --- Ce que la passe 2 a trouvé (2026-10-09) ---------------------------------------------------


# Le recueil des formes réelles, avec sa **population** : les 80 transcripts du projet au
# 2026-10-14 à 14:08 UTC (`~/.claude/projects/*ortfolio*/*.jsonl`), soit **1083 messages de rôle
# `user` hors résultat d'outil**.
#
# **Cette population est vivante** : les sessions en écrivent, et le harnais fait tourner les
# transcripts. Le 2026-10-10, elle valait 87 transcripts et 1137 messages à 09 h, puis 85 et 1106
# une heure plus tard. Les nombres ci-dessous sont donc un relevé **daté**, qu'un nouveau
# recensement ne reproduira pas — et ce n'est pas eux que la suite assère. Ce qu'elle assère est
# l'**invariant** : les 17 formes couvrent la population sans résidu, leur somme et leurs classes
# se répondent. Une famille neuve ne peut donc pas entrer sans que la population soit re-mesurée
# avec elle.
#
# Deux dénombrements ont déjà menti ici. La classe « pair » avait été fermée sur la seule forme
# qui l'avait révélée (`<cross-session-message`), alors que 48 messages portaient
# `<agent-message`. Puis la règle de forme a classé `system` **10 messages humains** : le harnais
# préfixe le texte du mainteneur d'une balise de contexte au lieu de l'injecter seule, et une
# balise *en tête* suffisait à classer. Les deux fois, le correctif a été déclaré clos sur la
# seule famille qui l'avait révélé ; les deux fois, la relecture suivante en a trouvé une autre.
# D'où la forme de ce recueil : **les 6 familles qui apparaissent en tête y sont**, plus la
# balise à attributs, et les trois formes de commande sont recopiées du relevé du 2026-10-14. Il
# y en a **8 en comptant toutes les positions** : `<command-args>` (23 messages) et
# `<skill-format>` (6) n'arrivent **jamais** en tête, toujours à la suite d'un autre bloc — c'est
# précisément ce que la règle de tête ne pouvait pas voir, et ce que le `+` du motif couvre.
FORMES_REELLES = {
    # Les 6 familles de balises. Un message n'est injecté que s'il n'est *rien d'autre* que des
    # blocs équilibrés : la famille de contexte IDE porte un texte humain après son bloc, et ce
    # texte est de la main du mainteneur.
    "notification de fin de tâche": (
        "<task-notification><status>completed</status></task-notification>",
        "system",
        79,
    ),
    # Une commande **tapée** porte la barre oblique dans `<command-name>` : c'est le mainteneur
    # qui agit, et son message rouvre un tour comme sa prose. Classée `system`, elle laissait
    # compter en travail d'agent l'attente qui la précède — 15 attentes et 1 j 17 h 45 au relevé
    # des attentes du 2026-10-14 à 13:47 UTC. Le skill que l'agent lance lui-même n'a pas de barre
    # oblique.
    "skill tapé par le mainteneur": (
        "<command-message>i-have-adhd</command-message>\n<command-name>/i-have-adhd</command-name>",
        "human",
        27,
    ),
    "commande locale tapée par le mainteneur": (
        (
            "<command-name>/model</command-name>\n            <command-message>model"
            "</command-message>\n            <command-args></command-args>"
        ),
        "human",
        13,
    ),
    # Chargé par le harnais à la suite d'un message du mainteneur, sans commande tapée : les 6
    # occurrences suivent un message `human`, aucune un appel d'outil de l'agent.
    "skill chargé par le harnais": (
        (
            "<command-message>workflow-authoring</command-message>\n<command-name>"
            "workflow-authoring</command-name>\n<skill-format>true</skill-format>"
        ),
        "system",
        6,
    ),
    "mise en garde d'une commande locale": (
        (
            "<local-command-caveat>Caveat: The messages below were generated by the "
            "user</local-command-caveat>"
        ),
        "system",
        13,
    ),
    "sortie d'une commande locale": (
        "<local-command-stdout>Set model to `claude-opus-5`</local-command-stdout>",
        "system",
        6,
    ),
    "fichier ouvert dans l'éditeur, puis le texte du mainteneur": (
        (
            "<ide_opened_file>The user opened the file e:\\Projets\\Portfolio\\x.py in the"
            " IDE.</ide_opened_file>oui go"
        ),
        "human",
        6,
    ),
    # La balise **à attributs** : elle n'est pas du harnais, c'est un collage du mainteneur. Elle
    # borne la règle de forme par le haut — un nom suivi d'un attribut n'est pas une injection.
    "collage du mainteneur": (
        '<pasted_content id="a4a8">Tu reprends le lot 1/4</pasted_content>',
        "human",
        12,
    ),
    # Les 5 formes injectées qui ne sont **pas** des balises — à énumérer, elles.
    "chargement d'un skill": (
        "Base directory for this skill: E:\\Projets\\Portfolio\\.claude\\skills\\x",
        "system",
        169,
    ),
    # Le texte d'un skill peut citer une balise de pair — `cycle-pr` le fait pour décrire une
    # vague. Classé `peer` sur cette seule citation, son chargement comptait un contact de pair
    # de plus.
    "chargement d'un skill qui cite une balise de pair": (
        (
            "Base directory for this skill: E:\\Projets\\Portfolio\\.claude\\skills\\cycle-pr\n\n"
            "**Vague parallèle.** Si le prompt de démarrage de cette session est arrivé dans un"
            " bloc `<cross-session-message>`, la session émettrice est le **lead**"
        ),
        "system",
        40,
    ),
    "interruption par le mainteneur": ("[Request interrupted by user]", "system", 32),
    # L'avis qu'une session voisine est au repos, que l'agent a demandé en l'attendant : il
    # rouvre un tour de pair, comme le message qu'elle aurait envoyé.
    "avis d'inactivité d'une session voisine": (
        '[Cross-session idle notice] "uds:\\\\.\\pipe\\LOCAL" est au repos',
        "peer",
        23,
    ),
    "référence d'écriture de workflow": (
        "# Workflow authoring reference\n\nA workflow structures work…",
        "system",
        6,
    ),
    "reprise d'une conversation compactée": (
        "This session is being continued from a previous conversation that ran out of context",
        "system",
        2,
    ),
    # Les 2 balises d'un message de pair : elles arrivent **après** une phrase d'introduction,
    # donc aucune règle de tête ne les voit.
    "message de pair, balise historique": (
        "Another Claude session sent a message:\n<cross-session-message from='lead'>",
        "peer",
        185,
    ),
    "message de pair, balise actuelle": (
        "Another Claude session sent a message:\n<agent-message from='relecteur'>",
        "peer",
        50,
    ),
    # Et la prose du mainteneur, qui ne commence par rien de tout cela.
    "prose du mainteneur": ("Quelles sont les bonnes pratiques pour cela ?", "human", 414),
}

# Le recensement du 2026-10-14 à 14:08 UTC, que le recueil doit couvrir sans résidu.
POPULATION = 1083
PAR_CLASSE = {"human": 472, "system": 353, "peer": 258}


@pytest.mark.parametrize(
    ("text", "expected", "seen"), FORMES_REELLES.values(), ids=FORMES_REELLES.keys()
)
def test_chaque_forme_reelle_tombe_dans_sa_classe(text: str, expected: str, seen: int) -> None:
    """Chaque forme réellement rencontrée tombe dans sa classe, dans sa forme **entière**.

    L'échantillon porte le bloc fermé, et le texte qui le suit quand il y en a un : tronqué
    avant sa fermeture, `<ide_opened_file>` attendait `system` et ne représentait aucune de ses
    9 occurrences réelles — le test épinglait le défaut au lieu de le trouver.

    Args:
        text: la forme, telle qu'elle arrive dans un message réel.
        expected: la classe attendue.
        seen: ses occurrences au recensement du 2026-10-14.
    """
    assert seen > 0, "une forme recensée zéro fois n'a rien à faire dans ce recueil"

    assert bilan.classify("user", [{"type": "text", "text": text}]) == expected


def test_le_recueil_couvre_la_population_entiere() -> None:
    """Les formes du recueil font la **somme exacte** de la population, sans résidu.

    C'est le cliquet du dénombrement. Deux fois de suite, un correctif de classement a été
    déclaré clos sur la famille qui l'avait révélé, et la relecture suivante en a trouvé une
    autre. Une somme assertée oblige à re-mesurer la population pour ajouter une forme, et
    rougit si l'on en retire une : le dénombrement cesse de vivre dans une phrase de docstring.
    """
    assert sum(seen for _, _, seen in FORMES_REELLES.values()) == POPULATION

    par_classe = {
        classe: sum(s for _, c, s in FORMES_REELLES.values() if c == classe)
        for classe in PAR_CLASSE
    }
    assert par_classe == PAR_CLASSE


PEER_MESSAGE = FORMES_REELLES["message de pair, balise historique"][0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [(text, expected) for text, expected, _ in FORMES_REELLES.values()],
    ids=FORMES_REELLES.keys(),
)
def test_chaque_forme_reelle_rouvre_un_tour_selon_sa_classe(
    tmp_path: Path, text: str, expected: str
) -> None:
    """Une attente court de la dernière sortie de l'agent au message qui rouvre son tour.

    Seuls le mainteneur — prose ou commande tapée — et un pair — message ou avis de repos —
    rouvrent un tour. Dénombrement sur les 17 formes du recueil : **8** rouvrent un tour, dont
    **5** ne fermaient aucune attente avant ce correctif — les deux commandes tapées, les deux
    balises de pair, l'avis de repos —, seul un message `human` fermant alors une attente. Au
    relevé des attentes du 2026-10-14 à 13:47 UTC, les 213 attentes closes par un message de
    pair, 6 j 18 h 46 au total, se comptaient ainsi en travail d'agent. Témoins des deux côtés :
    les 9 formes `system` du recueil ne rouvrent rien.

    Args:
        text: la forme, telle qu'elle arrive dans un message réel.
        expected: sa classe au recueil.
    """
    tour = [assistant("09:00:00"), said("09:20:00", text), assistant("09:21:00")]
    events = bilan.read_events([write_transcript(tmp_path / "tour.jsonl", tour)])

    attendu = [timedelta(minutes=20)] if expected in ("human", "peer") else []
    assert [bilan.total([window]) for window in bilan.measure(events).blocked] == attendu


def labelled(text: str, origin: str | None = None, meta: bool = False) -> dict[str, Any]:
    """Un message `user` portant les étiquettes que le harnais écrit lui-même.

    Args:
        text: le texte du message.
        origin: la valeur de `origin.kind`, ou `None` pour un message sans `origin`.
        meta: la valeur de `isMeta`.
    """
    record = said("09:20:00", text)
    if origin is not None:
        record["origin"] = {"kind": origin}
    if meta:
        record["isMeta"] = True
    return record


# Les étiquettes du harnais, au relevé du 2026-10-14 vers 16 h UTC (population vivante) : sur
# 1064 messages `user` hors résultat d'outil, 439 `origin.kind=human`, 234 `peer`,
# 83 `task-notification`, 259 `isMeta` sans origine, 49 sans aucune étiquette. `origin.kind`
# concorde avec le texte sur les 756 messages qu'il étiquette : il n'est pas lu. `isMeta`, lui,
# corrige le texte sur **9** messages qu'il classait `human` — corps de `/code-review` (3), de
# `/security-review` (2) et de `/fewer-permission-prompts` (1), reprise après coupure (2), image
# jointe (1) : aucune liste de préfixes ne les rattrape. Chaque cas ci-dessous est une forme
# réelle, portant les étiquettes de son enregistrement.
ETIQUETTES = {
    "commande tapée, étiquetée humaine": (
        labelled(FORMES_REELLES["skill tapé par le mainteneur"][0], origin="human"),
        "human",
    ),
    "prose étiquetée humaine": (labelled("oui go", origin="human"), "human"),
    "message de pair étiqueté": (labelled(PEER_MESSAGE, origin="peer", meta=True), "peer"),
    "notification étiquetée": (
        labelled(FORMES_REELLES["notification de fin de tâche"][0], origin="task-notification"),
        "system",
    ),
    "corps de /code-review, isMeta": (
        labelled("Review target: `91 medium`\n\n`xhigh effort → 10 inline angles`", meta=True),
        "system",
    ),
    "reprise après coupure, isMeta": (
        labelled("Your response above was cut off mid-stream. Resume directly.", meta=True),
        "system",
    ),
    "avis de repos, isMeta": (
        labelled(FORMES_REELLES["avis d'inactivité d'une session voisine"][0], meta=True),
        "peer",
    ),
    "commande locale sans étiquette": (
        labelled(FORMES_REELLES["commande locale tapée par le mainteneur"][0]),
        "human",
    ),
    "interruption sans étiquette": (labelled("[Request interrupted by user]"), "system"),
}


@pytest.mark.parametrize(("record", "expected"), ETIQUETTES.values(), ids=ETIQUETTES.keys())
def test_une_injection_du_harnais_n_est_jamais_du_mainteneur(
    tmp_path: Path, record: dict[str, Any], expected: str
) -> None:
    """`isMeta` marque une injection, qui n'est jamais du mainteneur — elle peut rester un pair,
    comme l'avis de repos. Sans `isMeta`, le texte décide, comme avant : témoins des messages
    du mainteneur, étiquetés ou non, d'un pair et d'une interruption.

    Args:
        record: le message, avec ses étiquettes.
        expected: la classe attendue.
    """
    events = bilan.read_events([write_transcript(tmp_path / "un.jsonl", [record])])

    assert [event.kind for event in events] == [expected]


def test_une_commande_tapee_se_reconnait_en_tete_du_message() -> None:
    """La barre oblique ne fait une commande tapée qu'en tête : citée dans un autre bloc — le
    résumé d'une notification, la sortie d'une commande —, elle n'en fait pas un message du
    mainteneur."""
    cite = (
        "<task-notification><status>completed</status><summary>a relancé "
        "<command-name>/model</command-name></summary></task-notification>"
    )

    assert bilan.classify("user", [{"type": "text", "text": cite}]) == "system"


def test_une_balise_de_pair_dans_un_rappel_systeme_ne_fait_pas_un_pair() -> None:
    """Un rappel système joint au message du mainteneur peut citer une balise de pair : le
    classement se fait sur le texte sans ses rappels, comme pour toutes les autres règles."""
    message = "oui go<system-reminder>arrivé dans un <cross-session-message></system-reminder>"

    assert bilan.classify("user", [{"type": "text", "text": message}]) == "human"


def test_un_message_livre_apres_un_retour_d_outil_n_ouvre_pas_d_attente(tmp_path: Path) -> None:
    """L'agent travaille jusqu'au retour de son outil : un message livré juste après n'a rien
    fait attendre. Ouverte à la sortie qui a lancé l'outil, l'attente comptait la durée de
    l'outil — 16 min 48 s sur 368 attentes du mainteneur au relevé du 2026-10-14, et désormais
    aussi chaque message de pair livré après un outil.
    """
    tour = [
        assistant("09:00:00", (BASH_CALL, "Bash")),
        {
            "type": "user",
            "timestamp": at("09:05:00"),
            "message": {"content": [{"type": "tool_result", "tool_use_id": BASH_CALL}]},
        },
        said("09:05:01", PEER_MESSAGE),
        assistant("09:06:00"),
    ]
    events = bilan.read_events([write_transcript(tmp_path / "outil.jsonl", tour)])

    assert [bilan.total([window]) for window in bilan.measure(events).blocked] == [
        timedelta(seconds=1)
    ]


def test_l_attente_court_jusqu_au_dernier_message_avant_la_reprise(tmp_path: Path) -> None:
    """Deux messages avant que l'agent ne reprenne : l'attente court jusqu'au second.

    Le premier n'a rien déclenché — l'agent n'a rien rendu entre les deux, par exemple parce que
    la session tenait le message de pair pour approbation. Fermer au premier compterait en
    travail d'agent un temps où il n'a rien fait. Au relevé des attentes du 2026-10-14 à
    13:47 UTC, les deux règles ne diffèrent que sur 16 attentes, 34 min au total : c'est ce
    montage qui les départage.
    """
    tour = [
        assistant("09:00:00"),
        said("09:10:00", PEER_MESSAGE),
        said("09:30:00", "ok"),
        assistant("09:31:00"),
    ]
    events = bilan.read_events([write_transcript(tmp_path / "tour.jsonl", tour)])

    assert [bilan.total([window]) for window in bilan.measure(events).blocked] == [
        timedelta(minutes=30)
    ]


def test_un_relais_ouvert_par_un_pair_le_lendemain_est_une_absence(tmp_path: Path) -> None:
    """Le cas qui a révélé le défaut : le bilan du lot 1 de #23, trois transcripts fusionnés,
    rendait 242 h 30 d'agent seul contre 2 h 53 en sommant leurs sorties séparées. La première
    reprise s'ouvrait par un message de pair, la seconde par une commande tapée — deux formes que
    `waits` ne comptait pas : l'écart entre deux transcripts, une nuit puis dix jours, passait
    en travail d'agent. Ce montage rejoue la première.
    """
    veille = [said("20:00:00", "go"), assistant("20:10:00")]
    lendemain = [
        {**said("08:00:00", PEER_MESSAGE), "timestamp": "2026-09-28T08:00:00.000Z"},
        {**assistant("08:05:00"), "timestamp": "2026-09-28T08:05:00.000Z"},
    ]
    events = bilan.read_events(
        [
            write_transcript(tmp_path / "veille.jsonl", veille),
            write_transcript(tmp_path / "lendemain.jsonl", lendemain),
        ]
    )
    m = bilan.measure(events)

    assert bilan.total(m.absences) == timedelta(hours=11, minutes=50)
    assert m.alone == timedelta(minutes=15), "10 min la veille, 5 min le lendemain"


def test_une_balise_non_fermee_reste_un_message_du_mainteneur() -> None:
    """Un bloc qui ne se ferme pas n'est pas une injection délimitable.

    Recensé sur les 87 transcripts : **0 balise en tête non fermée** — le harnais ferme toujours
    ses blocs. La règle refuse donc de classer `system` ce qu'elle ne peut pas borner, plutôt
    que de deviner où finit le bloc et d'avaler le texte qui le suit.
    """
    assert bilan.classify("user", [{"type": "text", "text": "<ide_opened_file>tronqué"}]) == "human"


def test_une_suite_de_blocs_qui_echoue_ne_fait_pas_exploser_le_classement() -> None:
    """Le découpage d'un message en blocs doit être **unique**, sinon le motif est exponentiel.

    Avec un corps en `.*?`, chaque bloc peut se fermer sur n'importe quelle fermeture suivante :
    mesuré le 2026-10-10, 1,5 s à 24 blocs, 6,1 s à 26, 24 s à 28, 98 s à 30 — ×4 tous les deux
    blocs. Et les messages à plusieurs blocs sont ordinaires : 48 en portent deux ou trois. Le
    corps interdit donc sa propre fermeture, ce qui rend le découpage unique et le coût
    quasi linéaire. **Domicile du relevé**, mesuré le 2026-10-12 par `timeit` sur
    `INJECTED_BLOCKS.match("<a>x</a>" * n + "Z")`, le module chargé par `load_script` comme
    ci-dessus : **quelques millisecondes** pour n = 20 000 (160 000 octets), et de l'ordre de
    **×2 par doublement de n** entre 5 000 et 40 000 — jamais exponentielle.

    Pas de plage chiffrée ici, et c'est un choix mesuré : quatre relevés successifs sur deux
    postes ont déplacé la borne haute à chaque fois, et des bornes au dixième de milliseconde
    ont été dépassées dès qu'un relevé a allongé son nombre de runs. Une chronométrie n'est
    pas une population figée par un commit — contrairement au 302/1041 de
    `test_mutation.py` —, donc elle n'a pas de dénombrement opposable : seul l'**ordre de
    grandeur** l'est, et c'est lui qui porte la conclusion de conception. Ce qui **rougit** est
    la borne de 1 s ci-dessous, jamais ce relevé.

    **26 blocs, pas 2 000** : à 2 000 le motif ambigu ne rend jamais la main, et un test qui
    pend prive le relecteur du nom du test fautif — le harnais rend PANNE sur son propre délai
    au lieu de ROUGE sur ce test. À 26, la forme ambigue met 6 s contre une borne de 1 s : elle
    **échoue**, et se nomme.

    26 blocs suivis d'un caractère qui fait échouer : le cas le plus défavorable, puisque
    l'échec est ce qui force le moteur à tout réessayer. La borne est large à dessein — elle
    attrape une explosion, pas une lenteur de poste.
    """
    message = "<a>x</a>" * 26 + "z"
    started = time.monotonic()

    assert bilan.classify("user", [{"type": "text", "text": message}]) == "human"

    elapsed = time.monotonic() - started
    assert elapsed < 1, f"le découpage est ambigu : {elapsed:.2f} s pour 26 blocs"


def test_les_chiffres_du_rapport_sont_epingles_un_a_un(tmp_path: Path) -> None:
    """`Measures` existe pour rendre les chiffres assertables ; encore faut-il les asserter.

    Mesuré en relecture : **10 mutations sur 15** de `bilan-session.py` restaient vertes, dont la
    frontière de l'heure, la **première** notification `completed` — une décision verrouillée du
    critère 3 —, tout `token_usage`, le compte de relais et la fusion des intervalles jointifs.
    Le rapport n'était gardé que par des présences de sous-chaînes, qui épinglent la mise en page
    et aucun nombre.
    """
    events = read(tmp_path)
    m = bilan.measure(events)

    assert m.span == timedelta(hours=2, minutes=40)
    assert m.sessions == 2
    assert m.relayed == [datetime.fromisoformat(at("12:30:00"))]
    assert bilan.total(m.reactivity) == timedelta(minutes=15)
    assert bilan.total(m.absences) == timedelta(hours=1, minutes=54, seconds=30)
    assert bilan.total(m.blocked) == timedelta(hours=2, minutes=9, seconds=30)
    assert bilan.total(m.windows) == timedelta(minutes=19, seconds=30), (
        "le workflow est imbriqué dans la fenêtre de l'agent : l'union ne double pas"
    )
    assert m.alone == m.span - bilan.total(bilan.union(list(m.blocked) + list(m.windows)))
    assert m.launched == ["Agent", "Workflow"]
    assert m.workflows == 1, "le critère 4 exige un workflow dans le transcript synthétique"
    assert m.dangling == 0
    assert m.kinds["human"] == 4
    assert m.kinds["peer"] == 1
    assert m.kinds["system"] == 1
    assert m.questions == 0


def test_le_relais_se_date_par_le_temps_pas_par_l_ordre_des_arguments(tmp_path: Path) -> None:
    """Le skill autorise à donner les transcripts dans n'importe quel ordre.

    Mesuré : classés par index d'argument, l'ordre inverse annonçait « relais à 12:00 » — le
    début de la session — au lieu de 12:30. Le test d'ordre existant passait bien les chemins à
    l'envers, mais n'assérait que l'ordre des événements, pas l'heure rendue.
    """
    chronologique = bilan.read_events(
        [
            write_transcript(tmp_path / "session.jsonl", TIMELINE),
            write_transcript(tmp_path / "relais.jsonl", RELAY),
        ]
    )
    inverse = bilan.read_events(
        [tmp_path / "relais.jsonl", tmp_path / "session.jsonl"],
    )

    attendu = [datetime.fromisoformat(at("12:30:00"))]
    assert bilan.relays(chronologique) == attendu
    assert bilan.relays(inverse) == attendu


def test_mesurer_une_session_vide_leve_au_lieu_de_rendre_des_zeros(tmp_path: Path) -> None:
    """`events[0]` levait un `IndexError` : `measure` et `report` sont publics et appelés
    directement par cette suite, et seul `main` gardait le cas."""
    with pytest.raises(ValueError, match="aucun événement"):
        bilan.measure([])


def test_les_jetons_se_comptent_une_fois_par_message(tmp_path: Path) -> None:
    """Un message diffusé en plusieurs blocs occupe plusieurs lignes du même `id` et du même
    `usage` : une seule compte. Prémisse vérifiée sur les transcripts réels du projet —
    305 répétitions, **zéro** divergence — et le dédoublonnage y évite un facteur 3,2."""
    diffuse: list[dict[str, Any]] = [
        {
            "type": "assistant",
            "timestamp": at("10:00:00"),
            "message": {"id": "msg_1", "usage": {"output_tokens": 100}, "content": []},
        },
        {
            "type": "assistant",
            "timestamp": at("10:00:01"),
            "message": {"id": "msg_1", "usage": {"output_tokens": 100}, "content": []},
        },
        {
            "type": "assistant",
            "timestamp": at("10:00:02"),
            "message": {"id": "msg_2", "usage": {"output_tokens": 7}, "content": []},
        },
    ]

    usage = bilan.token_usage([write_transcript(tmp_path / "jetons.jsonl", diffuse)])

    assert usage.output == 107, "msg_1 compte une fois, pas deux"
    assert usage.transcripts == 1


QUESTION_CALL = "toolu_question0000000004"


def test_les_fenetres_de_question_formelle_comptent_comme_attente(tmp_path: Path) -> None:
    """Une question formelle est du temps passé à attendre le mainteneur, même sans message.

    Elle n'est bornée par aucun message humain — l'outil rend lui-même le résultat —, donc sans
    sa fenêtre explicite elle disparaît de l'attente et le pourcentage flatte la pipeline.
    """
    posee: list[dict[str, Any]] = [
        said("10:00:00", "démarre"),
        assistant("10:01:00", (QUESTION_CALL, "AskUserQuestion")),
        {
            "type": "user",
            "timestamp": at("10:06:00"),
            "message": {"content": [{"type": "tool_result", "tool_use_id": QUESTION_CALL}]},
        },
        assistant("10:07:00"),
    ]
    events = bilan.read_events([write_transcript(tmp_path / "question.jsonl", posee)])
    m = bilan.measure(events)

    assert m.questions == 1
    assert bilan.total(m.blocked) == timedelta(minutes=5)


def test_les_intervalles_jointifs_fusionnent() -> None:
    """Deux attentes qui se touchent sont une seule attente : sans la fusion, une absence de
    deux heures en deux morceaux jointifs passerait pour deux heures de réactivité."""
    debut = datetime.fromisoformat(at("10:00:00"))
    milieu = debut + timedelta(minutes=30)
    fin = debut + timedelta(minutes=90)

    assert bilan.union([(debut, milieu), (milieu, fin)]) == [(debut, fin)]
    assert bilan.split_waits([(debut, fin)])[1] == [(debut, fin)], "90 min est une absence"


def test_un_message_de_sous_agent_ne_compte_pas_dans_la_session(tmp_path: Path) -> None:
    """Les tours d'un sous-agent vivent dans le même fichier, marqués `isSidechain`.

    Les compter ferait du travail de l'agent des points de contact humains, et allongerait la
    session de tours que le mainteneur n'a jamais vus.
    """
    melange: list[dict[str, Any]] = [
        said("10:00:00", "démarre"),
        {**said("10:01:00", "un tour de sous-agent"), "isSidechain": True},
        assistant("10:02:00"),
    ]

    events = bilan.read_events([write_transcript(tmp_path / "melange.jsonl", melange)])

    assert len(events) == 2
    assert sum(1 for event in events if event.kind == "human") == 1


def test_une_attente_d_exactement_une_heure_est_une_absence() -> None:
    """La frontière est inclusive, et seul ce montage la distingue.

    L'absence du transcript synthétique fait 1 h 54 : `>` et `>=` y rendent le même résultat.
    Mesuré en relecture — relâcher la comparaison laissait la suite verte.
    """
    debut = datetime.fromisoformat(at("10:00:00"))
    pile = debut + timedelta(hours=1)
    juste_avant = debut + timedelta(minutes=59, seconds=59)

    assert bilan.split_waits([(debut, pile)]) == ([], [(debut, pile)])
    assert bilan.split_waits([(debut, juste_avant)]) == ([(debut, juste_avant)], [])


def test_plusieurs_blocs_enchaines_restent_un_message_injecte() -> None:
    """Le `+` du motif : un message du harnais porte souvent **plusieurs** blocs de suite.

    Dénombré le 2026-10-10 sur la même population : des messages à bloc en tête, **111 en
    portent un, 18 en portent deux, 30 en portent trois**. C'est là que vivent les deux familles
    qui n'arrivent jamais en tête — `<command-args>` et `<skill-format>` —, donc le `+` n'est pas
    de la largeur spéculative : il couvre 48 messages réels, et les deux formes ci-dessous sont
    recopiées de transcripts.

    Le bloc vide (`<command-args></command-args>`) est le cas limite du corps : zéro caractère.

    Les deux premières formes sont des commandes **tapées** : le motif les reconnaît comme des
    blocs, mais `classify` les rend `human` (`TYPED_COMMAND`). Le motif s'éprouve donc seul, et la
    classe sur la forme à trois blocs que le harnais injecte quand il charge un skill de lui-même.
    """
    deux = (
        "<command-message>i-have-adhd</command-message>\n<command-name>/i-have-adhd</command-name>"
    )
    trois = (
        "<command-name>/mcp</command-name>\n<command-message>mcp</command-message>\n"
        "<command-args></command-args>"
    )
    charge_par_le_harnais = FORMES_REELLES["skill chargé par le harnais"][0]

    assert bilan.INJECTED_BLOCKS.match(deux)
    assert bilan.INJECTED_BLOCKS.match(trois)
    assert not bilan.INJECTED_BLOCKS.match(trois + "et vas-y")
    assert bilan.classify("user", [{"type": "text", "text": charge_par_le_harnais}]) == "system"


# --- Ce que chaque sous-agent a consommé, contact par contact (#77, lot 4c) --------------------


def api_call(clock: str, message: str, read: int, written: int, output: int) -> dict[str, Any]:
    """Un appel d'API d'un sous-agent : un enregistrement `assistant` porteur de son `usage`.

    `input_tokens` vaut 2, l'ordre de grandeur réel d'une entrée hors cache.
    """
    usage = {
        "input_tokens": 2,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": written,
        "output_tokens": output,
    }
    return {
        "type": "assistant",
        "timestamp": at(clock),
        "message": {"id": message, "content": [], "usage": usage},
    }


# Un relecteur lancé en fond par `AGENT_CALL`, puis repris par `SendMessage`. Deux pièges : un
# même message diffusé sur deux lignes (`msg_a`), et une relance du harnais qui n'est **pas** un
# contact — seul le coordinateur en ouvre un.
RELECTEUR: list[dict[str, Any]] = [
    said("10:00:30", "Première passe de relecture 4.2 — PR #89"),
    said("10:00:31", "<system-reminder>Your final report is delivered…</system-reminder>"),
    api_call("10:01:00", "msg_a", 0, 20_000, 10),
    api_call("10:01:01", "msg_a", 0, 20_000, 10),
    api_call("10:19:00", "msg_b", 20_000, 5_000, 900),
    said("10:19:30", "[Your previous response had no visible output. Please continue.]"),
    api_call("10:20:00", "msg_c", 25_000, 1_000, 50),
    said("11:00:00", "The coordinator sent a message while you were working: Seconde passe"),
    api_call("11:00:10", "msg_d", 26_000, 3_000, 200),
    api_call("11:05:00", "msg_e", 29_000, 500, 400),
]
RELECTEUR_META = {
    "agentType": "relecteur",
    "name": "relecteur-p1",
    "description": "Relecture 4.2, passe 1",
    "toolUseId": AGENT_CALL,
    "requestShape": "background",
}


def write_subagent(
    session: Path, stem: str, records: list[dict[str, Any]], meta: dict[str, Any]
) -> None:
    """Range un transcript de sous-agent là où le harnais le range : `<session>/subagents/`, et
    un cran plus bas pour un agent de workflow (`stem` = `workflows/<id>/agent-…`)."""
    target = session.with_suffix("") / "subagents" / f"{stem}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_transcript(target, records)
    target.with_name(target.stem + ".meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_un_agent_de_workflow_se_lit_un_cran_plus_bas_et_le_journal_du_workflow_non(
    tmp_path: Path,
) -> None:
    """Le harnais range les agents d'un workflow sous `subagents/workflows/<id>/`, à côté d'un
    `journal.jsonl` qui n'est pas un transcript d'agent. Recensé le 2026-10-14 à 09 h 36 par la
    relecture de la PR #89 (population vivante) : 57 des 91 transcripts de sous-agents du projet
    sont à ce niveau, sans `toolUseId` dans leur meta ; 9 journaux de workflow, sans horodatage,
    entreraient sinon comme des agents à zéro contact."""
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    write_subagent(
        session,
        "workflows/wf_1/agent-a3",
        [said("10:05:10", "obs 25-37"), api_call("10:09:00", "msg_w", 0, 4_000, 70)],
        {"agentType": "general-purpose", "description": "obs 25-37"},
    )
    write_transcript(
        session.with_suffix("") / "subagents" / "workflows" / "wf_1" / "journal.jsonl",
        [{"type": "launched"}],
    )

    assert [(agent.name, agent.launcher) for agent in bilan.subagents([session])] == [
        ("obs 25-37", "")
    ]


def test_un_sous_agent_se_mesure_contact_par_contact_dans_son_transcript(tmp_path: Path) -> None:
    """La consommation se lit dans les `usage` du transcript du sous-agent, pas dans sa
    notification de fin : celle-ci porte le **contexte** en fin de contact (mesuré au lot 4a :
    72 099 notifiés, 68 613 de contexte final), et ne voit que le premier contact d'un agent
    repris.

    Un contact s'ouvre au lancement, puis à chaque message du coordinateur. Forme mesurée le
    2026-10-14 à 09 h sur les transcripts de sous-agents du projet, **population vivante** :
    14 reprises sur 12 transcripts, toutes « The coordinator sent a message while you were
    working: », y compris pour un agent qui avait fini — chacune après un dernier tour sans
    appel d'outil.
    """
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    write_subagent(session, "agent-a1", RELECTEUR, RELECTEUR_META)

    [agent] = bilan.subagents([session])

    assert (agent.role, agent.name, agent.launcher) == (
        "relecteur",
        "Relecture 4.2, passe 1",
        AGENT_CALL,
    )
    assert [
        (c.calls, c.context, c.used.cache_read, c.used.cache_write) for c in agent.contacts
    ] == [
        (3, 2 + 25_000 + 1_000, 45_000, 26_000),
        (2, 2 + 29_000 + 500, 55_000, 3_500),
    ], "msg_a compte une fois ; la relance du harnais n'ouvre pas de contact"
    assert [bilan.total([c.window]) for c in agent.contacts] == [
        timedelta(minutes=19, seconds=30),
        timedelta(minutes=5),
    ]


def test_les_sous_agents_se_rendent_dans_l_ordre_du_temps(tmp_path: Path) -> None:
    """Le harnais nomme un transcript de sous-agent par un identifiant aléatoire : rangés par
    nom, la seconde passe d'une relecture sortait avant la première (mesuré sur la session de
    la PR #75)."""
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    write_subagent(
        session, "agent-a0", [said("11:30:00", "Seconde passe")], {"description": "passe 2"}
    )
    write_subagent(session, "agent-a9", RELECTEUR, {"description": "passe 1"})

    assert [agent.name for agent in bilan.subagents([session])] == ["passe 1", "passe 2"]


def delivered_as_text(clock: str, call: str, task: str) -> dict[str, Any]:
    """La seconde forme de livraison : un message `user` dont le texte nu **est** la notification."""
    body = notification(clock, call, task)["attachment"]["prompt"]
    return {"type": "user", "timestamp": at(clock), "message": {"role": "user", "content": body}}


# Les formes sous lesquelles le harnais **livre** une notification de fin `completed`, recensées
# le 2026-10-14 à 09 h 14 sur les 67 transcripts de session du projet (58 247 lignes lues,
# population vivante) : 70 pièces jointes `queued_command` et 43 messages `user` en texte nu qui
# commencent par la balise — dont 10 fins de workflow. Le script ne lisait que la première : le
# bilan de la session de revue du journal (#77) annonçait « workflows 0 / 1 » et un
# lancement « sans notification de fin ». Écartés à dessein : les `queue-operation` (la file du
# harnais, pas une livraison — `enqueue` 137, `remove` 94) et les 12 messages en blocs (9 `user`,
# 3 `assistant`) qui **citent** une notification sans commencer par elle. Deux formes recensées,
# une lue.
FORMES_DE_LIVRAISON = {
    "pièce jointe queued_command": notification,
    "message user en texte nu": delivered_as_text,
}


@pytest.mark.parametrize("deliver", FORMES_DE_LIVRAISON.values(), ids=FORMES_DE_LIVRAISON.keys())
def test_chaque_forme_de_livraison_ferme_la_fenetre_de_son_appel(
    tmp_path: Path, deliver: Any
) -> None:
    """Un workflow notifié sous l'une ou l'autre forme a sa fenêtre, et n'est pas un lancement
    perdu. Le message de 09:03 **cite** une notification complète sans commencer par elle : la
    fenêtre se fermerait là si une citation livrait."""
    cite = delivered_as_text("09:03:00", WORKFLOW_CALL, "wu6toltz4")
    cite["message"]["content"] = (
        "regarde ce que le harnais m'a envoyé : " + cite["message"]["content"]
    )
    transcript = [
        said("09:00:00", "lance la revue"),
        assistant("09:00:10", (WORKFLOW_CALL, "Workflow")),
        cite,
        deliver("09:06:10", WORKFLOW_CALL, "wu6toltz4"),
        assistant("09:06:20"),
    ]
    events = bilan.read_events([write_transcript(tmp_path / "revue.jsonl", transcript)])
    m = bilan.measure(events)

    assert m.windows == [
        (datetime.fromisoformat(at("09:00:10")), datetime.fromisoformat(at("09:06:10")))
    ]
    assert m.dangling == 0


VERIF_CALL = "toolu_verif000000000000005"


def test_un_agent_au_premier_plan_et_une_reprise_comptent_dans_le_temps_des_sous_agents(
    tmp_path: Path,
) -> None:
    """Deux fenêtres que les notifications ne voyaient pas. Un agent lancé **au premier plan**
    n'émet aucune notification de fin : il était compté « sans notification de fin (encore en
    cours, ou morts) » — le vérificateur du lot 4b, 2 min 47, faisait exactement ce « 1 ». Et la
    **reprise** d'un agent de fond n'a pas de notification de son lancement : seul le premier
    contact entrait dans le temps des sous-agents (0 h 05 lus au lot 4b, ~12 min réels). Mesuré
    le 2026-10-14 sur les 12 agents repris du corpus (2 ou 3 contacts chacun, population
    vivante) : 10 n'ont qu'**une** notification `completed` portant leur appel lanceur, 2 n'en
    ont aucune.

    Le compte des lancements est la troisième garde. Un sous-agent entre au rapport par **5
    chemins** — fenêtres, lancements perdus, lignes par agent, jetons des sous-agents, compte des
    lancements —, recensés avant le correctif : **1 fuyait**, ce compte, seul à lire encore les
    notifications (« workflows 0 / 0 » avec un relecteur au premier plan listé deux lignes plus
    bas, relecture de la PR #89, passe 1).
    """
    session = write_transcript(
        tmp_path / "session.jsonl",
        [
            *TIMELINE,
            assistant("12:00:30", (VERIF_CALL, "Agent")),
            {
                "type": "user",
                "timestamp": at("12:03:00"),
                "message": {"content": [{"type": "tool_result", "tool_use_id": VERIF_CALL}]},
            },
            assistant("12:03:10"),
        ],
    )
    write_subagent(session, "agent-a1", RELECTEUR, RELECTEUR_META)
    write_subagent(
        session,
        "agent-a2",
        [
            said("12:00:31", "Vérification d'avant-go de la PR #89"),
            api_call("12:02:50", "msg_v", 10_000, 500, 300),
        ],
        {"agentType": "verificateur", "toolUseId": VERIF_CALL, "requestShape": "foreground"},
    )

    events, agents = bilan.read_events([session]), bilan.subagents([session])
    m = bilan.measure(events, agents)

    assert m.dangling == 0, "le vérificateur a un transcript : il n'est ni en cours ni mort"
    assert bilan.total(m.windows) == timedelta(minutes=19, seconds=30) + timedelta(
        minutes=5
    ) + timedelta(minutes=2, seconds=19), "premier contact, reprise, et vérificateur"
    assert "(3 lancés, dont 1 workflows)" in bilan.report(events, bilan.Usage(), agents)


def test_une_absence_reste_une_absence_quand_un_sous_agent_y_travaille(tmp_path: Path) -> None:
    """Une attente se classe sur sa durée **brute**, puis perd le temps des sous-agents. Dans
    l'ordre inverse, la reprise du relecteur (11:00 → 11:05) coupait l'absence de 10:35:30 à
    12:00 en deux morceaux de moins d'une heure, reclassés en réactivité : 1 h 19 de réactivité
    en plus, et plus d'absence du tout — le sens d'erreur d'obs 43 (relevé par `/code-review`
    sur la PR #89).

    **Cas synthétique**, et la forme réelle est plus étroite : une reprise passe par un
    `SendMessage`, donc un tour de la session, qui coupe l'attente — une fenêtre de sous-agent ne
    recouvre une attente qu'à partir de son début (agent lancé juste avant une absence), et
    seulement si sa fin ne réveille pas la session — agent mort, ou contact repris sans
    notification `completed` de son lancement. Le défaut y vit pareil, **non observé** : une
    absence de 1 h 05 dont un tel agent ronge les 10 premières minutes passait en réactivité. Le montage le pousse à l'extrême pour que les deux classements
    divergent sans ambiguïté."""
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    write_subagent(session, "agent-a1", RELECTEUR, RELECTEUR_META)

    m = bilan.measure(bilan.read_events([session]), bilan.subagents([session]))

    assert bilan.total(m.reactivity) == timedelta(minutes=15)
    assert bilan.total(m.absences) == timedelta(hours=1, minutes=19, seconds=30)


def test_le_rapport_rend_chaque_contact_avec_sa_consommation(tmp_path: Path) -> None:
    """Une ligne par contact, sous le nom de son agent : c'est le coût **par contact** que les
    lots se comparent — un total dépend de la taille du delta relu (journal de spec de #77,
    2026-10-13). Et les jetons des sous-agents sont la somme de ces contacts, pas un second
    parcours des fichiers qui pourrait ne pas tomber juste.
    """
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    write_subagent(session, "agent-a1", RELECTEUR, RELECTEUR_META)
    agents = bilan.subagents([session])

    lines = bilan.report(bilan.read_events([session]), bilan.Usage(), agents).splitlines()

    titre = lines.index("  relecteur « Relecture 4.2, passe 1 » — 2 contacts")
    premier, reprise = lines[titre + 1], lines[titre + 2]
    for attendu in ("0 h 19", "3 appels", *map(bilan.thousands, (26_002, 45_000, 26_000))):
        assert attendu in premier, f"{attendu!r} manque au premier contact : {premier}"
    for attendu in ("0 h 05", "2 appels", *map(bilan.thousands, (29_502, 55_000, 3_500))):
        assert attendu in reprise, f"{attendu!r} manque à la reprise : {reprise}"
    assert bilan.consumed(agents) == bilan.Usage(
        cache_read=45_000 + 55_000, cache_write=26_000 + 3_500, transcripts=1
    )


def test_la_sortie_d_un_sous_agent_ne_se_rend_pas(tmp_path: Path) -> None:
    """Dans un transcript de sous-agent, une partie des messages porte un `output_tokens` figé
    bien en dessous de ce qu'ils contiennent : mesuré le 2026-10-14 vers 10 h, 5 à 33 messages
    par agent sur 10 examinés — 238 notés pour ~7 500 produits au vérificateur de la PR #86 —,
    quasi aucun dans les transcripts de session (0 sur 436 à ce relevé ; 1 sur 6 904 sur toute
    la population, mesuré par la relecture de la PR #90 à 10 h 38, contre 414 sur 4 179 côté
    sous-agents). Un chiffre plausible et faux se lit comme une mesure : la sortie d'un
    sous-agent ne se rend donc pas, ni par contact ni au total, et le total le dit. Celle de la
    session, juste à l'arrondi près, reste."""
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    write_subagent(session, "agent-a1", RELECTEUR, RELECTEUR_META)
    agents = bilan.subagents([session])

    lines = bilan.report(
        bilan.read_events([session]), bilan.Usage(output=5_000), agents
    ).splitlines()

    titre = lines.index("  relecteur « Relecture 4.2, passe 1 » — 2 contacts")
    for contact in lines[titre + 1 : titre + 3]:
        assert "sortie" not in contact, contact
    total = next(line for line in lines if line.startswith("jetons des sous-agents"))
    assert "sortie non mesurée" in total, total
    assert total.count("sortie") == 1, f"un chiffre de sortie à côté de la mention : {total}"
    session_line = next(line for line in lines if line.startswith("jetons de la session"))
    assert bilan.tokens(bilan.Usage(output=5_000)) in session_line, session_line


# --- Un transcript demandé qui n'existe plus (obs 73) --------------------------------------------


def run_main(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, str]:
    """Lance `main` sur une console cp1252, celle du poste, et rend son code et sa sortie.

    Un rapport plein de `→` mourait sur cette console ; `sys.stdout` est donc un flux texte cp1252
    sur un tampon d'octets, que le script doit contourner en écrivant de l'UTF-8 sur le tampon —
    sans l'envelopper : un `TextIOWrapper` collecté ferme le flux qu'il enveloppe (même mécanisme
    que `test_les_verdicts_s_impriment_sur_une_console_cp1252` de `test_mutation.py`).
    """
    tampon = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(tampon, encoding="cp1252"))
    code = bilan.main(argv)
    return code, tampon.getvalue().decode("utf-8")


def test_un_transcript_absent_se_dit_au_lieu_d_un_bilan_partiel_muet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le transcript d'une session relayée peut disparaître avant l'Étape 8 : le harnais l'a
    libéré 50 minutes avant que le relais ne commence (obs 73). Ceux des lots 4a et 4b de #77
    n'étaient déjà plus là le 2026-10-14 au matin — mesuré : aucun transcript du projet n'a
    d'horodatage entre 00:34 et 08:54, et quatre marqueurs `.desktop-released.json` datent de
    08:40 à 08:52. Le script plantait alors sur `FileNotFoundError` ; le chemin retiré, il rendait
    un bilan normal sur la moitié du cycle. Il doit le **dire**, et renvoyer au relevé que la
    session sortante a déposé."""
    present = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    absent = tmp_path / "libere.jsonl"

    code, sortie = run_main([str(absent), str(present)], monkeypatch)

    assert code == 0
    assert f"transcripts demandés 2, lus 1 — absents : {absent}" in sortie
    assert "(sessions : 1)" in sortie, "le bilan porte sur le seul transcript lu"
    assert "relevé déposé" in sortie, "le remède se lit à côté du constat"


def test_main_rend_le_releve_des_sous_agents_de_la_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le point d'entrée passe au rapport les sous-agents rangés à côté du transcript : sans ce
    branchement, la suite restait verte sur un `main` qui n'en rendait aucun (mutation jouée
    par la relecture de la PR #89, passe 1)."""
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    write_subagent(session, "agent-a1", RELECTEUR, RELECTEUR_META)

    code, sortie = run_main([str(session)], monkeypatch)

    assert code == 0
    assert "  relecteur « Relecture 4.2, passe 1 » — 2 contacts" in sortie


def test_aucun_transcript_lisible_ne_rend_pas_de_bilan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zéro transcript présent : pas de bilan du tout, et la liste de ce qui manque."""
    absent = tmp_path / "libere.jsonl"

    code, sortie = run_main([str(absent)], monkeypatch)

    assert code == 1
    assert f"absents : {absent}" in sortie
    assert "bilan partiel" not in sortie, "aucun bilan n'est rendu (relevé par `/code-review`)"


# --- Le profil de contexte de chaque transcript de session (#134, lot 5) ------------------------


def test_le_profil_compte_les_appels_le_contexte_initial_et_le_cache_lu_par_quart(
    tmp_path: Path,
) -> None:
    """Huit appels, dont un message diffusé sur deux lignes au même `id` — un seul appel, à sa
    place de première apparition — et un appel de sous-agent resté dans le transcript de session
    (`isSidechain`), écarté comme dans `read_events`. Les quarts tombent juste : 8 appels, 2 par
    quart."""
    lus = [100_000, 300_000, 500_000, 700_000, 900_000, 1_100_000, 2_000_000, 4_000_000]
    appels = [api_call(f"10:0{i}:00", f"msg_{i}", lu, 1_000, 10) for i, lu in enumerate(lus)]
    sous_agent = {**api_call("10:03:30", "msg_side", 9_000_000, 0, 10), "isSidechain": True}
    session = write_transcript(
        tmp_path / "session.jsonl",
        [said("09:59:00", "démarre"), *appels[:4], appels[3], sous_agent, *appels[4:]],
    )

    profil = bilan.context_profile(session)

    assert profil.calls == 8, "msg_3 compte une fois, l'appel du sous-agent pas du tout"
    assert profil.context == 2 + 100_000 + 1_000
    assert profil.quarters == [200_000, 600_000, 1_000_000, 3_000_000]


def test_les_bornes_des_quarts_s_arrondissent_par_le_bas() -> None:
    """Cinq appels ne se divisent pas par quatre : chaque borne `n·k//4` s'arrondit vers le bas,
    et le dernier quart prend le reste. Relevé par la passe 1 de relecture de la PR #146 : avec
    les seuls montages à 8 et 4 appels, l'arrondi supérieur restait VERT."""
    profil = bilan.Profile(
        name="session",
        reads=[100, 200, 300, 400, 500],
        context=0,
        gate=None,
        composition=bilan.Composition(),
    )

    assert profil.quarters == [100, 200, 300, 450]


def carrying(record: dict[str, Any], *blocks: dict[str, Any]) -> dict[str, Any]:
    """`record` — un appel d'API ou un message `user` —, porteur de ces blocs de contenu."""
    record["message"]["content"] = list(blocks)
    return record


def uses(
    clock: str, message: str, read: int, tool: str, given: dict[str, Any], uid: str
) -> dict[str, Any]:
    """Un appel d'API qui lance un outil : `api_call` porteur d'un bloc `tool_use`."""
    return carrying(
        api_call(clock, message, read, 0, 10),
        {"type": "tool_use", "id": uid, "name": tool, "input": given},
    )


def returned(clock: str, uid: str, content: str | list[dict[str, Any]]) -> dict[str, Any]:
    """Le retour d'un outil dans le rôle `user` — un texte, ou une liste de blocs."""
    return {
        "type": "user",
        "timestamp": at(clock),
        "message": {"content": [{"type": "tool_result", "tool_use_id": uid, "content": content}]},
    }


# La session de relecture que la session PR démarre, le titre qu'elle lui donne, et la
# parenthèse des adresses que porte le retour de son démarrage.
SESSION_DE_RELECTURE = "local_f6942c91-c0c7-4230-91c5-23af96ea3e16"
TITRE = "Relecture de la PR #142 (#134 lot 4a)"
PARENTHESE = f"(session_id: {SESSION_DE_RELECTURE}, name: relecture-pr-142)"


def demarrage(titre: str, parenthese: str = PARENTHESE) -> list[dict[str, Any]]:
    """L'appel 2 d'une session, qui démarre sa session de relecture sous `titre`, puis le retour
    de ce démarrage — sa forme réelle, relevée sur le transcript de la session PR du lot 4a de
    #134 : une liste d'un bloc `text`, le titre entre guillemets puis la `parenthese` des
    adresses, la dernière du retour — sa suite, « It runs on its own; … », n'en porte pas."""
    texte = f'Started session "{titre}" {parenthese}. It runs on its own; …'
    return [
        uses("10:01:00", "msg_2", 100, "mcp__ccd_session__start_session", {}, "toolu_start"),
        returned("10:01:05", "toolu_start", [{"type": "text", "text": texte}]),
    ]


# Chaque forme de porte, en littéraux, sous son libellé rendu : la ligne de `REVIEW_GATES` qu'elle
# éprouve — outil, champ de son `input`, valeur —, et l'`input` du `tool_use` qui la porte.
PORTES: dict[str, tuple[tuple[str, str, str], dict[str, Any]]] = {
    "Skill code-review": (("Skill", "skill", "code-review"), {"skill": "code-review"}),
    "Skill security-review": (("Skill", "skill", "security-review"), {"skill": "security-review"}),
    "Agent relecteur": (
        ("Agent", "subagent_type", "relecteur"),
        {"subagent_type": "relecteur", "prompt": "relis"},
    ),
    "SendMessage → session démarrée": (
        ("SendMessage", "to", "→ session démarrée"),
        {"to": SESSION_DE_RELECTURE, "message": "passe 1"},
    ),
}

# Ce qui ne doit pas mordre : un autre skill, un autre rôle, et un message à une session que ce
# transcript n'a pas démarrée — par son identifiant, celui de la coordinatrice du lot 4a au même
# relevé, par un nom, ou par ce nom suivi d'une référence.
TEMOINS: dict[str, tuple[str, dict[str, Any]]] = {
    "Skill ponytail": ("Skill", {"skill": "ponytail"}),
    "Agent developpeur": ("Agent", {"subagent_type": "developpeur"}),
    "SendMessage → session non démarrée ici": (
        "SendMessage",
        {"to": "local_d82a6420-3661-48a5-b7e5-11dacbbe2053"},
    ),
    "SendMessage → nom d'une session non démarrée ici": ("SendMessage", {"to": "coordinatrice"}),
    "SendMessage → même nom suivi d'une référence": (
        "SendMessage",
        {"to": "coordinatrice [3fa9c1]"},
    ),
    # L'entrée d'un outil est écrite par le modèle : un destinataire mal formé reste dans le
    # transcript, et ne doit ni mordre ni faire tomber le bilan.
    "SendMessage → destinataire qui n'est pas une chaîne": (
        "SendMessage",
        {"to": [SESSION_DE_RELECTURE]},
    ),
}


def gated(
    tmp_path: Path,
    tool: str,
    given: dict[str, Any],
    titre: str = TITRE,
    parenthese: str = PARENTHESE,
) -> Any:
    """Le profil d'une session qui démarre sa session de relecture sous `titre` à l'appel 2, puis
    lance `tool` à l'appel 4 — cinquième enregistrement, après le retour du démarrage."""
    return bilan.context_profile(
        write_transcript(
            tmp_path / "session.jsonl",
            [
                api_call("10:00:00", "msg_1", 100, 0, 10),
                *demarrage(titre, parenthese),
                api_call("10:02:00", "msg_3", 100, 0, 10),
                uses("10:03:00", "msg_4", 100, tool, given, "toolu_candidat000000000002"),
                api_call("10:04:00", "msg_5", 100, 0, 10),
            ],
        )
    )


@pytest.mark.parametrize(("label", "case"), PORTES.items(), ids=PORTES.keys())
def test_chaque_forme_de_porte_de_relecture_se_trouve_a_son_appel(
    tmp_path: Path, label: str, case: tuple[tuple[str, str, str], dict[str, Any]]
) -> None:
    """L'indice est le rang de l'appel qui porte le bloc, pas celui de l'enregistrement."""
    (tool, _, _), given = case

    assert gated(tmp_path, tool, given).gate == (4, label)


# Les formes d'adresse de la session que `gated` démarre, en littéraux.
ADRESSES: dict[str, str] = {
    "identifiant": "local_f6942c91-c0c7-4230-91c5-23af96ea3e16",
    "nom": "relecture-pr-142",
    "nom-et-reference": "relecture-pr-142 [3fa9c1]",
}


@pytest.mark.parametrize("adresse", ADRESSES.values(), ids=ADRESSES.keys())
def test_une_session_demarree_mord_sous_chacune_de_ses_formes_d_adresse(
    tmp_path: Path, adresse: str
) -> None:
    """`SendMessage` adresse une session par son identifiant, par son nom, ou par son nom suivi
    de ` [<ref>]` quand il est ambigu — doc de l'outil : « Teammate by name », « worker
    [3fa9c1] » —, et le retour de `start_session` porte l'identifiant et le nom (`demarrage`).
    Dénombrement, écrit avant le correctif : 3 formes recensées, 2 fuyaient — le nom, et le nom
    suivi de sa référence."""
    assert gated(tmp_path, "SendMessage", {"to": adresse}).gate == (
        4,
        "SendMessage → session démarrée",
    )


# Un titre est libre : ce qu'il porte n'est pas une adresse. Chaque forme, en littéraux.
TITRES_PIEGES: dict[str, str] = {
    "mot-name": "Relecture name: slug",
    "mot-session-id": "Relecture session_id: slug",
    "parenthese-entiere": "Relecture (session_id: slug, name: slug)",
    # Une parenthèse d'adresses depuis que le nom y est optionnel : la dernière l'emporte.
    "parenthese-sans-nom": "Relecture (session_id: slug)",
}


@pytest.mark.parametrize("titre", TITRES_PIEGES.values(), ids=TITRES_PIEGES.keys())
def test_un_titre_de_session_ne_fait_pas_d_adresse(tmp_path: Path, titre: str) -> None:
    """`SESSION_ADDRESS` cherchait `name: ` et `session_id: ` dans tout le retour de
    `start_session`, titre entre guillemets compris : un titre « … name: slug » ajoutait
    l'adresse `slug`. Dénombrement, écrit avant le correctif : 3 formes de titre recensées — le
    mot `name: `, le mot `session_id: `, la parenthèse entière —, 3 fuyaient. Les adresses se
    lisent dans la dernière parenthèse du retour, que le titre précède (`demarrage`)."""
    assert gated(tmp_path, "SendMessage", {"to": "slug"}, titre).gate is None
    for adresse in (ADRESSES["identifiant"], ADRESSES["nom"]):
        porte = gated(tmp_path, "SendMessage", {"to": adresse}, titre).gate
        assert porte == (4, "SendMessage → session démarrée"), adresse


# La parenthèse des adresses sous chaque forme de nom, en littéraux, et les adresses qui doivent
# y mordre — l'identifiant toujours.
NOMS: dict[str, tuple[str, tuple[str, ...]]] = {
    "sans-nom": ("(session_id: local_a)", ("local_a",)),
    "nom-a-point": (
        "(session_id: local_a, name: relecture.pr.142)",
        ("local_a", "relecture.pr.142"),
    ),
    "nom-a-espace": ("(session_id: local_a, name: relecture pr)", ("local_a",)),
    "nom-vide": ("(session_id: local_a, name: )", ("local_a",)),
}


@pytest.mark.parametrize(("parenthese", "adresses"), NOMS.values(), ids=NOMS.keys())
def test_une_session_demarree_mord_par_son_identifiant_quel_que_soit_son_nom(
    tmp_path: Path, parenthese: str, adresses: tuple[str, ...]
) -> None:
    """La forme de `bedb2b9` exigeait un nom de lettres, chiffres, soulignés et tirets : sans nom,
    ou avec tout autre caractère, la parenthèse ne rendait rien, et la porte adressée par
    l'identifiant ne mordait plus. Dénombrement, écrit avant le correctif : 4 formes recensées —
    sans nom, nom à point, nom à espace, nom vide —, 4 fuyaient. L'identifiant est obligatoire,
    le nom optionnel et lu jusqu'à la parenthèse fermante."""
    for adresse in adresses:
        porte = gated(tmp_path, "SendMessage", {"to": adresse}, parenthese=parenthese).gate
        assert porte == (4, "SendMessage → session démarrée"), adresse


@pytest.mark.parametrize(("tool", "given"), TEMOINS.values(), ids=TEMOINS.keys())
def test_un_outil_qui_n_est_pas_une_porte_de_relecture_ne_mord_pas(
    tmp_path: Path, tool: str, given: dict[str, Any]
) -> None:
    assert gated(tmp_path, tool, given).gate is None


def test_la_table_des_portes_du_script_est_celle_des_cas() -> None:
    """L'autre sens (`cycle-pr` 3.1, dernier cas) : une forme ajoutée au script sans son cas."""
    assert set(bilan.REVIEW_GATES) == {forme for forme, _ in PORTES.values()}


def test_un_message_a_une_session_avant_son_demarrage_ne_mord_pas(tmp_path: Path) -> None:
    """La session doit avoir été démarrée **plus haut** : un message qui précède le retour de
    son démarrage ne s'adresse pas encore à la session de relecture de ce transcript."""
    session = write_transcript(
        tmp_path / "session.jsonl",
        [
            uses(
                "10:00:00", "msg_1", 100, "SendMessage", {"to": SESSION_DE_RELECTURE}, "toolu_tot"
            ),
            *demarrage(TITRE),
        ],
    )

    assert bilan.context_profile(session).gate is None


def around(tmp_path: Path, second: dict[str, Any]) -> Any:
    """Le profil de quatre appels — 100 000, 50 000, 150 000 et 300 000 lus —, dont le deuxième
    est `second`."""
    return bilan.context_profile(
        write_transcript(
            tmp_path / "session.jsonl",
            [
                api_call("10:00:00", "msg_1", 100_000, 0, 10),
                second,
                api_call("10:02:00", "msg_3", 150_000, 0, 10),
                api_call("10:03:00", "msg_4", 300_000, 0, 10),
            ],
        )
    )


def test_la_part_du_cache_lu_apres_la_porte_exclut_l_appel_de_la_porte(tmp_path: Path) -> None:
    porte = uses("10:01:00", "msg_2", 50_000, "Skill", {"skill": "code-review"}, "toolu_cr")

    assert around(tmp_path, porte).after_gate == (150_000 + 300_000) / 600_000


def test_une_session_sans_porte_de_relecture_le_dit_sans_part(tmp_path: Path) -> None:
    profil = around(tmp_path, api_call("10:01:00", "msg_2", 50_000, 0, 10))

    assert profil.after_gate is None
    assert "  première porte de relecture : aucune" in bilan.profile_lines(profil)


def test_la_section_de_profil_rend_ses_grandeurs_ligne_a_ligne(tmp_path: Path) -> None:
    """La mise en page, une fois : quarts en milliers arrondis, contexte groupé par milliers,
    part en pourcentage entier."""
    porte = uses("10:01:00", "msg_2", 50_000, "Skill", {"skill": "code-review"}, "toolu_cr")

    assert bilan.profile_lines(around(tmp_path, porte)) == [
        "profil de contexte — session",
        (
            f"  appels 4 · contexte au 1er appel {bilan.thousands(100_002)}"
            " · cache lu moyen par quart 100 → 50 → 150 → 300 K"
        ),
        "  première porte de relecture : appel 2 (Skill code-review) · cache lu après elle 75 %",
        (
            "  composition (caractères) : résultats d'outils 0 K · réflexion 0 K"
            " · arguments d'outils 0 K dont édition 0 K · skills chargés 0 K · texte 0 K"
        ),
    ]


def test_la_composition_compte_chaque_bloc_dans_sa_categorie(tmp_path: Path) -> None:
    """Chaque ligne porte ses propres blocs — deux messages diffusés sur plusieurs lignes au même
    `id` comptent tous leurs blocs. Relevé le 2026-10-21 à 20 h sur les transcripts de la session
    PR et de la session de relecture du lot 4a de #134, population vivante : 154 messages sur 229
    diffusés sur plusieurs lignes, aucun des 430 blocs répété dans son message — compter chaque
    ligne ne compte donc rien deux fois. Les arguments d'outils se comptent sans échappement ASCII :
    `{"old_string": "é", "new_string": "è"}` fait 38 caractères, 48 échappés. Un skill ne se
    charge que dans le rôle `user` : l'agent qui cite la phrase écrit du texte. Un retour dont le
    transcript ne porte pas l'appel se range sous « ? ». Une image dans un retour d'outil, une
    pièce jointe, une copie de requête et un message de sous-agent ne comptent pas — la copie de
    requête, `api-request-blob`, porte un `message` `user`, `system` ou `assistant`, sans `usage`
    ni horodatage : c'est le type de l'enregistrement qui l'écarte, pas le rôle de son message.
    Relevé le 2026-10-21 à 21 h sur les mêmes transcripts : 15, 132 et 10 dans la session PR, 8, 75
    et 7 dans la session de relecture."""
    session = write_transcript(
        tmp_path / "session.jsonl",
        [
            carrying(
                api_call("10:00:00", "msg_1", 0, 0, 10),
                {"type": "thinking", "thinking": "abc", "signature": "sig12"},
            ),
            carrying(
                api_call("10:00:01", "msg_1", 0, 0, 10),
                {"type": "redacted_thinking", "data": "xxxxxx"},
                {"type": "text", "text": "bonjour"},
                {"type": "text", "text": "Base directory for this skill: cité"},
            ),
            uses("10:01:00", "msg_2", 0, "Read", {"file_path": "a.py"}, "toolu_read"),
            uses(
                "10:01:01", "msg_2", 0, "Edit", {"old_string": "é", "new_string": "è"}, "toolu_edit"
            ),
            uses("10:01:02", "msg_2", 0, "Bash", {"command": "ls"}, "toolu_bash"),
            returned("10:01:10", "toolu_read", "x" * 40),
            returned(
                "10:01:11",
                "toolu_edit",
                [
                    {"type": "text", "text": "ok"},
                    {"type": "image", "source": {"type": "base64", "data": "iVBORw0KGgo"}},
                    {"type": "text", "text": "fini"},
                ],
            ),
            returned("10:01:12", "toolu_bash", "y" * 20),
            returned("10:01:13", "toolu_absent", "abc"),
            said("10:02:00", "Base directory for this skill: x"),
            said("10:03:00", "ok go"),
            {"type": "attachment", "timestamp": at("10:03:01"), "attachment": {"prompt": "z" * 99}},
            {
                "type": "api-request-blob",
                "message": {"role": "user", "content": [{"type": "text", "text": "z" * 99}]},
            },
            {**said("10:03:02", "z" * 99), "isSidechain": True},
        ],
    )

    composition = bilan.context_profile(session).composition

    assert composition == bilan.Composition(
        thinking=3 + 5 + 6,
        tool_input=21 + 38 + 17,
        editing=38,
        skills=32,
        text=len("bonjour") + len("Base directory for this skill: cité") + len("ok go"),
        results=Counter({"Read": 40, "Bash": 20, "Edit": 6, "?": 3}),
    )
    # 40, 20 et 6 caractères sur 69 : les trois outils les plus lourds, « ? » quatrième.
    assert bilan.composition_line(composition) == (
        "  composition (caractères) : résultats d'outils 0 K (Read 58 %, Bash 29 %, Edit 9 %)"
        " · réflexion 0 K · arguments d'outils 0 K dont édition 0 K"
        " · skills chargés 0 K · texte 0 K"
    )


def test_un_profil_sans_cache_lu_ni_retour_d_outil_non_vide_se_rend_sans_part(
    tmp_path: Path,
) -> None:
    """Les deux parts du profil ont un dénominateur qui peut être nul — le cache lu de toute la
    session, la somme des retours d'outils : la section se rend alors sans part, au lieu de
    lever `ZeroDivisionError`. Sous quatre appels, les quarts se rendent d'un tiret."""
    session = write_transcript(
        tmp_path / "session.jsonl",
        [
            uses("10:00:00", "msg_1", 0, "Skill", {"skill": "code-review"}, "toolu_cr"),
            returned("10:00:05", "toolu_cr", ""),
        ],
    )

    assert bilan.profile_lines(bilan.context_profile(session))[1:] == [
        "  appels 1 · contexte au 1er appel 2 · cache lu moyen par quart —",
        "  première porte de relecture : appel 1 (Skill code-review)",
        (
            "  composition (caractères) : résultats d'outils 0 K · réflexion 0 K"
            " · arguments d'outils 0 K dont édition 0 K · skills chargés 0 K · texte 0 K"
        ),
    ]


# --- La session de relecture, désignée par `--relecture` (#134, lot 5) --------------------------


def deux_dossiers(tmp_path: Path) -> tuple[Path, Path]:
    """Une session PR et sa session de relecture, chacune avec un sous-agent. La session de
    relecture tourne dans son propre worktree : son transcript et ses sous-agents vivent sous un
    autre dossier de projet que ceux de la session PR."""
    pr, relecture = "1444a1a8-0389-4e7a-a299-a2ebe3a8e56c", "f6942c91-c0c7-4230-91c5-23af96ea3e16"
    (tmp_path / "dossier-pr").mkdir()
    (tmp_path / "dossier-relecture").mkdir()
    session_pr = write_transcript(
        tmp_path / "dossier-pr" / f"{pr}.jsonl",
        [
            said("10:00:00", "démarre le lot"),
            api_call("10:00:30", "msg_pr1", 1_000_000, 2_000_000, 30_000),
            api_call("10:05:00", "msg_pr2", 3_000_000, 500_000, 20_000),
        ],
    )
    write_subagent(
        session_pr,
        "agent-a1",
        [said("10:01:00", "Bloc A"), api_call("10:02:00", "msg_dev", 0, 9_000, 50)],
        {"agentType": "developpeur", "description": "Bloc A"},
    )
    session_relecture = write_transcript(
        tmp_path / "dossier-relecture" / f"{relecture}.jsonl",
        [
            said("10:10:00", "relis la PR"),
            api_call("10:10:30", "msg_rv1", 4_000_000, 1_000_000, 10_000),
        ],
    )
    write_subagent(session_relecture, "agent-b1", RELECTEUR, RELECTEUR_META)
    return session_pr, session_relecture


def test_main_rend_la_session_de_relecture_avec_la_session_pr_depuis_deux_dossiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Désignée par `--relecture`, la session de relecture rend ses sous-agents et sa section de
    profil, lus sous son propre dossier."""
    session_pr, session_relecture = deux_dossiers(tmp_path)

    code, sortie = run_main([str(session_pr), "--relecture", str(session_relecture)], monkeypatch)

    assert code == 0
    for agent in ("developpeur « Bloc A » — 1 contact", "relecteur « Relecture 4.2, passe 1 »"):
        assert f"  {agent}" in sortie, agent
    for session in (session_pr, session_relecture):
        assert f"profil de contexte — {session.stem[:8]}" in sortie, session
    assert sortie.count("  composition (caractères) : ") == 2


def test_la_session_de_relecture_rend_ses_jetons_sur_sa_propre_ligne(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Les jetons de la session ne portent que la session et ses relais ; ceux de la relecture
    ont leur ligne, juste après, et seulement quand elle est désignée."""
    session_pr, session_relecture = deux_dossiers(tmp_path)

    _, avec = run_main([str(session_pr), "--relecture", str(session_relecture)], monkeypatch)
    _, sans = run_main([str(session_pr)], monkeypatch)

    lignes = avec.splitlines()
    pr = bilan.Usage(
        output=30_000 + 20_000, cache_read=1_000_000 + 3_000_000, cache_write=2_000_000 + 500_000
    )
    relecture = bilan.Usage(output=10_000, cache_read=4_000_000, cache_write=1_000_000)
    session = lignes.index(f"jetons de la session         {bilan.tokens(pr)}")
    assert lignes[session + 1] == f"jetons de la session de relecture {bilan.tokens(relecture)}"
    assert "session de relecture" not in sans


def test_un_transcript_de_relecture_absent_se_dit_avec_les_autres(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    present = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    absent = tmp_path / "relecture.jsonl"

    code, sortie = run_main([str(present), "--relecture", str(absent)], monkeypatch)

    assert code == 0
    assert f"transcripts demandés 2, lus 1 — absents : {absent}" in sortie
    assert "jetons de la session de relecture" not in sortie, "une ligne à zéro se lirait mesurée"


def test_une_session_de_relecture_lue_seule_ne_rend_pas_de_bilan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans positionnel lu, pas de chronologie, donc pas de bilan : la ligne des absents ne
    promet pas de bilan partiel parce qu'un transcript de relecture, lui, est là."""
    absent = tmp_path / "libere.jsonl"
    relecture = write_transcript(
        tmp_path / "relecture.jsonl", [said("10:10:00", "relis"), assistant("10:20:00")]
    )

    code, sortie = run_main([str(absent), "--relecture", str(relecture)], monkeypatch)

    assert code == 1
    assert f"transcripts demandés 2, lus 1 — absents : {absent}" in sortie
    assert "bilan partiel" not in sortie


def test_sans_transcript_le_script_rend_son_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as sortie:
        bilan.main([])

    assert sortie.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_un_relais_donne_apres_la_relecture_reste_un_relais(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--relecture` prend un transcript par option : un positionnel qui le suit reste un relais
    de la session, au lieu d'être lu, sans rien dire, comme un relais de la relecture."""
    session = write_transcript(tmp_path / "session.jsonl", TIMELINE)
    relais = write_transcript(tmp_path / "relais.jsonl", RELAY)
    revue = write_transcript(tmp_path / "relecture.jsonl", PARALLELE)

    _, sortie = run_main([str(session), "--relecture", str(revue), str(relais)], monkeypatch)

    heure = bilan.local(datetime.fromisoformat(at("12:30:00")))
    assert ligne(sortie, "session ").endswith(f"(sessions : 2, relais à {heure})")


# Une session de relecture qui tourne pendant `TIMELINE`.
PARALLELE: list[dict[str, Any]] = [said("11:00:00", "relis"), assistant("11:10:00")]

# Chaque forme, en littéraux : les transcripts positionnels — la session et ses relais —, celui de
# la session de relecture qui les chevauche, les heures de relais attendues, et le transcript d'un
# sous-agent de la session de relecture, vide quand elle n'en a pas.
INFERENCES: dict[
    str,
    tuple[list[list[dict[str, Any]]], list[dict[str, Any]], list[str], list[dict[str, Any]]],
] = {
    "forme-1-parallele-lue-en-relais": ([TIMELINE], PARALLELE, [], []),
    "forme-2-relais-chevauche-par-la-relecture": (
        [TIMELINE, RELAY],
        [
            said("10:40:00", "relis la PR"),
            assistant("10:50:00"),
            said("12:35:00", "passe 2"),
            assistant("12:36:00"),
        ],
        ["12:30:00"],
        [],
    ),
    "forme-3-evenement-tardif-apres-le-relais": (
        [
            [said("10:00:00", "go"), assistant("10:10:00"), said("10:40:00", PEER_MESSAGE)],
            [
                said("10:30:00", "je relaie"),
                assistant("10:35:00"),
                said("10:50:00", "continue"),
                assistant("10:55:00"),
            ],
        ],
        [
            said("10:20:00", "relis"),
            assistant("10:25:00"),
            said("10:45:00", "passe 2"),
            assistant("10:46:00"),
        ],
        ["10:30:00"],
        [],
    ),
    "forme-4-sous-agent-de-la-relecture-pendant-une-attente": (
        [
            [
                said("10:00:00", "go"),
                assistant("10:01:00"),
                said("10:40:00", "continue"),
                assistant("10:45:00"),
            ]
        ],
        [said("10:05:00", "relis"), assistant("10:06:00")],
        [],
        [said("10:10:00", "passe 1"), api_call("10:30:00", "msg_r1", 0, 1_000, 10)],
    ),
}


@pytest.mark.parametrize(
    ("positionnels", "relecture", "relais", "sous_agent"),
    INFERENCES.values(),
    ids=INFERENCES.keys(),
)
def test_la_session_de_relecture_designee_n_entre_ni_dans_les_relais_ni_dans_les_attentes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    positionnels: list[list[dict[str, Any]]],
    relecture: list[dict[str, Any]],
    relais: list[str],
    sous_agent: list[dict[str, Any]],
) -> None:
    """Le bilan devinait d'après les heures si un transcript était un relais ou une session en
    parallèle. Dénombrement, écrit avant le correctif : 3 formes recensées, 3 fuient ou ont fui.

    1. Une session parallèle lue comme un relais : « relais à 23:33 » pour la session de
       relecture du lot 4a, mesuré le 2026-10-21.
    2. Le relais d'une session PR lu « en parallèle » quand la session de relecture est donnée
       avec elle : la relecture tourne du go jusqu'à la fin du cycle, donc elle chevauche tout
       relais (`/code-review` de la passe 2).
    3. Un vrai relais lu « en parallèle » quand la session sortante reçoit encore un événement
       après le premier de la remplaçante — notification de fond, message de la coordinatrice,
       moniteur de PR (`relecteur`, constat m-1, supposé sur une session réelle).

    Rejoué le 2026-10-21 sur ces montages avec les deux règles d'avant : celle d'origine lit la
    forme 1 en relais, celle de la tranche B les formes 2 et 3 « en parallèle » — la forme 3
    même sans session de relecture. Aucun motif sur les heures ne ferme les trois : l'appelant
    désigne la session de relecture (`--relecture`), et chaque transcript positionnel est un
    relais. L'en-tête — durée comprise — rend donc les positionnels seuls, et la réactivité est
    celle de la session et de ses relais lus sans elle.

    La forme 4 relève d'une autre classe, recensée plus bas : un sous-agent de la session de
    relecture dont le contact chevauche une attente de la session PR — réactivité 0 h 19 au lieu
    de 0 h 39, et « sous-agents en cours 0 h 20 (0 lancés) » (`relecteur`, relance de la PR
    #146 ; rejoué sur ce montage le 2026-10-21).

    Les chemins par lesquels la session de relecture entre dans la mesure de la session PR, lus
    dans `main`, `report` et `measure`. Dénombrement, écrit avant le correctif de la forme 4 :
    8 recensés, 2 fuyaient, 1 entrait sans effet.
    - Ses événements (`read_events`) : positionnels seuls depuis `51e6acc` — formes 1 à 3.
    - Ses jetons (`token_usage`) : sur leur ligne —
      `test_la_session_de_relecture_rend_ses_jetons_sur_sa_propre_ligne`.
    - Les fenêtres de ses sous-agents (`measure`) : retirées des attentes, comptées en
      « sous-agents en cours », retranchées d'« agent seul » hors des attentes — fuyaient,
      forme 4.
    - Leurs lancements (`launched_subagents`) : lus dans les événements — indemnes, forme 4.
    - `dangling` : leurs lanceurs entraient dans `seen`, qui ne retranche qu'un lancement de la
      session PR au même identifiant d'appel, propre à une session — sans effet, fermé avec
      les fenêtres.
    - Le compte de transcripts des jetons des sous-agents (`consumed`) : sommait les deux sans
      le dire — fuyait, `test_les_jetons_des_sous_agents_disent_la_part_de_la_relecture`.
    - Son profil (`context_profile`) : sa propre section, titrée de son identifiant — indemne.
    - La ligne des absents : compte ses transcripts, ce qu'elle doit dire — indemne.

    Comparée : la mesure de la session, tout ce qui précède ses jetons — la population des
    lignes où un chemin fuirait.
    """
    session = [
        write_transcript(tmp_path / f"session-{rang}.jsonl", records)
        for rang, records in enumerate(positionnels)
    ]
    chemins = [str(path) for path in session]
    revue = write_transcript(tmp_path / "relecture.jsonl", relecture)
    if sous_agent:
        write_subagent(revue, "agent-r1", sous_agent, {"agentType": "relecteur"})

    _, avec = run_main([*chemins, "--relecture", str(revue)], monkeypatch)
    _, sans = run_main(chemins, monkeypatch)

    heures = "".join(f", relais à {bilan.local(datetime.fromisoformat(at(c)))}" for c in relais)
    assert ligne(avec, "session ").endswith(f"(sessions : {len(positionnels)}{heures})")
    assert avec.split("\njetons ")[0] == sans.split("\njetons ")[0]


def test_les_jetons_des_sous_agents_disent_la_part_de_la_relecture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Les sous-agents de la session de relecture se somment à ceux de la session PR dans la
    ligne de leurs jetons, qui le dit — et ne dit rien quand la relecture n'en a lancé aucun."""
    session_pr, session_relecture = deux_dossiers(tmp_path)
    sans_sous_agent = write_transcript(tmp_path / "relecture-seule.jsonl", PARALLELE)

    _, avec = run_main([str(session_pr), "--relecture", str(session_relecture)], monkeypatch)
    _, seule = run_main([str(session_pr), "--relecture", str(sans_sous_agent)], monkeypatch)

    debut = "jetons des sous-agents"
    assert ligne(avec, debut).endswith("(2 transcripts, dont 1 de la session de relecture)")
    assert ligne(seule, debut).endswith("(1 transcripts)")
