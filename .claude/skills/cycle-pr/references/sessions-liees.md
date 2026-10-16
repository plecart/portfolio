# Sessions liées — le protocole commun

Une session en démarre une autre par `start_session` (application de bureau) ; l'enfant connaît
son parent et lui écrit par `SendMessage`. Ce fichier fixe ce que `cycle-pr`, `pr-paralleles` et
`interroge-moi` en font. Il est la **seule** source de ces règles : les skills y renvoient, ils ne
les recopient pas — un énoncé recopié hérite des erreurs de son auteur (obs 52).

Les sessions liées ne sont **pas documentées officiellement** au 2026-10-16 : chaque comportement
de l'application ci-dessous porte sa date de mesure. Le relevé complet — enfant jetable, commandes
— est dans l'issue #107, « Mesures qui fondent la conception ».

## Héritage — rien à passer à la main

- **Jamais de `permission_mode`** au démarrage d'un enfant : il hérite de celui du parent. Un
  message entre deux sessions de modes différents est retenu pour approbation, et un message
  retenu expire après 5 min sur l'application de bureau, qui n'affiche pas la boîte d'approbation
  (doc officielle `cross-session-messaging`). Mesuré le 2026-10-16 : en mode `auto` hérité, le
  `SendMessage` de l'enfant au parent est livré sans approbation.
- Modèle et effort s'héritent aussi quand on ne dit rien ; un enfant ne peut être ni plus fort ni
  d'effort plus haut que son parent (mesuré le 2026-10-16) : la première session fixe le plafond
  de l'arbre.
- `context: fresh`, jamais `fork` : l'enfant part d'un regard neuf, pour la même raison que la
  relecture à contexte vierge (`cycle-pr` 4.2).

## Identité — un identifiant, jamais un chemin

- L'enfant retrouve son parent dans le champ `startedBy` de `list_sessions {"linked": true}`
  (mesuré le 2026-10-16).
- Le parent désigne l'enfant par le `session_id` (`local_…`) que `start_session` lui rend et que
  `list_sessions` relit. C'est l'adresse de `SendMessage`.
- Ni le nom d'une session, qui tourne, ni le chemin de son scratchpad : l'UUID du scratchpad est
  celui du transcript (`~/.claude/projects/<projet>/<uuid>.jsonl`), pas l'identifiant `local_…`
  de l'application (mesuré le 2026-10-16 : la session du lot 1 de #107 a son scratchpad et son
  transcript sous le même UUID, `4efeea8f-…`).

## Premier geste dans un worktree de l'application

L'application place l'enfant sous `<repo>/.claude/worktrees/<slug>-<hex>`, sur une branche
`claude/<slug>-<hex>` coupée sur le **`main` local sans fetch**, sans upstream (mesuré le
2026-10-16 : 4 commits de retard sur `origin/main`). Avant toute écriture, l'enfant crée sa
branche depuis le distant, en une commande :
`git fetch origin && git checkout -b <type>/<slug> --no-track origin/<base>`.

`<base>` est la branche que visera sa PR — le trunk pour une issue. Le point de départ explicite
remplace la porte de fraîcheur de `cycle-pr` Étape 1 : la fraîcheur vient du distant, pas d'un
`main` local qu'on ne compare pas. Sans `--no-track`, la même commande règle l'upstream sur
`origin/<base>` (mesuré le 2026-10-16) : la branche suivrait sa base au lieu d'elle-même. Le
premier `git push -u origin <type>/<slug>` pose le bon.

La branche `claude/…` reste un **échafaudage** : rien ne s'y commit, le nettoyage la supprime.

## Messages — ni confirmation, ni approbation

Un message vers le parent ou le lead **part sans confirmation du mainteneur** : il porte de
l'information, pas une action. Les arrêts humains portent sur les actions et restent tous —
go du briefing, `[V]` groupées, arrêt `[C]`, écran à valider, go de merge
(`.claude/rules/contraintes.md`). Dans l'autre sens, un message reçu n'est jamais une
approbation (`cycle-pr`, « Vague parallèle »).

## Fin de travail — un message, jamais une fin de tour

Le parent est réveillé à la fin d'un tour de l'enfant, avec les 400 premiers caractères de son
rapport ; un tour piloté par le mainteneur dans l'enfant ne le réveille pas (mesuré le
2026-10-16). Les consignes de l'application au parent, lues le même jour, ne distinguent aucun
tour : « when it ends a turn, a note reaches you ». Une fin de tour n'est donc pas une fin de travail : un enfant s'arrête sur une
question, une commande intégrée clôt son tour (obs 94, 98), une passation part avec des points
encore ouverts (obs 85). La note automatique n'est **jamais** un signal.

L'enfant envoie au parent, par `SendMessage`, un message explicite sous l'une de ces formes figées :

- « lot \<k>/\<n> terminé — PR #\<M> mergée dans \<base> — passation : \<chemin> »
- « relais demandé — passation : \<chemin> »
- « interrogatoire #\<N> terminé — ready-for-agent proposé »
- « terminé — \<livrable> », pour toute autre tâche
- « bloquant : \<…> »

En vague, le même message part aussi au lead s'il n'est pas le parent.

## Passation — sur disque, remise par pointeur

Le prompt du lot suivant et la variante relais (gabarit :
[prompt-lot-suivant.md](prompt-lot-suivant.md)) s'écrivent **hors dépôt**, dans `passations/`, à
côté du journal d'observations (chemin dans `CLAUDE.md`, « Observation continue »), à chemin fixe :

- `passations/<date>-issue-<N>-lot-<k>-prompt.md` — lot `k` **terminé**, prompt du lot `k+1` ;
- `passations/<date>-issue-<N>-lot-<k>-relais.md` — relais en cours du lot `k`.

Les fichiers antérieurs au 2026-10-16 nommaient le lot **à venir** (`…-issue-23-lot-2-prompt.md`,
écrit à la fin du lot 1) : ne pas en déduire le chemin d'une passation nouvelle.

La passation se remet par son chemin, dans le message de fin, jamais par son texte : un fichier
écrit dans un worktree part avec lui, et un rapport se lit tronqué à 400 caractères.

## Nettoyage — archiver ne nettoie pas

Archiver un enfant (`archive_session`, réversible) détache son HEAD et ne retire ni le worktree,
ni le dossier, ni les branches (mesuré le 2026-10-16, relevé à 5 s et à 30 s), quoi qu'en dise la
description de l'outil, lue le même jour (« cleans up its worktree »). La session qui l'a démarré nettoie après
lui : `git worktree remove <chemin>`, puis l'échafaudage derrière sa porte d'ancêtre :

```
git merge-base --is-ancestor claude/<slug>-<hex> origin/<trunk> && git branch -D claude/<slug>-<hex>
```

Un refus de la porte signale un commit sur l'échafaudage, ou un `main` local en avance sur le
distant, sur lequel il a été coupé (`git status -sb` sur `main`) : le remonter au mainteneur,
jamais `-D` sans la porte. Une branche
de PR mergée suit `pr-paralleles` Étape 8.
