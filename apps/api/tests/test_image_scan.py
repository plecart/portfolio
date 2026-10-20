"""Tests du scan des images : la commande `make scan`, son étape en CI, ses exceptions datées.

Le scan lui-même tourne ailleurs — sur le poste par `make scan`, en CI dans les jobs `infra` et
`publish`. Ces tests gardent ce qui l'affaiblirait sans bruit : une option de Trivy retirée, une
étape de CI devenue indicative, une exception sans date. Trivy n'exige d'une exception que son
`id` — une entrée sans `expired_at` vaut pour toujours, une clé mal orthographiée est ignorée
sans un mot —, et la règle du projet est plus stricte (ADR 0014) : chaque exception porte
l'évaluation qui la fonde et la date où elle se refait.

Comme dans `test_supply_chain.py`, chaque garde est une fonction sur du texte, appliquée au dépôt
et à un recueil de formes — `SCAN_FORMS`, `CI_SCAN_FORMS`, `EXCEPTION_FORMS` —, chacune avec son
verdict attendu. Le dépôt ne montre qu'une forme, la conforme : c'est dans le recueil que chaque
garde se voit rouge, sans qu'il faille affaiblir le scan du dépôt pour l'éprouver.
"""

import re
import shlex
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
import yaml
from test_infra import (
    CI_WORKFLOW,
    MAKEFILE,
    PUBLISH_PREFIX,
    REPOSITORY_ROOT,
    built_images,
    make_dry_run,
    run_make,
)
from test_supply_chain import PINNED_IMAGE

EXCEPTIONS = REPOSITORY_ROOT / ".trivyignore.yaml"

# Une commande de scan telle que `make --dry-run` l'imprime : les options de `docker run`, l'image
# de Trivy, ses options, l'image scannée.
SCAN_COMMAND = re.compile(
    r"^docker run (?P<docker>.+) (?P<trivy>\S+) image (?P<options>.+) (?P<image>\S+)$",
    re.MULTILINE,
)

# La politique de scan (ADR 0014), en liste blanche : ces options de Trivy, toutes, et aucune
# autre. HIGH et CRITICAL bloquent, comme une image de base en fin de vie ; seules passent les
# exceptions datées de `.trivyignore.yaml`, que le rapport liste ; Trivy ne lit que les images que
# `make build` a chargées dans le moteur, et n'en tire aucune d'un registre sous le même nom.
#
# Une liste noire ne tenait pas : `--ignore-unfixed` s'écrit aussi `--ignore-status …`, et
# `--scanners secret`, `--pkg-types os` ou un second `--exit-code 0` vident le scan autrement
# (mesuré à la relecture de la PR #62, Trivy 0.74.0).
SCAN_OPTIONS = [
    "--severity HIGH,CRITICAL",
    "--exit-code 1",
    "--exit-on-eol 1",
    "--ignorefile .trivyignore.yaml",
    "--image-src docker",
    "--show-suppressed",
]

# Ce que le conteneur de Trivy reçoit du poste, par la fin de chaque montage : le socket du moteur,
# le cache de la base de vulnérabilités, et les exceptions en lecture seule, depuis le fichier que
# ces tests lisent — et rien d'autre. Une variable d'environnement (`-e TRIVY_IGNORE_UNFIXED=true`)
# ou un `trivy.yaml` monté dans son répertoire de travail régleraient Trivy sans toucher à ses
# options ; des exceptions montées d'un autre fichier échapperaient à leur garde.
SCAN_MOUNTS = [
    "/var/run/docker.sock:/var/run/docker.sock",
    ":/root/.cache/",
    "/.trivyignore.yaml:/.trivyignore.yaml:ro",
]
TRIVY_REPOSITORY = "ghcr.io/aquasecurity/trivy:"

