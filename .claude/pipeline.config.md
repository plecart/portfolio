# Configuration pipeline

## Dépôt GitHub
- repo : `plecart/portfolio` (privé, cadrage D11)
- branche trunk : `main`

## Sources de vérité
Ordre de normativité : **en cas de contradiction, le rang le plus haut l'emporte**. Lu par le skill
`contradiction` et par la règle `.claude/rules/decisions-vs-doc.md`.

| Rang | Fichier | Portée | Où s'inscrit un amendement |
|---|---|---|---|
| 1 | `docs/cadrage-technique.md` | périmètre, phases, architecture, contraintes, registre des décisions D1-D57 (§7) | le § concerné + une ligne au registre §7 (une décision remplacée y reste, marquée « remplacée par ») |
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
depuis la racine et rendant 0, la pile démarrée et regardée. Ces cibles demandent Docker, et
`build` et `dev` le front installé (`make web-install`) : ils le compilent s'il manque, les images
le copient (ADR 0014). La CI en fait un troisième job, qui installe donc Node aussi.
- build        : make build                       # une image par dossier `infra/<service>/` (`api`,
                                                  # `backup`, `caddy`), front compilé s'il manque ;
                                                  # sans publication ; vérifiée le 2026-10-04 (#23)
- scan         : make scan                        # Trivy sur chaque image que `make build` a
                                                  # chargée : HIGH et CRITICAL bloquent, corrigeables
                                                  # ou non, comme une image de base en fin de vie ;
                                                  # exceptions datées dans `.trivyignore.yaml` ;
                                                  # vérifiée le 2026-09-30 (#15)
- tests images : make image-test                  # pytest sur `infra/tests` : démarre les images que
                                                  # `make build` a chargées — test de fumée du
                                                  # Caddyfile, chaîne de sauvegarde de `backup` ;
                                                  # hors de `make test`, `make build` d'abord ;
                                                  # vérifiée le 2026-10-04 (#23)
- publication  : make push                        # **CI seulement** (job `publish`) : chaque image
                                                  # sous `IMAGE_TAG`, le SHA du commit, puis `latest` ;
                                                  # préfixe GHCR par `IMAGE_PREFIX` ; vérifiée le
                                                  # 2026-09-30 contre un registre local (#15)
- rétention    : make prune                       # **CI seulement**, après `push` : chaque paquet garde
                                                  # ses 3 versions les plus récentes (`gh api`, jeton du
                                                  # workflow) ; éprouvée sur un `gh` témoin et son
                                                  # filtre par gojq, le moteur de `gh` (#15)
- compose      : make compose-config              # résout `infra/compose.dev.yml` — exige un `.env` à la
                                                  # racine — et `infra/compose.yml`, avec le modèle
                                                  # `infra/prod.env.example` ; vérifiée le 2026-10-03 (#16)
- run local    : make dev                         # pile Postgres + Redis + `api`, ports sur `127.0.0.1` ;
                                                  # front compilé s'il manque

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
- e2e ciblé    : cd apps/web && npx playwright test   # une seule spec, et la seule forme à
                                                  # laquelle on peut ajouter les options d'un
                                                  # rapport : `make web-e2e` les refuserait,
                                                  # l'option partant à `make` et non au lanceur.
                                                  # Vérifiée le 2026-10-09 **par `--list`**
                                                  # (62 specs énumérées, 124 ms) : un run réel
                                                  # démarre le serveur web, donc compile le
                                                  # front. Le rapporteur qui la consomme est
                                                  # éprouvé **dans la suite** sur un rapport
                                                  # JSON réel recopié (`PLAYWRIGHT_REPORT` de
                                                  # `apps/api/tests/test_mutation.py`) ; le
                                                  # bout-en-bout contre le vrai lanceur a été
                                                  # joué **à la main** le 2026-10-09, il n'est
                                                  # pas dans la suite — aucune porte ne le rejoue
- lighthouse   : make web-lighthouse              # **CI seulement** : sous Windows, `chrome-launcher`
                                                  # échoue sur EPERM (docs/frontend-outillage.md §2.4)
