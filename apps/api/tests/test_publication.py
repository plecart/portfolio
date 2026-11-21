"""Tests de la publication des images sur GHCR : `make push`, `make prune`, le job `publish`, et le
job de fumée qui éprouve ses images avant leur déploiement (#26).

La publication tourne sur GitHub Actions, après chaque push sur `main` (ADR 0014) ; le poste n'a ni
le jeton ni le registre. Ces tests lisent donc ce que `make` exécuterait — `make --dry-run`, ou la
recette lancée sur un `gh` témoin —, sans rien pousser ni supprimer, et le workflow tel que
l'analyseur YAML le lit. Comme dans `test_image_scan.py`, la garde de chaque job est une fonction
sur du texte, appliquée au dépôt et à un recueil de formes, `PUBLISH_FORMS` et `SMOKE_FORMS`.
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from system_commands import make_dry_run, run_make
from test_image_scan import SCANNING_JOBS
from test_infra import (
    BUILD_COMMAND,
    CACHED_BUILDS,
    CI_WORKFLOW,
    DISQUE_RUN,
    PUBLISH_PREFIX,
    built_images,
    ci_build_flags,
    job_steps,
    run_bounded,
)

# Le SHA complet d'un commit, étiquette de l'image publiée à côté de `latest`.
SHA = "0123456789abcdef0123456789abcdef01234567"

# Une recette de `make prune` telle que `make --dry-run` l'imprime : la lecture des versions d'un
# paquet par `gh`, avec son filtre, puis la suppression de chacune de celles qu'il rend.
PRUNE_RECIPE = re.compile(
    r"^ids=\$\(gh api '(?P<versions>[^'?]+)\?per_page=100' --jq '(?P<filter>[^']+)'\) && \\\n"
    r"for id in \$ids; do gh api --method DELETE (?P=versions)/\$id \|\| exit 1; done$",
    re.MULTILINE,
)

# gojq, le moteur `jq` que `gh` embarque — v0.12.17 dans `gh` 2.94.0 (son `go.mod`) —, dans l'image
# que publie son auteur, épinglée étiquette et empreinte comme Trivy et Ryuk : Dependabot ne la
# suit pas, elle se monte à la main, avec la version de `gh`.
GOJQ_IMAGE = (
    "ghcr.io/itchyny/gojq:0.12.17"
    "@sha256:e9ddedb60bb27df4c7fd9ae92f38c05d4f3745fa8a6f2179499ca243a38b65ff"
)


def version(number: int, created: str, *tags: str) -> dict[str, object]:
    """Une version de paquet telle que l'API de GitHub la décrit, réduite à ce que lit le filtre."""
    return {
        "id": number,
        "created_at": f"2026-10-{created}T10:00:00Z",
        "metadata": {"package_type": "container", "container": {"tags": list(tags)}},
    }


# Liste de versions → celles que la rétention supprime, de la plus ancienne à la plus récente.
# L'API ne promet aucun ordre : la liste arrive mélangée.
RETENTION_CASES: dict[str, tuple[list[dict[str, object]], list[int]]] = {
    "six versions, dans le désordre": (
        [version(n, f"0{n}", f"c{n}") for n in (6, 5, 2, 4, 1, 3)],
        [1, 2, 3],
    ),
    # Un job relancé sur un commit dont le build ne se reproduit pas à l'octet déplace ses deux
    # étiquettes vers une nouvelle version : l'ancienne reste, sans étiquette, et compte.
    "une version orpheline d'une relance": (
        [
            version(4, "04", "c3", "latest"),
            version(3, "03"),
            version(2, "02", "c2"),
            version(1, "01", "c1"),
        ],
        [1],
    ),
    "trois versions": ([version(n, f"0{n}", f"c{n}") for n in (3, 2, 1)], []),
    "une version": ([version(1, "01", "c1", "latest")], []),
}

# Ce que porte le job `publish` (brief de #15, décision 5) : il ne tourne que sur un push vers
# `main`, et n'attend aucun job de vérification — la PR, fusionnée au trunk, les a joués (ADR 0031,
# décision 1) ; seul à écrire dans le registre, il lit le dépôt sans y écrire, et le reste du
# workflow ne fait que lire ; une publication attend la fin de la précédente, sans l'annuler.
PUBLISH_IF = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
READ_ONLY = {"contents": "read"}
PUBLISH_PERMISSIONS = {"contents": "read", "packages": "write"}