# Les jobs de la CI qui construisent puis scannent les images, chacun avec ses deux commandes, mot
# pour mot : `infra` sur chaque PR qui le lance (ADR 0017), sous le nom du poste ; `publish` avant
# de pousser, sous le nom GHCR. L'image y est nommée sans étiquette : les exceptions des paquets du
# système suivent la cible `…/portfolio-<service> (<système> <version>)` du rapport de Trivy,
# qu'une étiquette changerait (mesuré à la PR #62). Mot pour mot, parce qu'une variable de plus sur
# la ligne de commande (`SCAN_FLAGS=`) prime sur le `Makefile`.
SCANNING_JOBS = {
    "infra": ("make build", "make scan"),
    "publish": (
        f"make build IMAGE_PREFIX={PUBLISH_PREFIX}",
        f"make scan IMAGE_PREFIX={PUBLISH_PREFIX}",
    ),
}
# Ce qui, posé sur le job, ferait ignorer l'échec du scan : le job toléré en échec, ou un
# environnement qui réglerait `make` (`MAKEFLAGS: -i`).
LENIENT_JOB_KEYS = ["continue-on-error", "env"]

# Les champs d'une exception, tous obligatoires. Un champ en plus est refusé comme un champ en
# moins, comme pour les exceptions de `pip-audit` : c'est presque toujours une faute de frappe sur
# un champ requis (`expire_at`), que Trivy ignorerait — l'exception deviendrait permanente.
#
# `paths` borne l'exception à l'image pour laquelle elle a été évaluée : « atteint par ce qui
# tourne » se juge image par image, et un seul fichier vaut pour toutes. Sans lui, une image
# ajoutée hériterait des exceptions des autres, scan vert, sans évaluation.
FIELDS = {"id", "paths", "statement", "expired_at"}

# La durée la plus longue d'une exception, décidée par le mainteneur à la PR #62 : passé ce délai,
# l'évaluation se refait. Sans cette borne, `2099-01-01` serait une exception permanente datée.
MAX_LIFETIME = timedelta(days=90)


# --- Les gardes : des fonctions sur du texte ---------------------------------------------------


def scanned_images(printed: str) -> set[str]:
    """Les images qu'une sortie de `make --dry-run scan` ferait scanner."""
    return {command["image"] for command in SCAN_COMMAND.finditer(printed)}


def scan_findings(printed: str) -> list[str]:
    """Ce qui, dans une sortie de `make --dry-run scan`, s'écarte de la politique de scan.

    Returns:
        Un constat par commande dont les options de Trivy ne sont pas exactement `SCAN_OPTIONS`,
        dont le conteneur reçoit autre chose que `SCAN_MOUNTS`, ou dont Trivy n'est pas l'image
        officielle, épinglée étiquette `x.y.z` et empreinte ; un constat si aucune commande n'est
        lue. Liste vide : chaque scan suit la politique.
    """
    commands = list(SCAN_COMMAND.finditer(printed))
    findings = [] if commands else ["aucune commande de scan lue — sa forme a-t-elle changé ?"]
    expected = Counter(" ".join(SCAN_OPTIONS).split())
    for command in commands:
        image, trivy = command["image"], command["trivy"]
        given = Counter(command["options"].split())
        if given != expected:
            findings.append(
                f"{image} : options de Trivy en trop {sorted((given - expected).elements())}, "
                f"manquantes {sorted((expected - given).elements())}"
            )
        # `--rm`, puis une paire `-v <montage>` par montage attendu.
        docker = shlex.split(command["docker"])
        mounted = [
            target for mount in docker[2::2] for target in SCAN_MOUNTS if mount.endswith(target)
        ]
        if docker[:1] + docker[1::2] != ["--rm", *["-v"] * len(SCAN_MOUNTS)] or sorted(
            mounted
        ) != sorted(SCAN_MOUNTS):
            findings.append(f"{image} : `docker run` porte {docker}, attendus {SCAN_MOUNTS}")
        if not (trivy.startswith(TRIVY_REPOSITORY) and PINNED_IMAGE.match(trivy)):
            findings.append(f"{image} : Trivy hors de son image officielle épinglée, {trivy}")
    return findings


