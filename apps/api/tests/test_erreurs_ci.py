"""Tests de la première ligne d'erreur de chaque step en échec
(`.claude/skills/cycle-pr/scripts/erreurs-ci.py`).

Le script lit deux sorties de `gh` — les jobs du run en JSON, puis le journal de ses steps en
échec — par une seule fonction, `run`, que ces tests remplacent par un `gh` témoin : il ne répond
qu'aux deux commandes complètes attendues et lève sur toute autre. Les journaux sont des lignes
réelles de `gh run view <id> --log-failed` (gh 2.94.0, relevées le 2026-10-21 par la session PR du
lot 4b de #134) : celui de 39521079941 entier, des extraits nommés par leurs lignes pour les
autres ; les jobs sont réduits aux champs que le script lit, noms et conclusions réels. Les cas
s'écrivent en littéraux, jamais dérivés des constantes du script (`cycle-pr` 3.1).
"""

import json
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

import pytest
from skill_scripts import REPOSITORY_ROOT, load_script

erreurs_ci = load_script("cycle-pr", "erreurs-ci")

RUN = "4242"
FRONT = "Front — lint, types, tests, build, e2e, lighthouse, audit"
BACK = "Back — audit, lint, format, types, tests"
INFRA = "Infra — configuration Compose, images, tests des images, scan"
PUBLICATION = "Publication — images sur GHCR"
DEPLOIEMENT = "Déploiement — production par SSH"

Reponse = subprocess.CompletedProcess[bytes] | OSError


def sortie(octets: bytes) -> subprocess.CompletedProcess[bytes]:
    """Une commande `gh` qui réussit et écrit `octets` sur sa sortie standard."""
    return subprocess.CompletedProcess([], 0, stdout=octets, stderr=b"")


def document(contenu: Any) -> subprocess.CompletedProcess[bytes]:
    """La sortie de `gh run view --json` : le JSON brut, en UTF-8 — accents compris."""
    return sortie(json.dumps(contenu, ensure_ascii=False).encode())


def panne(stderr: bytes) -> subprocess.CompletedProcess[bytes]:
    """Une commande `gh` qui sort en 1 sans rien écrire sur sa sortie standard."""
    return subprocess.CompletedProcess([], 1, stdout=b"", stderr=stderr)


def job(nom: str, conclusion: str, *steps: tuple[str, str]) -> dict[str, Any]:
    """Un job de `gh run view --json jobs`, réduit aux champs lus ; un step est (nom, conclusion)."""
    return {
        "name": nom,
        "conclusion": conclusion,
        "steps": [{"name": step, "conclusion": fin} for step, fin in steps],
    }


def termine(*jobs: dict[str, Any], conclusion: str = "failure") -> dict[str, Any]:
    """Un run terminé, tel que `gh run view --json status,conclusion,jobs` le rend."""
    return {"status": "completed", "conclusion": conclusion, "jobs": list(jobs)}


def journal(job: str, step: str, *textes: str) -> str:
    """Une section de `gh run view --log-failed` : une ligne `<job>\\t<step>\\t<texte>` par texte."""
    return "".join(f"{job}\t{step}\t{texte}\n" for texte in textes)


