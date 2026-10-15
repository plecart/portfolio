"""Tests de la cible `make restore` : la restauration lancée du poste vers le VPS (brief de #24,
décision 1).

Le poste n'a ni le VPS ni la clé de production : la cible est exécutée avec des témoins à la place
de `scp` et `ssh` (`SCP`, `SSH`, comme `GH` pour la rétention). Ce qu'elle copierait et lancerait
sur le VPS se lit dans leurs appels, argument par argument, et ce qu'elle enverrait sur l'entrée
standard de `ssh` dans ce que le témoin y a lu. Le script lancé, `infra/restore.sh`, est éprouvé
contre la pile de test (`infra/tests/test_restore.py`).
"""

import subprocess
from pathlib import Path

import pytest
from call_witness import recorded_calls, recording
from test_infra import MAKEFILE, REPOSITORY_ROOT, run_make

HOST = "vps.example"
REMOTE_SCRIPT = "/root/portfolio-restore.sh"
KEY = "AGE-SECRET-KEY-1TEMOINTEMOINTEMOINTEMOINTEMOINTEMOINTEMOINTEMOINTEMOIN"

# Ce que chaque témoin fait de plus que consigner ses arguments : `ssh` recopie son entrée standard.
READERS = {"scp": "", "ssh": 'cat > "$0.stdin"\n'}


def restore_target(
    root: Path, environment: dict[str, str] | None = None, **variables: str
) -> subprocess.CompletedProcess[str]:
    """`make restore` avec `variables` sur la ligne de commande, et des témoins de `scp` et `ssh`
    dans `root` : chacun consigne son appel dans `root/calls` (`call_witness`), et `ssh` recopie son
    entrée standard dans `root/ssh.stdin`."""
    for tool, reader in READERS.items():
        script = recording(root / "calls") + reader
        (root / tool).write_text(script, encoding="utf-8", newline="\n")
    return run_make(
        "restore",
        makefile=MAKEFILE,
        directory=REPOSITORY_ROOT,
        environment=environment,
        SCP=f"sh {(root / 'scp').as_posix()}",
        SSH=f"sh {(root / 'ssh').as_posix()}",
        **variables,
    )


def witnessed(root: Path) -> list[list[str]]:
    """Les appels consignés par les témoins, outil en tête — son seul nom de fichier."""
    return [[Path(tool).name, *arguments] for tool, *arguments in recorded_calls(root / "calls")]


def identity_file(root: Path) -> Path:
    """Un fichier d'identité `age`, comme `age-keygen -o age.key` l'écrit, dans un dossier dont le
    nom porte une espace — comme celui d'un utilisateur du poste."""
    path = root / "Prénom Nom" / "age.key"
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"# created: 2026-10-15T00:00:00Z\n# public key: age1x\n{KEY}\n")
    return path


def test_la_cible_copie_le_script_puis_le_lance_dans_la_pile_la_cle_sur_l_entree(
    tmp_path: Path,
) -> None:
    """Le script de ce commit copié sur le VPS, hors du dossier de la pile ; puis lancé dans ce
    dossier, en `root`, avec `BACKUP` en argument et le seuil en variable — la clé sur l'entrée
    standard de `ssh`, jamais dans un argument."""
    identity = identity_file(tmp_path)

    done = restore_target(
        tmp_path,
        HOST=HOST,
        BACKUP="derniere",
        AGE_IDENTITY=identity.as_posix(),
        RESTORE_MIN_PROJECTS="1",
    )

    assert done.returncode == 0, done.stderr
    assert witnessed(tmp_path) == [
        ["scp", "infra/restore.sh", f"root@{HOST}:{REMOTE_SCRIPT}"],
        [
            "ssh",
            f"root@{HOST}",
            f"cd /srv/portfolio && RESTORE_MIN_PROJECTS=1 sh {REMOTE_SCRIPT} derniere",
        ],
    ]
    assert (tmp_path / "ssh.stdin").read_bytes() == identity.read_bytes()
    assert KEY not in done.stdout + done.stderr


def test_le_seuil_vaut_zero_par_defaut(tmp_path: Path) -> None:
    """Sans `RESTORE_MIN_PROJECTS`, le seuil est 0 : avant #27, la base n'a aucun projet publié
    (décision 7)."""
    done = restore_target(
        tmp_path,
        HOST=HOST,
        BACKUP="20261015T030000Z",
        AGE_IDENTITY=identity_file(tmp_path).as_posix(),
    )

    assert done.returncode == 0, done.stderr
    assert witnessed(tmp_path)[-1][-1].endswith(
        f"RESTORE_MIN_PROJECTS=0 sh {REMOTE_SCRIPT} 20261015T030000Z"
    )


# Cas → (variables de la ligne de commande, hormis les témoins et la clé ; ce que l'erreur nomme).
REFUSED = {
    "HOST absent": ({"BACKUP": "derniere"}, "HOST"),
    "HOST vide": ({"HOST": "", "BACKUP": "derniere"}, "HOST"),
    "BACKUP absent": ({"HOST": HOST}, "BACKUP"),
    "BACKUP vide": ({"HOST": HOST, "BACKUP": ""}, "BACKUP"),
    "clé introuvable": ({"HOST": HOST, "BACKUP": "derniere", "AGE_IDENTITY": "absente"}, "absente"),
    "BACKUP qui sort de la commande": ({"HOST": HOST, "BACKUP": "derniere;id"}, "BACKUP"),
    "HOST qui sort de la commande": ({"HOST": "vps.example;id", "BACKUP": "derniere"}, "HOST"),
    "seuil qui sort de la commande": (
        {"HOST": HOST, "BACKUP": "derniere", "RESTORE_MIN_PROJECTS": "0 id"},
        "RESTORE_MIN_PROJECTS",
    ),
}


@pytest.mark.parametrize(("variables", "named"), REFUSED.values(), ids=REFUSED.keys())
def test_une_variable_absente_ou_hors_bornes_arrete_la_cible_avant_tout_appel(
    tmp_path: Path, variables: dict[str, str], named: str
) -> None:
    """`HOST` et `BACKUP` sans défaut — restaurer détruit —, la clé lisible, et `BACKUP` comme le
    seuil bornés aux lettres et chiffres, puisqu'ils entrent dans la commande du shell distant :
    sinon, erreur qui nomme la variable, avant que `scp` ou `ssh` ne soient appelés."""
    arguments = {"AGE_IDENTITY": identity_file(tmp_path).as_posix(), **variables}

    done = restore_target(tmp_path, environment=None, **arguments)

    assert done.returncode != 0
    assert named in done.stderr
    assert witnessed(tmp_path) == []


def test_host_et_backup_de_l_environnement_ne_comptent_pas(tmp_path: Path) -> None:
    """Une variable `HOST` exportée par le shell du poste — certains la posent — ne désigne pas le
    VPS : seule la ligne de commande compte."""
    done = restore_target(
        tmp_path,
        environment={"HOST": HOST, "BACKUP": "derniere"},
        AGE_IDENTITY=identity_file(tmp_path).as_posix(),
    )

    assert done.returncode != 0
    assert "HOST" in done.stderr
    assert witnessed(tmp_path) == []