def ci_scan_findings(workflow: str, name: str) -> list[str]:
    """Ce qui empêche un job de `SCANNING_JOBS` de scanner les images qu'il construit.

    Args:
        workflow: le texte du workflow.
        name: le nom du job, clé de `SCANNING_JOBS`, qui donne ses deux commandes.

    Returns:
        Un constat si le job manque, ou s'il ne lance pas ses deux commandes, le build puis le
        scan ; un si l'étape de scan porte autre chose que son nom et sa commande ; un par réglage
        qui ferait ignorer l'échec du scan — `continue-on-error` sur le job, ou un `env:` sur le
        job ou le workflow, par lequel `MAKEFLAGS: -i` atteindrait `make`. Liste vide : le scan
        bloque.
    """
    build, scan = SCANNING_JOBS[name]
    document = yaml.safe_load(workflow)
    job = document["jobs"].get(name)
    if job is None:
        return [f"aucun job `{name}`"]
    steps = job["steps"]
    commands = [step.get("run") for step in steps]
    if build not in commands or scan not in commands:
        return [f"le job `{name}` ne lance pas `{build}` et `{scan}`"]
    position = commands.index(scan)
    findings = [f"`{scan}` avant `{build}`"] if position < commands.index(build) else []
    extra = sorted(set(steps[position]) - {"name", "run"})
    if extra:
        findings.append(f"l'étape de scan porte {extra}")
    findings += [f"le job `{name}` porte `{key}`" for key in LENIENT_JOB_KEYS if key in job]
    if "env" in document:
        findings.append("le workflow porte `env`")
    return findings


def scan_fails_with_trivy(makefile: Path = MAKEFILE) -> bool:
    """`make scan` sort-il en échec quand Trivy échoue ?

    Trivy est remplacé par `false` : rien n'est scanné, seul le code de sortie de `make` est lu.
    `make --dry-run` ne le dirait pas — il n'imprime ni le `-` qui préfixe une recette, ni
    `.IGNORE`, ni `MAKEFLAGS`.

    Args:
        makefile: le fichier de commandes — celui du dépôt, ou une copie témoin.
    """
    return run_make("scan", makefile=makefile, TRIVY="false").returncode != 0


def is_text(value: object) -> bool:
    """La valeur est-elle une chaîne qui porte autre chose que des espaces ?"""
    return isinstance(value, str) and bool(value.strip())


def is_bounded_path(value: object) -> bool:
    """La valeur est-elle un motif de chemin qui nomme quelque chose ?

    `**`, `*` ou `**/*` valent pour toute cible, donc pour toute image : l'exception ne serait
    bornée à rien (mesuré à la relecture de la PR #62 : `paths: ["**"]` passait).
    """
    return is_text(value) and bool(cast(str, value).strip("*?/ "))


def entry_findings(entry: object, today: date) -> list[str]:
    """Ce qui manque à une entrée pour être une exception valable à la date `today`.

    Args:
        entry: l'entrée lue par l'analyseur YAML.
        today: la date du jour, en UTC.

    Returns:
        Un constat par défaut relevé ; liste vide si l'exception est complète et en vigueur.
    """
    if not isinstance(entry, dict):
        return [f"table attendue, {type(entry).__name__} lu"]
    fields = cast(dict[object, object], entry)
    if set(fields) != FIELDS:
        return [f"champs {sorted(map(str, fields))}, attendus {sorted(FIELDS)}"]
    findings: list[str] = []
    for name in ("id", "statement"):
        if not is_text(fields[name]):
            findings.append(f"`{name}` doit être une chaîne non vide")
    paths = fields["paths"]
    if not (
        isinstance(paths, list) and paths and all(map(is_bounded_path, cast(list[object], paths)))
    ):
        findings.append("`paths` doit être une liste non vide de chemins qui nomment une cible")
    expired_at = fields["expired_at"]
    # `datetime` hérite de `date` : sans le test de type exact, une date et heure passerait ici.
    if type(expired_at) is not date:
        findings.append("`expired_at` doit être une date YAML sans guillemets ni heure")
    # Trivy compare l'instant présent à minuit UTC du jour indiqué (`IgnoreFindings.Prune`,
    # `pkg/result/ignore.go`) : l'exception cesse de valoir dès le début de ce jour-là.
    elif expired_at <= today:
        findings.append(f"{fields['id']} : expirée depuis le {expired_at}, évaluation à refaire")
    elif expired_at > today + MAX_LIFETIME:
        findings.append(f"`expired_at` au-delà de {MAX_LIFETIME.days} jours : {expired_at}")
    return findings


