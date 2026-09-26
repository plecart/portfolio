# Contribuer

Le développement suit une pipeline pilotée par les issues. **La source de vérité du process n'est
pas ce fichier** : c'est le skill `cycle-pr` (déroulé pas à pas) et les règles permanentes dans
[.claude/rules/](.claude/rules/). Ce document n'en donne que la carte.

Chaque étape ci-dessous a une commande dédiée (`/triage`, `/cycle-pr`…) — voir
[.claude/commands/](.claude/commands/).

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
privé. Demande Docker ; les ports 8000, 5432 et 6379 sont publiés sur `localhost` seulement.

```
make dev                    # construit l'image `api` si besoin, puis démarre la pile
```

`make dev` plutôt qu'un `docker compose` direct : la cible passe `--env-file infra/dev.env`, sans
quoi les valeurs interpolées du fichier Compose seraient vides. Le `.env` de la racine doit
exister — Compose refuse de résoudre un `env_file` absent, avant même de démarrer quoi que ce
soit. `Ctrl-C` arrête la pile ; les données Postgres survivent dans un volume nommé.

**Regarder l'admin.** La pile démarrée, créer le compte d'administration dans le conteneur `api`
— la commande de gestion de #6 prendra le relais —, puis ouvrir `http://127.0.0.1:8000/admin/` :

```
docker compose --env-file infra/dev.env -f infra/compose.dev.yml exec api python manage.py createsuperuser
```


Deux fichiers d'environnement, qui ne se remplacent pas :

| Fichier | Commité | Lu par | Contient |
|---|---|---|---|
| `.env` | non | la classe `Env` du back | les variables de `Env`, et elles seules |
| `infra/dev.env` | oui | Compose, pour l'interpolation `${…}` | identifiants Postgres de développement et ports publiés, aucune valeur secrète |

Le refus d'une clé inconnue vaut pour le **fichier**, donc sur le poste (`uv run manage.py`,
`make test`). Dans le conteneur, Compose injecte `.env` comme variables d'environnement et
`/app/.env` n'existe pas : une clé inconnue y est ignorée, comme n'importe quelle variable du
système. La séparation en deux fichiers ne repose donc pas sur ce garde-fou — elle repose sur le
fait que les variables de Compose ne sont pas des variables du back, et c'est
[apps/api/tests/test_env.py](apps/api/tests/test_env.py) qui tient la frontière.

Le code de `apps/api` est monté dans le conteneur : une modification sur le poste recharge `api`.
Les migrations s'exécutent à chaque démarrage. Les tests et les outils de qualité restent sur
l'hôte (`make test`, `make lint`) — le conteneur fait tourner l'application, il ne la vérifie pas.

Toutes les cibles disponibles : `Makefile`, repris dans la section « Commandes du projet » de
[.claude/pipeline.config.md](.claude/pipeline.config.md) — c'est cette section que lisent les
skills et la génération de CI.

`.env` vit à la **racine** du dépôt et n'est lu qu'en développement (cadrage §6.6) ; en
production il est écrit par `infra/bootstrap.sh` depuis les secrets, jamais édité à la main.
Toute variable d'environnement est déclarée dans `.env.example` et lue par la classe `Env`
(`apps/api/config/env.py`) — nulle part ailleurs, et jamais en dur.

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
   au socle) → auto-review → relecture à contexte vierge finale → `gh pr ready` → review → vérif de
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

Voir [.claude/rules/](.claude/rules/) (chargées automatiquement via `CLAUDE.md`) :

- **Aucun commit cassé**, jamais d'auto-merge, jamais de force-push — `contraintes.md`
- **Cleanup pass verbatim** à chaque relecture (DRY / KISS / YAGNI) — `cleanup-verbatim.md`
- **Format des commits** : `type(scope): description`, préfixe EN + description FR (bots de
  dépendances exemptés de la description) ; PR ≤ ~10 fichiers / ~500 lignes — `taille-pr.md`
- **Aucune décision ne contredit la doc en silence** : deux citations, arrêt, puis amendement ou
  abandon — `decisions-vs-doc.md`

## Deux choses qui surprennent au début

- **La PR existe avant le code.** Elle est ouverte en draft dès le départ, avec `Closes #N`. C'est
  ce qui signale qu'une issue est en cours de développement — sans quoi une autre session pourrait
  réécrire sa spec en croyant que personne n'y travaille.
- **La CI ne tourne pas sur une draft.** Aucun check n'apparaît tant que la PR n'est pas passée en
  ready. Ce n'est pas une CI cassée : les tests tournent en local à chaque commit.
