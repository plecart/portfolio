# 0029 — Les runs de PR fusionnent eux-mêmes la tête au trunk courant

- **Statut** : accepté
- **Date** : 2026-11-08
- **Décisions du cadrage** : D73 (`docs/cadrage-technique.md` §7) ; décisions de l'interrogatoire
  de #249 (2026-11-08)
- **Remplace** : dans l'ADR 0019, le point 1 de § Décision, « Il tourne, comme tout run de PR, sur
  la référence de fusion que GitHub calcule à ce moment et ne recalcule pas si le trunk avance
  ensuite », et le point de § Conséquences « la porte de fraîcheur de l'Étape 7 reste la seule
  preuve de l'état combiné, comme pour tout run de PR aujourd'hui » ; l'ADR 0019 reste accepté
  pour le reste, et l'ADR 0017 entier

## Contexte

Sur une PR, chaque job du workflow `CI` extrait la référence de fusion que GitHub calcule à
l'événement déclencheur, `refs/pull/<n>/merge` (doc GitHub « Events that trigger workflows »,
`pull_request` : « `GITHUB_SHA` … Last merge commit on the `GITHUB_REF` branch », lue le
2026-11-08). GitHub ne la recalcule ni à chaque merge sur le trunk ni au passage en ready (obs 51),
et un `gh run rerun` réutilise le commit enregistré au déclenchement (obs 83). Avant le go, `cycle-pr`
lit dans la trace de checkout de chaque job le trunk réellement combiné
(`porte-merge.py trunk`) ; quand il est périmé, le seul remède était `gh pr close` puis
`gh pr reopen`.

En vague `pr-paralleles`, chaque merge d'une PR sœur périme les runs de toutes les autres, et une
réouverture rejoue souvent la référence calculée à l'événement précédent : il en faut une seconde,
qui ne vaut que si le trunk n'a pas bougé entre les deux (obs 110). Mesuré : PR #109, trois
réouvertures pour un trunk avancé quatre fois (runs 38960319135, 38967746705, 38980769989,
2026-10-16) ; PR #185, deux réouvertures, chacune sur accord du mainteneur, et un run vert qui
avait extrait l'ancien trunk (run 40769309165, 2026-10-28) ; PR #219, quatre réouvertures pour un
seul go, sans fichier commun ni conflit avec les PR mergées entre-temps (2026-11-04). Le coût
croît avec le nombre de PR de la vague, pas avec le risque.

## Facteurs de décision

- La preuve CI porte sur l'état combiné que le merge produira : pas de relâchement de la porte de
  fraîcheur (`cycle-pr` Étape 7).
- Une relance coûte un run, pas deux, et pas d'accord du mainteneur par relance.
- Les lecteurs actuels du commit extrait ne changent pas : `HEAD^1..HEAD`, le delta de la PR que
  lit le job `api` pour choisir les jobs (ADR 0017), et `HEAD^1..HEAD^2`, les commits de la PR
  que lit le job `auteurs`.
- Jamais d'auto-merge dans le trunk (`.claude/rules/contraintes.md`).
- Aucun réglage du dépôt ni abonnement de plus.

## Options considérées

1. **Chaque job de PR fusionne lui-même la tête au trunk courant**, au lieu de lire la référence
   de la forge ; la relance devient `gh run rerun`.
2. **Une porte fondée sur le risque** : pas de relance quand les deltas du trunk et de la PR sont
   sur des piles disjointes, sans fichier de contrat, et `git merge-tree --write-tree` en 0.
3. **Un ordre de merge imposé en vague** : le lead ne fait relancer la CI d'une PR qu'après le
   merge de la précédente.
4. **La file de merge de GitHub**, qui éprouve elle-même la tête combinée au trunk.

## Décision

**Option 1.**

- Sur un événement `pull_request`, chaque job qui extrait le code — `api`, `web`, `infra`,
  `auteurs` de `ci.yml`, et `avis.yml` qu'il appelle — extrait la tête de la PR avec tout
  l'historique, puis une action locale, `.github/actions/fusion-trunk`, la fusionne à
  `origin/<branche cible de la PR>` tel qu'il est au démarrage du job. Le commit obtenu a le trunk
  en premier parent et la tête en second.
