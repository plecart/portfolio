# La pipeline de développement

Ce dépôt est un portfolio personnel : il n'accepte pas de contributions extérieures.
Ce document décrit comment il est développé, par un humain et des agents IA.

Le développement suit une pipeline pilotée par les issues. **La source de vérité du process n'est
pas ce fichier** : c'est le skill `cycle-pr` (déroulé pas à pas) et les règles permanentes dans
[.claude/rules/](.claude/rules/). Ce document n'en donne que la carte.

Chaque étape ci-dessous s'invoque par le nom de son skill (`/triage`, `/cycle-pr`…) — voir
[.claude/skills/](.claude/skills/).

## Démarrer en local

Le dépôt porte trois piles, provisionnées séparément : le back (`uv`), le front (Node) et la pile
de développement (Docker). Elles n'ont pas les mêmes prérequis, et la CI les tient dans trois jobs
distincts, pour qu'un rouge du front ne masque pas un rouge de l'infra, ni l'inverse ; les deux
attendent un back vert.

**Back (`apps/api`)** — Python 3.12, épinglé par `.python-version` et lu par `uv` :

```
uv sync                     # installe l'espace de travail : racine + apps/api
cp .env.example .env        # puis renseigner SECRET_KEY, ADMIN_USERNAME et ADMIN_PASSWORD
uv run pre-commit install   # branche les hooks — depuis ce clone, jamais depuis un worktree :
                            # .git/hooks est partagé et fige le chemin de l'interpréteur qui l'installe
```

`make test` exige Docker : les tests qui touchent la base démarrent un Postgres jetable — l'image
du Compose de développement — par testcontainers, et échouent en le disant si Docker ne répond
pas. Ils ne lisent jamais `.env` : leur environnement est posé par
[apps/api/tests/process_environment.py](apps/api/tests/process_environment.py).

`make test-pipeline` lance à part les tests de la pipeline — skills, règles, rôles et leurs
scripts —, qui vivent dans [.claude/tests/](.claude/tests/), sans Django ni Docker : à lancer
quand un changement les concerne (« Commandes du projet » de
[.claude/pipeline.config.md](.claude/pipeline.config.md)).

