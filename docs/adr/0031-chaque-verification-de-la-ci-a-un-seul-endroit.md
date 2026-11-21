# 0031 — Chaque vérification de la CI tourne à un seul endroit

- **Statut** : accepté
- **Date** : 2026-11-21
- **Décisions du cadrage** : D75 (`docs/cadrage-technique.md` §7) ; remplace, dans l'ADR 0014,
  « après `api`, `web` et `infra` » et « il récupère `dist` du job `web` par artefact » (§ Décision,
  point « Publication ») et « Une image publiée a passé toute la CI » (§ Conséquences) ; dans
  l'ADR 0017, « Un push vers `main` publie et déploie : tout y tourne », « Dans le doute, le job
  tourne » et « Aucune porte retirée ni allégée » (§ Facteurs de décision), « liste d'exclusion »
  et « Sur un push vers `main`, tout tourne » (§ Décision) ; dans l'ADR 0019, « **Aucune porte
  retirée du chemin vers la production** : le push sur `main` joue tout avant `publish` » et « Un
  avis neuf doit être vu sous un jour » (§ Facteurs de décision), « chaque jour sur `main` » et
  « Sur un push vers `main`, tout tourne » (§ Décision, point 2) ; dans l'ADR 0025, « sur un push
  vers `main`, toujours » (§ Décision) ; ces ADR restent acceptés pour le reste ; décision du
  mainteneur du 2026-11-21 (étude du coût de la CI), interrogatoire et go du briefing de #278

## Contexte

La CI tourne deux fois par changement : sur la PR, puis de nouveau au push sur `main`, où tout
rejoue avant `publish` (ADR 0017, ADR 0019). Le dépôt est privé (cadrage D11), et ses minutes sont
facturées au-delà des ≈ 3 000 comprises dans GitHub Pro ; depuis le 2026-11-20, les jobs ne
démarrent plus (limite de dépenses ou paiement refusé).

Mesure de départ — **population vivante**, relevée le 2026-11-21 vers 09 h UTC : 639 runs créés
du 2026-10-22T04:37Z au 2026-11-21T05:38Z (30,0 jours). Commande, dans le dossier de l'étude
(`etudes/2026-11-21-cout-ci/`, hors dépôt) : `python collect.py 2026-10-22 runs.json`, puis
`python analyse.py runs.json`. Minutes facturées estimées par job,
`ceil((completed_at − started_at)/60)` — l'arrondi par job à la minute supérieure est celui de la
doc « Actions runner pricing », lue le 2026-11-21 :

- **≈ 6 768 minutes / 30 jours**, contre ≈ 3 000 comprises ;
- une PR verte dure 11,0 min en médiane, un push sur `main` 15,5 min ;
- les jobs `api`, `web`, `infra` et `avis` du push sur `main` font 2 253 min ;
- les tests des images et l'e2e à deux tailles font 32 % de la facture, et tournent deux fois
  par changement.

## Facteurs de décision

- Le quota est dépassé ; le dépôt reste privé, et aucun runner n'est auto-hébergé (décision du
  mainteneur, 2026-11-21).
- **Une vérification tourne à un seul endroit.** Ce qui juge un changement tourne sur sa PR ; ce
  qui ne dépend d'aucun changement tourne à heure fixe. Le push sur `main` livre.
- La PR est fusionnée au trunk courant par chacun de ses jobs (ADR 0029) : son verdict porte sur
  l'état combiné, pas sur la tête seule. La porte de fraîcheur de `cycle-pr` (Étape 7) refuse un
  merge dont le trunk a bougé depuis ce run.
- La fumée (`fumee`) démarre la pile de production depuis les images publiées avant tout
  déploiement : elle reste la preuve finale du chemin vers la production.
- Un job sauté à tort cache un rouge ; le job `infra` d'une PR tourne donc sur ce que les images
  définissent ou exécutent, liste tenue par des tests paramétrés, et un chemin que `git` met entre
  guillemets le fait tourner.

## Options considérées