def exception_findings(text: str, today: date) -> list[str]:
    """Ce qui, dans un fichier d'exceptions de Trivy, n'est pas une exception valable.

    Toutes les sections sont lues, quel que soit leur nom : une exception de secret ou de
    mauvaise configuration suit la même règle qu'une exception de vulnérabilité.

    Args:
        text: le contenu du fichier, au format YAML de Trivy.
        today: la date du jour, en UTC — celle de la CI et celle que Trivy compare.

    Returns:
        Un constat par entrée fautive, préfixé de sa section et de son rang ; liste vide si tout
        est valable, ou si le fichier ne porte aucune exception.
    """
    document: object = yaml.safe_load(text) or {}
    if not isinstance(document, dict):
        return [f"table de sections attendue, {type(document).__name__} lu"]
    findings: list[str] = []
    for section, entries in cast(dict[object, object], document).items():
        if not isinstance(entries, list):
            findings.append(f"{section} : liste d'exceptions attendue")
            continue
        for number, entry in enumerate(cast(list[object], entries), start=1):
            findings.extend(
                f"{section} n° {number} : {finding}" for finding in entry_findings(entry, today)
            )
    return findings


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

TRIVY_PINNED = TRIVY_REPOSITORY + "0.74.0@sha256:" + "a" * 64
SOCKET_MOUNT = "-v /var/run/docker.sock:/var/run/docker.sock"
CACHE_MOUNT = "-v portfolio-trivy-cache:/root/.cache/"
EXCEPTIONS_MOUNT = '-v "/depot/.trivyignore.yaml:/.trivyignore.yaml:ro"'
DOCKER_OPTIONS = ["--rm", SOCKET_MOUNT, CACHE_MOUNT, EXCEPTIONS_MOUNT]


def scan_command(
    trivy: str = TRIVY_PINNED,
    options: Iterable[str] = SCAN_OPTIONS,
    docker: Iterable[str] = DOCKER_OPTIONS,
) -> str:
    """Une commande de scan telle que `make --dry-run` l'imprime, conforme par défaut."""
    return f"docker run {' '.join(docker)} {trivy} image {' '.join(options)} portfolio-api\n"


# Forme → constat attendu (`True`) ou aucun (`False`). Les options en trop sont celles dont
# l'effet a été mesuré : chacune laisse le scan vert sur une image vulnérable.
SCAN_FORMS = {
    "conforme": (scan_command(), False),
    "dépôt dont le chemin porte une espace": (
        scan_command(
            docker=[
                "--rm",
                SOCKET_MOUNT,
                CACHE_MOUNT,
                '-v "/mes projets/depot/.trivyignore.yaml:/.trivyignore.yaml:ro"',
            ]
        ),
        False,
    ),
    **{
        f"sans {option}": (scan_command(options=[o for o in SCAN_OPTIONS if o != option]), True)
        for option in SCAN_OPTIONS
    },
    **{
        f"avec {option}": (scan_command(options=[*SCAN_OPTIONS, option]), True)
        for option in [
            "--ignore-unfixed",
            "--ignore-status affected,will_not_fix,fix_deferred",
            "--exit-code 0",
            "--scanners secret",
            "--pkg-types os",
        ]
    },
    **{
        f"docker run {option}": (scan_command(docker=[*DOCKER_OPTIONS, option]), True)
        for option in [
            "-e TRIVY_IGNORE_UNFIXED=true",
            "--env TRIVY_IGNORE_STATUS=affected",
            "--env-file infra/dev.env",
            "-v ./trivy.yaml:/trivy.yaml",
        ]
    },
    "sans le montage des exceptions": (
        scan_command(docker=["--rm", SOCKET_MOUNT, CACHE_MOUNT]),
        True,
    ),
    "exceptions montées depuis un autre fichier": (
        scan_command(
            docker=[
                "--rm",
                SOCKET_MOUNT,
                CACHE_MOUNT,
                '-v "/depot/infra/ci/autre.yaml:/.trivyignore.yaml:ro"',
            ]
        ),
        True,
    ),
    "Trivy sans empreinte": (scan_command(trivy=TRIVY_REPOSITORY + "0.74.0"), True),
    "Trivy sous latest": (scan_command(trivy=TRIVY_PINNED.replace("0.74.0", "latest")), True),
    "Trivy d'un autre dépôt": (scan_command(trivy=TRIVY_PINNED.replace("ghcr.io/", "")), True),
    "aucune commande": ("", True),
}


