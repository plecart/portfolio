"""Le journal d'un témoin d'outil : un script `sh` qui consigne chacun de ses appels avant de faire
ce que le test lui demande — rien, recopier son entrée, exécuter la vraie commande. Ce qu'un script
sous test a lancé se lit ensuite dans ce journal, argument par argument.

Arguments séparés par US (0x1f), appels par RS (0x1e) : un argument peut porter des sauts de ligne
— le texte d'un `sh -c`, par exemple.
"""

from pathlib import Path


def recording(log: Path) -> str:
    """Les lignes `sh` qui consignent l'appel — `$0`, puis chaque argument — dans `log`."""
    return (
        f'printf "%s\\037" "$0" "$@" >> "{log.as_posix()}"\nprintf "\\036" >> "{log.as_posix()}"\n'
    )


def recorded_calls(log: Path) -> list[list[str]]:
    """Les appels consignés dans `log`, dans l'ordre, chacun `[$0, argument…]` ; aucun si le témoin
    n'a jamais été appelé."""
    recorded = log.read_text(encoding="utf-8") if log.exists() else ""
    return [call.split("\x1f")[:-1] for call in recorded.split("\x1e")[:-1]]
