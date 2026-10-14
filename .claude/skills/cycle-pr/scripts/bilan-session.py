"""Bilan chiffré d'une session Claude Code, lu dans ses transcripts JSONL.

Usage : python bilan-session.py <transcript.jsonl> [<relais.jsonl> …]

Un cycle qui a rempli un contexte a **plusieurs** transcripts : le script en accepte autant
qu'on lui en donne, les fusionne dans l'ordre du temps et rend l'heure de chaque relais (obs 40).

Rend, sans double compte : la durée de la session ; l'attente — du mainteneur ou d'un pair,
jusqu'au dernier message qui rouvre le tour de l'agent — **scindée** en réactivité (moins d'une
heure) et absences (une heure ou plus), le pourcentage hors absences en tête — les deux n'ont ni
la même cause ni le même remède, et leur somme se lit comme un défaut de la pipeline alors
qu'une nuit relève du calendrier (obs 43) ; le temps des sous-agents et des workflows,
**retiré** de cette attente, qui le compterait sinon comme du temps passé à attendre ; le temps
d'agent seul ; les jetons facturés par la session ; le cache que chaque sous-agent a lu et écrit,
**contact par contact**, lu dans son propre transcript — la notification de fin de son lancement
ne porte que le contexte en fin de premier contact, et un agent au premier plan n'en émet
aucune ; sa sortie, que ce transcript ne porte pas de façon fiable, n'est pas rendue ; les points
de contact humains et les appels d'outils.

Python 3.11 ou plus, bibliothèque standard seule.
"""

import json
import re
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, cast

# Une attente d'une heure ou plus n'est pas de la réactivité : c'est une absence, que la pipeline
# ne peut pas réduire. Les mêler fait attribuer au processus ce qui revient au calendrier.
ABSENCE = timedelta(hours=1)
QUESTION_TOOL = "AskUserQuestion"
SUBAGENT_TOOLS = {"Agent", "Task", "Workflow"}
WORKFLOW_TOOL = "Workflow"
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

# Une notification de fin de tâche, telle que le harnais la livre — sous deux formes : une pièce
# jointe `queued_command` dont le `commandMode` le dit, ou un message `user` dont le texte nu
# **commence** par la balise. Un test sur la *ligne* entière — la chaîne `<task-notification`
# apparaît aussi dans le texte du prompt système d'un `prompt_snapshot`, et dans les messages
# qui en citent une — compte ces citations comme des fins de sous-agent. Dénombrement et
# population : `FORMES_DE_LIVRAISON` dans la suite.
NOTIFICATION_MODE = "task-notification"
NOTIFICATION_TAG = "<task-notification>"
TOOL_USE_ID = re.compile(r"<tool-use-id>(?P<id>[^<]+)</tool-use-id>")
STATUS_COMPLETED = "<status>completed</status>"

# Les deux balises qu'un message de pair peut porter. N'en chercher qu'une classait les messages
# d'équipier portant l'autre comme des messages du mainteneur — la classe avait été fermée sur
# la seule forme qui l'avait révélée. Dénombrement et population : `FORMES_REELLES` dans la
# suite, seul endroit où les chiffres vivent — recopiés ici, ils dérivent au recensement suivant.
PEER_TAGS = ("<cross-session-message", "<agent-message")

# L'avis qu'une session voisine est au repos, que l'agent a demandé pour l'attendre : il rouvre un
# tour de pair au même titre que le message qu'elle aurait envoyé.
PEER_NOTICE = "[Cross-session idle notice]"

# Une commande **tapée** par le mainteneur — skill ou commande locale — porte la barre oblique
# dans son nom ; un skill que le harnais charge de lui-même n'en porte pas. Population :
# `FORMES_REELLES`.
TYPED_COMMAND = "<command-name>/"

# Les classes de message qui rouvrent un tour de l'agent, donc ferment son attente : le
# mainteneur, prose ou commande tapée, et un pair.
TURN_OPENERS = ("human", "peer")

# Dans le transcript d'un sous-agent, le message par lequel le coordinateur le reprend — un
# `SendMessage`, que l'agent ait fini ou non. C'est lui qui ouvre un nouveau contact.
COORDINATOR = "The coordinator sent a message"