# Ce que porte le job de fumée (brief de #26) : il éprouve les images que `publish` vient de
# pousser, avant que `deploy` ne les tire — sur un push vers `main` seulement, la condition de
# `publish`. Il tire les images privées du registre (ADR 0014) : la lecture des paquets, seule
# permission admise hors de `publish`, sur ce seul job. Les images du commit, jamais `latest`
# (décision 2). Ni `continue-on-error` ni `if` d'étape : rouge, il doit sauter `deploy`.
SMOKE_JOB = "fumee"
SMOKE_NEEDS = ["publish"]
SMOKE_PERMISSIONS = {"contents": "read", "packages": "read"}
SMOKE_RUN = f'make smoke IMAGE_PREFIX={PUBLISH_PREFIX} IMAGE_TAG="$GITHUB_SHA"'
SMOKE_JOB_KEYS = {"name", "runs-on", "needs", "if", "permissions", "timeout-minutes", "steps"}

# Les commandes du job, mot pour mot : le build et le scan de `SCANNING_JOBS`, la connexion au
# registre, le push de ce qui vient d'être scanné, sous l'étiquette du commit, puis la rétention.
_, PUBLISH_BUILD, PUBLISH_SCAN = SCANNING_JOBS["publish"]
PUBLISH_LOGIN = (
    'echo "$GH_TOKEN" | docker login ghcr.io --username "$GITHUB_ACTOR" --password-stdin'
)
PUBLISH_PUSH = f'make push IMAGE_PREFIX={PUBLISH_PREFIX} IMAGE_TAG="$GITHUB_SHA"'
PUBLISH_PRUNE = f"make prune IMAGE_PREFIX={PUBLISH_PREFIX}"

# Les drapeaux du build, seule variable de son étape : l'image chargée dans le moteur, où Trivy la
# lit, sans attestation (décision 7), depuis le cache des couches sauf l'étage `paquets`, et ce
# cache écrit pour `main` (ADR 0031). Mot pour mot : un drapeau de plus (`--push`,
# `--output type=registry`) enverrait l'image au registre avant son scan.
PUBLISH_BUILD_FLAGS = (
    "--load --no-cache-filter paquets --cache-from type=local,src=/tmp/buildx-cache,tag=$*"
    " --cache-to type=local,dest=/tmp/buildx-cache,tag=$*,mode=max"
    " --provenance=false --sbom=false"
)
# L'environnement des étapes qui parlent au registre : le jeton du job, rien d'autre.
WORKFLOW_TOKEN_ENV = {"GH_TOKEN": "${{ github.token }}"}

# Les étapes du job, dans l'ordre — l'action, sans son empreinte, ou la commande —, chacune avec
# son environnement, et aucune autre : rien n'atteint le registre avant le scan. Une connexion
# placée plus tôt donnerait son identifiant au build, une étape de plus pourrait pousser, une
# variable de plus (`MAKEFLAGS: -i`) ferait ignorer un échec. Le front, installé ici, que
# `make build` compile : aucun artefact d'un job de vérification (ADR 0031) ; le cache des couches,
# restauré puis écrit.
PUBLISH_STEPS: list[tuple[str, dict[str, str] | None]] = [
    ("actions/checkout", None),
    ("actions/setup-node", None),
    ("make web-install", None),
    (DISQUE_RUN, None),
    ("docker/setup-buildx-action", None),
    ("actions/cache", None),
    (PUBLISH_BUILD, {"DOCKER_BUILD_FLAGS": PUBLISH_BUILD_FLAGS}),
    (PUBLISH_SCAN, None),
    (PUBLISH_LOGIN, WORKFLOW_TOKEN_ENV),
    (PUBLISH_PUSH, None),
    (PUBLISH_PRUNE, WORKFLOW_TOKEN_ENV),
]

# Les étapes du job de fumée, de même : la connexion après les installations, dont les scripts ne
# voient donc pas l'identifiant du registre, et aucun tirage à part — `up` tire les images.
SMOKE_STEPS: list[tuple[str, dict[str, str] | None]] = [
    ("actions/checkout", None),
    ("actions/setup-node", None),
    ("make web-install", None),
    ("make web-browsers", None),
    (PUBLISH_LOGIN, WORKFLOW_TOKEN_ENV),
    (SMOKE_RUN, None),
]

# Les clés qu'une étape du job peut porter : ni `if` qui la sauterait, ni `continue-on-error` qui
# tolérerait son échec, ni `shell` ou `working-directory` qui changeraient ce qu'elle lance.
STEP_KEYS = {"name", "uses", "with", "run", "env"}


