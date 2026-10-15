"""Tests de la restauration : `infra/restore.sh`, joué contre la pile de test (brief de #24,
décisions 3 à 7 et 11).

Lancé par `make image-test`, après `make build` : la pile est celle de `test_backup_image.py`,
démarrée sous un nom de projet à ce module, `api` en plus — il migre la base au démarrage, qui
porte donc le vrai schéma. Une sauvegarde de `backup.sh` dépose son objet dans le témoin S3, puis
le script le restaure, lancé par `sh` comme `make restore` le lance sur le VPS. Sa commande Compose
(`COMPOSE`, décision 8) est celle de la pile, précédée d'un témoin qui consigne chacun de ses
appels avant de les exécuter : l'ordre des gestes et l'absence de la clé dans leurs arguments se
lisent dans ce journal.
"""

import subprocess
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_backup_image import (
    DATABASE,
    Stack,
    age_key_pair,
    compose_command,
    started_stack,
    succeeded,
)
from test_infra import loaded_image

SCRIPT = Path(__file__).parents[1] / "restore.sh"
PROJECT = f"portfolio-test-restore-{uuid.uuid4().hex[:8]}"

# Les étapes, dans l'ordre de la décision 4.
STEPS = [
    "sélection",
    "téléchargement",
    "déchiffrement",
    "arrêt",
    "restauration",
    "migrations",
    "contrôle",
    "redémarrage",
]

# Une table du schéma sauvegardé, vide dans l'archive : une ligne posée après la sauvegarde dit si la
# base a changé — une restauration la remet vide.
WITNESS_TABLE = "temoin_de_restauration"

# Le témoin de la commande Compose : chaque appel consigné, arguments séparés par US (0x1f), appels
# par RS (0x1e) — un argument peut porter des sauts de ligne —, puis exécuté tel quel.
COMPOSE_WITNESS = 'printf "%s\\037" "$@" >> "$0.calls"\nprintf "\\036" >> "$0.calls"\nexec "$@"\n'

# Des objets que la rétention ne reconnaît pas comme des sauvegardes, et qui suivent dans l'ordre
# des noms toute sauvegarde d'aujourd'hui : un 31 avril, que `date` normaliserait en 1ᵉʳ mai ; un
# suffixe de plus ; un fichier étranger. « derniere » doit les ignorer (décision 3).
UNRECOGNIZED = [
    f"{DATABASE}-29990431T030000Z.dump.age",
    f"{DATABASE}-29991231T030000Z.dump.age.partiel",
    "zz-notes.txt",
]
# Une sauvegarde reconnue, plus ancienne, que « derniere » ne doit pas prendre : vide, elle ferait
# échouer le déchiffrement.
OLDER = f"{DATABASE}-20000101T030000Z.dump.age"


@dataclass(frozen=True)
class Restoration:
    """Une exécution du script : son processus terminé, et les appels de sa commande Compose."""

    process: subprocess.CompletedProcess[str]
    calls: list[list[str]]

    @property
    def log(self) -> str:
        """Ce que le script a écrit, sortie standard puis sortie d'erreur."""
        return self.process.stdout + self.process.stderr

    @property
    def steps(self) -> list[str]:
        """Les étapes que le script a annoncées (`== <étape>`), dans l'ordre."""
        return [line[3:] for line in self.process.stdout.splitlines() if line.startswith("== ")]

    def index(self, *tail: str) -> int:
        """Le rang du premier appel de Compose qui finit par `tail`."""
        return next(i for i, call in enumerate(self.calls) if call[-len(tail) :] == list(tail))


@pytest.fixture(scope="module")
def stack() -> Iterator[Stack]:
    """La pile démarrée pour le module, `api` compris ; sa base porte la table témoin."""
    with started_stack(PROJECT) as started:
        started.output("up", "--detach", "--wait", "api")
        succeeded(started.as_owner(f"CREATE TABLE {WITNESS_TABLE} (id integer)"))
        yield started


@pytest.fixture(autouse=True)
def api_running(stack: Stack) -> Iterator[None]:
    """`api` tourne en sortant de chaque test : un échec après l'arrêt le laisse arrêté (brief,
    décision 6), et le test suivant le trouverait ainsi."""
    yield
    stack.output("up", "--detach", "--wait", "api")


def backed_up(stack: Stack) -> tuple[str, str]:
    """Une sauvegarde de `backup.sh` dans un bucket neuf, à côté d'objets que « derniere » doit
    écarter — la table témoin vide —, puis une ligne posée dans cette table, que l'archive ne porte
    pas.

    Returns:
        Le bucket, et le nom de l'objet de la sauvegarde.
    """
    succeeded(stack.as_owner(f"DELETE FROM {WITNESS_TABLE}"))
    run = stack.backup(stack.bucket(OLDER, *UNRECOGNIZED))
    assert run.process.returncode == 0, run.log
    (name,) = set(stack.objects(run.bucket)) - {OLDER, *UNRECOGNIZED}
    succeeded(stack.as_owner(f"INSERT INTO {WITNESS_TABLE} VALUES (1)"))
    return run.bucket, name


def witness_rows(stack: Stack) -> str:
    """Le nombre de lignes de la table témoin."""
    printed = stack.as_owner(f"SELECT count(*) FROM {WITNESS_TABLE}", "--tuples-only")
    return succeeded(printed).stdout.decode().strip()


def running_services(stack: Stack) -> list[str]:
    """Les services de la pile qui tournent."""
    return stack.output("ps", "--status", "running", "--services").split()


