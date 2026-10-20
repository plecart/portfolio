"""Tests de ce qui déclenche les jobs de la CI (`.github/workflows/ci.yml`, issue #124).

La CI ne dépense des minutes que là où un verdict peut changer (ADR 0017) : le run encore en cours
d'une PR s'annule au push suivant de la même PR, jamais sur `main` ; sur une PR, `web` et `infra`
ne tournent que si le delta touche leurs fichiers — règle de `infra/ci/changed_jobs.py`, lue par la
première étape du job `api`.

Mesure qui fonde ces réglages, relevée le 2026-10-18 sur les runs du 2026-10-04 au 2026-10-17 —
`gh api --paginate "repos/plecart/portfolio/actions/runs?created=%3E%3D2026-10-04&per_page=100"`,
puis `…/actions/runs/<id>/jobs` pour chaque run, chaque job arrondi à la minute supérieure : 370
runs, 3 202 minutes facturées ; 70 runs de PR suivis d'un autre run de la même branche en moins de
5 minutes ; ≈ 1 020 minutes de `web` et `infra` sur des PR qui ne touchaient que la pipeline.
Population vivante : ces chiffres changent à chaque run. L'invariant sous test est la forme du
workflow et la règle du script, jamais ces valeurs.

Comme dans `test_publication.py`, chaque garde est une fonction sur du texte, appliquée au dépôt et
à un recueil de formes construites en mémoire (`FORMS`) : le harnais de mutation refuse de muter
une porte de CI (obs 53).
"""

import ast
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from changed_jobs import IMAGE_TESTS, jobs_for
from test_agent_skills import CYCLE_PR
from test_infra import CI_WORKFLOW, REPOSITORY_ROOT
from test_restore_workflow import triggers
from test_supply_chain import repository_files

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


# Le garde du job `api` : il ne saute que l'ouverture d'une draft, dont l'amorce est vide.
API_IF = (
    "github.event_name != 'pull_request' || github.event.action != 'opened'"
    " || github.event.pull_request.draft == false"
)
# Les jobs que le delta d'une PR conditionne, et la sortie du job `api` que chacun lit.
GATED_JOBS = ("web", "infra")
API_OUTPUTS = {job: f"${{{{ steps.jobs.outputs.{job} }}}}" for job in GATED_JOBS}
# L'étape `jobs`, sans son nom : le delta de la PR contre sa base — le checkout d'une PR est son
# commit de fusion, `HEAD^1` la base qu'il combine —, passé au script. `shell: bash` lance
# `bash -eo pipefail` (doc GitHub « Workflow syntax », `jobs.<job_id>.steps[*].shell`) : sans lui,
# un `git diff` en échec rendrait `false` pour les deux jobs, en silence. `--no-renames` : sans lui,
# un renommage ne s'écrit que sous son nouveau chemin (mesuré le 2026-10-20 : `apps/web/a.tsx`
# déplacé vers `docs/` ne rend que `docs/a.tsx`).
CHANGED_JOBS_COMMAND = (
    "git diff --name-only --no-renames HEAD^1 HEAD"
    ' | python3 infra/ci/changed_jobs.py >> "$GITHUB_OUTPUT"'
)
JOBS_STEP = {"id": "jobs", "shell": "bash", "run": CHANGED_JOBS_COMMAND}


def gated_if(job: str) -> str:
    """Le `if` d'un job conditionné : sur une PR, la réponse du script pour ce job ; sur un push
    vers `main`, toujours — `publish` y attend les trois jobs. `!cancelled()` : le job part même
    quand `api` rougit plus loin, un rouge du back ne masquant pas un rouge du front (ADR 0014),
    mais pas quand le run est annulé par un push suivant. Mesuré le 2026-10-18 (run 39139043268,
    corps de #124) : les `outputs` d'un job rouge sont lus par ses jobs aval en `!cancelled()`."""
    return (
        "${{ !cancelled() && (github.event_name != 'pull_request'"
        f" || needs.api.outputs.{job} == 'true') }}}}"
    )


