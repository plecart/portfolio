# Contribuer

Le développement suit une pipeline pilotée par les issues. **La source de vérité du process n'est
pas ce fichier** : c'est le skill `cycle-pr` (déroulé pas à pas) et les règles permanentes dans
[.claude/rules/](.claude/rules/). Ce document n'en donne que la carte.

Chaque étape ci-dessous s'invoque par le nom de son skill (`/triage`, `/cycle-pr`…) — voir
[.claude/skills/](.claude/skills/).

## Démarrer en local

Le dépôt porte trois piles, provisionnées séparément : le back (`uv`), le front (Node) et la pile
de développement (Docker). Elles n'ont pas les mêmes prérequis, et la CI les tient dans trois jobs
distincts, pour qu'un rouge de l'une ne masque pas un rouge d'une autre.

**Back (`apps/api`)** — Python 3.12, épinglé par `.python-version` et lu par `uv` :

```
uv sync                     # installe l'espace de travail : racine + apps/api
cp .env.example .env        # puis renseigner SECRET_KEY
uv run pre-commit install   # branche les hooks — depuis ce clone, jamais depuis un worktree :
                            # .git/hooks est partagé et fige le chemin de l'interpréteur qui l'installe
```

`make test` exige Docker : les tests qui touchent la base démarrent un Postgres jetable — l'image
du Compose de développement — par testcontainers, et échouent en le disant si Docker ne répond
pas. Ils ne lisent jamais `.env` : leur environnement est posé par
[apps/api/tests/process_environment.py](apps/api/tests/process_environment.py).

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

**La pile de développement (`infra/`)** — Postgres, Redis et `api` en conteneurs sur un réseau
privé. Demande Docker, et le front installé (`make web-install`) : l'image `api` copie son
`index.html` compilé (ADR 0014). Les ports 8000, 5432 et 6379 sont publiés sur `127.0.0.1`
seulement.

```
make dev                    # compile le front s'il manque, construit l'image `api` si besoin,
                            # puis démarre la pile
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
Les migrations s'exécutent à chaque démarrage. Les tests et les outils de qualité restent sur
l'hôte (`make test`, `make lint`) — le conteneur fait tourner l'application, il ne la vérifie pas.

**Regarder l'admin.** La pile démarrée, créer le compte d'administration dans le conteneur `api`
— la commande de gestion de #6 prendra le relais —, puis ouvrir `http://127.0.0.1:8000/admin/` :

```
docker compose --env-file infra/dev.env -f infra/compose.dev.yml exec api python manage.py createsuperuser
```

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

**Audit des dépendances.** `make audit` (Python) et `make web-audit` (front) sont des portes de
CI. Côté Python, tout avis de sécurité connu bloque la PR — `pip-audit` n'expose pas de
sévérité ; côté front, les avis `high` et `critical`. Un avis Python qui ne s'applique pas au
projet — ou le temps qu'un correctif paraisse — se suspend par une entrée **datée** de
[infra/ci/pip-audit-exceptions.toml](infra/ci/pip-audit-exceptions.toml), dont le format est en
tête du fichier ; la date passée, l'audit rebloque. `npm audit` n'a pas de fichier d'exceptions :
son arbre se nettoie par les `overrides` du manifeste
([docs/frontend-outillage.md](docs/frontend-outillage.md) §2.4).

**Tests des images.** `make image-test`, porte de CI sur chaque PR, démarre les images que
`make build` a chargées et les interroge ([infra/tests/](infra/tests/)) : le test de fumée du
Caddyfile de production, et la chaîne de sauvegarde de l'image `backup`, jouée dans le Compose de
production contre un témoin S3 et un témoin de ping. Il ne fait pas partie de `make test` : il lui
faut les images construites, donc le front compilé. Sur le poste, `make build` d'abord. Chaque test
démarre sa pile sous son propre nom de projet Compose — sans port publié, ou sur un port hôte que
Docker attribue — et la supprime en partant, volumes compris.

