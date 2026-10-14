"""Tests de l'image `backup` : sa chaîne de sauvegarde, sa sonde, la majeure de son `pg_dump`, son
rôle Postgres (brief de #23, décisions 2 à 6, 10 et 11).

Lancé par `make image-test`, jamais par `make test` : il lui faut les images que `make build` a
chargées — `backup`, et `caddy` pour le témoin de ping. Le job `infra` de la CI le lance après son
build ; sur un poste, `make build` d'abord.

La pile est le Compose de production, résolu avec son modèle de `.env` et surchargé par
`backup.yml` : `postgres` et `backup` y gardent leur image, leur sonde et leurs variables, dont le
test ne remplace que les valeurs. Elle démarre dans l'ordre que suit `start_stack` de
`bootstrap.sh` : la base saine, puis le rôle de sauvegarde, créé par la SQL du script, puis
`backup`. Cet ordre est recopié ici, pas éprouvé : le script reste vérifié à la main par #25, sauf
cette SQL. Aucun service externe : un témoin S3 et un témoin de ping en tiennent lieu. Elle tourne
sous son propre nom de projet, sans port publié : le test agit par `docker compose exec`.
"""

import json
import os
import re
import secrets
import subprocess
import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from test_env import declared_variables
from test_infra import loaded_image

INFRA = Path(__file__).parents[1]
BOOTSTRAP = INFRA / "bootstrap.sh"
COMPOSE_PROD = INFRA / "compose.yml"
PROD_ENV_EXAMPLE = INFRA / "prod.env.example"
STACK = Path(__file__).with_name("backup.yml")
# Un nom par lancement : deux lancements simultanés sur le même moteur ne se partagent ni
# conteneurs, ni réseau, ni volume, et l'arrêt de l'un n'emporte pas l'autre.
PROJECT = f"portfolio-test-backup-{uuid.uuid4().hex[:8]}"

# Les valeurs du modèle que le test ne remplace pas : la base sauvegardée, qui nomme les objets
# (décision 6), et le propriétaire de son schéma.
MODEL = declared_variables(PROD_ENV_EXAMPLE)
DATABASE = MODEL["POSTGRES_DB"]
# Le nom d'un objet de sauvegarde : `<base>-<AAAAMMJJ>T<HHMMSS>Z.dump.age`, en UTC (décision 6).
OBJECT_NAME = re.compile(rf"^{re.escape(DATABASE)}-\d{{8}}T\d{{6}}Z\.dump\.age$")

# Où le témoin S3 range les buckets, un dossier chacun.
S3_ROOT = "/tmp/s3"
# Une table que la base porte avant la sauvegarde, et que l'archive doit contenir.
WITNESS_TABLE = "temoin_de_sauvegarde"

# Ce que le test donne à la pile, par-dessus le modèle : le rôle de sauvegarde et les adresses des
# témoins. Les clés du témoin S3 sont tirées à chaque lancement, assez longues pour qu'il les
# accepte — mesuré le 2026-10-03 : une paire trop courte y est refusée en 403.
STACK_VALUES = {
    "BACKUP_POSTGRES_USER": "sauvegarde",
    "BACKUP_POSTGRES_PASSWORD": secrets.token_hex(16),
    "BACKUP_R2_ENDPOINT": "http://s3:8080",
    "BACKUP_R2_ACCESS_KEY_ID": secrets.token_hex(16),
    "BACKUP_R2_SECRET_ACCESS_KEY": secrets.token_hex(32),
}


@dataclass(frozen=True)
class Run:
    """Une exécution de la chaîne : son processus terminé, son bucket, le chemin de son ping."""

    process: subprocess.CompletedProcess[bytes]
    bucket: str
    ping_path: str

    @property
    def log(self) -> str:
        """Ce que la chaîne a écrit, sortie standard puis sortie d'erreur."""
        return (self.process.stdout + self.process.stderr).decode()