**Réglage recommandé du poste.** Docker publie par défaut chaque port sur toutes les interfaces.
Pendant les tests, le Postgres jetable et Ryuk — le conteneur de nettoyage de testcontainers, qui
détient le socket Docker et n'exige aucune authentification — sont donc joignables depuis le
réseau local dès que le pare-feu laisse entrer Docker (Windows crée une règle entrante quand on
l'y autorise). Le Postgres a un mot de passe tiré au hasard ; Ryuk, rien. Pour fermer d'un coup
tous les ports publiés du poste, fixer l'adresse de liaison par défaut du démon à `127.0.0.1` —
`"ip": "127.0.0.1"` dans sa configuration (Docker Desktop : *Settings → Docker Engine*) — puis
redémarrer Docker. Vérifier ensuite qu'un `docker port <conteneur>` n'affiche plus que
`127.0.0.1`. Les tests joignent leurs conteneurs par `127.0.0.1`, et `.env.example` vise la même
adresse : sous Windows, `localhost` se résout d'abord en `::1`, où plus rien ne répondrait, et
chaque connexion attendrait son délai.

**Front (`apps/web`)** — Node, épinglé par `apps/web/.nvmrc` ; un gestionnaire de version (`nvm`,
`fnm`, `volta`…) lit ce fichier, et le champ `engines` du manifeste porte la même valeur, qu'un
test vérifie :

```
make web-install            # npm ci, à partir du verrou
make web-browsers           # Chromium pour Playwright — long, une fois par clone
```

`make web-lighthouse` est une cible de **CI seulement** : sous Windows, `chrome-launcher` échoue
en supprimant son dossier temporaire. Le détail et les autres écarts d'outillage sont dans
[docs/frontend-outillage.md](docs/frontend-outillage.md) §2.4.

**Valeurs du front.** Couleurs, ombres, durées et courbes ne s'écrivent qu'une fois, en jetons :
[apps/web/src/tokens.css](apps/web/src/tokens.css), sous les noms de la spec §2, lus par
`bg-(--paper)` ou `ease-(--ease-out)`. Ailleurs, un littéral est refusé — par ESLint dans les
classes et les styles de `apps/web/src/`, par un test dans toute autre feuille CSS —, et Tailwind
n'a plus ni couleurs, ni ombres, ni animations, ni courbes à lui, sauf le blanc par défaut de
`ring-offset-*` : un décalage d'anneau prend toujours sa couleur, `ring-offset-(--bg)`. Les
espacements n'ont pas de porte : un écart de l'échelle passe par son jeton `--s-1` à `--s-7` ;
une dimension propre à un objet (56, 36, 22, 76 px…) s'écrit telle quelle et cite son § de spec.
Formes couvertes et hors portée :
[apps/web/tests/value-rule.test.ts](apps/web/tests/value-rule.test.ts).

**Chaînes du front.** Tout texte que l'interface rend ou annonce vient du catalogue
[apps/web/src/strings.ts](apps/web/src/strings.ts) : identifiants en anglais, valeurs en français,
apostrophe typographique « ’ » (spec §6.2). ESLint refuse un texte qui contient une lettre écrit en
dur dans un composant de `apps/web/src/` — enfant JSX, attribut `children` compris, ou attribut
annoncé (`aria-label`, `title`, `alt`…). Il ne lit ni une variable, ni une expression, ni une
décomposition (`{...props}`), ni le HTML de `dangerouslySetInnerHTML`, ni un texte produit par CSS
(`content`), ni le bloc d'aperçu d'`index.html`. Formes couvertes et hors portée, dénombrées :
[apps/web/tests/string-rule.test.ts](apps/web/tests/string-rule.test.ts).

**La pile de développement (`infra/`)** — Postgres, Redis et `api` en conteneurs sur un réseau
privé. Demande Docker, et le front installé (`make web-install`) : l'image `api` copie son
`index.html` compilé (ADR 0014). Les ports 8000, 5432 et 6379 sont publiés sur `127.0.0.1`
seulement.

```
make dev                    # compile le front s'il manque ou s'il est périmé, construit
                            # l'image `api` si besoin, puis démarre la pile
```

`make dev` plutôt qu'un `docker compose` direct : la cible passe `--env-file infra/dev.env`, sans
quoi les valeurs interpolées du fichier Compose seraient vides. Le `.env` de la racine doit
exister — Compose refuse de résoudre un `env_file` absent, avant même de démarrer quoi que ce
soit. `Ctrl-C` arrête la pile ; les données Postgres survivent dans un volume nommé.

**Volume Postgres créé sous Debian 12.** L'image Postgres est passée de Debian 12 à Debian 13
(brief de #16, décision 5) : une base créée avant avertit à chaque connexion d'un écart de version
de collation (bibliothèque C 2.36, puis 2.41). À faire une fois, la pile démarrée — mesuré,
l'avertissement disparaît —, ou repartir d'un volume neuf :

```
docker compose --env-file infra/dev.env -f infra/compose.dev.yml exec postgres psql -U portfolio -d portfolio -c "REINDEX DATABASE portfolio" -c "ALTER DATABASE portfolio REFRESH COLLATION VERSION"
```

Trois fichiers d'environnement, qui ne se remplacent pas :

| Fichier | Commité | Lu par | Contient |
|---|---|---|---|
| `.env` | non | la classe `Env` du back | les variables de `Env`, et elles seules |
| `infra/dev.env` | oui | Compose, pour l'interpolation `${…}` | identifiants Postgres de développement et ports publiés, aucune valeur secrète |
| `infra/prod.env.example` | oui | `make compose-config`, qui résout `infra/compose.yml` | le modèle du `.env` du VPS : chaque variable que le Compose de production interpole, valeurs factices |

Le refus d'une clé inconnue vaut pour le **fichier**, donc sur le poste (`uv run manage.py`,
`make test`). Dans le conteneur, Compose injecte `.env` comme variables d'environnement et
`/app/.env` n'existe pas : une clé inconnue y est ignorée, comme n'importe quelle variable du
système. La séparation en deux fichiers ne repose donc pas sur ce garde-fou — elle repose sur le
fait que les variables de Compose ne sont pas des variables du back, et c'est
[apps/api/tests/test_env.py](apps/api/tests/test_env.py) qui tient la frontière.

Le code de `apps/api` est monté dans le conteneur : une modification sur le poste recharge `api`.
Les migrations, puis le compte de l'admin, s'exécutent à chaque démarrage. Les tests et les outils
de qualité restent sur l'hôte (`make test`, `make lint`) — le conteneur fait tourner
l'application, il ne la vérifie pas.

**Regarder l'admin.** Le compte unique de l'admin vient de `ADMIN_USERNAME` et `ADMIN_PASSWORD`,
dans `.env` : `api` le crée à son démarrage, et le met à jour si le mot de passe a changé
(`manage.py ensure_superuser`). Vides, ou un mot de passe neuf refusé par les validateurs de
Django, le démarrage d'`api` échoue, comme sans `SECRET_KEY` ; son journal dit pourquoi, sans
citer le mot de passe :

```
docker compose --env-file infra/dev.env -f infra/compose.dev.yml logs api
```

Il échoue aussi sur une base qui porte un autre compte d'admin, superutilisateur ou staff — celui
d'un ancien `createsuperuser`, sous un autre nom qu'`ADMIN_USERNAME` : l'admin n'en a qu'un. Mets
`ADMIN_USERNAME` à son nom, ou renomme le compte, ou supprime-le, dans le shell d'un conteneur
jetable d'`api` qui ne joue aucune étape de démarrage (`STARTUP_STEPS` vide) :

```
docker compose --env-file infra/dev.env -f infra/compose.dev.yml run --rm -e STARTUP_STEPS= api python manage.py shell
```

puis `User.objects.filter(username='<ancien>').update(username='<ADMIN_USERNAME>')`, ou
`.delete()` à la place d'`.update(…)` — si un autre compte porte déjà `ADMIN_USERNAME`,
`.update(…)` le refuse : supprime d'abord l'un des deux.

L'admin exige aussi un second facteur : sans lui, il ne sert que sa page de connexion. Le compte
posé, enrôle-le une fois — une application TOTP et dix codes de secours à usage unique :

```
docker compose --env-file infra/dev.env -f infra/compose.dev.yml exec api python manage.py enroll_second_factor
```

La commande imprime une seule fois l'URI `otpauth://`, à ouvrir ou coller dans une application
TOTP, puis les dix codes. La connexion se fait en un envoi : nom, mot de passe et jeton de
l'application ; un code de secours se donne après avoir choisi « Code de secours » dans le
sélecteur « Appareil OTP », que la page porte une fois le mot de passe accepté. Relancée, la
commande ré-enrôle : l'ancienne application et les anciens codes ne valent plus.

La pile démarrée, ouvrir `http://127.0.0.1:8000/admin/`.

Toutes les cibles disponibles : `Makefile`, repris dans la section « Commandes du projet » de
[.claude/pipeline.config.md](.claude/pipeline.config.md) — c'est cette section que lisent les
skills et la génération de CI.

`.env` vit à la **racine** du dépôt et n'est lu qu'en développement (cadrage §6.6). En
production, le `.env` du VPS — modèle `infra/prod.env.example` — est écrit par
`infra/bootstrap.sh` depuis les secrets, jamais édité à la main — seule sa ligne `IMAGE_TAG` est
réécrite, par le job de déploiement ; Compose le lit et donne à chaque
service ses variables, et à `api` celles de `Env`. Toute variable du back est déclarée dans
`.env.example` et lue par la classe `Env` (`apps/api/config/env.py`) — nulle part ailleurs, et
jamais en dur.

Les hooks ne lancent que `ruff` (`check --fix`, puis `format`), avec la version installée par
`uv sync` : le hook ne peut donc pas valider autre chose que la gate. Les périmètres, eux, ne
sont pas identiques — les hooks voient les fichiers Python, la CI y ajoute les carnets et les
`pyproject.toml`. Aucun des deux ne touche au Markdown, et c'est délibéré : sans la ligne
`include` de `pyproject.toml`, ruff reformaterait les blocs de code des ADR et du cadrage.
`pyright` et `pytest`
restent dans la boucle de développement et en CI, trop lents pour un hook.

**Contrat de l'API publique.** Le schéma OpenAPI de `GET /api/projets` est versionné dans
[apps/api/openapi.json](apps/api/openapi.json) : le front en dérive ses types,
[apps/web/src/api/schema.ts](apps/web/src/api/schema.ts). Après tout changement du contrat —
`apps/api/content/schemas.py`, ou l'opération de `apps/api/content/api.py`, dont la docstring est
la `description` du schéma —, régénérer les deux fichiers, `make openapi` puis `make web-openapi`,
et les committer avec le changement, dans la même PR — sinon les tests de fraîcheur rougissent,
celui de `make test` pour le schéma, celui de `make web-test` pour les types, en CI comme sur le
poste.

**Audit des dépendances.** `make audit` (Python) et `make web-audit` (front) ne sont pas des portes
de chaque PR : leur verdict change sans commit, quand un avis se publie. Le workflow
[`avis.yml`](.github/workflows/avis.yml) les joue chaque lundi sur `main`, appelé par le run
hebdomadaire [`hebdo.yml`](.github/workflows/hebdo.yml), et la CI les joue sur une PR qui touche
leurs entrées — manifestes, verrous, Dockerfiles, exceptions datées, porte de `pip-audit`,
`avis.yml` — ou ce qui décide des jobs (`Makefile`, `ci.yml`, `changed_jobs.py`)
([ADR 0019](docs/adr/0019-runs-de-ci-au-ready-et-avis-planifies.md), décision 2) ; le push sur
`main` ne fait que livrer, son scan des images avant chaque publication
([ADR 0031](docs/adr/0031-chaque-verification-de-la-ci-a-un-seul-endroit.md)). Un rouge d'avis
se corrige sur le trunk, par la voie courte — une montée de version ou une exception datée —,
jamais par d'autres pushes sur une PR. Côté Python, tout avis de sécurité connu rougit l'audit —
`pip-audit` n'expose pas de sévérité ; côté front, les avis `high` et `critical`. Un avis Python
qui ne s'applique pas au projet — ou le temps qu'un correctif paraisse — se suspend par une
entrée **datée** de [infra/ci/pip-audit-exceptions.toml](infra/ci/pip-audit-exceptions.toml),
dont le format est en tête du fichier ; la date passée, l'audit rebloque. `npm audit` n'a pas de
fichier d'exceptions : son arbre se nettoie par les `overrides` du manifeste
([docs/frontend-outillage.md](docs/frontend-outillage.md) §2.4).

**Tests des images.** `make image-test`, porte de CI sur chaque PR qui touche ce que les images
définissent ou exécutent — liste `INFRA` de [infra/ci/changed_jobs.py](infra/ci/changed_jobs.py)
([ADR 0031](docs/adr/0031-chaque-verification-de-la-ci-a-un-seul-endroit.md)) — et chaque lundi
sur `main`, dans [`hebdo.yml`](.github/workflows/hebdo.yml), démarre les images que `make build` a
chargées et les interroge ([infra/tests/](infra/tests/)) : le test de fumée du Caddyfile de
production, la chaîne de sauvegarde de l'image `backup`, jouée dans le Compose de production contre
un témoin S3 et un témoin de ping, et la restauration de ses sauvegardes par
[infra/restore.sh](infra/restore.sh), `api` compris. Il ne fait pas partie de `make test` : il lui
faut les images construites, donc le front compilé. Sur le poste, `make build` d'abord. Chaque test
démarre sa pile sous son propre nom de projet Compose — sans port publié, ou sur un port hôte que
Docker attribue — et la supprime en partant, volumes compris.

**Fumée de la pile complète.** `make smoke IMAGE_TAG=latest`, après `make build`, démarre la pile
de production depuis ces images — `caddy`, `api`, `worker`, leurs données, et un témoin S3 à la
place de R2 —, la sème d'un projet publié, puis la fait éprouver par Playwright sur Chromium
([apps/web/smoke/](apps/web/smoke/)) : la table, la fiche, les aperçus de lien, le plan du site et
`llms.txt` servis par Django, le 404 d'une adresse sans fichier, la CSP du vrai Caddyfile, le cache
contre le vrai Redis. Le navigateur y voit les origines de production, que
Playwright relaie vers la pile : aucune requête n'en sort. Des images construites sous un autre
préfixe se nomment de même : `make smoke IMAGE_PREFIX=<préfixe> IMAGE_TAG=latest`. La pile tourne
sous son propre nom de projet Compose, ses ports sur `127.0.0.1`, et se jette, verte ou rouge. En
CI, le job `fumee` la joue après chaque publication sur `main`, sur les images du commit tirées de
GHCR : rouge, il bloque le déploiement.

**Scan des images.** `make scan` scanne avec Trivy chaque image que `make build` a construite :
toute vulnérabilité HIGH ou CRITICAL bloque, corrigeable ou non, comme une image de base en fin
de vie ([ADR 0014](docs/adr/0014-ci-cd-github-actions-et-ghcr.md)). Porte d'avis comme les
audits, il tourne aux mêmes moments qu'eux, dans `avis.yml`, après son propre build des images —
et avant chaque publication. Une vulnérabilité sans correctif pour l'image s'évalue en trois
points — la place du composant dans l'image, l'atteinte du code vulnérable par ce qui tourne, les
alternatives — et se consigne en exception **datée**, à 90 jours au plus, bornée à son image, de
[.trivyignore.yaml](.trivyignore.yaml), dont le format est en tête du fichier ; la date passée, le
scan rebloque et l'évaluation se refait. Quand le correctif arrive
par une image de base reconstruite sous la même étiquette, Dependabot peut ne pas la proposer :
son empreinte se monte à la main, lue sur la ligne « Digest » de
`docker buildx imagetools inspect <image>:<étiquette>`.

Trivy tourne dans son image officielle, épinglée par étiquette et empreinte dans le `Makefile`
(`TRIVY_IMAGE`), que Dependabot ne suit pas. Pour la monter : vérifier la signature de la nouvelle
étiquette avec cosign — installé, ou lancé depuis son image `ghcr.io/sigstore/cosign/cosign` —,
puis relever son empreinte par la même commande `imagetools inspect` :

```
cosign verify ghcr.io/aquasecurity/trivy:<x.y.z> \
  --certificate-identity https://github.com/aquasecurity/trivy/.github/workflows/reusable-release.yaml@refs/tags/v<x.y.z> \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

`supercronic` entre dans l'image `backup` par le fichier `linux-amd64` de sa release, à la somme
SHA-256 épinglée dans [infra/backup/Dockerfile](infra/backup/Dockerfile) (`ADD --checksum`, que
BuildKit vérifie) : Dependabot ne le suit pas, le scan l'ouvre. Pour monter son épingle : relever
la somme que GitHub publie pour le fichier de la nouvelle version,

```
gh api repos/aptible/supercronic/releases/tags/v<x.y.z> --jq '.assets[] | select(.name == "supercronic-linux-amd64") | .digest'
```

puis la recouper par la somme SHA-1 de ses notes de release, et changer adresse et somme ensemble.
Enfin `make build-backup scan-backup`, puis `make build image-test`.

`age` — avec `age-keygen` — et `rclone` sont compilés par le projet, dans les étages `age` et
`rclone` du même Dockerfile, issus de l'étage `go`, avec le Go de l'image `golang` épinglée et à
la version exacte de leur release
([ADR 0018](docs/adr/0018-binaires-go-compiles-par-le-projet.md)). Dependabot monte l'image
`golang`, et sa PR les recompile ; leurs versions se montent à la main : changer la version du
`go install` — pour `age`, celle de ses deux commandes ensemble —, en relisant la forme de la
release, ses drapeaux pouvant changer d'une version à l'autre. Puis `make build-backup scan-backup`,
puis `make build image-test`, qui exige de chacun qu'il annonce la version épinglée.

`caddy` est compilé de même, dans l'étage `go` de [infra/caddy/Dockerfile](infra/caddy/Dockerfile),
comme dépendance d'un module principal, la forme de sa release ; l'image reste construite sur
`caddy:<x.y.z>-alpine`, dont seul le binaire est remplacé. Dependabot propose chaque nouvelle
étiquette de cette image, et chaque nouvelle image `golang` de ce Dockerfile, qui recompile `caddy`.
Le test d'égalité de `make image-test` rougit tant que la version du
`go mod edit -require=github.com/caddyserver/caddy/v2@v<x.y.z>` ne suit pas l'étiquette : la changer
dans la même PR, puis `make build-caddy scan-caddy`, puis `make build image-test`.

**Publication des images.** Rien à faire à la main : à chaque push sur `main`, sans attendre
d'autre job — la PR a joué les vérifications
([ADR 0031](docs/adr/0031-chaque-verification-de-la-ci-a-un-seul-endroit.md)) —, le job `publish`
compile le front, reconstruit les images, les scanne par `make scan`, puis les pousse sur
GHCR — `ghcr.io/plecart/portfolio-<service>`, paquets privés — sous le SHA complet du commit et
sous `latest` (`make push`) ; chaque paquet garde ses trois versions les plus récentes
(`make prune`). Le jeton du workflow suffit, aucun secret n'est à créer
([ADR 0014](docs/adr/0014-ci-cd-github-actions-et-ghcr.md)). Un déploiement vise l'étiquette du
commit : `latest` peut désigner l'avant-dernier quand deux pushes se suivent de près.

**Déploiement.** Rien à faire à la main non plus : après chaque publication sur `main`, une fois la
fumée de ses images verte (job `fumee`), le job `deploy` se connecte au VPS par SSH, y dépose
`infra/compose.yml`, fixe `IMAGE_TAG` au SHA du commit dans son `.env`, puis lance
`docker compose pull` et `up -d --wait` — il rougit si un service ne devient pas sain. Il ne
déploie que la tête de `main`, et reste sauté tant que la variable de dépôt `DEPLOY_ENABLED` ne
vaut pas `true`. Amorçage du VPS, secrets et déploiement de secours :
[infra/RUNBOOK.md](infra/RUNBOOK.md).

**Test de restauration.** Rien à faire à la main : le 1ᵉʳ de chaque mois, le workflow
[`restore.yml`](.github/workflows/restore.yml) restaure la dernière sauvegarde dans une pile
jetable du runner, par le script de `make restore`, et rougit si une étape échoue — c'est l'alerte.
Sauté lui aussi tant que `DEPLOY_ENABLED` ne vaut pas `true`. Ses secrets et son lancement à la
main : [infra/RUNBOOK.md](infra/RUNBOOK.md), « Le test mensuel ».

**Mises à jour des dépendances.** Dependabot ([.github/dependabot.yml](.github/dependabot.yml))
ouvre chaque mois, par écosystème (`uv`, npm, actions GitHub, images Docker), une PR qui
groupe versions mineures et correctifs ; chaque montée majeure arrive seule, sauf les majeures npm
que `.github/dependabot.yml` refuse — chacune avec sa raison et le test qui la tient
([docs/frontend-outillage.md](docs/frontend-outillage.md) §2.4). Ses PR sont exemptées des
métadonnées de PR et de la description en français
(`chore(deps): bump …`, [.claude/rules/taille-pr.md](.claude/rules/taille-pr.md)), passent par la
même CI et ne se mergent que sur un go humain.
Les mises à jour de sécurité ne suivent pas cette cadence : Dependabot ouvre sa PR dès qu'un avis
paraît, pour `uv`, npm et les actions GitHub — alertes et mises à jour de sécurité activées sur le
dépôt ([ADR 0019](docs/adr/0019-runs-de-ci-au-ready-et-avis-planifies.md), décision 4). Pas pour
les images Docker, que GitHub ne couvre pas : un avis sur une image se voit au scan des images
(`make scan`, ci-dessus) et se traite par une montée de version à la main.
Actions et images sont épinglées par empreinte, derrière leur version la plus précise :
Dependabot met l'une et l'autre à jour ensemble. Une nouvelle version mineure de Python (3.13)
n'est jamais proposée — elle se change à la main, dans `.python-version` puis dans l'image ; ses
versions de correctif (3.12.x) le sont.

## Le flux en une page

Chaque maillon nomme qui l'exécute ; la répartition des rôles est dans `CLAUDE.md`,
« Orchestration ».

0. **Configurer** — `init-projet`, dans une session de dialogue, écrit `.claude/pipeline.config.md`
   (dépôt, sources de vérité, labels, stack, commandes, domaines, surfaces). À relancer dès qu'une
   de ces valeurs change.
1. **Planifier** — `vers-prd` (dialogue avec le mainteneur → PRD) → `vers-issues` (dans sa
   propre session, `#issue-prd` en argument → une issue par sujet) → `triage` (relevé, puis une session
   de tri par issue, numéro en argument : machine à états, rattachement au thème, « agent brief »),
   chacun dans une session de dialogue avec le mainteneur.