def published_images() -> list[str]:
    """Les images que `make build` construit sous le préfixe de publication, dans l'ordre."""
    return list(built_images(make_dry_run("build", IMAGE_PREFIX=PUBLISH_PREFIX)).values())


def fake_gh(root: Path, failing_version: int | None = None) -> str:
    """Un `gh` témoin : il consigne chaque appel dans `root/calls`, rend deux versions, 11 et 12,
    à toute lecture, et réussit toute suppression, sauf celle de `failing_version`.

    Échouer sur la **première** version seulement : la réussite de la suivante masquerait un échec
    que la boucle ne remonte pas, là où deux échecs se verraient quand même.

    Returns:
        La commande qui le lance, à passer dans `GH`.
    """
    lines = [f'echo "$*" >> "{(root / "calls").as_posix()}"']
    if failing_version is not None:
        lines.append(f'case "$*" in *"--method DELETE"*/{failing_version}) exit 1 ;; esac')
    lines += ['case "$*" in *"--method DELETE"*) exit 0 ;; esac', "echo 11", "echo 12"]
    script = root / "gh"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return f"sh {script.as_posix()}"


def run_prune(gh: str) -> subprocess.CompletedProcess[str]:
    """`make prune` sous le préfixe de publication, avec `gh` remplacé par `gh`."""
    return run_make("prune", IMAGE_PREFIX=PUBLISH_PREFIX, GH=gh)


def prune_recipes() -> list[re.Match[str]]:
    """Les recettes de `make prune` sous le préfixe de publication, telles qu'imprimées."""
    return list(PRUNE_RECIPE.finditer(make_dry_run("prune", IMAGE_PREFIX=PUBLISH_PREFIX)))


def stale_versions(versions: list[dict[str, object]]) -> list[int]:
    """Les versions que `make prune` supprimerait parmi `versions` : son filtre, tel que
    `make --dry-run` l'imprime, évalué par gojq comme `gh` l'évaluerait."""
    recipes = prune_recipes()
    assert recipes, "aucune recette de rétention lue — sa forme a-t-elle changé ?"
    evaluated = run_bounded(
        ["docker", "run", "--rm", "-i", GOJQ_IMAGE, recipes[0]["filter"]],
        stdin=json.dumps(versions).encode(),
    )
    return [int(number) for number in evaluated.stdout.split()]


def needed(job: dict[str, Any]) -> list[str]:
    """Les jobs qu'attend `job`, que `needs` les nomme en chaîne ou en liste (doc GitHub
    « Workflow syntax », `jobs.<job_id>.needs`)."""
    needs: str | list[str] = job.get("needs") or []
    return [needs] if isinstance(needs, str) else needs


def steps_findings(
    steps: list[dict[str, object]], expected: list[tuple[str, dict[str, str] | None]]
) -> list[str]:
    """Ce qui écarte les étapes d'un job de la liste exacte `expected` — l'action, sans son
    empreinte, ou la commande, chacune avec son environnement, dans cet ordre.

    Returns:
        Un constat si la liste diffère, un par étape qui porte une clé hors de `STEP_KEYS`, et un
        si le checkout garde l'identifiant du dépôt. Liste vide : les étapes sont conformes.
    """
    launched = [
        (step.get("run") or str(step.get("uses", "")).split("@")[0], step.get("env"))
        for step in steps
    ]
    findings: list[str] = []
    if launched != expected:
        findings.append(f"le job lance {launched}, attendu, dans cet ordre, {expected}")
    findings += [
        f"l'étape `{name}` porte {sorted(set(step) - STEP_KEYS)}"
        for step, (name, _) in zip(steps, launched, strict=True)
        if set(step) - STEP_KEYS
    ]
    checkout = [
        step.get("with")
        for step, (name, _) in zip(steps, launched, strict=True)
        if name == "actions/checkout"
    ]
    if checkout != [{"persist-credentials": False}]:
        findings.append(f"le checkout reçoit {checkout}, attendu `persist-credentials: false`")
    return findings