@dataclass(frozen=True)
class Stack:
    """La pile démarrée : l'environnement qui la désigne à Compose, la clé privée `age` du test."""

    environment: Mapping[str, str]
    identity: str

    def compose(
        self, *arguments: str, stdin: bytes | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        """Lance `docker compose` sur la pile, sans vérifier son code de sortie."""
        return subprocess.run(
            compose_command(*arguments),
            env=self.environment,
            input=stdin,
            capture_output=True,
            check=False,
        )

    def output(self, *arguments: str) -> str:
        """La sortie standard de `docker compose`, qui doit réussir."""
        return succeeded(self.compose(*arguments)).stdout.decode()

    def psql(self, service: str, sql: str, *options: str) -> subprocess.CompletedProcess[bytes]:
        """Joue `sql` par l'entrée standard de `psql`, dans le conteneur `service` : arrêt à la
        première erreur, dont la sortie d'erreur ne donne que le code SQLSTATE. Dans `backup`, la
        session est celle de son rôle (variables de libpq du Compose de production)."""
        return self.compose(
            "exec",
            "-T",
            service,
            "psql",
            "--no-psqlrc",
            "--quiet",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "VERBOSITY=sqlstate",
            *options,
            stdin=sql.encode(),
        )

    def as_owner(self, sql: str, *options: str) -> subprocess.CompletedProcess[bytes]:
        """Joue `sql` sous le rôle de l'application, propriétaire de la base, par le socket du
        conteneur Postgres — comme `bootstrap.sh` la joue."""
        return self.psql("postgres", sql, "-U", MODEL["POSTGRES_USER"], "-d", DATABASE, *options)

    def backup_role_sql(self, password: str) -> str:
        """La SQL du rôle de sauvegarde, écrite par `bootstrap.sh` lui-même — pas une copie : le
        script chargé par `source`, qui n'y définit que ses fonctions, puis la sienne appelée. Dans
        le conteneur Postgres, qui a `bash` ; le script, en LF partout (`.gitattributes`)."""
        printed = self.compose(
            "exec",
            "-T",
            "postgres",
            "bash",
            "-c",
            'source /dev/stdin && backup_role_sql "$@"',
            BOOTSTRAP.name,
            STACK_VALUES["BACKUP_POSTGRES_USER"],
            password,
            stdin=BOOTSTRAP.read_bytes(),
        )
        return succeeded(printed).stdout.decode()

    def apply_backup_role(self, password: str) -> None:
        """Crée le rôle de sauvegarde, ou lui donne `password`, par la SQL de `bootstrap.sh`."""
        succeeded(self.as_owner(self.backup_role_sql(password)))

    def backup_role(self) -> str:
        """Ce que la base sait du rôle de sauvegarde, mot de passe excepté — `pg_roles` le masque :
        son identifiant, ses attributs, les rôles dont il est membre."""
        described = self.as_owner(
            "SELECT to_jsonb(r) || jsonb_build_object('member_of', ARRAY("
            "SELECT roleid::regrole::text FROM pg_auth_members WHERE member = r.oid))"
            f" FROM pg_roles r WHERE rolname = '{STACK_VALUES['BACKUP_POSTGRES_USER']}'",
            "--tuples-only",
            "--no-align",
        )
        role = succeeded(described).stdout.decode()
        assert role.strip(), "le rôle de sauvegarde est absent"
        return role

    def probe(self, password: str | None = None) -> subprocess.CompletedProcess[bytes]:
        """La sonde de `backup` du Compose de production, exécutée dans son conteneur — sous un
        autre mot de passe que le sien, si `password` en donne un."""
        options = ["-e", f"PGPASSWORD={password}"] if password else []
        return self.compose("exec", "-T", *options, "backup", *production_probe())

    def backup(self, **overrides: str) -> Run:
        """Lance la chaîne dans le conteneur `backup`, comme on le ferait à la main.

        Chaque exécution a son bucket et son chemin de ping : les tests ne voient que ce que la leur
        a produit. `overrides` remplace des variables du conteneur, le temps de cette exécution.
        """
        bucket, ping_path = uuid.uuid4().hex, f"/{uuid.uuid4().hex}"
        self.output("exec", "-T", "s3", "mkdir", "-p", f"{S3_ROOT}/{bucket}")
        variables = {
            "BACKUP_R2_BUCKET": bucket,
            "BACKUP_PING_URL": f"http://ping:8080{ping_path}",
            **overrides,
        }
        process = self.compose("exec", "-T", *environment_options(variables), "backup", "backup.sh")
        return Run(process, bucket, ping_path)

    def objects(self, bucket: str) -> list[str]:
        """Les objets d'un bucket du témoin S3."""
        return self.output("exec", "-T", "s3", "ls", "-A", f"{S3_ROOT}/{bucket}").split()

    def pings(self, path: str) -> int:
        """Le nombre de requêtes que le témoin de ping a reçues sur `path` — une ligne de son
        journal d'accès chacune."""
        logs = self.output("logs", "--no-log-prefix", "ping").splitlines()
        entries = [json.loads(line) for line in logs if line.startswith("{")]
        return sum(1 for entry in entries if entry.get("request", {}).get("uri") == path)

    def restored_listing(self, bucket: str, name: str) -> str:
        """La table des matières de l'archive d'un objet : déchiffrée par la clé privée du test,
        puis lue par le `pg_restore` du Postgres de production, celui qui la restaurera (#24)."""
        decrypted = self.compose(
            "exec",
            "-T",
            "-e",
            f"AGE_IDENTITY={self.identity}",
            "s3",
            "sh",
            "-c",
            'printf "%s\\n" "$AGE_IDENTITY" > /tmp/identity'
            ' && age --decrypt --identity /tmp/identity "$0"',
            f"{S3_ROOT}/{bucket}/{name}",
        )
        listing = self.compose(
            "exec", "-T", "postgres", "pg_restore", "--list", stdin=succeeded(decrypted).stdout
        )
        return succeeded(listing).stdout.decode()

    def leftovers(self) -> list[str]:
        """Ce qui reste dans le dossier des fichiers de travail du conteneur `backup`."""
        return self.output("exec", "-T", "backup", "ls", "-A", "/tmp").split()


def succeeded(
    completed: subprocess.CompletedProcess[bytes],
) -> subprocess.CompletedProcess[bytes]:
    """`completed`, qui doit avoir réussi : sinon, sa sortie d'erreur fait le message d'échec."""
    assert completed.returncode == 0, completed.stderr.decode()
    return completed


def environment_options(variables: Mapping[str, str]) -> list[str]:
    """Les options `-e NOM=valeur` de `docker compose exec` qui posent ces variables."""
    return [option for name, value in variables.items() for option in ("-e", f"{name}={value}")]


def compose_command(*arguments: str) -> list[str]:
    """La commande `docker compose` sur la pile : le Compose de production et son modèle de `.env`,
    surchargés par `backup.yml`, sous le nom de projet du test."""
    return [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "--env-file",
        str(PROD_ENV_EXAMPLE),
        "--file",
        str(COMPOSE_PROD),
        "--file",
        str(STACK),
        *arguments,
    ]


def age_key_pair(image: str) -> tuple[str, str]:
    """Une paire `age` neuve, engendrée par l'image : sa clé publique, sa clé privée. Jamais
    commitée, perdue à la fin du lancement."""
    printed = subprocess.run(
        ["docker", "run", "--rm", image, "age-keygen"], capture_output=True, text=True, check=True
    ).stdout
    public = re.search(r"^# public key: (age1\w+)$", printed, re.MULTILINE)
    private = re.search(r"^AGE-SECRET-KEY-1\w+$", printed, re.MULTILINE)
    assert public and private, printed
    return public[1], private[0]


@pytest.fixture(scope="module")
def stack() -> Iterator[Stack]:
    """La pile démarrée pour le module, arrêtée et supprimée à la fin — volumes compris —, même en
    cas d'échec."""
    image = loaded_image("backup")
    recipient, identity = age_key_pair(image)
    environment = {
        **os.environ,
        **STACK_VALUES,
        "BACKUP_IMAGE": image,
        "CADDY_IMAGE": loaded_image("caddy"),
        "BACKUP_AGE_RECIPIENT": recipient,
    }
    started = Stack(environment, identity)
    try:
        # Dans le `try` : un démarrage raté laisse un réseau et des conteneurs créés. Les services
        # nommés seulement : le reste du Compose de production ne démarre pas ici. L'ordre de
        # `bootstrap.sh` : la sonde de `backup` ouvre une session sous son rôle.
        started.output("up", "--detach", "--wait", "postgres")
        started.apply_backup_role(STACK_VALUES["BACKUP_POSTGRES_PASSWORD"])
        started.output("up", "--detach", "--wait", "backup")
        succeeded(started.as_owner(f"CREATE TABLE {WITNESS_TABLE} (id integer)"))
        yield started
    finally:
        started.compose("down", "--volumes")


@pytest.fixture(autouse=True)
def empty_work_directory(stack: Stack) -> Iterator[None]:
    """Chaque test laisse vide le dossier des fichiers de travail du conteneur `backup` : ce qu'un
    test rouge y laisserait ne fait pas rougir les suivants (mesuré à la relecture de la PR #73)."""
    yield
    stack.output("exec", "-T", "backup", "find", "/tmp", "-mindepth", "1", "-delete")


def major_version(printed: str) -> str:
    """La majeure d'une sortie `--version` de PostgreSQL : `pg_dump (PostgreSQL) 16.15` → `16`."""
    found = re.search(r"\(PostgreSQL\) (\d+)\.", printed)
    assert found, printed
    return found[1]


def production_probe() -> list[str]:
    """La commande de la sonde de `backup` dans `infra/compose.yml`, sans son type (`CMD`)."""
    services = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))["services"]
    kind, *command = services["backup"]["healthcheck"]["test"]
    assert kind == "CMD", kind
    return command


