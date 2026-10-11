# Image `backup` : la sauvegarde nocturne de Postgres (ADR 0007, D42) — `pg_dump`, `age`, `rclone`
# et `curl`, ordonnancés par `supercronic`, sous un utilisateur sans privilège. La chaîne elle-même
# est `backup.sh`, son horaire `crontab`.
#
# Contexte de build : la racine du dépôt, comme pour les autres images (ADR 0014).
#
# Chaque outil entre sous une forme que le scan ouvre (brief de #23, décision 1) : `pg_dump` et
# `curl` par les paquets d'Alpine, que suit sa base de sécurité ; les binaires Go hors de la base de
# paquets, où Trivy les analyse — il n'ouvre pas un binaire Go installé par `apk` (mesuré le
# 2026-10-03 : 0 au scan, 31 HIGH dans les mêmes binaires copiés hors de la base de paquets).

# Épinglées étiquette x.y.z et empreinte, `FROM` en colonne 0 : Dependabot
# (`.github/dependabot.yml`) propose chaque nouvelle version, étiquette et empreinte ensemble.
FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 AS base

# `rclone` depuis son image officielle, dans un étage à lui : Dependabot ne lit que les `FROM`.
FROM rclone/rclone:1.75.2@sha256:2687085f718d3c628f7fdfb77c52a1d344332aed543110bb88088f2c70d43eb5 AS rclone

# `age` et `supercronic` n'ont pas d'image officielle : les fichiers de leur release, à la somme
# SHA-256 épinglée, que BuildKit vérifie avant de les copier. Dependabot ne les suit pas : la
# procédure de montée est dans `CONTRIBUTING.md`. `linux/amd64` seulement, l'architecture du VPS,
# de la CI et du poste.
FROM base AS age
ADD --checksum=sha256:cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10 \
    https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz \
    /tmp/age.tar.gz
RUN tar -xzf /tmp/age.tar.gz -C /tmp


FROM base

# `pg_dump` de la majeure du serveur, 16 (décision 2) : une archive écrite par un `pg_dump` plus
# récent n'est pas garantie lisible par un serveur plus ancien — un test tient l'égalité. Les
# paquets ne sont pas épinglés à une version : Alpine retire de ses dépôts celles qu'il remplace,
# et la reconstruction suivante échouerait. L'empreinte de l'image de base et le scan tiennent ce
# qui est installé.
RUN apk add --no-cache postgresql16-client curl

COPY --from=rclone /usr/local/bin/rclone /usr/local/bin/rclone
# `age-keygen` sert aux tests, qui engendrent une paire à chaque lancement ; celle de la production
# s'engendre hors du VPS, où la clé privée ne vient jamais (ADR 0007, point 2).
COPY --from=age /tmp/age/age /tmp/age/age-keygen /usr/local/bin/
ADD --checksum=sha256:a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1 --chmod=755 \
    https://github.com/aptible/supercronic/releases/download/v0.2.49/supercronic-linux-amd64 \
    /usr/local/bin/supercronic

COPY --chmod=755 infra/backup/backup.sh /usr/local/bin/backup.sh
COPY infra/backup/crontab /etc/crontab

# Utilisateur système, sans mot de passe ni dossier personnel : la chaîne n'écrit que ses fichiers
# de travail, dans `/tmp`.
RUN adduser -S -D -H backup
USER backup

# `supercronic` est le processus du conteneur : s'il sort, le conteneur boucle et sa sonde ne répond
# plus (décision 10). Il transmet l'environnement du conteneur à la tâche (son README).
CMD ["supercronic", "/etc/crontab"]
