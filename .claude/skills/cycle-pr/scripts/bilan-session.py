"""Bilan chiffré d'une session Claude Code, lu dans ses transcripts JSONL.

Usage : python bilan-session.py <transcript.jsonl> [<relais.jsonl> …]

Un cycle qui a rempli un contexte a **plusieurs** transcripts : le script en accepte autant
qu'on lui en donne, les fusionne dans l'ordre du temps et rend l'heure de chaque relais (obs 40).

Rend, sans double compte : la durée de la session ; l'attente du mainteneur **scindée** en
réactivité (moins d'une heure) et absences (une heure ou plus), le pourcentage hors absences en
tête — les deux n'ont ni la même cause ni le même remède, et leur somme se lit comme un défaut
de la pipeline alors qu'une nuit relève du calendrier (obs 43) ; le temps des sous-agents et des
workflows, **retiré** de l'attente du mainteneur, qui serait sinon facturé du temps qu'il n'a pas
fait attendre ; le temps d'agent seul ; les jetons facturés, globaux et **par agent** ; les points
de contact humains et les appels d'outils.

Python 3.11 ou plus, bibliothèque standard seule.
"""

import io
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
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

# Une notification de fin de tâche, telle que le harnais l'injecte : une pièce jointe
# `queued_command` dont le `commandMode` le dit. Un test sur la *ligne* entière — la chaîne
# `<task-notification` apparaît aussi dans le texte du prompt système d'un `prompt_snapshot` —
# compte ces citations comme des fins de sous-agent.
NOTIFICATION_MODE = "task-notification"
TOOL_USE_ID = re.compile(r"<tool-use-id>(?P<id>[^<]+)</tool-use-id>")
STATUS_COMPLETED = "<status>completed</status>"
SUMMARY = re.compile(r"<summary>(?P<text>.*?)</summary>", re.DOTALL)
SUBAGENT_TOKENS = re.compile(r"<subagent_tokens>(?P<count>\d+)</subagent_tokens>")
# `Agent "<nom>" finished`, `Workflow "<nom>" completed` : le nom seul nous intéresse.
QUOTED_NAME = re.compile(r'"(?P<name>[^"]+)"')

# Les deux balises qu'un message de pair peut porter. N'en chercher qu'une classait les messages
# d'équipier portant l'autre comme des messages du mainteneur — la classe avait été fermée sur
# la seule forme qui l'avait révélée. Dénombrement et population : `FORMES_REELLES` dans la
# suite, seul endroit où les chiffres vivent — recopiés ici, ils dérivent au recensement suivant.
PEER_TAGS = ("<cross-session-message", "<agent-message")

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
# Sous cette forme, le découpage est unique et le coût redevient linéaire — là où le motif naïf
# n'atteint pas 25 blocs. Relevé et commande dans
# `test_une_suite_de_blocs_qui_echoue_ne_fait_pas_exploser_le_classement`, jamais ici.
INJECTED_BLOCKS = re.compile(r"\A(?:\s*<([a-z][a-z0-9_-]*)>(?:(?!</\1>).)*</\1>)+\s*\Z", re.DOTALL)

