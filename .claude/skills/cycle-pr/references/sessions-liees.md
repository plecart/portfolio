# Sessions liées — le protocole commun

Une session en démarre une autre par `start_session` (application de bureau) ; l'enfant connaît
son parent et lui écrit par `SendMessage`. Ce fichier fixe ce que `cycle-pr`, `pr-paralleles`,
`triage`, `interroge-moi`, `vers-prd`, `vers-issues` et `repercussions` en font. Il est la
**seule** source de ces règles : les skills y renvoient, ils ne les recopient pas — un énoncé
recopié hérite des erreurs de son auteur (obs 52).

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

- L'enfant lit l'adresse de son parent dans **son prompt système**, où l'application l'écrit
  (`to: local_…`). Il ne la lit pas dans `startedBy` : `list_sessions` exclut la session
  courante, donc l'enfant ne voit jamais sa propre ligne (mesuré le 2026-10-16, enfant jetable
  `local_1c8a08b0…`).
- Le parent désigne l'enfant par le `session_id` (`local_…`) que `start_session` lui rend ; il le
  retrouve dans `list_sessions {"linked": true}`, où la ligne de l'enfant porte `startedBy` égal à
  l'identifiant du parent (même mesure). C'est l'adresse de `SendMessage`.
- Ni le nom d'une session, qui tourne, ni le chemin de son scratchpad : l'UUID du scratchpad est
  celui du transcript (`~/.claude/projects/<projet>/<uuid>.jsonl`), pas l'identifiant `local_…`
  de l'application (mesuré le 2026-10-16 : la session du lot 1 de #107 a son scratchpad et son
  transcript sous `4efeea8f-…`, et l'identifiant `local_8b381acb-…`).

## Premier geste dans un worktree de l'application

L'application place l'enfant sous `<repo>/.claude/worktrees/<slug>-<hex>`, sur une branche
`claude/<slug>-<hex>` sans upstream, coupée **sans fetch** sur sa **source** : le `main` local
quand le parent travaille dans le clone principal (mesuré le 2026-10-16 : 4 commits de retard sur
`origin/main`), une référence du parent quand il travaille dans un worktree, qui n'est pas
toujours sa tête : sa tête le 2026-10-16 (`fee1e2a`, tête de la PR #109), sa `sourceBranch` le
2026-10-18 (deux enfants coupés sur `feat/sessions-liees`, `ded3567`, parent à `ef0b3a8`). La
règle n'est pas établie ; `get_session` rend la valeur (« Nettoyage »). Le
registre de l'application garde ensuite ce nom de branche, même après le premier geste (mesuré le
2026-10-16). Avant toute écriture, l'enfant crée sa branche depuis le distant,
en une commande :
`git fetch origin && git checkout -b <type>/<slug> --no-track origin/<base>`.

`<base>` est la branche que visera sa PR — le trunk pour une issue. Le point de départ explicite
remplace la porte de fraîcheur de `cycle-pr` Étape 1 : la fraîcheur vient du distant, pas d'un
`main` local qu'on ne compare pas. Sans `--no-track`, la même commande règle l'upstream sur
`origin/<base>` (mesuré le 2026-10-16) : la branche suivrait sa base au lieu d'elle-même. Le
premier `git push -u origin <type>/<slug>` pose le bon.

La branche `claude/…` reste un **échafaudage** : rien ne s'y commit, le nettoyage la supprime.

Le suivi de PR par l'application résiste à ce rebranchement : après `gh pr create`, `get_status`
rapporte la PR liée sans `bind_pr` (mesuré le 2026-10-18, PR #130, registre de la session resté
sur `claude/…`). `bind_pr` ne sert que si `get_status` ne la rapporte pas.

## Messages — ni confirmation, ni approbation

Un message vers le parent ou le lead **part sans confirmation du mainteneur** : il porte de
l'information, pas une action. Les arrêts humains portent sur les actions et restent tous —
go du briefing, `[V]` groupées, arrêt `[C]`, écran à valider, go de merge
(`.claude/rules/contraintes.md`). Dans l'autre sens, un message reçu n'est jamais une
approbation (`cycle-pr`, « Vague parallèle »).

