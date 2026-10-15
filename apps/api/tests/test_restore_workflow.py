"""Tests du test de restauration mensuel : `.github/workflows/restore.yml` (brief de #24,
décisions 7 à 11).

Le workflow tourne sur GitHub Actions, contre le vrai bucket et la vraie clé, que le poste n'a pas.
Comme pour le job `deploy` (`test_deployment.py`), ces tests lisent le workflow tel que l'analyseur
YAML le lit — sa forme, gardée par une fonction sur du texte, éprouvée sur un recueil de formes
(`RESTORE_FORMS`) — et exécutent ses scripts avec des témoins à la place de `docker` et du script
de restauration : ce qu'il lancerait se lit dans leurs appels. Le script qu'il lance,
`infra/restore.sh`, est éprouvé contre la pile de test (`infra/tests/test_restore.py`).
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from call_witness import recording, witnessed
from test_infra import REPOSITORY_ROOT
from test_publication import STEP_KEYS, WORKFLOW_TOKEN_ENV

RESTORE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "restore.yml"

# Ce que porte le workflow (décision 9) : le 1ᵉʳ du mois à 04:00 UTC, une heure après la
# sauvegarde de 03:00, et à la main ; la lecture du dépôt et des paquets, rien d'autre ; un seul
# job, sauté tant que la production n'existe pas — la garde de `deploy` —, qui lit les secrets de
# l'environnement `production` (décision 10).
TRIGGERS = {"schedule": [{"cron": "0 4 1 * *"}], "workflow_dispatch": None}
PERMISSIONS = {"contents": "read", "packages": "read"}
JOB_IF = "vars.DEPLOY_ENABLED == 'true'"
ENVIRONMENT = "production"
JOB_KEYS = {"name", "runs-on", "if", "environment", "timeout-minutes", "steps"}

# La pile du runner : le Compose de production et son modèle, sans surcharge — chaque service que
# la chaîne démarre y garde sa définition de production (décision 8).
COMPOSE = (
    "docker compose --project-name restauration"
    " --env-file infra/prod.env.example -f infra/compose.yml"
)

# L'environnement de chaque étape, et lui seul. La connexion à GHCR reçoit le jeton du workflow ;
# la restauration, la clé privée (pour son entrée standard), les images publiées sous `latest`
# — la dernière publication verte ; un SHA pourrait manquer —, le bucket et le jeton en lecture
# seule projetés dans les noms que le service `backup` lit, et le seuil, vide = 0 (décisions 7,
# 9 et 10).
LOGIN_ENV = WORKFLOW_TOKEN_ENV
RESTORE_ENV = {
    "COMPOSE": COMPOSE,
    "IMAGE_TAG": "latest",
    "AGE_IDENTITY": "${{ secrets.BACKUP_AGE_IDENTITY }}",
    "BACKUP_R2_ENDPOINT": "${{ vars.BACKUP_R2_ENDPOINT }}",
    "BACKUP_R2_BUCKET": "${{ vars.BACKUP_R2_BUCKET }}",
    "BACKUP_R2_ACCESS_KEY_ID": "${{ secrets.RESTORE_R2_ACCESS_KEY_ID }}",
    "BACKUP_R2_SECRET_ACCESS_KEY": "${{ secrets.RESTORE_R2_SECRET_ACCESS_KEY }}",
    "RESTORE_MIN_PROJECTS": "${{ vars.RESTORE_MIN_PROJECTS }}",
}
STEPS = ["actions/checkout", "run", "run"]


def triggers(workflow: dict[Any, Any]) -> object:
    """Les déclencheurs d'un workflow lu par PyYAML, qui suit YAML 1.1 : la clé `on` y est le
    booléen `True` — une clé `"on"` citée reste une chaîne."""
    return workflow.get(True, workflow.get("on"))


def restore_findings(text: str) -> list[str]:
    """Ce qui, dans un workflow, écarte sa forme de ce que le brief exige du test mensuel.

    Ce que ses scripts font, les tests l'éprouvent en les exécutant (`run_workflow`) ; la garde
    tient ce qui les entoure — ce qui le déclenche, le saute ou tolère son échec, et ce qu'il reçoit.

    Returns:
        Un constat par propriété altérée — déclencheurs, `permissions` du workflow, un job autre
        que `restore` seul, son `if`, son `environment`, une clé de job hors de `JOB_KEYS`
        (`permissions`, `continue-on-error`, `env`…), des étapes autres qu'un checkout sans
        identifiant suivi de deux scripts, l'environnement de chacun autre que `LOGIN_ENV` et
        `RESTORE_ENV`, une clé d'étape hors de `STEP_KEYS`. Liste vide : le workflow est conforme.
    """
    workflow: dict[Any, Any] = yaml.safe_load(text)
    findings: list[str] = []
    if triggers(workflow) != TRIGGERS:
        findings.append(f"déclencheurs {triggers(workflow)}, attendu {TRIGGERS}")
    if workflow.get("permissions") != PERMISSIONS:
        findings.append(f"`permissions` vaut {workflow.get('permissions')}, attendu {PERMISSIONS}")
    jobs: dict[str, Any] = workflow.get("jobs") or {}
    if list(jobs) != ["restore"]:
        return [*findings, f"jobs {list(jobs)}, attendu le seul job `restore`"]
    job: dict[str, Any] = jobs["restore"]
    if job.get("if") != JOB_IF:
        findings.append(f"`if` vaut {job.get('if')!r}, attendu {JOB_IF!r}")
    if job.get("environment") != ENVIRONMENT:
        findings.append(f"`environment` vaut {job.get('environment')!r}, attendu {ENVIRONMENT!r}")
    if extra := sorted(set(job) - JOB_KEYS):
        findings.append(f"le job porte {extra}")
    steps: list[dict[str, Any]] = job.get("steps") or []
    launched = [
        "run" if "run" in step else str(step.get("uses", "")).split("@")[0] for step in steps
    ]
    if launched != STEPS:
        findings.append(f"le job lance {launched}, attendu {STEPS}")
    else:
        if steps[0].get("with") != {"persist-credentials": False}:
            findings.append("le checkout garde l'identifiant du dépôt")
        for step, expected in zip(steps[1:], [LOGIN_ENV, RESTORE_ENV], strict=True):
            if step.get("env") != expected:
                findings.append(f"l'étape {step.get('name')!r} reçoit {step.get('env')}")
    findings += [
        f"l'étape {index} porte {sorted(set(step) - STEP_KEYS)}"
        for index, step in enumerate(steps)
        if set(step) - STEP_KEYS
    ]
    return findings


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------


def env_lines(env: dict[str, str]) -> str:
    """Le bloc `env:` d'une étape, indenté comme dans `CONFORMING_WORKFLOW`."""
    return "        env:\n" + "".join(f"          {name}: {value}\n" for name, value in env.items())


