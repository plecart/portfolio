#!/bin/sh
# La restauration de la base (ADR 0007 point 4, brief de #24) : une sauvegarde du bucket, nommée ou
# la plus récente, rejouée dans la base de la pile. Lancée par `make restore` depuis le poste — copiée
# sur le VPS, exécutée dans `/srv/portfolio` (décision 1) —, par le test mensuel sur un runner, et
# par `infra/tests/test_restore.py` contre la pile de test (décision 8).
#
# Usage : restore.sh <derniere|AAAAMMJJTHHMMSSZ> < age.key
#
# Elle orchestre des conteneurs de la pile, sans rien installer sur l'hôte : un conteneur jetable de
# l'image `backup` liste, télécharge et déchiffre (`rclone`, `age`) ; `pg_restore` et `psql` sont
# ceux du conteneur Postgres, sous le propriétaire de la base, par le socket local — aucun mot de
# passe ne traverse ; un conteneur jetable d'`api` joue les migrations.
#
# Chaque étape écrit son nom ; la première qui échoue arrête la chaîne en la nommant, comme
# `backup.sh`. Rien ne touche la base avant que l'archive ne soit téléchargée et son déchiffrement
# éprouvé. Après l'arrêt des services qui écrivent dans la base, un échec les laisse arrêtés : le
# runbook dit quoi faire (`infra/RUNBOOK.md`, « Restaurer une sauvegarde »).
#
# La clé privée `age` arrive sur l'entrée standard, jamais en argument : elle passe à l'entrée
# standard de chaque conteneur jetable qui déchiffre, qui l'écrit dans son `/tmp` — le `tmpfs` du
# Compose de production — le temps du déchiffrement. Le clair ne touche aucun disque : il va en flux
# à `pg_restore`. L'archive chiffrée attend sur l'hôte, dans un dossier supprimé en partant.
#
# Lit l'environnement :
#   COMPOSE               la commande Compose de la pile, découpée sur les espaces ;
#                         défaut `docker compose`, dans le dossier de la pile
#   RESTORE_MIN_PROJECTS  le nombre de projets publiés attendu au moins après la restauration ;
#                         vide ou absent : 0 (décision 7)
set -eu

COMPOSE=${COMPOSE:-docker compose}
min_projects=${RESTORE_MIN_PROJECTS:-0}
# Les services applicatifs qui écrivent dans la base, arrêtés pendant la restauration (décision 5).
# ponytail: `api` seul ; le `worker` de #12 s'ajoute ici.
WRITERS=api

step=préparation
work=$(mktemp -d)
stopped=

# En partant, réussite ou échec : l'archive chiffrée supprimée, l'étape qui a échoué nommée.
finish() {
	status=$?
	rm -rf "$work"
	[ "$status" -eq 0 ] || echo "échec à l'étape : $step" >&2
}
trap finish EXIT
# Un signal fait sortir la chaîne en échec, donc par `finish` (même raison que `backup.sh`).
trap 'exit 1' INT TERM HUP

# Une étape : son nom (1ᵉʳ argument), écrit avant sa commande et retenu pour le message d'échec.
run() {
	step=$1
	shift
	echo "== $step"
	"$@"
}

# Le stockage dans le conteneur jetable : le remote `r2` de `backup.sh`, configuré par les variables
# du service `backup`. ponytail: même configuration que `backup.sh`, recopiée — le script ne dépend
# ainsi que des outils de l'image, pas d'un fichier qu'elle porterait depuis tel commit.
R2='export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true RCLONE_CONFIG_R2_ENDPOINT="$BACKUP_R2_ENDPOINT"
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$BACKUP_R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$BACKUP_R2_SECRET_ACCESS_KEY"'