def ci_scan_forms(name: str) -> dict[str, tuple[str, bool]]:
    """Les formes recensées d'un job de `SCANNING_JOBS`, chacune avec son verdict attendu.

    Chaque forme est un workflow minimal où le job `name` porte les étapes de la forme.
    """
    build_step, scan_step = (f"run: {command}" for command in SCANNING_JOBS[name])

    def job(*steps: str, job_options: str = "") -> str:
        """Un workflow minimal dont le job `name` porte `job_options`, puis les étapes données."""
        listed = "".join(f"      - {step}\n" for step in steps)
        return f"jobs:\n  {name}:\n{job_options}    steps:\n{listed}"

    return {
        "build puis scan": (job(build_step, scan_step), False),
        "étape de scan nommée": (job(build_step, f"name: Scan\n        {scan_step}"), False),
        "sans le job": (job(build_step, scan_step).replace(f"  {name}:", "  autre:"), True),
        "sans scan": (job(build_step), True),
        "sans build": (job(scan_step), True),
        "scan avant build": (job(scan_step, build_step), True),
        "variable de plus sur le scan": (job(build_step, f"{scan_step} SCAN_FLAGS="), True),
        "continue-on-error": (
            job(build_step, f"{scan_step}\n        continue-on-error: true"),
            True,
        ),
        "if": (job(build_step, f"{scan_step}\n        if: github.event_name == 'push'"), True),
        "env": (job(build_step, f"{scan_step}\n        env:\n          MAKEFLAGS: -i"), True),
        "job qui tolère ses échecs": (
            job(build_step, scan_step, job_options="    continue-on-error: true\n"),
            True,
        ),
        "env sur le job": (
            job(build_step, scan_step, job_options="    env:\n      MAKEFLAGS: -i\n"),
            True,
        ),
        "env sur le workflow": ("env:\n  MAKEFLAGS: -i\n" + job(build_step, scan_step), True),
    }


CI_SCAN_FORMS = {
    f"{name} — {form}": (name, workflow, expected)
    for name in SCANNING_JOBS
    for form, (workflow, expected) in ci_scan_forms(name).items()
}

# Les façons dont un `Makefile` fait ignorer à `make` l'échec d'une recette : le texte du dépôt,
# et ce qui le remplace dans la copie témoin. `make --dry-run` n'en montre aucune. Une quatrième,
# le `-` en tête de la variable `TRIVY`, se lit dans le texte : remplacer `TRIVY` la masquerait.
SCAN_TARGET = "scan: $(IMAGE_SCANS)"
LENIENT_MAKEFILES = {
    "recette préfixée de -": ("\t$(TRIVY) image", "\t-$(TRIVY) image"),
    ".IGNORE": (SCAN_TARGET, f".IGNORE:\n{SCAN_TARGET}"),
    "MAKEFLAGS += -i": (SCAN_TARGET, f"MAKEFLAGS += -i\n{SCAN_TARGET}"),
}

TODAY = date(2026, 9, 30)
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def exception_file(section: str = "vulnerabilities", **changes: str | None) -> str:
    """Un fichier d'une exception valable à la date `TODAY`, modifiée par `changes`.

    Chaque changement remplace la valeur YAML brute d'un champ, ou le retire s'il vaut `None` ;
    un champ inconnu est ajouté. Un cas mal formé se lit ainsi comme l'écart exact qui le rend
    invalide.
    """
    fields: dict[str, str | None] = {
        "id": "CVE-2026-0001",
        "paths": "[usr/bin/caddy]",
        "statement": "Place, atteinte, alternatives.",
        "expired_at": TOMORROW,
        **changes,
    }
    lines = [f"{key}: {value}" for key, value in fields.items() if value is not None]
    return f"{section}:\n  - " + "\n    ".join(lines) + "\n"