def gating_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte le conditionnement de `web` et `infra` de l'ADR 0017.

    Returns:
        Un constat par propriété altérée : un job `changes` (un job de plus coûte une minute
        facturée par run), un `needs` sur `api`, son garde, ses `outputs`, son premier pas qui
        n'est pas un checkout à profondeur 2 — le commit de fusion et sa base —, son second pas qui
        n'est pas l'étape `JOBS_STEP` ; puis, pour `web` et `infra`, un `needs` autre que `api` ou
        un `if` autre que `gated_if`. Liste vide : le workflow est conforme.
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
    checkout, step = [*steps, {}, {}][:2]
    if not str(checkout.get("uses")).startswith("actions/checkout@") or checkout.get("with") != {
        "fetch-depth": 2
    }:
        findings.append(
            f"le premier pas d'`api` est {checkout}, attendu un checkout à profondeur 2"
        )
    if {key: value for key, value in step.items() if key != "name"} != JOBS_STEP:
        findings.append(f"le second pas d'`api` est {step}, attendu {JOBS_STEP}")
    for name in GATED_JOBS:
        job = jobs.get(name) or {}
        if job.get("needs") != "api":
            findings.append(f"`{name}` attend {job.get('needs')}, attendu `api`")
        if job.get("if") != gated_if(name):
            findings.append(f"`{name}` porte {job.get('if')!r}, attendu {gated_if(name)!r}")
    return findings