def test_pg_dump_est_de_la_majeure_du_postgres_de_production(stack: Stack) -> None:
    """Une archive écrite par un `pg_dump` plus récent n'est pas garantie lisible par un serveur
    plus ancien (doc PostgreSQL 16, « pg_dump », Notes) : la restauration (#24) se fait dans ce
    serveur-ci. Les deux binaires, interrogés dans leurs images (décision 2)."""
    client = stack.output("exec", "-T", "backup", "pg_dump", "--version")
    server = stack.output("exec", "-T", "postgres", "postgres", "--version")

    assert major_version(client) == major_version(server)


@pytest.mark.parametrize(("password", "healthy"), [(None, True), ("mot-de-passe-faux", False)])
def test_la_sonde_de_production_ne_dit_sain_que_le_role_qui_ouvre_une_session(
    stack: Stack, password: str | None, healthy: bool
) -> None:
    """Le déploiement attend `backup` sain (`up --wait`) : sain quand son rôle ouvre une session sur
    la base, malade quand il ne le peut pas (décision 10). Une sonde qui ne s'authentifie pas — un
    `pg_isready` — dirait sain un conteneur qui ne sauvegardera jamais rien."""
    probed = stack.probe(password)

    assert (probed.returncode == 0) is healthy, probed.stderr


