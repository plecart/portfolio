"""Tests de la chaîne d'approvisionnement : actions et images épinglées, Dependabot, audit Python.

Ces tests n'ont besoin ni de GitHub ni du réseau : ils lisent des fichiers de configuration, et
lancent la porte d'audit hors ligne. Ils gardent ce qui ne se verrait qu'après le merge, et en
silence : une action ou une image qui suit une étiquette déplaçable, un écosystème que Dependabot
ne surveille plus, une exception d'audit qui ne tomberait jamais.
"""

import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

# `test_supply_chain.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"
AUDIT_GATE = REPOSITORY_ROOT / "infra" / "ci" / "pip_audit_gate.py"
DEPENDABOT = REPOSITORY_ROOT / ".github" / "dependabot.yml"

# Les écosystèmes que Dependabot surveille (brief de #5), chacun avec un fichier qu'il doit trouver
# dans le dossier configuré.
ECOSYSTEM_MANIFESTS = {
    "uv": "uv.lock",
    "npm": "package-lock.json",
    "github-actions": ".github/workflows",
    "docker": "Dockerfile",
}

# La politique commune à tous les écosystèmes : passage hebdomadaire, mineures et correctifs
# groupés — les majeures restent seules, chacune dans sa PR —, aucun libellé hors du mapping de
# `.claude/pipeline.config.md`, commits au format conventional du dépôt (brief de #5, briefing du
# 2026-09-25).
UPDATE_POLICY: dict[str, Any] = {
    "schedule": {"interval": "weekly"},
    "groups": {"minor-and-patch": {"update-types": ["minor", "patch"]}},
    "labels": [],
    "commit-message": {"prefix": "chore", "include": "scope"},
}

# Tous les Dockerfile du dépôt : un Dockerfile ajouté est tenu aux mêmes règles sans retoucher
# les tests. Les noms d'étage de Docker sont insensibles à la casse, d'où `re.IGNORECASE`.
DOCKERFILES = sorted(REPOSITORY_ROOT.glob("infra/**/Dockerfile"))
FROM_LINE = re.compile(
    r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", re.MULTILINE | re.IGNORECASE
)
COPY_FROM = re.compile(r"^COPY\s+.*?--from=(\S+)", re.MULTILINE | re.IGNORECASE)
DIGEST_PINNED_IMAGE = re.compile(r"^[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}$")

PYTHON_UPGRADES_IGNORED = {
    "dependency-name": "python",
    "update-types": ["version-update:semver-major", "version-update:semver-minor"],
}

# Un identifiant d'avis quelconque : la porte ne le cherche nulle part, elle le transmet.
ADVISORY = "GHSA-aaaa-bbbb-cccc"

# Transmis à `pip-audit` à la place d'un audit réel : il répond sans réseau et sans rien auditer.
# C'est ce qui permet de savoir, sans dépendre de PyPI, si la porte a lancé `pip-audit` ou non.
PIP_AUDIT_VERSION = "--version"

# `uses: owner/action@<empreinte> # vX.Y.Z`. Le commentaire porte l'étiquette **la plus précise**
# du commit : Dependabot réécrit un commentaire qui se termine par une étiquette pointant encore
# sur le commit épinglé (`version_commenter.rb`, dependabot-core), et une étiquette majeure
# (`v7`) cesse d'y pointer dès qu'une version sort — précisément quand la mise à jour arrive.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<reference>\S+)(?P<comment>.*)$", re.MULTILINE)
PINNED_REFERENCE = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^ # v\d+\.\d+\.\d+$")

# Toute clé `uses`, quelle que soit sa forme. Dénombrement de la relecture de #5 : 10 formes de
# `uses:` recensées ; `USES` en lit 3 et en refuse 4 par excès (guillemets autour de la valeur,
# action locale, `docker://`, double espace avant `#`) ; les 3 autres lui échappaient — un fichier
# `.yaml`, un mapping en flux `{ uses: … }`, une clé entre guillemets. Le glob couvre la première,
# ce décompte les deux suivantes : une clé que `USES` ne lit pas fait échouer le test.
USES_KEY = re.compile(r"""\buses["']?\s*:""")


