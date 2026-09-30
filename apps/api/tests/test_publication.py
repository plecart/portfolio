"""Tests de la publication des images sur GHCR : `make push`, `make prune`.

La publication tourne sur GitHub Actions, après chaque push sur `main` (ADR 0014) ; le poste n'a ni
le jeton ni le registre. Ces tests lisent donc ce que `make` exécuterait — `make --dry-run`, ou la
recette lancée sur un `gh` témoin —, sans rien pousser ni supprimer.
"""

import re
import subprocess
from pathlib import Path

import pytest
from test_infra import PUBLISH_PREFIX, built_images, make_dry_run, run_make

# Le SHA complet d'un commit, étiquette de l'image publiée à côté de `latest`.
SHA = "0123456789abcdef0123456789abcdef01234567"

# Les versions que chaque paquet garde (brief de #15, décision 1).
KEPT_VERSIONS = 3

# Les versions qu'un paquet perd, dans le filtre `jq` de la lecture : tout, sauf les dernières.
KEPT_SLICE = re.compile(r"\.\[:-(\d+)\]")


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
