# Image `caddy` : le front compilé, servi en statique (ADR 0008), et rien d'autre que son image de
# base (ADR 0014). Le Caddyfile de production — routes vers `api`, en-têtes de cache — arrive avec
# #16 ; d'ici là, le Caddyfile par défaut de l'image sert `/usr/share/caddy`.
#
# Contexte de build : la racine du dépôt, comme pour `api`. Le `.dockerignore` n'y laisse entrer
# du front que sa compilation, `apps/web/dist`, que `make build` produit s'il manque.

# Épinglée par empreinte, derrière son étiquette la plus précise, `FROM` en colonne 0 : Dependabot
# (`.github/dependabot.yml`) propose chaque nouvelle version, étiquette et empreinte ensemble.
FROM caddy:2.11.4-alpine@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b

COPY apps/web/dist /usr/share/caddy
