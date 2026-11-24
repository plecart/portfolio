"""Tests du job `deploy` de la CI : le déploiement de la production par SSH (brief de #16,
décision 6).

Le déploiement tourne sur GitHub Actions, après chaque publication sur `main` et la fumée de ses
images (#26) ; le poste n'a ni la clé ni le VPS. Ces tests lisent le job tel que l'analyseur YAML
le lit, et exécutent son script avec des témoins à la place de `gh`, `scp` et `ssh` : ce qu'il
déposerait et lancerait sur le VPS se lit dans leurs appels, argument par argument. Comme pour
`publish`, la garde de la forme du job est une fonction sur du texte, appliquée au dépôt et à un
recueil de formes, `DEPLOY_FORMS`.
"""

import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from test_infra import CI_WORKFLOW, REPOSITORY_ROOT
from test_publication import SHA, STEP_KEYS, WORKFLOW_TOKEN_ENV, forms, needed

# Ce que porte le job (décision 6) : il suit la fumée des images du commit, elle-même après leur
# publication — une image rouge à la fumée reste publiée, jamais déployée (brief de #26,
# décision 2) —, et les vérifications que le push rejoue : `api` vert, `web`, `mobile` et `infra`
# verts ou sautés selon le delta ; un rouge le bloque (ADR 0032, décision 2). Une vérification
# sautée sauterait ce job sous le `success()` que GitHub applique à un `if` sans fonction d'état :
# `!cancelled()` le remplace — « If a job fails or is skipped, all jobs that need it are skipped
# unless the jobs use a conditional expression that causes the job to continue » (doc « Workflow
# syntax », `jobs.<job_id>.needs`, lue le 2026-11-24), et `needs.<job_id>.result` vaut `success`,
# `failure`, `cancelled` ou `skipped` (doc « Contexts », `needs`, même date). Il ne tourne que sur
# un push vers `main`, et seulement une fois le VPS prêt — la variable de dépôt `DEPLOY_ENABLED`,
# qu'un `if` de job lit dans `vars`, jamais dans `secrets` (doc GitHub « Contexts »). Aucun
# `permissions` : le jeton du workflow, en lecture, suffit. Ses secrets sont ceux de
# l'environnement `production`, que seule `main` peut viser (`infra/RUNBOOK.md`) : un run d'une
# autre branche ne les lit pas.
DEPLOY_NEEDS = {"fumee", "api", "web", "mobile", "infra"}
DEPLOY_IF = (
    "${{ !cancelled() && github.event_name == 'push' && github.ref == 'refs/heads/main'"
    " && vars.DEPLOY_ENABLED == 'true'"
    " && needs.fumee.result == 'success' && needs.api.result == 'success'"
    " && (needs.web.result == 'success' || needs.web.result == 'skipped')"
    " && (needs.mobile.result == 'success' || needs.mobile.result == 'skipped')"
    " && (needs.infra.result == 'success' || needs.infra.result == 'skipped') }}"
)
DEPLOY_ENVIRONMENT = "production"
DEPLOY_JOB_KEYS = {
    "name",
    "runs-on",
    "needs",
    "if",
    "environment",
    "timeout-minutes",
    "concurrency",
    "steps",
}

# L'environnement du script, et lui seul : le jeton du workflow pour lire la tête de `main`, et
# les quatre secrets du VPS — la clé dédiée, l'empreinte de l'hôte, l'utilisateur et l'hôte.
DEPLOY_ENV = WORKFLOW_TOKEN_ENV | {
    "SSH_KEY": "${{ secrets.DEPLOY_SSH_KEY }}",
    "KNOWN_HOSTS": "${{ secrets.DEPLOY_KNOWN_HOSTS }}",
    "TARGET": "${{ secrets.DEPLOY_USER }}@${{ secrets.DEPLOY_HOST }}",
}

# Le VPS tel que les témoins le voient : la cible, et le dossier de la pile, que
# `infra/bootstrap.sh` prépare.
TARGET = "deploy@vps.example"
REPOSITORY = "plecart/portfolio"
DEPLOY_DIRECTORY = "/srv/portfolio"


