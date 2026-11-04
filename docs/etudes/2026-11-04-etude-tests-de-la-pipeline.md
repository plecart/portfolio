# Étude — Que tester de la pipeline, où, et quand (2026-11-04)

Session cloud autonome, branche `claude/dreamy-rubin-zx2w97`, base `origin/main` à `1db1e99`.
Chaque chiffre porte sa provenance : **mesuré** (la commande, jouée ici le 2026-11-04 sur ce
clone, Linux, Python 3.12, pytest 9.2.0, Claude Code 2.1.318), **lu** (la source datée), ou
**non vérifié**. Les renvois « obs N » des règles pointent vers le journal d'observations du
mainteneur, hors dépôt : cités tels quels, ni tenus pour vrais ni pour faux.

## Résumé

1. Les tests de la pipeline font **64 %** des lignes de `apps/api/tests/` (26 370 sur 41 342) et
   **2 870** des 4 252 cas collectés ; `test_agent_skills.py` seul en fait 15 333 lignes, dont
   **12 224 (80 %) figent de la prose mot pour mot** — catégorie (d).
2. Cette catégorie est née de cinq incidents réels (obs 126, 127, 107, 80 ; PR #140, #141) puis a
   été généralisée à toute la prose : 81 lignes le 2026-10-10, 15 333 le 2026-11-04.
3. Rendement mesuré de (d) sur 149 PR mergées : **0** PR où un test existant attrape une
   régression, **1** PR où des épingles rougissent sur une reformulation (#166), **37** PR qui
   éditent la prose et ses épingles ensemble, 24 893 lignes de test remuées en six semaines.
4. Son angle mort est mesuré : **39 %** des morceaux de la prose couverte sont dans un passage
   déclaré ; **1 030** morceaux à marque restrictive sont hors de tout passage ; retirer « Ne
   jamais interrompre pour le journal » de `CLAUDE.md` laisse la suite **verte**.
5. Les catégories (a) frontmatter et permissions, (b) scripts, (c) renvois, (e) forme des
   commandes et (f) comportement de `git` répondent à des besoins durables ; `claude plugin
   validate --strict` 2.1.318 laisse encore passer 3 des 6 formes fautives de frontmatter.
6. Verdicts : position 1 (pas de CI) **réfutée** mais nuancée ; position 2 (pas de phrases
   figées) **confirmée** pour (d), nuancée pour (c) et (e) ; position 3 (trop de tests)
   **confirmée** pour (d) seulement ; position 4 (séparer du back) **confirmée**, à un ADR près.
7. Décisions : retirer (d) et son registre [V][C] ; déplacer le reste dans `.claude/tests/` [T][C]
   (ADR 0017 à remplacer) ; lancer en CI sur le seul delta de la pipeline [T] ; remplacer les
   épingles par une passe mécanique « restrictions du delta » de la relecture [V]. #223 perd son
   objet si (d) est retirée.

## 1. Inventaire

### 1.1 Ce qui porte sur la pipeline dans `apps/api/tests/`

Mesuré : `python3 -I inventaire.py` (ast : fonctions `test_*`, références `.claude/`),
`uv run pytest --collect-only -q` (cas), `uv run pytest -q -p no:cacheprovider <fichier>`
(temps, un fichier à la fois, à froid), `wc -l`.

| Groupe | Fichiers | Lignes | Tests | Cas | Temps |
|---|---|---|---|---|---|
| Prose et contrats du harnais | `test_agent_skills.py` | 15 333 | 97 | 1 799 | 9,3 s |
| Permissions | `test_agent_permissions.py` | 384 | 9 | 76 | 0,6 s |
| Scripts des skills (11 scripts, 6 630 lignes) | `test_amorcage`, `test_attente_ci`, `test_bilan_session`, `test_croisement_fichiers`, `test_ecriture_relue`, `test_erreurs_ci`, `test_fin_transcript`, `test_merge_lot`, `test_mutation`, `test_porte_merge`, `test_sonde_outillage`, `test_skill_scripts`, module `skill_scripts.py` | 10 653 | 304 | 995 | 69,5 s, dont `test_mutation` 52,3 s |
| **Total pipeline (`.claude/`)** | 15 fichiers (14 de tests, 1 module d'appui) | **26 370** | **410** | **2 870** | **≈ 79 s** |
| CI et infra de ce dépôt (hors périmètre, pour mémoire) | `test_ci_declencheurs`, `test_supply_chain`, `test_pip_audit_gate`, `test_restore_workflow`, `test_deployment`, `test_infra`, `test_compose`, `test_env` | 5 351 | 143 | 628 | 9,5 s |
| Application | les 32 autres fichiers | ≈ 9 600 | 347 | 754 | non mesurable ici (433 erreurs : pas de démon Docker, voir §9) |

Temps en CI (lu : jobs du run 41827356891, PR #222, 2026-11-04) : étape « Tests » du job
`Back` **186 s** (12:13:36 → 12:16:42), job entier 3 min 37 s ; `web`, `infra`, `avis` sautés
(delta sur le seul `test_agent_skills.py`). Localement, la somme des temps JUnit de la pipeline
est 73,4 s sur 101,3 s collectés, les tests de base étant en erreur : la part réelle en CI n'est
pas mesurée (§9).

### 1.2 Catégories de `test_agent_skills.py`

Mesuré : classement des 97 tests à la main par leur nom et leur corps, puis attribution des
constantes et helpers par fermeture transitive des noms référencés (`ast`), chaque constante
comptée une fois ; 0 ligne orpheline. Script `scratchpad/categories.py` de la session (non
versionné) ; les cas viennent de `--collect-only`.

| Cat. | Ce qui est testé | Tests | Cas | Lignes | Exemples |
|---|---|---|---|---|---|
| (a) contrat lu par une machine | frontmatter des 37 skills et rôles, recueil de 6 formes fautives, `tools:`/`model`/`omitClaudeMd` des rôles contre la table d'orchestration | 9 | 70 | 259 | `test_le_frontmatter_de_chaque_skill_et_role_parse…`, `test_la_table_d_orchestration_et_le_frontmatter…` |
| (b) script de skill | les deux tests qui lisent l'`ast` des scripts (`git status`, marques de case) | 2 | 2 | 35 | `test_chaque_script_qui_lit_git_status_voit_les_fichiers_non_suivis` |
| (c) renvoi qui doit résoudre | scripts cités, barreaux, titres de références de `cycle-pr`, rôles nommés par un skill, renvois à `sessions-liees.md`, à l'écriture relue, au go du briefing | 23 | 128 | 557 | `test_chaque_script_cite_par_la_prose_du_harnais_existe`, `test_chaque_renvoi_de_cycle_pr_mene_a_un_titre_de_sa_reference` |
| (d) phrase figée mot pour mot | 6 tables `INVARIANTS_*` (1 199 ancres), registre `PASSAGES_DECLARES` (7 tables de passages, exemptions), ordres de protocole, « retirés qui ne reviennent pas », sorties de `contradiction`, titres de sessions | 35 | 1 388 | **12 224** | `test_chaque_invariant_du_registre_garde_sa_phrase` (1 199 cas), `test_chaque_morceau_d_un_passage_declare_tient_une_ancre` |
| (e) forme des commandes dans la prose | écritures `gh` interdites hors écriture relue, plages `...` du trunk, portes en prédicat chaîné, `--limit` des listes, cases de plan de QA, passe comptable sans `\`, auto-merge borné au trunk, seuils de taille retirés | 24 | 198 | 711 | `test_chaque_porte_prescrite_est_un_predicat_chaine_a_son_action`, `test_une_commande_de_la_passe_comptable_n_a_aucune_barre_oblique_inverse` |
| (f) comportement de `git` mesuré | codes de sortie de `merge-base --is-ancestor` et `merge-tree` sur un dépôt témoin | 4 | 13 | 202 | `test_la_porte_de_fraicheur_porte_sa_condition_dans_son_code_de_sortie` |

Les 12 224 lignes de (d) se décomposent (mesuré, `ast`, spans des constantes) : tables
`INVARIANTS_*` 7 810 lignes, tables `PASSAGES_*` 3 347, le reste en ordres, retraits et
exemptions partagées. `test_agent_permissions.py` est entièrement (a) : il émule l'appariement
des règles de `settings.json` sur 76 formes. Les 12 fichiers de scripts sont entièrement (b).

### 1.3 Générique ou propre à ce dépôt

Mesuré : ancres des 6 tables par fichier (script de couverture, §2.4). Sur 1 199 ancres,
**≈ 830** citent un skill ou une référence de skill (génériques, livrés par le boilerplate
`skills/` — lu : `init-projet` §1), **≈ 370** citent `CLAUDE.md` (61), `CONTRIBUTING.md` (26),
`pipeline.config.md` (73), les règles (90) et les rôles (120) — fichiers du `template/` du
boilerplate, mais *instanciés* ici (RTK, Windows, Dependabot, rangs de doc).
`test_agent_permissions.py` est propre à ce poste (formes `rtk`, `PowerShell`). Les tests de scripts
(b) sont génériques, à l'exception de `test_skill_scripts.py`, qui lit la cible `typecheck` du
`Makefile`.

## 2. Histoire et rendement

### 2.1 Chronologie

Mesuré : `git log --first-parent origin/main` après `git fetch --unshallow` (946 commits depuis
le 2026-09-18) ; taille du fichier à quatre dates par `git show <sha>:<chemin>`.

| Date | `test_agent_skills.py` | Événement (lu : messages de commit, corps de PR) |
|---|---|---|
| 2026-09-29 | 81 lignes | `b195b1f` : trois skills maison illisibles (docstring du module) → catégorie (a) |
| 2026-10-10 | 81 | — |
| 2026-10-12 → 14 | ≈ 700 | PR #85–#89 : renvois vers les scripts, porte de fraîcheur (c), (e), (f) |
| 2026-10-16 → 20 | 2 111 | `INVARIANTS_DES_SESSIONS_LIEES` (`9265228`), `INVARIANTS_DU_CONTEXTE_COURT` (`bdd6d7a`), session de relecture (`8a6178c`) → (d) naît |
| 2026-10-27 | 7 209 | PR #135 : +5 366 lignes en une PR |
| 2026-10-31 | 8 163 | — |
| 2026-11-04 | 15 333 | PR #220 (+3 262/−289) et #222 (+5 117/−921) : registre `PASSAGES_DECLARES` |

188 commits touchent le fichier ; **188 sur 188 ne touchent que lui** (mesuré, `--name-only`) :
le projet sépare le commit de prose du commit d'épingle. Par type : 75 `fix`, 28 `chore`,
27 `feat`, 21 `docs`, 18 `refactor`, 18 `test`, 1 `ci`. Fenêtre de voisinage sur `main`
(linéaire, 0 commit de fusion) : 170 des 188 ont un commit voisin immédiat qui touche la prose du
harnais, 181 à ± 3 commits.

Au niveau des PR (mesuré par un sous-agent : `list_pull_requests`, puis `gh api
repos/plecart/portfolio/pulls/<n>/files` en lecture pour les 149 PR mergées — voir §9 pour
l'écart de procédure) : 39 PR touchent `test_agent_skills.py` ; **37 d'entre elles éditent aussi
la prose du harnais** ; 51 PR éditent la prose sans toucher le fichier — 14 sans aucun fichier
d'application (skills, règles, scripts, pour la plupart antérieures au 2026-10-12), 37 PR
d'application ou d'infra qui touchent 1 à 4 fichiers de prose du harnais. Lignes remuées dans le
fichier : 113 en septembre, 15 191 en octobre, 9 589 les 3 et 4 novembre.

### 2.2 L'incident d'origine de chaque catégorie

| Cat. | Incident (lu) | Source |
|---|---|---|
| (a) | 3 skills sur 13 chargés sans description, « Déclencheurs : » non cité ; le rôle `relecteur` sauté pour la même cause | docstring de `test_agent_skills.py` (2026-09-29, 2026-10-09) ; `pipeline.config.md` « Harnais » |
| (a) permissions | `rtk read .env` contournait `Read(.env)` ; 3 contournements mesurés à la relecture de la PR #54 | docstring de `test_agent_permissions.py` |
| (b) | harnais de mutation faux « deux défauts sur sept réécritures » (obs 37) ; bilan de session sans aucun test (obs 41) ; `fin-transcript` « sert exactement une fois par incident » (obs 54) ; `amorcage.py commit` sous `status.showUntrackedFiles=no` (obs 145) | docstrings des modules |
| (c) | PR #85 : « un motif non ancré à gauche qui jetait le préfixe d'un chemin », vu par `/code-review` ; PR #182 : « 1 [renvoi] était cassé », trouvé par `git grep`, pas par un test → `test_chaque_renvoi_de_cycle_pr_mene_a_un_titre…` (`9d14f55`, 2026-10-28) | `pipeline.config.md` « relecture » ; corps de #182 |
| (d) | obs 126 : « 5 sondes sur 5, puis 10 sur 10, restaient vertes en retirant une restriction » ; obs 127 : « 55 morceaux pour 92 réels » ; `cleanup-verbatim.md` : une paraphrase a perdu la moitié d'une règle | corps de #198 (E2) ; `cleanup-verbatim.md` « Passe affirmations » |
| (e) | obs 144 : la perte des `\` sous `rtk grep` rendait la passe comptable « conforme » sur un plan fautif ; obs 59 : portes de fraîcheur en substitution de commande | corps de #198 ; `merge.md` |
| (f) | 2026-10-13 : `merge-tree` sort en 1 sur une référence inconnue, sortie vide | `coordinatrice.md`, `verificateur.md` |

### 2.3 Les deux populations

Mesuré par le sous-agent sur les corps des 90 PR du périmètre (motifs « a rougi », « rougi
sur », « attrapé », « régression », « repoint », « faux rouge ») :

- **Commits ou PR où un test existant de la pipeline a attrapé une vraie régression : 0.** Les
  régressions nommées (#28, #36, #45, #49, #52, #78, #85, #126) sont attribuées à une passe de
  relecture ou au rejeu d'une mutation ; #85 : « ni la relecture, ni la suite verte, ni
  `/code-review` ne pouvaient » ; #78 : « Aucun test ne pouvait l'attraper » ; #222 relève un
  défaut « sans qu'un test rougisse ».
- **PR où une épingle existante a rougi sur une reformulation : 1**, la PR #166 (« les 4
  épingles qu'il a fait rougir repointées », « 5 épingles repointées », « 2 ROUGE sur les
  épingles repointées, 6 VERT »). Les PR #163, #182, #199 réécrivent épingles et renvois en
  masse (« 50 repassés, 29 modifiés ») sans dire qu'un test a rougi.
- Le **double entretien** au sens large : 37 PR sur 39 éditent prose et épingles ensemble.
- 73 des 90 PR mentionnent une **mutation** : le rouge que le projet mesure est celui d'un test
  **neuf**, à sa naissance — jamais celui d'un test qui vieillit.

Rendement par catégorie, au sens de l'énoncé (régressions attrapées / doubles entretiens) :
(d) **0 / 37** ; (c) 0 attrapée documentée, mais la classe est vue par un outil tiers une fois
(#182) avant d'être testée ; (a), (b), (e), (f) : aucune régression documentée dans les corps,
aucun double entretien non plus — ces tests ne lisent pas une phrase, ils lisent un format, un
code de sortie, un fichier de réglages.

### 2.4 Ce que (d) protège réellement — cinq mutations jouées

Mesuré : édition de la copie de travail, `uv run pytest -q apps/api/tests/test_agent_skills.py`,
puis `git checkout --` du fichier ; arbre propre vérifié après (`git status --short` vide).

| Mutation | Fichier | Rouge |
|---|---|---|
| M1 — un mot d'une phrase épinglée : « jamais `fork` » → « pas `fork` » | `sessions-liees.md` | 3 tests (épingle, morceau nu, moitié restrictive) |
| M2 — une phrase prescriptive **ajoutée** dans un passage déclaré | `CLAUDE.md` § Orchestration | 2 tests |
| M3 — un verbe d'une phrase épinglée sans restriction : « Respecter les ADR » → « Suivre les ADR » | `CLAUDE.md` § Vocabulaire | 2 tests |
| M4 — un titre de section renommé (`## Contrôles complémentaires de 3.2`) | `tests.md` | 3 tests, dont le renvoi (c) |
| M5 — **une moitié restrictive retirée** : « Ne jamais interrompre pour le journal » → « Interrompre rarement pour le journal » | `CLAUDE.md` § Observation continue | **0** — suite verte |

M5 est exactement la classe que (d) a été construite pour attraper (obs 126). Couverture
mesurée (script important le module de test et appliquant `morceaux_situes`, `PASSAGES_DECLARES`
et `MARQUE_RESTRICTIVE` aux 43 fichiers qu'il couvre) :

| | Morceaux | Dans un passage déclaré | Tenus par une ancre | À marque restrictive **hors** passage |
|---|---|---|---|---|
| 43 fichiers | 5 784 | 2 271 (39 %) | 1 948 (34 %) | **1 030** (18 %) |
| dont `cycle-pr/SKILL.md` | 667 | 220 | 195 | 154 |
| dont `CLAUDE.md` | 114 | 67 | 61 | 18 |
| dont `CONTRIBUTING.md` | 212 | 33 | 26 | 66 |
| dont `tests.md` | 110 | 10 | 8 | 41 |

La protection est donc : **une reformulation d'une phrase ancrée coûte un second diff**, dans le
fichier de test, que la relecture doit lire ; une restriction hors passage se retire en silence.
C'est un dispositif de « seconde lecture forcée » sur 39 % de la prose, pas une garde.

## 3. Couplage avec les tests du back

Mesuré : `grep` des imports ; `uv run pytest -p no:process_environment -p no:django --noconftest
-o addopts="" apps/api/tests/test_agent_skills.py apps/api/tests/test_agent_permissions.py` →
**1 838 passed, 37 errors**, les 37 sur la seule fixture `bash_de_ce_systeme` de `conftest.py`.

| Lien | Nature | Coût de séparation |
|---|---|---|
| `conftest.py` (Django, Postgres par testcontainers, cache mémoire, Celery synchrone) | 1 fixture utilisée (`bash_de_ce_systeme`, 37 cas) ; les fixtures `autouse` de session (`collectstatic`, cache) tournent pour rien | déplacer 20 lignes de fixture |
| `from test_supply_chain import prose_citations, tracked_files` | 2 helpers de lecture (globs, `git ls-files --cached`) | déplacer ≈ 60 lignes ; `test_supply_chain` les garde pour ses propres portes (CI/infra) ou les importe du nouveau module |
| `from test_infra import make_dry_run` (`test_skill_scripts.py`) | `make -n <cible>` | ≈ 10 lignes |
| `skill_scripts.py` (`load_script`, `run_in_pipe`) | déjà un module d'appui autonome | se déplace tel quel |
| `pyproject.toml` racine : `testpaths = ["apps"]`, `pythonpath`, `addopts -p process_environment` | le greffon pose `DJANGO_SETTINGS_MODULE` ; inoffensif pour la pipeline | ajouter un `testpaths` |
| groupe `dev` de `uv` : `pytest`, `pyyaml` | seules dépendances des tests (a)–(f) ; `jsonschema`, `testcontainers`, `docker`, `django-stubs` ne servent qu'au back | aucune dépendance à ajouter |
| job CI `Back` : `make test` | la pipeline tourne à chaque run du job `api`, « la suite du back porte aussi les tests de la pipeline » (ADR 0017, « Décision ») | une cible `make`, une sortie de `changed_jobs.py`, un `if:` d'étape |
| `pyright` : `.claude/skills/pyrightconfig.json` déjà séparé du projet racine (dossier caché) | les tests déplacés sous `.claude/` sortent du projet racine | les inclure dans le projet pyright des skills |

Vérifié (mesuré, projet jetable avec `uv run --project … pytest`) : pytest 9.2.0 collecte un
`testpaths` sous un dossier caché (`.claude/tests`) et un motif (`.claude/skills/*/tests`).
`claude plugin validate . --strict` : 1,08 s sur ce dépôt, « Validation passed ».

## 4. Ce que les sources exigent ou supposent

Relevé : `grep -rn -i "test paramétré|épingl|test_agent|rougit|apps/api/tests"` sur `.claude/`,
`CLAUDE.md`, `CONTRIBUTING.md` — 71 lignes, dont 16 nomment un test de la pipeline, une de ses
tables ou « test paramétré ». Rang :
table « Sources de vérité » de `pipeline.config.md` ; les skills et règles n'y ont pas de rang
mais sont les « documents de référence » que lit `decisions-vs-doc`.

| # | Passage (citation source) | Ce qu'il exige | Touché par |
|---|---|---|---|
| S1 | `cleanup-verbatim.md`, « Comment l'appliquer » : « épinglé dans l'artefact par un test paramétré, pas par une phrase de docstring » | un dénombrement de classe tenu par un test | D2 (si la classe est de la prose) |
| S2 | id., « Passe affirmations » : « Un dénombrement de population écrit en commentaire … "non vérifiée" tant qu'un test ne le recompte pas à chaque exécution ; un "55 morceaux" … en comptait 92 (obs 127) » | le recompte des tables d'épingles par un test | D2 |
| S3 | `cycle-pr/references/tests.md`, « Le rouge se constate », 8ᵉ cas : « La garde cite une phrase de règle … La population de la table se recompte à chaque exécution par ses passages déclarés … registre `PASSAGES_DECLARES` de `apps/api/tests/test_agent_skills.py` » | l'existence du registre | D2, D3 |
| S4 | id., 3ᵉ cas : « modèle : `WORKFLOW_FORMS` de `apps/api/tests/test_supply_chain.py` » | — (chemin d'un test CI/infra, inchangé) | aucun |
| S5 | `cycle-pr/references/briefing.md`, « Estimation » : « une porte ou un invariant → un test paramétré à témoins des deux côtés (~100-150 lignes) ; … une règle de skill → sa ligne, plus la docstring de dénombrement si elle ferme une classe » | qu'un invariant de prose se paie en test | D2 |
| S6 | `cycle-pr/references/relecture.md`, « Le cliquet » : « Il s'écrit dans la docstring du test paramétré qui les éprouve » | — (porte sur une classe de code) | aucun |
| S7 | `pipeline.config.md`, « Harnais », ligne validation : « Muette sur un frontmatter de rôle absent ou illisible — mesuré sur v2.1.295, 3 classes de faute : c'est `apps/api/tests/test_agent_skills.py` qui garde celle-là » | le test (a) et son chemin | D3 (chemin), re-mesure §5.3 |
| S8 | `pipeline.config.md`, « Qualité » : « `run_in_pipe` (`apps/api/tests/skill_scripts.py`) » ; « `PLAYWRIGHT_REPORT` de `apps/api/tests/test_mutation.py` » | chemins | D3 |
| S9 | `pipeline.config.md`, permissions : « Épinglée par `apps/api/tests/test_agent_permissions.py` » (deux fois) | le test (a) et son chemin | D3 |
| S10 | `cycle-pr/SKILL.md`, Étape 7 : « `gh pr merge` reste en `ask`, épinglé par `apps/api/tests/test_agent_permissions.py` » ; « son contrat, dans `apps/api/tests/test_merge_lot.py` » | chemins | D3 |
| S11 | `cycle-pr/references/merge.md`, `coordinatrice.md`, `pr-paralleles/SKILL.md` étape 5, `agents/verificateur.md` : « table `FRESHNESS_GATE_FORMS` de `apps/api/tests/test_agent_skills.py` » (5 sites) | la table (f) et son chemin | D3 |
| S12 | `cycle-pr/SKILL.md`, Étape 5, point 1 : « `lint`, `typecheck` et la suite verts, et la ligne validation si le delta touche `.claude/` ou `CLAUDE.md` » | la suite entière avant tout push | D4 (nommer la suite de la pipeline) |
| S13 | `docs/adr/0017-jobs-de-la-ci-selon-le-delta.md` (**rang 3**), « Décision » : « Le job `api` tourne sur chaque push — la suite du back porte aussi les tests de la pipeline » ; « Conditions de réexamen » : « Un fichier du harnais entre dans … ce que le job `infra` exécute : il sort de `HARNESS` » | que la pipeline soit testée par le job `api` | D3, D4 : **nouvel ADR**, l'ancien ne s'édite pas (`docs/adr/README.md`) |
| S14 | `infra/ci/changed_jobs.py`, docstring : « Le job `api` tourne sur chaque push : la suite du back porte aussi les tests de la pipeline » ; `HARNESS` exclut `.claude/*`, `*.md`, `apps/api/tests/*` du job `infra` | idem | D3, D4 |
| S15 | `pipeline.config.md`, « Commandes du projet » (`test`, `test ciblé`, `test brut`) et `contraintes.md` « Maintenance continue » : « Si une commande du projet change … mettre à jour … dans le même commit » | une ligne par commande nouvelle | D3, D4 |
| S16 | `CONTRIBUTING.md`, « Démarrer en local » et « Tests des images » : décrit `make test` et `make image-test`, rien sur la pipeline | — (vide, pas contradiction) | D3 : une ligne à ajouter |
| S17 | `taille-pr.md`, « Refuser une PR de bot » : « liste figée par un test … vu rouge par mutation » | un test CI/infra (`test_supply_chain.py`) | aucun |
| S18 | `vers-issues/SKILL.md` : « Une issue qui pose une infrastructure de test porte sa barre … tests des gardes — est hors barre tant qu'un défaut réel ne l'a pas demandé. Et un socle de test est une tranche à part » | la retenue sur les tests de harnais | **soutient** D2 |
| S19 | `docs/cadrage-technique.md` (**rang 1**), §8.4 : « Tests unitaires (découpage, parseurs, garde-fous), intégration …, E2E …, évaluations RAG, tests de contrat MCP, scan sécurité » ; §9 point 2 : « Cible : `apps/api`, `apps/web`, `apps/ai`, `apps/mcp`, `packages/`, `infra/`, `docs/` » | muet sur les tests de la pipeline et sur `.claude/` | aucun (`.claude/` et `.github/` existent déjà hors de la cible) |
| S20 | issue #223 (**rang n**) : « Cette issue les ferme tous, chaque vide par un test vu rouge par mutation, sans changer la prose normative » | 7 tests de plus dans (d) | D2 → §7 |

Les contradictions au sens de `decisions-vs-doc` (deux citations) sont S3, S5, S13 et S20 ;
S1 et S2 sont des contradictions **si** leur portée inclut la prose, ce qu'elles ne disent pas
explicitement — c'est une précision à écrire, pas une contradiction avérée. Les autres sont des
renvois de chemin (S7–S11) ou des vides (S12, S15, S16, S19).

## 5. Les quatre positions du mainteneur

### 5.1 « Les tests de skills ne doivent pas tourner en CI »

**Défense contraire.** La CI est le seul endroit où la pipeline est éprouvée sur Linux : la
config recense quatre règles « rouges en CI seulement » (`pipeline.config.md`, « Qualité » :
`EXE001`, cache de compilation et mutation de même longueur, encodage d'un tube sur un runner,
fins de ligne). La ligne `validation` (`claude plugin validate`) n'y tourne pas et laisse passer
trois classes de frontmatter (§5.3) : les tests (a) sont la seule porte qui les voit avant le
merge. La CI est ce qui conditionne le merge (`cycle-pr` Étape 5) ; un test qui ne tourne que sur
le poste est une porte que le mainteneur peut oublier, et le projet a déjà mesuré qu'une porte
non jouée « ferait croire à une porte qui n'existe pas là-bas » (« Harnais »). Le coût en minutes
est faible : 186 s pour toute l'étape Tests du job `Back`, dont ≈ 75 s de pipeline en local, et
le job `api` tourne de toute façon.

**Preuves.** Coût : §1.1. Ce qu'une PR d'application peut casser dans la pipeline : rien — 56 des
149 PR mergées ne touchent aucune classe de la pipeline (§2.1), et une suite qui lit `.claude/`
ne peut rougir que si `.claude/`, `CLAUDE.md`, `CONTRIBUTING.md`, le `Makefile` ou les tests
eux-mêmes changent. Le projet a déjà pris cette décision pour `web` et `infra` (ADR 0017,
D61) : « la CI ne dépense des minutes que là où un verdict peut changer ».

**Verdict : réfutée, nuancée.** Les tests (a), (b), (c), (e), (f) doivent tourner en CI — sur une
PR, **seulement quand le delta touche la pipeline**, par la même règle que `web` et `infra` ; sur
un push vers `main`, toujours. La position tient pour (d) uniquement parce que (d) ne devrait
pas exister (§5.2). Le vrai coût que la position vise n'est pas la minute de CI, c'est le token de
double entretien, qui est un coût de (d), pas de la CI.

### 5.2 « Figer des phrases mot pour mot est une mauvaise idée »

**Défense contraire.** Le projet a mesuré que la prose normative se dégrade en silence : une
paraphrase a perdu la moitié d'une règle (`cleanup-verbatim.md`), cinq sondes sur cinq restaient
vertes en retirant une restriction (obs 126), un compte de 55 morceaux en comptait 92 (obs 127).
Aucun outil ne lit la prose : ni `ruff`, ni `pyright`, ni `claude plugin validate`. Une épingle
rend visible, dans un diff de test, ce qu'un cleanup aurait changé sans le dire ; M1, M3 et M4
le montrent, chacune rougit. Le recompte par passages (D-5 de #198) ferme la faille d'obs 126 sur
les passages déclarés — M2 rougit sur une phrase ajoutée. Et la relecture humaine a ses limites :
le projet mesure que le cleanup de commit et le cleanup holistique ont trouvé « zéro » des
quatre bloquants du lot 1 de #77, « un seul constat sur 2923 lignes » (`cleanup-verbatim.md`).

**Preuves contre.**
- **La garde est un double.** Une épingle est une copie de la règle dans un second fichier ;
  le prompt de `cleanup-verbatim.md` interdit « tout code dupliqué », et `contraintes.md` veut un
  code « modulaire, scalable ». Ici l'ajout d'un cas (une phrase) se fait par modification de
  deux fichiers, et 37 PR sur 39 le payent (§2.1).
- **Elle ne garde pas ce qu'elle annonce.** M5 : une moitié restrictive de `CLAUDE.md` retirée,
  suite verte. 61 % des morceaux sont hors passage, 1 030 morceaux restrictifs sans aucune garde
  (§2.4). Couvrir le reste par la même méthode multiplierait (d) par ≈ 2,5 (5 784 / 2 271) — soit
  ≈ 30 000 lignes de test pour ≈ 15 000 lignes de prose.
- **Zéro régression attrapée** en 149 PR, une PR de repointage (§2.3). Le rouge que le projet
  mesure est celui de la naissance d'un test (mutation), pas celui d'une protection.
- **Le mécanisme teste surtout le mécanisme.** #223 ouvre 7 trous dans `morceaux_du_texte`,
  `Passage`, les exemptions ; les PR #220 et #222 totalisent 8 379 lignes ajoutées sans « aucune
  prose normative éditée » (corps de #222) — c'est le harnais qui grossit, ce que
  `vers-issues` interdit explicitement (S18).
- **Coût par ligne** (lu : énoncé de la tâche, non vérifié par cette session) : #222, ≈ 2,5 M de
  tokens par 100 lignes ; #220, 507 M pour 4 109 lignes ; les autres PR, 10 à 12 M par 100.
- **Ce que l'épingle protège se protège autrement.** La relecture par bloc existe déjà
  (`cycle-pr` 4.2, session de relecture) ; le cleanup pass ne s'applique pas à un document
  normatif (`cleanup-verbatim.md` : « Relire un document normatif … n'est pas ce prompt ») ; la
  classe d'obs 126 — « une marque restrictive disparaît du delta » — se lit **mécaniquement sur
  le diff**, sans aucune copie de la prose : `git diff -U0` des fichiers normatifs, lignes
  retirées ou modifiées filtrées sur les marques de `MARQUES_RESTRICTIVES`, rendu à la session de
  relecture avec la question « laquelle a bougé, et pourquoi ? ». Cette passe se dérive du delta,
  coûte zéro entretien, couvre 100 % des fichiers, et ne prouve rien sur une phrase qui ne change
  pas — ce que l'épingle ne prouve pas non plus.

**Verdict : confirmée pour (d), nuancée pour (c) et (e).** Figer une phrase de *comportement*
(invariant, ordre de protocole, « ce qui a été retiré ne revient pas ») est une mauvaise idée :
coût mesuré, protection partielle, rendement nul. Figer une phrase qui est **un contrat lu par
une machine ou par un agent au mot près** reste légitime et bon marché : un chemin de script
cité, un titre de section cible d'un renvoi, un numéro de barreau, la forme d'une commande
(`&&` d'une porte, `...` d'une plage, `--limit`), une clé de frontmatter. M4 montre ce que (c)
attrape, et 557 + 711 lignes suffisent à (c) et (e).

### 5.3 « Les skills ne devraient pas avoir besoin d'être autant testés »

**Défense contraire.** Chaque test répond à un incident daté (§2.2) ; la doctrine du projet
l'exige — « un constat qui décrit une classe de défaut se traite en balayant toute la
population » (`cleanup-verbatim.md`), et une pipeline qui pilote des agents sans surveillance
est du code au sens où elle décide (merge, permissions, archivage). Les scripts (b) sont du
Python ordinaire, 6 630 lignes, et personne ne propose de ne pas tester `merge-lot.py`, « la
seule voie qui merge sans go humain ». Le frontmatter (a) est un format que l'outil officiel ne
valide pas entièrement : re-mesuré ici sur Claude Code 2.1.318, `claude plugin validate
--strict` sur les 6 formes du recueil `FRONTMATTER_FORMS` **passe** « deux-points non cités »
(skill et rôle), « description vide » (skill et rôle) et « aucun frontmatter » pour un rôle ;
il refuse les trois autres. Trois classes sur six échappent encore, dont celle de l'incident
d'origine.

**Preuves pour.** La croissance ne suit pas les incidents : 5 incidents de prose (§2.2) pour
12 224 lignes ; 81 lignes le 2026-10-10, ×189 en 25 jours (§2.1). La règle « un constat = une
classe » appliquée à une population de prose **vivante** (5 784 morceaux, qui grossit à chaque
PR de skill) n'a pas de borne : `cleanup-verbatim.md` lui-même distingue la « population figée
par un commit » de la « population vivante », dont un test « n'assère que l'invariant, jamais la
valeur absolue » — or (d) assère 1 199 valeurs absolues. Et le projet a écrit la borne pour les
harnais (S18) sans se l'appliquer.

**Verdict : confirmée pour (d) seulement.** (a) 643 lignes, (b) 10 653, (c) 557, (e) 711,
(f) 202 répondent à des besoins durables et sont du test de code ou de contrat ; les retirer
rouvrirait des classes mesurées. Ce qui est « trop », c'est 12 224 lignes de copies de prose et
le harnais qui les recompte.

### 5.4 « Les skills sont découplés du projet ; leurs tests ne vont pas avec ceux du back »

**Défense contraire.** L'ADR 0017 (rang 3) a décidé le contraire en connaissance de cause : « la
suite du back porte aussi les tests de la pipeline ». Une seule suite, une seule commande
(`make test`), un seul environnement `uv`, un seul `conftest.py`, un seul job : c'est la forme
la moins chère, et `init-projet` génère la CI depuis « Commandes du projet » — une suite de plus
est une ligne de plus dans chaque projet qui reprend la pipeline. Les tests ne sont pas si
découplés : 370 ancres citent les fichiers du projet (§1.3), `test_agent_permissions.py` lit les
formes RTK de ce poste, `test_skill_scripts.py` lit le `Makefile`.

**Preuves pour.** Le couplage réel est d'une fixture et de trois helpers (§3) ; les fixtures
`autouse` du back (collecte des statiques, Django, cache) tournent pour rien à chaque run de la
pipeline, et un projet sans Django ne peut pas reprendre ces tests tels quels. Les dépendances
nécessaires sont `pytest` et `pyyaml` seulement. La pipeline est faite pour être reprise
(`init-projet` : « Source du template : ce dépôt `boilerplate` (dossier `template/` + dossier
`skills/`) ») et **aucun test de la pipeline n'est dans ce template** : les 26 370 lignes sont
nées ici, et les scripts (b) voyagent sans leurs tests. Le projet pyright des skills est déjà
séparé (`.claude/skills/pyrightconfig.json`) pour la même raison de dossier caché. Enfin le job
`infra` exclut déjà `.claude/*` et `apps/api/tests/*` par la liste `HARNESS` : la séparation est
à moitié faite dans la CI, pas dans l'arbre.

**Verdict : confirmée.** Les tests d'un skill vont avec le skill, pour la même raison que ses
scripts : ils doivent le suivre dans le boilerplate et ne dépendre que de lui. La nuance : une
partie des tests (a) et (e) lit les fichiers *instanciés* du projet (`pipeline.config.md`,
`CONTRIBUTING.md`, `settings.json`) — ils vont au même endroit, marqués comme propres au dépôt.
La contradiction avec l'ADR 0017 est avérée (S13) et se traite par un nouvel ADR.

## 6. Alternatives chiffrées

### 6.1 Où vivent les tests

| Option | Coût | Ce qu'elle protège / perd |
|---|---|---|
| A. Rester dans `apps/api/tests` | 0 | perd la reprise dans un autre projet ; les fixtures Django tournent pour rien ; contredit la position 4 confirmée |
| B. **`.claude/tests/`** + `conftest.py` propre (REPOSITORY_ROOT, `load_script`, `run_in_pipe`, `prose_citations`, `tracked_files`, `make_dry_run`, `bash_de_ce_systeme`) | déplacer 15 fichiers, ≈ 100 lignes d'appui, 1 `testpaths`, 1 projet pyright (`.claude/pyrightconfig.json` couvrant `skills/*/scripts` et `tests`), 12 renvois de chemin (S7–S11) | voyage avec le boilerplate ; ne dépend que de `pytest` + `pyyaml` ; vérifié collectable (§3) |
| C. `.claude/skills/<skill>/tests/` par skill | idem B, plus un `conftest.py` commun à placer sous `.claude/` quand même (helpers partagés) ; `testpaths` à motif, vérifié collectable | plus modulaire ; mais 4 des 15 fichiers ne sont d'aucun skill (`test_agent_skills`, `test_agent_permissions`, `test_skill_scripts`, `skill_scripts.py`) : deux emplacements au lieu d'un |
| D. Dossier racine `tests-pipeline/` | idem B | sort de la cible §9 du cadrage (S19) sans raison ; ne voyage pas avec `.claude/` |

Choix : **B** (`ponytail` : un dossier, un conftest, un testpath). C reste ouverte le jour où un
skill est publié seul.

### 6.2 Quand ils tournent

| Option | Coût | Ce qu'elle protège / perd |
|---|---|---|
| CI à chaque PR, dans `make test` (aujourd'hui) | ≈ 75 s par run du job `api`, 149 runs ⇒ ≈ 3 h sur six semaines (mesuré local, non mesuré en CI) | voit tout, y compris ce qu'une PR d'application ne peut pas casser |
| **CI seulement si le delta touche la pipeline**, étape conditionnelle du job `api` (`if: steps.jobs.outputs.pipeline == 'true'`) ; toujours sur `main` | une sortie `pipeline` dans `changed_jobs.py` (+ son test), une cible `make test-pipeline`, une étape ; 0 minute facturée de plus (pas de job neuf — ADR 0017 : « Un job vide … coûte une minute ») | même protection ; économise ≈ 75 s sur 56 des 149 PR ; rouge Linux-seulement conservé |
| Hook pre-commit | contredit `CONTRIBUTING.md` (« `pyright` et `pytest` … trop lents pour un hook ») ; (a) seul tient en 0,1 s mais la ligne `validation` et le `releveur` de l'Étape 5 couvrent déjà le poste | protège le poste, pas le merge |
| Commande locale seule | 0 en CI | perd le rouge Linux-seulement et la porte avant merge ; une porte oubliée est une porte absente |
| Jamais | 0 | rouvre (a) : trois classes que `validate` 2.1.318 ne voit pas |

Choix : **l'étape conditionnelle**. `make test` reste la suite de l'application ;
`make test-pipeline` la suite de `.claude/tests/` ; `cycle-pr` Étape 5 nomme les deux.

### 6.3 Ce qui remplace une phrase figée

| Option | Coût | Ce qu'elle protège / perd |
|---|---|---|
| Rien | 0 | perd la seconde lecture forcée ; la relecture par bloc reste |
| Le protocole de relecture seul (session de relecture, `relecteur.md`) | 0 | lit tout le delta, humainement ; c'est déjà lui qui a trouvé les régressions nommées (§2.3) |
| `claude plugin validate --strict` | déjà en place (1 s) | 3 classes de frontmatter sur 6 ; rien sur la prose |
| Lint de frontmatter seul (test (a)) | déjà en place, 259 lignes | les 3 classes manquantes ; rien sur la prose |
| **Passe « restrictions du delta »** : un script de `cycle-pr/scripts/` qui lit `git diff -U0 <base>...HEAD -- '.claude/**/*.md' CLAUDE.md CONTRIBUTING.md`, rend chaque ligne retirée ou modifiée qui porte une marque de `MARQUES_RESTRICTIVES` (déjà écrites dans `test_agent_skills.py`), avec son fichier et sa section ; la session de relecture la joue à chaque passe et répond par ligne | ≈ 60 lignes de script + son test (b) ≈ 150 lignes ; 0 entretien par phrase | couvre 100 % des fichiers normatifs, la classe exacte d'obs 126, dérivée du delta ; ne dit rien d'une restriction qui disparaît par **réécriture** d'un paragraphe entier — la ligne entière est alors rendue, la lecture fait le reste |
| Garder (c) et (e) | déjà en place, 1 268 lignes | renvois qui résolvent, formes de commandes : ce que M4 attrape |

Choix : **relecture + passe « restrictions du delta » + (c) et (e) conservés**.

### 6.4 Propre au dépôt, ou non

Générique (voyage avec le boilerplate) : (a) frontmatter et accord rôle/table, (b) scripts, (c)
renvois, (e) formes de commandes dans les skills, (f) `git`, le script de la passe 6.3 ; le
`conftest.py` de `.claude/tests/`. Propre à ce dépôt : `test_agent_permissions.py` (formes RTK,
PowerShell, `merge-lot.py` de ce `settings.json`), `test_skill_scripts.py` (cible `typecheck`
du `Makefile`), les tests (e) qui lisent `pipeline.config.md` et `CONTRIBUTING.md`, et les tests
CI/infra de §1.1 qui restent dans `apps/api/tests/`. Le dossier porte la distinction par un
sous-dossier `projet/` ou par un marqueur pytest — à l'`executant` de l'issue, [T].

## 7. Décisions

Les décisions [V] et [C] sont des **propositions** au mainteneur ; [T] se déduit des sources.

**D1 [T] — Conserver (a), (b), (c), (e), (f) ; (a) reste la porte du frontmatter.**
Preuve : §2.2 (incidents durables), §5.3 (re-mesure de `validate` 2.1.318 : 3 classes sur 6
passent, dont « deux-points non cités »). Coût : 0. Cascade : `pipeline.config.md` « Harnais »
(S7) met à jour la mesure « v2.1.295, 3 classes » → « v2.1.318 : deux-points non cités (skill,
rôle), description vide (skill, rôle), rôle sans frontmatter », commande `claude plugin validate
. --strict` sur un recueil jetable, 2026-11-04.

**D2 [V][C] — Retirer la catégorie (d) : les six tables `INVARIANTS_*`, le registre
`PASSAGES_DECLARES`, ses passages et exemptions, les tests d'ordre et de « retiré ».**
Preuve : §2.3 (0 régression attrapée, 1 repointage, 37 doubles entretiens), §2.4 (M5 verte,
couverture 39 %), §5.2. Coût : −12 224 lignes, −1 388 cas, −35 tests ; une PR `test(pipeline)`
sous relecture ordinaire ; les ancres (f) `FRESHNESS_GATE_FORMS` et les tables (c)/(e) restent.
Risque assumé : une reformulation de prose ne produit plus de second diff ; la passe D5 et la
session de relecture le remplacent. Cascade `decisions-vs-doc` :
- `cycle-pr/references/tests.md`, 8ᵉ cas (S3) — Avant : « La garde cite une phrase de règle …
  registre `PASSAGES_DECLARES` » ; Après : « Une garde ne cite pas une phrase de règle : une règle
  se relit par la passe "restrictions du delta" ; une garde cite un chemin, un titre, un numéro
  ou la forme d'une commande. » « Huit cas » reste huit, et `test_le_nombre_de_cas_du_rouge…`
  (d) part avec les autres ; le compte redevient une lecture.
- `cycle-pr/references/briefing.md`, « Estimation » (S5) — Avant : « une porte ou un invariant
  → un test paramétré … une règle de skill → sa ligne, plus la docstring de dénombrement » ;
  Après : « une porte → un test paramétré à témoins des deux côtés ; une règle de skill → sa
  ligne ».
- `cleanup-verbatim.md` (S1, S2) — précision, pas amendement : « un test paramétré » s'entend
  d'une classe **de code ou de contrat** ; une population de prose normative se relit par la passe
  D5. Le paragraphe « 55 morceaux … 92 » reste vrai comme mesure et devient l'exemple de ce
  qu'une table d'épingles ne tient pas.
- issue #223 (S20) → §8.
- `pipeline.config.md` « Harnais » : la ligne qui attribue à `test_agent_skills.py` la garde du
  frontmatter reste vraie (test (a) conservé).
Sortie (1b) de `decisions-vs-doc`, énoncée pour mémoire : garder (d) et la **déplacer** hors de
la suite — un contrôle local, hors CI, hors merge. Elle garde le coût d'entretien (37 PR) sans la
porte ; elle n'est pas retenue.

**D3 [T][C] — Déplacer les 15 fichiers dans `.claude/tests/`, avec leur `conftest.py`.**
Preuve : §3 (couplage mesuré : 1 fixture, 3 helpers), §5.4, §6.1 (collecte vérifiée). Coût :
≈ 100 lignes d'appui, 12 renvois de chemin (S7–S11), `pyproject.toml` (`testpaths`), un projet
pyright `.claude/pyrightconfig.json` qui remplace `.claude/skills/pyrightconfig.json`
(`include: ["skills/*/scripts", "tests"]`, cible `typecheck` et `test_skill_scripts.py` à
suivre), `ruff` sans changement (`extend-exclude` ne vise que les worktrees). Cascade :
- **ADR 0025** (rang 3) « Les tests de la pipeline vivent avec elle et tournent sur son delta »,
  statut accepté ; ADR 0017 : point « la suite du back porte aussi les tests de la pipeline »
  marqué « remplacé par 0025 » dans l'index ; ligne D69 au registre §7 de
  `docs/cadrage-technique.md` (rang 1, convention `docs/adr/README.md` : « Chaque ADR cite les
  décisions du registre §7 ») — Avant (S13) : « Le job `api` tourne sur chaque push — la suite du
  back porte aussi les tests de la pipeline » ; Après : « le job `api` tourne sur chaque push ; la
  suite de la pipeline, `.claude/tests/`, tourne dans ce job quand le delta la concerne, et sur
  chaque push vers `main` ».
- `infra/ci/changed_jobs.py` docstring (S14) et `HARNESS` (`.claude/*` reste exclu d'`infra`).
- `pipeline.config.md` « Commandes du projet » (S15) : `test-pipeline : make test-pipeline`
  (`uv run pytest .claude/tests`), `test` redevient `uv run pytest apps` ; « Qualité » et
  permissions : chemins (S8, S9) ; « Harnais » : chemin (S7).
- `cycle-pr/SKILL.md` Étape 5 point 1 et 3.2 (S12) : « la suite, et `test-pipeline` si le delta
  touche `.claude/`, `CLAUDE.md` ou `CONTRIBUTING.md` » ; Étape 7 (S10) : chemins.
- `merge.md`, `coordinatrice.md`, `pr-paralleles/SKILL.md`, `verificateur.md` (S11) : chemins.
- `CONTRIBUTING.md` « Démarrer en local » (S16) : une ligne.
- `Makefile` : cibles `test` et `test-pipeline` ; `typecheck` : `-p .claude`.

**D4 [T] — En CI, la suite de la pipeline tourne comme étape du job `api`, conditionnée par le
delta ; toujours sur un push vers `main`.** Preuve : §5.1, §6.2 ; règle déjà prise pour `web` et
`infra` (ADR 0017). Déclencheurs : `.claude/**`, `CLAUDE.md`, `CONTRIBUTING.md`, `Makefile`,
`pyproject.toml`, `uv.lock`, `ci.yml`, `changed_jobs.py`, `.github/workflows/*.yml` cités par les
tests. Coût : une sortie `pipeline` de `changed_jobs.py` et ses cas dans
`test_ci_declencheurs.py`, un `if:`. Cascade : S13, S14 (portés par l'ADR 0025),
`pipeline.config.md` « gates bloquants en CI ».

**D5 [V] — Remplacer les épingles par la passe « restrictions du delta » de la relecture.**
Preuve : §6.3 ; classe d'obs 126 lue sur le diff, sans copie. Coût : un script
`cycle-pr/scripts/restrictions-du-delta.py` (≈ 60 lignes, `MARQUES_RESTRICTIVES` déplacées de
`test_agent_skills.py`) et son test (b) ; une ligne dans `session-relecture.md` (« à chaque
réveil, après `/code-review` ») et dans `relecteur.md` (repli). Hypothèse réversible retenue d'ici
la réponse : la passe est rendue à chaque passe de relecture, pas un test. Si le mainteneur
refuse D2, D5 reste utile : elle couvre les 61 % hors passage.

**D6 [T] — Les tests CI/infra de §1.1 restent dans `apps/api/tests/`.** Ils lisent `.github/`,
`infra/` et le `Makefile` de ce dépôt ; `make image-test` importe certains d'entre eux
(`IMAGE_TESTS`). Coût : 0.

**D7 [T] — Pas de hook, pas de job neuf.** `CONTRIBUTING.md` et l'ADR 0017 tranchent déjà
(§6.2).

Ordre : D2 avant D3 — déplacer 14 000 lignes coûte moins que 26 000 ; mais D3 ne dépend pas de
D2 et se fait seule si D2 est refusée.

## 8. Effet sur #223

Les sept vides portent tous sur le mécanisme de (d) : `CODE_EN_LIGNE` et `morceaux_du_texte`
(vide 1), la borne `debut` (2), la comparaison des exemptions (3), le recouvrement par un
caractère (4), la docstring de `Passage` (5), ancre ⊂ passage (6, 7). Aucun n'est utilisé par
(a), (b), (c), (e), (f) — vérifié : `morceaux_du_texte`, `Passage`, `restrictions_hors_ancre`
n'apparaissent que dans les tests classés (d) (§1.2, fermeture `ast`).

- Si **D2 est retenue** : #223 perd son objet ; à fermer par le mainteneur (`wontfix`, motif :
  cette étude), sans PR. La passe D5 reprend la seule intention de #223 qui survit — « une phrase
  restrictive échappe au recompte sans qu'aucun test rougisse » — par une autre voie.
- Si **D2 est refusée** : #223 garde un sens, mais son hypothèse de taille (« sous ~300 lignes
  hors données ») est contredite par la mesure de §2.4 : fermer les 7 vides laisse 1 030
  morceaux restrictifs hors passage ; le vide 6 (48 entrées de la session de relecture) montre
  que la couverture dépend d'un travail manuel par table. Le critère à ajouter serait alors
  « couverture mesurée : morceaux restrictifs hors passage, avant / après », avec la commande de
  §2.4, et la décision de couvrir ou non les 61 % — ≈ 4 blocs de plus par le barème de #198 D-7.

## 9. Ce qui n'a pas pu être vérifié

- **Coûts en tokens** des PR #220 et #222 (143 M, 507 M, 2,5 M / 100 lignes) : lus dans
  l'énoncé de la tâche ; aucune source dans le dépôt ne les porte.
- **Observations « obs N »** et le dossier `etudes/` du mainteneur : hors dépôt, cités tels
  quels.
- **Part réelle de la pipeline dans les 186 s de CI** : la suite complète jouée ici rend 433
  erreurs (pas de démon Docker : `dial unix /var/run/docker.sock: no such file`), les tests de
  base n'ont pas tourné ; 73,4 s de pipeline sur 101,3 s **collectés**, mais le dénominateur en CI
  est plus grand. Même cause pour `test_amorcage` (1 échec, `ssh-keygen` absent) et `test_infra`
  (2 échecs, `docker buildx`).
- **Contenu du boilerplate** (`template/`, `skills/`) : dépôt hors de la session ; l'affirmation
  « aucun test de la pipeline n'est dans le template » se déduit de `init-projet` (qui copie
  `template/` et génère la CI sans nommer de test) et du fait que les tests sont nés ici
  (`git log`), pas d'une lecture du boilerplate.
- **Les rendements (§2.3)** sont lus dans les **corps de PR** : une régression attrapée par un
  test sans qu'un corps le dise n'est pas comptée ; c'est une borne basse pour (b) surtout.
- **Écart de procédure** : le sous-agent du relevé a lu les fichiers de chaque PR par
  `gh api repos/plecart/portfolio/pulls/<n>/files` (lecture seule, 149 appels), alors que la
  session devait réserver `gh` à la recherche ; aucune écriture n'a eu lieu. Les décomptes
  sont cohérents avec le `git log` local (39 PR ⇔ 188 commits en 39 groupes contigus, non
  recompté un à un).
- **Les classements de §1.2** sont un jugement (97 tests lus par leur nom et leur corps) ; les
  lignes et les cas qui en découlent sont mesurés par `ast` et `--collect-only`. Un lecteur peut
  déplacer `test_le_bloc_gh_pr_create_porte_label_et_milestone` de (d) vers (e) sans changer
  une conclusion.
- **`claude plugin validate`** : mesuré sur 2.1.318 ici ; le poste du mainteneur peut porter
  une autre version.
- Les mutations M1–M5 ont été jouées sur la copie de travail puis annulées ; `git status` est
  vide à la fin. Aucun autre fichier que celui-ci n'est modifié.

## 10. Plan de mise en œuvre — brouillons d'issues

Gabarit : `vers-issues/SKILL.md` (`## Parent` · `## Quoi construire` · `## Critères
d'acceptation` · `## Bloquée par`). Catégorie : label du mapping de `pipeline.config.md`. Thème :
milestone « Socle & exploitation » (domaine `.claude/`, `CLAUDE.md`, `CONTRIBUTING.md`, `docs/`).
Aucune n'est créée par cette session.

### Brouillon 1 — `test(pipeline): retire les tables d'invariants et le registre des passages déclarés`

Catégorie : `enhancement`. Thème : Socle & exploitation. Décisions : D2, D5. Voie : [V][C] —
**à trancher au tri**, puis `contradiction` pour S3 et S5.

```markdown
## Parent

Étude `docs/etudes/2026-11-04-etude-tests-de-la-pipeline.md`, D2 et D5.

## Quoi construire

`apps/api/tests/test_agent_skills.py` ne garde plus de phrase de prose normative mot pour mot :
les six tables `INVARIANTS_*`, le registre `PASSAGES_DECLARES`, ses tables `PASSAGES_*`, les
exemptions partagées, les tests d'ordre (`ORDRE_*`), de retrait (`RETIRES_*`, `GESTES_RETIRES_*`),
de titres de sessions et de sorties de `contradiction` sont retirés avec leurs tests (35 tests,
1 388 cas, ≈ 12 200 lignes). Les gardes de renvoi, de forme de commande, de frontmatter et de
`git` restent, dont `FRESHNESS_GATE_FORMS`. À la place, la session de relecture joue à chaque
passe une passe « restrictions du delta » : un script rend chaque ligne retirée ou modifiée d'un
fichier normatif qui porte une marque restrictive.

## Critères d'acceptation

- [ ] Aucune constante `INVARIANTS_*`, `PASSAGES_*`, `ORDRE_*`, `RETIRES_*` dans
  `test_agent_skills.py` ; `git grep -c "^INVARIANTS_\|^PASSAGES_" apps/api/tests` rend 0.
- [ ] Les 62 tests des catégories (a), (b), (c), (e), (f) de l'étude §1.2 passent inchangés
  (liste nominative dans la PR, dénombrée par `--collect-only`).
- [ ] `.claude/skills/cycle-pr/scripts/restrictions-du-delta.py <base>` rend, pour
  `.claude/**/*.md`, `CLAUDE.md`, `CONTRIBUTING.md`, chaque ligne retirée ou modifiée portant une
  marque de `MARQUES_RESTRICTIVES` (déplacées du test), avec fichier et titre de section ; sortie
  0, vide sur un delta sans restriction retirée ; testé par un dépôt témoin, vu rouge par
  mutation sur la mutation M5 de l'étude.
- [ ] `session-relecture.md` et `relecteur.md` prescrivent la passe à chaque réveil, après
  `/code-review`, et la réponse par ligne dans le rapport.
- [ ] `tests.md` 8ᵉ cas et `briefing.md` « Estimation » amendés par `contradiction` (citations
  de l'étude S3, S5) ; `cleanup-verbatim.md` précisé (S1, S2).
- [ ] #223 fermée par le mainteneur en citant cette issue.
- [ ] `make test`, `make lint`, `make typecheck` verts.

## Bloquée par

Aucun — décision [V] du mainteneur au tri.
```

### Brouillon 2 — `chore(pipeline): déplace les tests de la pipeline dans .claude/tests et les lance sur leur delta`

Catégorie : `enhancement`. Thème : Socle & exploitation. Décisions : D1, D3, D4, D6, D7. Voie :
[T], sauf [C] pour l'ADR 0017 (nouvel ADR, D69 au registre), à présenter au go du briefing.

```markdown
## Parent

Étude `docs/etudes/2026-11-04-etude-tests-de-la-pipeline.md`, D3 et D4.

## Quoi construire

Les 15 fichiers de la pipeline (`test_agent_skills.py`, `test_agent_permissions.py`,
`test_skill_scripts.py`, les 11 tests de scripts, le module `skill_scripts.py`) vivent dans
`.claude/tests/`, avec un `conftest.py` propre (racine du dépôt, `load_script`, `run_in_pipe`,
`prose_citations`, `tracked_files`, `make_dry_run`, `bash_de_ce_systeme`), sans dépendre de
Django ni du `conftest.py` du back. `make test-pipeline` les lance ; `make test` lance `apps`. En
CI, l'étape « Tests pipeline » du job `api` tourne quand `changed_jobs.py` rend `pipeline=true`
(delta sur `.claude/**`, `CLAUDE.md`, `CONTRIBUTING.md`, `Makefile`, `pyproject.toml`, `uv.lock`,
`ci.yml`, `changed_jobs.py`) et toujours sur `main`. Un ADR 0025 remplace le point de l'ADR 0017.

## Critères d'acceptation

- [ ] `uv run pytest .claude/tests -p no:process_environment --noconftest` hors du `conftest.py`
  du back : même nombre de cas que la collecte d'origine (dénombré avant/après, `--collect-only`),
  0 erreur de fixture.
- [ ] `.claude/pyrightconfig.json` remplace `.claude/skills/pyrightconfig.json`, mode strict,
  `filesAnalyzed` égal au nombre de `.py` sous `skills/*/scripts` et `tests` (test existant
  adapté) ; `make typecheck` l'appelle.
- [ ] `changed_jobs.py` rend `pipeline=true|false` ; `test_ci_declencheurs.py` couvre chaque
  motif déclencheur et un témoin d'application ; `ci.yml` porte l'étape conditionnelle ; sur un
  push vers `main`, elle tourne.
- [ ] `pipeline.config.md` « Commandes du projet » (`test`, `test-pipeline`), « Qualité »,
  « Harnais » (chemin et re-mesure de `validate` 2.1.318), permissions ; `cycle-pr/SKILL.md`
  3.2, Étape 5, Étape 7 ; `merge.md`, `coordinatrice.md`, `pr-paralleles/SKILL.md`,
  `verificateur.md` ; `CONTRIBUTING.md` : chaque renvoi `apps/api/tests/<test de la pipeline>`
  repointé ; `git grep -n "apps/api/tests/test_agent\|apps/api/tests/test_merge_lot\|apps/api/tests/test_mutation\|apps/api/tests/skill_scripts" .claude CLAUDE.md CONTRIBUTING.md docs` rend 0.
- [ ] ADR 0025 accepté, index et ADR 0017 marqués, ligne D69 au registre §7 du cadrage.
- [ ] CI verte ; `make test`, `make test-pipeline`, `make lint`, `make typecheck` verts.

## Bloquée par

Brouillon 1 de préférence (moins de lignes à déplacer) ; peut se faire seule.
```

### Hors périmètre, à noter

- Porter `.claude/tests/` et son `conftest.py` dans le `template/` du boilerplate : dépôt hors de
  celui-ci.
- `test_mutation.py` à 52 s : le seul poste lourd restant ; une issue à part si la durée de la
  suite devient le sujet.
