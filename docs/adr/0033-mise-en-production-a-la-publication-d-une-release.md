# 0033 — La mise en production à la publication d'une release

- **Statut** : accepté
- **Date** : 2026-11-28
- **Décisions du cadrage** : D80 (`docs/cadrage-technique.md` §7) ; remplace, dans l'ADR 0014,
  « sur push vers `main` seulement » (§ Décision, point « Publication ») ; dans l'ADR 0032, la
  décision (b3) — « Sur un push vers `main` […] tournent **pendant** `publish` » et la suite du
  point 2 qui y ordonne `fumee` et `deploy` (§ Décision) —, « Un merge de front ou d'images
  attend `web` ou `infra` avant de se déployer », « `infra` et `publish` écrivent sur `main` la
  même entrée du cache des couches » et « Deux merges à moins d'un run d'écart, le second
  rouge » (§ Conséquences, « Risques acceptés »), et « Un merge sans changement d'image […] qui
  se déploie quand même » (§ Conditions de réexamen) ; ces ADR restent acceptés pour le reste,
  les vérifications de `main` de l'ADR 0032 comprises ; dialogue du 2026-11-27 et
  interrogatoire de #299 du 2026-11-28, décisions 1 à 16 du corps de l'issue

## Contexte

Depuis l'ADR 0014, chaque push vers `main` publie les images ; depuis #16, il les déploie ; depuis
l'ADR 0032, `api`, `web`, `mobile` et `infra` rejouent le commit pendant `publish`, et `deploy`
attend leur vert. Une petite PR — une retouche, une PR de Dependabot — part donc en ligne au
merge, sans que le mainteneur ait décidé de livrer.

## Facteurs de décision

- Mettre en production est une décision du mainteneur, pas un effet du merge.
- `main` garde ses vérifications : le verdict d'un merge reste vu au push (ADR 0032).
- Le commit livré est vérifié avant le déploiement, et rien ne se déploie depuis un commit hors
  de `main`.
- Un run lent ne redéploie pas l'ancien code sur un schéma déjà migré (motif du garde « seule la
  tête de `main` se déploie » du pas « Déploiement », avant cet ADR).
- Un événement créé par le `GITHUB_TOKEN` ne lance aucun workflow, `workflow_dispatch` et
  `repository_dispatch` exceptés (doc GitHub « Triggering a workflow », « Triggering a workflow
  from a workflow », lue le 2026-11-28).

## Options considérées

1. **(a) Déployer à chaque merge** — l'état en place.
2. **(b) Un tag `v*` poussé** : `push: tags`. Un tag se pousse sans notes ni geste de
   publication, et sans brouillon où relire ce qui part.
3. **(c) Une release publiée** : `release: types: [published]`. Un brouillon porte les notes et
   ne lance rien ; le clic « Publish » lance le run.
4. **(d) `workflow_dispatch`** : un bouton, sans version ni notes : la production ne porte pas de
   nom.

## Décision

**(c).**

1. **La publication d'une release GitHub `vX.Y.Z`, taggée sur un commit de `main`, met en
   production.** Un merge sur `main` ne publie ni ne déploie plus rien ; il rejoue ses
   vérifications, comme le fixe l'ADR 0032.
2. **Le run de la release publie, éprouve et déploie le commit de son tag** : `publish` →
   `fumee` → `deploy`. Seul `published` est écouté : un brouillon ne lance rien, et une
   prerelease publiée lance le run, dont les jobs de livraison la sautent
   (`github.event.release.prerelease`, doc GitHub « Events that trigger workflows », `release`,
   lue le 2026-11-28).
3. **Il rejoue toutes les vérifications** : le delta se lit contre l'arbre vide, et `api`,
   `web`, `mobile` et `infra` tournent pendant `publish` ; `deploy` attend `fumee` et leur vert.
   `avis` n'y tourne pas, comme sur `main` : `publish` scanne avant de pousser, et `avis.yml`
   rejoue ses portes chaque jour (D78).
4. **Un tag hors de `main` rougit dans `changes`**, avant toute publication :
   `git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main`. Ce contrôle remplace le
   garde « push vers `main` » de `publish`, `fumee` et `deploy`.
5. **Seule la dernière release se déploie** : le pas « Déploiement » compare le tag du run à
   `releases/latest`, et une release plus ancienne s'arrête sur une notice, en 0. Il remplace la
   comparaison à la tête de `main`, pour le même motif.
6. **Les images ne changent pas** : étiquette au SHA complet, puis `latest`, trois versions par
   paquet. Publiées aux seules releases, les trois versions gardées sont celles des trois
   dernières releases arrivées à `publish` — ni une prerelease ni un tag hors de `main` n'y
   arrivent. Le retour arrière reste hors de cet ADR : un défaut se corrige par
   une release CORRECTIF.
7. **Le run d'une release a son groupe de concurrence**, préfixé de l'événement : il n'attend
   pas le run du push de son commit. `publish` et `deploy` gardent les leurs.
