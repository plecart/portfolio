# Configuration pipeline

## Dépôt GitHub
- repo : `plecart/portfolio` (privé, cadrage D11)
- branche trunk : `main`

## Sources de vérité
Ordre de normativité : **en cas de contradiction, le rang le plus haut l'emporte**. Lu par le skill
`contradiction` et par la règle `.claude/rules/decisions-vs-doc.md`.

| Rang | Fichier | Portée | Où s'inscrit un amendement |
|---|---|---|---|
| 1 | `docs/cadrage-technique.md` | périmètre, phases, architecture, contraintes, registre des décisions D1-D44 (§7) | le § concerné + une ligne au registre §7 (une décision remplacée y reste, marquée « remplacée par ») |
| 2 | `docs/adr/` (index et conventions : `docs/adr/README.md`) | le pourquoi d'une brique, options écartées | un nouvel ADR qui remplace l'ancien (statut MADR « remplacé par »), jamais l'édition d'un ADR accepté |
| 3 | `docs/frontend-outillage.md` | inventaire installé et plan d'installation de `apps/web/` (le pourquoi de D44 est dans l'ADR 0008), provisoire | le § concerné |
| n | issues GitHub ouvertes | découpage et planification, **dérivés** des rangs supérieurs | le corps de l'issue, jamais un commentaire — voir `repercussions` |

**Non normatif :** `docs/learning/` (phase 2, pédagogique) ; cadrage annexe C (bibliothèques
pressenties des phases 2 et 3, à confirmer par ADR). Le journal du cadrage v0 et la liste d'outils
dérivée ont été supprimés le 2026-09-18, leur matière reprise dans les ADR.

Toute référence croisée cite un **§ ou un titre de section**, jamais un numéro de ligne.

## Stack
- langages : Python 3.12 ; TypeScript (frontend, D44)
- frameworks :
  - phase 1 : Django + django-ninja (API, admin) ; Vite + React + TypeScript + Tailwind CSS + shadcn/ui (frontend, cadrage §5.2, D44)
  - phase 2 : FastAPI + LangGraph / LangChain / LangSmith ; embeddings et reranking `bge-m3` + `bge-reranker-v2-m3` via `text-embeddings-inference`
  - phase 3 : SDK Python `mcp` (FastMCP)
- infrastructure : Postgres 16 + pgvector, Redis 7, Docker Compose, Caddy, Cloudflare (DNS, CDN, WAF, Access, R2), GitHub Actions + GHCR
- gestionnaire de paquets : `uv` (Python) ; `npm` (frontend)
- runtime + version : python 3.12 ; Node : à fixer à l'initialisation de `apps/web/`

## Commandes du projet
Lues par `cycle-pr`, `execution-qa` et la génération de CI. `n/a` = étape absente du projet.
Toutes marquées `# non vérifiée` : aucun code au 2026-09-18 (étape 11 d'`init-projet`, cas « projet
sans code »). Le squelette monorepo (cadrage §9.2 : `apps/api`, `apps/web`, `apps/ai`, `apps/mcp`,
`packages/`, `infra/`) les fera peut-être préfixer d'un chemin — rejouer `init-projet` à ce moment-là.
- install      : uv sync                          # non vérifiée
- test         : uv run pytest                    # non vérifiée — suite complète (testcontainers pour Postgres/Redis)
- test ciblé   : uv run pytest <chemin|motif>     # non vérifiée — une seule cible, pour la boucle TDD
- lint         : uv run ruff check .              # non vérifiée
- format       : uv run ruff format .             # non vérifiée — écrit
- format:check : uv run ruff format --check .     # non vérifiée — vérifie sans écrire
- typecheck    : uv run pyright                   # non vérifiée — mode strict (cadrage §8.4)
- build        : n/a                              # tant qu'`infra/` n'existe pas
- run local    : n/a                              # tant qu'`infra/` n'existe pas
- hooks        : pre-commit (cadrage §8.4)        # non vérifiée — à installer au premier scaffold

## Qualité
- seuil de couverture : aucun (cadrage annexe A : « pragmatique ; évaluations RAG et E2E prioritaires »)
- gates bloquants en CI : lint, format:check, typecheck, test
- services requis en CI : aucun (testcontainers démarre Postgres et Redis dans les tests, cadrage §8.4)

## Périmètre
- domaines (nom métier → chemin ; chemins prévus au cadrage §9.2, à ajuster au squelette) — servent aussi de thèmes/milestones à `triage` :
  - Socle & exploitation : `infra/`, `.github/`, `packages/`, `.claude/`, `CLAUDE.md`, `CONTRIBUTING.md`, `docs/` — tout ce qui n'est pas métier, pour qu'aucune PR ne soit orpheline
  - Contenu & API : `apps/api/`
  - Frontend : `apps/web/`
  - Assistant RAG : `apps/ai/` (phase 2)
  - MCP : `apps/mcp/` (phase 3)
