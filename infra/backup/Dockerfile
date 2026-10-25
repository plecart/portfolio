# Image `backup` : la sauvegarde nocturne de Postgres (ADR 0007, D42) — `pg_dump`, `age`, `rclone`
# et `curl`, ordonnancés par `supercronic`, sous un utilisateur sans privilège. La chaîne elle-même
# est `backup.sh`, sa rétention `retention.sh`, son horaire `crontab`.
#
# Contexte de build : la racine du dépôt, comme pour les autres images (ADR 0014).
#
# Chaque outil entre sous une forme que le scan ouvre (brief de #23, décision 1) : `pg_dump` et
# `curl` par les paquets d'Alpine, que suit sa base de sécurité ; les binaires Go hors de la base de
# paquets, où Trivy les analyse — il n'ouvre pas un binaire Go installé par `apk` (mesuré le
# 2026-10-03 : 0 au scan, 31 HIGH dans les mêmes binaires copiés hors de la base de paquets).
# `age`, `age-keygen` et `rclone` sont compilés par le projet, avec le Go de l'image `golang`
# épinglée ci-dessous : leurs releases embarquent un Go en retard sur ses correctifs (ADR 0018).
# `supercronic` entre par le fichier de sa release.
#
# Qui suit quoi : Dependabot (`.github/dependabot.yml`) propose chaque nouvelle version d'`alpine`
# et de `golang` — une montée de Go recompile `age` et `rclone` ; les versions d'`age`, `rclone` et
# `supercronic` se montent à la main (`CONTRIBUTING.md`).

# Épinglées étiquette x.y.z et empreinte, `FROM` en colonne 0 : Dependabot propose chaque nouvelle
# version, étiquette et empreinte ensemble.
FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 AS base

# Le compilateur. Chaque binaire est compilé par `go install <module>@<version>` sous la forme de
# sa release officielle, sans cgo ; ses modules restent aux versions que fixe cette release : on
# change le compilateur, jamais le graphe de dépendances (ADR 0018). Le téléchargement est vérifié
# par la base de sommes de Go, active par défaut, à une version exacte — ce que
# `apps/api/tests/test_supply_chain.py` exige. `GOTOOLCHAIN=local`, défaut de l'image : un module
# qui exigerait un Go plus récent fait échouer le build au lieu d'en télécharger un autre. Les
# caches de Go — modules et objets de compilation — sont montés hors du layer, qui garde les
# binaires sans eux : le cache de la CI (`mode=max`) n'en grossit pas. Un étage par outil : monter
# l'un ne recompile pas l'autre, et BuildKit compile les deux en parallèle.
FROM golang:1.27.3-alpine@sha256:f2c872bcee949b7be9c490efd02b48a8a2fbf947cdf533f1c58525ec9d8170fd AS go
ENV CGO_ENABLED=0

# `age`, comme son workflow de release (`.github/workflows/build.yml`) : `-trimpath`, sans
# `-ldflags`. Ses deux commandes seulement — `cmd/...` installerait aussi `age-inspect` et
# `age-plugin-batchpass`, que l'image ne demande pas.
FROM go AS age
RUN --mount=type=cache,target=/root/.cache/go-build --mount=type=cache,target=/go/pkg/mod \
    go install -trimpath filippo.io/age/cmd/age@v1.3.2 filippo.io/age/cmd/age-keygen@v1.3.2

# `rclone`, comme son image officielle, que la cible par défaut de son `Makefile` compile : `-s`,
# sans étiquette, et la version de la source — le suffixe vidé, `fs.Version` vaut `fs.VersionTag`,
# et `rclone version` n'annonce pas de `-DEV`. `-trimpath`, comme ses archives de release
# (`bin/cross-compile.go`).
FROM go AS rclone
RUN --mount=type=cache,target=/root/.cache/go-build --mount=type=cache,target=/go/pkg/mod \
    go install -trimpath -ldflags "-s -X github.com/rclone/rclone/fs.VersionSuffix=" \
    github.com/rclone/rclone@v1.75.2


# `paquets` : l'étage que la CI reconstruit à chaque build, sans son cache (`ci.yml`) — les paquets
# d'Alpine suivent ses dépôts, pas un fichier du dépôt qu'une clé de cache suivrait.
FROM base AS paquets

# `pg_dump` de la majeure du serveur, 16 (décision 2) : une archive écrite par un `pg_dump` plus
# récent n'est pas garantie lisible par un serveur plus ancien — un test tient l'égalité. Les
# paquets ne sont pas épinglés à une version : Alpine retire de ses dépôts celles qu'il remplace,
# et la reconstruction suivante échouerait. L'empreinte de l'image de base et le scan tiennent ce
# qui est installé.
RUN apk add --no-cache postgresql16-client curl

# `age-keygen` sert aux tests, qui engendrent une paire à chaque lancement ; celle de la production
# s'engendre hors du VPS, où la clé privée ne vient jamais (ADR 0007, point 2).
COPY --from=age /go/bin/age /go/bin/age-keygen /usr/local/bin/
COPY --from=rclone /go/bin/rclone /usr/local/bin/

# `supercronic` n'a pas d'image officielle : le fichier de sa release, à la somme SHA-256
# épinglée, que BuildKit vérifie avant de le copier (ADR 0018). `linux/amd64` seulement,
# l'architecture du VPS, de la CI et du poste.
ADD --checksum=sha256:cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123 --chmod=755 \
    https://github.com/aptible/supercronic/releases/download/v0.2.51/supercronic-linux-amd64 \
    /usr/local/bin/supercronic

COPY --chmod=755 infra/backup/backup.sh infra/backup/retention.sh /usr/local/bin/
COPY infra/backup/crontab /etc/crontab

# Utilisateur système, sans mot de passe ni dossier personnel : la chaîne n'écrit que ses fichiers
# de travail, dans `/tmp`.
RUN adduser -S -D -H backup
USER backup

# `supercronic` est le processus du conteneur : s'il sort, le conteneur boucle et sa sonde ne répond
# plus (décision 10). Il transmet l'environnement du conteneur à la tâche (son README).
CMD ["supercronic", "/etc/crontab"]
