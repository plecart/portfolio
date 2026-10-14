#!/bin/sh
# La sauvegarde de la base (ADR 0007 point 3, brief de #23 décision 4) : dump, chiffrement, envoi,
# purge, ping — chaque étape sur des fichiers de travail, jamais un tube jusqu'au bucket. Lancée
# chaque nuit par `supercronic` (`crontab`), ou à la main : `docker compose exec backup backup.sh`.
#
# Chaque étape écrit son nom ; la première qui échoue arrête la chaîne (`set -e`), avant le ping —
# l'absence de ping est l'alerte (D33). Les fichiers de travail sont supprimés en partant : le dump
# en clair ne survit pas à l'exécution.
#
# Lit l'environnement du conteneur, que `supercronic` transmet (`infra/compose.yml`) :
#   PGHOST PGDATABASE PGUSER PGPASSWORD  la base, sous le rôle en lecture seule — lus par libpq
#   BACKUP_AGE_RECIPIENT                 la clé publique `age`, seule clé de l'image
#   BACKUP_R2_ENDPOINT BACKUP_R2_ACCESS_KEY_ID BACKUP_R2_SECRET_ACCESS_KEY BACKUP_R2_BUCKET
#                                        le bucket des sauvegardes et son jeton
#   BACKUP_PING_URL                      l'adresse de ping
set -eu

step=préparation
work=$(mktemp -d)

# En partant, réussite ou échec : les fichiers de travail supprimés, l'étape qui a échoué nommée.
finish() {
	status=$?
	rm -rf "$work"
	[ "$status" -eq 0 ] || echo "échec à l'étape : $step" >&2
}
trap finish EXIT
# Un signal — `Ctrl-C`, terminal fermé, `kill` — fait sortir la chaîne en échec, donc par `finish` :
# sans ce piège, le shell sortirait sans jouer celui de la sortie (mesuré, busybox `ash`). Un
# `SIGKILL` reste hors d'atteinte de tout piège — c'est ainsi que `docker stop` arrête une
# sauvegarde en cours : `/tmp` est un `tmpfs` (`infra/compose.yml`), que l'arrêt du conteneur vide.
trap 'exit 1' INT TERM HUP

# Le contrat avec la restauration (#24, décision 6) : `<base>-<AAAAMMJJ>T<HHMMSS>Z.dump.age`, à la
# date du début de l'exécution, en UTC — l'ordre des noms est l'ordre du temps.
name="$PGDATABASE-$(date -u +%Y%m%dT%H%M%SZ).dump.age"

# Le stockage, configuré par variables d'environnement, sans fichier (doc rclone « Environment
# variables ») : le remote `r2`. `no_check_bucket` : le jeton n'a de droits que sur les objets du
# bucket, pas sur le bucket lui-même (doc Cloudflare R2 « rclone »).
export RCLONE_CONFIG_R2_TYPE=s3 \
	RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
	RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true \
	RCLONE_CONFIG_R2_ENDPOINT="$BACKUP_R2_ENDPOINT" \
	RCLONE_CONFIG_R2_ACCESS_KEY_ID="$BACKUP_R2_ACCESS_KEY_ID" \
	RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$BACKUP_R2_SECRET_ACCESS_KEY"

# Une étape : son nom (1ᵉʳ argument), écrit avant sa commande et retenu pour le message d'échec.
run() {
	step=$1
	shift
	echo "== $step"
	"$@"
}

# La rétention (décision 7) : la liste du bucket, ce que `retention.sh` en écarte, chaque objet
# écarté supprimé puis nommé. Après l'envoi seulement — l'objet de l'exécution compte —, et la
# première suppression refusée arrête la chaîne, sans ping.
purge() {
	rclone lsf --files-only "r2:$BACKUP_R2_BUCKET" > "$work/objects"
	retention.sh "$PGDATABASE" < "$work/objects" > "$work/expired"
	while IFS= read -r object; do
		rclone deletefile "r2:$BACKUP_R2_BUCKET/$object"
		echo "supprimé : $object"
	done < "$work/expired"
}

# L'archive `custom`, compressée, que lit `pg_restore` (ADR 0007 point 4) : la base entière, sans
# option qui en retire propriétaires ou droits — la restauration choisit (décision 6).
run dump pg_dump --format=custom --file="$work/base.dump"
run chiffrement age --recipient "$BACKUP_AGE_RECIPIENT" --output "$work/$name" "$work/base.dump"
# La seule étape qui écrit dans le bucket : un stockage S3 ne rend un objet visible qu'entier.
run envoi rclone copyto "$work/$name" "r2:$BACKUP_R2_BUCKET/$name"
run purge purge
# Un seul signal, à la fin, en cas de réussite (décision 5). Délai et réessais : la forme que
# recommande healthchecks.io (docs « Shell scripts », lue le 2026-10-04).
run ping curl -fsS -m 10 --retry 5 -o /dev/null "$BACKUP_PING_URL"