def restore(
    stack: Stack,
    tmp_path: Path,
    bucket: str,
    *arguments: str,
    identity: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> Restoration:
    """Lance le script sur la pile, la clé `identity` — celle du test par défaut — sur l'entrée
    standard, dans un fichier d'identité comme `age-keygen` l'écrit, aux fins de ligne du poste
    Windows d'où `make restore` le lit.

    Vérifie, à chaque exécution, réussie ou non, que la clé n'a paru dans aucun argument de la
    commande Compose — donc d'aucun conteneur — et qu'aucun conteneur jetable ne survit : son
    `/tmp`, le `tmpfs` du Compose de production, part avec lui (brief, critère « Clé »).
    """
    witness = tmp_path / "compose.sh"
    witness.write_text(COMPOSE_WITNESS, encoding="utf-8", newline="\n")
    key = identity or stack.identity
    process = subprocess.run(
        ["sh", SCRIPT.as_posix(), *arguments],
        input=f"# created: 2026-10-15T00:00:00Z\r\n# public key: age1x\r\n{key}\r\n",
        env={
            **stack.environment,
            "COMPOSE": " ".join(["sh", witness.as_posix(), *compose_command()]),
            "BACKUP_R2_BUCKET": bucket,
            # Sur le poste, le `sh` de Git réécrirait en chemins Windows les arguments en `/…`.
            "MSYS_NO_PATHCONV": "1",
            **(environment or {}),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=600,
    )
    log = Path(f"{witness}.calls")
    recorded = log.read_text(encoding="utf-8") if log.exists() else ""
    calls = [call.split("\x1f")[:-1] for call in recorded.split("\x1e")[:-1]]
    one_off = subprocess.run(
        ["docker", "ps", "--all", "--quiet", "--filter", "label=com.docker.compose.oneoff=True"]
        + ["--filter", f"label=com.docker.compose.project={PROJECT}"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert all(key not in argument for call in calls for argument in call)
    assert one_off.stdout == ""
    return Restoration(process, calls)


@pytest.mark.parametrize("by_timestamp", [False, True], ids=["derniere", "horodatage"])
def test_la_chaine_restaure_la_sauvegarde_choisie_puis_redemarre_api(
    stack: Stack, tmp_path: Path, by_timestamp: bool
) -> None:
    """La chaîne complète (décisions 3 à 7) : chaque étape annoncée dans l'ordre, la sauvegarde
    choisie — la plus récente des objets reconnus, ou celle de l'horodatage —, la base revenue à
    son état sauvegardé, `api` arrêté avant la restauration et redémarré après, `migrate --check`
    joué, le contrôle écrit."""
    bucket, name = backed_up(stack)
    selector = name.removeprefix(f"{DATABASE}-").removesuffix(".dump.age")

    done = restore(stack, tmp_path, bucket, selector if by_timestamp else "derniere")

    assert done.process.returncode == 0, done.log
    assert done.steps == STEPS
    assert f"sauvegarde : {name}" in done.log
    assert witness_rows(stack) == "0"
    pg_restore = next(i for i, call in enumerate(done.calls) if call[-1].startswith("pg_restore"))
    assert done.index("stop", "api") < pg_restore < done.index("start", "--wait", "api")
    assert done.index("python", "manage.py", "migrate", "--check") > pg_restore
    assert "projets publiés : 0 (attendu ≥ 0)" in done.log
    assert "api" in running_services(stack)


# Cas → (arguments, environnement, clé privée autre que celle du test, étape qui échoue).
FAILURES: dict[str, tuple[list[str], dict[str, str], bool, str]] = {
    "horodatage inconnu": (["20000102T030000Z"], {}, False, "sélection"),
    "nom mal formé": (["hier"], {}, False, "sélection"),
    "BACKUP absent": ([], {}, False, "sélection"),
    "seuil mal formé": (["derniere"], {"RESTORE_MIN_PROJECTS": "un"}, False, "préparation"),
    "clé fausse": (["derniere"], {}, True, "déchiffrement"),
    "seuil non atteint": (["derniere"], {"RESTORE_MIN_PROJECTS": "1"}, False, "contrôle"),
}
# Les étapes qui précèdent l'arrêt : leur échec ne touche ni la base ni `api`.
BEFORE_STOP = {"préparation", "sélection", "téléchargement", "déchiffrement"}


@pytest.mark.parametrize(
    ("arguments", "environment", "foreign_key", "step"), FAILURES.values(), ids=FAILURES.keys()
)
def test_une_etape_qui_echoue_arrete_la_chaine_en_la_nommant(
    stack: Stack,
    tmp_path: Path,
    arguments: list[str],
    environment: dict[str, str],
    foreign_key: bool,
    step: str,
) -> None:
    """La première étape qui échoue arrête la chaîne : code non nul, étape nommée (décision 4).
    Avant l'arrêt, rien n'a changé — la base garde la ligne posée après la sauvegarde, `api`
    tourne ; après, la base est restaurée et `api` reste arrêté (décision 6)."""
    bucket, _ = backed_up(stack)
    identity = age_key_pair(loaded_image("backup"))[1] if foreign_key else None

    failed = restore(
        stack, tmp_path, bucket, *arguments, identity=identity, environment=environment
    )

    assert failed.process.returncode != 0
    assert f"échec à l'étape : {step}" in failed.log
    untouched = step in BEFORE_STOP
    assert witness_rows(stack) == ("1" if untouched else "0")
    assert ("api" in running_services(stack)) is untouched
