# Le cycle de commit — détail de `cycle-pr`

Passages déplacés mot pour mot de `cycle-pr/SKILL.md` (issue #177), chacun sous le titre que
cite son renvoi. Les liens `references/…` qu'ils portent se lisent depuis le dossier du skill,
et leurs renvois de position (« ci-dessous », « plus bas ») depuis l'emplacement du renvoi.

## La boucle s'enchaîne sans rendre la main

**La boucle s'enchaîne sans rendre la main.** Un cycle AFK va de 3.1 à 3.5 puis repart en 3.1
jusqu'à l'Étape 4 — en lançant au passage la **première passe de relecture 4.2** dès que le
commit qui vient d'être fait pose un invariant que les suivants supposeront vrai ; l'annonce de
l'étape suivante (« Next : commit 2/3 ») est un **titre**, pas une demande d'autorisation. Les
seuls arrêts légitimes du cycle : une question `[V]` dont dépend **tout** ce qui reste à faire, un
arrêt `decisions-vs-doc` (`[C]`), le point d'arrêt humain (zone sensible, une fois par PR, au
commit qui assemble l'écran — 3.5) et le « go » de l'Étape 7. Une `[V]` dont une partie du travail
ne dépend pas s'inscrit dans le body de la PR draft, sous « Questions en attente », avec
l'hypothèse réversible retenue d'ici là, et le cycle continue sur cette partie ; elle sera posée
groupée au prochain arrêt. Ailleurs, s'arrêter est une remise de main que personne n'a demandée.

## Documentation maximale

**Documentation maximale** : chaque fonction écrite est documentée à fond (intention, params,
valeur de retour, erreurs, effets de bord, pré/postconditions, exemples, edge cases) au format
idiomatique du langage. La doc explique le contrat, les tests prouvent le comportement.

**Doc projet en sync** : si le delta change un comportement, une commande, une interface ou
l'architecture, mettre à jour la doc concernée (`README`, `docs/`, `CLAUDE.md`, glossaire) **dans
le même commit** — voir `.claude/rules/contraintes.md`. La doc ne se met jamais à jour « plus tard ».

## Puis relire le gabarit

**Puis relire le gabarit** : le `developpeur` rend avec chaque commit le chiffre de
`git diff --stat <base>...HEAD`, la base de son brief, et s'arrête au seuil que ce brief porte ; la
session PR le relit contre les deux seuils de `taille-pr.md` — l'absolu, et le double de
l'estimation du briefing. Franchi, le re-découpage se rouvre maintenant, pas à l'Étape 5 (obs 70).

**Un sous-lot est un lot** (D-9, #134). Les PR qu'un re-découpage fait naître suivent « Une session
neuve par lot » (Étape 8) : la session courante finit son sous-lot et écrit la passation depuis
les artefacts ; le sous-lot suivant reçoit sa session neuve, ouverte par la coordinatrice s'il y
en a une ([references/coordinatrice.md](references/coordinatrice.md), « Ouvrir le lot suivant »),
sinon proposée au mainteneur par une carte (`start_session`, `initiation: own_initiative`) — aucune
session n'en démarre une autre hors d'un tour humain. Un re-découpage qui sépare un commit de ses
correctifs rejoue d'abord la passe « affirmations » de `cleanup-verbatim.md` sur le premier
morceau **seul** : chaque docstring s'y lit contre le code de ce morceau, pas contre l'état final,
et les limites que le morceau suivant lève s'y nomment (obs 109).
