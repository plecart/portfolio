#!/bin/sh
# La rétention des sauvegardes (brief de #23, décision 7) : lit sur l'entrée standard les noms des
# objets du bucket, un par ligne, et écrit ceux qu'elle écarte, que la purge supprime
# (`backup.sh`). Elle ne touche pas au bucket : elle se teste sur des noms (`infra/tests/`).
#
# Usage : retention.sh <base>
#
# La règle de `borg prune --keep-daily 7 --keep-weekly 4` (doc « borg prune » ; source de borg
# 1.4.5, `prune_split`) : en remontant le temps, la plus récente de chacun des 7 derniers jours qui
# ont une sauvegarde ; puis la plus récente de chaque semaine, du lundi au dimanche — une semaine
# dont celle-là est déjà gardée ne garde rien de plus —, jusqu'à 4. Une règle qui n'atteint pas son
# compte garde aussi la plus ancienne (« As of Borg 1.2.0 ») : tant que le bucket est jeune, la
# première sauvegarde vieillit au lieu de disparaître. Jour et semaine se lisent dans le nom, en UTC.
set -eu

base=$1

# Chaque nom au format de la décision 6, `<base>-<AAAAMMJJ>T<HHMMSS>Z.dump.age` à une date qui
# existe, suivi de son jour et de sa semaine ISO, séparés par des tabulations. Les autres ne sont ni
# comptés ni écartés : un objet que la chaîne n'a pas écrit n'est pas une sauvegarde.
dated() {
	while IFS= read -r name; do
		case $name in
		"$base"-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.dump.age) ;;
		*) continue ;;
		esac
		stamp=${name#"$base"-}
		stamp=${stamp%.dump.age}
		# `date` refuse un mois 13, une heure 25 ou un instant d'avant 1970, mais normalise un jour
		# qui n'existe pas — un 31 avril devient un 1ᵉʳ mai (mesuré, busybox) : relue au format du
		# nom, la date doit le rendre tel quel.
		read_back=$(date -u -D %Y%m%dT%H%M%SZ -d "$stamp" '+%Y%m%dT%H%M%SZ %G-%V' 2>/dev/null) ||
			continue
		[ "${read_back% *}" = "$stamp" ] || continue
		printf '%s\t%s\t%s\n' "$name" "${stamp%%T*}" "${read_back#* }"
	done
}

# La règle de borg (`prune_split`), sur les noms du plus récent au plus ancien — l'ordre des noms est
# celui du temps : par période, la première sauvegarde est gardée si une règle précédente ne l'a pas
# déjà fait, et compte alors, jusqu'à `n` ; sous ce compte, la plus ancienne est gardée aussi.
dated | sort -r | awk -F '\t' '
function keep_firsts(period, n,    i, last, count) {
	for (i = 1; i <= NR && count < n; i++)
		if (period[i] != last) {
			last = period[i]
			if (!(i in kept)) { kept[i] = 1; count++ }
		}
	if (count < n && NR) kept[NR] = 1
}
{ name[NR] = $1; day[NR] = $2; week[NR] = $3 }
END {
	keep_firsts(day, 7)
	keep_firsts(week, 4)
	for (i = 1; i <= NR; i++) if (!(i in kept)) print name[i]
}'
