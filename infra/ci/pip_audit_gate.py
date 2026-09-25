"""Porte d'audit Python : `pip-audit`, sous le contrôle d'exceptions datées.

Une exception suspend un avis de sécurité jusqu'à une date. Passée cette date, la porte échoue
**avant** de lancer l'audit : une exception ne peut donc pas devenir permanente par oubli, ni
passer inaperçue derrière un audit par ailleurs vert (brief de #5, « Aucune exception sans date »).

Usage — les arguments autres que `--exceptions` sont transmis tels quels à `pip-audit` :

    python pip_audit_gate.py --exceptions <fichier.toml> [options de pip-audit…]

Code de sortie : celui de `pip-audit` si les exceptions sont valables, 1 sinon.
"""

import argparse
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

# Les champs d'une exception, tous obligatoires. Un champ en plus est refusé comme un champ en
# moins : c'est presque toujours une faute de frappe (`raison`, `expire`) sur un champ requis.
FIELDS = {"id", "reason", "expires"}


class InvalidWaivers(ValueError):
    """Le fichier d'exceptions ne se lit pas, ou une de ses entrées est incomplète."""


@dataclass(frozen=True)
class Waiver:
    """Une exception d'audit : l'avis `id` est ignoré jusqu'au `expires` inclus.

    La raison est exigée et vérifiée à la lecture, mais pas conservée : elle s'adresse au
    lecteur du fichier, et rien dans l'audit ne la consomme.
    """

    id: str
    expires: date


def load_waivers(path: Path) -> list[Waiver]:
    """Lit et valide les exceptions d'un fichier TOML, une table `[[exception]]` chacune.

    Le fichier est écrit à la main : tout ce qui n'a pas exactement la forme attendue est
    refusé, plutôt que d'être ignoré en silence ou de casser plus loin sur une comparaison.

    Args:
        path: le fichier d'exceptions.

    Returns:
        Les exceptions, dans l'ordre du fichier ; une liste vide si le fichier n'en a aucune.

    Raises:
        InvalidWaivers: fichier absent ou illisible, table autre que `exception`, entrée
            incomplète ou mal typée.
    """
    try:
        with path.open("rb") as file:
            document = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise InvalidWaivers(f"{path} : {error}") from error

    unknown = sorted(set(document) - {"exception"})
    if unknown:
        raise InvalidWaivers(f"{path} : clés inconnues {unknown}, seule `[[exception]]` est lue")
    entries: object = document.get("exception", [])
    if not isinstance(entries, list):
        raise InvalidWaivers(f"{path} : `exception` doit être une liste de tables `[[exception]]`")
    # `cast` et non une annotation : `isinstance` ne sait pas typer les éléments d'une liste lue
    # par `tomllib` ; chacun est validé un par un juste après.
    listed = cast(list[object], entries)
    return [parse_waiver(entry, number) for number, entry in enumerate(listed, start=1)]


def parse_waiver(entry: object, number: int) -> Waiver:
    """Valide une entrée du fichier et la convertit en exception.

    Args:
        entry: la table lue par `tomllib`.
        number: son rang dans le fichier, à partir de 1, pour que le message la désigne.

    Returns:
        L'exception correspondante.

    Raises:
        InvalidWaivers: champ manquant ou en trop, `id` ou `reason` vide, `expires` qui n'est
            pas une date TOML.
    """
    if not isinstance(entry, dict):
        raise InvalidWaivers(f"exception n° {number} : table attendue, {type(entry).__name__} lu")
    fields = cast(dict[str, object], entry)  # `tomllib` ne produit que des clés `str`
    if set(fields) != FIELDS:
        raise InvalidWaivers(
            f"exception n° {number} : champs {sorted(fields)}, attendus {sorted(FIELDS)}"
        )
    identifier, reason, expires = fields["id"], fields["reason"], fields["expires"]
    if not (isinstance(identifier, str) and identifier.strip()):
        raise InvalidWaivers(f"exception n° {number} : `id` doit être une chaîne non vide")
    if not (isinstance(reason, str) and reason.strip()):
        raise InvalidWaivers(f"exception n° {number} ({identifier}) : `reason` est vide")
    # `datetime` hérite de `date` : sans le test de type exact, une date et heure passerait ici,
    # puis ferait échouer la comparaison avec la date du jour.
    if type(expires) is not date:
        raise InvalidWaivers(
            f"exception n° {number} ({identifier}) : `expires` doit être une date TOML "
            "sans guillemets ni heure, par exemple 2026-12-31"
        )
    return Waiver(identifier, expires)


def main(argv: list[str] | None = None) -> int:
    """Valide les exceptions, puis lance `pip-audit` en leur transmettant les avis à ignorer.

    Args:
        argv: arguments de la ligne de commande, `sys.argv[1:]` par défaut.

    Returns:
        Le code de sortie : 1 si une exception a expiré, celui de `pip-audit` sinon.
    """
    parser = argparse.ArgumentParser(description="Lance pip-audit sous des exceptions datées.")
    parser.add_argument("--exceptions", type=Path, required=True)
    options, forwarded = parser.parse_known_args(argv)

    try:
        waivers = load_waivers(options.exceptions)
    except InvalidWaivers as error:
        print(f"fichier d'exceptions invalide — {error}", file=sys.stderr)
        return 1
    # La date du jour en UTC, celle de la CI : le poste et GitHub Actions rendent ainsi le même
    # verdict, y compris autour de minuit.
    today = datetime.now(UTC).date()
    expired = [waiver for waiver in waivers if waiver.expires < today]
    if expired:
        for waiver in expired:
            print(f"exception expirée le {waiver.expires} : {waiver.id}", file=sys.stderr)
        return 1

    ignored = [flag for waiver in waivers for flag in ("--ignore-vuln", waiver.id)]
    arguments = [*forwarded, *ignored]
    # Le journal de CI dit ainsi quelles exceptions étaient en vigueur lors de cet audit.
    print(shlex.join(["pip-audit", *arguments]), file=sys.stderr)
    return subprocess.run([sys.executable, "-m", "pip_audit", *arguments], check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