def publish_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte le job `publish` de ce que le brief de #15 exige.

    Returns:
        Un constat si le job manque ; sinon un par propriété altérée — un `needs`, `if`,
        permissions du job, du workflow ou d'un autre job, hors `SMOKE_PERMISSIONS` sur le job de
        fumée, `concurrency`, et ses étapes (`steps_findings`, `PUBLISH_STEPS`). Liste vide : le
        job est conforme.
    """
    document = yaml.safe_load(workflow)
    jobs = document["jobs"]
    job = jobs.get("publish")
    if job is None:
        return ["aucun job `publish`"]
    findings: list[str] = []
    if needs := needed(job):
        findings.append(f"`publish` attend {needs} : il n'attend aucun job (ADR 0031)")
    if job.get("if") != PUBLISH_IF:
        findings.append(f"`if` vaut {job.get('if')!r}, attendu {PUBLISH_IF!r}")
    if document.get("permissions") != READ_ONLY:
        findings.append(f"le workflow donne {document.get('permissions')}, attendu {READ_ONLY}")
    if job.get("permissions") != PUBLISH_PERMISSIONS:
        findings.append(f"le job donne {job.get('permissions')}, attendu {PUBLISH_PERMISSIONS}")
    findings += [
        f"le job `{name}` donne {other['permissions']}"
        for name, other in jobs.items()
        if name != "publish"
        and "permissions" in other
        and (name, other["permissions"]) != (SMOKE_JOB, SMOKE_PERMISSIONS)
    ]
    concurrency = job.get("concurrency")
    settings: dict[str, object] = (
        cast(dict[str, object], concurrency) if isinstance(concurrency, dict) else {}
    )
    if not (settings.get("group") and settings.get("cancel-in-progress") is False):
        findings.append(
            "`concurrency` doit nommer son groupe et porter `cancel-in-progress: false`"
        )
    return findings + steps_findings(job.get("steps") or [], PUBLISH_STEPS)


def smoke_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte le job de fumée de ce que le brief de #26 exige.

    Ce que la fumée fait, `make smoke` et `apps/web/smoke/` le portent, `test_compose.py` en tient
    la pile ; la garde tient ce qui l'entoure — ce qui la déclenche, la saute ou tolère son échec,
    ce qu'elle reçoit, et les images qu'elle éprouve.

    Returns:
        Un constat si le job manque ; sinon un par propriété altérée — `needs`, `if`,
        `permissions`, une clé de job hors de `SMOKE_JOB_KEYS` (`continue-on-error`, `env`…), et
        ses étapes (`steps_findings`, `SMOKE_STEPS`). Liste vide : le job est conforme.
    """
    job = yaml.safe_load(workflow)["jobs"].get(SMOKE_JOB)
    if job is None:
        return [f"aucun job `{SMOKE_JOB}`"]
    findings: list[str] = []
    if needed(job) != SMOKE_NEEDS:
        findings.append(f"`needs` vaut {job.get('needs')}, attendu {SMOKE_NEEDS}")
    if job.get("if") != PUBLISH_IF:
        findings.append(f"`if` vaut {job.get('if')!r}, attendu {PUBLISH_IF!r}")
    if job.get("permissions") != SMOKE_PERMISSIONS:
        findings.append(f"le job donne {job.get('permissions')}, attendu {SMOKE_PERMISSIONS}")
    if extra := sorted(set(job) - SMOKE_JOB_KEYS):
        findings.append(f"le job porte {extra}")
    return findings + steps_findings(job.get("steps") or [], SMOKE_STEPS)


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------


def forms(
    conforming: str, changes: dict[str, tuple[str, str, bool]]
) -> dict[str, tuple[str, bool]]:
    """Le recueil d'une garde : chaque forme de `changes` — texte remplacé dans `conforming`,
    remplacement, constat attendu — rendue en workflow et constat attendu ; un texte remplacé
    vide rend `conforming` tel quel."""
    return {
        form: (conforming.replace(old, new) if old else conforming, expected)
        for form, (old, new, expected) in changes.items()
    }


