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

# Le front compilé, que les images copient depuis le contexte de build (ADR 0014). `index.html`
# en est le témoin : absent, `build` et `dev` compilent le front ; présent, ils le reprennent tel
# quel — `make web-build` le recompile à la demande.
WEB_INDEX = $(WEB)/dist/index.html

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

# Drapeaux supplémentaires de la commande de build, vides sur un poste. La CI y passe ses
# options de cache : elle règle ainsi *comment* le build s'exécute sans redéfinir *ce qu'il*
# construit — la cible `build` reste la seule définition, appelée à l'identique ici et sur
# GitHub Actions.
DOCKER_BUILD_FLAGS ?=

# `--env-file` n'est pas une commodité : c'est la seule façon d'alimenter l'interpolation
# `${...}` de `compose.dev.yml`. Le `env_file:` du service, lui, ne remplit que l'environnement
# du conteneur. Nommé une fois ici pour qu'aucun appel ne puisse l'oublier.
COMPOSE := docker compose --env-file infra/dev.env -f infra/compose.dev.yml

.PHONY: install test lint format format-check typecheck audit build compose-config dev
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

# Audite l'environnement que `uv sync` a installé, dépendances de développement comprises — même
# raison que `web-audit` : un outil de build compromis écrit dans ce qu'on livre. Le seuil et sa
# raison sont dans le workflow, à l'étape qui appelle cette cible.
#
# La porte lit les exceptions datées, puis lance `pip-audit` avec les options ci-dessous.
# `--skip-editable` : les membres de l'espace de travail (`api`) sont installés en mode éditable
# et n'existent pas sur PyPI — les y chercher n'audite rien. Pas de `--strict`, qui compte ce
# membre sauté comme un échec de collecte (mesuré, sortie 1 sur un arbre sans aucun avis).
audit:
	$(UV) run python infra/ci/pip_audit_gate.py \
		--exceptions infra/ci/pip-audit-exceptions.toml --skip-editable

# Contexte de build : la racine du dépôt, où vivent l'espace de travail `uv` et son verrou.
# La CI appelle cette cible plutôt qu'un `docker build` à elle, pour que l'image vérifiée en
# CI soit exactement celle qu'on construit sur le poste. #15 réutilise ce build pour publier.
#
# `docker buildx build` et non `docker build` : le second garde **toujours** le builder par
# défaut du moteur, même après un `docker buildx use`, et la documentation Docker vise
# nommément les scripts `make` qui s'y heurtent. En CI, où le builder sélectionné est le seul
# capable d'exporter un cache, `docker build` échoue sur « Cache export is not supported for
# the docker driver ». Mesuré.
build: $(WEB_INDEX)
	docker buildx build $(DOCKER_BUILD_FLAGS) -f infra/api/Dockerfile -t $(API_IMAGE) .

# Vérifie que le Compose de développement se résout — interpolation comprise. Appelée par le
# job `infra` de la CI, qui crée un `.env` depuis `.env.example` au préalable : Compose exige
# que la cible d'un `env_file` existe, même pour une simple résolution.
compose-config:
	$(COMPOSE) config --quiet

# Démarre la pile de développement. `--build` : l'image est reconstruite si le Dockerfile ou
# une dépendance a changé, pour qu'un `git pull` n'exige pas de s'en souvenir.
dev: $(WEB_INDEX)
	$(COMPOSE) up --build

$(WEB_INDEX):
	$(MAKE) web-build

# Cibles du front. Elles restent séparées des cibles back et d'infrastructure plutôt que fondues
# dedans : les trois piles n'ont pas les mêmes prérequis — `uv`, Node, Docker — et la CI en fait
# trois jobs distincts, de sorte qu'un rouge de l'une ne masque pas un rouge d'une autre.

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
