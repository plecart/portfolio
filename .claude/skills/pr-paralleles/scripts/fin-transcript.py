"""Reconstitue le récit d'une session Claude Code disparue, depuis ses transcripts JSONL.

Usage : python fin-transcript.py <transcript.jsonl> [<nombre de tours>]

Une session tuée par l'arrêt de l'application n'écrit aucune passation. Le seul récit de l'étape
qu'elle avait atteinte est la fin de son transcript ; le seul récit de ses sous-agents est le leur,
et un sous-agent lancé en fond avant l'arrêt est perdu sans avoir rien rendu (obs 54). Ce script
rend les trois choses qu'on cherche alors, et rien d'autre :

1. **la fin de l'échange** — les derniers tours, pour savoir où elle en était ;
2. **les messages du mainteneur** — les décisions prises en séance, seule matière du transcript qui
   ne se re-dérive pas des artefacts ;
3. **le dernier texte de chaque sous-agent** — avec son rôle et sa description.

Ce qui est **prouvé** se lit sur les artefacts — tête, base, CI, body de PR, worktrees : ce script
n'en touche aucun. Il rend le *récit*, et la passation qu'on écrit ensuite doit séparer les deux.

Les sous-agents se trouvent seuls, à côté du transcript : `<transcript sans .jsonl>/subagents/`.

Python 3.11 ou plus, bibliothèque standard seule.
"""

import json
import re
import sys
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any

TOURS = 12
EXTRAIT = 400

# Les blocs que le harnais injecte dans le rôle `user` : `<task-notification>`, `<command-message>`,
# `<system-reminder>`, `<ide_opened_file>`… Un `sub` **non gourmand** les retire ; ce qui reste est
# de la main du mainteneur. Le nom se lit sans attribut à dessein — `<pasted_content id="…">` en
# porte un, et son contenu est du texte que le mainteneur a collé, donc il doit rester.
#
# `bilan-session.py` (skill `cycle-pr`) porte une version plus stricte de cette distinction, parce
# qu'il **compte** les contacts humains et doit donc trancher pour chaque message. Ici on ne compte
# rien : on rend du texte à lire, et un retrait trop généreux laisse voir un message vide, pas un
# faux chiffre. Les deux ne s'importent pas l'un l'autre à dessein — un skill recopié dans un dépôt
# sans l'autre doit fonctionner seul.
BLOC_INJECTE = re.compile(r"<(?P<balise>[a-z][a-z0-9_-]*)>.*?</(?P=balise)>", re.DOTALL)

# Les textes injectés qui ne sont pas des blocs balisés.
PREFIXES_INJECTES = (
    "Base directory for this skill:",
    "[Cross-session idle notice]",
    "[Request interrupted",
    "Another Claude session sent a message",
    "This session is being continued from a previous conversation",
)


def enregistrements(chemin: Path) -> Iterator[dict[str, Any]]:
    """Les lignes JSON d'un transcript, une par une, les illisibles sautées.

    Args:
        chemin: le fichier `.jsonl` à lire.

    Yields:
        Chaque enregistrement décodé. Un transcript de plusieurs dizaines de mégaoctets se lit
        ligne à ligne : rien n'est gardé en mémoire que ce que l'appelant retient.
    """
    with open(chemin, encoding="utf-8") as flux:
        for ligne in flux:
            try:
                yield json.loads(ligne)
            except json.JSONDecodeError:
                continue


def texte(enregistrement: dict[str, Any]) -> str:
    """Le texte d'un enregistrement, blocs concaténés, ou la chaîne vide s'il n'en porte pas."""
    contenu = (enregistrement.get("message") or {}).get("content")
    if isinstance(contenu, str):
        return contenu
    if not isinstance(contenu, list):
        return ""
    blocs: list[dict[str, Any]] = contenu
    return "".join(
        str(bloc.get("text", ""))
        for bloc in blocs
        if isinstance(bloc, dict) and bloc.get("type") == "text"
    )


def de_la_main_du_mainteneur(brut: str) -> bool:
    """Vrai si ce texte du rôle `user` a été tapé par un humain, et non injecté par le harnais.

    Un message n'est injecté que s'il ne reste **rien** après retrait des blocs balisés : le
    harnais préfixe parfois le texte humain d'un bloc de contexte au lieu de l'injecter seul
    (`<ide_opened_file>…</ide_opened_file>oui go`), et s'arrêter à la tête perdrait ce « oui go ».
    """
    reste = BLOC_INJECTE.sub("", brut).strip()
    return bool(reste) and not reste.startswith(PREFIXES_INJECTES)