def test_chaque_action_est_epinglee_par_empreinte_de_commit() -> None:
    """Une étiquette peut être déplacée par son propriétaire ou par un attaquant ; une empreinte non.

    L'incident `tj-actions/changed-files` (2025) est passé par là : des étiquettes de version
    redirigées vers un commit malveillant, exécuté sans signal par tous les dépôts qui les
    suivaient (brief de #5).
    """
    workflows = sorted([*WORKFLOWS_DIRECTORY.glob("*.yml"), *WORKFLOWS_DIRECTORY.glob("*.yaml")])
    found: list[tuple[str, re.Match[str]]] = []
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        matches = list(USES.finditer(text))
        assert len(USES_KEY.findall(text)) == len(matches), (
            f"{workflow.name} : une clé `uses` échappe au motif — forme non lue, donc non vérifiée"
        )
        found += [(workflow.name, match) for match in matches]

    assert found, "aucun `uses:` trouvé — le motif a-t-il cessé de mordre ?"
    unpinned = [
        f"{name} : {match.group('reference')}{match.group('comment')}"
        for name, match in found
        if not (
            PINNED_REFERENCE.match(match.group("reference"))
            and VERSION_COMMENT.match(match.group("comment"))
        )
    ]
    assert not unpinned, f"{len(found)} `uses:` repassés, non épinglés : {unpinned}"


def dependabot_updates() -> list[dict[str, Any]]:
    """Les entrées `updates` de `.github/dependabot.yml`, une par écosystème surveillé."""
    return yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))["updates"]


def dependabot_entry(ecosystem: str) -> dict[str, Any]:
    """L'entrée Dependabot d'un écosystème ; le test échoue si elle manque."""
    entries = [entry for entry in dependabot_updates() if entry["package-ecosystem"] == ecosystem]
    assert entries, f"aucune entrée Dependabot pour « {ecosystem} »"
    return entries[0]


def test_dependabot_surveille_chaque_ecosysteme_une_seule_fois() -> None:
    """Une entrée en double ferait deux jeux de PR pour les mêmes dépendances ; une en moins, aucun."""
    ecosystems = sorted(entry["package-ecosystem"] for entry in dependabot_updates())

    assert ecosystems == sorted(ECOSYSTEM_MANIFESTS)


@pytest.mark.parametrize(("ecosystem", "manifest"), sorted(ECOSYSTEM_MANIFESTS.items()))
def test_chaque_ecosysteme_suit_la_politique_de_mise_a_jour(ecosystem: str, manifest: str) -> None:
    """Même politique partout, et un dossier qui contient bien ce que Dependabot doit y lire.

    Un dossier déplacé sans sa ligne de configuration ne fait échouer que la tâche Dependabot,
    dans un onglet que personne ne lit : ce test le fait échouer ici.
    """
    entry = dependabot_entry(ecosystem)
    directory = REPOSITORY_ROOT / entry["directory"].lstrip("/")

    assert (directory / manifest).exists(), f"{manifest} introuvable dans {entry['directory']}"
    assert {key: entry.get(key) for key in UPDATE_POLICY} == UPDATE_POLICY


def test_dependabot_ne_propose_jamais_de_nouvelle_version_de_python() -> None:
    """La version de Python est une décision du projet, pas une mise à jour.

    `.python-version` l'épingle et l'image la suit sous test (`test_infra.py`) : une PR qui
    proposerait `3.13-slim-bookworm` échouerait chaque semaine, par construction. Dependabot ne
    propose donc, pour cette image, que la nouvelle empreinte de la même étiquette.
    """
    ignored = dependabot_entry("docker").get("ignore", [])

    assert PYTHON_UPGRADES_IGNORED in ignored


def dockerfile_stages(dockerfile: Path) -> tuple[list[str], set[str]]:
    """Les images citées par les `FROM` d'un Dockerfile, et les noms d'étage qu'il déclare.

    Un `FROM <étage>` qui reprend un étage déjà déclaré n'est pas une image : il est écarté.

    Returns:
        Les images, dans l'ordre du fichier, et l'ensemble des noms d'étage (`AS <nom>`).
    """
    lines = FROM_LINE.findall(dockerfile.read_text(encoding="utf-8"))
    stages = {stage.lower() for _, stage in lines if stage}
    return [image for image, _ in lines if image.lower() not in stages], stages


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda path: path.parent.name)
def test_chaque_image_de_base_est_epinglee_par_empreinte(dockerfile: Path) -> None:
    """Une étiquette d'image peut changer de contenu ; une empreinte non.

    Le guide « Building best practices » de Docker le recommande, et c'est ce qui donne prise à
    Dependabot : il propose la nouvelle empreinte quand l'étiquette bouge. L'étiquette est gardée
    devant l'empreinte, pour la lecture et pour que Dependabot sache quelle ligne suivre.
    """
    images, _ = dockerfile_stages(dockerfile)

    assert images, "aucune image de base trouvée — le motif a-t-il cessé de mordre ?"
    unpinned = [image for image in images if not DIGEST_PINNED_IMAGE.match(image)]
    assert not unpinned, f"{len(images)} images repassées, non épinglées : {unpinned}"


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda path: path.parent.name)
def test_toute_image_copiee_passe_par_un_etage_nomme(dockerfile: Path) -> None:
    """Dependabot ne lit que les lignes `FROM` (`docker/file_parser.rb`, dependabot-core).

    Une image citée seulement dans un `COPY --from=<image>` ne serait jamais mise à jour : elle
    est déclarée dans un étage à elle, et `COPY --from` en reprend le nom.
    """
    _, stages = dockerfile_stages(dockerfile)
    sources = COPY_FROM.findall(dockerfile.read_text(encoding="utf-8"))

    outside = [source for source in sources if source.lower() not in stages]
    assert not outside, f"{len(sources)} `COPY --from` repassés, hors d'un étage : {outside}"