- Un conflit fait échouer le job, et sa trace le dit. Une PR déjà en conflit à l'événement ne
  déclenche aucun run (doc GitHub « Events that trigger workflows », `pull_request`, lue le
  2026-11-08) : ce cas-ci est celui d'un trunk qui a avancé en conflit, vu à la relance.
- L'action est du code du dépôt, lue dans l'arbre extrait et sans `uses` à elle : rien n'y
  échappe à Dependabot, et les gardes d'épinglage (`apps/api/tests/test_supply_chain.py`)
  l'acceptent à ce titre.
- Chaque job écrit dans sa trace une ligne stable,
  `Fusion explicite : <commit> Merge <tête> into <trunk>`, lue sur les parents du commit ;
  `porte-merge.py trunk` la lit au lieu de la ligne de checkout de la forge, et exige toujours que
  **chaque** job ait fusionné `origin/<trunk>` : les jobs démarrent à des moments différents.
- Sur un `push` vers `main`, rien ne change : aucune fusion.
- Quand le trunk a avancé, la relance est `gh run rerun <run>`, run entier : elle refait la fusion
  sur le trunk du moment. La fermeture-réouverture ne reste que pour un événement perdu
  (`cycle-pr` Étape 5, « Si aucun run n'apparaît »).

Les options écartées :

- **la porte fondée sur le risque** : elle assouplit la preuve de l'état combiné — une interaction
  sans fichier commun passe — et demande une liste de fichiers de contrat à tenir ; remise à une
  vague mesurée qui montrerait des relances encore chères ;
- **l'ordre de merge en vague** : il sérialise la fin de vague, reporte l'attente sur le
  mainteneur, et ne supprime pas la double réouverture ;
- **la file de merge** : elle suppose une règle de protection ou un ensemble de règles sur `main`
  (aucun aujourd'hui), donc GitHub Pro ou une organisation pour ce dépôt privé personnel
  (« Managing a merge queue », « GitHub's plans », lus le 2026-11-08), et une file qui merge à la
  fin de sa validation contredit « jamais d'auto-merge dans le trunk ».

## Conséquences

**Positives**

- Une relance par avancée du trunk au lieu de deux ou plus, sans fermeture de la PR ni accord du
  mainteneur à chaque fois.
- Le trunk qu'un run a éprouvé se lit dans une ligne que le workflow écrit lui-même, sur les
  parents du commit qu'il a construit.
- Une PR de lot vers une branche d'intégration est fusionnée à sa propre branche cible.

**Négatives, assumées**

- Il reste une relance par avancée du trunk : la porte de fraîcheur de l'Étape 7 en est toujours
  le juge, mais un run relancé éprouve désormais le trunk du moment.
- Chaque job qui fusionne extrait tout l'historique, pour trouver l'ancêtre commun — sur un push
  vers `main` aussi, où le même pas de checkout sert (≈ 19 Mio de paquets au 2026-11-08,
  `git count-objects -vH`).
- Un run d'avant cette décision n'écrit pas la ligne : `porte-merge.py trunk` le refuse, et sa
  relance relit l'ancien workflow ; une PR ouverte au merge de cette décision se relance encore
  par fermeture-réouverture, jusqu'à un run qui écrit la ligne.

## Comparaison des options

| | Relances par avancée du trunk | Preuve de l'état combiné | Coût de mise en place |
|---|---|---|---|
| Option 1 | **une, `gh run rerun`** | **inchangée, chaque job** | **workflow, une action, la porte** |
| Option 2 | zéro sur piles disjointes | relâchée | une liste de contrats à tenir |
| Option 3 | une par PR, sérialisée | inchangée | aucun script, l'ordre à la main |
| Option 4 | zéro | par la file | abonnement, protection de `main`, auto-merge |

## Conditions de réexamen

- Une vague mesurée montre que les relances restent chères : l'option 2 se rouvre.
- Le dépôt passe à une offre qui permet la protection de `main` et la file de merge, et la
  doctrine du go humain s'y accommode : l'option 4 se rouvre.
- GitHub recalcule la référence de fusion à chaque avancée du trunk, ou un `gh run rerun` la
  relit : l'action devient inutile.