# Et les formes injectées qui ne sont **pas** des balises — à énumérer, elles. `Caveat: The
# messages below were generated` y figurait et n'a jamais mordu : la forme réelle est
# `<local-command-caveat>Caveat: …`, donc une balise. Dénombrement : `FORMES_REELLES`.
INJECTED = (
    "Base directory for this skill:",
    "[Cross-session idle notice]",
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
        label: pour une notification, le nom de l'agent, lu dans son `<summary>`.
        tokens: pour une notification, les jetons que le sous-agent a facturés.
        source: le rang de son transcript, pour datar les relais.
    """

    when: datetime
    kind: str
    uses: list[tuple[str, str]] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    ends: str = ""
    label: str = ""
    tokens: int = 0
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
    """Un sous-agent ou un workflow, de son lancement à sa notification de fin."""

    name: str
    tool: str
    tokens: int
    window: Interval


@dataclass
class Usage:
    """Jetons facturés par un ensemble de transcripts, un seul compte par message."""

    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    transcripts: int = 0


def token_usage(paths: Sequence[Path]) -> Usage:
    """Somme l'`usage` du dernier enregistrement de chaque message assistant.

    Un message diffusé en plusieurs blocs occupe plusieurs lignes qui portent le même `id` et le
    même `usage` : une seule compte.
    """
    usage = Usage(transcripts=len(paths))
    for path in paths:
        last: dict[str, dict[str, int]] = {}
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    record: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = record.get("message") or {}
                if record.get("type") == "assistant" and message.get("usage"):
                    last[message.get("id") or record.get("uuid", "")] = message["usage"]
        for counts in last.values():
            usage.output += counts.get("output_tokens") or 0
            usage.cache_read += counts.get("cache_read_input_tokens") or 0
            usage.cache_write += counts.get("cache_creation_input_tokens") or 0
    return usage


def notification_event(when: datetime, attachment: Mapping[str, Any], source: int) -> Event | None:
    """L'événement d'une notification de fin de tâche, ou `None` si ce n'en est pas une.

    Seul un `commandMode` égal à `task-notification` en fait une. Et seule une notification
    `completed` ferme une fenêtre : la même tâche peut notifier plusieurs fois, le harnais le dit
    lui-même dans sa note.
    """
    if attachment.get("commandMode") != NOTIFICATION_MODE:
        return None
    prompt = str(attachment.get("prompt", ""))
    if STATUS_COMPLETED not in prompt:
        return None
    call = TOOL_USE_ID.search(prompt)
    summary = SUMMARY.search(prompt)
    quoted = QUOTED_NAME.search(summary.group("text")) if summary else None
    tokens = SUBAGENT_TOKENS.search(prompt)
    return Event(
        when,
        "notification",
        ends=call.group("id") if call else "",
        label=quoted.group("name") if quoted else "",
        tokens=int(tokens.group("count")) if tokens else 0,
        source=source,
    )


def read_events(paths: Sequence[Path | str]) -> list[Event]:
    """Lit tous les transcripts d'une session et rend leurs événements, ordonnés par le temps."""
    events: list[Event] = []
    for source, path in enumerate(paths):
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    record: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not record.get("timestamp") or record.get("isSidechain"):
                    continue
                when = datetime.fromisoformat(record["timestamp"])
                if record.get("type") == "attachment":
                    attachment = cast(dict[str, Any], record.get("attachment") or {})
                    found = notification_event(when, attachment, source)
                    if found:
                        events.append(found)
                    continue
                if record.get("type") not in ("user", "assistant"):
                    continue
                content = (record.get("message") or {}).get("content", [])
                blocks = (
                    cast(list[dict[str, Any]], content)
                    if isinstance(content, list)
                    else [{"type": "text", "text": content}]
                )
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
    """La classe d'un message : d'où il vient, et s'il borne une attente du mainteneur.

    Un message de pair **commence** par « Another Claude session sent a message: » et porte la
    balise plus loin : le chercher en tête le classait humain. Un texte injecté par le harnais —
    chargement de skill, commande, notification — est dans le rôle `user` sans qu'un humain
    l'ait tapé. Une balise de contexte **suivie** d'un texte reste un message du mainteneur :
    c'est lui qui a tapé ce qui dépasse la balise.
    """
    if role == "assistant":
        return "assistant"
    if any(block.get("type") == "tool_result" for block in blocks):
        return "tool_result"
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if any(tag in text for tag in PEER_TAGS):
        return "peer"
    stripped = SYSTEM_REMINDER.sub("", text).strip()
    if not stripped or stripped.startswith(INJECTED) or INJECTED_BLOCKS.match(stripped):
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
        runs.append(AgentRun(end.label, tool, end.tokens, (started, end.when)))
    return runs


def launched_subagents(
    events: Sequence[Event], calls: Sequence[ToolCall]
) -> list[tuple[str, tuple[str, datetime]]]:
    """Tous les sous-agents et workflows **lancés**, par ordre de lancement.

    Distinct de `agent_runs`, qui ne garde que ceux dont la notification de fin est arrivée :
    un agent encore en cours, ou mort sans notifier, n'a pas de fenêtre et serait écarté sans
    laisser de trace. Le rapport compare les deux dénombrements pour que l'écart se voie.
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


def subagent_windows(events: Sequence[Event], calls: Sequence[ToolCall]) -> list[Interval]:
    """Les fenêtres pendant lesquelles un sous-agent ou un workflow tournait, fusionnées."""
    return union([run.window for run in agent_runs(events, calls)])


def blocked_windows(
    events: Sequence[Event],
    calls: Sequence[ToolCall],
    subagents: Sequence[Interval] | None = None,
) -> list[Interval]:
    """Dernière sortie de l'agent → message humain suivant, moins le temps des sous-agents.

    Le retrait est le cœur d'obs 41 : sans lui, une session à relectures parallèles facture au
    mainteneur le temps de ses sous-agents, et le chiffre cache précisément le gain que ces
    relectures produisent.
    """
    windows: list[Interval] = []
    last_agent: datetime | None = None
    for event in events:
        if event.kind == "assistant":
            last_agent = event.when
        elif event.kind == "human" and last_agent is not None:
            windows.append((last_agent, event.when))
            last_agent = None
    windows += [
        (call.started, call.started + call.duration) for call in calls if call.name == QUESTION_TOOL
    ]
    busy = subagent_windows(events, calls) if subagents is None else subagents
    return without(union(windows), busy)


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


def tokens(usage: Usage) -> str:
    """La ligne de jetons d'un ensemble de transcripts."""
    return (
        f"sortie {usage.output / 1e3:6.0f} k · cache lu {usage.cache_read / 1e6:5.1f} M"
        f" · écrit {usage.cache_write / 1e6:4.1f} M"
    )


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
    runs: list[AgentRun]
    dangling: int
    calls: list[ToolCall]
    kinds: Counter[str]
    questions: int

    @property
    def workflows(self) -> list[AgentRun]:
        """Les seuls sous-agents lancés par l'outil `Workflow`."""
        return [run for run in self.runs if run.tool == WORKFLOW_TOOL]

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
        (15 min sur 1 h 15 affichés, 20 % imprimés), et pas sur une session dont les durées
        tombent entre deux minutes.
        """
        return self.span - total(self.absences)


def measure(events: Sequence[Event]) -> Measures:
    """Mesure une session à partir de ses événements, sans rien mettre en forme."""
    if not events:
        raise ValueError("aucun événement à mesurer — transcripts vides ou illisibles")
    calls = tool_calls(events)
    runs = agent_runs(events, calls)
    # Les fenêtres se déduisent des `runs` déjà calculés, et sont **passées** à
    # `blocked_windows`. Chacune des trois les recalculait, soit trois parcours complets de la
    # liste d'événements — sensible sur un transcript de plusieurs dizaines de méga-octets.
    windows = union([run.window for run in runs])
    blocked = blocked_windows(events, calls, windows)
    reactivity, absences = split_waits(blocked)
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
        runs=runs,
        dangling=len(launched_subagents(events, calls)) - len(runs),
        calls=calls,
        kinds=Counter(event.kind for event in events),
        questions=sum(1 for call in calls if call.name == QUESTION_TOOL),
    )


def report(events: Sequence[Event], session: Usage, subagents: Usage) -> str:
    """Le bilan, prêt à être recopié dans une rétrospective.

    L'ordre des lignes est celui de leur lecture : l'attente **hors absences** d'abord, parce
    que c'est la seule que la pipeline peut réduire ; l'agrégat brut ensuite, pour mémoire.

    Deux dénominateurs, et chaque ligne dit le sien. Ce que la pipeline peut réduire se rapporte
    au temps **actif** (session moins absences) ; les absences et l'attente totale se rapportent
    à la session. Tout rapporter à la session diluait la réactivité d'autant que le mainteneur
    avait été absent, d'un facteur qui croît avec l'absence — et un pourcentage dont le
    dénominateur ne se lit pas est le défaut, pas le chiffre. Les deux parts sont épinglées par
    `test_la_reactivite_se_rapporte_au_temps_actif_et_les_absences_a_la_session`.
    """
    m = measure(events)
    humans = m.kinds["human"]
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
            f"(workflows {len(m.workflows)} / {len(m.runs)})",
        ),
        row("agent seul", m.alone, m.active),
        row(
            "absences (≥ 1 h)", total(m.absences), m.span, f"({len(m.absences)} — détail plus bas)"
        ),
        row("attente totale", total(m.blocked), m.span),
        *(
            [f"sous-agents sans notification de fin : {m.dangling} (encore en cours, ou morts)"]
            if m.dangling
            else []
        ),
        f"jetons de la session         {tokens(session)}",
        f"jetons des sous-agents       {tokens(subagents)}   ({subagents.transcripts} transcripts)",
        (
            f"points de contact humains    {humans + m.questions:>9}   "
            f"(messages {humans}, questions formelles {m.questions}, "
            f"pairs {m.kinds['peer']}, injectés {m.kinds['system']})"
        ),
        *(["par agent :"] if m.runs else []),
        *(
            f"  {local(run.window[0])} → {local(run.window[1])}   "
            f"{hm(total([run.window])):>7}   {thousands(run.tokens):>9} jetons   "
            f"{run.tool} « {run.name} »"
            for run in m.runs
        ),
        *(["absences, une à une :"] if m.absences else []),
        *(f"  {local(start)} → {local(end)}   {hm(end - start)}" for start, end in m.absences),
        "appels d'outils : "
        + ", ".join(
            f"{name} {count}" for name, count in Counter(c.name for c in m.calls).most_common(8)
        ),
    ]
    return "\n".join(lines)


def main(argv: Sequence[str]) -> int:
    """Point d'entrée : un ou plusieurs transcripts de la **même** session, relais compris."""
    if not argv:
        print(__doc__)
        return 2
    paths = [Path(argument) for argument in argv]
    events = read_events(paths)
    if not events:
        print("transcripts vides ou illisibles")
        return 1
    subagents = [found for path in paths for found in sorted(path.with_suffix("").rglob("*.jsonl"))]
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    out.write(report(events, token_usage(paths), token_usage(subagents)) + "\n")
    out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