1. **(a) Payer** : un budget Actions, CI inchangée.
2. **(b) Rendre le dépôt public** : les runners standard y sont gratuits ; contredit le cadrage
   § 3 et D11.
3. **(c) Un seul endroit par vérification** : le push sur `main` ne fait que livrer, `infra` par
   inclusion, l'e2e mobile, les tests des images et les avis à heure fixe.
4. **(c′) Variante prudente** : garder `api` sur le push vers `main`.

## Décision

**(c).**

1. **Le push sur `main` livre, rien d'autre** : `publish`, `fumee`, `deploy`, dans cet ordre.
   `api`, `web`, `infra` et `avis` ne tournent que sur une PR prête, les tests de la pipeline
   avec `api`. `publish` ne dépend d'aucun job de vérification : il installe et compile le front,
   construit les images, les scanne (`make scan`), les pousse et applique la rétention. Il écrit
   le cache des couches que les jobs de PR et le run hebdomadaire relisent : un cache écrit sur
   la branche d'une PR n'est pas lisible depuis `main`.
2. **`infra` par inclusion** : sur une PR, il tourne si le delta touche ce que les images
   définissent ou exécutent — `infra/`, les Dockerfiles, les fichiers Compose, les manifestes et
   verrous, `.python-version`, `.dockerignore`, `.env.example`, les migrations du back, les
   modules d'appui des tests des images, ce qui décide des jobs — ou un chemin entre guillemets
   (`infra/ci/changed_jobs.py`).
3. **Sur une PR, l'e2e ne joue que le projet `desktop`** ; Lighthouse reste sur la PR.
4. **Un run hebdomadaire sur `main`**, le lundi à 05:37 UTC et à la main (`hebdo.yml`) : les
   portes d'avis (`avis.yml` — `make audit`, `make web-audit`, `make build`, `make scan`), les
   tests des images (`make image-test`) et l'e2e du projet `mobile`, en trois jobs. Le job `avis`
   d'une PR appelle le même `avis.yml` quand le delta touche une entrée d'un avis. Un rouge
   planifié se traite sur le trunk (`cycle-pr` Étape 6, « Rouge d'avis »).
5. Le contrôle des auteurs est un pas du job `api`, non un job : un job compte au moins une minute.

## Conséquences

**Positives**

- Cible estimée, non mesurée : ≈ 3 300 minutes un mois de vague ; ≈ 9 min par PR de front,
  ≈ 3 min par PR de back, ≈ 8 min par push sur `main`.
- Le push sur `main` publie et déploie plus vite : ses jobs de vérification ne le précèdent plus.

**Risques acceptés**

- Un merge dont le trunk a bougé après le run de PR n'est plus retesté avant la livraison ; la
  porte de fraîcheur de `cycle-pr` Étape 7 le couvre pour une PR de session.
- Des PR de Dependabot mergées d'affilée ne sont plus éprouvées ensemble : la fumée, puis le run
  hebdomadaire, sont leur seule épreuve commune (interrogatoire de #278).
- Un avis neuf est vu sous une semaine, ou à la prochaine PR qui touche une entrée d'un avis ;
  le scan de `publish` reste avant chaque publication.
- Une régression des images ou du mobile, née d'une PR qui ne touche pas leurs entrées — pour le
  mobile, toute PR —, est vue à la fumée ou au run hebdomadaire.

## Conditions de réexamen

- **Re-mesure quatre semaines après le merge de la PR #279** (date du merge + 28 jours), par la
  commande de la mesure de départ ; le résultat entre au bilan de la première vague après cette
  date. La cible est une estimation, pas une porte.
- Le quota cesse d'être une contrainte, ou le dépôt devient public : le push sur `main` peut
  rejouer les vérifications, et l'e2e mobile revenir sur la PR.
- Un rouge du run hebdomadaire naît d'une PR mergée qui ne touchait pas les entrées des images ou
  du mobile : resserrer la liste d'inclusion d'`infra`, ou rendre le mobile à la PR de front.