PERSIST_LINES = "        with:\n          persist-credentials: false\n"
CHECKOUT_LINE = "      - uses: actions/checkout@v0\n" + PERSIST_LINES
BUILD_FLAGS_LINE = f"          DOCKER_BUILD_FLAGS: {PUBLISH_BUILD_FLAGS}\n"
TOKEN_LINES = f"        env:\n          GH_TOKEN: {WORKFLOW_TOKEN_ENV['GH_TOKEN']}\n"
SCAN_LINE, PUSH_LINE = (f"      - run: {command}\n" for command in (PUBLISH_SCAN, PUBLISH_PUSH))
LOGIN_LINE, PRUNE_LINE = (
    f"      - run: {command}\n{TOKEN_LINES}" for command in (PUBLISH_LOGIN, PUBLISH_PRUNE)
)
LOGIN_ACTION_LINE = "      - uses: docker/login-action@v0\n"
INSTALL_LINES = "      - uses: actions/setup-node@v0\n      - run: make web-install\n"
CONFORMING_WORKFLOW = f"""\
permissions:
  contents: read
jobs:
  api:
    steps: []
  web:
    steps: []
  infra:
    steps: []
  {SMOKE_JOB}:
    steps: []
  publish:
    if: {PUBLISH_IF}
    permissions:
      contents: read
      packages: write
    concurrency:
      group: publish
      cancel-in-progress: false
    steps:
{CHECKOUT_LINE}{INSTALL_LINES}\
      - run: {json.dumps(DISQUE_RUN)}
      - uses: docker/setup-buildx-action@v0
      - uses: actions/cache@v0
      - run: {PUBLISH_BUILD}
        env:
{BUILD_FLAGS_LINE}{SCAN_LINE}{LOGIN_LINE}{PUSH_LINE}{PRUNE_LINE}"""


def granted(job: str, permissions: dict[str, str]) -> tuple[str, str]:
    """Le texte remplacé et son remplacement qui donnent `permissions` au job `job` de
    `CONFORMING_WORKFLOW`, qui n'en règle aucune."""
    scopes = "".join(f"      {scope}: {access}\n" for scope, access in permissions.items())
    return f"  {job}:\n    steps: []\n", f"  {job}:\n    permissions:\n{scopes}    steps: []\n"


