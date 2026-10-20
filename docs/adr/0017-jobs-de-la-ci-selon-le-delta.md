# 0017 — Les jobs de la CI selon le delta d'une PR

- **Statut** : accepté
- **Date** : 2026-10-20
- **Décisions du cadrage** : D61 (`docs/cadrage-technique.md` §7) ; remplace le point « Scan :
  Trivy, sur chaque PR (job `infra`) » de l'ADR 0014 (§ Décision) ; l'ADR 0014 reste accepté pour
  tout le reste, scan avant chaque publication compris ; décisions de l'interrogatoire de #124
  (2026-10-18)

## Contexte

L'ADR 0014 donne à la CI trois jobs parallèles, un par pile — `api`, `web`, `infra` —, lancés sur
chaque push d'une PR quel que soit le delta, et un run de plus au passage en ready. Le compte est
GitHub Pro : 3 000 minutes d'Actions par mois (doc GitHub « GitHub Actions billing », lue le
2026-09-27 pour l'ADR 0014 et relue le 2026-10-20).

Mesure du 2026-10-18 sur les runs du 2026-10-04 au 2026-10-17 (commandes dans le corps de #124,
chaque job arrondi à la minute supérieure) : 370 runs, 3 202 minutes facturées, soit ≈ 6 900 par
mois — le quota tombe au 13ᵉ jour. Le job `infra` en prend 1 389, `api` 858, `web` 791. Environ
1 020 minutes de `web` et `infra` ont tourné sur des PR qui ne touchaient que la pipeline
(`.claude/`, `docs/`, Markdown, tests du back) ; 70 runs ont été suivis d'un autre run de la même
branche en moins de 5 minutes ; 54 rejouaient un SHA déjà couvert. Aucune porte n'est en cause :
le gaspillage vient de **quand** les jobs tournent.

## Facteurs de décision

- Aucune porte retirée ni allégée : audit, scan, e2e, Lighthouse et tests des images gardent leur
  raison (ADR 0014, ADR 0008).
- Un job sauté à tort cache un rouge ; un job lancé pour rien ne coûte que des minutes. Dans le
  doute, le job tourne.
- Chaque job compte au moins une minute, même vide : la mesure de #124 arrondit chaque job à la
  minute supérieure ; la page « GitHub Actions billing », relue le 2026-10-20, ne précise pas
  l'arrondi.
- Un push vers `main` publie et déploie : tout y tourne, rien ne s'y annule, et `publish` attend
  toujours les trois jobs.
- Un rouge du back ne masque pas un rouge du front (ADR 0014, `ci.yml`).

## Options considérées

1. **(a) Un job dédié `changes`**, qui lit le delta et dont `api`, `web` et `infra` dépendent.
2. **(b) Une étape en tête du job `api`**, qui lit le delta ; `web` et `infra` en dépendent par
   `needs: api` et ne tournent que si leur réponse vaut `true`.
3. **(c) `paths` / `paths-ignore` au niveau du workflow.**

## Décision

**Option b**, avec deux réglages voisins, pris dans le même mouvement (#124) :

- **Sur une PR, `web` et `infra` ne tournent que sur leurs fichiers.** La première étape du job
  `api` passe `git diff --name-only --no-renames HEAD^1 HEAD` — le delta de la PR contre sa base,
  le checkout d'une PR étant son commit de fusion, un renommage sous ses deux chemins — à
  `infra/ci/changed_jobs.py`, qui rend `web` et `infra`. `web` : le front, ou le schéma de l'API
  dont ses types sont générés. `infra` : tout chemin hors du harnais — liste d'exclusion, un
  fichier inconnu fait tourner le job —, ou l'un des modules d'appui des tests du back que
  `make image-test` charge aussi. `web` et `infra` partent
  après `api`, même rouge (`!cancelled()`). Sur un push vers `main`, tout tourne. Le job `api`
  tourne sur chaque push — la suite du back porte aussi les tests de la pipeline ; seule
  l'ouverture d'une draft le saute, et avec lui `web` et `infra`.
- **Un push annule le run encore en cours de la même PR** (`concurrency` du workflow, groupe par
  numéro de PR) ; jamais sur `main`, où le groupe se replie sur le SHA.
- **Le passage en ready ne déclenche plus de run** : il rejouait un SHA déjà couvert, sur la
  référence de fusion existante, que GitHub ne recalcule pas (obs 51). `cycle-pr` (Étape 5)
  lit à la place le run du SHA de tête, et son verdict, avant `gh pr ready`.

Le point de l'ADR 0014 remplacé : le scan Trivy tourne sur chaque PR qui touche un fichier hors du
harnais, et sur chaque push vers `main` ; avant chaque publication, inchangé.

## Conséquences

**Positives**

- Une PR de pipeline ne paie plus que le job `api` : ≈ 1 020 minutes sur les 14 jours mesurés.
  L'estimation de #124, tous ses réglages appliqués, tombe à ≈ 1 300-1 500 minutes par 14 jours,
  contre 3 202 mesurées.
- La règle vit dans un script de la bibliothèque standard, tenu par ses témoins
  (`apps/api/tests/test_ci_declencheurs.py`), comme la forme du workflow.

**Négatives, assumées**

- `web` et `infra` partent après la fin d'`api`, 2,4 minutes en médiane : un `needs` attend le
  job entier.
- Un avis neuf sur une image ou une dépendance du front n'est plus vu par une PR de pipeline : il
  l'est à la PR suivante qui touche les images ou le front, ou au push vers `main` suivant.
- Le quota reste serré : ≈ 2 800-3 200 minutes par mois contre 3 000. Plafond de dépense ou
  changement d'offre restent au mainteneur.

## Comparaison des options

| | (a) Job `changes` | (b) Étape du job `api` | (c) `paths` de workflow |
|---|---|---|---|
| Coût par run | une minute facturée de plus, ≈ 300 minutes par 14 jours | aucun | aucun |
| Démarrage de `web` et `infra` | après `changes`, quelques secondes | après `api`, 2,4 minutes en médiane | immédiat |
| Granularité | par job | par job | le workflow entier : ne sait pas sauter un seul job |
| Verdict | Écartée : le coût | **Retenue** | Écartée : ne conditionne pas un job |

## Conditions de réexamen

- Le quota cesse d'être une contrainte (offre changée, dépôt public) : le gain ne paie plus
  l'attente de `web` et `infra`.
- Un fichier du harnais entre dans une image, ou dans ce que le job `infra` exécute : il sort de
  `HARNESS`. Les modules d'appui des tests des images sont recalculés par un test, pas à la main.
- Un job vide cesse de coûter une minute : l'option (a) ne coûte plus rien.
