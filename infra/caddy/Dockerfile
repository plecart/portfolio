# Image `caddy` : le front compilé, servi en statique (ADR 0008), son Caddyfile de production, et
# rien d'autre que son image de base (ADR 0014).
#
# Contexte de build : la racine du dépôt, comme pour `api`. Le `.dockerignore` n'y laisse entrer
# du front que sa compilation, `apps/web/dist`, que `make build` produit s'il manque.

# Épinglée par empreinte, derrière son étiquette la plus précise, `FROM` en colonne 0 : Dependabot
# (`.github/dependabot.yml`) propose chaque nouvelle version, étiquette et empreinte ensemble.
FROM caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f

COPY apps/web/dist /usr/share/caddy

# À la place de celui de l'image, au chemin que sa commande lit.
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
