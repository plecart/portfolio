# Fichier de commandes du projet.
#
# Source unique des commandes : la section « Commandes du projet » de
# `.claude/pipeline.config.md` reprend ces cibles, et la CI les appelle. Une commande définie
# ici est donc la même pour un humain, pour les skills et pour GitHub Actions.
#
# Aucune version de runtime n'apparaît ici : `.python-version` l'épingle, `uv` le lit, et la CI
# ne fait que provisionner `uv`. Un second endroit qui déclarerait « 3.12 » finirait par mentir.

UV ?= uv
NPM ?= npm
WEB := apps/web

# `cd` plutôt que `npm --prefix` : mesuré, `--prefix` ne déplace pas le répertoire courant, et
# les scripts du front résolvent leurs chemins depuis celui-ci. Le préfixe est nommé une fois :
# le jour où la façon d'entrer dans le front change, elle change ici seulement.
WEB_NPM := cd $(WEB) && $(NPM)

# L'affectation **avant** l'export, et pas l'inverse : un `export` nu définit la variable à vide,
# après quoi `?=` n'assigne plus rien et l'image part sans étiquette (`-t  .`). Mesuré.
#
# Exportée parce que l'interpolation de Compose lit l'environnement du processus : c'est ce qui
# fait que `make dev` et `make build` construisent une seule et même image.
API_IMAGE ?= portfolio-api
export API_IMAGE

# Drapeaux supplémentaires de `docker build`, vides sur un poste. La CI y passe ses options de
# cache : elle règle ainsi *comment* le build s'exécute sans redéfinir *ce qu'il* construit —
# la cible `build` reste la seule définition, appelée à l'identique ici et sur GitHub Actions.
DOCKER_BUILD_FLAGS ?=

# `--env-file` n'est pas une commodité : c'est la seule façon d'alimenter l'interpolation
# `${...}` de `compose.dev.yml`. Le `env_file:` du service, lui, ne remplit que l'environnement
# du conteneur. Nommé une fois ici pour qu'aucun appel ne puisse l'oublier.
COMPOSE := docker compose --env-file infra/dev.env -f infra/compose.dev.yml

.PHONY: install test lint format format-check typecheck build compose-config dev
.PHONY: web-install web-browsers web-lint web-typecheck web-test web-build web-e2e web-lighthouse web-audit

install:
	$(UV) sync

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

format-check:
	$(UV) run ruff format --check .

typecheck:
	$(UV) run pyright

# Contexte de build : la racine du dépôt, où vivent l'espace de travail `uv` et son verrou.
# La CI appelle cette cible plutôt qu'un `docker build` à elle, pour que l'image vérifiée en
# CI soit exactement celle qu'on construit sur le poste. #15 réutilise ce build pour publier.
build:
	docker build $(DOCKER_BUILD_FLAGS) -f infra/api/Dockerfile -t $(API_IMAGE) .

# Vérifie que le Compose de développement se résout — interpolation comprise. Appelée par le
# job `infra` de la CI, qui crée un `.env` depuis `.env.example` au préalable : Compose exige
# que la cible d'un `env_file` existe, même pour une simple résolution.
compose-config:
	$(COMPOSE) config --quiet

# Démarre la pile de développement. `--build` : l'image est reconstruite si le Dockerfile ou
# une dépendance a changé, pour qu'un `git pull` n'exige pas de s'en souvenir.
dev:
	$(COMPOSE) up --build

# Cibles du front. Elles restent séparées des cibles back plutôt que fondues dedans : les deux
# piles n'ont pas les mêmes prérequis (l'une veut `uv`, l'autre Node), et la CI en fait deux jobs
# distincts, de sorte qu'un rouge du front ne masque pas un rouge du back.

web-install:
	$(WEB_NPM) ci

# Séparé de `web-install` : le téléchargement du navigateur est long, et en faire une étape
# distincte le rend lisible dans le journal de CI au lieu de le noyer dans l'installation.
# `--with-deps` installe les bibliothèques système que Chromium réclame sous Linux.
web-browsers:
	$(WEB_NPM) exec -- playwright install --with-deps chromium

web-lint:
	$(WEB_NPM) run lint

web-typecheck:
	$(WEB_NPM) run typecheck

web-test:
	$(WEB_NPM) test

web-build:
	$(WEB_NPM) run build

web-e2e:
	$(WEB_NPM) run test:e2e

web-lighthouse:
	$(WEB_NPM) run lighthouse

# Porte sur l'**arbre entier**, dépendances de développement comprises : une chaîne de build
# compromise sait écrire dans `dist/`, et `--omit=dev` ne la verrait pas. Tenable parce que
# l'arbre est propre : les `overrides` du manifeste écartent les 10 avis qu'`@lhci/cli` traînait,
# en traitant leurs 3 racines (`docs/frontend-outillage.md` §2.4).
#
# Seuil `high` et non le défaut : sous ce niveau, les avis d'un arbre de développement de 650
# paquets rougissent la porte sans que rien ne soit livré — et une porte qu'on apprend à ignorer
# ne protège plus rien.
web-audit:
	$(WEB_NPM) audit --audit-level=high