# Forme → (texte remplacé, remplacement, constat attendu). Le texte remplacé est pris dans
# `CONFORMING_WORKFLOW` : une forme qui ne le changerait pas resterait conforme, et son verdict
# attendu la ferait rougir.
PUBLISH_CHANGES = {
    "conforme": ("", "", False),
    "sans le job": ("  publish:", "  autre:", True),
    "sans le disque libéré": (f"      - run: {json.dumps(DISQUE_RUN)}\n", "", True),
    # Un job de vérification attendu : il ne tourne plus sur un push vers `main`, et `publish`
    # sauterait avec lui (ADR 0031, décision 1).
    "attend un job": ("  publish:\n", "  publish:\n    needs: api\n", True),
    "attend les quatre jobs": (
        "  publish:\n",
        "  publish:\n    needs: [api, web, infra, avis]\n",
        True,
    ),
    # Le front du job `web`, par artefact : il n'y en a plus sur `main`.
    "télécharge le front": (
        INSTALL_LINES,
        "      - uses: actions/download-artifact@v0\n",
        True,
    ),
    "sans le front installé": ("      - run: make web-install\n", "", True),
    # Un cache que seule une PR écrirait : `main` ne le lit pas (ADR 0031, décision 1).
    "cache restauré sans être écrit": ("actions/cache@v0", "actions/cache/restore@v0", True),
    "build qui n'écrit pas le cache": (
        " --cache-to type=local,dest=/tmp/buildx-cache,tag=$*,mode=max",
        "",
        True,
    ),
    "sans if": (f"    if: {PUBLISH_IF}\n", "", True),
    "sur un push vers toute branche": (PUBLISH_IF, "github.event_name == 'push'", True),
    "sur tout événement": (PUBLISH_IF, "always()", True),
    "écriture des paquets pour tout le workflow": (
        "  contents: read\njobs:",
        "  contents: read\n  packages: write\njobs:",
        True,
    ),
    "écriture sur le dépôt": ("      contents: read\n", "      contents: write\n", True),
    "job qui ne lit plus le dépôt": ("      contents: read\n", "", True),
    "job en write-all": (
        "    permissions:\n      contents: read\n      packages: write\n",
        "    permissions: write-all\n",
        True,
    ),
    "permissions sur un autre job": (*granted("infra", {"packages": "write"}), True),
    # La lecture des paquets du job de fumée, sur lui seul et telle quelle (brief de #26).
    "lecture des paquets sur la fumée": (*granted(SMOKE_JOB, SMOKE_PERMISSIONS), False),
    "écriture des paquets sur la fumée": (*granted(SMOKE_JOB, PUBLISH_PERMISSIONS), True),
    "scope de plus sur la fumée": (
        *granted(SMOKE_JOB, SMOKE_PERMISSIONS | {"actions": "read"}),
        True,
    ),
    "lecture des paquets sur un autre job": (*granted("infra", SMOKE_PERMISSIONS), True),
    "concurrence qui annule": ("cancel-in-progress: false", "cancel-in-progress: true", True),
    "concurrence sans annulation implicite": ("      cancel-in-progress: false\n", "", True),
    "sans concurrence": (
        "    concurrency:\n      group: publish\n      cancel-in-progress: false\n",
        "",
        True,
    ),
    "push avant scan": (
        SCAN_LINE + LOGIN_LINE + PUSH_LINE,
        PUSH_LINE + SCAN_LINE + LOGIN_LINE,
        True,
    ),
    "sans rétention": (PRUNE_LINE, "", True),
    "rétention avant push": (PUSH_LINE + PRUNE_LINE, PRUNE_LINE + PUSH_LINE, True),
    "push sans l'étiquette du commit": (' IMAGE_TAG="$GITHUB_SHA"', "", True),
    "push en double": (PUSH_LINE, PUSH_LINE + PUSH_LINE, True),
    # Une étape tolérée en échec, sautée, ou dont `make` ignore les erreurs : la CI reste verte,
    # rien n'est publié, ou les versions s'accumulent jusqu'au quota du compte.
    "push toléré en échec": (PUSH_LINE, PUSH_LINE + "        continue-on-error: true\n", True),
    "push sauté": (PUSH_LINE, PUSH_LINE + "        if: false\n", True),
    "rétention tolérée en échec": (
        PRUNE_LINE,
        PRUNE_LINE + "        continue-on-error: true\n",
        True,
    ),
    "rétention qui ignore ses erreurs": (
        PRUNE_LINE,
        PRUNE_LINE + "          MAKEFLAGS: -i\n",
        True,
    ),
    # Une image atteint le registre avant son scan : poussée par le build, qui trouverait
    # l'identifiant d'une connexion placée plus tôt, ou par une étape de plus.
    "connexion avant le scan": (SCAN_LINE + LOGIN_LINE, LOGIN_LINE + SCAN_LINE, True),
    "connexion par une action": (LOGIN_LINE, LOGIN_ACTION_LINE, True),
    "connexion de plus en tête du job": (CHECKOUT_LINE, LOGIN_ACTION_LINE + CHECKOUT_LINE, True),
    "build qui pousse": ("--load", "--load --push", True),
    "build exporté vers le registre": ("--load", "--load --output type=registry", True),
    "build sans chargement dans le moteur": ("--load ", "", True),
    "identifiant passé au build": (
        BUILD_FLAGS_LINE,
        BUILD_FLAGS_LINE + "          GH_TOKEN: ${{ github.token }}\n",
        True,
    ),
    "étape de push avant le scan": (
        SCAN_LINE,
        "      - uses: docker/build-push-action@v0\n" + SCAN_LINE,
        True,
    ),
    "checkout qui garde l'identifiant du dépôt": (PERSIST_LINES, "", True),
}
PUBLISH_FORMS = forms(CONFORMING_WORKFLOW, PUBLISH_CHANGES)

BROWSERS_LINE = "      - run: make web-browsers\n"
SMOKE_LINE = f"      - run: {SMOKE_RUN}\n"
SMOKE_CONFORMING = f"""\
jobs:
  {SMOKE_JOB}:
    runs-on: ubuntu-latest
    needs: publish
    if: {PUBLISH_IF}
    permissions:
      contents: read
      packages: read
    timeout-minutes: 20
    steps:
{CHECKOUT_LINE}{INSTALL_LINES}{BROWSERS_LINE}{LOGIN_LINE}{SMOKE_LINE}"""

# Même recueil pour le job de fumée, pris dans `SMOKE_CONFORMING`.
SMOKE_CHANGES = {
    "conforme": ("", "", False),
    "needs en liste": ("needs: publish", "needs: [publish]", False),
    "sans le job": (f"  {SMOKE_JOB}:", "  autre:", True),
    "avant la publication": ("needs: publish", "needs: infra", True),
    "sur un push vers toute branche": (PUBLISH_IF, "github.event_name == 'push'", True),
    "sans la lecture des paquets": ("      packages: read\n", "", True),
    "écriture des paquets": ("packages: read", "packages: write", True),
    "job toléré en échec": (
        "    timeout-minutes: 20\n",
        "    timeout-minutes: 20\n    continue-on-error: true\n",
        True,
    ),
    "images sous latest": ('IMAGE_TAG="$GITHUB_SHA"', "IMAGE_TAG=latest", True),
    "sans la fumée": (SMOKE_LINE, "", True),
    "fumée tolérée en échec": (SMOKE_LINE, SMOKE_LINE + "        continue-on-error: true\n", True),
    "fumée sautée": (SMOKE_LINE, SMOKE_LINE + "        if: false\n", True),
    "checkout qui garde l'identifiant du dépôt": (PERSIST_LINES, "", True),
    "connexion avant l'installation": (
        INSTALL_LINES + BROWSERS_LINE + LOGIN_LINE,
        LOGIN_LINE + INSTALL_LINES + BROWSERS_LINE,
        True,
    ),
    "tirage à part": (SMOKE_LINE, "      - run: docker compose pull\n" + SMOKE_LINE, True),
}
SMOKE_FORMS = forms(SMOKE_CONFORMING, SMOKE_CHANGES)