LOGIN_LINES = "      - name: Connexion à GHCR\n        run: echo\n" + env_lines(LOGIN_ENV)
RESTORE_LINES = "      - name: Restauration\n        run: echo\n" + env_lines(RESTORE_ENV)
CHECKOUT_LINES = (
    "      - uses: actions/checkout@v0\n        with:\n          persist-credentials: false\n"
)
CONFORMING_WORKFLOW = f"""\
on:
  schedule:
    - cron: "0 4 1 * *"
  workflow_dispatch:
permissions:
  contents: read
  packages: read
jobs:
  restore:
    runs-on: ubuntu-latest
    if: {JOB_IF}
    environment: {ENVIRONMENT}
    timeout-minutes: 30
    steps:
{CHECKOUT_LINES}{LOGIN_LINES}{RESTORE_LINES}"""

# Forme → (texte remplacé, remplacement, constat attendu). Le texte remplacé est pris dans
# `CONFORMING_WORKFLOW` : une forme qui ne le changerait pas resterait conforme, et son verdict
# attendu la ferait rougir.
RESTORE_CHANGES = {
    "conforme": ("", "", False),
    "sans le planning": ('  schedule:\n    - cron: "0 4 1 * *"\n', "", True),
    "chaque jour": ('"0 4 1 * *"', '"0 4 * * *"', True),
    "avant la sauvegarde": ('"0 4 1 * *"', '"0 2 1 * *"', True),
    "sans lancement à la main": ("  workflow_dispatch:\n", "", True),
    "sur chaque push": ("  workflow_dispatch:\n", "  workflow_dispatch:\n  push:\n", True),
    "sans permissions": ("permissions:\n  contents: read\n  packages: read\n", "", True),
    "écriture des paquets": ("packages: read", "packages: write", True),
    "permission de plus": ("  packages: read\n", "  packages: read\n  id-token: write\n", True),
    "sans la garde de la production": (f"    if: {JOB_IF}\n", "", True),
    "garde lue dans les secrets": ("vars.DEPLOY_ENABLED", "secrets.DEPLOY_ENABLED", True),
    "sans environnement": (f"    environment: {ENVIRONMENT}\n", "", True),
    "autre environnement": (f"environment: {ENVIRONMENT}", "environment: essai", True),
    "deux jobs": ("jobs:\n", "jobs:\n  autre:\n    runs-on: ubuntu-latest\n", True),
    "job renommé": ("  restore:", "  autre:", True),
    "permissions sur le job": (
        "    timeout-minutes: 30\n",
        "    timeout-minutes: 30\n    permissions:\n      contents: write\n",
        True,
    ),
    "job toléré en échec": (
        "    timeout-minutes: 30\n",
        "    timeout-minutes: 30\n    continue-on-error: true\n",
        True,
    ),
    "environnement de job": (
        "    timeout-minutes: 30\n",
        "    timeout-minutes: 30\n    env:\n      RESTORE_MIN_PROJECTS: 0\n",
        True,
    ),
    "étape de plus": (RESTORE_LINES, "      - run: echo\n" + RESTORE_LINES, True),
    "action à la place d'un script": (LOGIN_LINES, "      - uses: docker/login-action@v0\n", True),
    "script toléré en échec": (
        RESTORE_LINES,
        RESTORE_LINES + "        continue-on-error: true\n",
        True,
    ),
    "script sauté": (RESTORE_LINES, RESTORE_LINES + "        if: false\n", True),
    "checkout qui garde l'identifiant du dépôt": (
        "        with:\n          persist-credentials: false\n",
        "",
        True,
    ),
    "jeton du workflow donné à la restauration": (
        env_lines(RESTORE_ENV),
        env_lines(RESTORE_ENV | WORKFLOW_TOKEN_ENV),
        True,
    ),
    "jeton du VPS à la place du jeton en lecture seule": (
        "secrets.RESTORE_R2_ACCESS_KEY_ID",
        "secrets.BACKUP_R2_ACCESS_KEY_ID",
        True,
    ),
    "images au SHA du commit": ("IMAGE_TAG: latest", "IMAGE_TAG: ${{ github.sha }}", True),
    "seuil en dur": (
        "RESTORE_MIN_PROJECTS: ${{ vars.RESTORE_MIN_PROJECTS }}",
        "RESTORE_MIN_PROJECTS: 0",
        True,
    ),
}
RESTORE_FORMS = {
    form: (CONFORMING_WORKFLOW.replace(old, new) if old else CONFORMING_WORKFLOW, expected)
    for form, (old, new, expected) in RESTORE_CHANGES.items()
}


