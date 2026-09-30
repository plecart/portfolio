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
WEB_INDEX := $(WEB)/dist/index.html

# `cd` plutôt que `npm --prefix` : mesuré, `--prefix` ne déplace pas le répertoire courant, et
# les scripts du front résolvent leurs chemins depuis celui-ci. Le préfixe est nommé une fois :
# le jour où la façon d'entrer dans le front change, elle change ici seulement.
WEB_NPM := cd $(WEB) && $(NPM)

# Une image par dossier `infra/<service>/` qui porte un `Dockerfile` (ADR 0014) : `make build` les
# trouve, et ajouter un dossier suffit. Chacune a ses cibles, `build-<service>` et `scan-<service>`.
IMAGES := $(patsubst infra/%/Dockerfile,%,$(wildcard infra/*/Dockerfile))
IMAGE_BUILDS := $(addprefix build-,$(IMAGES))
IMAGE_SCANS := $(addprefix scan-,$(IMAGES))

# Le préfixe du nom des images — `portfolio-api`, `portfolio-caddy` —, que la CI surcharge pour
# publier sous le nom GHCR sans redéfinir la commande.
#
# L'affectation **avant** l'export, et pas l'inverse : un `export` nu définit la variable à vide,
# après quoi `?=` n'assigne plus rien. Mesuré sur l'ancien nom d'image, qui partait alors sans
# étiquette (`-t  .`).
#
# Exportée pour que l'environnement du processus l'emporte sur `infra/dev.env`, où Compose lit
# aussi ses variables d'interpolation : un préfixe que ce fichier nommerait donnerait à `make dev`
# une autre image `api` que celle de `make build` (mesuré à la relecture de la PR #53).
IMAGE_PREFIX ?= portfolio-
export IMAGE_PREFIX

# Drapeaux supplémentaires de la commande de build, vides sur un poste. La CI y passe ses
# options de cache : elle règle ainsi *comment* le build s'exécute sans redéfinir *ce qu'il*
# construit — les cibles `build-<service>` restent la seule définition, appelée à l'identique ici
# et sur GitHub Actions. Développés dans la recette, ils peuvent citer le service par `$*`.
DOCKER_BUILD_FLAGS ?=

# `--env-file` n'est pas une commodité : c'est la seule façon d'alimenter l'interpolation
# `${...}` de `compose.dev.yml`. Le `env_file:` du service, lui, ne remplit que l'environnement
# du conteneur. Nommé une fois ici pour qu'aucun appel ne puisse l'oublier.
COMPOSE := docker compose --env-file infra/dev.env -f infra/compose.dev.yml

# Trivy, dans son image officielle plutôt qu'installé : même commande sur le poste et en CI, et une
# seule épingle (ADR 0014). Étiquette et empreinte, comme les images de base. Dependabot ne lit pas
# cette épingle ; elle se monte à la main : nouvelle étiquette, signature vérifiée par `cosign
# verify`, empreinte lue sur la ligne « Digest » de `docker buildx imagetools inspect` — la
# procédure est dans `CONTRIBUTING.md`. `:=` et non `?=` : l'environnement ne peut pas la remplacer.
TRIVY_IMAGE := ghcr.io/aquasecurity/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969

# Le conteneur de Trivy reçoit le socket du moteur, pour lire les images que `make build` y a
# chargées ; un volume pour sa base de vulnérabilités, téléchargée une fois pour toutes les images ;
# et les exceptions datées, en lecture seule, à la racine — son répertoire de travail.
TRIVY := docker run --rm \
	-v /var/run/docker.sock:/var/run/docker.sock \
	-v portfolio-trivy-cache:/root/.cache/ \
	-v "$(CURDIR)/.trivyignore.yaml:/.trivyignore.yaml:ro" \
	$(TRIVY_IMAGE)

# La politique de scan (ADR 0014) : toute vulnérabilité HIGH ou CRITICAL bloque, corrigeable ou
# non — jamais `--ignore-unfixed` —, comme une image de base en fin de vie ; seules passent les
# exceptions datées de `.trivyignore.yaml`, que `--show-suppressed` liste dans le rapport : le
# journal de CI dit lesquelles étaient en vigueur. `--image-src docker` : Trivy ne lit que le moteur
# local, et ne tire pas d'un registre une image qui porterait le même nom.
SCAN_FLAGS := --image-src docker --severity HIGH,CRITICAL --exit-code 1 --exit-on-eol 1 \
	--ignorefile .trivyignore.yaml --show-suppressed

.PHONY: install test lint format format-check typecheck audit build $(IMAGE_BUILDS) compose-config dev
.PHONY: scan $(IMAGE_SCANS)
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

# Contexte de build : la racine du dépôt, pour toutes les images — l'espace de travail `uv` et son
# verrou y vivent, et le front compilé. La CI appelle cette cible plutôt qu'un `docker build` à
# elle, pour que les images vérifiées en CI soient exactement celles qu'on construit sur le poste.
# #15 réutilise ce build pour publier.
#
# `docker buildx build` et non `docker build` : le second garde **toujours** le builder par
# défaut du moteur, même après un `docker buildx use`, et la documentation Docker vise
# nommément les scripts `make` qui s'y heurtent. En CI, où le builder sélectionné est le seul
# capable d'exporter un cache, `docker build` échoue sur « Cache export is not supported for
# the docker driver ». Mesuré.
#
# Une règle à motif statique, et non implicite : `.PHONY` écarte les règles implicites de la
# recherche, et une cible `build-<service>` doit rester phony.
build: $(IMAGE_BUILDS)

$(IMAGE_BUILDS): build-%: $(WEB_INDEX)
	docker buildx build $(DOCKER_BUILD_FLAGS) -f infra/$*/Dockerfile -t $(IMAGE_PREFIX)$* .

# Scanne les images que `make build` a construites, sous le même nom. Sans dépendance vers
# `build` : en CI, `make scan` reconstruirait chaque image pour rien — sans `--load`, le pilote
# conteneurisé construit et jette.
#
# `MSYS_NO_PATHCONV` : lancé depuis Git Bash, `make` passe ses recettes à un shell qui réécrit en
# chemins Windows les arguments commençant par `/` — le socket du moteur devenait
# `C:\Program Files\Git\var\run\docker.sock` (mesuré). Sans effet ailleurs.
scan: $(IMAGE_SCANS)

$(IMAGE_SCANS): export MSYS_NO_PATHCONV := 1
$(IMAGE_SCANS): scan-%:
	$(TRIVY) image $(SCAN_FLAGS) $(IMAGE_PREFIX)$*

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