EXCEPTION_FORMS = {
    "complète, expire demain": (exception_file(), False),
    "fichier sans exception": ("# aucune exception\n", False),
    "sans expired_at": (exception_file(expired_at=None), True),
    "sans statement": (exception_file(statement=None), True),
    "sans id": (exception_file(id=None), True),
    "statement vide": (exception_file(statement='""'), True),
    "id vide": (exception_file(id='""'), True),
    "sans paths": (exception_file(paths=None), True),
    "paths vide": (exception_file(paths="[]"), True),
    "paths qui n'est pas une liste": (exception_file(paths="usr/bin/caddy"), True),
    "paths dont un chemin est vide": (exception_file(paths='[usr/bin/caddy, ""]'), True),
    **{
        f"paths qui vaut pour toute cible, {pattern}": (
            exception_file(paths=f'["{pattern}"]'),
            True,
        )
        for pattern in ["**", "*", "**/*"]
    },
    "paths des paquets du système": (
        exception_file(paths='["**/portfolio-api (debian 13.*)"]'),
        False,
    ),
    "expire aujourd'hui": (exception_file(expired_at=TODAY.isoformat()), True),
    "expirée hier": (exception_file(expired_at=YESTERDAY), True),
    "expire dans 90 jours": (exception_file(expired_at=(TODAY + MAX_LIFETIME).isoformat()), False),
    "expire dans 91 jours": (
        exception_file(expired_at=(TODAY + MAX_LIFETIME + timedelta(days=1)).isoformat()),
        True,
    ),
    "date entre guillemets": (exception_file(expired_at=f'"{TOMORROW}"'), True),
    "date et heure": (exception_file(expired_at=f"{TOMORROW}T00:00:00Z"), True),
    "champ mal orthographié": (exception_file(expired_at=None, expire_at=TOMORROW), True),
    "champ en trop": (exception_file(note="x"), True),
    "autre section, sans date": (exception_file(section="secrets", expired_at=None), True),
    "autre section, complète": (exception_file(section="secrets"), False),
    "entrée qui n'est pas une table": ("vulnerabilities:\n  - CVE-2026-0001\n", True),
    "section qui n'est pas une liste": ("vulnerabilities: CVE-2026-0001\n", True),
    "document qui n'est pas une table": ("- CVE-2026-0001\n", True),
}


@pytest.mark.parametrize(("printed", "expected"), SCAN_FORMS.values(), ids=SCAN_FORMS.keys())
def test_la_garde_du_scan_rend_son_verdict_sur_chaque_forme(printed: str, expected: bool) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle s'écarte de la politique."""
    assert bool(scan_findings(printed)) is expected, scan_findings(printed)


@pytest.mark.parametrize(
    ("name", "workflow", "expected"), CI_SCAN_FORMS.values(), ids=CI_SCAN_FORMS.keys()
)
def test_la_garde_du_scan_en_ci_rend_son_verdict_sur_chaque_forme(
    name: str, workflow: str, expected: bool
) -> None:
    """Chaque forme recensée, pour chaque job qui scanne : signalée si, et seulement si, le scan
    ne bloquerait plus."""
    findings = ci_scan_findings(workflow, name)

    assert bool(findings) is expected, findings


