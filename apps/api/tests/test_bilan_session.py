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

import pytest
from skill_scripts import load_script

bilan = load_script("cycle-pr", "bilan-session")

AGENT_CALL = "toolu_agent0000000000000001"
BASH_CALL = "toolu_bash00000000000000002"
WORKFLOW_CALL = "toolu_workflow000000000003"
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
    assistant("10:05:00", (WORKFLOW_CALL, "Workflow")),
    notification("10:15:00", WORKFLOW_CALL, "w3k9fjz2q", status="completed"),
    # La même tâche peut notifier plusieurs fois — le harnais le dit dans sa propre note. Seule
    # une notification `completed` ferme la fenêtre ; celle-ci la fermerait 10 minutes trop tôt.
    notification("10:10:00", AGENT_CALL, "a25bc5b33dbf83cd2", status="in_progress"),
    notification(
        "10:20:00",
        AGENT_CALL,
        "a25bc5b33dbf83cd2",
        f"<usage><subagent_tokens>{AGENT_TOKENS}</subagent_tokens></usage>\n",
    ),
    # Reprise puis arrêt : une seconde `completed` du **même** appel, avec un autre compte de
    # jetons. La première l'emporte, donc fenêtre close à 10:20 et AGENT_TOKENS ; la dernière
    # donnerait 10:22 et 999. C'est ce qui épingle la décision verrouillée du critère 3.
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
    events = read(tmp_path)
    windows = bilan.subagent_windows(events, bilan.tool_calls(events))

    assert [bilan.total([window]) for window in windows] == [timedelta(minutes=19, seconds=30)]


def test_l_attente_du_mainteneur_exclut_le_temps_des_sous_agents(tmp_path: Path) -> None:
    """Sinon le mainteneur est facturé du temps qu'il n'a pas fait attendre (obs 41).

    Deux attentes réelles ici : 15 min après le dernier tour de l'agent, et 1 h 24 min 30
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

    assert [(run.tool, run.tokens) for run in runs] == [
        ("Agent", AGENT_TOKENS),
        ("Workflow", 0),
    ]
    assert {run.name for run in runs} == {"Relecture 4.2 passe 1 #5"}


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
    # L'attente hors absences se lit avant l'agrégat : 15 min sur 2 h 40 de session.
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


# --- Ce que la passe 2 a trouvé (2026-10-09) ---------------------------------------------------


# Le recueil des formes réelles, avec sa **population** : les 87 transcripts du projet au
# 2026-10-10 (`~/.claude/projects/*ortfolio*/*.jsonl`), soit **1137 messages de rôle `user` hors
# résultat d'outil**. Les 16 formes ci-dessous en font la somme exacte — c'est ce que
# `test_le_recueil_couvre_la_population_entiere` assère, pour qu'une famille neuve ne puisse pas
# entrer sans que la population soit re-mesurée.
#
# Deux dénombrements ont déjà menti ici. La classe « pair » avait été fermée sur la seule forme
# qui l'avait révélée (`<cross-session-message`), alors que 48 messages portent `<agent-message`.
# Puis la règle de forme a classé `system` **10 messages humains** : le harnais préfixe le texte
# du mainteneur d'une balise de contexte au lieu de l'injecter seule, et une balise *en tête*
# suffisait à classer. Les deux fois, le correctif a été déclaré clos sur la seule famille qui
# l'avait révélé ; les deux fois, la relecture suivante en a trouvé une autre. D'où la forme de
# ce recueil : **les 7 familles de balises y sont, pas les 3 qui ont servi de preuve**.
FORMES_REELLES = {
    # Les 7 familles de balises. Un message n'est injecté que s'il n'est *rien d'autre* que des
    # blocs équilibrés : les deux familles de contexte IDE portent un texte humain après leur
    # bloc, et ce texte est de la main du mainteneur.
    "notification de fin de tâche": (
        "<task-notification><status>completed</status></task-notification>",
        "system",
        86,
    ),
    "message d'une commande locale": (
        "<command-message>cycle-pr is running…</command-message>",
        "system",
        37,
    ),
    "nom d'une commande locale": ("<command-name>cycle-pr</command-name>", "system", 13),
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
        9,
    ),
    "sélection dans l'éditeur, puis le texte du mainteneur": (
        (
            "<ide_selection>The user selected the lines 140 to 140 from e:\\x.md"
            "</ide_selection>On a donc un ADR et un system design défini."
        ),
        "human",
        1,
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
        179,
    ),
    "interruption par le mainteneur": ("[Request interrupted by user]", "system", 33),
    "avis d'inactivité d'une session voisine": (
        '[Cross-session idle notice] "uds:\\\\.\\pipe\\LOCAL" est au repos',
        "system",
        22,
    ),
    "référence d'écriture de workflow": (
        "# Workflow authoring reference\n\nA workflow structures work…",
        "system",
        9,
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
        233,
    ),
    "message de pair, balise actuelle": (
        "Another Claude session sent a message:\n<agent-message from='relecteur'>",
        "peer",
        48,
    ),
    # Et la prose du mainteneur, qui ne commence par rien de tout cela.
    "prose du mainteneur": ("Quelles sont les bonnes pratiques pour cela ?", "human", 434),
}

# Le recensement du 2026-10-10, que le recueil doit couvrir sans résidu.
POPULATION = 1137
PAR_CLASSE = {"human": 456, "system": 400, "peer": 281}


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
        seen: ses occurrences au recensement du 2026-10-10.
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


def test_une_balise_non_fermee_reste_un_message_du_mainteneur() -> None:
    """Un bloc qui ne se ferme pas n'est pas une injection délimitable.

    Recensé sur les 87 transcripts : **0 balise en tête non fermée** — le harnais ferme toujours
    ses blocs. La règle refuse donc de classer `system` ce qu'elle ne peut pas borner, plutôt
    que de deviner où finit le bloc et d'avaler le texte qui le suit.
    """
    assert bilan.classify("user", [{"type": "text", "text": "<ide_opened_file>tronqué"}]) == "human"


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
    assert bilan.total(m.absences) == timedelta(hours=1, minutes=24, seconds=30)
    assert bilan.total(m.blocked) == timedelta(hours=1, minutes=39, seconds=30)
    assert bilan.total(m.windows) == timedelta(minutes=19, seconds=30), (
        "le workflow est imbriqué dans la fenêtre de l'agent : l'union ne double pas"
    )
    assert m.alone == m.span - bilan.total(bilan.union(list(m.blocked) + list(m.windows)))
    assert len(m.runs) == 2
    assert len(m.workflows) == 1, "le critère 4 exige un workflow dans le transcript synthétique"
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

    L'absence du transcript synthétique fait 1 h 24 : `>` et `>=` y rendent le même résultat.
    Mesuré en relecture — relâcher la comparaison laissait la suite verte.
    """
    debut = datetime.fromisoformat(at("10:00:00"))
    pile = debut + timedelta(hours=1)
    juste_avant = debut + timedelta(minutes=59, seconds=59)

    assert bilan.split_waits([(debut, pile)]) == ([], [(debut, pile)])
    assert bilan.split_waits([(debut, juste_avant)]) == ([(debut, juste_avant)], [])