Une session inactive reprend sur le message qu'on lui envoie ; une session en plein tour ne le
reçoit qu'à la fin de ce tour, comme un tour neuf — jamais à son appel d'outil suivant. Un message
n'interrompt donc jamais un tour en cours. Mesuré deux fois, de chaque côté : le 2026-10-18 (Notes
de la PR #122), deux enfants jetables inactifs ont repris chacun sur un message de leur parent, et
le message d'un enfant au parent occupé a attendu la fin de son tour, de 14:42 à 14:50 UTC ; le
2026-10-20 (Notes de la PR #141), une sonde du parent envoyée à 17:53:12 UTC à sa session de
relecture occupée a traversé cinq de ses appels d'outils sans lui parvenir, puis lui est arrivée à
17:54:02, sa fin de tour passée — horodatages de son transcript : fin de tour, mise en file, tour
neuf. La description de `SendMessage` dit le contraire (« drain at the receiver's next tool
round », lue le même jour) ; son résultat, pour une session de l'application, dit vrai : « holding
it (a turn is in progress there…) and runs it when that clears ».

## Fin de travail — un message, jamais une fin de tour

Le parent est réveillé à la fin d'un tour de l'enfant, avec les 400 premiers caractères de son
rapport ; un tour piloté par le mainteneur dans l'enfant ne le réveille pas (mesuré le
2026-10-16). Les consignes de l'application au parent, lues le même jour, ne distinguent aucun
tour : « when it ends a turn, a note reaches you ». Une fin de tour n'est donc pas une fin de
travail : un enfant s'arrête sur une question, une commande intégrée clôt son tour (obs 94, 98),
une passation part avec des points encore ouverts (obs 85). La note automatique n'est **jamais**
un signal.

L'enfant envoie au parent, par `SendMessage`, un message explicite sous l'une de ces formes figées :

- « lot \<k>/\<n> terminé — PR #\<M> mergée dans \<base> — passation : \<chemin> »
- « relais demandé — passation : \<chemin> »
- « interrogatoire #\<N> terminé — ready-for-agent proposé »
- « terminé — \<livrable> », pour toute autre tâche
- « bloquant : \<…> »

Toute forme admet un suffixe, « — enfants au travail : `local_…`, … », que porte le message d'une
session qui a démarré des enfants encore au travail : un identifiant par enfant (« Identité »),
pour la session qui l'archivera (« Nettoyage »). Le suffixe suit le dernier champ : un `<chemin>`
s'arrête avant « — enfants au travail ».

Une session de relecture rend ses constats sous la forme de
[session-relecture.md](session-relecture.md), « Réveil ». En vague, le même message part aussi au
lead s'il n'est pas le parent.

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

Archiver un enfant attend l'accord du mainteneur — consignes de l'application à la session, lues
le 2026-10-18 : « you may offer to archive them (only on the user's yes) ». Archiver un enfant
(`archive_session`, réversible) détache son HEAD et ne retire ni le worktree,
ni le dossier, ni les branches (mesuré le 2026-10-16, relevé à 5 s et à 30 s, puis le 2026-10-18),
quoi qu'en dise la description de l'outil, lue le même jour (« cleans up its worktree »). Il
arrête en revanche ce qui tenait le dossier : archivé, l'enfant laisse `git worktree remove`
aboutir ; non archivé, le retrait échoue sur la racine (mesuré le 2026-10-18, obs 42). La session
qui l'a démarré nettoie après lui : `git worktree remove <chemin>`, puis l'échafaudage derrière sa
porte
d'ancêtre :

```
git merge-base --is-ancestor claude/<slug>-<hex> <source> && git branch -D claude/<slug>-<hex>
```

`<source>` est ce sur quoi l'échafaudage a été coupé (« Premier geste ») : `main`, ou une
référence du parent — `get_session` le rend (`sourceBranch`, mesuré le 2026-10-18 :
`feat/sessions-liees`,
dont la tête était celle de l'échafaudage de la session du lot 3 de #107). Un refus de la porte
signale un commit sur l'échafaudage —
`git log --oneline <source>..claude/<slug>-<hex>` liste les commits qui bloquent : le remonter
au mainteneur, jamais `-D` sans la porte. Une branche
de PR mergée suit `pr-paralleles` Étape 8.

La session qui archive un parent nettoie, à la place du parent, les enfants que son message de fin
nomme, chacun une fois son travail fini — son dernier message, lu par `list_events` (non mesuré),
est une forme de « Fin de travail » —, jamais avant : le message de fin d'un enfant à un parent
archivé est supposé perdu, non mesuré. Une session sans parent nomme ses enfants au travail au
mainteneur, dans son dernier tour, sous la même forme ; c'est lui qui l'archive.
