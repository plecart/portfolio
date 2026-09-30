"""Tests du scan des images : la commande `make scan`, son étape en CI, ses exceptions datées.

Le scan lui-même tourne ailleurs — sur le poste par `make scan`, en CI dans le job `infra`. Ces
tests gardent ce qui l'affaiblirait sans bruit : une option de Trivy retirée, une étape de CI
devenue indicative, une exception sans date. Trivy n'exige d'une exception que son `id` — une
entrée sans `expired_at` vaut pour toujours, une clé mal orthographiée est ignorée sans un mot —,
et la règle du projet est plus stricte (ADR 0014) : chaque exception porte l'évaluation qui la
fonde et la date où elle se refait.

Comme dans `test_supply_chain.py`, chaque garde est une fonction sur du texte, appliquée au dépôt
et à un recueil de formes — `SCAN_FORMS`, `CI_SCAN_FORMS`, `EXCEPTION_FORMS` —, chacune avec son
verdict attendu. Le dépôt ne montre qu'une forme, la conforme : c'est dans le recueil que chaque
garde se voit rouge, sans qu'il faille affaiblir le scan du dépôt pour l'éprouver.
"""

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest
import yaml
from test_infra import CI_WORKFLOW, REPOSITORY_ROOT, built_images, job_steps, make_dry_run
from test_supply_chain import PINNED_IMAGE

EXCEPTIONS = REPOSITORY_ROOT / ".trivyignore.yaml"

# Une commande de scan telle que `make --dry-run` l'imprime : l'image de Trivy, ses options,
# l'image scannée.
SCAN_COMMAND = re.compile(
    r"^docker run .* (?P<trivy>\S+) image (?P<options>.+) (?P<image>\S+)$", re.MULTILINE
)

# La politique de scan (ADR 0014) : HIGH et CRITICAL bloquent, comme une image de base en fin de
# vie, et seules les exceptions datées de `.trivyignore.yaml` passent. `--image-src docker` : Trivy
# ne lit que les images que `make build` a chargées dans le moteur, et n'en tire aucune d'un
# registre sous le même nom.
SCAN_POLICY = [
    "--severity HIGH,CRITICAL",
    "--exit-code 1",
    "--exit-on-eol 1",
    "--ignorefile .trivyignore.yaml",
    "--image-src docker",
]
# L'option que la politique écarte, sous ses deux formes : le drapeau, et la variable
# d'environnement que Trivy lit à sa place (`TRIVY_IGNORE_UNFIXED`).
UNFIXED_IGNORED = re.compile(r"ignore[-_]unfixed", re.IGNORECASE)
TRIVY_REPOSITORY = "ghcr.io/aquasecurity/trivy:"

# Les commandes que le job `infra` de la CI lance pour construire puis scanner les images.
CI_BUILD = "make build"
CI_SCAN = "make scan"

# Les champs d'une exception, tous obligatoires. Un champ en plus est refusé comme un champ en
# moins, comme pour les exceptions de `pip-audit` : c'est presque toujours une faute de frappe sur
# un champ requis (`expire_at`), que Trivy ignorerait — l'exception deviendrait permanente.
FIELDS = {"id", "statement", "expired_at"}


# --- Les gardes : des fonctions sur du texte ---------------------------------------------------


def scanned_images(printed: str) -> set[str]:
    """Les images qu'une sortie de `make --dry-run scan` ferait scanner."""
    return {command["image"] for command in SCAN_COMMAND.finditer(printed)}