- audit        : make web-audit                   # npm audit, seuil high, arbre complet (dev compris)
- run local    : cd apps/web && npm run dev

**Harnais (`.claude/`, `CLAUDE.md`)** — vérifiée le 2026-10-09 depuis la racine, avec témoins.
Sans cible `make` : le binaire n'est pas installé dans le runner de CI, et une cible que la CI ne
peut pas appeler ferait croire à une porte qui n'existe pas là-bas. Lancée par `cycle-pr` à
l'Étape 3 avant tout push d'un delta sur `.claude/` ou `CLAUDE.md`.
- validation   : claude plugin validate . --strict  # `--strict` est ce qui la rend bloquante :
                                                  # sans lui un avertissement sort en 0. Couvre
                                                  # `.claude/{skills,agents,commands}` (doc :
                                                  # « those three directories under its
                                                  # `.claude` »), le manifeste s'il existe et
                                                  # les entrées MCP. **Muette** sur un
                                                  # frontmatter de rôle absent ou illisible —
                                                  # mesuré sur v2.1.295, 3 classes de faute :
                                                  # c'est `apps/api/tests/test_agent_skills.py`
                                                  # qui garde celle-là. Installée hors dépôt
                                                  # (`npm i -g @anthropic-ai/claude-code`) ; se
                                                  # lance **depuis la racine**, le PATH du poste
                                                  # portant une entrée relative qui résout un
                                                  # shim cassé ailleurs.
- relecture    : /code-review <niveau>            # commande **intégrée au binaire**, pas un
                                                  # skill du dépôt : rien dans `.claude/` ne la
                                                  # porte. Lancée par `cycle-pr` 4.2 avant
                                                  # chaque appel du relecteur, **additive** au
                                                  # prompt de `cleanup-verbatim.md` (D27). Ce
                                                  # qu'elle couvre, mesuré le 2026-10-12 sur le
                                                  # delta de #85 (672 lignes, niveau `medium`) :
                                                  # **1 défaut de correction réel** qu'aucune
                                                  # des deux passes de relecture n'avait vu —
                                                  # un motif non ancré à gauche qui jetait le
                                                  # préfixe d'un chemin. Ce qu'elle ne couvre
                                                  # pas, mesuré au même run : **zéro** constat
                                                  # sur la prose de protocole, où vivaient les
                                                  # 2 bloquants et 7 importants de la relecture
                                                  # à contexte vierge. Deux portes, deux
                                                  # populations — elle ne remplace rien.
- sécurité     : /security-review                 # même nature. Lancée par `cycle-pr` 4.2
                                                  # **seulement** si le diff touche une zone
                                                  # sensible ou une surface exposée (section
                                                  # « Périmètre »). Première mesure le
                                                  # 2026-10-14, commit 1 de la PR #92 (rôle
                                                  # Postgres de `backup`, 5 fichiers, +204/−63,
                                                  # surface « persistance Postgres ») : **zéro**
                                                  # constat. Inventaire : son prompt écarte les
                                                  # constats portant sur les tests et la
                                                  # documentation (exclusions 11 et 16) — seuls 2
                                                  # fichiers sur 5 pouvaient en porter
                                                  # (`bootstrap.sh`, le modèle de `.env`), ni la
                                                  # pile de test, ni le runbook où vivent les
                                                  # rotations. Son prompt lui interdit de lancer
                                                  # une commande : un zéro de lecture, sur des
                                                  # droits que les tests du rôle et quatre
                                                  # mutations tenaient déjà.
                                                  # Son prompt prescrit des sous-tâches (une de
                                                  # recherche, une de filtre par constat) ; la
                                                  # session l'a déroulée sans elles.

