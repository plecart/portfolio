# Configuration pipeline

## Dépôt GitHub
- repo : `plecart/portfolio` (privé, cadrage D11)
- branche trunk : `main`

## Sources de vérité
Ordre de normativité : **en cas de contradiction, le rang le plus haut l'emporte**. Lu par le skill
`contradiction` et par la règle `.claude/rules/decisions-vs-doc.md`.

| Rang | Fichier | Portée | Où s'inscrit un amendement |
|---|---|---|---|
| 1 | `docs/cadrage-technique.md` | périmètre, phases, architecture, contraintes, registre des décisions D1-D55 (§7) | le § concerné + une ligne au registre §7 (une décision remplacée y reste, marquée « remplacée par ») |
| 2 | `docs/specification-ux.md` | interface du site : direction (§1), jetons, écrans, composants, états, responsive, accessibilité, performance, contraintes de contenu (§2-§7, valeurs mesurées sur les prototypes retenus) | le § concerné, puis le prototype HTML correspondant (hors dépôt, `E:/Projets/Portfolio-prototypes/`, README de reprise) : les deux restent alignés |
| 3 | `docs/adr/` (index et conventions : `docs/adr/README.md`) | le pourquoi d'une brique, options écartées | un nouvel ADR qui remplace l'ancien (statut MADR « remplacé par »), jamais l'édition d'un ADR accepté |
| 4 | `docs/frontend-outillage.md` | inventaire installé et plan d'installation de `apps/web/` (le pourquoi de D44 est dans l'ADR 0008), provisoire | le § concerné |
| n | issues GitHub ouvertes | découpage et planification, **dérivés** des rangs supérieurs | le corps de l'issue, jamais un commentaire — voir `repercussions` |

**Non normatif :** `docs/learning/` (phase 2, pédagogique) ; cadrage annexe C (bibliothèques
pressenties des phases 2 et 3, à confirmer par ADR). Le journal du cadrage v0 et la liste d'outils
dérivée ont été supprimés le 2026-09-18, leur matière reprise dans les ADR. Les prototypes HTML
de `E:/Projets/Portfolio-prototypes/` (hors dépôt) sont les sources de mesure de `docs/specification-ux.md` :
rien ne s'y décide, et un amendement de la spec s'y répercute.

Toute référence croisée cite un **§ ou un titre de section**, jamais un numéro de ligne.

## Stack
- langages : Python 3.12 ; TypeScript (frontend, D44)
- frameworks :
  - phase 1 : Django + django-ninja (API, admin) ; Vite + React + TypeScript + Tailwind CSS + shadcn/ui (frontend, cadrage §5.2, D44)
  - phase 2 : FastAPI + LangGraph / LangChain / LangSmith ; embeddings et reranking `bge-m3` + `bge-reranker-v2-m3` via `text-embeddings-inference`
  - phase 3 : SDK Python `mcp` (FastMCP)
- infrastructure : Postgres 16 + pgvector, Redis 7, Docker Compose, Caddy, Cloudflare (DNS, CDN, WAF, Access, Tunnel, R2), GitHub Actions + GHCR
- gestionnaire de paquets : `uv` (Python) ; `npm` (frontend)
- runtime + version : python 3.12 ; Node 24.21.0 — LTS active au 2026-09-23 (ligne 24 « Krypton » ;
  la 26 est *current*, pas LTS). Épinglée deux fois, `apps/web/.nvmrc` et le champ `engines` de
  `apps/web/package.json`, dont un test Vitest vérifie l'égalité : deux épingles qui divergeraient
  en silence ne vaudraient pas mieux qu'aucune.

