---
name: pr-paralleles
description: Orchestre plusieurs PR en parallèle via des git worktrees — sélectionne des issues ready-for-agent non bloquées et à faible recouvrement de fichiers, crée un worktree + une branche par issue, prépare une session par worktree, tient un tableau de bord, et nettoie après merge. Utiliser pour développer plusieurs issues en même temps, paralléliser la réalisation de PR, ou lancer une vague de travail AFK.
argument-hint: "[#issues | nombre de PR à lancer]"
---

# PR parallèles

Permet de travailler sur **plusieurs PR en même temps** sans qu'elles se marchent dessus, en
isolant chaque unité de travail dans son propre **git worktree** (un dossier de travail + une
branche distincts, partageant le même dépôt `.git`). Chaque worktree se développe dans **sa propre
session Claude Code**, en suivant `cycle-pr`.

Prérequis : `.claude/pipeline.config.md` existe (sinon lancer `init-projet`).

## Quand l'utiliser

- Plusieurs issues `ready-for-agent` sont prêtes et indépendantes.
- L'utilisateur veut « faire plusieurs PR en même temps ».

## Process

### 1. Rassembler les issues candidates

Un argument borne le lot : des numéros d'issues (`#N`) → ne considérer que celles-là parmi les
`ready-for-agent` listées ci-dessous, puis le crible de l'étape 2 ; un nombre nu → c'est le degré
de parallélisme à proposer à l'étape 2.

Lister les issues prêtes :

```
gh issue list --label ready-for-agent --state open --json number,title,labels
```

Lire l'« agent brief » de chacune (commentaire posé par `triage`). En extraire la **liste des
fichiers/zones probablement touchés** (les briefs décrivent des interfaces et des comportements,
pas des chemins — déduire les zones du code à partir de là).

### 2. Sélectionner un lot sûr

Ne retenir que des issues :

- **sans bloqueur en attente** — vérifier le champ « Bloquée par » de l'issue / du brief ; tout
  bloqueur doit être déjà mergé.
- **à faible recouvrement de fichiers/zones** entre elles — deux issues qui touchent le même
  module sont des candidates au conflit de merge ; les exécuter en série, pas en parallèle.
- **à faible recouvrement sur les ressources à état partagées** — l'isolation par worktree ne
  couvre que le système de fichiers. Recenser les services à état que les commandes de test
  touchent (base, cache, broker, ports du compose du poste) et vérifier que chaque suite s'y
  présente sous une clé propre, sur l'**écriture et l'observation** (purges et scans compris).
  Sinon, deux issues dont les suites touchent le même magasin se recouvrent comme un fichier
  partagé : en série.

Présenter le lot proposé à l'utilisateur sous forme de tableau (issue, titre, zones touchées,
risque de recouvrement), suivi pour chaque issue de **deux ou trois phrases en langage courant**
qui disent ce qu'elle apporte à l'utilisateur final et ce qu'elle change dans le code — pas le
titre reformulé, pas le brief recopié. Puis **demander confirmation** avant de créer quoi que ce
soit. Recommander un degré de parallélisme raisonnable (souvent 2–4, ou le nombre donné en argument)
plutôt que tout d'un coup.

### 3. Créer un worktree + une branche par issue

Pour chaque issue retenue, depuis `main` à jour — **les deux `main`** —, et derrière une **porte** :
une commande dont le code de sortie porte la condition, enchaînée par `&&` à celle qu'elle garde.
`git rev-parse main origin/main` ne garde rien : il **imprime** deux SHA et sort en 0, et un
worktree créé sur un `main` en retard prive la session de commits dont son brief dépend
(`cycle-pr` Étape 7, « Le go, puis le merge », pour la classe entière).

```
git fetch origin
git merge-base --is-ancestor main origin/main && git merge-base --is-ancestor origin/main main && git worktree add ../<repo>--<numéro-issue> -b <type>/<slug> origin/main
```

**Deux prédicats**, parce que `--is-ancestor` dit « ancêtre ou égal » et qu'une seule direction
laisse passer l'autre cas : les deux ensemble valent l'égalité. Les deux directions comptent ici —
`origin/main` en avance prive chaque session de commits dont son brief dépend ; `main` local en
avance ferait apparaître ses commits non poussés dans le diff de **chaque** PR du lot. Le
raisonnement complet, le rôle de `&&` et la mesure du garde de permissions sont à `cycle-pr`
Étape 1 ; ne pas les recopier ici.