## Qualité
- seuil de couverture : aucun (cadrage annexe A : « pragmatique ; évaluations RAG et E2E prioritaires »)
- règles sensibles à la plateforme (poste Windows, CI Linux) :
  - bit exécutable POSIX (`ruff` `EXE001`) — vérifié en CI seulement
  - fins de ligne des fichiers lus par un conteneur (`.gitattributes` + `test_infra`) — rouge
    possible sur le seul poste, copie de travail en CRLF
  - **argument `<rev>:<chemin>` dans le shell** — sur ce poste, MSYS réécrit un argument de la
    forme `<rev>:<chemin>` avant que git ne le voie : `git show main:<chemin>` lancé par l'outil
    Bash rend **zéro octet** en sortant en 0, et tout ce qui le lit ensuite conclut « fichier
    différent » ou « 0 occurrence » sur du vide. Quatrième occurrence dans le cycle de #77 au
    2026-10-13, comptée par le lead de la vague ; c'est l'évidence n° 1 du principe transverse
    « une seule méthode qui conclut n'est pas une mesure ». Appeler `git show` **sans shell**
    (`subprocess.run([...])`), et exiger un témoin d'octets lus avant de conclure
  - **heredoc de l'outil Bash et antislashs** — un fichier écrit par `cat >> … <<'EOF'` depuis
    l'outil Bash du poste arrive sur disque avec ses antislashs **divisés par deux** : mesuré le
    2026-10-13, un motif `\\?<` tapé est devenu `\?<`, soit un `?` littéral, et une porte sur la
    prose des skills n'appariait plus rien — vue rouge sur son témoin, pas sur son motif. Écrire
    les fichiers par l'outil d'écriture ou d'édition (littéraux) ; un heredoc ne convient qu'à un
    contenu sans antislash
  - **cache de compilation et mutation de même longueur**
    (`.claude/skills/cycle-pr/scripts/mutation.py`, fonction `rewrite`) — `__pycache__`
    s'invalide sur le couple (date, taille) : une mutation qui ne change ni l'une ni l'autre
    fait servir la version témoin, et le harnais rend VERT un test qui tient. Rouge **en CI
    seulement**, l'horodatage de fichier de NTFS étant plus fin que celui des runners ; mesuré
    le 2026-10-09 sur deux mutations de longueur identique
- gates bloquants en CI :
  - back : audit, lint, format:check, typecheck, test
  - front : lint, typecheck, test, build, e2e (Playwright + axe), lighthouse, audit
  - infra : compose (résolution de `infra/compose.dev.yml` et `infra/compose.yml`), build des images `api`, `backup` et `caddy` sans publication, tests des images (`make image-test`), scan (Trivy : HIGH et CRITICAL, corrigeables ou non, et fin de vie ; exceptions datées de `.trivyignore.yaml`)
