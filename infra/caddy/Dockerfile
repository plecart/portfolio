# Image `caddy` : le front compilé, servi en statique (ADR 0008), son Caddyfile de production, et
# son image de base (ADR 0014), dont seul le binaire `caddy` est remplacé : le projet le compile
# avec le Go de l'image `golang` épinglée ci-dessous, sa release embarquant un Go en retard sur ses
# correctifs (ADR 0018).
#
# Contexte de build : la racine du dépôt, comme pour `api`. Le `.dockerignore` n'y laisse entrer
# du front que sa compilation, `apps/web/dist`, que `make build` produit s'il manque.
#
# Qui suit quoi : Dependabot (`.github/dependabot.yml`) propose chaque nouvelle version de `caddy`
# et de `golang` — une montée de Go recompile `caddy` ; la version compilée suit à la main
# l'étiquette de l'image de base, et `infra/tests/test_caddy_image.py` exige leur égalité
# (`CONTRIBUTING.md`).

# Épinglées étiquette x.y.z et empreinte, `FROM` en colonne 0 : Dependabot propose chaque nouvelle
# version, étiquette et empreinte ensemble.
#
# Le compilateur : sans cgo, comme la release ; `GOTOOLCHAIN=local`, défaut de l'image — un module
# qui exigerait un Go plus récent fait échouer le build au lieu d'en télécharger un autre. Le module
# principal vit dans `/src` : Go ignore un `go.mod` posé dans `/go`, le `GOPATH` de l'image
# (mesuré).
FROM golang:1.27.3-alpine@sha256:f2c872bcee949b7be9c490efd02b48a8a2fbf947cdf533f1c58525ec9d8170fd AS go
ENV CGO_ENABLED=0
WORKDIR /src

# `caddy`, comme sa release (`.goreleaser.yml`) : une **dépendance** d'un module principal `caddy`,
# compilée avec le `main.go` de son `cmd/caddy` — compilé en module principal, il répondrait
# `unknown` à `caddy version` (mesuré). Ce `main.go` est copié du module, téléchargé à la version
# de l'exigence et dont `go list` lit le dossier : la version ne s'écrit qu'une fois. `go mod tidy`
# résout les modules que fixe la release : on change le compilateur, jamais le graphe de
# dépendances (ADR 0018). Le téléchargement est vérifié par la base de sommes de Go, active par
# défaut, à une version exacte — ce que `apps/api/tests/test_supply_chain.py` exige. Les caches de
# Go sont montés hors du layer, qui ne garde que le binaire et son module principal.
RUN --mount=type=cache,target=/root/.cache/go-build --mount=type=cache,target=/go/pkg/mod \
    go mod init caddy \
    && go mod edit -require=github.com/caddyserver/caddy/v2@v2.11.7 \
    && go mod download github.com/caddyserver/caddy/v2 \
    && cp "$(go list -m -f '{{.Dir}}' github.com/caddyserver/caddy/v2)/cmd/caddy/main.go" . \
    && go mod tidy \
    && go build -trimpath -mod=readonly -ldflags "-s -w" -tags nobadger,nomysql,nopgx \
        -o /go/bin/caddy


FROM caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f

# `curl` vient de l'image de base et rien ne l'appelle : la sonde de production appelle `wget`
# (busybox), et le binaire `caddy`, statique, ne charge aucune bibliothèque. Retiré avec ce qu'il
# tire — `libcurl`, `brotli-libs`… —, il n'apporte plus ses avis au scan. `--no-network` : un
# retrait n'a pas besoin des dépôts, dont `apk` laisserait sinon les index dans la couche (3 Mo,
# mesuré) ; la couche ne dépend donc que de l'image de base, et son cache ne périme rien.
RUN apk del --no-network curl

# À la place de celui de l'image. Le sien porte `cap_net_bind_service=ep`, que la copie perd :
# l'image tourne en root, qui ouvre le port 80 sans elle.
COPY --from=go /go/bin/caddy /usr/bin/caddy

COPY apps/web/dist /usr/share/caddy

# À la place de celui de l'image, au chemin que sa commande lit.
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