**Au blocage**, laquelle des deux a mordu se lit par `git status -sb` (`[ahead n]` / `[behind n]`),
jamais par `git status --porcelain`, **vide** sur une branche en avance (mesuré). Rattrapages :
`main` local en avance → s'arrêter et demander à l'utilisateur de pousser, ou l'autorisation de le
faire, **avant le premier worktree** ; `origin/main` en avance → sur `main`, `git pull --ff-only`.
Dans les deux cas, rejouer la porte.

- `<type>` = `feat` / `fix` / `chore` / `docs` / `refactor` selon la catégorie de l'issue.
- `<slug>` = description courte en kebab-case.
- Le dossier `../<repo>--<numéro-issue>` est un **frère** du dépôt, pour ne pas polluer l'arbre.

**Provisionner chaque worktree — obligatoire avant de le confier à une session.** Un worktree est
un checkout neuf, pas une copie de l'environnement de travail : tout ce que git ignore en est
absent. Cinq gestes, dans l'ordre :

1. **Copier depuis le dépôt principal** les fichiers locaux ignorés par git dont les commandes du
   projet dépendent — ex. un `.env` lu par le fichier de commandes, `.claude/settings.local.json`
   (jetons MCP). Les repérer en croisant `.gitignore` et le fichier de commandes, pas de mémoire.
2. **Recréer les artefacts d'outillage par l'outil qui les gère** — ex. le lien de SDK posé par le
   gestionnaire de version déclaré dans « runtime + version » de `.claude/pipeline.config.md`
   (FVM, mise, asdf…). **Jamais de lien fabriqué à la main** (`mklink`, `ln -s`) : l'outil qui
   crée le lien sait aussi le défaire, un lien manuel se fait traverser à la suppression (étape 8).
   Si l'outil n'est pas résolvable depuis le shell, utiliser la surcharge que la CI emploie déjà
   plutôt que d'improviser.
3. **Installer les dépendances des piles que l'issue touche**, par la commande `install` de
   chaque pile dans `.claude/pipeline.config.md` — une pile non touchée ne s'installe pas.
4. **Commande de fumée** avant de remettre le prompt (la commande `lint` de la config) : un échec
   « exécutable introuvable » signale un worktree non préparé, pas un défaut du code.
5. **Vérifier que chaque service à état recensé à l'étape 2 pour cette issue répond** — démon
   Docker par `docker info`, base ou broker par leur commande de santé : la fumée `lint` ne les
   exerce pas, et un échec de suite au premier test coûterait un tour de session. Consigner
   « provisionné ✅ » dans le tableau de bord.

**Jamais d'installation des hooks depuis un worktree.** `.git/hooks/` vit dans le répertoire git
commun, partagé par tous les worktrees et le clone principal, et le gabarit écrit par la commande
`hooks` de `.claude/pipeline.config.md` y fige un **chemin absolu** vers l'interpréteur qui l'a
installé. Lancée depuis un worktree, elle fait pointer le hook de tout le dépôt vers un
environnement qui disparaît avec le worktree — et le clone principal refuse ensuite tout commit
(« exécutable introuvable »), cassé par un worktree qu'il n'a jamais ouvert. Les hooks
s'installent une fois, depuis le clone principal ; un worktree les trouve installés.

### 4. Tenir le tableau de bord