**Scan des images.** `make scan`, porte de CI sur chaque PR, scanne avec Trivy chaque image que
`make build` a construite : toute vulnérabilité HIGH ou CRITICAL bloque, corrigeable ou non, comme
une image de base en fin de vie
([ADR 0014](docs/adr/0014-ci-cd-github-actions-et-ghcr.md)). Une vulnérabilité sans correctif
pour l'image s'évalue en trois points — la place du composant dans l'image, l'atteinte du code
vulnérable par ce qui tourne, les alternatives — et se consigne en exception **datée**, à 90 jours
au plus, bornée à son image, de [.trivyignore.yaml](.trivyignore.yaml), dont le format est en tête
du fichier ; la date passée, le scan rebloque et l'évaluation se refait. Quand le correctif arrive
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

`age` et `supercronic` entrent dans l'image `backup` par les fichiers `linux-amd64` de leur
release, à la somme SHA-256 épinglée dans [infra/backup/Dockerfile](infra/backup/Dockerfile)
(`ADD --checksum`, que BuildKit vérifie) : Dependabot ne les suit pas, le scan les ouvre. Pour
monter une épingle : relever la somme que GitHub publie pour le fichier de la nouvelle version,

```
gh api repos/FiloSottile/age/releases/tags/v<x.y.z> --jq '.assets[] | select(.name | endswith("linux-amd64.tar.gz")) | .digest'
gh api repos/aptible/supercronic/releases/tags/v<x.y.z> --jq '.assets[] | select(.name == "supercronic-linux-amd64") | .digest'
```

