"""Bilan chiffré d'une session Claude Code, lu dans son transcript JSONL.

Usage : python bilan-session.py <transcript.jsonl>

Rend, sans double compte : la durée de la session, le temps bloqué sur le mainteneur (dernière
sortie de l'agent → message humain suivant, plus les questions formelles restées ouvertes), le
temps des sous-agents et workflows (lancement → notification de fin), le temps d'agent seul, les
attentes humaines de plus de cinq minutes, les points de contact humains, les appels d'outils, et
les jetons facturés — sortie, cache lu, cache écrit — de la session et de ses sous-agents, dont
les transcripts vivent sous `<répertoire du transcript>/<uuid de session>/`.
Python 3.11 ou plus, bibliothèque standard seule.
"""

import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

WAIT_THRESHOLD = timedelta(minutes=5)
SUBAGENT_TOOLS = {"Agent", "Task", "Workflow"}
QUESTION_TOOL = "AskUserQuestion"
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

Interval = tuple[datetime, datetime]


@dataclass
class Event:
    """Une ligne datée du transcript principal."""

    when: datetime
    kind: str  # assistant | tool_result | notification | peer | system | human
    uses: list[tuple[str, str]]  # (id, outil) lancés
    results: list[str]  # ids des outils rendus


@dataclass
class ToolCall:
    """Un appel d'outil dont le résultat est revenu."""

    name: str
    started: datetime
    duration: timedelta


@dataclass
class Usage:
    """Jetons facturés par un ensemble de transcripts, un seul compte par message."""

    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    transcripts: int = 0


def token_usage(paths: list[Path]) -> Usage:
    """Somme l'`usage` du dernier enregistrement de chaque message assistant.

    Un message diffusé en plusieurs blocs occupe plusieurs lignes qui portent le même `id` et le
    même `usage` : une seule compte.
    """
    usage = Usage(transcripts=len(paths))
    for path in paths:
        last: dict[str, dict[str, int]] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    obj: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = obj.get("message") or {}
                if obj.get("type") == "assistant" and message.get("usage"):
                    last[message.get("id") or obj.get("uuid", "")] = message["usage"]
        for u in last.values():
            usage.output += u.get("output_tokens") or 0
            usage.cache_read += u.get("cache_read_input_tokens") or 0
            usage.cache_write += u.get("cache_creation_input_tokens") or 0
    return usage


def tokens(u: Usage) -> str:
    return (
        f"sortie {u.output / 1e3:6.0f} k · cache lu {u.cache_read / 1e6:5.1f} M"
        f" · écrit {u.cache_write / 1e6:4.1f} M"
    )


def read_events(path: str) -> list[Event]:
    events: list[Event] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                obj: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not obj.get("timestamp") or obj.get("isSidechain"):
                continue
            when = datetime.fromisoformat(obj["timestamp"])
            # La fin d'un sous-agent arrive en pièce jointe, pas en message.
            if obj.get("type") == "attachment" and "<task-notification" in line:
                events.append(Event(when, "notification", [], []))
                continue
            if obj.get("type") not in ("user", "assistant"):
                continue
            content = obj.get("message", {}).get("content", [])
            blocks = (
                cast(list[dict[str, Any]], content)
                if isinstance(content, list)
                else [{"type": "text", "text": content}]
            )
            events.append(
                Event(
                    when,
                    classify(obj["type"], blocks),
                    [(b["id"], b["name"]) for b in blocks if b.get("type") == "tool_use"],
                    [b["tool_use_id"] for b in blocks if b.get("type") == "tool_result"],
                )
            )
    events.sort(key=lambda e: e.when)
    return events


def classify(role: str, blocks: list[dict[str, Any]]) -> str:
    if role == "assistant":
        return "assistant"
    if any(b.get("type") == "tool_result" for b in blocks):
        return "tool_result"
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if text.lstrip().startswith("<cross-session-message"):
        return "peer"
    if not SYSTEM_REMINDER.sub("", text).strip():
        return "system"
    return "human"