# Les déclencheurs du workflow. Pas de `ready_for_review` : le passage en ready rejouait un SHA déjà
# couvert, sur la référence de fusion existante, que GitHub ne recalcule pas (obs 51) ; `cycle-pr`
# (Étape 5) lit à la place le run du SHA de tête. `reopened` reste : c'est la voie de relance d'une
# PR dont un événement s'est perdu pendant une panne d'Actions (même Étape).
TRIGGERS = {
    "pull_request": {"types": ["opened", "synchronize", "reopened"]},
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


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

TYPES_LINE = "    types: [opened, synchronize, reopened]\n"
BRANCHES_LINE = "    branches: [main]\n"
TRIGGERS_BLOCK = f"on:\n  pull_request:\n{TYPES_LINE}  push:\n{BRANCHES_LINE}"

# Les lignes de la concurrence conforme, telles que le workflow les écrit.
GROUP_LINE = f"  group: {CONCURRENCY['group']}\n"
CANCEL_LINE = f"  cancel-in-progress: {CONCURRENCY['cancel-in-progress']}\n"
CONCURRENCY_BLOCK = f"concurrency:\n{GROUP_LINE}{CANCEL_LINE}"
# Le job `api` conforme, ses deux premiers pas en tête, puis l'installation.
API_IF_LINE = f"    if: {API_IF}\n"
OUTPUTS_LINES = "    outputs:\n" + "".join(f"      {k}: {v}\n" for k, v in API_OUTPUTS.items())
DEPTH_LINES = "        with:\n          fetch-depth: 2\n"
JOBS_STEP_LINES = (
    "      - name: Jobs à lancer\n        id: jobs\n        shell: bash\n"
    f"        run: {CHANGED_JOBS_COMMAND}\n"
)
INSTALL_LINES = "      - uses: astral-sh/setup-uv@v0\n      - run: make install\n"
GATED_LINES = "".join(
    f"  {name}:\n    needs: api\n    if: {gated_if(name)}\n    steps: []\n" for name in GATED_JOBS
)
CONFORMING_WORKFLOW = (
    f"{TRIGGERS_BLOCK}{CONCURRENCY_BLOCK}jobs:\n  api:\n{API_IF_LINE}{OUTPUTS_LINES}    steps:\n"
    f"      - uses: actions/checkout@v0\n{DEPTH_LINES}{JOBS_STEP_LINES}{INSTALL_LINES}{GATED_LINES}"
)

Guard = Callable[[str], list[str]]

# Forme → (garde, texte remplacé, remplacement, constat attendu). Le texte remplacé est pris dans
# `CONFORMING_WORKFLOW` : une forme qui ne le changerait pas resterait conforme, et son verdict
# attendu la ferait rougir.
FORMS: dict[str, tuple[Guard, str, str, bool]] = {
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
    "api sans outputs": (gating_findings, OUTPUTS_LINES, "", True),
    "checkout sans fetch-depth": (gating_findings, DEPTH_LINES, "", True),
    "étape jobs après make install": (
        gating_findings,
        JOBS_STEP_LINES + INSTALL_LINES,
        INSTALL_LINES + JOBS_STEP_LINES,
        True,
    ),
    "étape jobs sans shell bash": (gating_findings, "        shell: bash\n", "", True),
    "commande sans GITHUB_OUTPUT": (gating_findings, ' >> "$GITHUB_OUTPUT"', "", True),
    "commande qui suit les renommages": (gating_findings, " --no-renames", "", True),
    "web sans needs": (gating_findings, "  web:\n    needs: api\n", "  web:\n", True),
    "infra sans needs": (gating_findings, "  infra:\n    needs: api\n", "  infra:\n", True),
    # Sur `main`, `publish` perdrait l'artefact `dist` du job `web`.
    "if de web qui ignore le push": (
        gating_findings,
        gated_if("web"),
        "${{ !cancelled() && needs.api.outputs.web == 'true' }}",
        True,
    ),
    # Un rouge d'`api` masquerait celui de `web`.
    "if de web sans !cancelled()": (
        gating_findings,
        gated_if("web"),
        "${{ github.event_name != 'pull_request' || needs.api.outputs.web == 'true' }}",
        True,
    ),
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
    "déclencheurs conformes": (trigger_findings, "", "", False),
    "avec ready_for_review": (
        trigger_findings,
        TYPES_LINE,
        "    types: [opened, synchronize, reopened, ready_for_review]\n",
        True,
    ),
    "sans reopened": (trigger_findings, TYPES_LINE, "    types: [opened, synchronize]\n", True),
    # Sans `types`, GitHub prend `opened`, `synchronize` et `reopened` (doc « Events that trigger
    # workflows », relue le 2026-10-20) : la forme est équivalente aujourd'hui, mais un défaut qui
    # changerait rouvrirait le run au ready sans qu'aucune ligne du dépôt ne bouge.
    "sans types": (trigger_findings, "  pull_request:\n" + TYPES_LINE, "  pull_request:\n", True),
    "push sur toute branche": (trigger_findings, "  push:\n" + BRANCHES_LINE, "  push:\n", True),
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


# --- Le script qui lit le delta : `infra/ci/changed_jobs.py` -----------------------------------

CHANGED_JOBS = REPOSITORY_ROOT / "infra" / "ci" / "changed_jobs.py"

# Delta → (`web`, `infra`) attendus. En littéraux, jamais dérivés des motifs du script : une table
# tirée de l'artefact sous test perdrait son cas avec le motif retiré (obs 80). Chaque motif du
# script a au moins un témoin qui rougit s'il disparaît : `.claude/*` et `docs/*` ont le leur hors
# Markdown, que `*.md` couvrirait seul. Les entrées témoins du corps de #124 y sont — il en annonce
# 11, sa liste en compte 10 —, plus quatre : pipeline et documentation hors Markdown, Dependabot et
# test mensuel, chemin non ASCII.
JOBS_WITNESSES: dict[str, tuple[list[str], bool, bool]] = {
    "delta vide": ([], False, False),
    "harnais seul": (
        [".claude/skills/x/SKILL.md", "apps/api/tests/test_x.py", "docs/a.md", "CLAUDE.md"],
        False,
        False,
    ),
    "pipeline hors Markdown": ([".claude/settings.json"], False, False),
    "documentation hors Markdown": (["docs/diagramme.svg"], False, False),
    "Dependabot et test mensuel": (
        [".github/dependabot.yml", ".github/workflows/restore.yml"],
        False,
        False,
    ),
    "front": (["apps/web/src/a.tsx"], True, True),
    "back": (["apps/api/content/models.py"], False, True),
    "schéma de l'API": (["apps/api/openapi.json"], True, True),
    "Makefile": (["Makefile"], True, True),
    "workflow de CI": ([".github/workflows/ci.yml"], True, True),
    "le script lui-même": (["infra/ci/changed_jobs.py"], True, True),
    "verrou Python": (["uv.lock"], False, True),
    "tests des images": (["infra/tests/test_caddy_image.py"], False, True),
    "module d'appui des tests des images": (["apps/api/tests/test_infra.py"], False, True),
    # `fnmatchcase` : les chemins de git sont sensibles à la casse. Rouge sous Windows seulement
    # si `fnmatch` revenait : sous Linux, les deux coïncident.
    "casse distincte du front": (["APPS/WEB/a.tsx"], False, True),
    "chemin non ASCII, mis entre guillemets par git": ([r'"docs/caf\303\251.md"'], True, True),
}


@pytest.mark.parametrize(
    ("paths", "web", "infra"), JOBS_WITNESSES.values(), ids=JOBS_WITNESSES.keys()
)
def test_le_delta_decide_des_jobs_web_et_infra(paths: list[str], web: bool, infra: bool) -> None:
    """Chaque témoin : la réponse de `jobs_for`, `web` puis `infra`."""
    assert jobs_for(paths) == {"web": web, "infra": infra}


@pytest.mark.parametrize(
    ("paths", "web", "infra"), JOBS_WITNESSES.values(), ids=JOBS_WITNESSES.keys()
)
def test_le_script_ecrit_sa_reponse_au_format_github_output(
    paths: list[str], web: bool, infra: bool
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
    assert completed.stdout == f"web={str(web).lower()}\ninfra={str(infra).lower()}\n"


# Les dossiers où `pytest` résout un import de module d'appui : son `pythonpath`, et les dossiers
# de tests eux-mêmes (`rootdir` et mode d'import par défaut).
SUPPORT_DIRS = ("apps/api/tests", "infra/tests")


def image_test_modules() -> set[str]:
    """Les fichiers de `apps/api/tests/` que `make image-test` charge : le greffon de `addopts`,
    `process_environment`, et tout module d'appui que `infra/tests/` importe, directement ou non.

    Lue par l'analyseur de Python (`ast`), jamais par un motif : un `import` dans une fonction
    compte comme un `import` en tête. Dénombré le 2026-10-20 (relecture de la PR #137, passe 1) :
    5 fichiers — `call_witness`, `process_environment`, `test_env`, `test_infra`,
    `test_supply_chain` —, que le motif `apps/api/tests/*` sortait tous du job `infra`.
    """
    todo = [*(REPOSITORY_ROOT / "infra" / "tests").glob("*.py")]
    todo.append(REPOSITORY_ROOT / "apps" / "api" / "tests" / "process_environment.py")
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
            todo += [
                REPOSITORY_ROOT / folder / f"{name.split('.')[0]}.py"
                for name in names
                for folder in SUPPORT_DIRS
                if (REPOSITORY_ROOT / folder / f"{name.split('.')[0]}.py").is_file()
            ]
    return {
        module.relative_to(REPOSITORY_ROOT).as_posix()
        for module in seen
        if module.is_relative_to(REPOSITORY_ROOT / "apps")
    }


def test_chaque_module_que_charge_image_test_fait_tourner_infra() -> None:
    """Un module d'appui des tests des images, changé seul, fait tourner `infra` : sans lui, une PR
    qui ne touche que lui sauterait les tests des images, et le rouge n'apparaîtrait qu'au push
    vers `main`, où il bloquerait `publish`. L'égalité garde aussi l'autre sens : un module qui
    cesse d'être chargé sort de la liste."""
    modules = image_test_modules()
    assert modules == set(IMAGE_TESTS)
    assert all(jobs_for([module])["infra"] for module in modules)


# --- La prose de la pipeline : plus de run au passage en ready ---------------------------------

# Ce qui cite un run au passage en ready : la prose que les sessions suivent. Population au
# 2026-10-18, `grep -rln ready_for_review .claude CONTRIBUTING.md CLAUDE.md` : 2 fichiers,
# `cycle-pr` et `init-projet` ; re-dénombrée le 2026-10-20 contre la base du lot, inchangée.
READY_EVENT = "ready_for_review"


def pipeline_prose() -> list[str]:
    """Les fichiers de prose de la pipeline : le Markdown de `.claude/`, `CONTRIBUTING.md` et
    `CLAUDE.md`, tels que le prochain commit peut les contenir — un worktree sous `.claude/`,
    ignoré par git, n'en fait pas partie."""
    return [
        name
        for name in repository_files()
        if (name.startswith(".claude/") and name.endswith(".md"))
        or name in {"CONTRIBUTING.md", "CLAUDE.md"}
    ]


def test_aucune_prose_ne_promet_un_run_au_passage_en_ready() -> None:
    """Le workflow n'écoute plus `ready_for_review` : une prose qui le cite ferait attendre un run
    qui ne vient jamais."""
    citing = [
        name
        for name in pipeline_prose()
        if READY_EVENT in (REPOSITORY_ROOT / name).read_text(encoding="utf-8")
    ]
    assert citing == []


def test_cycle_pr_lit_le_run_du_sha_de_tete_avant_de_sortir_du_draft() -> None:
    """À l'Étape 5, la lecture du run du SHA de tête précède `gh pr ready` : un agent qui suit le
    skill dans l'ordre la fait avant de sortir du draft, pas après (obs 30)."""
    text = CYCLE_PR.read_text(encoding="utf-8")
    step = text[text.index("## Étape 5 ") : text.index("## Étape 6 ")]
    assert "actions/runs?head_sha=" in step
    assert step.index("actions/runs?head_sha=") < step.index("gh pr ready <numéro>")
