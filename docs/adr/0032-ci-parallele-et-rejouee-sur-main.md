# 0032 — La CI d'un dépôt public : vérifications en parallèle, rejouées sur `main`

- **Statut** : accepté
- **Date** : 2026-11-24
- **Décisions du cadrage** : D78 (`docs/cadrage-technique.md` §7) ; remplace, dans l'ADR 0017,
  « **Option b** » et « La première étape du job `api` passe […] à `infra/ci/changed_jobs.py` »
  (§ Décision), « `web` et `infra` partent après la fin d'`api`, 2,4 minutes en médiane »
  (§ Conséquences), les verdicts « Écartée : le coût » et « **Retenue** » (§ Comparaison des
  options) ; dans l'ADR 0019, « `web` et `infra` attendent un `api` vert » (§ Décision,
  point 3) ; dans l'ADR 0031, « **Une vérification tourne à un seul endroit.** » et « Le push sur
  `main` livre. » (§ Facteurs de décision), les points 1, 3 et 4 (§ Décision), « Le push sur
  `main` publie et déploie plus vite : ses jobs de vérification ne le précèdent plus », « Un merge
  dont le trunk a bougé après le run de PR n'est plus retesté avant la livraison », « Des PR de
  Dependabot mergées d'affilée ne sont plus éprouvées ensemble », « Un avis neuf est vu sous une
  semaine » et « Une régression des images ou du mobile […] est vue à la fumée ou au run
  hebdomadaire » (§ Conséquences), « Re-mesure quatre semaines après le merge de la PR #279 » et
  « Un rouge du run hebdomadaire naît d'une PR mergée » (§ Conditions de réexamen) ; ces ADR
  restent acceptés pour le reste ; interrogatoire de #285 du 2026-11-24, décisions D1 à D8 du
  corps de l'issue

## Contexte

Le dépôt est public depuis D76 (2026-11-21). Les ADR 0017, 0019 et 0031 ont ordonné la CI sous
la contrainte du quota de minutes de GitHub Pro, et chacun avait écrit sa condition de réexamen
pour ce cas : « Le quota cesse d'être une contrainte (offre changée, dépôt public) » (0017),
« Le quota cesse d'être une contrainte, ou le dépôt devient public » (0031).

Gratuité vérifiée à la source le 2026-11-24 : doc GitHub « GitHub Actions billing »
(`docs.github.com/en/billing/concepts/product-billing/github-actions`), les runners standard
sont gratuits dans un dépôt public, sans quota ; les « larger runners » y restent facturés, et
aucun job du dépôt n'en utilise (`ubuntu-latest` partout). Doc « Actions limits » : 40 jobs
simultanés en Pro.

Durées en médiane des jobs verts des 30 derniers runs de `ci.yml` et `hebdo.yml` — **population
vivante**, relevée le 2026-11-24, un ordre de grandeur : `api` 3 min, `web` 13, `infra` 13,
`avis` 10, `publish` 7,5, `fumee` 1, e2e `mobile` 3, tests des images 6.

## Facteurs de décision

- Les minutes ne coûtent plus rien ; l'attente, si. Une règle qui n'avait que le quota pour motif
  tombe ; une règle qui en a un autre — la durée, le bruit, les jetons d'une session — reste.
- Un job sauté à tort cache un rouge (ADR 0017, inchangé).
- Le verdict d'une PR porte sur l'état combiné au trunk de son run (ADR 0029). Sur `main`, l'état
  livré est le commit poussé : c'est lui qu'une vérification rejouée juge.
- La fumée reste la seule preuve en CI que la pile de production démarre (ADR 0031).
- Un avis neuf doit être vu sous un jour (ADR 0019, § Facteurs de décision) : motif de sécurité,
  que l'ADR 0031 avait reculé au lundi pour le seul quota, et que cet ADR rétablit.
- Chaque rouge réveille la session PR : un rouge qui ne porte pas sur ce que la PR change coûte
  des jetons sans rien juger (ADR 0019, § Contexte, « Jetons »).

## Options considérées

**A. L'ordre des jobs d'une PR**

1. **(a1) `needs: api`** — l'état en place (ADR 0017 option b, ADR 0019 point 3).
2. **(a2) Un job `changes`** lit le delta, et toutes les vérifications en dépendent et partent
   ensemble — l'option (a) de l'ADR 0017, écartée alors pour sa minute facturée.

**B. Le push sur `main`**

1. **(b1) Il livre seulement** — l'état en place (ADR 0031 point 1).
2. **(b2) Les vérifications selon le delta précèdent `publish`.**
3. **(b3) Les vérifications selon le delta tournent pendant `publish`, et `deploy` attend leur
   vert.**

**C. Ce qui tourne à heure fixe** — e2e `mobile`, tests des images, portes d'avis : sur la PR, au
run planifié, ou les deux.

## Décision

**a2, b3.**