# Les sept écritures que la décision 3 refuse au rôle de sauvegarde, sur une table de l'application.
WRITES = {
    "insert": f"INSERT INTO {WITNESS_TABLE} VALUES (1)",
    "update": f"UPDATE {WITNESS_TABLE} SET id = 2",
    "delete": f"DELETE FROM {WITNESS_TABLE}",
    "truncate": f"TRUNCATE {WITNESS_TABLE}",
    "create-table": "CREATE TABLE intrus (id integer)",
    "drop-table": f"DROP TABLE {WITNESS_TABLE}",
    "create-role": "CREATE ROLE intrus",
}

# Le code SQLSTATE d'un défaut de droit, `insufficient_privilege` (doc PostgreSQL 16, annexe A
# « PostgreSQL Error Codes ») : un refus pour une autre cause — syntaxe, objet absent — n'en est pas
# un.
INSUFFICIENT_PRIVILEGE = "42501"


def in_cancelled_transaction(statement: str) -> str:
    """`statement` dans une transaction annulée : qu'il réussisse ou non, la base n'en garde rien."""
    return f"BEGIN;\n{statement};\nROLLBACK;\n"


@pytest.mark.parametrize("statement", WRITES.values(), ids=WRITES.keys())
def test_le_role_cree_par_bootstrap_se_voit_refuser_chaque_ecriture(
    stack: Stack, statement: str
) -> None:
    """Le rôle que crée la SQL de `bootstrap.sh` lit tout et n'écrit rien (décision 3) : chaque
    écriture lui est refusée faute de droit. Qu'il prenne un dump complet, la chaîne réussie le
    montre (`test_une_sauvegarde_reussie_laisse_un_objet_chiffre_lisible_et_un_seul_ping`)."""
    refused = stack.psql("backup", in_cancelled_transaction(statement))

    assert refused.returncode != 0
    assert INSUFFICIENT_PRIVILEGE in refused.stderr.decode(), refused.stderr


