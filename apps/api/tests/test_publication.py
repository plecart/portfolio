"""Tests de la publication des images sur GHCR : `make push`, `make prune`, et le job `publish`.

La publication tourne sur GitHub Actions, après chaque push sur `main` (ADR 0014) ; le poste n'a ni
le jeton ni le registre. Ces tests lisent donc ce que `make` exécuterait — `make --dry-run`, ou la
recette lancée sur un `gh` témoin —, sans rien pousser ni supprimer, et le workflow tel que
l'analyseur YAML le lit. Comme dans `test_image_scan.py`, la garde du job est une fonction sur du
texte, appliquée au dépôt et à un recueil de formes, `PUBLISH_FORMS`.
"""

import re
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml
from test_image_scan import SCANNING_JOBS
from test_infra import (
    BUILD_COMMAND,
    CI_WORKFLOW,
    PUBLISH_PREFIX,
    built_images,
    ci_build_flags,
    make_dry_run,
    run_make,
)

# Le SHA complet d'un commit, étiquette de l'image publiée à côté de `latest`.
SHA = "0123456789abcdef0123456789abcdef01234567"

# Les versions que chaque paquet garde (brief de #15, décision 1).
KEPT_VERSIONS = 3

# Les versions qu'un paquet perd, dans le filtre `jq` de la lecture : tout, sauf les dernières.
KEPT_SLICE = re.compile(r"\.\[:-(\d+)\]")

# Ce que porte le job `publish` (brief de #15, décision 5) : il attend les trois autres jobs, pour
# ne publier qu'un commit dont toute la CI est verte ; il ne tourne que sur un push vers `main` ;
# seul à écrire dans le registre, il lit le dépôt sans y écrire, et le reste du workflow ne fait
# que lire ; une publication attend la fin de la précédente, sans l'annuler.
PUBLISH_NEEDS = {"api", "web", "infra"}
PUBLISH_IF = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
READ_ONLY = {"contents": "read"}
PUBLISH_PERMISSIONS = {"contents": "read", "packages": "write"}

# Ce que le job lance après son build, dans cet ordre : le scan, puis le push de ce qui vient
# d'être scanné, sous l'étiquette du commit, puis la rétention.
PUBLISH_COMMANDS = [
    SCANNING_JOBS["publish"][1],
    f'make push IMAGE_PREFIX={PUBLISH_PREFIX} IMAGE_TAG="$GITHUB_SHA"',
    f"make prune IMAGE_PREFIX={PUBLISH_PREFIX}",
]


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
    if failing_version:
        lines.append(f'case "$*" in *"--method DELETE"*/{failing_version}) exit 1 ;; esac')
    lines += ['case "$*" in *"--method DELETE"*) exit 0 ;; esac', "echo 11", "echo 12"]
    script = root / "gh"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return f"sh {script.as_posix()}"


def run_prune(gh: str) -> subprocess.CompletedProcess[str]:
    """`make prune` sous le préfixe de publication, avec `gh` remplacé par `gh`."""
    return run_make("prune", IMAGE_PREFIX=PUBLISH_PREFIX, GH=gh)


def publish_findings(workflow: str) -> list[str]:
    """Ce qui, dans un workflow, écarte le job `publish` de ce que le brief de #15 exige.

    Returns:
        Un constat si le job manque ; sinon un par propriété altérée — `needs`, `if`, permissions
        du job, du workflow ou d'un autre job, `concurrency`, et l'ordre scan, push, rétention.
        Liste vide : le job est conforme.
    """
    document = yaml.safe_load(workflow)
    jobs = document["jobs"]
    job = jobs.get("publish")
    if job is None:
        return ["aucun job `publish`"]
    findings: list[str] = []
    if set(job.get("needs") or []) != PUBLISH_NEEDS:
        findings.append(f"`needs` vaut {job.get('needs')}, attendu {sorted(PUBLISH_NEEDS)}")
    if job.get("if") != PUBLISH_IF:
        findings.append(f"`if` vaut {job.get('if')!r}, attendu {PUBLISH_IF!r}")
    if document.get("permissions") != READ_ONLY:
        findings.append(f"le workflow donne {document.get('permissions')}, attendu {READ_ONLY}")
    if job.get("permissions") != PUBLISH_PERMISSIONS:
        findings.append(f"le job donne {job.get('permissions')}, attendu {PUBLISH_PERMISSIONS}")
    findings += [
        f"le job `{name}` règle ses permissions"
        for name, other in jobs.items()
        if name != "publish" and "permissions" in other
    ]
    concurrency = job.get("concurrency")
    settings: dict[str, object] = (
        cast(dict[str, object], concurrency) if isinstance(concurrency, dict) else {}
    )
    if not (settings.get("group") and settings.get("cancel-in-progress") is False):
        findings.append(
            "`concurrency` doit nommer son groupe et porter `cancel-in-progress: false`"
        )
    steps: list[dict[str, object]] = job.get("steps") or []
    launched = [step.get("run") for step in steps]
    if [command for command in launched if command in PUBLISH_COMMANDS] != PUBLISH_COMMANDS:
        findings.append(
            f"le job ne lance pas, une fois chacune et dans cet ordre, {PUBLISH_COMMANDS}"
        )
    return findings


# --- Le recueil des formes : chaque cas recensé, avec son verdict attendu ---------------------