def extrait(brut: str) -> str:
    """Le texte réduit à une ligne d'au plus `EXTRAIT` caractères, pour un rapport lisible."""
    plat = " ".join(brut.split())
    return plat if len(plat) <= EXTRAIT else f"{plat[:EXTRAIT]}…"


def sous_agents(transcript: Path) -> list[Path]:
    """Les transcripts des sous-agents de cette session, triés par nom.

    Args:
        transcript: le `.jsonl` de la session.

    Returns:
        Les `.jsonl` de `<transcript sans extension>/subagents/`, ou une liste vide si ce dossier
        n'existe pas — une session sans sous-agent est le cas normal, pas une anomalie.
    """
    dossier = transcript.with_suffix("") / "subagents"
    return sorted(dossier.glob("*.jsonl")) if dossier.is_dir() else []


def identite(agent: Path) -> str:
    """Le rôle et la description d'un sous-agent, lus dans son `.meta.json` voisin."""
    meta = agent.with_suffix(".meta.json")
    if not meta.is_file():
        return agent.stem
    try:
        champs: dict[str, Any] = json.loads(meta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return agent.stem
    return f"{champs.get('agentType', '?')} — {champs.get('description', agent.stem)}"


def dernier_texte(chemin: Path) -> tuple[str, str]:
    """L'horodatage et le texte du dernier message d'assistant de ce transcript.

    Returns:
        Le couple (horodatage, texte), ou `("", "")` si le transcript n'en contient aucun — un
        sous-agent mort avant son premier mot laisse un transcript sans texte d'assistant, et
        c'est une information, pas une erreur.
    """
    trouve = ("", "")
    for enregistrement in enregistrements(chemin):
        if enregistrement.get("type") == "assistant" and (corps := texte(enregistrement).strip()):
            trouve = (str(enregistrement.get("timestamp", "")), corps)
    return trouve


def rapport(transcript: Path, tours: int) -> list[str]:
    """Les trois sections du rapport, prêtes à imprimer."""
    derniers: deque[tuple[str, str, str]] = deque(maxlen=tours)
    humains: list[tuple[str, str]] = []
    for enregistrement in enregistrements(transcript):
        type_ = enregistrement.get("type")
        if type_ not in ("user", "assistant"):
            continue
        brut = texte(enregistrement).strip()
        if not brut:
            continue
        horodatage = str(enregistrement.get("timestamp", ""))
        derniers.append((horodatage, str(type_), brut))
        if type_ == "user" and de_la_main_du_mainteneur(brut):
            humains.append((horodatage, BLOC_INJECTE.sub("", brut).strip()))

    agents = sous_agents(transcript)
    puces_humains = [f"- `{quand}` {extrait(corps)}" for quand, corps in humains]
    puces_agents: list[str] = []
    for agent in agents:
        quand, corps = dernier_texte(agent)
        rendu = f"`{quand}` {extrait(corps)}" if corps else "**aucun texte** — mort avant de rendre"
        puces_agents += [f"- **{identite(agent)}**", f"  {rendu}"]

    return [
        f"# Fin de transcript — {transcript.name}",
        "",
        f"## Derniers tours ({len(derniers)} sur les {tours} demandés)",
        "",
        *[f"- `{quand}` **{role}** : {extrait(corps)}" for quand, role, corps in derniers],
        "",
        f"## Messages du mainteneur ({len(humains)})",
        "",
        *(puces_humains or ["- aucun"]),
        "",
        f"## Sous-agents ({len(agents)})",
        "",
        *(puces_agents or ["- aucun"]),
    ]


def main(arguments: list[str]) -> int:
    """Imprime le rapport, ou l'usage en sortant en 2."""
    if not arguments or arguments[0] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        return 2
    transcript = Path(arguments[0])
    if not transcript.is_file():
        print(f"transcript introuvable : {transcript}", file=sys.stderr)
        return 1
    tours = int(arguments[1]) if len(arguments) > 1 else TOURS
    if tours < 1:
        print(f"nombre de tours invalide : {tours}", file=sys.stderr)
        return 2
    print("\n".join(rapport(transcript, tours)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