- zones sensibles (arrêt humain — cadence dans `.claude/rules/contraintes.md` : une fois par PR, avant `gh pr ready`) : écrans à valider visuellement, et rien d'autre
- hors périmètre (cadrage §4 « Hors périmètre ») : email, anglais, commentaires, MCP d'édition de contenu, Kubernetes, CMS headless, content-as-code, Postgres managé
- surfaces exposées (phase 1 ; phases 2 et 3 ajoutées quand elles démarrent) — ce que la QA a le droit de vérifier :
  API HTTP (django-ninja) · interface web · admin Django (un seul compte, pas d'isolation entre comptes) · persistance Postgres · traitements asynchrones (worker) · fichiers produits (médias sur R2)
- surfaces visibles par un utilisateur (déclenchent la vérif de fumée de `cycle-pr` et la proposition de campagne QA) :
  accueil (grille d'icônes) · fiche projet (modal) · page « à propos » · admin Django

## Langue
- skills / issues / PRD / descriptions : français
- identifiants du code : anglais
- commentaires / docstrings / noms de tests : français
- préfixe conventional commit : anglais (feat/fix/chore/docs/refactor)

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
rescanner avec SkillSpector (frontend-outillage §2.3).

**Maison** (Boilerplate `skills/`, une commande homonyme chacun dans `.claude/commands/`) :
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
| `prototype` | emilkowalski/skills @ 85e8e23 | Idée → plusieurs variantes d'UI comparables dans un sélecteur |
| `animate` | emilkowalski/skills @ 85e8e23 | Écrire une animation (courbes, durées, propriétés) |
| `review-animations` | emilkowalski/skills @ 85e8e23 | Relecture stricte d'animations |
| `improve-animations` | emilkowalski/skills @ 85e8e23 | Audit + plans d'amélioration, lecture seule |
| `find-animation-opportunities` | emilkowalski/skills @ 85e8e23 | Repérer où le mouvement apporte quelque chose |
| `animation-vocabulary` | emilkowalski/skills @ 85e8e23 | Vocabulaire précis pour décrire une animation |
| `no-ai-slop` | petergyang/no-ai-slop @ 000650b | Rédaction des fiches ; motifs écrits pour l'anglais, transfert partiel au français |
| `improve-codebase-architecture` | mattpocock/skills @ c55ee46 | Audit d'architecture (modules profonds), s'appuie sur les ADR |

**Session** : `task-observer` (journal d'observations pour l'amélioration des skills — activé dans
`CLAUDE.md`, section « Observation continue ») ; `i-have-adhd` (mise en forme des réponses : action
suivante d'abord, étapes numérotées, état restitué à chaque tour ; `/i-have-adhd`).

**Outils hors dépôt** (`uv tool`, environnements isolés — frontend-outillage §2.2) :
- SkillSpector 2.11.2 (NVIDIA/skillspector @ d162d9b) — `skillspector scan .claude/skills/<skill> --no-llm` après chaque ajout ou mise à jour de skill
- strix 1.6.2 (`strix-agent`) — pentest par agents IA, en fin de parcours contre la préproduction, jamais la prod ; sorties dans `strix_runs/` (ignoré)
- Manus (service en ligne, compte à créer — frontend-outillage §4) — maquettes jetables, moodboards, recherches ; son code ne part pas en production (D27)

**Serveur MCP** : `context7` — déclaré en portée `user` (`~/.claude.json`, hors dépôt), vérifier avec
`claude mcp list`.

**Écartés :**
- `design-system` — recoupait `taste-skill` (frontend-outillage §5) ; retiré le 2026-09-18
- emilkowalski/skills : `animate-expo`, `write-swift`, `mobile-native` (natif) ; `ask-sonner` (librairie non choisie) ; `pick-ui-library` (choix fait) ; `apple-design`
- Leonxlnx/taste-skill : variantes `soft`, `brutalist`, `redesign`, `output`, `gpt-tasteskill`, `stitch`, générateurs d'images, `v1`
- audit frontend-outillage §1 : anime.js (doublon de motion) ; design-motion-principles (reconditionne Emil Kowalski) ; UX Engine / designmotionhq (payant, doublon) ; boneyard (sur-ingénierie) ; Spline (3D lourde — à rouvrir si un besoin 3D réel apparaît, three.js en alternative) ; watermelon-platform et motion-primitives (doublons de react-bits) ; dépôt 21st (inactif depuis mai 2025) ; ui-ux-pro-max-skill (`taste-skill` préféré)