1. **Un job `changes`** lit le delta par `infra/ci/changed_jobs.py`, règle inchangée — `infra`
   par inclusion compris — et rend `web`, `infra`, `avis` et `pipeline`. `api`, `web`, `mobile`,
   `infra` et `avis` en dépendent et partent ensemble, chacun selon sa sortie : `api` toujours,
   `mobile` sur la sortie de `web`. Aucun job de vérification n'en attend un autre. Une PR en
   draft ne tourne toujours pas (ADR 0019 point 1) : le garde est sur `changes`, et un job sauté
   saute ceux qui l'attendent.
2. **Sur un push vers `main`**, `changes` lit le delta du push — `github.event.before` à
   `github.sha` : un merge par rebase pousse plusieurs commits d'un coup — ; `api`, et selon le
   delta `web`, `mobile` et `infra`, tournent **pendant** `publish`. `fumee` suit `publish` seul.
   `deploy` attend `fumee` et chaque vérification : il part quand `fumee` et `api` sont verts, et
   `web`, `mobile` et `infra` verts ou sautés ; un rouge le bloque. `avis` ne tourne pas sur
   `main` : `publish` scanne avant de pousser, et un avis porte sur l'état du monde, pas sur le
   merge. Les tests de la pipeline suivent `api`, sur la sortie `pipeline` du delta.
3. **L'e2e `mobile` revient sur la PR et sur `main`**, dans un job à part, parallèle,
   déclenché comme `web` ; `web` garde le projet `desktop` et Lighthouse.
4. **Les tests des images restent dans `infra`**, déjà sur la PR, et le suivent sur `main` ; pas
   de job à part, qui reconstruirait les images qu'`infra` construit.
5. **Le run planifié joue chaque jour sur `main` les seules portes d'avis**, et à la main
   (`workflow_dispatch`). Il vit dans `avis.yml`, qui les définit déjà et que le job `avis` d'une
   PR appelle : `hebdo.yml` disparaît, ses jobs images et `mobile` étant rendus à la PR. Sur une
   PR, `avis` reste conditionné au delta d'une de ses entrées.

Gardés, pour un motif autre que le quota : le filtrage par delta — la durée, une PR de pipeline
attend `api` seul, 3 min, au lieu de ≈ 16 — ; aucun run en draft — les jetons — ; le contrôle des
auteurs en pas d'`api` — rien à gagner à en faire un job — ; l'annulation d'un run de PR au push
suivant, jamais sur `main` ; Dependabot mensuel. Retirée : la re-mesure du coût de la CI que
fixait l'ADR 0031, sans facture à mesurer.

## Conséquences

**Positives**

- Une PR de front ou d'images rend son verdict ≈ 3 min plus tôt : `web` et `infra` n'attendent
  plus `api`.
- Une régression du mobile se voit sur la PR qui la cause, et aucune vérification n'attend plus
  le lundi.
- Un merge qui casse le commit livré — trunk avancé après le run de PR, PR de Dependabot mergées
  d'affilée — est vu avant le déploiement, et le bloque.

**Risques acceptés**

- Une image dont une vérification rougit sur `main` reste publiée, `latest` compris (lu par
  `restore.yml`), sans être déployée — comme déjà après une fumée rouge ; `deploy` déploie par
  SHA.
- Un merge de front ou d'images attend `web` ou `infra` avant de se déployer : ≈ 5 à 7 min de plus
  qu'un `publish` suivi de la fumée ; nul pour un merge de pipeline ou de back.
- Un rouge d'avis planifié envoie un mail chaque matin tant que l'avis n'est pas traité.
- `infra` et `publish` écrivent sur `main` la même entrée du cache des couches, sous la même clé :
  le second à finir ne l'écrit pas — « You cannot change the contents of an existing cache » (doc
  GitHub « Dependency caching », lue le 2026-11-24).
- Deux merges à moins d'un run d'écart, le second rouge : aucun ne se déploie — le premier cède
  la place à la tête de `main`, que le second ne déploie pas —, et la production reste sur le
  dernier commit déployé, jusqu'au merge vert suivant.

## Comparaison des options

| | (b1) Livrer seulement | (b2) Avant `publish` | (b3) Pendant `publish` |
|---|---|---|---|
| Attente ajoutée à un merge de front ou d'images | nulle | 13 à 16 min | ≈ 5 à 7 min |
| Le commit livré est vérifié | non | oui | oui, avant le déploiement |
| Image publiée sur une vérification rouge | — | non | oui, jamais déployée |
| Verdict | Écartée : son seul motif était le quota | Écartée : trop long (mainteneur) | **Retenue** |

## Conditions de réexamen

- Le dépôt redevient privé, ou les runners standard cessent d'être gratuits pour un dépôt public.
- Un merge sans changement d'image (docs, pipeline) qui se déploie quand même devient un coût :
  sujet distinct, non tranché ici.