@pytest.mark.parametrize("statement", WRITES.values(), ids=WRITES.keys())
def test_chaque_ecriture_refusee_au_role_passe_sous_le_proprietaire(
    stack: Stack, statement: str
) -> None:
    """Le témoin du test précédent : la même écriture réussit sous le propriétaire de la base — le
    refus vient du rôle, pas de l'instruction."""
    applied = stack.as_owner(in_cancelled_transaction(statement))

    assert applied.returncode == 0, applied.stderr


def test_rejouee_la_sql_du_role_ne_change_que_son_mot_de_passe(stack: Stack) -> None:
    """`bootstrap.sh` joue la SQL du rôle à chaque passage, et c'est ainsi qu'il en renouvelle le mot
    de passe (décision 3) : rejouée, elle ne recrée pas le rôle et ne touche ni à ses attributs ni à
    ses appartenances ; l'ancien mot de passe n'ouvre plus de session, le nouveau si."""
    before = stack.backup_role()
    renewed = secrets.token_hex(16)
    try:
        stack.apply_backup_role(renewed)

        assert stack.backup_role() == before
        assert stack.probe(STACK_VALUES["BACKUP_POSTGRES_PASSWORD"]).returncode != 0
        assert stack.probe(renewed).returncode == 0
    finally:
        stack.apply_backup_role(STACK_VALUES["BACKUP_POSTGRES_PASSWORD"])


# Étape → ce qui la fait échouer, le temps d'une exécution : un mot de passe que la base refuse, un
# destinataire que `age` ne sait pas lire, une clé d'accès que le stockage refuse.
FAILURES = {
    "dump": {"PGPASSWORD": "mot-de-passe-faux"},
    "chiffrement": {"BACKUP_AGE_RECIPIENT": "age1-destinataire-illisible"},
    "envoi": {"BACKUP_R2_SECRET_ACCESS_KEY": secrets.token_hex(32)},
}


@pytest.mark.parametrize(("step", "overrides"), FAILURES.items(), ids=FAILURES.keys())
def test_une_etape_qui_echoue_arrete_la_chaine_sans_objet_ni_ping(
    stack: Stack, step: str, overrides: dict[str, str]
) -> None:
    """La première étape qui échoue arrête la chaîne : sortie non nulle, l'étape nommée dans le
    journal, aucun ping — healthchecks.io alerte de son absence (décision 5). Rien n'arrive dans le
    bucket : l'envoi est la seule étape qui y écrit, et un objet S3 n'est visible qu'entier
    (décision 4). Les fichiers de travail sont supprimés aussi en cas d'échec."""
    run = stack.backup(**overrides)

    assert run.process.returncode != 0, run.log
    assert f"échec à l'étape : {step}" in run.log
    assert stack.pings(run.ping_path) == 0
    assert stack.objects(run.bucket) == []
    assert stack.leftovers() == []


# Les signaux qui interrompent une exécution lancée à la main — `Ctrl-C`, terminal fermé, `kill`.
# Un shell non interactif qui les reçoit sans les piéger sort sans jouer son `trap … EXIT` (mesuré à
# la relecture de la PR #73, busybox `ash`).
SIGNALS = ["INT", "TERM", "HUP"]

# Une base qui ne répond pas — une adresse réservée à la documentation (RFC 5737) —, et le délai au
# bout duquel `pg_dump` y renonce : assez long pour que le signal tombe pendant le dump.
UNREACHABLE_DATABASE = {"PGHOST": "192.0.2.1", "PGCONNECT_TIMEOUT": "5"}

