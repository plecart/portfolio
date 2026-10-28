"""Tests de ce qui déclenche les jobs de la CI (`.github/workflows/ci.yml`, issue #124).

La CI ne dépense des minutes que là où un verdict peut changer (ADR 0017, ADR 0019) : une PR en
draft ne tourne pas, son premier run vient du passage en ready, puis de chaque push ; le run encore
en cours d'une PR s'annule au push suivant de la même PR, jamais sur `main` ; `web` et `infra`
attendent un `api` vert et, sur une PR, ne tournent que si le delta touche leurs fichiers — règle
de `infra/ci/changed_jobs.py`, lue par la première étape du job `api`.

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
import subprocess
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from changed_jobs import IMAGE_TESTS, jobs_for
from test_agent_skills import CYCLE_PR, texte_normalise
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


# Le garde du job `api` : il saute toute PR en draft, quel que soit l'événement (ADR 0019) ; un push
# vers `main`, où l'objet `pull_request` n'existe pas, tourne toujours.
API_IF = "github.event_name != 'pull_request' || github.event.pull_request.draft == false"
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
    vers `main`, toujours — `publish` y attend les trois jobs. Sans fonction d'état, GitHub y
    applique `success()` (doc « Expressions », « Status check functions », lue le 2026-10-28) : un
    `api` rouge, sauté ou annulé saute ce job, sur une PR comme sur `main` (ADR 0019, décision 3)."""
    return f"${{{{ github.event_name != 'pull_request' || needs.api.outputs.{job} == 'true' }}}}"


def gating_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte le conditionnement de `web` et `infra` des ADR 0017 et 0019.

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


# Les déclencheurs du workflow. `ready_for_review` lance le premier run d'une PR, aucune draft n'en
# ayant (ADR 0019) : `cycle-pr` sort du draft, puis attend ce run (Étape 5). `reopened` reste :
# c'est la voie de relance d'une PR dont un événement s'est perdu pendant une panne d'Actions (même
# Étape).
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


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

TYPES_LINE = "    types: [opened, synchronize, reopened, ready_for_review]\n"
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
        "${{ needs.api.outputs.web == 'true' }}",
        True,
    ),
    # L'ancien `if` (ADR 0017) : derrière un `api` rouge, un run payait `web` et `infra`.
    "if de web avec !cancelled()": (
        gating_findings,
        gated_if("web"),
        (
            "${{ !cancelled() && (github.event_name != 'pull_request'"
            " || needs.api.outputs.web == 'true') }}"
        ),
        True,
    ),
    "if d'infra avec !cancelled()": (
        gating_findings,
        gated_if("infra"),
        (
            "${{ !cancelled() && (github.event_name != 'pull_request'"
            " || needs.api.outputs.infra == 'true') }}"
        ),
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


# --- La prose de la pipeline : le premier run vient du passage en ready ------------------------


def pipeline_prose() -> list[str]:
    """Les fichiers de la pipeline : tout `.claude/` — skills, règles, rôles, scripts, réglages —,
    `CONTRIBUTING.md` et `CLAUDE.md`, tels que le prochain commit peut les contenir — un worktree
    sous `.claude/`, ignoré par git, n'en fait pas partie."""
    return [
        name
        for name in repository_files()
        if name.startswith(".claude/") or name in {"CONTRIBUTING.md", "CLAUDE.md"}
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
# `cycle-pr` et `verificateur.md` ; et le rollup tout `SKIPPED` de `cycle-pr/scripts/merge-lot.py`,
# « l'amorce vide d'une draft », exemple étroit d'une tête poussée en draft, dont le garde saute
# encore chaque job.
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