def utc_today() -> date:
    """La date du jour telle que la porte la calcule : en UTC, celle de la CI."""
    return datetime.now(UTC).date()


def exception_entry(**changes: str | None) -> bytes:
    """Une exception valable, modifiée par `changes`, au format du fichier d'exceptions.

    Chaque changement remplace la valeur TOML brute d'un champ, ou le retire s'il vaut `None` ;
    un champ inconnu est ajouté. Un cas mal formé se lit ainsi comme l'écart exact qui le rend
    invalide.

    Args:
        changes: champ → valeur TOML brute (`'"texte"'`, `2026-12-31`), ou `None` pour le retirer.

    Returns:
        La table `[[exception]]`, encodée en UTF-8 ; par défaut, elle expire aujourd'hui (UTC).
    """
    fields: dict[str, str | None] = {
        "id": f'"{ADVISORY}"',
        "reason": '"aucun chemin d\'appel vers le code vulnérable"',
        "expires": utc_today().isoformat(),
        **changes,
    }
    lines = [f"{key} = {value}" for key, value in fields.items() if value is not None]
    return "\n".join(["[[exception]]", *lines, ""]).encode()


def run_audit_gate(
    tmp_path: Path, exceptions: bytes | None, *forwarded: str, timezone: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Lance la porte d'audit, depuis `tmp_path`, sur un fichier d'exceptions écrit pour le test.

    Args:
        tmp_path: dossier temporaire du test : il reçoit le fichier et sert de dossier courant.
        exceptions: contenu du fichier d'exceptions ; `None` pour un fichier absent.
        forwarded: arguments que la porte doit transmettre à `pip-audit`.
        timezone: valeur de `TZ` pour la porte, c'est-à-dire son fuseau local ; celui du poste
            par défaut.

    Returns:
        Le processus terminé, sorties capturées.
    """
    path = tmp_path / "exceptions.toml"
    if exceptions is not None:
        path.write_bytes(exceptions)
    environment = dict(os.environ)
    if timezone:
        environment["TZ"] = timezone
    return subprocess.run(
        [sys.executable, str(AUDIT_GATE), "--exceptions", str(path), *forwarded],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def offline_audit(tmp_path: Path) -> list[str]:
    """Les arguments d'un audit réel, mais hors ligne, que `pip-audit` journalise.

    `--dry-run` sur un environnement vide ne consulte aucun service ; `-v` fait journaliser par
    `pip-audit` les arguments qu'il a reçus, dont `ignore_vulns`. C'est ce qui prouve la
    transmission des exceptions : l'écho de la commande par la porte ne prouve que l'écho.
    """
    empty = tmp_path / "environnement-vide"
    empty.mkdir()
    return ["-v", "--dry-run", "--progress-spinner", "off", "--path", str(empty)]


def test_une_exception_expiree_fait_echouer_l_audit_sans_le_lancer(tmp_path: Path) -> None:
    """Passée sa date, une exception rebloque : c'est ce qui l'empêche de devenir permanente.

    L'échec précède l'audit : `pip-audit` ne tourne pas du tout, pour qu'une exception expirée
    ne puisse jamais passer inaperçue derrière un audit qui, par ailleurs, serait vert.
    """
    yesterday = (utc_today() - timedelta(days=1)).isoformat()

    result = run_audit_gate(tmp_path, exception_entry(expires=yesterday), PIP_AUDIT_VERSION)

    assert result.returncode == 1
    assert ADVISORY in result.stderr
    assert "pip-audit" not in result.stdout, "`pip-audit` a tourné malgré l'exception expirée"


def test_une_exception_valable_est_transmise_a_pip_audit(tmp_path: Path) -> None:
    """Jusqu'à sa date incluse, `pip-audit` reçoit l'ordre d'ignorer l'avis, et l'audit tourne."""
    result = run_audit_gate(tmp_path, exception_entry(), *offline_audit(tmp_path))

    assert result.returncode == 0, result.stderr
    assert f"ignore_vulns=['{ADVISORY}']" in result.stderr


# Deux fuseaux extrêmes. À toute heure, l'un d'eux décale la date locale d'un jour par rapport à la
# date UTC : UTC+14 dès 10 h UTC, UTC-12 avant midi UTC. Une porte qui lirait la date locale fait
# donc échouer l'un des deux cas, quelle que soit l'heure du run. Notation POSIX de `TZ`, honorée
# aussi par le CRT de Windows (mesuré) — le signe y est inversé : `AAA-14` est en avance sur UTC.
@pytest.mark.parametrize(
    ("timezone", "age_in_days", "expected"),
    [("AAA-14", 0, 0), ("AAA+12", 1, 1)],
    ids=["UTC+14, expire aujourd'hui en UTC", "UTC-12, a expiré hier en UTC"],
)
def test_la_date_du_jour_est_celle_de_l_utc(
    tmp_path: Path, timezone: str, age_in_days: int, expected: int
) -> None:
    """Le poste et la CI rendent le même verdict, quel que soit le fuseau du poste."""
    expires = (utc_today() - timedelta(days=age_in_days)).isoformat()

    result = run_audit_gate(
        tmp_path, exception_entry(expires=expires), PIP_AUDIT_VERSION, timezone=timezone
    )

    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize(
    ("forwarded", "expected", "trace"),
    [
        (("--option-inconnue",), 2, "pip-audit: error"),
        (("-r", "requirements-absent.txt"), 1, "invalid requirements input"),
    ],
    ids=["refus d'une option", "échec de l'audit"],
)
def test_la_porte_rend_le_code_de_sortie_de_pip_audit(
    tmp_path: Path, forwarded: tuple[str, ...], expected: int, trace: str
) -> None:
    """Une porte qui avalerait le code de `pip-audit` ne bloquerait jamais rien.

    Les deux codes viennent de `pip-audit` lui-même, sans réseau — `trace` le prouve : 2 pour une
    option qu'il refuse, 1 pour un audit qui échoue, le code d'une vulnérabilité trouvée. Le
    fichier d'exceptions est vide : le test ne dépend pas de la date.
    """
    result = run_audit_gate(tmp_path, b"", *forwarded)

    assert result.returncode == expected, result.stderr
    assert trace in result.stderr


# Les formes que prend un fichier d'exceptions mal écrit : 14 recensées sur les 10 branches de
# validation de la porte, toutes refusées avant l'audit. Sans validation, chacune finit en trace
# d'appel illisible dans le journal de CI, ou — pire — en exception acceptée à tort ou ignorée en
# silence : une date en chaîne ne se compare à rien, une table mal nommée n'est lue par personne,
# un `id` entouré d'espaces ne correspond à aucun avis. Toute branche de validation ajoutée à la
# porte ajoute sa forme ici.
MALFORMED_EXCEPTIONS: dict[str, bytes | None] = {
    "fichier absent": None,
    "encodage autre qu'UTF-8": '[[exception]]\nreason = "é"\n'.encode("latin-1"),
    "TOML illisible": b"[[exception]]\nexpires = \n",
    "table mal nommée": exception_entry().replace(b"[[exception]]", b"[[exceptions]]"),
    # Un entier et non une chaîne : une chaîne s'itère, et la branche suivante la refuserait
    # quand même — seul un non-itérable montre que ces deux branches-là mordent.
    "exception qui n'est pas une liste": b"exception = 2026\n",
    "entrée qui n'est pas une table": b"exception = [2026]\n",
    "sans date": exception_entry(expires=None),
    "champ en trop": exception_entry(note='"x"'),
    "champ mal orthographié": exception_entry(reason=None, raison='"r"'),
    "id vide": exception_entry(id='""'),
    "id entouré d'espaces": exception_entry(id=f'" {ADVISORY} "'),
    "raison vide": exception_entry(reason='""'),
    "date entre guillemets": exception_entry(expires='"2099-01-01"'),
    "date et heure": exception_entry(expires="2099-01-01T00:00:00"),
}


@pytest.mark.parametrize(
    "exceptions", MALFORMED_EXCEPTIONS.values(), ids=MALFORMED_EXCEPTIONS.keys()
)
def test_un_fichier_d_exceptions_mal_forme_fait_echouer_l_audit(
    tmp_path: Path, exceptions: bytes | None
) -> None:
    """Un fichier mal formé est refusé avant l'audit, avec un message et sans trace d'appel."""
    result = run_audit_gate(tmp_path, exceptions, PIP_AUDIT_VERSION)

    assert result.returncode == 1
    assert "fichier d'exceptions invalide" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr
    assert "pip-audit" not in result.stdout, "`pip-audit` a tourné malgré un fichier invalide"