## Commandes du projet
Lues par `cycle-pr`, `execution-qa` et la génération de CI. `n/a` = étape absente du projet.
Vérifiées une à une le 2026-09-23 au premier scaffold du back (#2), depuis la racine du dépôt :
chaque cible ci-dessous a été lancée et a rendu 0. Les lignes qui nomment une cible `make` la
tirent du `Makefile`, source unique appelée aussi par la CI : une commande ne peut donc pas
diverger entre le poste et GitHub Actions. Deux lignes n'ont volontairement pas de cible —
« test ciblé » prend un argument, « hooks » ne se lance qu'une fois par clone.

Les trois piles gardent des cibles distinctes (`make lint` / `make web-lint` / `make build`) :
elles n'ont pas les mêmes prérequis — `uv`, Node, Docker — et la CI en fait trois jobs séparés,
pour qu'un rouge de l'une ne masque pas un rouge d'une autre.

**Back (`apps/api/`)** — vérifiées le 2026-09-23 au premier scaffold du back (#2) :
- install      : make install                     # uv sync
- test         : make test                        # suite complète ; exige Docker : les tests de base
                                                  # démarrent Postgres par testcontainers (#7) ;
                                                  # vérifiée le 2026-09-26
- test ciblé   : uv run pytest <chemin|motif>     # une seule cible, pour la boucle TDD
- test brut    : rtk proxy make test              # sortie du lanceur sans le résumeur RTK du poste :
                                                  # le verdict se lit ici (cycle-pr 3.2) ; vérifiée le 2026-09-25
- lint         : make lint                        # ruff check
- format       : make format                      # ruff format — écrit
- format:check : make format-check                # vérifie sans écrire
- typecheck    : make typecheck                   # pyright, mode strict (cadrage §8.4)
- audit        : make audit                       # pip-audit, toute vulnérabilité bloque ;
                                                  # exceptions datées dans
                                                  # infra/ci/pip-audit-exceptions.toml ;
                                                  # vérifiée le 2026-09-25 (#5)
- hooks        : uv run pre-commit install        # ruff seulement (check --fix, format)

`build` et `run local` du back ne figurent pas ici : ils demandent Docker, pas `uv`, et vivent
dans le bloc « Infra » ci-dessous. Aucune ligne `n/a` ne les double — une valeur trouvée en
premier serait lue comme la bonne.

**Infra (`infra/`)** — vérifiées le 2026-09-24 à la naissance d'`infra/` (#4), chacune lancée
depuis la racine et rendant 0, la pile démarrée et regardée. Ces trois cibles demandent Docker :
c'est le seul bloc dont les prérequis ne sont ni `uv` ni Node, et la CI en fait un troisième job.
- build        : make build                       # image `api` (`infra/api/Dockerfile`), sans publication
- compose      : make compose-config              # résout `infra/compose.dev.yml` — exige un `.env` à la racine
- run local    : make dev                         # pile Postgres + Redis + `api`, ports sur `127.0.0.1`

**Front (`apps/web/`)** — vérifiées le 2026-09-23 au scaffold du front (#3), chacune lancée depuis
la racine et rendant 0, sauf `web-lighthouse`, seule cible qui ne tourne pas sur le poste :
- install      : make web-install                 # npm ci, à partir du verrou
- navigateurs  : make web-browsers                # Chromium pour Playwright ; long, étape distincte en CI
- test         : make web-test                    # Vitest
- test ciblé   : cd apps/web && npm test -- <motif>
- test brut    : rtk proxy make web-test          # sortie du lanceur sans le résumeur RTK du poste ;
                                                  # vérifiée le 2026-09-25
- lint         : make web-lint                    # ESLint 9 + jsx-a11y, `--max-warnings 0`
- format       : n/a                              # aucun formateur front installé — ESLint ne formate pas
- format:check : n/a
- typecheck    : make web-typecheck               # tsc -b, mode strict
- build        : make web-build                   # typecheck puis `vite build` → apps/web/dist
- e2e          : make web-e2e                     # Playwright + axe, projets desktop et mobile
- lighthouse   : make web-lighthouse              # **CI seulement** : sous Windows, `chrome-launcher`
                                                  # échoue sur EPERM (docs/frontend-outillage.md §2.4)
- audit        : make web-audit                   # npm audit, seuil high, arbre complet (dev compris)
- run local    : cd apps/web && npm run dev

## Qualité
- seuil de couverture : aucun (cadrage annexe A : « pragmatique ; évaluations RAG et E2E prioritaires »)
- règles sensibles à la plateforme (poste Windows, CI Linux) :
  - bit exécutable POSIX (`ruff` `EXE001`) — vérifié en CI seulement
  - fins de ligne des fichiers lus par un conteneur (`.gitattributes` + `test_infra`) — rouge
    possible sur le seul poste, copie de travail en CRLF
- gates bloquants en CI :
  - back : audit, lint, format:check, typecheck, test
  - front : lint, typecheck, test, build, e2e (Playwright + axe), lighthouse, audit
  - infra : compose (résolution de `infra/compose.dev.yml`), build de l'image `api` sans publication — la publication sur GHCR et le scan Trivy restent à #15
- services requis en CI : aucun déclaré — les tests de base démarrent eux-mêmes Postgres par testcontainers (cadrage §8.4), sur le Docker du runner ; Redis suivra avec #11

## Périmètre
- domaines (nom métier → chemin ; chemins cibles du cadrage §9 point 2, chaque dossier né avec sa première brique) — servent aussi de thèmes/milestones à `triage` :
  - Socle & exploitation : `infra/`, `.github/`, `packages/`, `.claude/`, `CLAUDE.md`, `CONTRIBUTING.md`, `docs/` — tout ce qui n'est pas métier, pour qu'aucune PR ne soit orpheline
  - Contenu & API : `apps/api/`
  - Frontend : `apps/web/`
  - Assistant RAG : `apps/ai/` (phase 2)
  - MCP : `apps/mcp/` (phase 3)
- zones sensibles (arrêt humain — cadence dans `.claude/rules/contraintes.md` : une fois par PR, dès que l'écran est assemblé) : écrans à valider visuellement, et rien d'autre
- hors périmètre (cadrage §4 « Hors périmètre ») : email, anglais, commentaires, MCP d'édition de contenu, Kubernetes, CMS headless, content-as-code, Postgres managé
- surfaces exposées (phase 1 ; phases 2 et 3 ajoutées quand elles démarrent) — ce que la QA a le droit de vérifier :
  API HTTP (django-ninja) · interface web · admin Django (un seul compte, pas d'isolation entre comptes) · persistance Postgres · traitements asynchrones (worker) · fichiers produits (médias sur R2)
- surfaces visibles par un utilisateur (déclenchent la vérif de fumée de `cycle-pr` et la proposition de campagne QA) :
  accueil (grille de cartes) · fiche projet (modal) · admin Django

## Langue
- skills / issues / PRD / descriptions : français
- identifiants du code : anglais
- commentaires / docstrings / noms de tests : français
- préfixe conventional commit : anglais (feat/fix/chore/docs/refactor/test/ci)

## Mapping labels (rôle canonique → label GitHub)
- bug → `bug`
- enhancement → `enhancement`
- needs-triage → `needs-triage`
- needs-info → `needs-info`
- needs-interrogation → `needs-interrogation`
- ready-for-agent → `ready-for-agent`
- ready-for-human → `ready-for-human`
- wontfix → `wontfix`
- qa-plan → `qa-plan`
- qa-finding → `qa-finding`
- prd → `prd`   # label de nature (document parent) — hors machine à états, ni rôle d'état ni thème
- documentation → `documentation`   # label de nature (PR `docs(…)` sans issue liée) — hors machine à états

**Métadonnées d'une PR** — posées à l'Étape 2 de `cycle-pr`, vérifiées à l'Étape 5, corrigées
avant `gh pr ready` si elles dévient. Toute PR qui n'est pas l'œuvre d'un bot porte :
- **assignee** : son auteur ;
- **un** label de catégorie : celui de l'issue qu'elle ferme ; sans issue, dérivé du type
  conventional commit — `feat` / `chore` / `refactor` → `enhancement`, `fix` → `bug`,
  `docs` → `documentation` ;
- **le milestone** du domaine de ses fichiers (section « Périmètre »).

## Skills du projet
Sélection faite à la main lors de l'audit du 2026-09-18 (`docs/frontend-outillage.md` §1-§2), sans
`claude-code-setup` ni `find-skills`. Mise à jour d'un skill public : re-cloner le dépôt, recopier,
rescanner avec SkillSpector (frontend-outillage §2.3), puis **réappliquer les modifications locales**
des skills marqués « modifié localement » ci-dessous (`git log -p -- .claude/skills/<skill>` les donne).

**Maison** (Boilerplate `skills/`, chacun invocable par `/<nom>` — sans fichier de commande
homonyme : un skill le masquerait) :
`init-projet`, `vers-prd`, `vers-issues`, `triage`, `interroge-moi`, `cycle-pr`, `contradiction`,
`repercussions`, `pr-paralleles`, `plan-qa`, `execution-qa`, `bug-vers-issue`, `audit-spec-ui`.

**Minimalisme** : `ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt`, `ponytail-gain`,
`ponytail-help` — activés dans `CLAUDE.md` (section « Minimalisme »), doctrine D27.

**Frontend et rédaction** (licence MIT jointe dans chaque dossier) :

| Skill | Dépôt @ commit | Usage |
|---|---|---|
| `taste-skill` (`design-taste-frontend`) | Leonxlnx/taste-skill @ e79ca9e | Direction visuelle anti-générique ; molettes variance / mouvement / densité |
| `minimalist-skill` (`minimalist-ui`) | Leonxlnx/taste-skill @ e79ca9e | Variante sobre, éditoriale (cadrage annexe B : « le plus sobre possible ») |
| `emil-design-eng` | emilkowalski/skills @ 85e8e23 | Principes design engineering d'Emil Kowalski |
| `prototype` | emilkowalski/skills @ 85e8e23 | Idée → plusieurs variantes d'UI comparables dans un sélecteur — **modifié localement** (PR #34, obs 3 à 6 : vérification isolée du rendu, relecture de la spec avant promotion) |
| `animate` | emilkowalski/skills @ 85e8e23 | Écrire une animation (courbes, durées, propriétés) |
| `review-animations` | emilkowalski/skills @ 85e8e23 | Relecture stricte d'animations |
| `improve-animations` | emilkowalski/skills @ 85e8e23 | Audit + plans d'amélioration, lecture seule |
| `find-animation-opportunities` | emilkowalski/skills @ 85e8e23 | Repérer où le mouvement apporte quelque chose |
| `animation-vocabulary` | emilkowalski/skills @ 85e8e23 | Vocabulaire précis pour décrire une animation |
| `no-ai-slop` | petergyang/no-ai-slop @ 000650b | Rédaction des fiches ; motifs écrits pour l'anglais, transfert partiel au français |
| `improve-codebase-architecture` | mattpocock/skills @ c55ee46 | Audit d'architecture (modules profonds), s'appuie sur les ADR |

**Session** : `task-observer` (journal d'observations pour l'amélioration des skills — activé dans
`CLAUDE.md`, section « Observation continue » ; **modifié localement**, PR #34, obs 21 : artefacts
plutôt que gestes, pannes connues en tête de revue) ; `i-have-adhd` (mise en forme des réponses : action
suivante d'abord, étapes numérotées, état restitué à chaque tour ; `/i-have-adhd`).

**RTK** (hook utilisateur `rtk hook claude`, `~/.claude/RTK.md`, hors dépôt) réécrit la commande
avant son exécution — `make …`, `gh …` (sauf `gh label` et `gh api … --jq`), `cat`/`head -N`/`tail`
(→ `rtk read …` ; `head -n N` n'est pas réécrit), `ls`, `wc`, `grep`, chaque segment d'une commande
composée ; ni `git …` ni `sed`. Les règles de permission sont évaluées sur la forme **réécrite**
(doc hooks, `updatedInput`, mesuré le 2026-09-29) : c'est pourquoi les entrées `allow` de
`.claude/settings.json` commencent par `rtk`, et pourquoi les lectures auto-autorisées par Claude
Code (`cat`, `gh pr view`…) y figurent quand même. RTK lit aussi `permissions.allow` et renvoie
lui-même `permissionDecision: "allow"` quand la commande **d'origine** y figure (`gh pr *`,
`gh issue *`…) : les entrées sous forme d'origine restent actives, et les entrées `rtk` sont celles
que le harnais évalue sans lui — les deux se doublent à dessein. Même
logique pour les `deny` : le harnais ne reconnaît ni `rtk read` ni `rtk grep` comme des lectures de
fichier, donc `Read(.env)` ne les arrête pas — deux `deny` Bash (`rtk read *.env*`, `rtk grep *.env*`)
ferment les neuf formes recensées par `apps/api/tests/test_agent_permissions.py` (citation, glob,
`--max-lines`, `--tail-lines`, `grep`) — et attrapent aussi, collatéral accepté et épinglé par le
même test, `rtk read .env.example`, `rtk read infra/dev.env` et toute recherche dont le texte
contient `.env` (`os.environ`, `config.env`, `process.env`) : passer par l'outil Grep ou `git grep`,
que RTK ne réécrit pas. Restent ouverts, et la doc le dit (« isn't a security boundary around the
program ») : un glob sans `.env` littéral (`.en?`), `grep -r` sans nom de fichier, une indirection
par variable (`f=.env; cat "$f"`), tout sous-processus qui ouvre le fichier lui-même.

**Outils hors dépôt** (`uv tool`, environnements isolés — frontend-outillage §2.2) :
- SkillSpector 2.11.2 (NVIDIA/skillspector @ d162d9b) — `skillspector scan .claude/skills/<skill> --no-llm` après chaque ajout ou mise à jour de skill
- strix 1.6.2 (`strix-agent`) — pentest par agents IA, en fin de parcours contre la préproduction, jamais la prod ; sorties dans `strix_runs/` (ignoré)
- Manus (service en ligne, compte à créer — frontend-outillage §4) — maquettes jetables, moodboards, recherches ; son code ne part pas en production (D27)

**Serveurs MCP** (vérifier avec `claude mcp list`) :
- `playwright` — portée **projet**, `.mcp.json` à la racine, donc présent dans tout clone et tout
  worktree ; outil de la vérif de fumée de `cycle-pr` sur l'interface web. Version épinglée à la
  main — Dependabot ne lit pas ce fichier : `npm view @playwright/mcp version` pour la remonter.
  Le wrapper `cmd /c` est celui du poste Windows.
- `context7` — portée `user` (`~/.claude.json`, hors dépôt), installé par `init-projet`.

**Écartés :**
- `design-system` — recoupait `taste-skill` (frontend-outillage §5) ; retiré le 2026-09-18
- emilkowalski/skills : `animate-expo`, `write-swift`, `mobile-native` (natif) ; `ask-sonner` (librairie non choisie) ; `pick-ui-library` (choix fait) ; `apple-design`
- Leonxlnx/taste-skill : variantes `soft`, `brutalist`, `redesign`, `output`, `gpt-tasteskill`, `stitch`, générateurs d'images, `v1`
- audit frontend-outillage §1 : anime.js (doublon de motion) ; design-motion-principles (reconditionne Emil Kowalski) ; UX Engine / designmotionhq (payant, doublon) ; boneyard (sur-ingénierie) ; Spline (3D lourde — à rouvrir si un besoin 3D réel apparaît, three.js en alternative) ; watermelon-platform et motion-primitives (doublons de react-bits) ; dépôt 21st (inactif depuis mai 2025) ; ui-ux-pro-max-skill (`taste-skill` préféré)