def scan_findings(printed: str) -> list[str]:
    """Ce qui, dans une sortie de `make --dry-run scan`, s'écarte de la politique de scan.

    Returns:
        Un constat par option de `SCAN_POLICY` absente d'une commande, par commande qui écarte les
        vulnérabilités sans correctif, et par commande dont Trivy n'est pas l'image officielle,
        épinglée étiquette `x.y.z` et empreinte ; un constat si aucune commande n'est lue. Liste
        vide : chaque scan suit la politique.
    """
    commands = list(SCAN_COMMAND.finditer(printed))
    findings = [] if commands else ["aucune commande de scan lue — sa forme a-t-elle changé ?"]
    for command in commands:
        image, trivy = command["image"], command["trivy"]
        findings += [
            f"{image} : sans `{option}`"
            for option in SCAN_POLICY
            if option not in command["options"]
        ]
        if UNFIXED_IGNORED.search(command.group()):
            findings.append(f"{image} : vulnérabilités sans correctif écartées")
        if not (trivy.startswith(TRIVY_REPOSITORY) and PINNED_IMAGE.match(trivy)):
            findings.append(f"{image} : Trivy hors de son image officielle épinglée, {trivy}")
    return findings


def ci_scan_findings(workflow: str) -> list[str]:
    """Ce qui empêche le job `infra` d'un workflow de scanner les images qu'il construit.

    Returns:
        Un constat si le job ne lance pas le build puis le scan, dans cet ordre, et un si l'étape
        de scan porte autre chose que son nom et sa commande. Liste vide : le scan bloque.
    """
    steps = job_steps(workflow, "infra")
    commands = [step.get("run") for step in steps]
    if CI_BUILD not in commands or CI_SCAN not in commands:
        return [f"le job `infra` ne lance pas `{CI_BUILD}` et `{CI_SCAN}`"]
    scan = commands.index(CI_SCAN)
    findings = [f"`{CI_SCAN}` avant `{CI_BUILD}`"] if scan < commands.index(CI_BUILD) else []
    extra = sorted(set(steps[scan]) - {"name", "run"})
    return findings + ([f"l'étape de scan porte {extra}"] if extra else [])


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
        value = fields[name]
        if not (isinstance(value, str) and value.strip()):
            findings.append(f"`{name}` doit être une chaîne non vide")
    expired_at = fields["expired_at"]
    # `datetime` hérite de `date` : sans le test de type exact, une date et heure passerait ici.
    if type(expired_at) is not date:
        findings.append("`expired_at` doit être une date YAML sans guillemets ni heure")
    # Trivy compare l'instant présent à minuit UTC du jour indiqué (`IgnoreFindings.Prune`,
    # `pkg/result/ignore.go`) : l'exception cesse de valoir dès le début de ce jour-là.
    elif expired_at <= today:
        findings.append(f"{fields['id']} : expirée depuis le {expired_at}, évaluation à refaire")
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


def scan_command(
    trivy: str = TRIVY_PINNED, options: Iterable[str] = SCAN_POLICY, docker_options: str = ""
) -> str:
    """Une commande de scan telle que `make --dry-run` l'imprime, conforme par défaut."""
    return f"docker run --rm {docker_options}{trivy} image {' '.join(options)} portfolio-api\n"


# Forme → constat attendu (`True`) ou aucun (`False`).
SCAN_FORMS = {
    "conforme": (scan_command(), False),
    **{
        f"sans {option}": (scan_command(options=[o for o in SCAN_POLICY if o != option]), True)
        for option in SCAN_POLICY
    },
    "--ignore-unfixed": (scan_command(options=[*SCAN_POLICY, "--ignore-unfixed"]), True),
    "TRIVY_IGNORE_UNFIXED": (scan_command(docker_options="-e TRIVY_IGNORE_UNFIXED=true "), True),
    "Trivy sans empreinte": (scan_command(trivy=TRIVY_REPOSITORY + "0.74.0"), True),
    "Trivy sous latest": (scan_command(trivy=TRIVY_PINNED.replace("0.74.0", "latest")), True),
    "Trivy d'un autre dépôt": (scan_command(trivy=TRIVY_PINNED.replace("ghcr.io/", "")), True),
    "aucune commande": ("", True),
}


def infra_job(*steps: str) -> str:
    """Un workflow minimal dont le job `infra` porte les étapes données."""
    return "jobs:\n  infra:\n    steps:\n" + "".join(f"      - {step}\n" for step in steps)