Maintenir un fichier `PR-PARALLELES.md` à la racine du dépôt (et le tenir à jour à chaque
changement d'état) :

```markdown
# PR en parallèle — <date>

| Issue | PR | Branche | Worktree | Session | Base du verdict | État |
|-------|----|---------|----------|---------|-----------------|------|
| #51 lot 1/2 | #62 (draft) | feat/extraction-pdf | ../app--51 | app-40 · 7534fbb3 | — | 🟡 en cours |
| #52 | #63 | fix/quota-upload | ../app--52 | app-73 · 2afdedb5, 9c1e0a4f (relais) | 863d606 | 🔵 en review |
```

Trois colonnes portent chacune une identité qu'un nom ne suffit pas à tenir :

- **Issue** — `#N lot k/n` dès qu'une issue est réalisée en plusieurs lots. Le worktree survit au
  merge d'un lot, la branche non : sans le rang, une ligne mergée et une ligne en vol se
  ressemblent (obs 36). Seul le dernier lot porte `Closes`, les autres `En vol pour #N (lot k/n)`.
- **Session** — le nom **et l'UUID**. Le nom est un repère qui tourne : une session passe de
  `app-6b` à `app-ef` en cours de vie sans que rien ne le signale. L'UUID ne change pas, et c'est
  lui qu'un ordre **durable** comme `EnterWorktree` doit viser (obs 34, étape 5). Une session
  **relayée** ajoute son UUID à côté de ceux qui l'ont précédée au lieu de les remplacer :
  l'unité qui survit au relais est le cycle, et c'est elle qui porte la liste de ses sessions
  (obs 40) — c'est aussi cette liste que `cycle-pr` Étape 8 passe à son bilan, un transcript par
  UUID.
- **Base du verdict** — le SHA d'`origin/main` pour lequel le dernier verdict d'avant-go a été
  rendu (étape 6). Un verdict ne vaut que pour sa base : si le trunk avance, il est périmé avec
  toutes les preuves de la PR. Sans ce SHA, on relit un verdict sans savoir de quel état il parle.

États : `🟡 en cours` → `🔵 en review` → `🟢 mergée` → `⚪ worktree nettoyé`.

La colonne **PR** se remplit dès l'Étape 2 de `cycle-pr` : chaque session ouvre sa **PR draft avant
d'écrire la moindre ligne**. Le lead la lit sans rien demander aux sessions —
`gh pr list --state open --json number,headRefName,isDraft` relie chaque branche à sa PR. C'est ce
qui rend le lot lisible d'un coup d'œil — et détectable par `repercussions`.

### 5. Démarrer chaque session par message inter-sessions

L'utilisateur **ouvre lui-même** ses sessions — application de bureau Claude Code ou extension
VS Code, **n'importe où dans le dépôt** (la fenêtre principale suffit) — jamais par une commande
`claude` dans un terminal. Le lead ne lui donne **rien à coller** ni à taper : il lui demande
d'ouvrir N sessions — en précisant qu'il peut y taper `/i-have-adhd` s'il veut le mode court et
que ce skill est installé —
puis de revenir dire « ouvertes ». Inutile d'ouvrir une fenêtre par dossier de worktree : chaque
session **se déplace elle-même** dans son worktree (ci-dessous). Tout le reste transite par
`SendMessage`, que les sessions Claude Code d'une même machine partagent sans configuration — un
message de pair suffit à donner son premier tour à une session vierge.

**Placement — l'identité d'abord, l'ordre ensuite.** `ListAgents` liste les pairs `interactive`,
mais ni l'âge ni le nom ne **désignent** une session : l'utilisateur ouvre ses propres fenêtres
pendant la vague, et deux sessions plus jeunes que la vague se ressemblent. Un `EnterWorktree`
envoyé à la mauvaise déplace **durablement** une session qui travaillait dans le clone principal
(obs 34). Dès qu'il y a **plus d'une** session plus jeune que la vague, ou que l'utilisateur en
désigne une par son identifiant, demander d'abord l'identité, **sans rien faire changer** :

```
Réponds-moi le chemin de ton répertoire scratchpad, rien d'autre, et ne change rien.
```

Ce chemin porte l'**UUID de session** ; les refs de `ListAgents` (`[79236b]`) n'en dérivent pas, et
le nom « #N » que l'utilisateur a donné à une fenêtre est un indice, pas une preuve. Reporter
l'UUID dans la colonne « Session » du tableau (étape 4). **Puis** seulement l'affectation :

```
Entre dans le worktree `<chemin absolu>` avec l'outil `EnterWorktree`, puis réponds-moi la
sortie de `git rev-parse --show-toplevel`, rien d'autre.
```

`EnterWorktree` change le répertoire **de la session** (durable), pas seulement du shell — un
simple `cd` ne suffirait pas. La réponse arrive dans un bloc
`<cross-session-message from="…" from-name="…">` : `from-name` est la session, la sortie prouve
son placement. **N'envoyer le prompt de démarrage qu'à une session dont la réponse nomme le bon
worktree** — c'est la vérification qui empêche un prompt de partir vers une session restée sur
`main` ou placée sur le worktree d'une autre issue. **Les noms tournent** : relancer `ListAgents`
avant chaque envoi, jamais d'envoi à un nom noté plus tôt sans l'avoir revu dans la liste.

Cette vérification est une **lecture**, pas une porte, et c'est structurel : elle franchit une
frontière de session, où aucune commande du lead ne peut porter la condition de l'ordre suivant
(`cycle-pr` Étape 7, « Le go, puis le merge », pour le dénombrement de la classe).

**Session relayée.** Un cycle peut durer plus qu'un contexte : la session qui reprend un worktree
envoie d'abord au lead son chemin de scratchpad et la sortie de `git rev-parse --show-toplevel`,
et le lead **ajoute** son UUID à la colonne « Session » en gardant ceux des sessions précédentes,
puis repose son abonnement idle — celui de la session remplie ne distingue plus rien (obs 40). La
passation que la session sortante écrit porte donc deux choses que le relais ne peut pas deviner :
l'adresse du lead, et cette consigne-ci.

**Une session neuve par lot, et c'est la session sortante qui la fait démarrer.** Une issue
réalisée en plusieurs lots ne garde **pas** la même session d'un lot au suivant : le contexte d'un
lot porte les hypothèses qui l'ont produit, et une session qui enchaîne arrive au lot suivant à
moitié pleine, donc se fait relayer en plein cycle (`cycle-pr` Étape 8, « Une session neuve par
lot »). La session qui finit un lot écrit, après sa passe `repercussions`, le prompt du lot suivant
depuis `.claude/skills/cycle-pr/references/prompt-lot-suivant.md` et le **remet au mainteneur** ;
la session neuve entre dans le worktree, crée sa branche, puis envoie au lead son chemin de
scratchpad, sa racine et sa branche. Le lead vérifie, inscrit l'UUID au tableau (étape 4), et
répond par ce que lui seul sait : base du moment, PR en vol, fichiers croisés. Le lead ne réécrit
plus le prompt à chaque frontière — c'est exactement ce qui faisait grossir son contexte (obs 62).

**Démarrage.** Envoyer ensuite à chaque session son prompt, dans cet ordre :

```
Tu travailles dans le worktree `<chemin absolu>` (branche `<branche>`), dédié à l'issue #N.
Je suis la session lead de la vague : ton interlocuteur pour la vérification avant merge de
`cycle-pr` (Étape 7) — réponds toujours au `from` de ce message.
Charge le skill `task-observer` s'il est installé (session longue ; le journal est hors du
worktree, chemin dans CLAUDE.md). Lis CLAUDE.md, .claude/pipeline.config.md et ta mémoire de phase.

Réalise le cycle complet de l'issue #N en invoquant le skill `cycle-pr` (outil Skill) avec N —
brief : commentaire de l'issue.
Tu es autorisé à lancer l'équipier `relecteur` de l'Étape 4.2 : **un seul pour toute la PR**, à
qui reviennent la seconde passe et la relance par `SendMessage`. Cette
invocation de `cycle-pr` vaut demande de l'utilisateur.
Ne lance pas la commande `hooks` de la config ici : les hooks sont partagés entre worktrees et
déjà installés depuis le clone principal.
Le garde de permissions de ta session refuse les commandes qu'il ne sait pas vérifier, sans
nommer le fragment fautif — heredoc suivi d'une commande, boucle `for`, gabarit `--format` ou
`--jq` avec accolades, `sh -c` en ligne, enchaînement de trois commandes. Écris les fichiers
longs avec l'outil d'écriture plutôt qu'un heredoc, une commande par objet plutôt qu'une boucle,
un script dans le répertoire temporaire de session plutôt qu'un `-c` : chaque refus coûte deux ou
trois reformulations à l'aveugle.
<une ligne par point de vigilance propre à cette issue : HITL attendu, fichier partagé avec une
autre PR du lot et ordre de merge, décision verrouillée à ne pas rouvrir>
```

**Une consigne du lead cite l'artefact qui la porte** — le fichier, le test, le § d'issue qui
gardent l'invariant — jamais l'énoncé seul : une reformulation dérive vers le plus strict, et
« ne l'assouplis pas » décourage précisément la vérification que la session doit faire à son
Étape 1. Une divergence remonte au mainteneur.

Les skills s'invoquent **par l'outil Skill, jamais par `/commande`** : un `/nom` dans un message
de pair n'est pas une saisie de l'utilisateur, la session peut ne pas le déclencher. Ne jamais
inscrire dans le prompt un skill marqué `disable-model-invocation` (frontmatter à vérifier avant
d'écrire « invoque X ») : l'outil Skill le refuse — c'est le cas d'`i-have-adhd`, que seule une
saisie `/i-have-adhd` de l'utilisateur active, d'où la consigne donnée à l'ouverture des
fenêtres. La vérification de placement existe parce qu'un prompt envoyé à la mauvaise session
travaillerait sur `main` ou sur le worktree d'une autre issue, sans rien signaler.

Chaque session est **indépendante** : elle déroule le briefing pré-PR, **ouvre sa PR draft**, puis
le cycle de commit, les relectures, et sort du draft en fin de parcours. Ses questions à
l'utilisateur s'affichent dans **sa** fenêtre, pas dans celle du lead. Les worktrees partageant le
même `.git`, les branches sont visibles entre elles, mais les fichiers de travail sont isolés.

### 6. Vérifier chaque PR avant le go — un vérificateur éphémère par (PR, go)

À l'Étape 7 de `cycle-pr`, chaque session **propose à l'utilisateur** d'envoyer au lead l'état de
sa PR ; rien ne part sans son accord. Quand ce message arrive :

1. **Déléguer la vérification, ne pas la lire soi-même.** Lancer l'équipier **`verificateur`**
   (`.claude/agents/verificateur.md`), **un par (PR, go)** — jamais réutilisé d'un go au suivant,
   c'est ce qui garantit qu'aucun verdict n'hérite du précédent. Il reçoit le numéro de la PR,
   celui de l'issue, le chemin absolu du worktree et la liste des autres branches en vol. Il ne
   reçoit **ni** le message de la session **ni** aucun résumé du lead, et c'est là tout le
   dispositif : un vérificateur neuf ouvre l'artefact, sur disque et sur la forge, donc il n'a
   **rien à désapprendre**. C'est le mode d'échec exact d'obs 52 — une consigne recopiée d'une
   mémoire de phase citait un correctif en énonçant la règle que ce correctif avait retirée, et
   quatre artefacts en aval l'ont reprise sur trois sessions.

   Le lead ne garde que le **verdict structuré** que le rôle rend : critères ✅/❌/⚠️ avec preuve,
   base du dernier run et ses parents, conflit, heurts `decisions-vs-doc`, fichiers croisés, et ce
   que le plafond a laissé « non vérifié ». C'est ce qui empêche son contexte de grossir d'un diff
   complet par PR et par go, jusqu'à devoir être relayé (obs 62). Le rôle porte **ce qu'il
   vérifie** et dans quel ordre : ne pas le recopier ici, deux énoncés de la même consigne
   divergent au premier amendement.

   Inscrire la **base du verdict** dans le tableau (étape 4), et la reporter dans la réponse : un
   verdict ne vaut que pour l'`origin/main` sur lequel il a été pris. Si le trunk avance ensuite,
   le redemander — un vérificateur neuf, puisqu'ils sont éphémères — plutôt que le consommer.
2. **Répondre à la session** (`SendMessage`, au `from` du message), sous l'une des deux formes :
   `Verdict : rien à corriger.` — ou `À corriger avant merge :` suivi d'une liste numérotée, chaque
   point avec fichier et raison. Le lead ne donne **jamais** le « go merge » : c'est l'utilisateur,
   dans la fenêtre de la session. Ni `contraintes.md` ni le harness ne l'admettent — une session
   ne prend jamais un message de pair pour une approbation.
3. **Résumer à l'utilisateur** dans la fenêtre du lead : les deux phrases de vulgarisation de
   l'étape 2 de ce skill sur ce que fait la PR, le verdict, et où taper le go — « go merge dans
   `<session>` ».

Après corrections, la session propose à nouveau l'envoi ; le lead refait la passe sur le delta.
À tout moment, l'utilisateur peut aussi dire à une session « discute de ça avec le lead » —
c'est le seul autre canal, et il passe par lui.

### 7. Surveiller et faire converger

- `git worktree list` montre tous les worktrees actifs — **deux familles, à ne pas confondre** :
  un worktree **d'issue**, qui a sa ligne au tableau de bord, et un worktree **de relecture**
  (`.claude/worktrees/agent-<id>`), qui n'en a jamais et vit tant que la boucle 4.2 d'une PR
  n'est pas fermée. C'est l'absence de ligne au tableau qui le distingue, jamais un verrou
  git : le verrou ne tient que pendant l'invocation initiale de l'agent (`cycle-pr` 4.2,
  « Retrait »). Le second n'est pas une dérive : le retirer termine le
  relecteur et ferme la voie de la relance (`cycle-pr` 4.2, « Retrait »). Seule la session qui l'a
  lancé le retire. Le `verificateur` de l'étape 6, lui, n'en crée **aucun** — il n'a pas
  d'`isolation` : un worktree par (PR, go) serait précisément le coût que son éphémérité évite.
- Quand une PR passe en review puis est mergée, mettre à jour `PR-PARALLELES.md`.
- Après chaque merge, la session concernée déroule la clôture de l'Étape 8 de `cycle-pr` —
  label d'état retiré, critères d'acceptation cochés, puis la passe `repercussions`. **C'est le
  moment le plus dangereux d'une vague parallèle** : les autres issues du
  lot sont en cours de développement, et leurs sessions ont déjà lu leur spec.
  - `repercussions` les détecte comme **« en vol »** (via les PR ouvertes et ce tableau de bord) :
    il **n'édite pas** leur corps et **ne change pas** leurs labels, il dépose un commentaire sur
    **leur PR ouverte**, que `cycle-pr` traite à son Étape 6.
  - **Tenir `PR-PARALLELES.md` à jour est donc fonctionnel, pas décoratif** : une ligne périmée
    (issue mergée encore marquée en cours, ou worktree **d'issue** actif absent du tableau) fait
    mal classer une issue — et une issue en vol traitée comme dormante se fait réécrire sa spec
    sous les pieds. Un worktree de relecture absent du tableau, lui, est l'état normal.
  - Un signalement **bloquant** sur une issue du lot : le lead **interrompt la session** par
    `SendMessage` (« arrête-toi après l'outil en cours, signalement bloquant : … ») — une session
    occupée lit ses messages entre deux appels d'outils, pas seulement en fin de tâche. Le temps
    d'arbitrer, elle ne produit pas de travail à jeter.
- **Après chaque merge du lot, avant toute consigne aux sessions encore en vol** : croiser les
  fichiers **réellement mergés** (`gh pr diff <PR> --name-only`) avec ceux de chaque branche en vol
  (`git diff --name-only origin/main...<branche>`). La consigne se fonde sur ce croisement, jamais
  sur la carte de recouvrement de l'étape 2 : elle décrit des issues entières, un merge livre un
  lot. Une branche qui recouvre vérifie d'abord l'absence de conflit — `git merge-tree
  --write-tree origin/main <branche>`, **prédicat** : 0 sans conflit, 1 avec, mesuré le 2026-10-13
  avec un témoin de chaque côté (table `FRESHNESS_GATE_FORMS` de
  `apps/api/tests/test_agent_skills.py`) — et relance sa CI, qui tourne sur la
  référence de fusion — pas de commit de fusion sur un trunk fusionné par rebase, ni de rebase
  d'une branche poussée sans demande explicite (`contraintes.md`) ; un conflit se résout par un
  commit réel sur la branche.

**Session disparue.** Une session absente de `ListAgents` alors que sa PR est ouverte est **morte,
pas en attente** : l'abonnement idle ne les distingue pas — une session morte et une session qui
attend un go rendent le même silence (obs 54). Dans cet ordre :

1. **Mesurer les artefacts** — tête, base, CI, body de PR, worktrees : c'est ce qui est *prouvé*,
   et ça ne dépend pas d'elle.
2. **Lire la fin de son récit**, et celui de ses sous-agents :

   ```
   python <répertoire de ce skill>/scripts/fin-transcript.py <transcript .jsonl> [<tours>]
   ```

   Le transcript vit sous `~/.claude/projects/<id du répertoire de travail>/<uuid>.jsonl`, ses
   sous-agents dans `<uuid>/subagents/`. L'uuid est celui du répertoire scratchpad de la session
   (étape 5), et pour une session placée en worktree c'est le dossier **du worktree** qui porte le
   projet, pas celui du clone principal. Le script rend les derniers tours, les messages du
   mainteneur — débarrassés des blocs que le harnais injecte — et le dernier texte de chaque
   sous-agent, « mort avant de rendre » compris.
3. **Écrire la passation en séparant prouvé et récit** : le point 1 donne le premier, le point 2 le
   second, et les mêler fait hériter la reprise d'un récit comme s'il était mesuré.
4. **Proposer d'abord de rouvrir la même conversation** — son contexte est intact, elle coûte bien
   moins qu'un relais neuf. Un relais neuf sinon, avec le prompt de l'étape 5.
5. **Identifier la reprise par son scratchpad** (étape 5) : même UUID → un prompt court suffit ;
   autre UUID → `EnterWorktree`, puis le prompt de relais.

Un **sous-agent de fond lancé avant l'arrêt est perdu** : le relancer sur la même plage. C'est ce
qu'obs 54 a payé — une seconde passe de relecture partie six minutes avant l'arrêt, morte sans
rapport, et un body de PR rédigé dans le contexte sans avoir jamais été posé.

### 8. Nettoyer après merge

Une fois une PR mergée et sa branche supprimée côté distant, **faire d'abord sortir du worktree
toute session qu'on y a placée.** Un dossier qui est le répertoire courant d'un processus ne
s'efface pas sous Windows : `git worktree remove` désenregistre le worktree, **efface tout son
contenu**, puis échoue sur le dossier racine (« Permission denied ») — on découvre le verrou par
l'erreur, avec un dossier à moitié supprimé et déjà désenregistré, état que la procédure ne décrit
nulle part (obs 42). Demander donc à chaque session placée là un `ExitWorktree`, ou de se placer
dans le clone principal, et **attendre sa réponse** : son message de clôture porte la ligne « je
suis sortie du worktree » (`cycle-pr` Étape 8), parce qu'une session sait qu'elle a fini avant que
le lead ne le sache.

Puis **détacher ce qui n'appartient pas au worktree** : énumérer les liens et jonctions qu'il
contient avec un détecteur qui **prouve d'abord qu'il voit** — le filtre `Where-Object LinkType`
de PowerShell a rendu une liste vide sur une jonction connue du système, et une liste vide
autorise une suppression :

```
python - <chemin du worktree> <<'EOF'
import os, stat, sys
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
def est_lien(p):
    st = os.lstat(p)
    return stat.S_ISLNK(st.st_mode) or (os.name == "nt" and bool(st.st_file_attributes & REPARSE))
temoin = r"C:\Documents and Settings" if os.name == "nt" else "/proc/self/exe"
assert est_lien(temoin), f"témoin non détecté : {temoin} — détecteur aveugle, ne rien supprimer"
liens = []
def illisible(e): sys.exit(f"dossier illisible : {e} — liste incomplète, ne rien supprimer")
for racine, dossiers, fichiers in os.walk(sys.argv[1], onerror=illisible):
    for nom in dossiers + fichiers:
        chemin = os.path.join(racine, nom)
        if est_lien(chemin):
            liens.append(chemin)
    dossiers[:] = [d for d in dossiers if os.path.join(racine, d) not in liens]  # jamais dans un lien
print(f"témoin détecté ; {len(liens)} lien(s) ou jonction(s)", *liens, sep="\n")
EOF
```

Le témoin est une jonction que le système possède toujours ; s'il n'est pas vu, la liste ne vaut
rien. Et **on ne descend jamais dans un lien** : un parcours qui suit une jonction vers la
ressource partagée liste ses liens internes comme « à retirer », et boucle sur une jonction vers
un ancêtre — `Path.rglob` fait les deux, mesuré. Retirer chaque lien trouvé avec la commande qui
supprime **le lien, pas sa cible**
(`cmd /c rmdir <jonction>` sous Windows, `rm <lien>` ailleurs). Une suppression récursive peut
traverser une jonction et vider la ressource partagée qu'elle vise, sans aucun avertissement.
Puis seulement :

```
git worktree remove ../<repo>--<numéro-issue>
gh pr view <n> --json state,headRefOid   # MERGED, et headRefOid égal à `git rev-parse <branche>`
git branch -D <type>/<slug>
```

`git branch -d` ne satisfait qu'une fusion par commit de merge : rebase et squash réécrivent les
commits, et son contrôle « not fully merged » refuse une branche pourtant dans `main`. La preuve
est celle de la forge — PR `MERGED` et tête identique à la branche locale, donc rien de local non
poussé —, puis `-D`. Tout contrôle qui autorise une suppression se valide d'abord sur un
**témoin positif**, un cas dont la réponse « oui » est connue : `cmd && ok || ko` confond
condition fausse et commande en erreur, et c'est l'outil qu'on suspecte en premier.

**Ce contrôle-ci reste une lecture, et c'est structurel** : il compare la valeur rendue par la
forge à celle d'une référence locale, donc deux outils, ce qu'aucune commande ne porte sans
substitution — refusée par le garde d'une session isolée. Il n'est pas une porte au sens de
`cycle-pr` Étape 7 (« Le go, puis le merge »), où vit le dénombrement de la classe, et ce qu'il
garde est une suppression **locale**, récupérable par le reflog.

Vérifier ensuite que les ressources partagées répondent encore : le dépôt principal passe sa
commande de fumée, et le hook partagé pointe toujours sur lui — le chemin d'interpréteur figé
dans `.git/hooks/pre-commit` (`grep INSTALL_PYTHON .git/hooks/pre-commit` pour pre-commit) est
sous le clone principal, sinon relancer la commande `hooks` de la config **depuis sa racine**.
Un worktree supprimé qui avait installé les hooks laisse ce chemin mort, et la vague sabote le
dépôt qu'elle servait.

Marquer la ligne `⚪ worktree nettoyé` dans le tableau. Quand tout le lot est nettoyé, supprimer
`PR-PARALLELES.md` (ou archiver le tableau dans les notes du projet).

**Issue en plusieurs lots : le worktree survit, la branche meurt.** Après le merge d'un lot qui ne
ferme pas l'issue, rien de ce qui précède ne s'applique au worktree — il sert au lot suivant. Ce
qui meurt, c'est la **branche** : sous un trunk fusionné par rebase ou squash, ses commits
réécrits doubleraient dans la PR du lot suivant. Nommer explicitement les deux à chaque frontière,
sinon une session prolonge un artefact mort (obs 36). La voie normale est celle de l'étape 5 — la
session sortante remet le prompt, la session neuve crée sa branche depuis `origin/main` et
supprime la précédente, locale et distante. **Repli**, si la session sortante a disparu : le lead
fait les deux gestes à sa place — `git checkout -b <type>/<slug> origin/main` dans le worktree,
suppression de la branche mergée, réinstallation et fumée —, puis place une session neuve comme à
l'étape 5.

**Bilan de vague.** Compter les issues ouvertes pendant la vague
(`gh issue list --state all --search "created:>=<date de début>"`) et justifier chacune par le
barreau de `contraintes.md` « Création d'issues en cours de cycle » qui a échoué — gabarit,
catégorie et thème vérifiés. Une vague qui ouvre plus d'issues qu'elle n'en ferme est un signal à
remonter au mainteneur, pas un résultat. Vérifier aussi que chaque issue réalisée en plusieurs
lots affiche autant de PR liées que de lots (`cycle-pr` Étape 8, cas découpé) : chaque session a
obéi à « un seul `Closes` », et le trou ne se voit qu'en regardant la population.

## Règles

- **Jamais deux worktrees sur des zones qui se recouvrent fortement** sans le signaler — c'est la
  première cause de conflits.
- Chaque session suit `cycle-pr` à la lettre (le parallélisme ne dispense d'aucune étape, ni du
  cleanup pass verbatim).
- **Jamais d'auto-merge**, même en parallèle : chaque PR attend son « go » humain.
- Ne jamais créer de worktree sur une branche déjà active dans un autre worktree.
