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
# trouve, et ajouter un dossier suffit. Chacune a ses cibles, `build-<service>`, `scan-<service>`
# et, pour la publication, `push-<service>` et `prune-<service>`.
IMAGES := $(patsubst infra/%/Dockerfile,%,$(wildcard infra/*/Dockerfile))
IMAGE_BUILDS := $(addprefix build-,$(IMAGES))
IMAGE_SCANS := $(addprefix scan-,$(IMAGES))
IMAGE_PUSHES := $(addprefix push-,$(IMAGES))
IMAGE_PRUNES := $(addprefix prune-,$(IMAGES))

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

# L'étiquette qu'une image publiée porte à côté de `latest` : le SHA complet du commit, que la CI
# passe (ADR 0014). Vide sur un poste, qui ne publie pas.
IMAGE_TAG ?=

# `--env-file` n'est pas une commodité : c'est la seule façon d'alimenter l'interpolation
# `${...}` de `compose.dev.yml`. Le `env_file:` du service, lui, ne remplit que l'environnement
# du conteneur. Nommé une fois ici pour qu'aucun appel ne puisse l'oublier.
COMPOSE := docker compose --env-file infra/dev.env -f infra/compose.dev.yml

# Le Compose de production, avec le modèle de son `.env` : le vrai n'existe que sur le VPS. Ses
# valeurs factices ne servent qu'à résoudre le fichier (ADR 0012, brief de #16).
COMPOSE_PROD := docker compose --env-file infra/prod.env.example -f infra/compose.yml

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

# La rétention des images publiées (ADR 0014) : chaque paquet garde ses `KEEP_VERSIONS` versions
# les plus récentes. Le filtre `jq` rend les autres, de la plus ancienne à la plus récente.
#
# Toute version compte, étiquetée ou non : un job relancé sur un commit dont le build ne se
# reproduit pas à l'octet déplace ses étiquettes et laisse une version orpheline, que la rétention
# doit aussi emporter. Tenable parce que chaque publication est une image à un seul manifeste —
# ni attestation ni plateforme multiple (décision 7 du brief de #15).
# ponytail: un index multi-plateforme ferait supprimer ses manifestes par plateforme, versions
# sans étiquette — ne compter alors que les versions étiquetées.
KEEP_VERSIONS := 3
STALE_VERSIONS := sort_by(.created_at) | .[:-$(KEEP_VERSIONS)][].id

# Les versions d'un paquet dans l'API de GitHub : `ghcr.io/<propriétaire>/<nom>` y devient
# `users/<propriétaire>/packages/container/<nom>/versions`, un paquet d'utilisateur comme ceux de ce
# dépôt. Développées dans la recette, où `$*` nomme le service.
PACKAGE = $(patsubst ghcr.io/%,%,$(IMAGE_PREFIX)$*)
PACKAGE_VERSIONS = users/$(dir $(PACKAGE))packages/container/$(notdir $(PACKAGE))/versions

# `gh`, qui porte la rétention ; les tests le remplacent par un témoin.
GH ?= gh

.PHONY: install test lint format format-check typecheck openapi audit build $(IMAGE_BUILDS) compose-config dev
.PHONY: scan $(IMAGE_SCANS) image-test push $(IMAGE_PUSHES) prune $(IMAGE_PRUNES)
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

# Le schéma OpenAPI de l'API publique, versionné : le front en dérive ses types (#19). À relancer
# après tout changement du contrat — sinon le test de fraîcheur de `make test` rougit. La commande
# est celle de django-ninja ; `--api` la mène à l'instance, qu'elle chercherait sinon sous `/api/`.
# Comme toute commande `manage.py`, elle lit l'environnement du back (`.env`).
openapi:
	$(UV) run python apps/api/manage.py export_openapi_schema --api content.api.api --indent 2 \
		--output apps/api/openapi.json

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
# elle, pour que les images vérifiées en CI soient exactement celles qu'on construit sur le poste
# — celles aussi que le job `publish` reconstruit pour publier.
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

# Les tests des images que `make build` a chargées — le test de fumée de `caddy`, d'abord. Hors de
# `make test`, qui ne lit que `apps` : ils démarrent les images, donc il leur faut le front compilé.
# Sans dépendance vers `build`, pour la même raison que `scan` : la CI les lance après son build.
image-test:
	$(UV) run pytest infra/tests

# Publie chaque image que `make build` a chargée, sous `IMAGE_TAG` puis sous `latest` — l'étiquette
# que le build lui a donnée. Dans cet ordre, `latest` ne désigne jamais une image dont l'étiquette
# du commit manque au registre. Sans dépendance vers `build` ni `scan`, pour la même raison que
# `scan` envers `build` : la CI les lance en étapes distinctes, et se connecte au registre entre le
# scan et le push. Réservée à la CI, seule à détenir le jeton d'écriture.
push: $(IMAGE_PUSHES)

$(IMAGE_PUSHES): push-%:
	$(if $(IMAGE_TAG),,$(error IMAGE_TAG manque : l'étiquette du commit à publier))
	docker tag $(IMAGE_PREFIX)$* $(IMAGE_PREFIX)$*:$(IMAGE_TAG)
	docker push $(IMAGE_PREFIX)$*:$(IMAGE_TAG)
	docker push $(IMAGE_PREFIX)$*:latest

# Supprime les versions que la rétention ne garde pas. Lancée par la CI après `make push`, avec le
# jeton du workflow dans `GH_TOKEN` : le dépôt dont le workflow a publié un paquet en reçoit le rôle
# `admin`, qui suffit à supprimer (docs GitHub, « Deleting and restoring a package » — en
# préversion publique au 2026-09-30).
#
# La lecture d'abord, puis une suppression par version, chacune vérifiée : dans un tube ou une
# boucle nue, l'échec de `gh` se perdrait et la CI resterait verte. `per_page=100` et non
# `--paginate`, qui appliquerait le filtre page par page : sous la rétention, un paquet ne compte
# jamais autant de versions.
prune: $(IMAGE_PRUNES)

$(IMAGE_PRUNES): prune-%:
	$(if $(filter ghcr.io/%,$(IMAGE_PREFIX)),,$(error IMAGE_PREFIX ne nomme pas un paquet GHCR))
	ids=$$($(GH) api '$(PACKAGE_VERSIONS)?per_page=100' --jq '$(STALE_VERSIONS)') && \
	for id in $$ids; do $(GH) api --method DELETE $(PACKAGE_VERSIONS)/$$id || exit 1; done

# Vérifie que les deux fichiers Compose se résolvent — interpolation comprise : une variable de
# production que son modèle ne déclare pas fait échouer la cible. Appelée par le job `infra` de la
# CI, qui crée un `.env` depuis `.env.example` au préalable : Compose exige que la cible d'un
# `env_file` existe, même pour une simple résolution, et le fichier de développement en cite un.
compose-config:
	$(COMPOSE) config --quiet
	$(COMPOSE_PROD) config --quiet

# La restauration (`make restore`, brief de #24) : le fichier de la clé privée `age`, tiré du
# gestionnaire de mots de passe ; le nombre de projets publiés attendu au moins après la
# restauration (décision 7, #27 le passe à 1) ; `scp` et `ssh`, que les tests remplacent par des
# témoins ; où le script attend sur le VPS — hors de `/srv/portfolio`, qui ne porte que
# `compose.yml` et `.env` (#16 lot 3).
AGE_IDENTITY ?= age.key
RESTORE_MIN_PROJECTS ?= 0
SCP ?= scp
SSH ?= ssh
RESTORE_REMOTE := /root/portfolio-restore.sh

.PHONY: restore

# Restaure une sauvegarde dans la base de production, depuis le poste (brief de #24, décision 1) :
#   make restore HOST=<adresse du VPS> BACKUP=<derniere|AAAAMMJJTHHMMSSZ>
# La copie de travail de `infra/restore.sh` copiée sur le VPS, puis lancée dans le dossier de la
# pile, la clé privée sur l'entrée standard — jamais en argument. En `root`, comme l'amorçage :
# `deploy` n'admet que la clé de la CI. `HOST` et `BACKUP` se donnent sur la ligne de commande,
# sans défaut — restaurer détruit — : une variable homonyme de l'environnement ne compte pas. Le
# script vérifie le format de `BACKUP` ; la cible borne les caractères de `HOST`, qui entre dans la
# commande du poste, et ceux de `BACKUP` et du seuil, qui entrent dans celle du shell du VPS. Le
# chemin de la clé est cité : un dossier du poste peut porter une espace. Procédure :
# `infra/RUNBOOK.md`.
restore:
	$(if $(and $(filter command line,$(origin HOST)),$(HOST)),,$(error HOST manque : l'adresse du VPS))
	$(if $(and $(filter command line,$(origin BACKUP)),$(BACKUP)),,$(error BACKUP manque : derniere, ou l'horodatage <AAAAMMJJ>T<HHMMSS>Z))
	@test -r '$(AGE_IDENTITY)' || { \
		echo "AGE_IDENTITY : $(AGE_IDENTITY) introuvable, le fichier de la clé privée age" >&2; exit 1; }
	@case '$(HOST)' in *[!A-Za-z0-9.-]*) \
		echo "HOST : une adresse IPv4 ou un nom d'hôte seulement" >&2; exit 1 ;; esac
	@case '$(BACKUP)$(RESTORE_MIN_PROJECTS)' in *[!A-Za-z0-9]*) \
		echo "BACKUP et RESTORE_MIN_PROJECTS : lettres et chiffres seulement" >&2; exit 1 ;; esac
	$(SCP) infra/restore.sh root@$(HOST):$(RESTORE_REMOTE)
	$(SSH) root@$(HOST) 'cd /srv/portfolio && RESTORE_MIN_PROJECTS=$(RESTORE_MIN_PROJECTS) sh $(RESTORE_REMOTE) $(BACKUP)' < '$(AGE_IDENTITY)'

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
# l'arbre est propre : les `overrides` du manifeste écartent les avis qu'`@lhci/cli` traîne, en
# traitant leurs 4 racines (`docs/frontend-outillage.md` §2.4).
#
# Seuil `high` et non le défaut : sous ce niveau, les avis d'un arbre de développement de 650
# paquets rougissent la porte sans que rien ne soit livré — et une porte qu'on apprend à ignorer
# ne protège plus rien.
web-audit:
	$(WEB_NPM) audit --audit-level=high