SCAN_LINE, PUSH_LINE, PRUNE_LINE = (f"      - run: {command}\n" for command in PUBLISH_COMMANDS)
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
  publish:
    needs: [api, web, infra]
    if: {PUBLISH_IF}
    permissions:
      contents: read
      packages: write
    concurrency:
      group: publish
      cancel-in-progress: false
    steps:
{SCAN_LINE}{PUSH_LINE}{PRUNE_LINE}"""

# Forme → (texte remplacé, remplacement, constat attendu). Le texte remplacé est pris dans
# `CONFORMING_WORKFLOW` : une forme qui ne le changerait pas resterait conforme, et son verdict
# attendu la ferait rougir.
PUBLISH_CHANGES = {
    "conforme": ("", "", False),
    "sans le job": ("  publish:", "  autre:", True),
    "needs sans web": ("[api, web, infra]", "[api, infra]", True),
    "needs d'un seul job": ("[api, web, infra]", "infra", True),
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
    "permissions sur un autre job": (
        "  infra:\n    steps: []",
        "  infra:\n    permissions:\n      packages: write\n    steps: []",
        True,
    ),
    "concurrence qui annule": ("cancel-in-progress: false", "cancel-in-progress: true", True),
    "concurrence sans annulation implicite": ("      cancel-in-progress: false\n", "", True),
    "sans concurrence": (
        "    concurrency:\n      group: publish\n      cancel-in-progress: false\n",
        "",
        True,
    ),
    "push avant scan": (SCAN_LINE + PUSH_LINE, PUSH_LINE + SCAN_LINE, True),
    "sans rétention": (PRUNE_LINE, "", True),
    "rétention avant push": (PUSH_LINE + PRUNE_LINE, PRUNE_LINE + PUSH_LINE, True),
    "push sans l'étiquette du commit": (' IMAGE_TAG="$GITHUB_SHA"', "", True),
    "push en double": (PUSH_LINE, PUSH_LINE + PUSH_LINE, True),
}
PUBLISH_FORMS = {
    form: (CONFORMING_WORKFLOW.replace(old, new) if old else CONFORMING_WORKFLOW, expected)
    for form, (old, new, expected) in PUBLISH_CHANGES.items()
}


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
    """Chaque paquet publié lit ses versions dans l'API de GitHub, filtrées pour en garder trois
    (brief de #15, décision 1), et supprime chacune de celles que la lecture rend — ici les
    versions 11 et 12 du `gh` témoin. Le filtre lui-même, `gh` l'évalue : ce test en lit le
    paramètre."""
    assert run_prune(fake_gh(tmp_path)).returncode == 0
    calls = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
    packages = [
        f"users/plecart/packages/container/{Path(image).name}/versions"
        for image in published_images()
    ]

    listings = [call.split(" --jq ") for call in calls if "--method" not in call]
    assert [url for url, _ in listings] == [f"api {package}?per_page=100" for package in packages]
    assert [KEPT_SLICE.findall(jq) for _, jq in listings] == [[str(KEPT_VERSIONS)]] * len(packages)
    assert [call for call in calls if "--method" in call] == [
        f"api --method DELETE {package}/{version}" for package in packages for version in (11, 12)
    ]


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


def test_le_job_publish_ne_publie_qu_un_commit_vert_de_main_une_fois_scanne() -> None:
    """`needs` sur les trois autres jobs, push vers `main` seulement, `packages: write` sur ce
    seul job, publications sans annulation ; scan, push puis rétention (brief de #15, décision 5).
    Un `workflow_run` ou une publication depuis `infra` sont écartés : le premier publierait
    depuis le workflow de la branche par défaut, la seconde un commit dont `api` ou `web` a
    échoué (ADR 0014)."""
    assert publish_findings(CI_WORKFLOW.read_text(encoding="utf-8")) == []


def test_la_publication_construit_sans_attestation() -> None:
    """Ni provenance ni SBOM (brief de #15, décision 7) : chacune entrerait au paquet comme une
    version sans étiquette, que la rétention ne supprime jamais, et rien ne les consomme. Sans ces
    drapeaux, `make build` exporte une attestation (mesuré au lot 1)."""
    flags = ci_build_flags("publish")
    assert flags, "aucune étape du job `publish` ne passe `DOCKER_BUILD_FLAGS`"

    printed = make_dry_run("build", environment={"DOCKER_BUILD_FLAGS": flags})
    builds = [match.group().split() for match in BUILD_COMMAND.finditer(printed)]

    assert builds, "aucune commande de build lue — sa forme a-t-elle changé ?"
    assert all({"--provenance=false", "--sbom=false"} <= set(build) for build in builds)


def test_la_publication_reconstruit_depuis_le_cache_du_job_infra() -> None:
    """`publish` restaure, sous la même clé, l'entrée de cache qu'`infra` vient d'écrire dans le
    même run, et ne l'écrit pas. Deux clés qui dériveraient le feraient reconstruire à froid, sans
    un signal."""
    jobs = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]

    def cache_inputs(job: str, action: str) -> object:
        steps = jobs[job]["steps"]
        found = [step for step in steps if str(step.get("uses", "")).startswith(f"{action}@")]
        assert len(found) == 1, f"le job `{job}` a {len(found)} étape `{action}`"
        return found[0]["with"]

    assert cache_inputs("publish", "actions/cache/restore") == cache_inputs(
        "infra", "actions/cache"
    )
