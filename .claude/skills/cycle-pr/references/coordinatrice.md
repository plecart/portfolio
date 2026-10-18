# La coordinatrice — une issue en lots pilotée par sa session

Lue quand l'Étape 1 de `cycle-pr` découpe une issue en n > 1 lots : la session qui a fait ce
découpage devient la **coordinatrice** de ses lots. Le protocole commun des sessions liées —
héritage, identité, premier geste, fin de travail, passation, nettoyage — est dans
[sessions-liees.md](sessions-liees.md) ; ce fichier ne le recopie pas (obs 52).

La coordinatrice **n'écrit pas de code**. Elle ouvre la branche et la PR d'intégration, démarre les
sessions de lot, ouvre chaque lot sur deux preuves, guette la dérive avec le trunk, puis porte la PR
d'intégration jusqu'à son go. Entre deux lots, elle attend : son contexte ne grossit que des
pointeurs qu'elle lit — la session d'un lot connaît son lot, la coordinatrice connaît la suite des
lots (obs 62).

## Au go du découpage — le seul tour où elle démarre des sessions

`start_session` est refusé dans un tour ouvert par un message de session ou par un événement
automatique (provoqué par le lead de la vague le 2026-10-16 — #107, journal de spec, 2026-10-17) ;
seul un tour ouvert par le mainteneur le démarre, et seulement sur sa demande écrite (consignes de
l'application à la session, lues le 2026-10-18 ; mesuré le même jour, PR #122). Le go du
découpage est ce tour : la question du go nomme donc les n sessions qu'il fera démarrer, avec
l'accord pour le `verificateur` de chaque lot quand il n'y a pas de lead de vague (`cycle-pr`
Étape 7, « Sans lead »). La coordinatrice y tourne en Opus 5.5, effort `max` (#107, décision 8) :
un enfant n'étant ni plus fort ni d'effort plus haut que son parent (`sessions-liees.md`,
« Héritage »), une coordinatrice en dessous ne pourrait pas démarrer un lot `max` — sinon, la
question du go demande d'abord au mainteneur de la passer en Opus 5.5 (sélecteur de modèle) et
`/effort max`. Dans ce tour, dans cet ordre :

1. **La branche d'intégration**, depuis le trunk :
   `git fetch origin && git checkout -b <type>/<slug> --no-track origin/<trunk>`, puis une amorce
   vide, poussée — GitHub refuse une PR sans commit (mesuré le 2026-10-17, PR jetable #118).
2. **La PR d'intégration**, en draft, vers le trunk : son body s'ouvre par
   « En vol pour #<N> (intégration, <n> lots) », puis `Closes #<N>`, puis le découpage. C'est la
   seule PR de l'issue qui porte `Closes`, et la première ligne est celle que lit le script de
   merge d'un lot (`cycle-pr` Étape 7, « Le merge d'un lot »).
3. **Les sessions de lot** : la coordinatrice démarre d'un coup les sessions des lots non mergés,
   une par `start_session` — `initiation: user_asked`, `context: fresh`, worktree de l'application,
   `wake_when_done: true`, `use_worktree: true` (omis, l'outil peut donner à l'enfant le dossier
   de la coordinatrice — `pr-paralleles` Étape 3), `name: <slug>-lot-<k>`. Effort par lot (#107,
   décision 8) : `high` par
   défaut, `max` si le bloc du lot porte un ADR, une surface de sécurité ou un contrat entre piles,
   `medium` pour un lot de doc ou de config seule ; `model` omis quand la coordinatrice est en
   Opus 5.5, `claude-opus-5-5` si elle est au-dessus.

Le brief d'une session de lot porte : le bloc du lot dans le corps de l'issue, l'effort retenu, la
branche d'intégration, et son lead. Il nomme toujours son lead — celui de la vague, ou « aucun » :
sans ce nom, la règle « à défaut l'émettrice » de `cycle-pr` (« Vague parallèle ») ferait de la
coordinatrice le lead. Le premier lot non mergé — le lot 1, ou celui où reprend une issue déjà
entamée — reçoit l'ordre d'ouvrir dans ce brief même ; chaque autre lot reçoit « attends le message
« ouvre le lot <k>/<n> — passation : <chemin> » ; d'ici là, réponds « en attente » et termine ton
tour ».

## Ouvrir le lot suivant — deux preuves, jamais une note

Réveillée par la fin de tour d'une session de lot, la coordinatrice ne tient la note automatique
que pour un réveil, jamais pour un signal (`sessions-liees.md`, « Fin de travail »). Elle ouvre le
lot k+1 sur deux preuves :

1. le message « lot <k>/<n> terminé — PR #<M> mergée dans <branche d'intégration> — passation :
   <chemin> », reçu de la session du lot k ;
2. le fichier présent à ce chemin : `test -f '<chemin>'` sort en 0 — cité, un chemin Windows
   perdant ses antislashs dans le shell.

Un message de fin sans fichier de passation n'ouvre pas le lot suivant : la coordinatrice répond
« passation absente : <chemin> » à la session du lot k, et attend (mesuré le 2026-10-18 sur deux
lots jetables, Notes de la PR #122). Les deux preuves tenues, elle ajoute la PR #<M> à la liste
du body de la PR d'intégration — première ligne intacte, que lit le script de merge d'un lot, et
body relu après écriture (`contraintes.md`, « Écritures sur un artefact distant »).

Puis la dérive, après chaque merge de lot : `git fetch origin`, puis
`git merge-tree --write-tree origin/<trunk> origin/<type>/<slug>` — un prédicat, 0 sans conflit,
1 avec (table `FRESHNESS_GATE_FORMS` de `apps/api/tests/test_agent_skills.py`). Sur 1, elle
s'arrête au premier conflit et le remonte au mainteneur, chemins en conflit cités ; sur tout autre
code non nul, elle s'arrête et lui remonte la sortie. Dans les deux cas, sans ouvrir de lot :
jamais de force-push sur la branche d'intégration, et la résolution n'est pas la sienne.

Puis seulement, par `SendMessage` à la session du lot k+1 : « ouvre le lot <k+1>/<n> —
passation : <chemin> ». Inactive depuis le go, elle reprend sur ce message (`sessions-liees.md`,
« Messages »). Dans l'autre sens, un message de lot arrivé pendant un tour de la coordinatrice
attend la fin de ce tour : c'est une raison de plus pour qu'entre deux lots, elle reste inactive.
Les sessions des lots mergés restent en place jusqu'au nettoyage final (« Après le dernier lot »).

Ces deux contrôles — `test -f` et `merge-tree` — précèdent un `SendMessage`, pas une commande :
rien ne s'y chaîne, ce sont des lectures par construction (`cycle-pr` Étape 7, « Le go, puis le
merge »).

## La session de lot

Ce que le brief de la coordinatrice change au cycle de `cycle-pr` :

- **Premier geste**, au message « ouvre » — à la lecture de son brief pour le premier lot non
  mergé — et pas avant :
  `git fetch origin && git checkout -b <type>/<slug>-lot-<k> --no-track origin/<type>/<slug>`
  (`sessions-liees.md`, « Premier geste », la base étant la branche d'intégration). Chaque lot a
  donc son worktree neuf ; la branche mergée d'un lot n'est jamais un point de départ.
- **La base de la PR** : partout où `cycle-pr` mesure contre le trunk ce que la PR apporte — gabarit
  (3.5), diff holistique (4.1), plage du relecteur (4.2), base de branche et verdict (Étape 7) —,
  le trunk, `main` comme `origin/main`, se lit `origin/<type>/<slug>`. Contre le trunk, chaque
  mesure compterait les lots déjà mergés.
- **Le go du briefing est conditionnel** (#107, décision 5) : la session ne s'arrête à son Étape 1
  que si l'auto-challenge relève un écart avec le bloc du lot, ou s'il lui reste une `[V]` ; sinon
  elle écrit « plan confirmé, aucune `[V]` » dans le body de sa PR et enchaîne — le go du
  découpage vaut pour le lot. Un arrêt prévient aussi la coordinatrice — « bloquant : `[V]` en
  attente dans cette fenêtre » —, sa note de fin de tour n'étant pas un signal.
- **Sa PR** vise la branche d'intégration ; son body s'ouvre par
  « En vol pour #<N> (lot <k>/<n>) », sans `Closes`.
- **La vérification d'avant-go** part au lead que son brief nomme, jamais à la coordinatrice ;
  « lead : aucun » → la session lance elle-même son `verificateur`, sur l'accord du go du découpage.
- **Le merge** suit `cycle-pr` Étape 7, « Le merge d'un lot » : sans go, par le script.
- **Son Étape 8 se borne à cocher ses critères et à écrire sa passation** — en dernier, liste
  vide ou arbitrée (`cycle-pr` Étape 8, « Cas découpé ») —, puis le message de fin à la
  coordinatrice. L'issue reste ouverte : aucun label d'état ne tombe, et `repercussions` ne tourne
  pas ici.

## Relais en cours de lot

La session de lot dont le contexte se remplit pousse sa branche, détache sa tête
(`git switch --detach` — une branche ne s'extrait que dans un seul worktree : mesuré le 2026-10-18,
git 2.47.1, « is already used by worktree », sortie 128),
écrit la variante relais de [prompt-lot-suivant.md](prompt-lot-suivant.md) et envoie « relais
demandé — passation : <chemin> ». Réveillée par ce message, la coordinatrice ne peut pas démarrer
la remplaçante elle-même : elle la propose par une **carte de proposition** (`start_session`,
`initiation: own_initiative`, `use_worktree: true`, brief : la passation de relais), qu'un clic du
mainteneur démarre
dans un worktree neuf ; la remplaçante y reprend la même branche par
`git fetch origin && git switch <type>/<slug>-lot-<k>`. Non mesuré à ce jour.

## Après le dernier lot — la PR d'intégration

Elle n'a pas de code propre, et chaque lot a eu son relecteur : elle passe par les Étapes 5 à 7
seulement — ready, CI, vérification d'avant-go, puis le seul go de merge de l'issue, dans la
fenêtre de la coordinatrice, et le merge derrière la porte de l'Étape 7, en `--rebase` ; squash
seulement sur demande explicite. Puis l'Étape 8 entière : `repercussions` tourne une fois, au
merge de la PR d'intégration. Le lien d'une PR de lot ne se repose pas : elle vise la branche
d'intégration, et GitHub ignore un mot-clé de fermeture hors de la branche par défaut — « these
keywords are ignored, no links are created » (doc « Linking a pull request to an issue », lue le
2026-10-18). L'issue affiche la PR d'intégration, dont le body liste ses PR de lot (« Ouvrir le
lot suivant »).

Le nettoyage des sessions de lot — archivage, worktree, échafaudage `claude/…` (`sessions-liees.md`,
« Nettoyage »), branche de lot mergée par `--rebase` (`pr-paralleles` Étape 8), ancien worktree
d'un relais — se fait une fois, après ce merge, sur un seul accord du mainteneur, que l'archivage
demande (`sessions-liees.md`, « Nettoyage »).

## Repli — la passation manuelle

Si la coordinatrice ne peut pas ouvrir un lot — `start_session` refusé au go, session de lot
disparue de `list_sessions`, message qui n'arrive pas —, la frontière reprend la voie manuelle :
la passation est remise au mainteneur, qui ouvre la session du lot (`cycle-pr` Étape 8, « Cas
découpé »), et l'échec devient une observation du journal.