BUILD_STEP = f"run: {CI_BUILD}"
SCAN_STEP = f"run: {CI_SCAN}"

CI_SCAN_FORMS = {
    "build puis scan": (infra_job(BUILD_STEP, SCAN_STEP), False),
    "étape de scan nommée": (infra_job(BUILD_STEP, f"name: Scan\n        {SCAN_STEP}"), False),
    "sans scan": (infra_job(BUILD_STEP), True),
    "sans build": (infra_job(SCAN_STEP), True),
    "scan avant build": (infra_job(SCAN_STEP, BUILD_STEP), True),
    "continue-on-error": (
        infra_job(BUILD_STEP, f"{SCAN_STEP}\n        continue-on-error: true"),
        True,
    ),
    "if": (infra_job(BUILD_STEP, f"{SCAN_STEP}\n        if: github.event_name == 'push'"), True),
    "env": (
        infra_job(BUILD_STEP, f"{SCAN_STEP}\n        env:\n          TRIVY_IGNORE_UNFIXED: true"),
        True,
    ),
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
    "expire aujourd'hui": (exception_file(expired_at=TODAY.isoformat()), True),
    "expirée hier": (exception_file(expired_at=YESTERDAY), True),
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


@pytest.mark.parametrize(("workflow", "expected"), CI_SCAN_FORMS.values(), ids=CI_SCAN_FORMS.keys())
def test_la_garde_du_scan_en_ci_rend_son_verdict_sur_chaque_forme(
    workflow: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, le scan ne bloquerait plus."""
    assert bool(ci_scan_findings(workflow)) is expected, ci_scan_findings(workflow)


@pytest.mark.parametrize(("text", "expected"), EXCEPTION_FORMS.values(), ids=EXCEPTION_FORMS.keys())
def test_la_garde_des_exceptions_rend_son_verdict_sur_chaque_forme(
    text: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, l'exception est incomplète, mal
    typée ou expirée."""
    assert bool(exception_findings(text, TODAY)) is expected, exception_findings(text, TODAY)


# --- Les fichiers du dépôt --------------------------------------------------------------------


def test_make_scan_scanne_chaque_image_que_make_build_construit() -> None:
    """Le scan lit les images sous le nom que le build leur donne, préfixe compris : une image
    construite et jamais scannée serait publiée sans avoir été regardée (ADR 0014). Ajouter un
    dossier à `infra/` suffit donc aussi à scanner son image."""
    built = set(built_images(make_dry_run("build")).values())

    assert scanned_images(make_dry_run("scan")) == built


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


def test_la_ci_scanne_les_images_qu_elle_vient_de_construire() -> None:
    """Le job `infra` scanne sur chaque PR, après le build qui charge les images dans le moteur
    (`--load`) : avant lui, Trivy ne trouverait rien à lire.

    L'étape ne porte que son nom et sa commande. Un `continue-on-error` la rendrait indicative, un
    `if:` la ferait sauter, un `env:` pourrait assouplir Trivy par ses variables (`TRIVY_*`) sans
    toucher au `Makefile` : la politique vit dans `make scan`, et nulle part ailleurs.
    """
    assert ci_scan_findings(CI_WORKFLOW.read_text(encoding="utf-8")) == []


def test_chaque_exception_du_scan_est_complete_et_en_vigueur() -> None:
    """Une exception ne devient permanente ni par oubli, ni par une clé mal orthographiée.

    Passée sa date, elle fait échouer ce test le jour même où Trivy cesse de l'appliquer : le
    rouge dit quelle évaluation refaire, avant même de lire le rapport du scan (ADR 0014). La
    date du jour est celle de l'UTC, comme pour les exceptions de `pip-audit` : le poste et la CI
    rendent le même verdict.
    """
    findings = exception_findings(EXCEPTIONS.read_text(encoding="utf-8"), datetime.now(UTC).date())

    assert not findings, findings