8. **Une session écrit la release en brouillon, le mainteneur la publie** : son clic
   « Publish » vaut go de mise en production. Une release créée par la CI ou par le
   `GITHUB_TOKEN` ne lancerait aucun run. La procédure, le modèle des notes et le barème SemVer
   vivent dans `infra/RUNBOOK.md`, « Livrer une version » ; le bilan de vague de `pr-paralleles`
   propose le brouillon.
9. **Le contenu n'attend pas de release** : fiches et projets s'éditent dans l'admin, en base, et
   sont en ligne aussitôt (cadrage §5.4, « Flux clés », point 2). Seul le code attend une
   version.
10. **L'environnement `production` accepte les tags `v*` en plus de `main`** — réglage de
    GitHub, hors du dépôt, posé avant la première release. `main` y reste : le test de
    restauration mensuel, `restore.yml`, y lit ses secrets et tourne depuis `main` (cadrage
    §6.7, ADR 0007).

## Conséquences

**Positives**

- Rien ne part en ligne sans un clic du mainteneur, et chaque mise en production porte un
  numéro et des notes.
- Le commit livré est vérifié en entier, quel que soit le delta du dernier merge.
- Un merge de docs ou de pipeline ne se déploie plus : la condition de réexamen que l'ADR 0032
  laissait ouverte tombe.

**Risques acceptés**

- **Un merge de Dependabot ou un correctif de sécurité n'est en ligne qu'à la release
  suivante.** Une urgence se livre aussitôt par une release CORRECTIF qui ne porte qu'elle.
- **Le cache des couches de `main` n'est plus rafraîchi par `publish`.** Le run d'une release
  lit l'entrée de `main`, la branche par défaut, et écrit la sienne sous la portée de son tag,
  que seule une relance de ce run relit — « cannot restore caches created for different tag
  names » (doc GitHub « Dependency caching », « Restrictions for accessing a cache », lue le
  2026-11-28). L'entrée de `main`, `infra` seul l'écrit, au push où il tourne et ne la trouve
  pas : chaque fichier de la clé est dans sa liste `INFRA` (ADR 0031, décision 2). GitHub retire
  une entrée que rien n'a lue depuis 7 jours (même doc, « Usage limits and eviction policy », lue
  le 2026-11-28) : retirée, l'entrée de `main` manque jusqu'au prochain push où `infra` tourne, et
  une release publiée entre-temps construit ses images sans elle — des minutes de plus, gratuites
  sur un dépôt public (ADR 0032). Le risque que l'ADR 0032 acceptait — deux écritures
  concurrentes de la même entrée — disparaît.
- **`releases/latest` dépend de la case « Set as the latest release »** (`make_latest`, doc REST
  « Create a release »). Décochée, la release est verte sans se déployer, sur une notice ; sans
  aucune autre release, l'appel rend 404 et `deploy` rougit.
- **`latest` désigne la dernière image publiée, pas la production** : `make push` la pose avant
  `fumee` et `deploy`. Une release rouge à la fumée, ou une release plus ancienne arrivée la
  dernière au job `publish`, laisse `latest` sur une image qui n'est pas en ligne — celle que tire
  `restore.yml`. Un déploiement vise toujours le SHA complet.
- **`main` lit toujours les secrets de `production`**, comme avant cet ADR : seul le garde du
  job `deploy` réserve le déploiement à une release publiée. Le pas « Tag issu de main » vit dans
  le `ci.yml` du commit taggé : il garde contre l'erreur, il ne protège pas ces secrets. Un tag et
  une release se créent avec l'écriture sur le dépôt (doc REST « Create a release »), qu'a
  aujourd'hui le seul mainteneur (`gh api repos/{owner}/{repo}/collaborators`, relevé le
  2026-11-28) : la même confiance qu'un push sur `main`.
- Deux releases à moins d'un run d'écart, la seconde rouge : aucune ne se déploie — la première
  cède la place à la dernière, qui ne passe pas —, et la production reste sur la dernière release
  déployée, jusqu'à la release verte suivante.

## Comparaison des options

| | (a) Chaque merge | (b) Tag poussé | (c) Release publiée | (d) `workflow_dispatch` |
|---|---|---|---|---|
| Le mainteneur décide de livrer | non | oui | oui | oui |
| Version et notes | non | version seule | oui, relues en brouillon | non |
| Ce qui se déploie | la tête de `main` | le commit du tag | le commit du tag | la référence choisie au lancement |
| Verdict | Écartée : rien ne se décide | Écartée : ni notes ni brouillon | **Retenue** | Écartée : la production ne porte plus de nom |

## Conditions de réexamen

- Des correctifs de sécurité attendent leur release, de façon répétée : la cadence des releases
  se revoit.
- Un retour arrière devient nécessaire : redéployer une release antérieure est un sujet à
  décider (#299, « Hors périmètre »).
- Un second compte reçoit l'écriture sur le dépôt : la confiance dans un tag se revoit
  (protection des tags `v*`).