@pytest.mark.parametrize(("workflow", "expected"), RESTORE_FORMS.values(), ids=RESTORE_FORMS.keys())
def test_la_garde_du_workflow_mensuel_rend_son_verdict_sur_chaque_forme(
    workflow: str, expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle s'écarte du brief."""
    assert bool(restore_findings(workflow)) is expected, restore_findings(workflow)


def test_le_workflow_mensuel_a_la_forme_du_brief() -> None:
    """Le 1ᵉʳ du mois à 04:00 UTC et à la main, en lecture seule, sauté tant que la production
    n'existe pas, sous les secrets de `production`, et rien qui saute ou tolère un échec : l'échec
    du workflow est l'alerte (critère 3 du corps)."""
    assert restore_findings(RESTORE_WORKFLOW.read_text(encoding="utf-8")) == []


# --- Les scripts, exécutés avec des témoins ---------------------------------------------------

# Les contextes du run tels que GitHub les remplirait : le jeton du workflow, l'acteur, les
# secrets et les variables de l'environnement `production`. `RESTORE_MIN_PROJECTS` n'y est pas :
# une variable absente se rend en chaîne vide (doc GitHub « Contexts », `vars`).
ACTOR = "plecart"
CONTEXTS = {
    "github": {"token": "jeton-du-workflow"},
    "secrets": {
        "BACKUP_AGE_IDENTITY": "# public key: age1x\nAGE-SECRET-KEY-1TEMOIN",
        "RESTORE_R2_ACCESS_KEY_ID": "identifiant-lecture-seule",
        "RESTORE_R2_SECRET_ACCESS_KEY": "secret-lecture-seule",
    },
    "vars": {"BACKUP_R2_ENDPOINT": "https://compte.r2.example", "BACKUP_R2_BUCKET": "sauvegardes"},
}
EXPRESSION = re.compile(r"\$\{\{ (\w+)\.(\w+) \}\}")

# Ce que le témoin du script de restauration relève de son environnement.
SEEN = [name for name in RESTORE_ENV if name != "AGE_IDENTITY"] + ["GH_TOKEN"]


def resolved(env: dict[str, str]) -> dict[str, str]:
    """L'environnement d'une étape, ses expressions `${{ contexte.nom }}` rendues par `CONTEXTS`."""
    return {
        name: EXPRESSION.sub(lambda m: CONTEXTS[m[1]].get(m[2], ""), value)
        for name, value in env.items()
    }


def workflow_steps() -> list[dict[str, Any]]:
    """Les étapes de script du job `restore`, dans l'ordre."""
    job = yaml.safe_load(RESTORE_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["restore"]
    return [step for step in job["steps"] if "run" in step]


def run_workflow(root: Path, failing: str | None = None) -> list[subprocess.CompletedProcess[str]]:
    """Exécute les scripts du job dans l'ordre, chacun par `sh -e` — GitHub les lance par
    `bash -e` ; ils restent POSIX —, jusqu'au premier qui échoue, comme le runner. Dans `root` : un
    témoin de `docker` dans le `PATH`, et le dépôt vu du runner réduit à un témoin de
    `infra/restore.sh` ; chacun consigne son appel (`call_witness`) et recopie son entrée
    standard dans `<témoin>.stdin`, et celui de la restauration son environnement (`SEEN`) dans
    `restore.env`.

    Args:
        root: un dossier vide.
        failing: le témoin qui sort en erreur — `docker` qui refuse la connexion, `restore.sh`
            dont une étape échoue —, ou aucun.

    Returns:
        Les processus terminés, un par script lancé.
    """
    log = root / "calls"
    tools, infra = root / "bin", root / "infra"
    tools.mkdir()
    infra.mkdir()
    seen = "".join(f'printf "%s=%s\\n" {name} "${{{name}-}}"\n' for name in SEEN)
    witnesses = {
        tools / "docker": "",
        infra / "restore.sh": f'{{\n{seen}}} > "{(root / "restore.env").as_posix()}"\n',
    }
    for path, extra in witnesses.items():
        stdin = f'cat > "{(root / path.name).as_posix()}.stdin"\n'
        fails = "exit 1\n" if path.name == failing else ""
        # `#!` : sans lui, le shell du poste Windows ne tient pas le témoin pour un exécutable, et
        # le `PATH` mène au vrai `docker` (mesuré).
        script = "#!/bin/sh\n" + recording(log) + stdin + extra + fails
        path.write_text(script, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    # Sans le `GH_TOKEN` du poste : le témoin de la restauration doit voir l'absence du jeton.
    base = {k: v for k, v in os.environ.items() if k != "GH_TOKEN"}
    base |= {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "GITHUB_ACTOR": ACTOR}
    finished: list[subprocess.CompletedProcess[str]] = []
    for step in workflow_steps():
        done = subprocess.run(
            ["sh", "-e", "-c", step["run"]],
            cwd=root,
            env=base | resolved(step.get("env", {})),
            capture_output=True,
            text=True,
            check=False,
        )
        finished.append(done)
        if done.returncode:
            break
    return finished


def test_le_workflow_se_connecte_a_ghcr_puis_restaure_la_derniere_sauvegarde(
    tmp_path: Path,
) -> None:
    """La connexion à GHCR par le jeton du workflow, sur l'entrée standard ; puis la chaîne de
    `make restore` par `derniere`, la clé privée sur son entrée standard — jamais en argument —,
    les images publiées sous `latest`, le jeton en lecture seule sous les noms du service
    `backup`, le seuil vide quand la variable n'existe pas, et pas le jeton du workflow."""
    finished = run_workflow(tmp_path)

    assert [done.returncode for done in finished] == [0, 0], [d.stderr for d in finished]
    assert witnessed(tmp_path / "calls") == [
        ["docker", "login", "ghcr.io", "--username", ACTOR, "--password-stdin"],
        ["restore.sh", "derniere"],
    ]
    assert (tmp_path / "docker.stdin").read_text(encoding="utf-8") == "jeton-du-workflow\n"
    identity = CONTEXTS["secrets"]["BACKUP_AGE_IDENTITY"]
    assert (tmp_path / "restore.sh.stdin").read_text(encoding="utf-8") == identity + "\n"
    assert (tmp_path / "restore.env").read_text(encoding="utf-8").splitlines() == [
        f"COMPOSE={COMPOSE}",
        "IMAGE_TAG=latest",
        "BACKUP_R2_ENDPOINT=https://compte.r2.example",
        "BACKUP_R2_BUCKET=sauvegardes",
        "BACKUP_R2_ACCESS_KEY_ID=identifiant-lecture-seule",
        "BACKUP_R2_SECRET_ACCESS_KEY=secret-lecture-seule",
        "RESTORE_MIN_PROJECTS=",
        "GH_TOKEN=",
    ]


@pytest.mark.parametrize("failing", ["docker", "restore.sh"])
def test_un_echec_fait_echouer_le_workflow(tmp_path: Path, failing: str) -> None:
    """Une connexion refusée — les images ne se tireraient pas — ou une étape de la restauration
    qui échoue : le script rend un code non nul, le job rougit, et c'est l'alerte."""
    finished = run_workflow(tmp_path, failing=failing)

    assert finished[-1].returncode != 0
    assert witnessed(tmp_path / "calls")[-1][0] == failing


# --- Ce que le workflow suppose des autres fichiers -------------------------------------------


def test_les_fichiers_que_le_workflow_nomme_existent() -> None:
    """Le Compose, son modèle et le script : un fichier renommé ne casserait le workflow qu'au
    premier du mois suivant, sans qu'aucune PR ne rougisse."""
    restore = workflow_steps()[-1]
    named = re.findall(r"infra/[\w./-]+", restore["env"]["COMPOSE"] + " " + restore["run"])

    assert sorted(named) == ["infra/compose.yml", "infra/prod.env.example", "infra/restore.sh"]
    assert all((REPOSITORY_ROOT / path).is_file() for path in named)


def test_les_valeurs_que_le_workflow_substitue_sont_des_variables_du_modele() -> None:
    """Le runner lit `prod.env.example`, et l'environnement de l'étape prime sur lui (brief,
    décision 8) : chaque valeur réelle — l'étiquette des images, le bucket, son jeton — doit y
    être une variable, sans quoi Compose garderait la valeur factice."""
    model = (REPOSITORY_ROOT / "infra" / "prod.env.example").read_text(encoding="utf-8")
    declared = set(re.findall(r"^([A-Z_][A-Z0-9_]*)=", model, re.MULTILINE))
    substituted = {"IMAGE_TAG", *(name for name in RESTORE_ENV if name.startswith("BACKUP_R2_"))}

    assert substituted - declared == set()


def test_la_base_et_son_proprietaire_du_vps_sont_ceux_du_modele() -> None:
    """Le runner ne connaît la base que par `prod.env.example` : son nom préfixe les objets du
    bucket (`backup.sh`), son propriétaire possède les objets du dump. Le VPS a les mêmes, parce
    que `bootstrap.sh` les reprend du modèle au lieu de les demander (`FROM_MODEL`)."""
    bootstrap = (REPOSITORY_ROOT / "infra" / "bootstrap.sh").read_text(encoding="utf-8")
    from_model = re.search(r"^FROM_MODEL=\(([^)]*)\)$", bootstrap, re.MULTILINE)

    assert from_model is not None
    assert {"POSTGRES_USER", "POSTGRES_DB"} <= set(from_model[1].split())
