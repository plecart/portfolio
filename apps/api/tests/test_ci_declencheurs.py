"""Tests de ce qui déclenche les jobs de la CI (`.github/workflows/ci.yml`, issue #124).

La CI ne dépense des minutes que là où un verdict peut changer (ADR 0017, ADR 0019, ADR 0031) :
une PR en draft ne tourne pas, son premier run vient du passage en ready, puis de chaque push ; le
run encore en cours d'une PR s'annule au push suivant de la même PR, jamais sur `main`, où le push
ne fait que livrer ; `web`, `infra` et `avis` attendent un `api` vert et ne tournent que si le
delta de la PR touche leurs fichiers — règle de `infra/ci/changed_jobs.py`, lue par la première
étape du job `api`. Le job `avis` appelle `.github/workflows/avis.yml`, qui joue aussi les portes
d'avis chaque jour sur `main`. Sur une PR, chaque job qui extrait le dépôt fusionne lui-même la
tête au trunk courant, par le pas « Fusion explicite du trunk », écrit dans la définition du
workflow et joué ici (ADR 0029).

Mesure qui fonde ces réglages, relevée le 2026-10-18 sur les runs du 2026-10-04 au 2026-10-17 —
`gh api --paginate "repos/plecart/portfolio/actions/runs?created=%3E%3D2026-10-04&per_page=100"`,
puis `…/actions/runs/<id>/jobs` pour chaque run, chaque job arrondi à la minute supérieure : 370
runs, 3 202 minutes facturées ; 70 runs de PR suivis d'un autre run de la même branche en moins de
5 minutes ; ≈ 1 020 minutes de `web` et `infra` sur des PR qui ne touchaient que la pipeline. Celle
qui fonde l'ADR 0019, relevée le 2026-10-28 sur les 100 derniers runs, est dans son § Contexte :
818 minutes en 3,85 jours, dont 112 de `web` et `infra` derrière un `api` déjà rouge. Population
vivante : ces chiffres changent à chaque run. L'invariant sous test est la forme du workflow et la
règle du script, jamais ces valeurs.

Comme dans `test_publication.py`, chaque garde est une fonction sur du texte, appliquée au dépôt et
à un recueil de formes construites en mémoire (`FORMS`) : le harnais de mutation refuse de muter
une porte de CI (obs 53).
"""

import ast
import json
import os
import subprocess
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from changed_jobs import IMAGE_TESTS, PIPELINE_TESTS, jobs_for
from system_commands import run_make
from test_infra import AVIS_WORKFLOW, CI_WORKFLOW, DISQUE_RUN, REPOSITORY_ROOT
from test_restore_workflow import triggers
from test_supply_chain import repository_files, texte_normalise

# Un run par PR, le plus récent : le groupe est le numéro de la PR. Sur un push vers `main`,
# `github.event.pull_request` est vide (doc GitHub « Contexts ») : le groupe se replie sur le SHA,
# propre à chaque commit, et l'annulation n'y vaut que sur `pull_request` — un push vers `main`
# publie et déploie, il ne s'annule jamais.
CONCURRENCY = {
    "group": "ci-${{ github.event.pull_request.number || github.sha }}",
    "cancel-in-progress": "${{ github.event_name == 'pull_request' }}",
}


def concurrency_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte sa concurrence de `CONCURRENCY`.

    Returns:
        Un constat si la clé `concurrency` du workflow manque ou diffère de `CONCURRENCY` ; liste
        vide sinon. Les groupes des jobs `publish` et `deploy` ne sont pas lus : ils s'ajoutent à
        celui du workflow, et leurs propres tests les tiennent.
    """
    concurrency = yaml.safe_load(workflow).get("concurrency")
    if concurrency != CONCURRENCY:
        return [f"`concurrency` vaut {concurrency!r}, attendu {CONCURRENCY!r}"]
    return []


# Le garde du job `api` : une PR prête seulement — il saute toute draft, quel que soit l'événement
# (ADR 0019), et tout push vers `main`, qui ne fait que livrer (ADR 0031, décision 1). Les jobs qui
# l'attendent sautent avec lui.
API_IF = "github.event_name == 'pull_request' && github.event.pull_request.draft == false"
# Les jobs que le delta d'une PR conditionne, et la sortie du job `api` que chacun lit.
GATED_JOBS = ("web", "infra", "avis")
API_OUTPUTS = {job: f"${{{{ steps.jobs.outputs.{job} }}}}" for job in GATED_JOBS}
# Le job `avis` appelle le workflow des portes d'avis, du même commit que `ci.yml` (doc GitHub
# « Reuse workflows », lue le 2026-10-29) : une seule définition de leurs cibles et de leur ordre,
# pour le run planifié comme pour la CI (ADR 0019, décision 2). Les cibles de ces portes, aucun
# job de pile ne les lance plus.
AVIS_CALL = "./.github/workflows/avis.yml"
ADVISORY_TARGETS = {"audit", "web-audit", "scan"}
STACK_JOBS = ("api", "web", "infra")
# Sur une PR, chaque job qui extrait le dépôt en extrait la tête, puis la fusionne lui-même au trunk
# courant par le pas de ce nom : la référence de fusion de la forge n'est pas recalculée quand le
# trunk avance, et un `gh run rerun` la réutilise (ADR 0029). Clone complet : la fusion exige
# l'ancêtre commun. Sur un push vers `main`, `ref` est vide et le checkout prend son défaut, le
# commit de l'événement (`src/input-helper.ts` d'`actions/checkout`, lu le 2026-11-08). Le pas vit
# dans la définition du workflow, lue au commit du run, jamais dans l'arbre extrait : une action
# locale se lirait dans la tête, qu'une PR ouverte avant elle ne porte pas.
FUSION_NAME = "Fusion explicite du trunk"
PR_HEAD = "${{ github.event.pull_request.head.sha }}"
FUSION_CHECKOUT = {"ref": PR_HEAD, "fetch-depth": 0}
# Les jobs qui ne tournent que sur un push vers `main`, où rien ne se fusionne : leur `if`, ce sont
# `test_publication.py` et `test_deployment.py` qui le tiennent.
PUSH_ONLY_JOBS = ("publish", "fumee", "deploy")
# L'étape `jobs`, sans son nom : le delta de la PR contre le trunk qu'elle a fusionné — `HEAD^1`,
# premier parent du commit du pas de fusion —, passé au script. `shell: bash` lance
# `bash -eo pipefail` (doc GitHub « Workflow syntax », `jobs.<job_id>.steps[*].shell`) : sans lui,
# un `git diff` en échec rendrait `false` pour chaque job, en silence. `--no-renames` : sans lui,
# un renommage ne s'écrit que sous son nouveau chemin (mesuré le 2026-10-20 : `apps/web/a.tsx`
# déplacé vers `docs/` ne rend que `docs/a.tsx`).
CHANGED_JOBS_COMMAND = (
    "git diff --name-only --no-renames HEAD^1 HEAD"
    ' | python3 infra/ci/changed_jobs.py >> "$GITHUB_OUTPUT"'
)
JOBS_STEP = {"id": "jobs", "shell": "bash", "run": CHANGED_JOBS_COMMAND}


def gated_if(job: str) -> str:
    """Le `if` d'un job conditionné : la réponse du script pour ce job. Sans fonction d'état,
    GitHub y applique `success()` (doc « Expressions », « Status check functions », lue le
    2026-10-28) : un `api` rouge, sauté ou annulé saute ce job (ADR 0019, décision 3) — et `api`
    saute tout push vers `main` (ADR 0031)."""
    return f"needs.api.outputs.{job} == 'true'"


def gating_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte le conditionnement de `GATED_JOBS` des ADR 0017, 0019 et
    0031.

    Returns:
        Un constat par propriété altérée : un job `changes` (un job de plus coûte une minute
        facturée par run), un `needs` sur `api`, son garde, ses `outputs`, son premier pas qui
        n'est pas le checkout `FUSION_CHECKOUT`, son second qui n'est pas le pas `FUSION_NAME` — le
        trunk en premier parent, `HEAD^1..HEAD` le delta —, son troisième qui n'est pas l'étape
        `JOBS_STEP` ; puis, pour chaque job de `GATED_JOBS`, un `needs` autre que `api` ou un `if`
        autre que `gated_if`. Liste vide : le workflow est conforme.
    """
    jobs = cast(dict[str, dict[str, Any]], yaml.safe_load(workflow)["jobs"])
    findings = (
        ["un job `changes` : l'ADR 0017 lit le delta dans `api`"] if "changes" in jobs else []
    )
    api = jobs.get("api") or {}
    if "needs" in api:
        findings.append(f"`api` attend {api['needs']} : il doit partir le premier")
    if api.get("if") != API_IF:
        findings.append(f"`api` porte le garde {api.get('if')!r}, attendu {API_IF!r}")
    if api.get("outputs") != API_OUTPUTS:
        findings.append(f"`api` rend {api.get('outputs')}, attendu {API_OUTPUTS}")
    steps = cast(list[dict[str, Any]], api.get("steps") or [])
    checkout, fusion, step = [*steps, {}, {}, {}][:3]
    if not str(checkout.get("uses")).startswith("actions/checkout@") or (
        checkout.get("with") != FUSION_CHECKOUT
    ):
        findings.append(
            f"le premier pas d'`api` est {checkout}, attendu un checkout {FUSION_CHECKOUT}"
        )
    if fusion.get("name") != FUSION_NAME:
        findings.append(f"le second pas d'`api` est {fusion}, attendu le pas « {FUSION_NAME} »")
    if {key: value for key, value in step.items() if key != "name"} != JOBS_STEP:
        findings.append(f"le troisième pas d'`api` est {step}, attendu {JOBS_STEP}")
    for name in GATED_JOBS:
        job = jobs.get(name) or {}
        if job.get("needs") != "api":
            findings.append(f"`{name}` attend {job.get('needs')}, attendu `api`")
        if job.get("if") != gated_if(name):
            findings.append(f"`{name}` porte {job.get('if')!r}, attendu {gated_if(name)!r}")
    return findings