# Le temps laissé à la chaîne pour créer ses fichiers de travail.
STARTUP_DEADLINE = 10.0


@pytest.mark.parametrize("signal", SIGNALS)
def test_une_sauvegarde_interrompue_ne_laisse_aucun_fichier_de_travail(
    stack: Stack, signal: str
) -> None:
    """Le dump en clair ne survit pas à l'exécution, même interrompue (décision 4) : le signal
    arrive pendant le dump, la chaîne sort en échec et ses fichiers de travail disparaissent."""
    running = subprocess.Popen(
        compose_command(
            "exec", "-T", *environment_options(UNREACHABLE_DATABASE), "backup", "backup.sh"
        ),
        env=stack.environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + STARTUP_DEADLINE
    while not stack.leftovers():
        assert time.monotonic() < deadline, "la chaîne n'a créé aucun fichier de travail"
        time.sleep(0.2)
    stack.output("exec", "-T", "backup", "pkill", f"-{signal}", "-f", "backup.sh")
    running.communicate(timeout=30)

    assert running.returncode != 0
    assert stack.leftovers() == []


def test_les_fichiers_de_travail_ne_survivent_pas_a_l_arret_du_conteneur(stack: Stack) -> None:
    """`docker stop` n'envoie `SIGTERM` qu'à `supercronic`, qui attend la tâche, puis le moteur la
    tue (`SIGKILL`) : aucun piège ne joue, et une sauvegarde interrompue ainsi laisse son dump en
    clair dans `/tmp` (mesuré à la relecture de la PR #73). Le conteneur arrêté n'en garde rien."""
    stack.output("exec", "-T", "backup", "mkdir", "/tmp/tmp.interrompue")
    stack.output("restart", "backup")

    assert stack.leftovers() == []


def test_les_fichiers_de_travail_ont_une_place_bornee(stack: Stack) -> None:
    """`/tmp` est en mémoire : sans taille, il prendrait jusqu'à la moitié de la RAM de l'hôte et
    pèserait sur toute la pile, Postgres compris (mesuré à la relecture de la PR #73). Borné, un
    dump trop gros échoue à son étape, nommée, sans ping — l'alerte de healthchecks.io."""
    mounts = stack.output("exec", "-T", "backup", "cat", "/proc/mounts").splitlines()
    tmp = [line.split() for line in mounts if line.split()[1:3] == ["/tmp", "tmpfs"]]

    assert len(tmp) == 1, mounts
    assert any(option.startswith("size=") for option in tmp[0][3].split(",")), tmp


def test_supercronic_lance_la_chaine_chaque_nuit(stack: Stack) -> None:
    """`supercronic` est le processus du conteneur, et sa table lance la chaîne chaque nuit à 03:00
    (décision 8) : une autre commande d'image, ou une table qui lance autre chose, laisserait la
    pile saine sans qu'aucune sauvegarde ne parte — seule l'absence de ping le dirait."""
    jobs = [
        line
        for line in stack.output("exec", "-T", "backup", "cat", "/etc/crontab").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    assert stack.output("exec", "-T", "backup", "cat", "/proc/1/comm").strip() == "supercronic"
    stack.output("exec", "-T", "backup", "supercronic", "-test", "/etc/crontab")
    assert jobs == ["0 3 * * * backup.sh"]


def test_une_sauvegarde_reussie_laisse_un_objet_chiffre_lisible_et_un_seul_ping(
    stack: Stack,
) -> None:
    """La chaîne complète, contre les témoins : un objet au nom du contrat avec #24, que la clé
    privée déchiffre en une archive que `pg_restore` lit — la base entière, table témoin comprise —,
    puis un ping, un seul. Les fichiers de travail, dump en clair compris, ne survivent pas à
    l'exécution."""
    run = stack.backup()

    assert run.process.returncode == 0, run.log
    objects = stack.objects(run.bucket)
    assert len(objects) == 1 and OBJECT_NAME.match(objects[0]), objects
    assert f"TABLE public {WITNESS_TABLE}" in stack.restored_listing(run.bucket, objects[0])
    assert stack.pings(run.ping_path) == 1
    assert stack.leftovers() == []
