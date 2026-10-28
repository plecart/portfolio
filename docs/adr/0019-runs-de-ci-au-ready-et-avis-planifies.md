# 0019 — Runs de CI au passage en ready, portes d'avis planifiées

- **Statut** : accepté
- **Date** : 2026-10-28
- **Décisions du cadrage** : D63 (`docs/cadrage-technique.md` §7) ; remplace quatre points de
  l'ADR 0017 (§ Décision) : « Le passage en ready ne déclenche plus de run », « seule l'ouverture
  d'une draft le saute », « `web` et `infra` partent après `api`, même rouge (`!cancelled()`) » —
  repris dans D61 — et « le scan Trivy tourne sur chaque PR qui touche un fichier hors du
  harnais » ; renverse la décision « portes à base d'avis (…) **sans horloge** » du 2026-10-13
  (#77, inscrite dans `.claude/pipeline.config.md`, « Qualité ») ; l'ADR 0017 reste accepté pour le
  reste — jobs selon le delta, annulation du run en cours — ; l'ADR 0014 est entier, scan avant
  chaque publication compris, et son point « pas de job planifié » visait la montée d'empreinte
  d'une image de base, pas une porte d'avis ; décisions du dialogue du 2026-10-28 (étude du coût
  de la CI, session `claude/great-knuth-gv4xbw`), chiffres corrigés après la relecture
  indépendante de la PR #178

## Contexte

L'ADR 0017 (2026-10-20) a conditionné `web` et `infra` au delta d'une PR, fait annuler le run en
cours au push suivant et retiré le run du passage en ready. Son estimation : 1 300 à 1 500
minutes par 14 jours, soit 2 800 à 3 200 par mois, contre 3 000 incluses dans l'offre GitHub Pro.

Mesure du 2026-10-28, relevée vers 11 h UTC, sur les 100 derniers runs du workflow `CI`, du 2026-10-24T14:40Z au
2026-10-28T10:57Z — `GET /repos/plecart/portfolio/actions/runs?workflow=ci.yml&per_page=100`,
puis `GET /repos/plecart/portfolio/actions/runs/<id>/jobs` pour chacun, chaque job qui a reçu un
runner arrondi à la minute supérieure, un job sans runner compté 0. Population vivante : ces
chiffres changent à chaque run ; l'invariant est la forme du workflow, jamais ces valeurs.

- **818 minutes facturées** en 3,85 jours, soit ≈ 6 400 par mois : `infra` 411, `api` 238,
  `web` 147, `publish` 22. Le dépassement du quota est facturé ; le mainteneur relève ≈ 20 $ sur
  le mois.
- **32 runs rouges sur 100, 362 minutes.** Steps en échec, 34 jobs : `Audit` du back (pip-audit)
  14, `Scan` (Trivy) 14, `Audit` du front (npm audit) 3, `Tests des images` 2, un job sans step.
  **Zéro rouge** de lint, de format, de types, de suite du back ou du front dans les jobs où ces
  steps ont tourné ; dans les 18 jobs où l'`Audit`, placé avant eux, a rougi, ils ont été sautés
  et n'ont pas pu rougir. Sur ce que la mesure voit, la CI rougit sur l'état des bases d'avis,
  rarement sur ce qu'une PR change.
- **221 minutes de rouges répétés** (27 %) : les 18 runs rouges dont le run précédent de la même
  branche était déjà rouge sur le même step — 272 minutes (33 %) si l'on compte tout run rouge
  qui en suit un autre, quel que soit le step. Les séries : la PR d'intégration #135, 9 rouges
  d'affilée dont 7 sur le même scan ; `feat/stockage-r2`, 6, sur trois steps ;
  `feat/table-logique`, 4 ; `main`, 4 ; `feat/contexte-court-lot-6b2`, 4, sur deux steps.
  Un rouge d'avis se corrige sur le trunk, et rien dans `cycle-pr` ne lit la CI entre deux pushes :
  l'Étape 3.5 pousse après chaque commit, le premier regard sur un run est l'Étape 5 ; le moniteur
  réveille la session sur un échec, mais le skill ne dit rien d'un réveil en plein cycle. La
  session enchaîne donc, et chaque push repaie un verdict déjà connu — le scan étant la dernière
  étape du job `infra`, un rouge de scan paie le job entier, de 7 à 14 minutes, médiane 8.
- **112 minutes de `web` et `infra`** sur les 16 runs où `api` était déjà rouge, par
  `!cancelled()` (ADR 0017, § Facteurs : un rouge du back ne masque pas un rouge du front).
- **La PR d'intégration #135 : 11 runs, 169 minutes**, dont 9 rouges. Chaque merge d'un lot dans
  la branche d'intégration est un `synchronize` de sa PR, dont le delta cumulé — `ci.yml`,
  `changed_jobs.py`, `pyproject.toml` — fait tourner les trois jobs, sur un contenu que la PR du lot
  venait de faire vérifier contre la même base.
- **Les PR de lot 7a à 8b : 4 à 7 runs chacune, dont un run sauté à l'ouverture de la draft, soit
  3 à 6 runs réels, aucun rouge.** Les runs suivent les pushes, et les pushes suivent les commits,
  pas les moments où un verdict peut changer.
- **Dependabot : 7 écosystèmes hebdomadaires.** Le 2026-10-27, 4 merges sur `main` en 3 minutes
  (runs 782 à 785), 61 minutes, tous rouges sur un avis `msgpack` ; 3 runs de PR, 34 minutes.
- **Jetons.** Chaque rouge réveille la session PR ; le tri « Rouge d'avis » de `cycle-pr` Étape 6
  est la procédure la plus chère du skill — vérifier que le trunk rougit aussi, reconstruire ses
  images dans un worktree jetable — et elle a été rejouée pour des avis qu'aucun commit de la PR
  n'avait fait naître.

## Facteurs de décision

- Le quota est dépassé ; chaque minute au-delà est facturée.
- **Aucune porte retirée du chemin vers la production** : le push sur `main` joue tout avant
  `publish`, et `publish` scanne avant de pousser (ADR 0014). Ce qui change, c'est quand une porte
  tourne sur une PR, jamais si elle tourne avant un déploiement. Ce facteur resserre celui de
  l'ADR 0017, « Aucune porte retirée ni allégée », au chemin vers la production : sur une PR, les
  portes d'avis sont allégées.
- Un rouge n'a de valeur que s'il porte sur ce que la PR change. Un avis porte sur l'état du monde,
  et se corrige sur le trunk.
- Un avis neuf doit être vu sous un jour, pas à la prochaine PR qui touche la pile concernée.
- **Zéro jeton ajouté par tour** : une règle que la forge applique vaut mieux qu'une phrase de
  skill qu'une session doit se rappeler à chaque push.
- Un rouge de plateforme — règle de lint que NTFS ne déclenche pas, fin de ligne, casse — reste
  possible (`cycle-pr` 3.2) ; mesuré : aucun parmi les jobs où ces steps ont tourné sur ces
  100 runs.

## Options considérées

**A. Quand une PR tourne**

1. **(a1) À chaque push, draft comprise** — ADR 0017, l'état en place.
2. **(a2) Pousser moins souvent**, aux seuls points où la session de relecture a besoin du SHA —
   une règle de `cycle-pr`.
3. **(a3) `[skip ci]` sur les commits intermédiaires** — la décision dans le message de commit.
4. **(a4) Aucun run en draft ; le passage en ready déclenche le premier, puis chaque push.**

**B. Les portes d'avis** — pip-audit, npm audit, Trivy

1. **(b1) Dans les jobs de chaque run** — l'état en place.
2. **(b2) Planifiées chaque jour sur `main` ; sur une PR, seulement si elle touche leurs
   entrées ; avant chaque publication, inchangé.**
3. **(b3) Retirées des PR, gardées avant publication seulement.**

**C. `web` et `infra` quand `api` est rouge** — tourner quand même (`!cancelled()`) ou attendre
un push vert.

**D. Cadence de Dependabot** — hebdomadaire ou mensuelle.

## Décision

**a4, b2, attendre, mensuelle.**

1. **Une PR en draft ne déclenche aucun run.** Le garde du job `api` saute toute draft, pas
   seulement son ouverture ; `ready_for_review` revient dans les types du workflow, et c'est lui qui
   produit le premier run — il ne rejoue plus un SHA couvert, puisqu'aucun run ne l'a couvert.
   Il tourne, comme tout run de PR, sur la référence de fusion que GitHub calcule à ce moment et
   ne recalcule pas si le trunk avance ensuite (ADR 0017, obs 51) : ce qu'il prouve de l'état
   combiné se lit à l'Étape 7 de `cycle-pr`, inchangée. Ensuite, chaque push tourne, comme
   aujourd'hui. `cycle-pr` Étape 5 sort du draft **puis** attend
   ce run (`attente-ci.py`) ; la première passe de relecture (4.2) relit un SHA sans verdict de CI.
   Après le passage en ready, **jamais de push sur une tête rouge sans tri** (Étape 6) : le
   moniteur qui réveille sur un échec est l'événement, et le tri précède le prochain push. Un
   lot d'une issue découpée suit la même règle ; sa PR d'intégration, en draft jusqu'au dernier
   lot, ne tourne plus à chaque merge de lot.
2. **Les portes d'avis sortent des jobs de PR.** Un workflow planifié, chaque jour sur `main`
   (`schedule`, plus `workflow_dispatch`), joue `make audit`, `make web-audit`, puis `make build`
   et `make scan`. Sur une PR, un job `avis` tourne si le delta touche une **entrée** d'un avis —
   `pyproject.toml`, `apps/api/pyproject.toml`, `uv.lock`, `apps/web/package.json`,
   `apps/web/package-lock.json`, `infra/*/Dockerfile`, `.trivyignore.yaml`,
   `infra/ci/pip-audit-exceptions.toml`, `infra/ci/pip_audit_gate.py`, le `Makefile`, qui définit
   les cibles, l'image Trivy et ses drapeaux, et le workflow planifié lui-même —, réponse de
   `infra/ci/changed_jobs.py`, comme pour `web` et `infra` ; les
   PR de Dependabot le font donc tourner. Sur un push vers `main`, tout tourne, et `publish`
   scanne avant de pousser, inchangé. Un rouge du run planifié se traite sur le trunk par la voie
   courte de `cycle-pr` — bump ou exception datée — ; le tri « Rouge d'avis » de l'Étape 6 devient
   celui du trunk, et cesse d'être une procédure de PR.
3. **`web` et `infra` attendent un `api` vert** : `needs: api` sans `!cancelled()`, sur une PR
   comme sur `main`. Un `api` rouge appelle un push, et ce push montrera `web` et `infra`.
4. **Dependabot passe en mensuel** pour ses sept entrées. Les mises à jour de sécurité ne suivent
   pas l'intervalle : elles partent à l'avis (doc GitHub « Dependabot security updates », lue le
   2026-10-28). Elles partent de la base d'avis de GitHub, qui ne couvre pas les images Docker
   (supposé, à confirmer à l'implémentation) : un avis sur une image se voit au scan planifié et
   se traite par une montée de version à la main. Les trois entrées Docker se regroupent en une entrée `directories` si la doc de
   l'option confirme à l'implémentation qu'un groupe y couvre les trois répertoires ; sinon elles
   restent trois.

## Conséquences

**Positives**

- Une PR tourne au passage en ready puis à chaque correction : 2 à 3 runs au lieu de 3 à 6 sur
  les PR de lot mesurées ; une PR d'intégration, 1 à 2 au lieu de 11.
- Sur les 31 jobs d'avis rouges mesurés, 5 étaient sur `main`, où tout tourne encore, et 22 sur
  des PR dont le delta touchait une entrée du job `avis` — verrou, `pyproject.toml`,
  `.trivyignore.yaml`, Dockerfile —, où il aurait tourné aussi : la décision 2 seule n'en retire
  que 4. Ce sont la décision 1 et la règle « jamais de push sur une tête rouge » qui font tomber
  les 221 minutes de rouges répétés ; la décision 2 retire aux autres PR un rouge qui ne vient pas
  d'elles, et sort le tri « Rouge d'avis » du cycle de PR.
- Estimation combinée, non mesurée : 350 à 450 minutes par 3,85 jours au lieu de 818, soit
  ≈ 2 700 à 3 500 par mois, autour du quota — à re-mesurer au premier mois, même commande ; la
  projection vaut moins que le relevé.
- `publish` reste gardé par les trois jobs et par son propre scan.

**Négatives, assumées**

- Un rouge de plateforme se voit au passage en ready, après les passes de relecture, et non plus
  au premier push : mesuré, aucun parmi les jobs où ces steps ont tourné sur 100 runs — les 18
  jobs rougis à l'`Audit` ne les ont pas joués.
- Le run du passage en ready tourne sur la référence de fusion de ce moment, que GitHub ne
  recalcule pas si le trunk avance ensuite (obs 51) : la porte de fraîcheur de l'Étape 7 reste la
  seule preuve de l'état combiné, comme pour tout run de PR aujourd'hui.
- La première passe de relecture n'a pas de verdict de CI à côté du SHA qu'elle relit.
- Un avis neuf est vu par le run planifié du lendemain, et par les seules PR qui touchent ses
  entrées — et non plus par chaque push de chaque PR. Le trunk peut rougir un matin sans qu'une
  PR l'ait vu venir ; c'est déjà ce qui arrivait, sur toutes les PR à la fois.
- Sur `main`, un `api` rouge cache `web` et `infra` jusqu'au push correctif.
- Une mise à jour de version non liée à un avis attend jusqu'à un mois.

**Ce que l'implémentation touche** — à découper en issues depuis cet ADR :

- `.github/workflows/ci.yml` : garde du job `api`, types du `pull_request`, `needs` de `web` et
  `infra`, retrait des steps `Audit` et `Scan` au profit d'un job `avis` conditionné ; un workflow
  planifié ; `infra/ci/changed_jobs.py` et sa sortie `avis` ;
  `apps/api/tests/test_ci_declencheurs.py`, dont le test qui interdit toute prose citant
  `ready_for_review` s'inverse : la prose doit dire que le ready déclenche le run.
- `.claude/skills/cycle-pr/SKILL.md` : encadré de l'Étape 2, Étape 5 (`gh pr ready` puis
  `attente-ci.py`), Étape 6 (règle de la tête rouge, tri d'avis déplacé au trunk) ;
  `.claude/skills/cycle-pr/scripts/attente-ci.py` (sortie 3, « draft jamais repoussée ») ;
  `.claude/pipeline.config.md`, « Qualité » (ligne « sans horloge », liste « gates bloquants en
  CI ») et commentaires des lignes `audit`, `web-audit`, `scan` ; `CONTRIBUTING.md`, « Audit des
  dépendances » et « Mises à jour des dépendances ».
- `.github/dependabot.yml` et `apps/api/tests/test_supply_chain.py`, qui épingle la cadence
  hebdomadaire (`UPDATE_POLICY`) et rejette la forme « cadence mensuelle » (`DEPENDABOT_FORMS`) :
  les deux s'inversent.

## Comparaison des options

| | (a1) Chaque push | (a2) Pousser moins | (a3) `[skip ci]` | (a4) Au ready, puis chaque push |
|---|---|---|---|---|
| Runs par PR de lot mesurée | 3 à 6 | 2 à 3 | 2 à 3 | 2 à 3 |
| Qui applique la règle | — | la session, à chaque commit | la session, dans chaque message | la forge |
| Jetons par tour | aucun | une décision par push | un marqueur dans chaque message de commit | aucun |
| Rouge de plateforme vu | au premier push | au premier push gardé | au dernier commit | au ready |
| PR d'intégration | un run par lot | un run par lot | selon les merges de lot | un run au dernier lot |
| Verdict | en place, écarté | repli si a4 ne tient pas | écarté | **retenue** |

| | (b1) Chaque run | (b2) Planifiées + entrées + publication | (b3) Publication seulement |
|---|---|---|---|
| Avis neuf vu sous | le prochain push de n'importe quelle PR | un jour | la prochaine publication |
| Rouges de PR nés hors de la PR | 26 des 34 jobs mesurés | sur les seules PR qui touchent une entrée | aucun |
| Procédure « Rouge d'avis » | sur chaque PR touchée | sur le trunk, une fois | sur `main`, au pire moment |
| Verdict | en place, écarté | **retenue** | écarté : trop tard |

## Conditions de réexamen

- Un rouge de plateforme réapparaît au passage en ready après une relecture : ajouter un
  `workflow_dispatch` que la session peut lancer sur une draft quand elle veut ce verdict.
- Un rouge du run planifié reste sans suite plus d'un jour : lui faire ouvrir ou mettre à jour
  une issue (un workflow à part, `issues: write`), ou le lire au démarrage de `triage`.
- Le quota cesse d'être une contrainte, ou GitHub change sa facturation : a1 redevient
  envisageable pour voir un rouge de plateforme plus tôt.