@pytest.mark.parametrize(("text", "expected"), EXCEPTION_FORMS.values(), ids=EXCEPTION_FORMS.keys())
def test_la_garde_des_exceptions_rend_son_verdict_sur_chaque_forme(
    text: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, l'exception est incomplète, mal
    typée, expirée ou datée trop loin."""
    assert bool(exception_findings(text, TODAY)) is expected, exception_findings(text, TODAY)


@pytest.mark.parametrize(
    ("strict", "lenient"), LENIENT_MAKEFILES.values(), ids=LENIENT_MAKEFILES.keys()
)
def test_un_makefile_qui_ignore_l_echec_de_trivy_est_vu(
    tmp_path: Path, strict: str, lenient: str
) -> None:
    """Chaque forme recensée, dans une copie témoin du `Makefile` : `make scan` y sort en 0 quand
    Trivy échoue, et la garde le voit."""
    text = MAKEFILE.read_text(encoding="utf-8")
    assert text.count(strict) == 1, f"« {strict} » n'est plus dans le `Makefile` — forme changée ?"
    copy = tmp_path / "Makefile"
    copy.write_text(text.replace(strict, lenient), encoding="utf-8")

    assert not scan_fails_with_trivy(copy)


# --- Les fichiers du dépôt --------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["portfolio-", PUBLISH_PREFIX])
def test_make_scan_scanne_chaque_image_que_make_build_construit(prefix: str) -> None:
    """Le scan lit les images sous le nom que le build leur donne, préfixe compris — celui du
    poste comme celui sous lequel la CI publiera : une image construite et jamais scannée serait
    publiée sans avoir été regardée (ADR 0014). Ajouter un dossier à `infra/` suffit donc aussi à
    scanner son image."""
    built = set(built_images(make_dry_run("build", IMAGE_PREFIX=prefix)).values())

    assert built, "aucune image construite lue — la forme de la commande a-t-elle changé ?"
    assert scanned_images(make_dry_run("scan", IMAGE_PREFIX=prefix)) == built


def test_make_scan_suit_la_politique_de_scan() -> None:
    """Chaque option porte une part de la politique (ADR 0014) : sans `--exit-code 1`, Trivy liste
    les vulnérabilités et sort en 0 ; sans `--ignorefile`, aucune exception ne vaut ; et une
    vulnérabilité sans correctif s'évalue et se consigne, là où `--ignore-unfixed` la ferait
    disparaître sans trace.

    Trivy tourne dans son image officielle, épinglée comme les images de base. En mars 2026, les
    étiquettes de ses deux actions ont été déplacées vers un voleur d'identifiants, et une version
    piégée publiée sous `latest` (GHSA-69fq-xp46-6x23) ; une image citée par son empreinte n'était
    pas touchée. Dependabot ne lit pas cette épingle : elle se monte à la main.
    """
    assert scan_findings(make_dry_run("scan")) == []


def test_make_scan_echoue_quand_trivy_echoue() -> None:
    """Un scan dont `make` ignore l'échec liste les vulnérabilités et laisse la CI verte : une
    recette préfixée de `-`, pour lire le rapport de chaque image au lieu de s'arrêter à la
    première, suffit (mesuré à la relecture de la PR #62).

    Le `-` peut aussi se loger en tête de la variable `TRIVY`, que ce test remplace : son début
    est donc lu dans le `Makefile`.
    """
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert re.search(r"^TRIVY := docker run\b", makefile, re.MULTILINE), (
        "`TRIVY` ne commence plus par `docker run` — un `-` en tête ferait ignorer son échec"
    )
    assert scan_fails_with_trivy()


@pytest.mark.parametrize("name", SCANNING_JOBS)
def test_la_ci_scanne_les_images_qu_elle_vient_de_construire(name: str) -> None:
    """Le job `infra` scanne sur chaque PR qui le lance (ADR 0017), le job `publish` avant de
    pousser — chacun après le build qui charge les images dans le moteur (`--load`) : avant lui,
    Trivy ne trouverait rien à lire. Aucune image n'est publiée sans avoir été scannée (ADR 0014).

    L'étape ne porte que son nom et sa commande. Un `continue-on-error` la rendrait indicative, un
    `if:` la ferait sauter, un `env:` pourrait régler `make` lui-même (`MAKEFLAGS: -i` ignore
    l'échec de Trivy) sans toucher au `Makefile` — sur l'étape, le job ou le workflow : la
    politique vit dans `make scan`, et nulle part ailleurs.
    """
    assert ci_scan_findings(CI_WORKFLOW.read_text(encoding="utf-8"), name) == []


def test_chaque_exception_du_scan_est_complete_et_en_vigueur() -> None:
    """Une exception ne devient permanente ni par oubli, ni par une clé mal orthographiée.

    Passée sa date, elle fait échouer ce test le jour même où Trivy cesse de l'appliquer : le
    rouge dit quelle évaluation refaire, avant même de lire le rapport du scan (ADR 0014). La
    date du jour est celle de l'UTC, comme pour les exceptions de `pip-audit` : le poste et la CI
    rendent le même verdict.
    """
    findings = exception_findings(EXCEPTIONS.read_text(encoding="utf-8"), datetime.now(UTC).date())

    assert not findings, findings