def tool_calls(events: list[Event]) -> list[ToolCall]:
    started: dict[str, tuple[str, datetime]] = {}
    for e in events:
        for uid, name in e.uses:
            started[uid] = (name, e.when)
    calls: list[ToolCall] = []
    for e in events:
        for uid in e.results:
            if uid in started:
                name, t0 = started[uid]
                calls.append(ToolCall(name, t0, e.when - t0))
    return calls


def subagent_windows(events: list[Event], calls: list[ToolCall]) -> list[Interval]:
    """Lancement d'un sous-agent → première notification de fin encore non attribuée."""
    notifications = [e.when for e in events if e.kind == "notification"]
    windows: list[Interval] = []
    for start in sorted(c.started for c in calls if c.name in SUBAGENT_TOOLS):
        later = [n for n in notifications if n > start]
        if later:
            windows.append((start, later[0]))
            notifications.remove(later[0])
    return union(windows)


def blocked_windows(events: list[Event], calls: list[ToolCall]) -> list[Interval]:
    """Dernière sortie de l'agent → message humain suivant, plus les questions formelles ouvertes."""
    windows: list[Interval] = []
    last_agent: datetime | None = None
    for e in events:
        if e.kind == "assistant":
            last_agent = e.when
        elif e.kind == "human" and last_agent is not None:
            windows.append((last_agent, e.when))
            last_agent = None
    windows += [(c.started, c.started + c.duration) for c in calls if c.name == QUESTION_TOOL]
    return union(windows)


def union(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def total(intervals: list[Interval]) -> timedelta:
    return sum((b - a for a, b in intervals), timedelta())


def hm(d: timedelta) -> str:
    minutes = int(d.total_seconds() // 60)
    return f"{minutes // 60} h {minutes % 60:02d}"


def local(t: datetime) -> str:
    return f"{t.astimezone():%H:%M}"


def report(events: list[Event], session: Usage, subagents: Usage) -> str:
    calls = tool_calls(events)
    blocked = blocked_windows(events, calls)
    reviews = subagent_windows(events, calls)
    start, end = events[0].when, events[-1].when
    span = end - start
    idle = total(union(blocked + reviews))
    kinds = Counter(e.kind for e in events)
    questions = sum(1 for c in calls if c.name == QUESTION_TOOL)
    by_tool = Counter(c.name for c in calls)
    contacts = f"(messages {kinds['human']}, questions formelles {questions})"

    lines = [
        f"session          {local(start)} → {local(end)}   {hm(span)}",
        f"bloqué sur le mainteneur     {hm(total(blocked)):>9}   {total(blocked) / span:4.0%}",
        f"sous-agents en cours         {hm(total(reviews)):>9}   {total(reviews) / span:4.0%}",
        f"agent seul                   {hm(span - idle):>9}   {(span - idle) / span:4.0%}",
        f"jetons de la session         {tokens(session)}",
        f"jetons des sous-agents       {tokens(subagents)}   ({subagents.transcripts} transcripts)",
        f"points de contact humains    {kinds['human'] + questions:>9}   {contacts}",
        "sous-agents :",
        *(f"  {local(a)} → {local(b)}   {hm(b - a)}" for a, b in reviews),
        f"attentes humaines de plus de {WAIT_THRESHOLD.seconds // 60} min :",
        *(f"  {local(a)} → {local(b)}   {hm(b - a)}" for a, b in blocked if b - a > WAIT_THRESHOLD),
        "appels d'outils : " + ", ".join(f"{name} {n}" for name, n in by_tool.most_common(8)),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    transcript = read_events(sys.argv[1])
    if not transcript:
        sys.exit("transcript vide ou illisible")
    main_path = Path(sys.argv[1])
    session = token_usage([main_path])
    subagents = token_usage(sorted(main_path.with_suffix("").rglob("*.jsonl")))
    io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8").write(
        report(transcript, session, subagents) + "\n"
    )