puis la recouper par ce que chaque projet publie — pour `age`, sa preuve Sigsum (`sigsum-verify`
sur l'archive et son `.proof`, procédure dans le `SIGSUM.md` de son dépôt) ; pour `supercronic`, la
somme SHA-1 de ses notes de release —, et changer adresse et somme ensemble. Enfin
`make build-backup scan-backup`, puis `make build image-test`.

**Publication des images.** Rien à faire à la main : à chaque push sur `main`, une fois la CI
verte, le job `publish` reconstruit les images, les scanne comme sur une PR, puis les pousse sur
GHCR — `ghcr.io/plecart/portfolio-<service>`, paquets privés — sous le SHA complet du commit et
sous `latest` (`make push`) ; chaque paquet garde ses trois versions les plus récentes
(`make prune`). Le jeton du workflow suffit, aucun secret n'est à créer
([ADR 0014](docs/adr/0014-ci-cd-github-actions-et-ghcr.md)). Un déploiement vise l'étiquette du
commit : `latest` peut désigner l'avant-dernier quand deux pushes se suivent de près.

**Déploiement.** Rien à faire à la main non plus : après chaque publication sur `main`, le job
`deploy` se connecte au VPS par SSH, y dépose `infra/compose.yml`, fixe `IMAGE_TAG` au SHA du
commit dans son `.env`, puis lance `docker compose pull` et `up -d --wait` — il rougit si un
service ne devient pas sain. Il ne déploie que la tête de `main`, et reste sauté tant que la
variable de dépôt `DEPLOY_ENABLED` ne vaut pas `true`. Amorçage du VPS, secrets et déploiement de
secours : [infra/RUNBOOK.md](infra/RUNBOOK.md).

**Mises à jour des dépendances.** Dependabot ([.github/dependabot.yml](.github/dependabot.yml))
ouvre chaque semaine, par écosystème (`uv`, npm, actions GitHub, images Docker), une PR qui
groupe versions mineures et correctifs ; chaque montée majeure arrive seule, sauf les majeures npm
que `.github/dependabot.yml` refuse — chacune avec sa raison et le test qui la tient
([docs/frontend-outillage.md](docs/frontend-outillage.md) §2.4). Ses PR sont exemptées des
métadonnées de PR et de la description en français
(`chore(deps): bump …`, [.claude/rules/taille-pr.md](.claude/rules/taille-pr.md)), passent par la
même CI et ne se mergent que sur un go humain.
Actions et images sont épinglées par empreinte, derrière leur version la plus précise :
Dependabot met l'une et l'autre à jour ensemble. Une nouvelle version mineure de Python (3.13)
n'est jamais proposée — elle se change à la main, dans `.python-version` puis dans l'image ; ses
versions de correctif (3.12.x) le sont.

## Le flux en une page

0. **Configurer** — `init-projet` écrit `.claude/pipeline.config.md` (dépôt, sources de vérité,
   labels, stack, commandes, domaines, surfaces). À relancer dès qu'une de ces valeurs change.
1. **Planifier** — `vers-prd` (conversation → PRD) → `vers-issues` (PRD → petites issues) →
   `triage` (machine à états, rattachement au thème, « agent brief »).
2. **Interroger** — `interroge-moi`, **obligatoire** : `ready-for-agent` et `ready-for-human` ne
   s'atteignent que via l'état `needs-interrogation`. Les décisions tranchées sont écrites dans
   l'issue, pas laissées dans une conversation.
3. **Implémenter** — `cycle-pr` : briefing pré-PR → **PR draft ouverte avant tout code** → TDD
   red-green-refactor → cycle `modif → test → cleanup → test → commit` (relecture à contexte vierge
   au socle) → cleanup holistique → relecture à contexte vierge finale → `gh pr ready` → CI → vérif de
   fumée → merge. Plusieurs PR en parallèle : `pr-paralleles` (worktrees ;
   la session lead démarre les autres et vérifie chaque PR avant le go, par messages
   inter-sessions — le go lui-même reste humain, dans la fenêtre de la PR).
3bis. **Amender** — `contradiction` dès qu'une décision de conversation contredit une source de
   vérité (section « Sources de vérité » de `.claude/pipeline.config.md`) : le document est amendé
   dans la session, ou la décision est abandonnée — ou son effet déplacé hors de ce que le document
   affirme. Déclenché par la règle `decisions-vs-doc`, à n'importe quel moment.
4. **Répercuter** — `repercussions` après chaque merge : confronte d'abord le delta aux sources de
   vérité (un § falsifié → `contradiction`), puis corrige la spec — corps et brief d'agent —
   des issues dont la planification est devenue fausse. Lancé automatiquement en fin de `cycle-pr`.
5. **Valider** — `plan-qa` → `execution-qa` → `bug-vers-issue`, proposé quand un **thème se vide**
   de ses issues ouvertes. La QA ne re-teste jamais ce que la CI couvre déjà.

## Les règles qui ne se négocient pas

Voir [.claude/rules/](.claude/rules/) (chargées automatiquement à chaque session) :

- **Aucun commit cassé**, jamais d'auto-merge, jamais de force-push — `contraintes.md`
- **Cleanup pass verbatim** à chaque relecture (DRY / KISS / YAGNI) — `cleanup-verbatim.md`
- **Format des commits** : `type(scope): description`, préfixe EN + description FR (bots de
  dépendances exemptés de la description) ; PR ≤ ~10 fichiers / ~500 lignes — `taille-pr.md`
- **Aucune décision ne contredit la doc en silence** : deux citations, arrêt, puis amendement ou
  abandon — `decisions-vs-doc.md`
- **Toute question a une voie** : technique, elle se tranche selon les bonnes pratiques et se
  trace ; vision, elle attend le mainteneur, groupée ; contradiction, elle arrête — `contraintes.md`

## Deux choses qui surprennent au début

- **La PR existe avant le code.** Elle est ouverte en draft dès le départ, avec `Closes #N`. C'est
  ce qui signale qu'une issue est en cours de développement — sans quoi une autre session pourrait
  réécrire sa spec en croyant que personne n'y travaille.
- **La CI tourne sur chaque push, draft comprise**, sauf sur l'ouverture de la draft, dont
  l'amorce est vide. Une draft sans push de code n'a donc aucun check : ce n'est pas une CI cassée.