def workflow_steps(workflow: str) -> dict[str, list[dict[str, Any]]]:
    """Les pas de chaque job d'un workflow ; aucun pour un job qui appelle un workflow."""
    jobs = cast(dict[str, dict[str, Any]], yaml.safe_load(workflow)["jobs"])
    return {name: cast(list[dict[str, Any]], job.get("steps") or []) for name, job in jobs.items()}


def fusion_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte un job de la fusion explicite du trunk (issue #249).

    Returns:
        Pour chaque job hors de `PUSH_ONLY_JOBS`, un constat par checkout qui ne porte pas la paire
        `FUSION_CHECKOUT`, et un si le pas `FUSION_NAME` ne suit pas immédiatement chaque checkout,
        et lui seul ; pour chaque job de `PUSH_ONLY_JOBS`, un constat s'il le porte. Que ce pas soit
        celui du job `api`, `test_chaque_pas_de_fusion_est_celui_du_job_api` le tient. Liste
        vide : le workflow est conforme.
    """
    findings: list[str] = []
    for name, steps in workflow_steps(workflow).items():
        uses = [str(step.get("uses", "")) for step in steps]
        fusions = [index for index, step in enumerate(steps) if step.get("name") == FUSION_NAME]
        if name in PUSH_ONLY_JOBS:
            if fusions:
                findings.append(f"`{name}`, qui ne tourne que sur un push, fusionne")
            continue
        checkouts = [
            index for index, action in enumerate(uses) if action.startswith("actions/checkout@")
        ]
        findings += [
            f"`{name}` extrait avec {steps[index].get('with')}, attendu {FUSION_CHECKOUT}"
            for index in checkouts
            if not FUSION_CHECKOUT.items() <= (steps[index].get("with") or {}).items()
        ]
        if fusions != [index + 1 for index in checkouts]:
            findings.append(
                f"`{name}` fusionne aux pas {fusions}, attendu juste après chaque checkout {checkouts}"
            )
    return findings


def advisory_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, sort les portes d'avis de `avis.yml` (ADR 0019, décision 2).

    Returns:
        Un constat si le job `avis` n'appelle pas `AVIS_CALL`, et un par pas d'un job de
        `STACK_JOBS` qui lance une cible de `ADVISORY_TARGETS`, seule ou parmi d'autres
        (`make lint audit`). Liste vide : le workflow est conforme.
    """
    jobs = cast(dict[str, dict[str, Any]], yaml.safe_load(workflow)["jobs"])
    findings: list[str] = []
    if (jobs.get("avis") or {}).get("uses") != AVIS_CALL:
        findings.append(f"`avis` n'appelle pas `{AVIS_CALL}`")
    for name in STACK_JOBS:
        steps = cast(list[dict[str, Any]], (jobs.get(name) or {}).get("steps") or [])
        runs = [str(step.get("run", "")).split() for step in steps]
        findings += [
            f"`{name}` lance `{' '.join(run)}` : les portes d'avis vivent dans `avis.yml`"
            for run in runs
            if run[:1] == ["make"] and ADVISORY_TARGETS & set(run)
        ]
    return findings


# Les déclencheurs du workflow. `ready_for_review` lance le premier run d'une PR, aucune draft n'en
# ayant (ADR 0019) : `cycle-pr` sort du draft, puis attend ce run (Étape 5). `reopened` reste :
# c'est la voie de relance d'une PR dont un événement s'est perdu pendant une panne d'Actions (même
# Étape), ou dont le trunk a changé la définition du workflow depuis le déclenchement — seul un
# événement neuf la relit (ADR 0029).
TRIGGERS = {
    "pull_request": {"types": ["opened", "synchronize", "reopened", "ready_for_review"]},
    "push": {"branches": ["main"]},
}


def trigger_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte ses déclencheurs de `TRIGGERS`.

    Returns:
        Un constat si les déclencheurs diffèrent de `TRIGGERS` — un type, une branche ou un
        déclencheur de plus ou de moins ; liste vide sinon.
    """
    found = triggers(yaml.safe_load(workflow))
    return (
        [] if found == TRIGGERS else [f"le workflow se déclenche sur {found}, attendu {TRIGGERS}"]
    )


# L'étape des tests de la pipeline, dans le job `api`, après celle de la suite du back : seulement si
# le delta de la PR la concerne — la sortie `pipeline` de l'étape `jobs` (ADR 0025, ADR 0031). Aucun
# job neuf : un job vide coûte une minute facturée (ADR 0017).
PIPELINE_IF = "steps.jobs.outputs.pipeline == 'true'"
PIPELINE_STEP = {"name": "Tests pipeline", "if": PIPELINE_IF, "run": "make test-pipeline"}


def pipeline_step_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte les tests de la pipeline de leur étape (ADR 0025).

    Returns:
        Un constat si le job `api` ne porte pas une et une seule étape `PIPELINE_STEP`, ou s'il
        la porte avant l'étape `make test` ; liste vide sinon.
    """
    jobs = cast(dict[str, dict[str, Any]], yaml.safe_load(workflow)["jobs"])
    steps = cast(list[dict[str, Any]], (jobs.get("api") or {}).get("steps") or [])
    runs = [step.get("run") for step in steps]
    found = [step for step in steps if step.get("run") == PIPELINE_STEP["run"]]
    if found != [PIPELINE_STEP]:
        return [f"`api` porte {found}, attendu une étape {PIPELINE_STEP}"]
    if "make test" not in runs or runs.index(PIPELINE_STEP["run"]) < runs.index("make test"):
        return ["l'étape des tests de la pipeline ne suit pas celle de la suite du back"]
    return []


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

TYPES_LINE = "    types: [opened, synchronize, reopened, ready_for_review]\n"
BRANCHES_LINE = "    branches: [main]\n"
TRIGGERS_BLOCK = f"on:\n  pull_request:\n{TYPES_LINE}  push:\n{BRANCHES_LINE}"

# Les lignes de la concurrence conforme, telles que le workflow les écrit.
GROUP_LINE = f"  group: {CONCURRENCY['group']}\n"
CANCEL_LINE = f"  cancel-in-progress: {CONCURRENCY['cancel-in-progress']}\n"
CONCURRENCY_BLOCK = f"concurrency:\n{GROUP_LINE}{CANCEL_LINE}"
# Le job `api` conforme, ses trois premiers pas en tête, puis l'installation.
API_IF_LINE = f"    if: {API_IF}\n"
OUTPUTS_LINES = "    outputs:\n" + "".join(f"      {k}: {v}\n" for k, v in API_OUTPUTS.items())
REF_LINE = f"          ref: {PR_HEAD}\n"
DEPTH_LINE = "          fetch-depth: 0\n"
CHECKOUT_LINES = f"      - uses: actions/checkout@v0\n        with:\n{REF_LINE}{DEPTH_LINE}"
# Le pas de fusion, par son seul nom : son contenu, `test_chaque_pas_de_fusion_est_celui_du_job_api`
# le tient sur les fichiers du dépôt.
FUSION_STEP_LINE = f"      - name: {FUSION_NAME}\n"
JOBS_STEP_LINES = (
    "      - name: Jobs à lancer\n        id: jobs\n        shell: bash\n"
    f"        run: {CHANGED_JOBS_COMMAND}\n"
)
INSTALL_LINES = "      - uses: astral-sh/setup-uv@v0\n      - run: make install\n"
# Les deux suites, celle du back puis celle de la pipeline.
TESTS_LINE = "      - run: make test\n"
PIPELINE_STEP_LINES = (
    f"      - name: Tests pipeline\n        if: {PIPELINE_IF}\n        run: make test-pipeline\n"
)
# Les jobs conditionnés : `web` et `infra` sans pas, `avis` qui appelle son workflow.
GATED_LINES = "".join(
    f"  {name}:\n    needs: api\n    if: {gated_if(name)}\n"
    + (f"    uses: {AVIS_CALL}\n" if name == "avis" else "    steps: []\n")
    for name in GATED_JOBS
)
CONFORMING_WORKFLOW = (
    f"{TRIGGERS_BLOCK}{CONCURRENCY_BLOCK}jobs:\n  api:\n{API_IF_LINE}{OUTPUTS_LINES}    steps:\n"
    f"{CHECKOUT_LINES}{FUSION_STEP_LINE}{JOBS_STEP_LINES}{INSTALL_LINES}"
    f"{TESTS_LINE}{PIPELINE_STEP_LINES}{GATED_LINES}"
)


def stack_step(name: str, lines: str) -> tuple[str, str]:
    """Le couple (texte remplacé, remplacement) qui donne les pas `lines` au job `name`, sans pas
    dans `CONFORMING_WORKFLOW`."""
    return (
        f"{gated_if(name)}\n    steps: []\n",
        f"{gated_if(name)}\n    steps:\n{lines}",
    )


Guard = Callable[[str], list[str]]
# (garde, texte remplacé, remplacement, constat attendu).
Form = tuple[Guard, str, str, bool]


def gated_forms(job: str) -> dict[str, Form]:
    """Les formes qui écartent le job `job` de `GATED_JOBS` du conditionnement des ADR 0017, 0019
    et 0031, chacune signalée. Une fonction d'état remplace le `success()` implicite."""
    return {
        f"{job} sans needs": (gating_findings, f"  {job}:\n    needs: api\n", f"  {job}:\n", True),
        # Le `if` de l'ADR 0017 : derrière un `api` rouge, un run paierait ce job.
        f"{job} : if avec !cancelled()": (
            gating_findings,
            gated_if(job),
            f"${{{{ !cancelled() && {gated_if(job)} }}}}",
            True,
        ),
        # Le `if` de l'ADR 0019 sous `!cancelled()` : sur un push vers `main`, où `api` est sauté,
        # le job tournerait.
        f"{job} : if qui tourne sur un push": (
            gating_findings,
            gated_if(job),
            f"${{{{ !cancelled() && (github.event_name != 'pull_request' || {gated_if(job)}) }}}}",
            True,
        ),
    }


# Forme → `Form`. Le texte remplacé est pris dans `CONFORMING_WORKFLOW` : une forme qui ne le
# changerait pas resterait conforme, et son verdict attendu la ferait rougir.
FORMS: dict[str, Form] = {
    "concurrence conforme": (concurrency_findings, "", "", False),
    "sans concurrence": (concurrency_findings, CONCURRENCY_BLOCK, "", True),
    "groupe constant": (concurrency_findings, GROUP_LINE, "  group: ci\n", True),
    "groupe par branche": (
        concurrency_findings,
        GROUP_LINE,
        "  group: ci-${{ github.ref }}\n",
        True,
    ),
    "annulation aussi sur main": (
        concurrency_findings,
        CANCEL_LINE,
        "  cancel-in-progress: true\n",
        True,
    ),
    "aucune annulation": (concurrency_findings, CANCEL_LINE, "  cancel-in-progress: false\n", True),
    "sans règle d'annulation": (concurrency_findings, CANCEL_LINE, "", True),
    "jobs conformes": (gating_findings, "", "", False),
    "étape jobs sans nom": (
        gating_findings,
        "      - name: Jobs à lancer\n        id",
        "      - id",
        False,
    ),
    "un job changes": (gating_findings, "jobs:\n", "jobs:\n  changes:\n    steps: []\n", True),
    "api avec needs": (gating_findings, "  api:\n", "  api:\n    needs: changes\n", True),
    "api sans garde draft": (gating_findings, API_IF_LINE, "", True),
    # L'ancien garde (ADR 0019) : sur un push vers `main`, `api` tournerait, et les jobs qui
    # l'attendent avec lui.
    "api aussi sur un push": (
        gating_findings,
        API_IF_LINE,
        "    if: github.event_name != 'pull_request' || github.event.pull_request.draft == false\n",
        True,
    ),
    # Sur un push, `draft` est nul, et GitHub compare `null` à `false` en nombres, 0 contre 0 (doc
    # « Expressions », « Operators », lue le 2026-11-21) : `api` tournerait.
    "api sans la condition d'événement": (
        gating_findings,
        "github.event_name == 'pull_request' && ",
        "",
        True,
    ),
    # L'ancien garde (ADR 0017) : chaque push d'une draft payait un run.
    "garde sur l'ouverture seule": (
        gating_findings,
        API_IF_LINE,
        (
            "    if: github.event_name != 'pull_request' || github.event.action != 'opened'"
            " || github.event.pull_request.draft == false\n"
        ),
        True,
    ),
    "api sans outputs": (gating_findings, OUTPUTS_LINES, "", True),
    "checkout sans ref": (gating_findings, REF_LINE, "", True),
    "checkout sans fetch-depth": (gating_findings, DEPTH_LINE, "", True),
    # L'ancienne profondeur, et celle que rendrait `cond && 0 || 2` : `0` y est faux.
    "checkout à profondeur 2": (gating_findings, DEPTH_LINE, "          fetch-depth: 2\n", True),
    "api sans pas de fusion": (gating_findings, FUSION_STEP_LINE, "", True),
    # L'étape `jobs` lirait le delta avant la fusion : `HEAD^1` serait le parent de la tête.
    "pas de fusion après l'étape jobs": (
        gating_findings,
        FUSION_STEP_LINE + JOBS_STEP_LINES,
        JOBS_STEP_LINES + FUSION_STEP_LINE,
        True,
    ),
    "étape jobs après make install": (
        gating_findings,
        JOBS_STEP_LINES + INSTALL_LINES,
        INSTALL_LINES + JOBS_STEP_LINES,
        True,
    ),
    "étape jobs sans shell bash": (gating_findings, "        shell: bash\n", "", True),
    "commande sans GITHUB_OUTPUT": (gating_findings, ' >> "$GITHUB_OUTPUT"', "", True),
    "commande qui suit les renommages": (gating_findings, " --no-renames", "", True),
    **{name: form for job in GATED_JOBS for name, form in gated_forms(job).items()},
    "if de web inversé": (
        gating_findings,
        "needs.api.outputs.web == 'true'",
        "needs.api.outputs.web != 'true'",
        True,
    ),
    "infra qui lit la sortie de web": (
        gating_findings,
        "needs.api.outputs.infra",
        "needs.api.outputs.web",
        True,
    ),
    "api sans la sortie avis": (
        gating_findings,
        f"      avis: {API_OUTPUTS['avis']}\n",
        "",
        True,
    ),
    "portes d'avis à leur place": (advisory_findings, "", "", False),
    # Le workflow de `main`, et non celui du commit : une PR qui change ses portes ne les verrait
    # pas jouer.
    "avis appelé depuis main": (
        advisory_findings,
        AVIS_CALL,
        "plecart/portfolio/.github/workflows/avis.yml@main",
        True,
    ),
    "api qui lance make audit": (
        advisory_findings,
        INSTALL_LINES,
        INSTALL_LINES + "      - run: make audit\n",
        True,
    ),
    "api qui lance l'audit parmi d'autres cibles": (
        advisory_findings,
        INSTALL_LINES,
        INSTALL_LINES + "      - run: make lint audit\n",
        True,
    ),
    "web qui lance make web-audit": (
        advisory_findings,
        *stack_step("web", "      - run: make web-audit\n"),
        True,
    ),
    "infra qui lance make scan": (
        advisory_findings,
        *stack_step("infra", "      - run: make scan\n"),
        True,
    ),
    "fusion conforme": (fusion_findings, "", "", False),
    "fusion : checkout sans ref": (fusion_findings, REF_LINE, "", True),
    "fusion : checkout sans fetch-depth": (fusion_findings, DEPTH_LINE, "", True),
    "fusion : pas absent": (fusion_findings, FUSION_STEP_LINE, "", True),
    "fusion : pas qui ne suit pas le checkout": (
        fusion_findings,
        FUSION_STEP_LINE + JOBS_STEP_LINES,
        JOBS_STEP_LINES + FUSION_STEP_LINE,
        True,
    ),
    # La garde vaut pour tout job qui peut tourner sur une PR, pas pour `api` seul.
    "fusion : web qui extrait sans la paire": (
        fusion_findings,
        *stack_step("web", "      - uses: actions/checkout@v0\n"),
        True,
    ),
    "fusion : web qui extrait et fusionne": (
        fusion_findings,
        *stack_step("web", CHECKOUT_LINES + FUSION_STEP_LINE),
        False,
    ),
    "fusion : publish qui fusionne": (
        fusion_findings,
        "jobs:\n",
        "jobs:\n  publish:\n    steps:\n" + CHECKOUT_LINES + FUSION_STEP_LINE,
        True,
    ),
    "fusion : publish qui extrait sans fusionner": (
        fusion_findings,
        "jobs:\n",
        "jobs:\n  publish:\n    steps:\n      - uses: actions/checkout@v0\n",
        False,
    ),
    "déclencheurs conformes": (trigger_findings, "", "", False),
    # L'ancienne liste (ADR 0017) : une PR sortie du draft resterait sans run jusqu'à son prochain
    # push.
    "sans ready_for_review": (
        trigger_findings,
        TYPES_LINE,
        "    types: [opened, synchronize, reopened]\n",
        True,
    ),
    "sans reopened": (
        trigger_findings,
        TYPES_LINE,
        "    types: [opened, synchronize, ready_for_review]\n",
        True,
    ),
    # Sans `types`, GitHub prend `opened`, `synchronize` et `reopened` (doc « Events that trigger
    # workflows », relue le 2026-10-28) : `ready_for_review` en sortirait.
    "sans types": (trigger_findings, "  pull_request:\n" + TYPES_LINE, "  pull_request:\n", True),
    "push sur toute branche": (trigger_findings, "  push:\n" + BRANCHES_LINE, "  push:\n", True),
    "étape des tests de la pipeline conforme": (pipeline_step_findings, "", "", False),
    "sans étape des tests de la pipeline": (
        pipeline_step_findings,
        PIPELINE_STEP_LINES,
        "",
        True,
    ),
    # Sans garde, l'étape paierait la suite sur chaque PR, que son delta la concerne ou non.
    "étape de la pipeline sans garde": (
        pipeline_step_findings,
        f"        if: {PIPELINE_IF}\n",
        "",
        True,
    ),
    "garde qui lit la sortie de web": (
        pipeline_step_findings,
        "steps.jobs.outputs.pipeline",
        "steps.jobs.outputs.web",
        True,
    ),
    "étape de la pipeline avant la suite du back": (
        pipeline_step_findings,
        TESTS_LINE + PIPELINE_STEP_LINES,
        PIPELINE_STEP_LINES + TESTS_LINE,
        True,
    ),
    "étape de la pipeline en double": (
        pipeline_step_findings,
        PIPELINE_STEP_LINES,
        PIPELINE_STEP_LINES * 2,
        True,
    ),
}


@pytest.mark.parametrize(("guard", "old", "new", "expected"), FORMS.values(), ids=FORMS.keys())
def test_chaque_garde_rend_son_verdict_sur_chaque_forme(
    guard: Guard, old: str, new: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle s'écarte de la forme conforme."""
    assert old in CONFORMING_WORKFLOW, f"forme absente de la forme conforme : {old!r}"
    findings = guard(CONFORMING_WORKFLOW.replace(old, new, 1))
    assert bool(findings) is expected, findings


@pytest.mark.parametrize("guard", dict.fromkeys(guard for guard, *_ in FORMS.values()))
def test_le_workflow_de_ci_est_conforme(guard: Guard) -> None:
    """Le `ci.yml` du dépôt passe chaque garde."""
    assert guard(CI_WORKFLOW.read_text(encoding="utf-8")) == []


# Les jobs dont le checkout fusionne, en littéraux (obs 80) : ceux de `ci.yml` qui peuvent tourner
# sur une PR, et le job de `avis.yml`, que `ci.yml` appelle sur une PR.
FUSING_WORKFLOWS = (CI_WORKFLOW, AVIS_WORKFLOW)
FUSING_JOBS = {
    ("ci.yml", "api"),
    ("ci.yml", "web"),
    ("ci.yml", "infra"),
    ("avis.yml", "avis"),
}


def fusion_steps() -> list[tuple[str, str, dict[str, Any]]]:
    """Les pas de fusion de `ci.yml` et `avis.yml`, chacun avec son fichier et son job."""
    return [
        (path.name, job, step)
        for path in FUSING_WORKFLOWS
        for job, steps in workflow_steps(path.read_text(encoding="utf-8")).items()
        for step in steps
        if step.get("name") == FUSION_NAME
    ]


def fusion_step() -> dict[str, Any]:
    """Le pas de fusion du job `api` de `ci.yml`, sous sa forme analysée : celui que les autres
    jobs reprennent."""
    (step,) = [step for name, job, step in fusion_steps() if (name, job) == ("ci.yml", "api")]
    return step


def test_chaque_job_qui_peut_tourner_sur_une_pr_fusionne_la_tete_au_trunk_courant() -> None:
    """`ci.yml` et `avis.yml` passent la garde de la fusion, et les jobs qui fusionnent sont ceux
    de `FUSING_JOBS` : un job que la garde cesserait de lire en sortirait."""
    texts = {path.name: path.read_text(encoding="utf-8") for path in FUSING_WORKFLOWS}
    assert {name: fusion_findings(text) for name, text in texts.items()} == {
        name: [] for name in texts
    }
    assert {(name, job) for name, job, _ in fusion_steps()} == FUSING_JOBS


def test_chaque_pas_de_fusion_est_celui_du_job_api() -> None:
    """Le pas du job `api` de `ci.yml` est le seul écrit en entier : les autres jobs de `ci.yml` le
    reprennent par alias (doc GitHub « Reusing workflow configurations », lue le 2026-11-08), et
    `avis.yml` en porte une copie, une ancre ne valant que dans son fichier. Analysés, ils lui sont
    égaux."""
    canonical = fusion_step()
    assert [(name, job) for name, job, step in fusion_steps() if step != canonical] == []


# --- Le workflow des portes d'avis : `.github/workflows/avis.yml` ------------------------------

# Ses déclencheurs (ADR 0019, décision 2) : chaque jour sur `main`, à une minute que le début
# d'heure n'encombre pas — GitHub y retarde, voire abandonne, les runs planifiés en période de
# charge (doc « Events that trigger workflows », `schedule`, lue le 2026-10-29) —, à la main, et
# appelé par le job `avis` de `ci.yml`. Ses permissions : la lecture du dépôt, rien d'autre.
AVIS_TRIGGERS = {
    "schedule": [{"cron": "37 5 * * *"}],
    "workflow_dispatch": None,
    "workflow_call": None,
}
AVIS_PERMISSIONS = {"contents": "read"}
# Les pas de son seul job, dans l'ordre — ce que chacun lance, `launched` : le checkout et le pas de
# fusion, qui ne joue qu'appelé sur une PR, l'audit Python, l'audit npm, puis le disque libéré, le
# build des images et leur scan, chaque porte après ce qu'elle lit. Le cache des couches, sous la
# clé du job `infra`, est restauré et jamais réécrit.
AVIS_STEPS = [
    "actions/checkout",
    FUSION_NAME,
    "astral-sh/setup-uv",
    "make install",
    "make audit",
    "actions/setup-node",
    "make web-install",
    "make web-audit",
    DISQUE_RUN,
    "docker/setup-buildx-action",
    "actions/cache/restore",
    "make build",
    "make scan",
]


def launched(step: dict[str, Any]) -> str:
    """Ce qu'un pas lance : le pas de fusion, son nom ; une commande, telle quelle ; une action,
    sans son empreinte."""
    if step.get("name") == FUSION_NAME:
        return FUSION_NAME
    return step.get("run") or str(step.get("uses", "")).split("@")[0]


def avis_findings(text: str) -> list[str]:
    """Ce qui, dans un workflow, écarte sa forme de celle des portes d'avis (ADR 0019).

    Returns:
        Un constat par propriété altérée — déclencheurs, `permissions` du workflow, un job autre
        que `avis` seul, et des pas autres que `AVIS_STEPS`, dans cet ordre. Ce qui rendrait le
        scan indicatif, `test_image_scan.py` le tient. Liste vide : le workflow est conforme.
    """
    workflow: dict[Any, Any] = yaml.safe_load(text)
    findings: list[str] = []
    if triggers(workflow) != AVIS_TRIGGERS:
        findings.append(f"déclencheurs {triggers(workflow)}, attendu {AVIS_TRIGGERS}")
    if workflow.get("permissions") != AVIS_PERMISSIONS:
        findings.append(
            f"`permissions` vaut {workflow.get('permissions')}, attendu {AVIS_PERMISSIONS}"
        )
    jobs: dict[str, Any] = workflow.get("jobs") or {}
    if list(jobs) != ["avis"]:
        return [*findings, f"jobs {list(jobs)}, attendu le seul job `avis`"]
    steps = cast(list[dict[str, Any]], jobs["avis"].get("steps") or [])
    found = [launched(step) for step in steps]
    if found != AVIS_STEPS:
        findings.append(f"le job lance {found}, attendu, dans cet ordre, {AVIS_STEPS}")
    return findings


# L'audit npm et ce dont il dépend, que la forme conforme place après l'audit Python.
AVIS_NPM_LINES = (
    "      - uses: actions/setup-node@v0\n"
    "      - run: make web-install\n"
    "      - run: make web-audit\n"
)
AVIS_CONFORMING = f"""\
on:
  schedule:
    - cron: "37 5 * * *"
  workflow_dispatch:
  workflow_call:
permissions:
  contents: read
jobs:
  avis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v0
      - name: {FUSION_NAME}
      - uses: astral-sh/setup-uv@v0
      - run: make install
      - run: make audit
{AVIS_NPM_LINES}\
      - run: {json.dumps(DISQUE_RUN)}
      - uses: docker/setup-buildx-action@v0
      - uses: actions/cache/restore@v0
      - run: make build
      - run: make scan
"""

# Forme → (texte remplacé, remplacement, constat attendu). Le texte remplacé est pris dans
# `AVIS_CONFORMING` : une forme qui ne le changerait pas resterait conforme, et son verdict attendu
# la ferait rougir.
AVIS_CHANGES = {
    "conforme": ("", "", False),
    "sans planning": ('  schedule:\n    - cron: "37 5 * * *"\n', "", True),
    "chaque semaine": ('"37 5 * * *"', '"37 5 * * 1"', True),
    "sans lancement à la main": ("  workflow_dispatch:\n", "", True),
    # Le job `avis` de `ci.yml` ne pourrait plus l'appeler.
    "sans appel par la CI": ("  workflow_call:\n", "", True),
    "écriture sur le dépôt": ("  contents: read\n", "  contents: write\n", True),
    "un second job": ("jobs:\n", "jobs:\n  autre:\n    steps: []\n", True),
    "sans fusion du trunk": (FUSION_STEP_LINE, "", True),
    "sans audit Python": ("      - run: make audit\n", "", True),
    "sans audit npm": ("      - run: make web-audit\n", "", True),
    "sans build": ("      - run: make build\n", "", True),
    "sans scan": ("      - run: make scan\n", "", True),
    "scan avant le build": (
        "      - run: make build\n      - run: make scan\n",
        "      - run: make scan\n      - run: make build\n",
        True,
    ),
    "audit Python après l'audit npm": (
        "      - run: make audit\n" + AVIS_NPM_LINES,
        AVIS_NPM_LINES + "      - run: make audit\n",
        True,
    ),
    "cache réécrit": ("actions/cache/restore@v0", "actions/cache@v0", True),
    "sans le disque libéré": (f"      - run: {json.dumps(DISQUE_RUN)}\n", "", True),
    "disque à moitié libéré": ("/usr/local/.ghcup ", "", True),
}


@pytest.mark.parametrize(("old", "new", "expected"), AVIS_CHANGES.values(), ids=AVIS_CHANGES.keys())
def test_la_garde_du_workflow_des_portes_d_avis_rend_son_verdict_sur_chaque_forme(
    old: str, new: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle s'écarte de l'ADR 0019."""
    assert old in AVIS_CONFORMING, f"forme absente de la forme conforme : {old!r}"
    findings = avis_findings(AVIS_CONFORMING.replace(old, new, 1))
    assert bool(findings) is expected, findings


def test_le_workflow_des_portes_d_avis_est_conforme() -> None:
    """L'`avis.yml` du dépôt : planifié, à la main et appelé par la CI, en lecture seule, ses
    quatre cibles dans l'ordre."""
    assert avis_findings(AVIS_WORKFLOW.read_text(encoding="utf-8")) == []


# --- Le script qui lit le delta : `infra/ci/changed_jobs.py` -----------------------------------

CHANGED_JOBS = REPOSITORY_ROOT / "infra" / "ci" / "changed_jobs.py"

# Delta → (`web`, `infra`, `avis`, `pipeline`) attendus. En littéraux, jamais dérivés des motifs du
# script : une table tirée de l'artefact sous test perdrait son cas avec le motif retiré (obs 80).
# Chaque motif du script a au moins un témoin qui rougit s'il disparaît. Les entrées témoins du
# corps de #124 y sont — il en annonce 11, sa liste en compte 10 —, plus quatre : pipeline et
# documentation hors Markdown, Dependabot et test mensuel, chemin non ASCII. Pour `infra`
# (ADR 0031, décision 2), une par motif de `INFRA` — `infra/`, les manifestes, les verrous,
# `.python-version`, une migration du back, `.dockerignore`, `.env.example` —, un module d'appui des
# tests des images, et les témoins du back, du front et du schéma de l'API, qui ne le font pas
# tourner. Pour `avis`, une par entrée de l'ADR 0019,
# décision 2 — onze, dont le `Makefile` et le verrou Python, déjà là —, une par chemin de `ALL` et
# le chemin cité ; les autres sont hors entrées. Pour `pipeline` (ADR 0025), un par motif de
# `PIPELINE` — `.claude/` hors Markdown, `CLAUDE.md`, `CONTRIBUTING.md`, `.github/` hors `ci.yml`,
# la description du schéma d'architecture, le manifeste racine, le verrou et la version de Python —
# et par chemin de `ALL`, le chemin cité, et le témoin du back, `apps/api/content/models.py`, qui
# ne la fait pas tourner.
JOBS_WITNESSES: dict[str, tuple[list[str], bool, bool, bool, bool]] = {
    "delta vide": ([], False, False, False, False),
    "pipeline, test du back et documentation": (
        [".claude/skills/x/SKILL.md", "apps/api/tests/test_x.py", "docs/a.md", "CLAUDE.md"],
        False,
        False,
        False,
        True,
    ),
    "pipeline hors Markdown": ([".claude/settings.json"], False, False, False, True),
    "règles de la session": (["CLAUDE.md"], False, False, False, True),
    "guide du contributeur": (["CONTRIBUTING.md"], False, False, False, True),
    "documentation hors Markdown": (["docs/diagramme.svg"], False, False, False, False),
    "description du schéma d'architecture": (
        ["docs/schema/architecture.json"],
        False,
        False,
        False,
        True,
    ),
    "Dependabot et test mensuel": (
        [".github/dependabot.yml", ".github/workflows/restore.yml"],
        False,
        False,
        False,
        True,
    ),
    "front": (["apps/web/src/main.tsx"], True, False, False, False),
    "back": (["apps/api/content/models.py"], False, False, False, False),
    "schéma de l'API": (["apps/api/openapi.json"], True, False, False, False),
    "migration du back": (
        ["apps/api/content/migrations/0001_initial.py"],
        False,
        True,
        False,
        False,
    ),
    "Makefile": (["Makefile"], True, True, True, True),
    "workflow de CI": ([".github/workflows/ci.yml"], True, True, True, True),
    "le script lui-même": (["infra/ci/changed_jobs.py"], True, True, True, True),
    "manifeste racine": (["pyproject.toml"], False, True, True, True),
    "manifeste du back": (["apps/api/pyproject.toml"], False, True, True, False),
    "verrou Python": (["uv.lock"], False, True, True, True),
    "version de Python": ([".python-version"], False, True, False, True),
    "manifeste du front": (["apps/web/package.json"], True, True, True, False),
    "verrou du front": (["apps/web/package-lock.json"], True, True, True, False),
    "Dockerfile d'une image": (["infra/caddy/Dockerfile"], False, True, True, False),
    "configuration de Caddy": (["infra/caddy/Caddyfile"], False, True, False, False),
    "contexte de build des images": ([".dockerignore"], False, True, False, False),
    "modèle de l'environnement": ([".env.example"], False, True, False, False),
    "exceptions du scan": ([".trivyignore.yaml"], False, False, True, False),
    "exceptions de l'audit Python": (
        ["infra/ci/pip-audit-exceptions.toml"],
        False,
        True,
        True,
        False,
    ),
    "porte de l'audit Python": (["infra/ci/pip_audit_gate.py"], False, True, True, False),
    "workflow des portes d'avis": ([".github/workflows/avis.yml"], False, False, True, True),
    "tests des images": (["infra/tests/test_caddy_image.py"], False, True, False, False),
    "module d'appui des tests des images": (
        ["apps/api/tests/test_infra.py"],
        False,
        True,
        False,
        False,
    ),
    # `fnmatchcase` : les chemins de git sont sensibles à la casse. Rouge sous Windows seulement
    # si `fnmatch` revenait : sous Linux, les deux coïncident.
    "casse distincte du front": (["APPS/WEB/a.tsx"], False, False, False, False),
    "chemin non ASCII, mis entre guillemets par git": (
        [r'"docs/caf\303\251.md"'],
        True,
        True,
        True,
        True,
    ),
}


@pytest.mark.parametrize(
    ("paths", "web", "infra", "avis", "pipeline"),
    JOBS_WITNESSES.values(),
    ids=JOBS_WITNESSES.keys(),
)
def test_le_delta_decide_des_jobs_et_des_tests_de_la_pipeline(
    paths: list[str], web: bool, infra: bool, avis: bool, pipeline: bool
) -> None:
    """Chaque témoin : la réponse de `jobs_for`, `web`, `infra`, `avis` puis `pipeline`."""
    assert jobs_for(paths) == {"web": web, "infra": infra, "avis": avis, "pipeline": pipeline}


@pytest.mark.parametrize(
    ("paths", "web", "infra", "avis", "pipeline"),
    JOBS_WITNESSES.values(),
    ids=JOBS_WITNESSES.keys(),
)
def test_le_script_ecrit_sa_reponse_au_format_github_output(
    paths: list[str], web: bool, infra: bool, avis: bool, pipeline: bool
) -> None:
    """Le script tel que l'étape `jobs` le lance : les chemins sur l'entrée standard, une ligne
    vide en plus — `git diff` n'en écrit pas, la ligne vide est ignorée —, et la réponse sur la
    sortie, au format que `$GITHUB_OUTPUT` lit."""
    completed = subprocess.run(
        [sys.executable, str(CHANGED_JOBS)],
        input="".join(f"{path}\n" for path in paths) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    answers = {"web": web, "infra": infra, "avis": avis, "pipeline": pipeline}
    assert completed.stdout == "".join(
        f"{job}={str(runs).lower()}\n" for job, runs in answers.items()
    )


def loaded_modules(seeds: list[Path], folders: tuple[str, ...]) -> set[str]:
    """Les fichiers de `apps/` qu'une suite charge : ses `seeds`, et tout module d'appui qu'ils
    importent, directement ou non, résolu dans le premier de `folders` qui le porte — l'ordre où
    `pytest` le cherche : le dossier du test d'abord (mode d'import par défaut), puis son
    `pythonpath`.

    Lue par l'analyseur de Python (`ast`), jamais par un motif : un `import` dans une fonction
    compte comme un `import` en tête. Le premier dossier seul compte : `conftest`, présent dans
    `.claude/tests` et dans `apps/api/tests`, ne désigne que le premier.
    """
    todo = list(seeds)
    seen: set[Path] = set()
    while todo:
        module = todo.pop()
        if module in seen:
            continue
        seen.add(module)
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            else:
                continue
            for name in names:
                paths = [
                    REPOSITORY_ROOT / folder / f"{name.split('.')[0]}.py" for folder in folders
                ]
                todo += [path for path in paths if path.is_file()][:1]
    return {
        module.relative_to(REPOSITORY_ROOT).as_posix()
        for module in seen
        if module.is_relative_to(REPOSITORY_ROOT / "apps")
    }


def image_test_modules() -> set[str]:
    """Les fichiers de `apps/api/tests/` que `make image-test` charge : le greffon de `addopts`,
    `process_environment`, et tout module d'appui que `infra/tests/` importe, directement ou non.
    Dénombré le 2026-10-20 (relecture de la PR #137, passe 1) : 5 fichiers — `call_witness`,
    `process_environment`, `test_env`, `test_infra`, `test_supply_chain` —, que le motif
    `apps/api/tests/*` sortait tous du job `infra`.
    """
    seeds = [*(REPOSITORY_ROOT / "infra" / "tests").glob("*.py")]
    seeds.append(REPOSITORY_ROOT / "apps" / "api" / "tests" / "process_environment.py")
    return loaded_modules(seeds, ("infra/tests", "apps/api/tests"))


def pipeline_test_modules() -> set[str]:
    """Les fichiers de `apps/api/tests/` que `make test-pipeline` charge : ce que `.claude/tests/`
    importe, directement ou non — sans `process_environment`, que la cible retire."""
    seeds = [*(REPOSITORY_ROOT / ".claude" / "tests").glob("*.py")]
    return loaded_modules(seeds, (".claude/tests", "apps/api/tests"))


def test_chaque_module_que_charge_image_test_fait_tourner_infra() -> None:
    """Un module d'appui des tests des images, changé seul, fait tourner `infra` : sans lui, une PR
    qui ne touche que lui sauterait les tests des images, et le rouge n'apparaîtrait qu'au push
    vers `main`, où il bloquerait `publish`. L'égalité garde aussi l'autre sens : un module qui
    cesse d'être chargé sort de la liste."""
    modules = image_test_modules()
    assert modules == set(IMAGE_TESTS)
    assert all(jobs_for([module])["infra"] for module in modules)


def test_chaque_module_que_charge_test_pipeline_fait_tourner_ses_tests() -> None:
    """Même règle pour la suite de la pipeline : un module d'appui du back qu'elle importe, changé
    seul, la fait tourner (ADR 0025)."""
    modules = pipeline_test_modules()
    assert modules == set(PIPELINE_TESTS)
    assert all(jobs_for([module])["pipeline"] for module in modules)


# --- La prose de la pipeline : le premier run vient du passage en ready ------------------------


# Les binaires de `.claude/`, où aucune prose ne se lit : les polices du rendu du skill
# `schema-architecture`. Un binaire d'une autre extension fait rougir la lecture en UTF-8 de
# `pipeline_texts()`, qui le signale au lieu de l'omettre.
BINARY_SUFFIXES = (".woff2",)


def pipeline_prose() -> list[str]:
    """Les fichiers de la pipeline : tout `.claude/` — skills, règles, rôles, scripts, réglages —,
    `CONTRIBUTING.md` et `CLAUDE.md`, tels que le prochain commit peut les contenir — un worktree
    sous `.claude/`, ignoré par git, n'en fait pas partie —, hors de ses binaires."""
    return [
        name
        for name in repository_files()
        if (name.startswith(".claude/") or name in {"CONTRIBUTING.md", "CLAUDE.md"})
        and not name.endswith(BINARY_SUFFIXES)
    ]


@cache
def pipeline_texts() -> dict[str, str]:
    """Chaque fichier de `pipeline_prose()` et son texte par `texte_normalise`, en minuscules : une
    phrase coupée en fin de ligne, dans une marge `# ` ou ouverte par une majuscule s'y lit d'un
    tenant."""
    return {name: texte_normalise(name).lower() for name in pipeline_prose()}


# Ce qui dit le contraire de l'ADR 0019 — une draft qui tourne, un passage en ready qui ne lance
# rien, un run lu avant de sortir du draft —, en minuscules, chaque phrase assez longue pour ne
# désigner que sa thèse : « l'ouverture d'une draft » seule dirait aussi un fait vrai. Dénombré
# avant le correctif, le 2026-10-28 sur `5467349` (l'arbre de `155b355`), par `pipeline_texts()`
# — 112 fichiers — : 18 phrases, 26 occurrences en 14 passages de 5 fichiers — `cycle-pr/SKILL.md`
# 7 (encadré de l'Étape 2, « Pousser avant chaque réveil » de l'Étape 4, cinq à l'Étape 5),
# `cycle-pr/references/briefing.md` 1 (la section de l'encadré), `cycle-pr/scripts/attente-ci.py`
# 4 (docstring, verdict vert), `init-projet/SKILL.md` 1 (« Conserver le garde `if:` »),
# `CONTRIBUTING.md` 1 (« Deux choses qui surprennent au début »). Hors de la table, parce que
# vrai : GitHub ne recalcule la référence de fusion « ni au passage en ready » (obs 51), dans
# `cycle-pr` (Étape 7, ce qui justifie l'ADR 0029) ; et le rollup tout `SKIPPED` de
# `cycle-pr/scripts/merge-lot.py`, « l'amorce vide d'une draft », exemple étroit d'une tête poussée
# en draft, dont le garde saute encore chaque job.
CONTRARY_PROSE = {
    "CI à chaque push d'une draft": "draft comprise",
    "premier run au premier push de code": "au premier push de code",
    "un push de code lance un run": "draft sans push de code",
    "CI pendant la relecture": "éprouve la plateforme cible pendant que la relecture tourne",
    "garde qui ne saute que l'ouverture": "ne saute que l'ouverture d'une draft",
    "skipped pris pour l'ouverture": "`skipped`, l'ouverture d'une draft",
    "sauté pris pour l'ouverture": "**sauté** — l'ouverture d'une draft",
    "seule l'ouverture sautée": "sauf à l'ouverture de la draft",
    "seule l'ouverture sautée, CONTRIBUTING": "sauf sur l'ouverture de la draft",
    "garde sur toute draft écarté": "élargir le garde à toute draft",
    "gh pr ready sans run": "`gh pr ready` ne déclenche aucun run",
    "passage en ready sans run": "en ready, lui, ne lance pas de run",
    "run lu avant le ready": "avant de sortir du draft, lire le run",
    "run lu avant le ready, init-projet": "run du sha de tête avant de sortir la pr du draft",
    "vert qui mène au ready": "→ sortir du draft",
    "vert qui mène au ready, docstring": "vert, sortir du draft",
    "ready après le run": "puis seulement, sortir du draft",
    "draft sautée hors panne": "sauf pour une draft jamais repoussée",
}


@pytest.mark.parametrize("phrase", CONTRARY_PROSE.values(), ids=CONTRARY_PROSE.keys())
def test_aucune_prose_ne_dit_qu_une_draft_tourne_ni_que_le_ready_ne_lance_rien(
    phrase: str,
) -> None:
    """Une prose qui le dirait ferait attendre, en draft, un run qui ne vient pas, ou sortir du
    draft sur la foi d'un verdict qui n'existe pas."""
    assert [name for name, text in pipeline_texts().items() if phrase in text] == []


CYCLE_PR = REPOSITORY_ROOT / ".claude" / "skills" / "cycle-pr" / "SKILL.md"


def step_5() -> str:
    """L'Étape 5 de `cycle-pr`, de son titre à celui de l'Étape 6, espaces normalisés : une ancre
    coupée en fin de ligne s'y lit d'un tenant (obs 124)."""
    text = CYCLE_PR.read_text(encoding="utf-8")
    return " ".join(text[text.index("## Étape 5 ") : text.index("## Étape 6 ")].split())


# Ce que l'Étape 5, qui sort du draft, doit dire : c'est ce geste qui lance le run attendu.
READY_RUN = "`gh pr ready` déclenche le premier run de la PR"


def test_l_etape_5_dit_que_gh_pr_ready_declenche_le_premier_run() -> None:
    """Sans elle, rien ne dit à un agent pourquoi il sort du draft avant d'attendre la CI."""
    assert READY_RUN in step_5()


# Les deux autres textes qui présentent la CI d'une draft le disent aussi, lus en minuscules par
# `pipeline_texts()` : l'encadré de l'Étape 2 de `cycle-pr`, et `CONTRIBUTING.md` pour qui arrive.
READY_RUN_PROSE = {
    ".claude/skills/cycle-pr/references/briefing.md": "le premier run vient du passage en ready",
    "CONTRIBUTING.md": "le premier part quand elle sort du draft (`gh pr ready`)",
}


@pytest.mark.parametrize(("name", "phrase"), READY_RUN_PROSE.items(), ids=READY_RUN_PROSE.keys())
def test_la_prose_qui_presente_la_ci_d_une_draft_dit_que_le_ready_lance_le_run(
    name: str, phrase: str
) -> None:
    """Sans elle, une draft sans check se lirait comme une CI cassée."""
    assert phrase in pipeline_texts()[name]


def test_cycle_pr_sort_du_draft_avant_de_lire_le_run_du_sha_de_tete() -> None:
    """À l'Étape 5, `gh pr ready` précède l'appel d'`attente-ci.py` : le passage en ready lance le
    run que le script attend, et un agent qui suit le skill dans l'ordre sort du draft d'abord
    (obs 30)."""
    step = step_5()
    assert "scripts/attente-ci.py <numéro>" in step
    assert step.index("gh pr ready <numéro>") < step.index("scripts/attente-ci.py <numéro>")


# Chaque issue de la lecture du run du SHA de tête, et le mot que l'Étape 5 doit porter pour elle
# après l'appel d'`attente-ci.py`. Dénombré le 2026-10-20 (relecture de la PR #137, passe 2) : une
# lecture qui ne rendait que la conclusion traitait 4 issues sur 6 — une réouverture laisse deux
# runs sur la même tête, `skipped` puis `success`, et la ligne `skipped` relançait une réouverture
# en boucle ; `cancelled` n'avait pas de voie. Depuis le lot 4b de #134, `attente-ci.py` tranche le
# plus récent, le run en cours et la tête remplacée — un cas chacun dans `test_attente_ci.py` — et
# rend une sortie par issue : ce sont elles que la prose porte. Depuis l'ADR 0019, une PR encore en
# draft a la sienne : 8 issues.
RUN_READINGS = {
    "vert": "- sortie 0, vert (`success`) →",
    "rouge": "- sortie 1, rouge — toute autre conclusion",
    "refus": "« refus — » sort aussi en 1",
    "draft": "- sortie 3, draft",
    "draft jamais repoussée": "- sortie 3 → « Si aucun run n'apparaît », ci-dessous : `skipped`",
    "annulé sans remplaçant": "`cancelled` sans nouvelle tête, annulé sans remplaçant",
    "aucun run": "aucun run au délai",
    "délai dépassé": "- sortie 124, délai dépassé",
}


@pytest.mark.parametrize("anchor", RUN_READINGS.values(), ids=RUN_READINGS.keys())
def test_l_etape_5_traite_chaque_issue_de_la_lecture_du_run(anchor: str) -> None:
    """Chaque issue a sa voie, écrite après l'appel d'`attente-ci.py` : un agent qui suit le skill
    dans l'ordre la lit quand le script lui rend sa ligne (obs 30)."""
    step = step_5()
    assert anchor in step
    assert step.index(anchor) > step.index("scripts/attente-ci.py <numéro>")


# --- Auteurs des commits d'une PR : un pas du job `api` ---

AUTHOR_STEP = "Refuser un auteur Claude"
CLAUDE_AUTHOR = "Claude <noreply@anthropic.com>"
HUMAN_AUTHOR = "plecart <pacome@lecart.dev>"


def api_steps() -> list[dict[str, Any]]:
    """Les pas du job `api` de `ci.yml`, sous leur forme analysée."""
    return workflow_steps(CI_WORKFLOW.read_text(encoding="utf-8"))["api"]


def author_step() -> dict[str, Any]:
    """Le pas du contrôle des auteurs, dans le job `api` de `ci.yml`."""
    (step,) = [step for step in api_steps() if step.get("name") == AUTHOR_STEP]
    return step


def git(repo: Path, *args: str) -> str:
    """`git <args>` dans `repo`, sa sortie standard sans blancs autour ; une erreur lève. Le dépôt
    témoin se construit avec son identité, jamais le pas sous test."""
    identity = (
        "-c",
        "user.name=ci",
        "-c",
        "user.email=ci@example.test",
        "-c",
        "commit.gpgsign=false",
    )
    return subprocess.run(
        ["git", *identity, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def pr_merge_commit(repo: Path, author: str) -> None:
    """Pose dans `repo` la forme que la CI extrait : un commit de fusion, tête de PR en second parent.

    `author` écrit le premier commit de la PR, pas sa tête, et le trunk est d'auteur Claude : le pas
    doit lire tous les commits de la PR, et eux seuls."""
    git(repo, "init", "-b", "main")
    git(repo, "commit", "--allow-empty", "-m", "base")
    git(repo, "checkout", "-b", "pr")
    git(repo, "commit", "--allow-empty", "-m", "commit de la PR", f"--author={author}")
    git(repo, "commit", "--allow-empty", "-m", "tête de la PR", f"--author={HUMAN_AUTHOR}")
    git(repo, "checkout", "main")
    git(repo, "commit", "--allow-empty", "-m", "trunk", f"--author={CLAUDE_AUTHOR}")
    git(repo, "merge", "--no-ff", "-m", "fusion", "pr")


def play_step(
    step: dict[str, Any], repo: Path, bash: str, **env: str
) -> subprocess.CompletedProcess[str]:
    """Le `run` d'un pas tel que son fichier l'écrit, sous le shell d'Actions (`shell: bash`, doc
    GitHub « Workflow syntax »), dans `repo`, l'environnement du test complété de `env`."""
    return subprocess.run(
        [bash, "-eo", "pipefail", "-c", step["run"]],
        cwd=repo,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def play_author_step(repo: Path, bash: str) -> int:
    """Le code de sortie du pas tel que `ci.yml` l'écrit, sous le shell d'Actions."""
    return play_step(author_step(), repo, bash).returncode


@pytest.mark.parametrize(
    ("author", "code"),
    [
        (CLAUDE_AUTHOR, 1),
        (CLAUDE_AUTHOR.upper(), 1),
        (HUMAN_AUTHOR, 0),
        ("noreply@anthropic.com <pacome@lecart.dev>", 0),
        ("x <noreply@anthropic.com.evil>", 0),
    ],
    ids=[
        "auteur Claude refusé",
        "casse ignorée",
        "auteur humain accepté",
        "adresse dans le nom seulement",
        "adresse plus longue",
    ],
)
def test_le_controle_des_auteurs_refuse_un_commit_de_pr_d_auteur_claude(
    tmp_path: Path, author: str, code: int, bash_de_ce_systeme: str
) -> None:
    """Joué sur un commit de fusion réel."""
    pr_merge_commit(tmp_path, author)
    assert play_author_step(tmp_path, bash_de_ce_systeme) == code


def test_le_controle_des_auteurs_echoue_ferme_si_git_log_echoue(
    tmp_path: Path, bash_de_ce_systeme: str
) -> None:
    """Dans un dépôt sans commit, `git log` échoue : le pas rougit au lieu de passer sans rien lire."""
    git(tmp_path, "init", "-b", "main")
    assert play_author_step(tmp_path, bash_de_ce_systeme) != 0


def test_le_controle_des_auteurs_ignore_le_mailmap(tmp_path: Path, bash_de_ce_systeme: str) -> None:
    """`--author` lit `.mailmap` : une PR qui en apporte un ne masque pas un commit Claude."""
    pr_merge_commit(tmp_path, CLAUDE_AUTHOR)
    (tmp_path / ".mailmap").write_text(
        "plecart <pacome@lecart.dev> Claude <noreply@anthropic.com>\n", encoding="utf-8"
    )
    assert play_author_step(tmp_path, bash_de_ce_systeme) == 1


def test_le_controle_des_auteurs_est_le_pas_d_api_qui_suit_l_etape_jobs() -> None:
    """Un pas, non un job : un job compte au moins une minute (ADR 0031, décision 5). Juste après
    l'étape `jobs`, avant toute installation, et sans `if` qui le sauterait : il tourne avec tout
    le job `api`, sur une PR prête seulement, clone complet fusionné au trunk — `gating_findings`
    tient son garde et ses trois premiers pas."""
    steps, step = api_steps(), author_step()
    assert steps.index(step) == [each.get("id") for each in steps].index("jobs") + 1
    assert "if" not in step


# --- La fusion explicite du trunk : le pas « Fusion explicite du trunk » de `ci.yml` ------------

# Son cadre : sur une PR seulement ; le trunk est la branche cible de la PR — pas `main` en dur :
# une PR de lot vise la branche d'intégration de son issue —, passé avec la tête par
# l'environnement, jamais développé dans le script.
FUSION_FRAME = {
    "if": "github.event_name == 'pull_request'",
    "shell": "bash",
    "env": {
        "TRUNK": "${{ github.event.pull_request.base.ref }}",
        "HEAD_SHA": PR_HEAD,
    },
}
# L'identité du commit de fusion, que le pas se donne : le runner n'en a aucune.
FUSION_COMMITTER = "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
# Le préfixe de la ligne de trace, qu'un pas en échec n'écrit pas. Sa forme, et qu'aucune ligne du
# script ne l'imite, `.claude/tests/test_porte_merge.py` les tient : il fait lire par la porte ce
# que le pas écrit, script recopié compris.
TRACE_PREFIX = "Fusion explicite"
# Le fichier que la base porte et que le trunk change : la tête qui le change aussi entre en conflit.
CONFLICTED = "conflit.txt"


def play_fusion(repo: Path, bash: str, head: str) -> subprocess.CompletedProcess[str]:
    """Le pas de fusion joué dans `repo` comme sur une PR de tête `head` vers `main`."""
    return play_step(fusion_step(), repo, bash, TRUNK="main", HEAD_SHA=head)


def error_lines(played: subprocess.CompletedProcess[str]) -> list[str]:
    """Les annotations d'erreur que le pas a écrites."""
    return [line for line in played.stdout.splitlines() if line.startswith("::error::")]


@pytest.fixture
def git_isole(monkeypatch: pytest.MonkeyPatch) -> None:
    """La configuration git du poste écartée (`.claude/rules/cleanup-verbatim.md`, lecture d'état
    `git`), et l'identité que l'environnement pourrait donner : le pas fusionne sans elles."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    identity = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")
    for name in (*identity, "EMAIL"):
        monkeypatch.delenv(name, raising=False)


def as_checked_out(repo: Path) -> tuple[str, str]:
    """Laisse `repo` comme le checkout le laisse au pas : le trunk, la branche `main`, en
    `refs/remotes/origin/main`, et la tête, la branche `pr`, extraite détachée, sans branche locale.

    Returns:
        Le trunk et la tête, en SHA complets.
    """
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    trunk, head = git(repo, "rev-parse", "main", "pr").split()
    git(repo, "checkout", "--detach", head)
    git(repo, "branch", "-D", "main", "pr")
    return trunk, head


def trunk_and_head(repo: Path, changed: str) -> tuple[str, str]:
    """Pose dans `repo` un trunk avancé depuis la base de la tête, tel que le checkout le laisse
    (`as_checked_out`). La base porte `CONFLICTED`, que le trunk change ; la tête change `changed`.
    """
    git(repo, "init", "-b", "main")
    (repo / CONFLICTED).write_text("base", encoding="utf-8")
    git(repo, "add", CONFLICTED)
    git(repo, "commit", "-m", "base")
    git(repo, "checkout", "-b", "pr")
    (repo / changed).write_text("tête", encoding="utf-8")
    git(repo, "add", changed)
    git(repo, "commit", "-m", "tête de la PR")
    git(repo, "checkout", "main")
    (repo / CONFLICTED).write_text("trunk", encoding="utf-8")
    git(repo, "commit", "-am", "trunk")
    return as_checked_out(repo)


def trace_lines(text: str) -> list[str]:
    """Les lignes de `text` qui commencent par `TRACE_PREFIX`, blancs ôtés."""
    return [line for line in map(str.strip, text.splitlines()) if line.startswith(TRACE_PREFIX)]


def test_le_pas_de_fusion_ne_joue_que_sur_une_pr_vers_sa_branche_cible() -> None:
    """Sur un push, rien ne se fusionne ; sur une PR, le trunk est celui qu'elle vise. Aucune
    expression dans le script : une branche nommée par l'auteur de la PR y serait développée en
    shell."""
    step = fusion_step()
    assert {key: step.get(key) for key in FUSION_FRAME} == FUSION_FRAME
    assert "${{" not in step["run"]


@pytest.mark.usefixtures("git_isole")
def test_le_pas_fusionne_la_tete_au_trunk_courant_trunk_en_premier_parent(
    tmp_path: Path, bash_de_ce_systeme: str
) -> None:
    """Le trunk en premier parent, la tête en second — `HEAD^1..HEAD` reste le delta, `HEAD^1..HEAD^2`
    les commits de la PR —, le message en SHA complets et l'identité du robot d'Actions. La ligne de
    trace, `.claude/tests/test_porte_merge.py` la fait lire par la porte."""
    trunk, head = trunk_and_head(tmp_path, "autre.txt")

    played = play_fusion(tmp_path, bash_de_ce_systeme, head)

    assert played.returncode == 0, played.stderr
    first, second = git(tmp_path, "rev-parse", "HEAD^1", "HEAD^2").split()
    assert [first, second] == [trunk, head]
    assert git(tmp_path, "log", "-1", "--format=%s%n%cn <%ce>").splitlines() == [
        f"Merge {head} into {trunk}",
        FUSION_COMMITTER,
    ]


@pytest.mark.usefixtures("git_isole")
def test_le_pas_echoue_sur_un_conflit_et_nomme_le_fichier(
    tmp_path: Path, bash_de_ce_systeme: str
) -> None:
    """La même ligne changée des deux côtés : le pas échoue, une annotation d'erreur nomme la tête,
    le trunk et le fichier en conflit, et aucune trace de fusion n'est écrite."""
    trunk, head = trunk_and_head(tmp_path, CONFLICTED)

    played = play_fusion(tmp_path, bash_de_ce_systeme, head)

    errors = error_lines(played)
    assert played.returncode != 0
    assert len(errors) == 1, played.stdout
    assert all(part in errors[0] for part in (head, f"origin/main ({trunk})", CONFLICTED)), errors
    assert trace_lines(played.stdout + played.stderr) == []


# Les formes d'une tête que le trunk contient déjà : les gestes qui, la tête posée sur la branche
# `pr` depuis la base, amènent `main` à la contenir. Sur chacune, `merge --no-ff` sort en 0 sans
# construire de commit (mesuré le 2026-11-08, git 2.47.1).
CONTAINED_HEADS = {
    "tête au sommet du trunk": [("merge", "--ff-only", "pr")],
    "tête ancêtre du trunk": [
        ("merge", "--ff-only", "pr"),
        ("commit", "--allow-empty", "-m", "trunk"),
    ],
    # Le sommet du trunk est une fusion, la tête en second parent : `HEAD^2` existe, et seul le
    # commit construit, comparé au trunk, dit que rien ne l'a été.
    "tête second parent du sommet du trunk": [
        ("commit", "--allow-empty", "-m", "trunk"),
        ("merge", "--no-ff", "-m", "fusion", "pr"),
    ],
}


@pytest.mark.usefixtures("git_isole")
@pytest.mark.parametrize("gestures", CONTAINED_HEADS.values(), ids=CONTAINED_HEADS.keys())
def test_le_pas_echoue_sur_une_tete_que_le_trunk_contient_deja(
    tmp_path: Path, gestures: list[tuple[str, ...]], bash_de_ce_systeme: str
) -> None:
    """Rien n'est construit : le pas échoue, une annotation d'erreur nomme la tête et le trunk, et
    aucune trace n'est écrite — elle donnerait pour fusion un commit du trunk."""
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "commit", "--allow-empty", "-m", "base")
    git(tmp_path, "checkout", "-b", "pr")
    git(tmp_path, "commit", "--allow-empty", "-m", "tête de la PR")
    git(tmp_path, "checkout", "main")
    for gesture in gestures:
        git(tmp_path, *gesture)
    trunk, head = as_checked_out(tmp_path)

    played = play_fusion(tmp_path, bash_de_ce_systeme, head)

    errors = error_lines(played)
    assert played.returncode != 0
    assert len(errors) == 1, played.stdout
    assert all(part in errors[0] for part in (head, f"origin/main ({trunk})")), errors
    assert trace_lines(played.stdout + played.stderr) == []


# --- L'e2e du job `web` : le seul projet `desktop` (ADR 0031, décision 3) -----------------------

E2E_PROJECT_OPTION = "--project="


def e2e_projects(*variables: str) -> list[str]:
    """Les projets Playwright que `make web-e2e` nomme, lancé avec `variables` — des affectations,
    telles qu'une ligne de commande les écrit ; aucun : Playwright joue tous ceux de sa
    configuration."""
    printed = run_make("--dry-run", "web-e2e", *variables)
    printed.check_returncode()
    words = printed.stdout.split()
    return [
        word.removeprefix(E2E_PROJECT_OPTION)
        for word in words
        if word.startswith(E2E_PROJECT_OPTION)
    ]


def test_le_job_web_ne_joue_que_le_projet_desktop_du_front_qu_il_a_compile() -> None:
    """Le pas e2e du job `web` lance `make web-e2e` avec la variable qui choisit les projets, que le
    `Makefile` développe en `--project=desktop` seul : le projet `mobile` est au run hebdomadaire
    (ADR 0031, décisions 3 et 4). Il suit `make web-build` : sous `CI`, Playwright sert ce front
    sans le recompiler (`apps/web/playwright.config.ts`)."""
    steps = workflow_steps(CI_WORKFLOW.read_text(encoding="utf-8"))["web"]
    runs = [str(step.get("run", "")).split() for step in steps]
    (e2e,) = [index for index, run in enumerate(runs) if run[:2] == ["make", "web-e2e"]]
    assert runs.index(["make", "web-build"]) < e2e
    assert e2e_projects(*runs[e2e][2:]) == ["desktop"]


def test_sur_le_poste_make_web_e2e_joue_tous_les_projets() -> None:
    """Sans variable, `make web-e2e` ne nomme aucun projet : Playwright les joue tous."""
    assert e2e_projects() == []
