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

.PHONY: install test lint format format-check typecheck
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

# `--omit=dev` borne la porte à ce qui est livré au navigateur. L'arbre de développement porte
# aujourd'hui 7 avis `high` sans correctif publié, tous dans les invites interactives de
# `@lhci/cli` (`inquirer` → `external-editor` → `tmp`), qui ne s'exécutent jamais en CI : une
# porte bloquante sur l'arbre complet serait rouge dès le premier run et sans voie de sortie.
web-audit:
	$(WEB_NPM) audit --audit-level=high --omit=dev