class Gh:
    """Un `gh` témoin : il rend `jobs` à `gh run view <run> --json status,conclusion,jobs` et
    `log` à `gh run view <run> --log-failed` — une `OSError` y est levée, comme un `gh`
    introuvable —, et lève sur toute autre commande. `log` à `None` lève aussi : le journal ne doit
    pas être lu."""

    def __init__(self, jobs: Reponse, log: Reponse | None = None, run: str = RUN) -> None:
        self.reponses: dict[tuple[str, ...], Reponse | None] = {
            ("gh", "run", "view", run, "--json", "status,conclusion,jobs"): jobs,
            ("gh", "run", "view", run, "--log-failed"): log,
        }
        self.appels: list[tuple[str, ...]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        cmd = tuple(cmd)
        self.appels.append(cmd)
        reponse = self.reponses.get(cmd)
        if reponse is None:
            raise AssertionError(f"commande inattendue : {cmd}")
        if isinstance(reponse, OSError):
            raise reponse
        return reponse


def lance(gh: Gh, *args: str) -> int:
    """Le script tel que la session l'appelle."""
    return erreurs_ci.main(list(args), run=gh)


def lignes(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Ce que le script a écrit sur sa sortie standard, ligne par ligne."""
    return capsys.readouterr().out.splitlines()


# 39521079941, Front › Audit (npm audit) : le journal entier, ses 43 lignes — le BOM de la
# première, la notation `^[` de l'échappement ANSI que `gh` écrit dans un tube.
JOURNAL_39521079941 = journal(
    FRONT,
    "Audit",
    "\ufeff2026-10-21T00:27:13.6512999Z ##[group]Run make web-audit",
    "2026-10-21T00:27:13.6513298Z ^[[36;1mmake web-audit^[[0m",
    "2026-10-21T00:27:13.6568456Z shell: /usr/bin/bash -e {0}",
    "2026-10-21T00:27:13.6568701Z ##[endgroup]",
    "2026-10-21T00:27:13.6651577Z cd apps/web && npm audit --audit-level=high",
    "2026-10-21T00:27:14.2511635Z # npm audit report",
    "2026-10-21T00:27:14.2512327Z ",
    "2026-10-21T00:27:14.2517541Z sprintf-js  *",
    "2026-10-21T00:27:14.2518054Z Severity: moderate",
    "2026-10-21T00:27:14.2519126Z sprintf-js vulnerable to denial of service through unbounded"
    " precision specifiers - https://github.com/advisories/GHSA-hp3w-g68c-fv3c",
    "2026-10-21T00:27:14.2520244Z fix available via `npm audit fix --force`",
    "2026-10-21T00:27:14.2520954Z Will install @lhci/cli@0.3.5, which is a breaking change",
    "2026-10-21T00:27:14.2521517Z node_modules/sprintf-js",
    "2026-10-21T00:27:14.2522029Z   argparse  1.0.0 - 1.0.10",
    "2026-10-21T00:27:14.2522569Z   Depends on vulnerable versions of sprintf-js",
    "2026-10-21T00:27:14.2523122Z   node_modules/argparse",
    "2026-10-21T00:27:14.2523574Z     js-yaml  3.2.7 - 3.15.2",
    "2026-10-21T00:27:14.2524244Z     Depends on vulnerable versions of argparse",
    "2026-10-21T00:27:14.2524789Z     node_modules/js-yaml",
    "2026-10-21T00:27:14.2525245Z       @lhci/utils  >=0.3.6",
    "2026-10-21T00:27:14.2525812Z       Depends on vulnerable versions of js-yaml",
    "2026-10-21T00:27:14.2526449Z       node_modules/@lhci/utils",
    "2026-10-21T00:27:14.2527126Z         @lhci/cli  >=0.3.6",
    "2026-10-21T00:27:14.2527663Z         Depends on vulnerable versions of @lhci/utils",
    "2026-10-21T00:27:14.2528226Z         node_modules/@lhci/cli",
    "2026-10-21T00:27:14.2528418Z ",
    "2026-10-21T00:27:14.2528557Z vite  8.3.0 - 8.3.2",
    "2026-10-21T00:27:14.2528841Z Severity: high",
    "2026-10-21T00:27:14.2529614Z launch-editor: escapeCmdArgs() omits % escaping on Windows -"
    " https://github.com/advisories/GHSA-698v-4r3x-3vcv",
    "2026-10-21T00:27:14.2532495Z launch-editor: Editor CLI flag misinterpretation causing"
    " arbitrary command execution for some editors -"
    " https://github.com/advisories/GHSA-r825-w8mm-5pxw",
    "2026-10-21T00:27:14.2533928Z launch-editor: `fs.existsSync()` existence check can be bypassed"
    " on Windows - https://github.com/advisories/GHSA-587h-7wmj-h5pm",
    "2026-10-21T00:27:14.2534727Z fix available via `npm audit fix`",
    "2026-10-21T00:27:14.2535078Z node_modules/vite",
    "2026-10-21T00:27:14.2535471Z ",
    "2026-10-21T00:27:14.2535681Z 6 vulnerabilities (5 moderate, 1 high)",
    "2026-10-21T00:27:14.2535937Z ",
    "2026-10-21T00:27:14.2536202Z To address issues that do not require attention, run:",
    "2026-10-21T00:27:14.2536609Z   npm audit fix",
    "2026-10-21T00:27:14.2536788Z ",
    "2026-10-21T00:27:14.2537225Z To address all issues (including breaking changes), run:",
    "2026-10-21T00:27:14.2537655Z   npm audit fix --force",
    "2026-10-21T00:27:14.2617285Z make: *** [Makefile:315: web-audit] Error 1",
    "2026-10-21T00:27:14.2630990Z ##[error]Process completed with exit code 2.",
)

# 39562241493 : Infra › Scan (trivy), lignes 1-8, 139-141, 534-536 et 575-576 — le `Total: 0`
# d'une cible propre précède le total qui rougit ; Back › Audit (pip-audit), lignes 577-588 et
# 603-604.
JOURNAL_39562241493 = journal(
    INFRA,
    "Scan",
    "\ufeff2026-10-21T07:34:24.6037432Z ##[group]Run make scan",
    "2026-10-21T07:34:24.6037690Z ^[[36;1mmake scan^[[0m",
    "2026-10-21T07:34:24.6080602Z shell: /usr/bin/bash -e {0}",
    "2026-10-21T07:34:24.6080763Z env:",
    "2026-10-21T07:34:24.6080935Z   UV_PYTHON_INSTALL_DIR: /home/runner/work/_temp/uv-python-dir",
    "2026-10-21T07:34:24.6081167Z   UV_CACHE_DIR: /home/runner/work/_temp/setup-uv-cache",
    "2026-10-21T07:34:24.6081365Z ##[endgroup]",
    "2026-10-21T07:34:24.6159735Z docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v"
    " portfolio-trivy-cache:/root/.cache/ -v"
    ' "/home/runner/work/portfolio/portfolio/.trivyignore.yaml:/.trivyignore.yaml:ro"'
    " ghcr.io/aquasecurity/trivy:0.74.0@sha256:"
    "62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969 image --image-src docker"
    " --severity HIGH,CRITICAL --exit-code 1 --exit-on-eol 1 --ignorefile .trivyignore.yaml"
    " --show-suppressed portfolio-api",
    "2026-10-21T07:34:56.9018440Z portfolio-api (debian 13.7)",
    "2026-10-21T07:34:56.9018688Z ===========================",
    "2026-10-21T07:34:56.9019085Z Total: 0 (HIGH: 0, CRITICAL: 0)",
    "2026-10-21T07:34:56.9416102Z Python (python-pkg)",
    "2026-10-21T07:34:56.9416447Z ===================",
    "2026-10-21T07:34:56.9416694Z Total: 7 (HIGH: 6, CRITICAL: 1)",
    "2026-10-21T07:35:02.8504399Z make: *** [Makefile:181: scan-api] Error 1",
    "2026-10-21T07:35:02.8535463Z ##[error]Process completed with exit code 2.",
) + journal(
    BACK,
    "Audit",
    "\ufeff2026-10-21T07:28:51.1376490Z ##[group]Run make audit",
    "2026-10-21T07:28:51.1376791Z ^[[36;1mmake audit^[[0m",
    "2026-10-21T07:28:51.1412533Z shell: /usr/bin/bash -e {0}",
    "2026-10-21T07:28:51.1412822Z env:",
    "2026-10-21T07:28:51.1413359Z   UV_PYTHON_INSTALL_DIR: /home/runner/work/_temp/uv-python-dir",
    "2026-10-21T07:28:51.1413755Z   UV_CACHE_DIR: /home/runner/work/_temp/setup-uv-cache",
    "2026-10-21T07:28:51.1414058Z ##[endgroup]",
    "2026-10-21T07:28:51.1483260Z uv run python infra/ci/pip_audit_gate.py \\",
    "2026-10-21T07:28:51.1484183Z \t--exceptions infra/ci/pip-audit-exceptions.toml --skip-editable",
    "2026-10-21T07:28:51.2025604Z pip-audit --skip-editable",
    "2026-10-21T07:28:53.4878837Z Found 9 known vulnerabilities in 2 packages",
    "2026-10-21T07:28:53.4893826Z Name    Version   ID              Fix Versions",
    "2026-10-21T07:28:53.5462036Z make: *** [Makefile:149: audit] Error 1",
    "2026-10-21T07:28:53.5477882Z ##[error]Process completed with exit code 2.",
)

# 38936444116, Back › Tests (pytest), lignes 1-9, 82-88, 110-113, 165 et 191-193 : le code source
# que pytest affiche avant l'assertion — `failure = …` à la ligne 86, `error = …` à la 87 — nomme
# une erreur bien avant le détail de l'assertion, ligne 111.
JOURNAL_38936444116 = journal(
    BACK,
    "Tests",
    "\ufeff2026-10-16T17:01:41.6337889Z ##[group]Run make test",
    "2026-10-16T17:01:41.6338184Z ^[[36;1mmake test^[[0m",
    "2026-10-16T17:01:41.6399562Z shell: /usr/bin/bash -e {0}",
    "2026-10-16T17:01:41.6399842Z env:",
    "2026-10-16T17:01:41.6400150Z   UV_PYTHON_INSTALL_DIR: /home/runner/work/_temp/uv-python-dir",
    "2026-10-16T17:01:41.6400588Z   UV_CACHE_DIR: /home/runner/work/_temp/setup-uv-cache",
    "2026-10-16T17:01:41.6400926Z ##[endgroup]",
    "2026-10-16T17:01:41.6496229Z uv run pytest",
    "2026-10-16T17:01:45.8720602Z ============================= test session starts"
    " ==============================",
    "2026-10-16T17:04:13.5143923Z =================================== FAILURES"
    " ===================================",
    "2026-10-16T17:04:13.5145462Z _ test_une_conversion_qui_echoue_ne_laisse_aucune_variante"
    "[\\xe9chec apr\\xe8s l'\\xe9criture sous un nom d\\xe9j\\xe0 pris] _",
    "2026-10-16T17:04:13.5147248Z ",
    "2026-10-16T17:04:13.5147959Z tmp_path ="
    " PosixPath('/tmp/pytest-of-runner/pytest-0/test_une_conversion_qui_echoue3')",
    "2026-10-16T17:04:13.5149566Z failure = \"après l'écriture\", failing = 3, taken = '320.webp'",
    "2026-10-16T17:04:13.5150665Z error = <class 'OSError'>",
    "2026-10-16T17:04:13.5151141Z ",
    '2026-10-16T17:04:13.5176809Z >       assert storage.listdir("images/abc") =='
    ' ([], sorted([*kept, "original.png"]))',
    "2026-10-16T17:04:13.5178123Z E       AssertionError: assert ([], ['origin..., '320.webp'])"
    " == ([], ['320.we...riginal.png'])",
    "2026-10-16T17:04:13.5179147Z E         ",
    "2026-10-16T17:04:13.5180072Z E         At index 1 diff: ['original.png', '320.webp'] !="
    " ['320.webp', 'original.png']",
    "2026-10-16T17:04:13.5224480Z FAILED apps/api/tests/test_variants.py::"
    "test_une_conversion_qui_echoue_ne_laisse_aucune_variante"
    "[\\xe9chec apr\\xe8s l'\\xe9criture sous un nom d\\xe9j\\xe0 pris] - AssertionError: assert"
    " ([], ['origin..., '320.webp']) == ([], ['320.we...riginal.png'])",
    "2026-10-16T17:04:13.5238152Z ======= 2 failed, 1320 passed, 1 skipped, 9 xfailed in 149.47s"
    " (0:02:29) =======",
    "2026-10-16T17:04:13.9974637Z make: *** [Makefile:118: test] Error 1",
    "2026-10-16T17:04:13.9990331Z ##[error]Process completed with exit code 2.",
)

# (run, jobs réduits, sortie de `gh run view <run> --log-failed`, lignes attendues)
RUNS_ROUGES_REELS = {
    "39521079941-npm-audit": (
        "39521079941",
        termine(
            job(BACK, "success", ("Audit", "success")),
            job(INFRA, "success", ("Scan", "success")),
            job(
                FRONT, "failure", ("Install", "success"), ("Audit", "failure"), ("Lint", "skipped")
            ),
            job(PUBLICATION, "skipped"),
            job(DEPLOIEMENT, "skipped"),
        ),
        sortie(JOURNAL_39521079941.encode()),
        [f"{FRONT} › Audit : 6 vulnerabilities (5 moderate, 1 high)"],
    ),
    "39562241493-trivy-et-pip-audit": (
        "39562241493",
        termine(
            job(INFRA, "failure", ("Tests des images", "success"), ("Scan", "failure")),
            job(BACK, "failure", ("Install", "success"), ("Audit", "failure"), ("Lint", "skipped")),
            job(FRONT, "success", ("Audit", "success")),
            job(PUBLICATION, "skipped"),
            job(DEPLOIEMENT, "skipped"),
        ),
        sortie(JOURNAL_39562241493.encode()),
        [
            f"{INFRA} › Scan : Total: 7 (HIGH: 6, CRITICAL: 1)",
            f"{BACK} › Audit : Found 9 known vulnerabilities in 2 packages",
        ],
    ),
    "38936444116-pytest": (
        "38936444116",
        termine(
            job(FRONT, "success", ("Tests", "success")),
            job(BACK, "failure", ("Typecheck", "success"), ("Tests", "failure")),
            job(INFRA, "success"),
            job(PUBLICATION, "skipped"),
            job(DEPLOIEMENT, "skipped"),
        ),
        sortie(JOURNAL_38936444116.encode()),
        [
            (
                f"{BACK} › Tests : E       AssertionError: assert ([], ['origin..., '320.webp'])"
                " == ([], ['320.we...riginal.png'])"
            )
        ],
    ),
    # Trois jobs en échec sans aucun step : `gh` ne trouve pas leur journal et sort en 1.
    "38944674078-aucun-step": (
        "38944674078",
        termine(
            job(INFRA, "failure"),
            job(BACK, "failure"),
            job(FRONT, "failure"),
            job(PUBLICATION, "skipped"),
            job(DEPLOIEMENT, "skipped"),
        ),
        panne(b"log not found: 117120678982\n"),
        [
            f"{INFRA} : aucun step en échec — conclusion failure",
            f"{BACK} : aucun step en échec — conclusion failure",
            f"{FRONT} : aucun step en échec — conclusion failure",
        ],
    ),
}


@pytest.mark.parametrize(
    ("run", "jobs", "log", "attendu"),
    RUNS_ROUGES_REELS.values(),
    ids=RUNS_ROUGES_REELS.keys(),
)
def test_un_run_rouge_reel_rend_une_ligne_par_step_en_echec(
    run: str,
    jobs: dict[str, Any],
    log: subprocess.CompletedProcess[bytes],
    attendu: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Chaque step en échec rend sa première ligne d'erreur, dans l'ordre des jobs puis des steps
    du JSON. Sur 38936444116, le marqueur de pytest passe avant le mot d'erreur : sans lui, la
    ligne 86 du code source affiché, `failure = …`, serait rendue (vu rouge par mutation)."""
    assert lance(Gh(document(jobs), log, run), run) == 0
    assert lignes(capsys) == attendu


def test_deux_steps_en_echec_d_un_meme_job_rendent_deux_lignes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    jobs = termine(job(BACK, "failure", ("Lint", "failure"), ("Tests", "failure")))
    log = journal(BACK, "Lint", "fatal: ruff introuvable") + journal(
        BACK, "Tests", "FAILED test_forms.py::test_fails - assert 1 == 2"
    )

    assert lance(Gh(document(jobs), sortie(log.encode())), RUN) == 0
    assert lignes(capsys) == [
        f"{BACK} › Lint : fatal: ruff introuvable",
        f"{BACK} › Tests : FAILED test_forms.py::test_fails - assert 1 == 2",
    ]


def test_une_section_du_journal_qu_aucun_step_en_echec_ne_nomme_rend_sa_ligne(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`gh run view --help` (gh 2.94.0) : une ligne de journal que `gh` ne rattache à aucun step
    porte le nom de step `UNKNOWN STEP`. Elle ne se perd pas en silence : sa section rend sa
    ligne après celles des steps du JSON."""
    jobs = termine(job(BACK, "failure", ("Tests", "failure")))
    log = journal(BACK, "Tests", "Error: boom") + journal(
        BACK, "UNKNOWN STEP", "##[error]The operation was canceled."
    )

    assert lance(Gh(document(jobs), sortie(log.encode())), RUN) == 0
    assert lignes(capsys) == [
        f"{BACK} › Tests : Error: boom",
        f"{BACK} › UNKNOWN STEP : ##[error]The operation was canceled.",
    ]


def test_seules_les_conclusions_d_echec_rendent_une_ligne(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """L'API REST (« Workflow jobs », schéma `job`) énumère `success`, `failure`, `neutral`,
    `cancelled`, `skipped`, `timed_out` et `action_required` ; les quatre qui ne sont pas un échec
    ne rendent rien, ni pour un job ni pour un step, et une conclusion hors de l'énumération —
    `startup_failure`, celle d'une CI qui ne démarre pas (`cycle-pr` Étape 6) — compte en échec."""
    jobs = termine(
        job("Lint", "success"),
        job("Publication", "skipped"),
        job("Build", "cancelled"),
        job("Docs", "neutral"),
        job("Tests", "failure"),
        job("E2E", "timed_out"),
        job("Déploiement", "action_required"),
        job("Infra", "startup_failure"),
        job(
            BACK,
            "failure",
            ("Install", "success"),
            ("Lint", "skipped"),
            ("Format check", "cancelled"),
            ("Typecheck", "neutral"),
            ("Audit", "failure"),
        ),
    )
    log = journal(BACK, "Audit", "Found 1 known vulnerability in 1 package")

    assert lance(Gh(document(jobs), sortie(log.encode())), RUN) == 0
    assert lignes(capsys) == [
        "Tests : aucun step en échec — conclusion failure",
        "E2E : aucun step en échec — conclusion timed_out",
        "Déploiement : aucun step en échec — conclusion action_required",
        "Infra : aucun step en échec — conclusion startup_failure",
        f"{BACK} › Audit : Found 1 known vulnerability in 1 package",
    ]


# (sortie de `gh run view 4242 --log-failed`, ce que rend le step en échec qui n'y a pas de section)
JOURNAUX_INDISPONIBLES = {
    "gh-en-echec": (
        panne(b"log not found: 117120678982\n"),
        (
            "journal indisponible — `gh run view 4242 --log-failed` a échoué (1) :"
            " log not found: 117120678982"
        ),
    ),
    "section-absente": (sortie(b""), "journal indisponible — aucune section du journal à son nom"),
    "ligne-sans-ses-trois-champs": (
        sortie(f"{BACK}\tTests\tError: boom\n{BACK} Tests sans tabulation\n".encode()),
        "journal indisponible — la ligne 2 du journal n'a pas la forme `<job>\\t<step>\\t<texte>`",
    ),
}


@pytest.mark.parametrize(
    ("log", "rendu"), JOURNAUX_INDISPONIBLES.values(), ids=JOURNAUX_INDISPONIBLES.keys()
)
def test_un_journal_illisible_ne_fait_pas_refuser_et_chaque_step_garde_sa_ligne(
    log: subprocess.CompletedProcess[bytes], rendu: str, capsys: pytest.CaptureFixture[str]
) -> None:
    jobs = termine(job(BACK, "failure", ("Tests", "failure")), job(FRONT, "failure"))

    assert lance(Gh(document(jobs), log), RUN) == 0
    assert lignes(capsys) == [
        f"{BACK} › Tests : {rendu}",
        f"{FRONT} : aucun step en échec — conclusion failure",
    ]


def test_un_octet_hors_utf_8_ne_rend_pas_le_journal_illisible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le journal est du texte pour la session, pas une donnée : un octet invalide y devient
    `\\ufffd`, et la ligne reste."""
    jobs = termine(job(BACK, "failure", ("Tests", "failure")))
    log = f"{BACK}\tTests\t".encode() + "Error: café\n".encode("cp1252")

    assert lance(Gh(document(jobs), sortie(log)), RUN) == 0
    assert lignes(capsys) == [f"{BACK} › Tests : Error: caf\ufffd"]


# Les lignes `test_forms.py` sont la sortie de pytest 9.1.1 en `-v --tb=no` sur le poste, le
# 2026-10-21 : sans détail d'assertion, le résumé court est le seul marqueur, et la ligne verbeuse
# qui le précède nomme `FAILED` ou `ERROR` sans en dire la cause.
# (textes de la section du journal, première ligne d'erreur attendue)
PREMIERES_LIGNES = {
    "bom-et-horodatage-otes": (
        ("\ufeff2026-10-21T00:27:13.6512999Z Error: boom",),
        "Error: boom",
    ),
    "ansi-en-notation-caret": (
        ("2026-10-21T00:27:13.6513298Z ^[[31mError^[[0m: boom",),
        "Error: boom",
    ),
    "ansi-brut": (("2026-10-21T00:27:13.6513298Z \x1b[31mError\x1b[0m: boom",), "Error: boom"),
    "pytest-resume-court-failed": (
        (
            "test_forms.py::test_ok PASSED                                            [ 33%]",
            "test_forms.py::test_fails FAILED                                         [ 66%]",
            "=========================== short test summary info ===========================",
            "FAILED test_forms.py::test_fails - assert 1 == 2",
        ),
        "FAILED test_forms.py::test_fails - assert 1 == 2",
    ),
    "pytest-resume-court-error": (
        (
            "test_forms.py::test_errors ERROR                                         [100%]",
            "=========================== short test summary info ===========================",
            "ERROR test_forms.py::test_errors - RuntimeError: fixture cassée",
        ),
        "ERROR test_forms.py::test_errors - RuntimeError: fixture cassée",
    ),
    "mot-d-erreur": (
        (
            "compilation",
            "fatal: not a git repository",
            "make: *** [Makefile:1: build] Error 128",
            "##[error]Process completed with exit code 2.",
        ),
        "fatal: not a git repository",
    ),
    "ligne-make-hors-du-mot-d-erreur": (
        (
            "compilation",
            "make: *** [Makefile:1: build] Error 1",
            "##[error]Process completed with exit code 2.",
        ),
        "##[error]Process completed with exit code 2.",
    ),
    "annotation-generique-hors-du-mot-d-erreur": (
        ("##[error]Process completed with exit code 1.", "Error: Unable to upload artifact"),
        "Error: Unable to upload artifact",
    ),
    "ligne-make-sans-annotation": (
        ("compilation", "make: *** [Makefile:1: build] Error 1", "fin"),
        "make: *** [Makefile:1: build] Error 1",
    ),
    "derniere-ligne-hors-vides-et-groupes": (
        (
            "compilation",
            "sortie 3",
            "2026-10-21T00:27:14.2512327Z ",
            "##[group]Détail",
            "##[endgroup]",
        ),
        "sortie 3",
    ),
    "section-sans-ligne": (
        ("2026-10-21T00:27:14.2512327Z ", "##[group]Run make x", "##[endgroup]"),
        "section du journal sans ligne non vide",
    ),
}


@pytest.mark.parametrize(
    ("textes", "attendu"), PREMIERES_LIGNES.values(), ids=PREMIERES_LIGNES.keys()
)
def test_la_premiere_ligne_d_erreur_suit_l_ordre_des_regles(
    textes: tuple[str, ...], attendu: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """BOM, horodatage et séquences ANSI ôtés, lignes vides et groupes sautés ; puis un marqueur
    d'outil, sinon un mot d'erreur hors `make: *** [` et l'annotation générique, sinon la première
    `##[error]`, sinon la `make: *** [`, sinon la dernière ligne."""
    jobs = termine(job(BACK, "failure", ("Tests", "failure")))
    log = journal(BACK, "Tests", *textes)

    assert lance(Gh(document(jobs), sortie(log.encode())), RUN) == 0
    assert lignes(capsys) == [f"{BACK} › Tests : {attendu}"]


# (réponse de `gh run view 4242 --json status,conclusion,jobs`, motif attendu)
REFUS = {
    "run-en-cours": (
        document({"status": "in_progress", "conclusion": "", "jobs": []}),
        "run 4242 pas terminé (status in_progress) : l'attendre par `attente-ci.py`",
    ),
    "aucun-job-en-echec": (
        document(termine(job(FRONT, "success"), job(PUBLICATION, "skipped"), conclusion="success")),
        "aucun job en échec dans le run 4242 (conclusion success)",
    ),
    "lecture-des-jobs-en-panne": (
        panne(b"HTTP 404: Not Found\n(https://api.github.com/...)\n"),
        (
            "`gh run view 4242 --json status,conclusion,jobs` a échoué (1) : HTTP 404: Not Found"
            " (https://api.github.com/...)"
        ),
    ),
    "gh-absent": (FileNotFoundError("gh introuvable"), "`gh` ne se lance pas : gh introuvable"),
    "reponse-non-json": (
        sortie(b"<html>"),
        "`gh run view 4242 --json status,conclusion,jobs` ne rend pas du JSON UTF-8",
    ),
}


@pytest.mark.parametrize(("jobs", "motif"), REFUS.values(), ids=REFUS.keys())
def test_un_refus_sort_en_1_en_une_ligne_sans_lire_le_journal(
    jobs: Reponse, motif: str, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = Gh(jobs)

    assert lance(gh, RUN) == 1
    (ligne,) = lignes(capsys)
    assert ligne.startswith(f"refus — {motif}"), ligne
    assert gh.appels == [("gh", "run", "view", RUN, "--json", "status,conclusion,jobs")]


ABSENT = object()

# Chaque champ que le script lit, absent puis d'un autre type : (chemin du champ, valeur qui le
# remplace — `ABSENT` le retire). Dénombré avant le code : 8 champs — `status`, `conclusion` et
# `jobs` du run, `name`, `conclusion` et `steps` d'un job, `name` et `conclusion` d'un step —,
# plus un document, un job et un step qui ne sont pas des objets. Une liste remplacée par un objet
# vide : un objet non vide ou un texte donneraient, à l'itération, des textes qui lèvent déjà —
# ils ne verraient jamais rouge la garde de type.
FORMES: dict[str, tuple[tuple[str | int, ...], Any]] = {
    "document-hors-objet": ((), ["completed"]),
    "status-absent": (("status",), ABSENT),
    "status-non-textuel": (("status",), 1),
    "conclusion-absente": (("conclusion",), ABSENT),
    "conclusion-non-textuelle": (("conclusion",), None),
    "jobs-absents": (("jobs",), ABSENT),
    "jobs-hors-liste": (("jobs",), {}),
    "job-hors-objet": (("jobs", 0), BACK),
    "nom-de-job-absent": (("jobs", 0, "name"), ABSENT),
    "nom-de-job-non-textuel": (("jobs", 0, "name"), 7),
    "conclusion-de-job-absente": (("jobs", 0, "conclusion"), ABSENT),
    "conclusion-de-job-non-textuelle": (("jobs", 0, "conclusion"), ["failure"]),
    "steps-absents": (("jobs", 0, "steps"), ABSENT),
    "steps-hors-liste": (("jobs", 0, "steps"), {}),
    "step-hors-objet": (("jobs", 0, "steps", 0), ["Tests", "failure"]),
    "nom-de-step-absent": (("jobs", 0, "steps", 0, "name"), ABSENT),
    "nom-de-step-non-textuel": (("jobs", 0, "steps", 0, "name"), None),
    "conclusion-de-step-absente": (("jobs", 0, "steps", 0, "conclusion"), ABSENT),
    "conclusion-de-step-non-textuelle": (("jobs", 0, "steps", 0, "conclusion"), False),
}


def altere(contenu: Any, chemin: tuple[str | int, ...], valeur: Any) -> Any:
    """`contenu` dont le champ au bout de `chemin` vaut `valeur` — retiré pour `ABSENT` ; un
    chemin vide remplace le document entier."""
    if not chemin:
        return valeur
    *parents, cle = chemin
    cible = contenu
    for etape in parents:
        cible = cible[etape]
    if valeur is ABSENT:
        del cible[cle]
    else:
        cible[cle] = valeur
    return contenu


@pytest.mark.parametrize(("chemin", "valeur"), FORMES.values(), ids=FORMES.keys())
def test_des_jobs_d_une_autre_forme_sortent_en_1_en_une_ligne_sans_lire_le_journal(
    chemin: tuple[str | int, ...], valeur: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    jobs = altere(termine(job(BACK, "failure", ("Tests", "failure"))), chemin, valeur)
    gh = Gh(document(jobs))

    assert lance(gh, RUN) == 1
    (ligne,) = lignes(capsys)
    assert ligne.startswith(
        "refus — `gh run view 4242 --json status,conclusion,jobs` ne rend pas la forme attendue"
    ), ligne
    assert gh.appels == [("gh", "run", "view", RUN, "--json", "status,conclusion,jobs")]


APPELS_MAL_FORMES = {"lettres": ("abc",), "chiffre-unicode": ("²",), "argument-absent": ()}


@pytest.mark.parametrize("args", APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys())
def test_un_appel_mal_forme_sort_en_2_sans_appeler_gh(
    args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    gh = Gh(document(termine()))

    assert lance(gh, *args) == 2
    assert gh.appels == []
    assert "usage" in capsys.readouterr().err


def test_le_lanceur_par_defaut_rend_les_octets_tels_quels() -> None:
    """Le défaut réel du lanceur, que le `gh` témoin remplace partout ailleurs : ni le mode texte
    ni la page de code de la console ne touchent ce qui sort (obs 108)."""
    octets = "Critère › A\r\n".encode()
    ecrit = f"import sys; sys.stdout.buffer.write({octets!r})"

    assert erreurs_ci.default_run([sys.executable, "-c", ecrit]).stdout == octets


@pytest.mark.parametrize(
    ("args", "code", "flux", "texte"),
    [
        (["--help"], 0, "stdout", "Première ligne d'erreur"),
        (["²"], 2, "stderr", "identifiant de run attendu, pas '²'"),
    ],
    ids=["aide-sur-stdout", "usage-sur-stderr"],
)
def test_la_sortie_du_script_lance_en_tube_est_en_utf_8(
    args: list[str], code: int, flux: str, texte: str
) -> None:
    """La session lit le script par un tube. Sur ce poste, dont la page de code est cp1252, Python
    y écrit dans cet encodage (`pipeline.config.md`, « Qualité ») — l'erreur d'argparse comprise,
    qui part sur la sortie d'erreur. Sur un runner Linux, locale en UTF-8, supposé vert même sans
    le correctif — non mesuré."""
    script = REPOSITORY_ROOT / ".claude/skills/cycle-pr/scripts/erreurs-ci.py"
    done = subprocess.run([sys.executable, str(script), *args], capture_output=True, check=False)

    assert done.returncode == code
    assert texte in getattr(done, flux).decode("utf-8")