# Le harnais injecte ses textes dans le rôle `user` sous des **balises** : `<task-notification>`,
# `<command-message>`, `<local-command-caveat>`, `<ide_opened_file>`… Les énumérer une par une,
# c'est rouvrir le défaut à chaque balise neuve ; cette forme-là ferme la famille entière.
#
# Mais une balise **en tête** ne suffit pas à classer : le harnais préfixe le texte humain d'une
# balise de contexte au lieu de l'injecter seule — `<ide_opened_file>…</ide_opened_file>oui go` —
# et s'arrêter à la tête perdait ce « oui go ». Un message n'est injecté que s'il n'est **rien
# d'autre** que des blocs de balises équilibrés ; ce qui dépasse est de la main du mainteneur.
# Le nom se lit sans attribut à dessein : `<pasted_content id="…">` en porte un, et son contenu
# est du texte que le mainteneur a collé. Population et dénombrement : `FORMES_REELLES`.
#
# Le corps d'un bloc ne peut pas contenir sa propre fermeture — `(?:(?!</\1>).)*` et non `.*?`.
# Ce n'est pas un raffinement : avec `.*?`, un découpage ambigu rend le motif **exponentiel**,
# parce que chaque bloc peut se fermer sur n'importe quelle fermeture suivante. Mesuré le
# 2026-10-10 sur `<a>x</a>` répété puis un caractère qui fait échouer : 0,03 s à 18 blocs,
# 0,09 s à 20, ×3 tous les deux blocs — quelques dizaines de blocs suffisent à figer la mesure.
# Sous cette forme, le découpage est unique et le coût redevient quasi linéaire — là où le motif
# naïf n'atteint pas 25 blocs. Relevé, plage et commande dans
# `test_une_suite_de_blocs_qui_echoue_ne_fait_pas_exploser_le_classement`, jamais ici.
INJECTED_BLOCKS = re.compile(r"\A(?:\s*<([a-z][a-z0-9_-]*)>(?:(?!</\1>).)*</\1>)+\s*\Z", re.DOTALL)

# Et les formes injectées qui ne sont **pas** des balises — à énumérer, elles. `Caveat: The
# messages below were generated` y figurait et n'a jamais mordu : la forme réelle est
# `<local-command-caveat>Caveat: …`, donc une balise. Dénombrement : `FORMES_REELLES`.
INJECTED = (
    "Base directory for this skill:",
    "[Request interrupted",
    "# Workflow authoring reference",
    "This session is being continued from a previous conversation",
)

Interval = tuple[datetime, datetime]


@dataclass
class Event:
    """Une ligne datée d'un transcript.

    Attributes:
        when: son horodatage.
        kind: `assistant`, `tool_result`, `notification`, `peer`, `system` ou `human`.
        uses: les `(identifiant, outil)` lancés par ce tour.
        results: les identifiants d'outils dont le résultat revient ici.
        ends: pour une notification, l'identifiant de l'appel d'outil qu'elle termine — c'est
            lui qui l'apparie à son lancement, et non son ordre d'arrivée.
        source: le rang de son transcript, pour dater les relais.
    """

    when: datetime
    kind: str
    uses: list[tuple[str, str]] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    ends: str = ""
    source: int = 0


@dataclass
class ToolCall:
    """Un appel d'outil dont le résultat est revenu."""

    name: str
    uid: str
    started: datetime
    duration: timedelta


@dataclass
class AgentRun:
    """Un sous-agent ou un workflow, de son lancement à sa notification de fin.

    Rien de plus : le nom et la consommation se lisent dans le transcript du sous-agent
    (`subagents`), la notification de son lancement ne portant que le contexte en fin de premier
    contact.
    """

    uid: str
    tool: str
    window: Interval


@dataclass
class Usage:
    """Jetons facturés par un ensemble d'appels d'API, un seul compte par message."""

    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    transcripts: int = 0

    def add(self, counts: Mapping[str, int]) -> None:
        """Ajoute l'`usage` d'un appel d'API."""
        self.output += counts.get("output_tokens") or 0
        self.cache_read += counts.get("cache_read_input_tokens") or 0
        self.cache_write += counts.get("cache_creation_input_tokens") or 0


# Ce qu'un appel d'API a eu en contexte : son entrée hors cache, et le cache qu'il a lu ou écrit.
CONTEXT_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


@dataclass
class Contact:
    """Un contact d'un sous-agent : son lancement, ou une reprise par le coordinateur.

    Attributes:
        window: du premier enregistrement du contact à son dernier appel d'API.
        calls: les appels d'API, un par message — un message diffusé sur plusieurs lignes
            compte une fois.
        context: le contexte du dernier appel — ce que la notification de fin rapporte, et
            **pas** une consommation.
        used: la consommation du contact, sommée sur ses appels — sa sortie n'est pas rendue,
            le transcript d'un sous-agent ne la portant pas de façon fiable (`consumed`).
    """

    window: Interval
    calls: int = 0
    context: int = 0
    used: Usage = field(default_factory=Usage)