- portes à base d'avis (`make audit`, `make web-audit`, `make scan`) **sans horloge** : le `ci.yml` du projet n'a pas de `schedule`, par décision du mainteneur (#77, journal de spec, entrée du 2026-10-13 « lot 4, briefing ») — la règle de génération d'`init-projet` le prévoit, ce projet s'en écarte. Un avis neuf se voit au premier run venu — une PR, ou un push vers `main` : `cycle-pr` Étape 6, « rouge d'avis »
- publication (job `publish`, push vers `main` seulement, après les trois jobs verts ; pas une gate de PR) : front compilé repris du job `web`, images reconstruites depuis le cache sans attestation, scannées par `make scan`, poussées sur GHCR (`ghcr.io/plecart/portfolio-<service>`, SHA complet et `latest`) par `make push`, trois versions par paquet gardées par `make prune`
- déploiement (job `deploy`, après `publish`, push vers `main` seulement, sauté tant que la variable de dépôt `DEPLOY_ENABLED` ne vaut pas `true` ; pas une gate de PR) : seule la tête de `main` se déploie ; par SSH (clé dédiée, empreinte de l'hôte épinglée, secrets de l'environnement `production`, restreint à `main`), le job dépose `infra/compose.yml` dans `/srv/portfolio`, y fixe `IMAGE_TAG` au SHA du commit, puis `docker compose pull` et `up -d --wait` — rouge si un service ne devient pas sain, chacun ayant sa sonde ; procédures dans `infra/RUNBOOK.md`
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
plutôt que gestes, pannes connues en tête de revue ; audit du 2026-09-30 : cadence et surfaçage
retirés, `CLAUDE.md` les remplace ; #77 lot 4c : plafond par cycle, relais compris, obs 75 ;
section de date à l'ajout, obs 25 ; re-mesure d'un outil crédité avant inscription, obs 67 ;
champ « Application window ») ; `i-have-adhd` (mise en forme des réponses : action
suivante d'abord, étapes numérotées, état restitué à chaque tour ; `/i-have-adhd`).

**RTK** (hook utilisateur `rtk hook claude`, `~/.claude/RTK.md`, hors dépôt) réécrit la commande
avant son exécution — `make …`, `gh …` (sauf `gh label` et `gh api … --jq`), `cat`/`head -N`/`tail`
(→ `rtk read …` ; `head -n N` n'est pas réécrit), `ls`, `wc`, `grep`, chaque segment d'une commande
composée ; ni `git …` ni `sed`, ni l'outil PowerShell (son matcher ne vise que `Bash`). Les règles
de permission sont évaluées sur la forme **réécrite** (doc hooks, `updatedInput`, mesuré le
2026-09-29) : c'est pourquoi les entrées `allow` de `.claude/settings.json` commencent par `rtk`, et
pourquoi les lectures auto-autorisées par Claude Code (`cat`, `gh pr view`…) y figurent quand même.
RTK lit aussi `permissions.allow` et renvoie lui-même `permissionDecision: "allow"` quand la
commande **d'origine** y figure (`gh pr *`, `gh issue *`…), et retient cet `allow` dès que la forme
d'origine figure en `ask` (mesuré, rtk 0.43.0) : les entrées sous forme d'origine restent actives,
et les entrées `rtk` sont celles que le harnais évalue sans lui — les deux se doublent à dessein.

Un `ask` passe avant tout `allow`, y compris celui qu'un hook renvoie (doc permissions : « a
matching ask rule still prompts even when the hook returned "allow" »), en mode auto compris
(doc permission-modes, § auto mode : « Explicit ask rules still force a prompt ») :
`permissions.ask` sur `gh pr merge` et sur `gh pr update-branch … --rebase` — forme d'origine,
forme `rtk`, `rtk proxy`, outil PowerShell — est la porte de « jamais d'auto-merge » et du « rebase
explicitement demandé » (`contraintes.md`), épinglée par `apps/api/tests/test_agent_permissions.py`.
Elle se déclenche aussi sur `gh pr merge` placé **après `&&`** dans une commande composée —
mesuré le 2026-10-13 avec `git merge-base --is-ancestor HEAD HEAD && gh pr merge --help` :
l'invite est apparue dans la fenêtre du mainteneur, et la commande n'a tourné qu'après. C'est ce
qui rend sûre la porte de merge **à une commande** de `cycle-pr` Étape 7 (« Le go, puis le
merge ») ; l'émulation du test, elle, ne sait pas le vérifier — elle ne découpe pas les commandes
composées, et le dit. Restent ouverts : un merge local suivi de
`git push origin main` (`main` n'est pas protégée côté GitHub), `gh api -X PUT …/pulls/<n>/merge`
et `gh -R … pr merge` — aucun `allow` ne les couvre, ils demandent en mode manuel et passent au
classifieur en mode auto.

Même logique de forme réécrite pour les `deny` : le harnais ne reconnaît ni `rtk read` ni `rtk grep`
comme des lectures de fichier, donc `Read(.env)` ne les arrête pas — deux `deny` Bash
(`rtk read *.env*`, `rtk grep *.env*`) ferment les neuf formes recensées par le même test
(citation, glob, `--max-lines`, `--tail-lines`, `grep`) — et attrapent aussi, collatéral accepté et
épinglé, `rtk read .env.example`, `rtk read infra/dev.env` et toute recherche dont le texte contient
`.env` (`os.environ`, `config.env`, `process.env`) : passer par l'outil Grep ou `git grep`, que RTK
ne réécrit pas. Restent ouverts, et la doc le dit (« isn't a security boundary around the
program ») : un glob sans `.env` littéral (`.en?`), `grep -r` sans nom de fichier, une indirection
par variable (`f=.env; cat "$f"`), une lecture par l'outil PowerShell (`Get-Content .env`, non
vérifiée), tout sous-processus qui ouvre le fichier lui-même.

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