2. **Interroger** — `interroge-moi`, **obligatoire**, dans une session de dialogue — la sienne,
   numéro de l'issue en argument : `ready-for-agent` et `ready-for-human` ne s'atteignent que via
   l'état `needs-interrogation`. Les décisions tranchées sont écrites dans le corps de l'issue,
   section « Décisions », que le brief reprend — pas laissées dans une conversation.
3. **Implémenter** — `cycle-pr`, porté par la session PR, qui orchestre et délègue : briefing
   pré-PR (relevés au `releveur`, cartographie à l'`executant`) → **PR draft ouverte avant tout
   code** → un `developpeur` neuf par bloc de plus de ~50 lignes : TDD red-green-refactor, cycle
   `modif → test → cleanup → test → commit` (relecture à contexte vierge à chaque bloc, par la session
   de relecture que la session PR démarre à son go) → cleanup holistique par un `developpeur`
   neuf au-delà de 3 commits ou 150 lignes → relecture à contexte vierge finale, par la même
   session → `gh pr ready` → CI → vérif de fumée → vérification d'avant-go par le `verificateur`,
   que la session PR lance quand la PR ferme une issue ou croise une branche en vol → merge.
   Plusieurs PR en parallèle : `pr-paralleles` (la session lead démarre une session par issue,
   chacune dans un worktree de l'application, et tient le tableau
   de bord — le go reste humain, dans la fenêtre de la PR). Trop peu d'issues prêtes : son étape 0
   ouvre d'abord une session de triage et d'interrogatoire par issue, puis se termine sur la liste
   des issues prêtes et une carte « démarrer la vague » : un lead neuf la conduit — préparer et
   conduire sont deux sessions. Correctif évident (`contraintes.md`, barreau 3) : la **voie
   courte** de `cycle-pr`, sans issue ni draft, une passe de relecture, un go.
3bis. **Amender** — `contradiction`, lancé par la session de dialogue dès qu'une de ses décisions
   contredit une source de vérité (section « Sources de vérité » de
   `.claude/pipeline.config.md`) : le document est amendé par la session de dialogue qui a décidé,
   ou la décision est abandonnée — ou son effet déplacé hors de ce que le document affirme.
   Déclenché par la règle `decisions-vs-doc`, à n'importe quel moment.
4. **Répercuter** — `repercussions` après chaque merge qui la rend due (`cycle-pr` Étape 8) :
   confronte d'abord le delta aux sources de
   vérité (un § falsifié → `contradiction`), puis corrige la spec — corps et brief d'agent —
   des issues dont la planification est devenue fausse. Porté par la session PR en fin de
   `cycle-pr` — collecte au `releveur`, go d'édition au mainteneur dans sa fenêtre ; pour une issue
   en lots coordonnés, par la coordinatrice au merge de la PR d'intégration.
5. **Valider** — `plan-qa` → `execution-qa` → `bug-vers-issue`, chacun dans une session de
   dialogue, proposé quand un **thème se vide** de ses issues ouvertes. La QA ne re-teste jamais
   ce que la CI couvre déjà.

## Les règles qui ne se négocient pas

Voir [.claude/rules/](.claude/rules/) (chargées automatiquement à chaque session) :

- **Aucun commit cassé**, jamais d'auto-merge dans le trunk, jamais de force-push — `contraintes.md`
- **Cleanup pass verbatim** à chaque relecture (DRY / KISS / YAGNI) — `cleanup-verbatim.md`
- **Format des commits** : `type(scope): description`, préfixe EN + description FR (bots de
  dépendances exemptés de la description) ; un sujet = une issue = une PR, sans limite de lignes
  ni de fichiers, et découper exige un motif écrit avec son coût — `taille-pr.md`
- **Aucune décision ne contredit la doc en silence** : deux citations, arrêt, puis amendement ou
  abandon — `decisions-vs-doc.md`
- **Toute question a une voie** : technique, elle se tranche selon les bonnes pratiques et se
  trace ; vision, elle attend le mainteneur, groupée ; contradiction, elle arrête — `contraintes.md`

## Deux choses qui surprennent au début

- **La PR existe avant le code.** Elle est ouverte en draft dès le départ, avec `Closes #N`. C'est
  ce qui signale qu'une issue est en cours de développement — sans quoi une autre session pourrait
  réécrire sa spec en croyant que personne n'y travaille.
- **Une PR en draft n'a aucun run de CI.** Le premier part quand elle sort du draft
  (`gh pr ready`), puis chaque push en lance un. Une draft sans check n'est donc pas une CI
  cassée.