@dataclass
class Subagent:
    """Un sous-agent tel que son transcript le raconte, contact par contact.

    Attributes:
        role: son `agentType` (`relecteur`, `verificateur`…).
        name: sa description, à défaut son nom, à défaut le nom de son transcript.
        launcher: l'identifiant de l'appel d'outil qui l'a lancé — vide pour un agent de
            workflow, que le harnais lance sans appel de la session.
        contacts: ses contacts, dans l'ordre.
    """

    role: str
    name: str
    launcher: str
    contacts: list[Contact]


def records(path: Path | str) -> Iterator[dict[str, Any]]:
    """Les enregistrements d'un transcript JSONL, lignes illisibles écartées."""
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def content_blocks(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Les blocs d'un message, qu'il porte une liste de blocs ou un texte nu."""
    content = (record.get("message") or {}).get("content", [])
    if isinstance(content, list):
        return cast(list[dict[str, Any]], content)
    return [{"type": "text", "text": content}]


def api_call(record: Mapping[str, Any]) -> tuple[str, Mapping[str, int]] | None:
    """L'identifiant de message et l'`usage` d'un appel d'API, ou `None`.

    Un message diffusé en plusieurs blocs occupe plusieurs lignes qui portent le même `id` et le
    même `usage` : c'est l'identifiant qui permet de n'en compter qu'une.
    """
    message = record.get("message") or {}
    if record.get("type") == "assistant" and message.get("usage"):
        return message.get("id") or record.get("uuid", ""), message["usage"]
    return None


def token_usage(paths: Sequence[Path]) -> Usage:
    """Somme l'`usage` de chaque message assistant de ces transcripts, une fois par message."""
    usage = Usage(transcripts=len(paths))
    for path in paths:
        calls = dict(call for record in records(path) if (call := api_call(record)))
        for counts in calls.values():
            usage.add(counts)
    return usage


def resumes(record: Mapping[str, Any]) -> bool:
    """Vrai si l'enregistrement est un message du coordinateur, qui reprend le sous-agent."""
    return record.get("type") == "user" and any(
        str(block.get("text", "")).startswith(COORDINATOR)
        for block in content_blocks(record)
        if block.get("type") == "text"
    )


def contacts(path: Path) -> list[Contact]:
    """Les contacts d'un transcript de sous-agent, et ce que chacun a consommé.

    Un contact s'ouvre au premier enregistrement, puis à chaque message du coordinateur — la
    seule forme qui reprenne un agent. Les relances du harnais (« [Your previous response had
    no visible output… », « [SYSTEM NOTIFICATION… », « [Request interrupted… ») restent dans
    le contact en cours. Population et dénombrement : la docstring de
    `test_un_sous_agent_se_mesure_contact_par_contact_dans_son_transcript`.
    """
    segments: list[list[dict[str, Any]]] = []
    for record in records(path):
        if record.get("timestamp"):
            if not segments or resumes(record):
                segments.append([])
            segments[-1].append(record)
    return [measure_contact(segment) for segment in segments]


def measure_contact(segment: Sequence[Mapping[str, Any]]) -> Contact:
    """La fenêtre, les appels, le contexte final et la consommation d'un contact non vide."""
    start = end = datetime.fromisoformat(segment[0]["timestamp"])
    calls: dict[str, Mapping[str, int]] = {}
    for record in segment:
        if call := api_call(record):
            calls[call[0]] = call[1]
            end = datetime.fromisoformat(record["timestamp"])
    contact = Contact((start, end), calls=len(calls))
    for counts in calls.values():
        contact.used.add(counts)
    if calls:
        last = list(calls.values())[-1]
        contact.context = sum(last.get(key) or 0 for key in CONTEXT_KEYS)
    return contact


def consumed(agents: Sequence[Subagent]) -> Usage:
    """Le cache que ces sous-agents ont lu et écrit, somme de leurs contacts.

    Pas leur sortie : dans un transcript de sous-agent, une partie des messages porte un
    `output_tokens` figé bien en dessous de ce qu'ils contiennent — population et mesure dans
    `test_la_sortie_d_un_sous_agent_ne_se_rend_pas`. Elle reste à zéro ici, et le rapport le dit.
    """
    usage = Usage(transcripts=len(agents))
    for agent in agents:
        for contact in agent.contacts:
            usage.cache_read += contact.used.cache_read
            usage.cache_write += contact.used.cache_write
    return usage


def subagents(paths: Sequence[Path]) -> list[Subagent]:
    """Les sous-agents de ces transcripts de session, lus dans leurs propres transcripts.

    Le harnais les range sous `<uuid de session>/subagents/` — ceux d'un workflow un cran plus
    bas —, chacun avec un `.meta.json`. Partir de là, et non des notifications de fin, voit
    l'agent lancé au premier plan, qui n'en émet aucune, et chaque reprise d'un agent repris.
    """
    found: list[Subagent] = []
    for path in paths:
        for transcript in sorted(path.with_suffix("").glob("subagents/**/agent-*.jsonl")):
            meta_path = transcript.with_name(transcript.stem + ".meta.json")
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            found.append(
                Subagent(
                    role=str(meta.get("agentType", "")),
                    name=str(meta.get("description") or meta.get("name") or transcript.stem),
                    launcher=str(meta.get("toolUseId", "")),
                    contacts=contacts(transcript),
                )
            )
    # L'ordre du temps, pas celui des noms de fichier, qui sont des identifiants aléatoires.
    # Un transcript sans enregistrement daté n'a pas de contact : il passe en tête.
    return sorted(found, key=lambda agent: [contact.window[0] for contact in agent.contacts[:1]])


def delivered_notification(record: Mapping[str, Any]) -> str | None:
    """Le texte de la notification de fin que cet enregistrement **livre**, ou `None`.

    Deux formes, et elles seules : une pièce jointe dont le `commandMode` vaut
    `task-notification`, ou un message `user` dont le texte nu commence par la balise. Un
    message qui en cite une plus loin n'en livre pas.
    """
    if record.get("type") == "attachment":
        attachment = cast(dict[str, Any], record.get("attachment") or {})
        if attachment.get("commandMode") == NOTIFICATION_MODE:
            return str(attachment.get("prompt", ""))
        return None
    content = (record.get("message") or {}).get("content")
    if (
        record.get("type") == "user"
        and isinstance(content, str)
        and content.lstrip().startswith(NOTIFICATION_TAG)
    ):
        return content
    return None


def notification_event(when: datetime, text: str, source: int) -> Event | None:
    """L'événement d'une notification livrée, ou `None` si elle ne ferme rien.

    Seule une notification `completed` ferme une fenêtre : la même tâche peut notifier plusieurs
    fois, le harnais le dit lui-même dans sa note.
    """
    if STATUS_COMPLETED not in text:
        return None
    call = TOOL_USE_ID.search(text)
    return Event(when, "notification", ends=call.group("id") if call else "", source=source)


def read_events(paths: Sequence[Path | str]) -> list[Event]:
    """Lit tous les transcripts d'une session et rend leurs événements, ordonnés par le temps."""
    events: list[Event] = []
    for source, path in enumerate(paths):
        for record in records(path):
            if not record.get("timestamp") or record.get("isSidechain"):
                continue
            when = datetime.fromisoformat(record["timestamp"])
            delivered = delivered_notification(record)
            if delivered is not None:
                found = notification_event(when, delivered, source)
                if found:
                    events.append(found)
                continue
            if record.get("type") not in ("user", "assistant"):
                continue
            blocks = content_blocks(record)
            events.append(
                Event(
                    when,
                    classify(str(record["type"]), blocks),
                    [(b["id"], b["name"]) for b in blocks if b.get("type") == "tool_use"],
                    [b["tool_use_id"] for b in blocks if b.get("type") == "tool_result"],
                    source=source,
                )
            )
    events.sort(key=lambda event: event.when)
    return events


def classify(role: str, blocks: list[dict[str, Any]]) -> str:
    """La classe d'un message : d'où il vient, et s'il rouvre le tour de l'agent.

    Un message de pair **commence** par « Another Claude session sent a message: » et porte la
    balise plus loin : le chercher en tête le classait humain. Un texte injecté par le harnais —
    chargement de skill, commande, notification — est dans le rôle `user` sans qu'un humain
    l'ait tapé. Une balise de contexte **suivie** d'un texte reste un message du mainteneur :
    c'est lui qui a tapé ce qui dépasse la balise.

    Un texte injecté se reconnaît à son **début**, donc avant toute recherche de balise de pair :
    le texte d'un skill peut citer `<cross-session-message>`, et cette citation classait son
    chargement `peer` (40 messages au recensement de `FORMES_REELLES`). Une commande tapée par
    le mainteneur est faite de blocs de balises, mais c'est lui qui agit : `human`.
    """
    if role == "assistant":
        return "assistant"
    if any(block.get("type") == "tool_result" for block in blocks):
        return "tool_result"
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    stripped = SYSTEM_REMINDER.sub("", text).strip()
    if not stripped or stripped.startswith(INJECTED):
        return "system"
    if stripped.startswith(PEER_NOTICE) or any(tag in text for tag in PEER_TAGS):
        return "peer"
    if INJECTED_BLOCKS.match(stripped) and TYPED_COMMAND not in stripped:
        return "system"
    return "human"


def tool_calls(events: Sequence[Event]) -> list[ToolCall]:
    """Les appels d'outils dont le résultat est revenu, avec leur durée."""
    started: dict[str, tuple[str, datetime]] = {}
    for event in events:
        for uid, name in event.uses:
            started[uid] = (name, event.when)
    calls: list[ToolCall] = []
    for event in events:
        for uid in event.results:
            if uid in started:
                name, began = started[uid]
                calls.append(ToolCall(name, uid, began, event.when - began))
    return calls


def agent_runs(events: Sequence[Event], calls: Sequence[ToolCall]) -> list[AgentRun]:
    """Chaque sous-agent ou workflow lancé, apparié à sa notification de fin par son identifiant.

    L'appariement passe par le `<tool-use-id>` que porte la notification, jamais par l'ordre
    d'arrivée : entre le lancement d'un sous-agent et sa fin s'intercalent les notifications des
    commandes Bash de fond, et « la première non attribuée » raccourcit la fenêtre d'autant.
    """
    ended: dict[str, Event] = {}
    for event in events:
        if event.kind == "notification" and event.ends:
            # La **première** fin l'emporte : une compréhension de dictionnaire garderait la
            # dernière, et une tâche reprise puis arrêtée notifie plusieurs fois.
            ended.setdefault(event.ends, event)
    runs: list[AgentRun] = []
    for uid, (tool, started) in launched_subagents(events, calls):
        end = ended.get(uid)
        if end is None:
            continue
        runs.append(AgentRun(uid, tool, (started, end.when)))
    return runs


def launched_subagents(
    events: Sequence[Event], calls: Sequence[ToolCall]
) -> list[tuple[str, tuple[str, datetime]]]:
    """Tous les sous-agents et workflows **lancés**, par ordre de lancement.

    Distinct de `agent_runs`, qui ne garde que ceux dont la notification de fin est arrivée :
    un agent au premier plan n'en émet aucune, et un agent mort sans notifier serait écarté sans
    laisser de trace. Le rapport compte les lancements ici, et les rapproche des notifications
    et des transcripts pour que l'écart se voie.
    """
    launches = {
        uid: (name, event.when)
        for event in events
        for uid, name in event.uses
        if name in SUBAGENT_TOOLS
    }
    for call in calls:
        if call.name in SUBAGENT_TOOLS:
            launches.setdefault(call.uid, (call.name, call.started))
    return sorted(launches.items(), key=lambda item: item[1][1])


def waits(events: Sequence[Event], calls: Sequence[ToolCall]) -> list[Interval]:
    """Les attentes de l'agent et les questions formelles, fusionnées.

    Une attente court de sa dernière sortie au **dernier** message qui rouvre son tour avant la
    sortie suivante — du mainteneur ou d'un pair (`TURN_OPENERS`). Le dernier, pas le premier :
    un message qui n'a rien déclenché n'a pas mis l'agent au travail. Ne compter que le
    mainteneur faisait passer en travail d'agent toute attente close par un pair, écart entre
    deux transcripts compris — 242 h 30 d'agent seul au bilan du lot 1 de #23, pour 2 h 53 de
    travail (`test_un_relais_ouvert_par_un_pair_le_lendemain_est_une_absence`).

    Brutes : le temps des sous-agents s'en retire dans `measure`, **après** leur classement —
    le retrait est le cœur d'obs 41, sans lui une session à relectures parallèles facture au
    mainteneur le temps de ses sous-agents.
    """
    reopened: dict[datetime, datetime] = {}
    idle_since: datetime | None = None
    for event in events:
        if event.kind == "assistant":
            idle_since = event.when
        elif event.kind in TURN_OPENERS and idle_since is not None:
            reopened[idle_since] = event.when
    windows = list(reopened.items())
    windows += [
        (call.started, call.started + call.duration) for call in calls if call.name == QUESTION_TOOL
    ]
    return union(windows)


def split_waits(blocked: Sequence[Interval]) -> tuple[list[Interval], list[Interval]]:
    """Scinde les attentes en réactivité (moins d'une heure) et absences (une heure ou plus)."""
    reactivity = [window for window in blocked if window[1] - window[0] < ABSENCE]
    absences = [window for window in blocked if window[1] - window[0] >= ABSENCE]
    return reactivity, absences


def union(intervals: Sequence[Interval]) -> list[Interval]:
    """Fusionne les intervalles qui se chevauchent, pour qu'aucune minute ne compte deux fois."""
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def without(intervals: Sequence[Interval], holes: Sequence[Interval]) -> list[Interval]:
    """Retire des intervalles tout ce que couvrent les `holes`, en gardant les morceaux restants."""
    kept: list[Interval] = []
    for start, end in intervals:
        pieces = [(start, end)]
        for hole_start, hole_end in holes:
            remaining: list[Interval] = []
            for piece_start, piece_end in pieces:
                if hole_end <= piece_start or hole_start >= piece_end:
                    remaining.append((piece_start, piece_end))
                    continue
                if piece_start < hole_start:
                    remaining.append((piece_start, hole_start))
                if hole_end < piece_end:
                    remaining.append((hole_end, piece_end))
            pieces = remaining
        kept += pieces
    return kept


def total(intervals: Sequence[Interval]) -> timedelta:
    """La somme des durées d'intervalles déjà fusionnés."""
    return sum((end - start for start, end in intervals), timedelta())


def hm(duration: timedelta) -> str:
    """Une durée en heures et minutes, arrondie à la minute inférieure."""
    minutes = int(duration.total_seconds() // 60)
    return f"{minutes // 60} h {minutes % 60:02d}"


def local(moment: datetime) -> str:
    """Un horodatage dans le fuseau du lecteur."""
    return f"{moment.astimezone():%H:%M}"


def thousands(count: int) -> str:
    """Un nombre de jetons, groupé par milliers avec une espace."""
    return f"{count:,}".replace(",", " ")


def cached(usage: Usage) -> str:
    """Le cache lu et écrit d'un ensemble de transcripts, en millions."""
    return f"cache lu {usage.cache_read / 1e6:5.1f} M · écrit {usage.cache_write / 1e6:4.1f} M"


def tokens(usage: Usage) -> str:
    """La ligne de jetons de la session : sa sortie, puis son cache."""
    return f"sortie {usage.output / 1e3:6.0f} k · {cached(usage)}"


def relays(events: Sequence[Event]) -> list[datetime]:
    """Le premier instant de chaque transcript après le premier : les heures de relais."""
    first: dict[int, datetime] = {}
    for event in events:
        first.setdefault(event.source, event.when)
    # Dans l'ordre du **temps**, pas dans celui des arguments : le skill autorise à donner
    # les transcripts dans n'importe quel ordre, et classer par index d'argument annonçait
    # alors le début de la session comme heure de relais. Mesuré le 2026-10-09.
    return sorted(first.values())[1:]


@dataclass(frozen=True)
class Measures:
    """Ce qu'une session a coûté — mesuré une fois, indépendamment de la mise en page.

    Séparer les deux rend les chiffres assertables sans passer par des chaînes de rapport, et
    c'est le seul moyen de relire la mise en page sans relire les mesures.
    """

    start: datetime
    end: datetime
    span: timedelta
    sessions: int
    relayed: list[datetime]
    blocked: list[Interval]
    reactivity: list[Interval]
    absences: list[Interval]
    windows: list[Interval]
    alone: timedelta
    launched: list[str]
    dangling: int
    calls: list[ToolCall]
    kinds: Counter[str]
    questions: int

    @property
    def workflows(self) -> int:
        """Combien de lancements sont des `Workflow` — notifiés ou non."""
        return self.launched.count(WORKFLOW_TOOL)

    @property
    def active(self) -> timedelta:
        """La durée de la session **hors absences** — le seul denominateur actionnable.

        Rapporter la réactivité à la session entière la dilue d'autant que le mainteneur a été
        absent, et le chiffre flatte alors la pipeline sans que rien n'ait été amélioré — le
        sens d'erreur même d'obs 41. Hors absences, la même attente pèse ce que la pipeline peut
        réellement réduire. Les absences, elles, se rapportent à la session : c'est leur poids
        réel.

        Les deux dénominateurs sont épinglés, sur un montage dont les durées sont celles du
        transcript synthétique, par
        `test_la_reactivite_se_rapporte_au_temps_actif_et_les_absences_a_la_session` — seul
        endroit où ces pourcentages vivent. Aucun n'est recopié ici : un chiffre pris sur une
        session réelle n'est pas reproductible, son transcript pouvant avoir disparu (obs 73),
        et l'arrondi d'affichage des durées ne redonne **pas toujours** le pourcentage que le
        rapport imprime, qui se calcule sur les secondes — il le redonne sur le montage ci-dessus
        (15 min sur 0 h 45 affichés, 33 % imprimés), et pas sur une session dont les durées
        tombent entre deux minutes.
        """
        return self.span - total(self.absences)


def measure(events: Sequence[Event], agents: Sequence[Subagent] = ()) -> Measures:
    """Mesure une session à partir de ses événements, sans rien mettre en forme."""
    if not events:
        raise ValueError("aucun événement à mesurer — transcripts vides ou illisibles")
    calls = tool_calls(events)
    runs = agent_runs(events, calls)
    # Les fenêtres se déduisent des `runs` déjà calculés, une seule fois : les recalculer à
    # chaque usage coûtait un parcours complet de la liste d'événements par usage — sensible
    # sur un transcript de plusieurs dizaines de méga-octets. S'y ajoutent les contacts lus dans
    # les transcripts des sous-agents : une notification ne borne que le premier contact d'un
    # agent de fond, et un agent au premier plan n'en a pas.
    windows = union(
        [run.window for run in runs] + [c.window for agent in agents for c in agent.contacts]
    )
    seen = {run.uid for run in runs} | {agent.launcher for agent in agents}
    launched = launched_subagents(events, calls)
    # Une attente se classe sur sa durée **brute**, puis perd le temps des sous-agents : retiré
    # d'abord, un sous-agent au milieu d'une absence la coupait en morceaux de moins d'une heure,
    # reclassés en réactivité (`test_une_absence_reste_une_absence_quand_un_sous_agent_y_travaille`).
    raw_reactivity, raw_absences = split_waits(waits(events, calls))
    reactivity, absences = without(raw_reactivity, windows), without(raw_absences, windows)
    blocked = union(reactivity + absences)
    start, end = events[0].when, events[-1].when
    span = end - start
    return Measures(
        start=start,
        end=end,
        span=span,
        sessions=max((event.source for event in events), default=0) + 1,
        relayed=relays(events),
        blocked=blocked,
        reactivity=reactivity,
        absences=absences,
        windows=windows,
        alone=span - total(union(list(blocked) + list(windows))),
        launched=[tool for _, (tool, _) in launched],
        dangling=sum(1 for uid, _ in launched if uid not in seen),
        calls=calls,
        kinds=Counter(event.kind for event in events),
        questions=sum(1 for call in calls if call.name == QUESTION_TOOL),
    )


def contact_line(contact: Contact) -> str:
    """Une ligne de contact : sa fenêtre, ses appels, son contexte final et le cache consommé —
    pas la sortie, que le transcript d'un sous-agent ne porte pas de façon fiable (`consumed`)."""
    start, end = contact.window
    return (
        f"    {local(start)} → {local(end)}   {hm(end - start):>7}   {contact.calls:>4} appels   "
        f"contexte final {thousands(contact.context):>9}   "
        f"cache lu {thousands(contact.used.cache_read):>11}"
        f" · écrit {thousands(contact.used.cache_write):>9}"
    )


def agent_lines(agent: Subagent) -> list[str]:
    """Le titre d'un sous-agent, puis une ligne par contact."""
    count = len(agent.contacts)
    title = f"  {agent.role} « {agent.name} » — {count} contact{'s' if count > 1 else ''}"
    return [title, *(contact_line(contact) for contact in agent.contacts)]


def report(events: Sequence[Event], session: Usage, agents: Sequence[Subagent]) -> str:
    """Le bilan, prêt à être recopié dans une rétrospective.

    L'ordre des lignes est celui de leur lecture : l'attente **hors absences** d'abord, parce
    que c'est la seule que la pipeline peut réduire ; l'agrégat brut ensuite, pour mémoire.

    Deux dénominateurs, et chaque ligne dit le sien. Ce que la pipeline peut réduire se rapporte
    au temps **actif** (session moins absences) ; les absences et l'attente totale se rapportent
    à la session. Tout rapporter à la session diluait la réactivité d'autant que le mainteneur
    avait été absent, d'un facteur qui croît avec l'absence — et un pourcentage dont le
    dénominateur ne se lit pas est le défaut, pas le chiffre. Les deux parts sont épinglées par
    `test_la_reactivite_se_rapporte_au_temps_actif_et_les_absences_a_la_session`.

    Chaque sous-agent se rend **contact par contact**, consommation comprise : c'est la seule
    grandeur que deux lots peuvent comparer, un total dépendant de la taille du delta relu.
    """
    m = measure(events, agents)
    humans = m.kinds["human"]
    used = consumed(agents)
    relayed = ", ".join(f"relais à {local(moment)}" for moment in m.relayed)

    def row(label: str, duration: timedelta, basis: timedelta, note: str = "") -> str:
        """Une ligne « libellé · durée · part de son dénominateur »."""
        share = f"{duration / basis:4.0%}" if basis else "   —"
        return f"{label:<28} {hm(duration):>9}   {share}{'   ' + note if note else ''}"

    def typical(windows: Sequence[Interval]) -> str:
        return hm(median([end - start for start, end in windows])) if windows else "—"

    lines = [
        (
            f"session          {local(m.start)} → {local(m.end)}   {hm(m.span)}   "
            f"(sessions : {m.sessions}{', ' + relayed if relayed else ''})"
        ),
        f"actif (hors absences)        {hm(m.active):>9}   — dénominateur des trois lignes qui suivent",
        row(
            "réactivité (< 1 h)",
            total(m.reactivity),
            m.active,
            f"({len(m.reactivity)} attentes, médiane {typical(m.reactivity)})",
        ),
        row(
            "sous-agents en cours",
            total(m.windows),
            m.active,
            f"({len(m.launched)} lancés, dont {m.workflows} workflows)",
        ),
        row("agent seul", m.alone, m.active),
        row(
            "absences (≥ 1 h)", total(m.absences), m.span, f"({len(m.absences)} — détail plus bas)"
        ),
        row("attente totale", total(m.blocked), m.span),
        *(
            [f"sous-agents sans notification de fin ni transcript rattaché : {m.dangling}"]
            if m.dangling
            else []
        ),
        f"jetons de la session         {tokens(session)}",
        (
            f"jetons des sous-agents       {cached(used)} · sortie non mesurée"
            f"   ({used.transcripts} transcripts)"
        ),
        (
            f"points de contact humains    {humans + m.questions:>9}   "
            f"(messages {humans}, questions formelles {m.questions}, "
            f"pairs {m.kinds['peer']}, injectés {m.kinds['system']})"
        ),
        *(
            ["par agent — consommation lue dans ses transcripts, contact par contact :"]
            if agents
            else []
        ),
        *(line for agent in agents for line in agent_lines(agent)),
        *(["absences, une à une :"] if m.absences else []),
        *(f"  {local(start)} → {local(end)}   {hm(end - start)}" for start, end in m.absences),
        "appels d'outils : "
        + ", ".join(
            f"{name} {count}" for name, count in Counter(c.name for c in m.calls).most_common(8)
        ),
    ]
    return "\n".join(lines)


def say(text: str) -> None:
    """Écrit une ligne sur la sortie standard en octets UTF-8, quelle que soit la console.

    La console du poste est en cp1252, et le rapport porte des `→` et des `≥` : imprimé tel quel,
    il lèverait `UnicodeEncodeError`. Les octets vont au tampon **sans** envelopper `sys.stdout` :
    un `TextIOWrapper` collecté ferme le flux qu'il enveloppe, et un appelant en processus — la
    suite de tests — perd sa sortie derrière. Même forme que `dire` de `mutation.py`.
    """
    sys.stdout.flush()
    sys.stdout.buffer.write(f"{text}\n".encode())
    sys.stdout.buffer.flush()


def main(argv: Sequence[str]) -> int:
    """Point d'entrée : un ou plusieurs transcripts de la **même** session, relais compris.

    Un transcript absent se **dit**, il ne fait ni planter le script ni rendre en silence un
    bilan sur la moitié du cycle : le harnais a le droit de supprimer un transcript entre deux
    sessions (obs 73), et le relevé que la session sortante a déposé s'additionne alors à la main.
    """
    if not argv:
        say(str(__doc__))
        return 2
    paths = [Path(argument) for argument in argv]
    present = [path for path in paths if path.is_file()]
    absent = ", ".join(str(path) for path in paths if not path.is_file())
    if absent:
        partial = " (bilan partiel : additionner le relevé déposé par chaque session absente)"
        say(
            f"transcripts demandés {len(paths)}, lus {len(present)} — absents : {absent}"
            + (partial if present else "")
        )
    events = read_events(present)
    if not events:
        say("transcripts vides ou illisibles")
        return 1
    say(report(events, token_usage(present), subagents(present)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