# Le choix dans le conteneur jetable — `$1` : l'horodatage voulu, vide pour la plus récente. Les
# objets reconnus comme des sauvegardes le sont comme par `retention.sh` : `<base>-<AAAAMMJJ>T
# <HHMMSS>Z.dump.age` à une date qui existe, relue par le `date` de busybox ; un objet que la
# chaîne n'a pas écrit n'est pas une sauvegarde (décision 3).
SELECT='set -o pipefail
rclone lsf --files-only "r2:$BACKUP_R2_BUCKET" | while IFS= read -r name; do
	case $name in
	"$PGDATABASE"-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.dump.age) ;;
	*) continue ;;
	esac
	stamp=${name#"$PGDATABASE"-}
	stamp=${stamp%.dump.age}
	[ "$(date -u -D %Y%m%dT%H%M%SZ -d "$stamp" +%Y%m%dT%H%M%SZ 2>/dev/null)" = "$stamp" ] || continue
	[ -z "$1" ] || [ "$stamp" = "$1" ] || continue
	echo "$name"
done | sort | tail -n 1'

# Le déchiffrement dans le conteneur jetable : la clé sur la première ligne de l'entrée standard,
# écrite dans `/tmp`, puis l'archive, sur le reste de l'entrée, en clair sur la sortie standard.
DECRYPT='set -o pipefail
identity=$(mktemp)
trap '\''rm -f "$identity"'\'' EXIT
trap '\''exit 1'\'' INT TERM HUP
IFS= read -r key
printf "%s\n" "$key" > "$identity"
age --decrypt --identity "$identity"'

# Lance `$1` par `sh -c` dans un conteneur jetable de l'image `backup`, arguments suivants en `$1`…
in_backup() {
	script=$1
	shift
	$COMPOSE run --rm -T backup sh -c "$R2
$script" restore "$@"
}

# La clé puis l'archive, sur l'entrée standard du déchiffrement, suivi de `$1` dans le conteneur.
decrypted() {
	{ printf '%s\n' "$key"; cat "$work/archive"; } | in_backup "$DECRYPT$1"
}

prepare() {
	case $min_projects in
	*[!0-9]*)
		echo "RESTORE_MIN_PROJECTS vaut « $min_projects » : attendu un entier" >&2
		return 1
		;;
	esac
	# La ligne de la clé, dans un fichier d'identité comme `age-keygen` l'écrit — fins de ligne du
	# poste Windows retirées.
	key=$(tr -d '\r' | sed -n '/^AGE-SECRET-KEY-1/{p;q;}')
	[ -n "$key" ] || {
		echo "aucune clé privée age (AGE-SECRET-KEY-1…) sur l'entrée standard" >&2
		return 1
	}
}

select_backup() {
	case ${1:-} in
	derniere) wanted= ;;
	[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) wanted=$1 ;;
	*)
		echo "BACKUP vaut « ${1:-} » : attendu derniere, ou l'horodatage <AAAAMMJJ>T<HHMMSS>Z" >&2
		return 1
		;;
	esac
	name=$(in_backup "$SELECT" "$wanted")
	[ -n "$name" ] || {
		echo "aucune sauvegarde ${wanted:-reconnue} dans le bucket" >&2
		return 1
	}
	echo "sauvegarde : $name"
}

download() {
	in_backup 'rclone cat "r2:$BACKUP_R2_BUCKET/$1"' "$name" > "$work/archive"
}

# L'archive entière, lisible : la clé l'ouvre, et `pg_restore` en lit la table des matières.
check_archive() {
	decrypted ' | pg_restore --list > /dev/null'
}

stop_writers() {
	running=" $($COMPOSE ps --status running --services | tr '\n' ' ') "
	for service in $WRITERS; do
		case $running in *" $service "*) stopped="$stopped $service" ;; esac
	done
	[ -z "$stopped" ] || $COMPOSE stop $stopped
	echo "arrêtés :${stopped:- aucun}"
}

# Les objets de l'archive remplacent ceux de la base, en une transaction : un échec la laisse telle
# qu'elle était. Sans pipefail dans `sh`, un flux tronqué se lit dans l'échec de `pg_restore`, qui
# ne restaure pas une archive incomplète.
restore_database() {
	decrypted '' | $COMPOSE exec -T postgres sh -c \
		'pg_restore --clean --if-exists --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

# `migrate` par le point d'entrée d'`api`, qui nomme chaque migration appliquée, puis `--check` :
# non nul si une migration attendue manque (doc Django « django-admin », décision 6).
migrate() {
	$COMPOSE run --rm -T -e STARTUP_STEPS=migrate api python manage.py migrate --check
}

# La requête de contrôle : les projets publiés, au moins `RESTORE_MIN_PROJECTS` (décision 7).
check_projects() {
	count=$($COMPOSE exec -T postgres sh -c 'psql --no-psqlrc --tuples-only --no-align \
		-v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
		-c "SELECT count(*) FROM content_project WHERE published"')
	echo "projets publiés : $count (attendu ≥ $min_projects)"
	[ "$count" -ge "$min_projects" ]
}

restart_writers() {
	[ -z "$stopped" ] || $COMPOSE start --wait $stopped
	echo "redémarrés :${stopped:- aucun}"
}

prepare
run sélection select_backup "$@"
run téléchargement download
run déchiffrement check_archive
run arrêt stop_writers
run restauration restore_database
run migrations migrate
run contrôle check_projects
run redémarrage restart_writers