def test_make_push_publie_chaque_image_sous_son_sha_puis_latest() -> None:
    """Chaque image que `make build` construit part sous le SHA complet du commit, puis sous
    `latest` (ADR 0014) : `latest` ne désigne ainsi jamais une image dont l'étiquette du commit n'a
    pas été poussée. `latest` est l'étiquette que le build lui a déjà donnée ; seule celle du commit
    se pose ici."""
    images = published_images()
    expected = [
        command
        for image in images
        for command in (
            f"docker tag {image} {image}:{SHA}",
            f"docker push {image}:{SHA}",
            f"docker push {image}:latest",
        )
    ]

    assert images, "aucune image construite lue — la forme de la commande a-t-elle changé ?"
    assert make_dry_run("push", IMAGE_PREFIX=PUBLISH_PREFIX, IMAGE_TAG=SHA).splitlines() == expected


def test_make_push_exige_l_etiquette_du_commit() -> None:
    """Sans étiquette de commit, l'image ne partirait que sous `latest`, qui change à chaque
    publication : rien ne désignerait plus ce qui a été déployé."""
    pushed = run_make("--dry-run", "push", IMAGE_PREFIX=PUBLISH_PREFIX)

    assert pushed.returncode != 0
    assert "IMAGE_TAG" in pushed.stderr


def test_make_prune_supprime_ce_que_la_retention_ne_garde_pas(tmp_path: Path) -> None:
    """Chaque paquet publié lit ses versions dans l'API de GitHub, et supprime chacune de celles
    que la lecture rend — ici les versions 11 et 12 du `gh` témoin. Ce que le filtre de la lecture
    garde, `test_la_retention_supprime_tout_sauf_les_trois_versions_les_plus_recentes` l'évalue."""
    assert run_prune(fake_gh(tmp_path)).returncode == 0
    calls = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
    packages = [
        f"users/plecart/packages/container/{Path(image).name}/versions"
        for image in published_images()
    ]

    listings = [call.split(" --jq ")[0] for call in calls if "--method" not in call]
    assert listings == [f"api {package}?per_page=100" for package in packages]
    assert [call for call in calls if "--method" in call] == [
        f"api --method DELETE {package}/{number}" for package in packages for number in (11, 12)
    ]


def test_make_prune_exige_un_prefixe_ghcr() -> None:
    """Hors de GHCR, l'adresse des versions ne désignerait aucun paquet (`users/./packages/…`) :
    la rétention s'arrête sur la cause, pas sur une erreur 404 de l'API."""
    pruned = run_make("--dry-run", "prune")

    assert pruned.returncode != 0
    assert "IMAGE_PREFIX" in pruned.stderr


def test_make_prune_lit_et_supprime_par_gh() -> None:
    """Sans `GH` sur la ligne de commande, la recette appelle `gh` lui-même — le défaut que la CI
    emploie, et que les autres tests remplacent par un témoin. Un défaut changé (`GH ?= true`)
    ferait de la rétention une étape verte qui ne supprime rien."""
    assert [recipe["versions"] for recipe in prune_recipes()] == [
        f"users/plecart/packages/container/{Path(image).name}/versions"
        for image in published_images()
    ]


@pytest.mark.parametrize(
    ("versions", "expected"), RETENTION_CASES.values(), ids=RETENTION_CASES.keys()
)
def test_la_retention_supprime_tout_sauf_les_trois_versions_les_plus_recentes(
    versions: list[dict[str, object]], expected: list[int]
) -> None:
    """Chaque paquet garde ses trois versions les plus récentes par date de création, étiquetées
    ou non (brief de #15, décision 1) — « au plus trois versions ». Le filtre est évalué par le
    moteur de `gh` : un tri inversé supprimerait `latest`."""
    assert stale_versions(versions) == expected