def deploy_job(workflow: str) -> dict[str, Any] | None:
    """Le job `deploy` d'un workflow, tel que l'analyseur YAML le lit ; `None` s'il manque."""
    return yaml.safe_load(workflow)["jobs"].get("deploy")


def deploy_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte la forme du job `deploy` de ce que le brief exige.

    Ce que son script fait, les tests l'éprouvent en l'exécutant (`run_deploy`) ; la garde tient
    ce qui l'entoure — ce qui le déclenche, le saute ou tolère son échec, et ce qu'il reçoit.

    Returns:
        Un constat si le job manque ; sinon un par propriété altérée — `needs`, `if`,
        `environment`, une clé de job hors de `DEPLOY_JOB_KEYS` (`permissions`,
        `continue-on-error`, `env`…),
        `concurrency`, des étapes autres qu'un checkout sans identifiant suivi d'un script, son
        environnement autre que `DEPLOY_ENV`, une clé d'étape hors de `STEP_KEYS`. Liste vide :
        le job est conforme.
    """
    job = deploy_job(workflow)
    if job is None:
        return ["aucun job `deploy`"]
    findings: list[str] = []
    if set(needed(job)) != DEPLOY_NEEDS:
        findings.append(f"`needs` vaut {job.get('needs')}, attendu {sorted(DEPLOY_NEEDS)}")
    if job.get("if") != DEPLOY_IF:
        findings.append(f"`if` vaut {job.get('if')!r}, attendu {DEPLOY_IF!r}")
    if job.get("environment") != DEPLOY_ENVIRONMENT:
        findings.append(
            f"`environment` vaut {job.get('environment')!r}, attendu {DEPLOY_ENVIRONMENT!r}"
        )
    if extra := sorted(set(job) - DEPLOY_JOB_KEYS):
        findings.append(f"le job porte {extra}")
    concurrency = job.get("concurrency")
    settings = cast(dict[str, object], concurrency) if isinstance(concurrency, dict) else {}
    if not (settings.get("group") and settings.get("cancel-in-progress") is False):
        findings.append(
            "`concurrency` doit nommer son groupe et porter `cancel-in-progress: false`"
        )
    return findings + checkout_then_scripts_findings(job.get("steps") or [], [DEPLOY_ENV])


def checkout_then_scripts_findings(
    steps: list[dict[str, Any]], environments: list[dict[str, str]]
) -> list[str]:
    """Ce qui écarte les étapes d'un job de la forme « un checkout qui ne garde pas l'identifiant du
    dépôt, puis un script par environnement attendu » — la forme des jobs qui lancent un script
    sur un secret (`deploy`, et le test de restauration mensuel de `test_restore_workflow.py`).

    Args:
        steps: les étapes du job, telles que l'analyseur YAML les lit.
        environments: l'environnement exact de chaque script, dans l'ordre.

    Returns:
        Un constat par écart — étapes autres qu'un checkout suivi d'autant de scripts que
        d'environnements, checkout qui garde l'identifiant, script dont l'environnement diffère,
        clé d'étape hors de `STEP_KEYS` (`if`, `continue-on-error`…). Liste vide : conforme.
    """
    findings: list[str] = []
    launched = [
        "run" if "run" in step else str(step.get("uses", "")).split("@")[0] for step in steps
    ]
    expected = ["actions/checkout"] + ["run"] * len(environments)
    if launched != expected:
        findings.append(f"le job lance {launched}, attendu {expected}")
    else:
        if steps[0].get("with") != {"persist-credentials": False}:
            findings.append("le checkout garde l'identifiant du dépôt")
        for step, environment in zip(steps[1:], environments, strict=True):
            if step.get("env") != environment:
                findings.append(f"un script reçoit {step.get('env')}, attendu {environment}")
    findings += [
        f"l'étape {index} porte {sorted(set(step) - STEP_KEYS)}"
        for index, step in enumerate(steps)
        if set(step) - STEP_KEYS
    ]
    return findings


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

ENV_LINES = "".join(f"          {name}: {value}\n" for name, value in DEPLOY_ENV.items())
SCRIPT_LINE = "      - run: echo\n        env:\n" + ENV_LINES
CHECKOUT_LINES = (
    "      - uses: actions/checkout@v0\n        with:\n          persist-credentials: false\n"
)
CONCURRENCY_LINES = "    concurrency:\n      group: deploy\n      cancel-in-progress: false\n"
NEEDS_LINE = "    needs: [fumee, api, web, mobile, infra]\n"
CONFORMING_WORKFLOW = f"""\
jobs:
  deploy:
    runs-on: ubuntu-latest
{NEEDS_LINE}\
    if: {DEPLOY_IF}
    environment: {DEPLOY_ENVIRONMENT}
    timeout-minutes: 15
{CONCURRENCY_LINES}\
    steps:
{CHECKOUT_LINES}{SCRIPT_LINE}"""


def success_or_skipped(job: str) -> str:
    """La clause de `DEPLOY_IF` qui accepte le job `job` vert ou sauté."""
    return f"(needs.{job}.result == 'success' || needs.{job}.result == 'skipped')"


def verification_forms(job: str) -> dict[str, tuple[str, str, bool]]:
    """Les formes qui écartent la vérification `job`, que le delta peut sauter, de `DEPLOY_IF` ou
    de `DEPLOY_NEEDS` : rouge, elle laisserait partir le déploiement ; exigée verte, un merge qui
    ne la lance pas ne se déploierait plus."""
    clause = success_or_skipped(job)
    return {
        f"sans attendre {job}": (f", {job}", "", True),
        f"sans condition sur {job}": (f" && {clause}", "", True),
        f"{job} exigé vert": (clause, f"needs.{job}.result == 'success'", True),
        f"{job} toléré rouge": (clause, f"needs.{job}.result != 'cancelled'", True),
    }


# Forme → (texte remplacé, remplacement, constat attendu). Le texte remplacé est pris dans
# `CONFORMING_WORKFLOW` : une forme qui ne le changerait pas resterait conforme, et son verdict
# attendu la ferait rougir.
DEPLOY_CHANGES = {
    "conforme": ("", "", False),
    "needs dans un autre ordre": ("[fumee, api, ", "[api, fumee, ", False),
    "sans le job": ("  deploy:", "  autre:", True),
    "sans aucun needs": (NEEDS_LINE, "", True),
    "après la publication, sans la fumée": ("[fumee, ", "[publish, ", True),
    "sans attendre la fumée": ("[fumee, ", "[", True),
    # Le `needs` d'avant l'ADR 0032 : un merge qui casse le commit livré se déploierait.
    "sans attendre les vérifications": (NEEDS_LINE, "    needs: fumee\n", True),
    "sans attendre api": (", api", "", True),
    # Sous le `success()` implicite, une vérification sautée sauterait le déploiement : un merge
    # sans front ni image ne se déploierait plus.
    "sans !cancelled()": ("!cancelled() && ", "", True),
    # `always()` déploierait aussi un run annulé (doc « Expressions », `always`).
    "always() au lieu de !cancelled()": ("!cancelled()", "always()", True),
    "api accepté sauté": ("needs.api.result == 'success'", success_or_skipped("api"), True),
    "fumée acceptée sautée": ("needs.fumee.result == 'success'", success_or_skipped("fumee"), True),
    **{
        name: form
        for job in ("web", "mobile", "infra")
        for name, form in verification_forms(job).items()
    },
    "sans la variable du VPS prêt": (" && vars.DEPLOY_ENABLED == 'true'", "", True),
    "variable lue dans les secrets": ("vars.DEPLOY_ENABLED", "secrets.DEPLOY_ENABLED", True),
    "sur un push vers toute branche": (" && github.ref == 'refs/heads/main'", "", True),
    "sans environnement": (f"    environment: {DEPLOY_ENVIRONMENT}\n", "", True),
    "autre environnement": (f"environment: {DEPLOY_ENVIRONMENT}", "environment: essai", True),
    "permissions sur le job": (
        "    timeout-minutes: 15\n",
        "    timeout-minutes: 15\n    permissions:\n      packages: read\n",
        True,
    ),
    "job toléré en échec": (
        "    timeout-minutes: 15\n",
        "    timeout-minutes: 15\n    continue-on-error: true\n",
        True,
    ),
    "environnement de job": (
        "    timeout-minutes: 15\n",
        "    timeout-minutes: 15\n    env:\n      MAKEFLAGS: -i\n",
        True,
    ),
    "concurrence qui annule": ("cancel-in-progress: false", "cancel-in-progress: true", True),
    "sans concurrence": (CONCURRENCY_LINES, "", True),
    "étape de plus": (SCRIPT_LINE, "      - run: ssh-keyscan vps.example\n" + SCRIPT_LINE, True),
    "action à la place du script": (SCRIPT_LINE, "      - uses: appleboy/ssh-action@v0\n", True),
    "script toléré en échec": (
        SCRIPT_LINE,
        SCRIPT_LINE + "        continue-on-error: true\n",
        True,
    ),
    "script sauté": (SCRIPT_LINE, SCRIPT_LINE + "        if: false\n", True),
    "checkout qui garde l'identifiant du dépôt": (
        "        with:\n          persist-credentials: false\n",
        "",
        True,
    ),
    "secret de plus": (ENV_LINES, ENV_LINES + "          AUTRE: ${{ secrets.AUTRE }}\n", True),
}
DEPLOY_FORMS = forms(CONFORMING_WORKFLOW, DEPLOY_CHANGES)


@pytest.mark.parametrize(("workflow", "expected"), DEPLOY_FORMS.values(), ids=DEPLOY_FORMS.keys())
def test_la_garde_du_job_deploy_rend_son_verdict_sur_chaque_forme(
    workflow: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle s'écarte du brief."""
    assert bool(deploy_findings(workflow)) is expected, deploy_findings(workflow)