@pytest.mark.parametrize("failing", ["lecture", "suppression"])
def test_make_prune_echoue_quand_gh_echoue(tmp_path: Path, failing: str) -> None:
    """Un échec de `gh` fait échouer la rétention : ignoré, il laisserait la CI verte et les
    versions s'accumuler jusqu'au quota du compte."""
    gh = "false" if failing == "lecture" else fake_gh(tmp_path, failing_version=11)

    assert run_prune(gh).returncode != 0


@pytest.mark.parametrize(("workflow", "expected"), PUBLISH_FORMS.values(), ids=PUBLISH_FORMS.keys())
def test_la_garde_du_job_publish_rend_son_verdict_sur_chaque_forme(
    workflow: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle s'écarte du brief."""
    assert bool(publish_findings(workflow)) is expected, publish_findings(workflow)


def test_le_job_publish_ne_publie_qu_un_commit_de_main_une_fois_scanne() -> None:
    """Aucun `needs` : la PR a joué les vérifications, fusionnée au trunk (ADR 0031) ; push vers
    `main` seulement, `packages: write` sur ce seul job, publications sans annulation ; le front
    installé ici, build qui écrit le cache des couches, scan, connexion, push puis rétention, et
    rien n'atteint le registre avant le scan (brief de #15, décision 5).
    Un `workflow_run` est écarté : il publierait depuis le workflow de la branche par défaut
    (ADR 0014)."""
    assert publish_findings(CI_WORKFLOW.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(("workflow", "expected"), SMOKE_FORMS.values(), ids=SMOKE_FORMS.keys())
def test_la_garde_du_job_de_fumee_rend_son_verdict_sur_chaque_forme(
    workflow: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle s'écarte du brief de #26."""
    assert bool(smoke_findings(workflow)) is expected, smoke_findings(workflow)


def test_le_job_de_fumee_eprouve_les_images_du_commit_apres_leur_publication() -> None:
    """Après `publish`, sur un push vers `main` seulement, la lecture du dépôt et des paquets et
    rien d'autre, `make smoke` sur les images GHCR du commit — jamais `latest` —, et rien qui saute
    ou tolère son échec : rouge, il saute `deploy` (brief de #26, décision 2)."""
    assert smoke_findings(CI_WORKFLOW.read_text(encoding="utf-8")) == []


def test_la_publication_construit_sans_attestation() -> None:
    """Ni provenance ni SBOM (brief de #15, décision 7) : chacune ferait de l'image un index, dont
    chaque manifeste entrerait au paquet comme une version sans étiquette — que la rétention, qui
    compte toute version, supprimerait sous l'index qui la cite —, et rien ne les consomme. Sans
    ces drapeaux, `make build` exporte une attestation (mesuré au lot 1)."""
    printed = make_dry_run("build", environment={"DOCKER_BUILD_FLAGS": ci_build_flags("publish")})
    builds = [match.group().split() for match in BUILD_COMMAND.finditer(printed)]

    assert builds, "aucune commande de build lue — sa forme a-t-elle changé ?"
    assert all({"--provenance=false", "--sbom=false"} <= set(build) for build in builds)


def cache_inputs(job: str, action: str) -> object:
    """Les entrées de l'unique étape `action` du job `job` de `CACHED_BUILDS`."""
    steps = job_steps(CACHED_BUILDS[job][0], job)
    found = [step for step in steps if str(step.get("uses", "")).startswith(f"{action}@")]
    assert len(found) == 1, f"le job `{job}` a {len(found)} étape `{action}`"
    return found[0]["with"]


@pytest.mark.parametrize("job", [job for job in CACHED_BUILDS if job != "infra"])
def test_chaque_build_en_cache_prend_la_cle_du_job_infra(job: str) -> None:
    """`publish`, qui écrit l'entrée que `main` lit, et ceux qui la restaurent — `avis` pour
    scanner, `images` pour les tests du run hebdomadaire — prennent la clé d'`infra`, celle qu'une
    PR restaure, ou écrit si elle manque. Deux clés qui dériveraient feraient reconstruire à
    froid, sans un signal."""
    action = "actions/cache" if CACHED_BUILDS[job][1] else "actions/cache/restore"
    assert cache_inputs(job, action) == cache_inputs("infra", "actions/cache")