def test_le_job_deploy_suit_la_fumee_et_les_verifications_d_un_push_sur_main() -> None:
    """Après la fumée et les vérifications rejouées — `api` vert, `web`, `mobile` et `infra` verts
    ou sautés —, push vers `main`, une fois le VPS prêt — `DEPLOY_ENABLED` lue dans `vars` —, aucun
    `permissions`, un déploiement à la fois, et rien qui saute ou tolère l'échec de son script."""
    assert deploy_findings(CI_WORKFLOW.read_text(encoding="utf-8")) == []


# --- Le script, exécuté avec des témoins -----------------------------------------------------


def deploy_script() -> str:
    """Le script du job `deploy`, tel que la CI le lance."""
    job = deploy_job(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert job is not None, "aucun job `deploy`"
    scripts = [step["run"] for step in job["steps"] if "run" in step]
    assert len(scripts) == 1, f"{len(scripts)} scripts dans le job `deploy`"
    return scripts[0]


def run_deploy(
    root: Path, main: str = SHA, failing: str | None = None
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Exécute le script du job avec `-e`, comme GitHub Actions — qui le lance par `bash -e` ; le
    script reste POSIX, donc `sh -e` ici —, avec des témoins de `gh`, `scp` et `ssh` qui
    consignent leurs arguments.

    Args:
        root: un dossier vide — témoins, appels consignés et `RUNNER_TEMP` y vivent.
        main: le SHA que le témoin de `gh` rend pour la tête de `main`.
        failing: le témoin qui sort en erreur — `scp` qui ne dépose pas le Compose, `ssh` dont la
            commande échoue sur le VPS —, ou aucun.

    Returns:
        Le processus terminé, et les appels des témoins dans l'ordre, outil en tête.
    """
    tools, calls = root / "bin", root / "calls"
    tools.mkdir()
    log = calls.as_posix()
    record = f'printf "%s\\t" "$(basename "$0")" "$@" >> "{log}"\necho >> "{log}"\n'
    replies = {"gh": f"echo {main}\n", "scp": "", "ssh": ""}
    if failing:
        replies[failing] += "exit 1\n"
    for tool, reply in replies.items():
        (tools / tool).write_text(f"#!/bin/sh\n{record}{reply}", encoding="utf-8", newline="\n")
        (tools / tool).chmod(0o755)
    environment = os.environ | {
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_SHA": SHA,
        "GITHUB_REPOSITORY": REPOSITORY,
        "RUNNER_TEMP": root.as_posix(),
        "GH_TOKEN": "jeton-du-workflow",
        "SSH_KEY": "clé privée",
        "KNOWN_HOSTS": "vps.example ssh-ed25519 AAAA",
        "TARGET": TARGET,
    }
    finished = subprocess.run(
        ["sh", "-e", "-c", deploy_script()],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return finished, [line.rstrip("\t").split("\t") for line in lines]


def test_le_deploiement_depose_le_compose_puis_relance_la_pile_a_l_etiquette_du_commit(
    tmp_path: Path,
) -> None:
    """Le Compose du commit sur le VPS, l'étiquette du commit — SHA complet, jamais `latest` —
    dans son `.env`, puis `pull` et `up --wait`, qui échoue si un service ne devient pas sain
    (mesure : en-tête de `infra/compose.yml`). La connexion n'accepte que l'hôte dont l'empreinte
    est épinglée par secret : jamais une première connexion de confiance."""
    finished, calls = run_deploy(tmp_path)
    options = [
        "-i",
        f"{tmp_path.as_posix()}/deploy_key",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        f"UserKnownHostsFile={tmp_path.as_posix()}/known_hosts",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=30",
    ]
    remote = (
        f"cd {DEPLOY_DIRECTORY}"
        f" && sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG={SHA}/' .env"
        " && docker compose pull --quiet"
        " && docker compose up -d --wait --wait-timeout 300"
    )

    assert finished.returncode == 0, finished.stderr
    assert calls == [
        ["gh", "api", f"repos/{REPOSITORY}/commits/main", "--jq", ".sha"],
        ["scp", *options, "infra/compose.yml", f"{TARGET}:{DEPLOY_DIRECTORY}/compose.yml"],
        ["ssh", *options, TARGET, remote],
    ]
    assert (tmp_path / "deploy_key").read_text(encoding="utf-8") == "clé privée\n"
    assert (tmp_path / "known_hosts").read_text(
        encoding="utf-8"
    ) == "vps.example ssh-ed25519 AAAA\n"


def test_un_commit_que_main_a_depasse_ne_se_deploie_pas(tmp_path: Path) -> None:
    """La publication range les runs par ordre d'arrivée (`ci.yml`, job `publish`) : un run plus
    lent que le suivant arriverait après lui et redéploierait l'ancien code sur un schéma déjà
    migré. Seule la tête de `main` se déploie — le run du commit qui l'a dépassée s'en charge."""
    finished, calls = run_deploy(tmp_path, main="f" * 40)

    assert finished.returncode == 0, finished.stderr
    assert [call[0] for call in calls] == ["gh"]


@pytest.mark.parametrize("failing", ["scp", "ssh"])
def test_un_echec_vers_le_vps_fait_echouer_le_job(tmp_path: Path, failing: str) -> None:
    """Un Compose qui n'a pas été déposé — les nouvelles images tourneraient sous l'ancien —, ou
    un service qui ne devient pas sain, dont `up --wait` sort en erreur et dont `ssh` rend le code :
    le job rougit au lieu de laisser `main` verte sur une pile en panne."""
    finished, calls = run_deploy(tmp_path, failing=failing)

    assert finished.returncode != 0
    assert calls[-1][0] == failing


def test_l_amorcage_prepare_le_dossier_ou_le_job_depose_la_pile() -> None:
    """Le job dépose le Compose et réécrit `IMAGE_TAG` dans le dossier que `infra/bootstrap.sh`
    a créé et où il a écrit le `.env` : deux noms qui divergeraient ne casseraient qu'au premier
    déploiement réel."""
    bootstrap = (REPOSITORY_ROOT / "infra" / "bootstrap.sh").read_text(encoding="utf-8")

    assert f"\nSTACK_DIR={DEPLOY_DIRECTORY}\n" in bootstrap


def test_le_script_de_deploiement_ne_cite_jamais_latest() -> None:
    """`latest` peut désigner l'avant-dernier commit quand deux publications se croisent (job
    `publish`) : le déploiement vise toujours l'étiquette du commit. Le runner du job,
    `ubuntu-latest`, n'est pas une image déployée."""
    assert "latest" not in deploy_script()
