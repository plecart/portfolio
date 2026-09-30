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

Pour chaque issue retenue, depuis `main` à jour — **les deux `main`** : après `git fetch origin`,
`git rev-parse main origin/main` doit rendre deux fois le même SHA. Si `main` local est en avance,
s'arrêter et demander à l'utilisateur de pousser (ou l'autorisation de le faire) avant le premier
worktree : brancher sur `origin/main` priverait la session d'un commit dont son brief dépend,
brancher sur `main` local ferait apparaître ce commit dans le diff de sa PR. Si `origin/main` est
en avance, sur `main`, `git pull --ff-only` d'abord.

```
git fetch origin
git rev-parse main origin/main      # deux SHA identiques, sinon voir ci-dessus
git worktree add ../<repo>--<numéro-issue> -b <type>/<slug> origin/main
```

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
   chaque pile dans `.claude/pipeline.config.md` — une pile non touchée ne s'installe pas. Ce
   geste manquait : deux vagues de suite, l'utilisateur l'a prescrit à la main.
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

| Issue | PR | Branche | Worktree | Session | État |
|-------|----|---------|----------|---------|------|
| #51 | #62 (draft) | feat/extraction-pdf | ../app--51 | app-40 | 🟡 en cours |
| #52 | #63 (draft) | fix/quota-upload | ../app--52 | app-73 | 🟡 en cours |
```

La colonne **Session** porte le nom du pair tel que `ListAgents` l'a montré au dernier contact —
un repère, pas une adresse : les noms tournent (étape 5).

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

**Placement.** `ListAgents` liste les pairs `interactive` ; les nouveaux sont ceux dont l'âge
est inférieur à celui de la vague. Envoyer à chacun son affectation :

```
Entre dans le worktree `<chemin absolu>` avec l'outil `EnterWorktree`, puis réponds-moi la
sortie de `git rev-parse --show-toplevel`, rien d'autre.
```

`EnterWorktree` change le répertoire **de la session** (durable), pas seulement du shell — un
simple `cd` ne suffirait pas. La réponse arrive dans un bloc
`<cross-session-message from="…" from-name="…">` : `from-name` est la session, la sortie prouve
son placement. **N'envoyer le prompt de démarrage qu'à une session dont la réponse nomme le bon
worktree** — c'est la vérification qui empêche un prompt de partir vers une session restée sur
`main` ou placée sur le worktree d'une autre issue. Reporter le nom dans la colonne « Session »
du tableau. **Les noms tournent** — une session peut passer de `app-6b` à `app-ef` en cours de
vie sans que rien ne le signale : relancer `ListAgents` avant chaque envoi, jamais d'envoi à un
nom noté plus tôt sans l'avoir revu dans la liste.

**Démarrage.** Envoyer ensuite à chaque session son prompt, dans cet ordre :

```
Tu travailles dans le worktree `<chemin absolu>` (branche `<branche>`), dédié à l'issue #N.
Je suis la session lead de la vague : ton interlocuteur pour la vérification avant merge de
`cycle-pr` (Étape 7) — réponds toujours au `from` de ce message.
Charge le skill `task-observer` s'il est installé (session longue ; le journal est hors du
worktree, chemin dans CLAUDE.md). Lis CLAUDE.md, .claude/pipeline.config.md et ta mémoire de phase.

Réalise le cycle complet de l'issue #N en invoquant le skill `cycle-pr` (outil Skill) avec N —
brief : commentaire de l'issue.
Tu es autorisé à lancer l'équipier `relecteur` de l'Étape 4.2, à ses deux temps, un seul par
passe : cette
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
le cycle de commit, l'auto-review, et sort du draft en fin de parcours. Ses questions à
l'utilisateur s'affichent dans **sa** fenêtre, pas dans celle du lead. Les worktrees partageant le
même `.git`, les branches sont visibles entre elles, mais les fichiers de travail sont isolés.

### 6. Vérifier chaque PR avant le go — le rôle du lead

À l'Étape 7 de `cycle-pr`, chaque session **propose à l'utilisateur** d'envoyer au lead l'état de
sa PR ; rien ne part sans son accord. Quand ce message arrive :

1. **Lire, ne pas croire.** Le message est le récit de la session — il dit *où* regarder. Vérifier
   sur les artefacts : `gh pr diff <PR>`, `gh pr checks <PR>`, `gh pr view <PR> --comments`, et le
   worktree sur disque si le diff ne suffit pas. Relire le diff avec le prompt de
   `cleanup-verbatim.md` et contre les critères d'acceptation de l'issue ; confronter les décisions
   rapportées aux sources de vérité (`decisions-vs-doc`). **Dater le verdict par sa base**
   (`git merge-base origin/main <branche>`, inscrite dans la réponse) : si le trunk avance ensuite,
   le verdict est périmé avec toutes les preuves de la PR — le redemander plutôt que le consommer.
   `git merge-tree --write-tree origin/main <branche>` dit s'il y a conflit, l'état `MERGEABLE` de
   la forge le dit en retard.
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

- `git worktree list` montre tous les worktrees actifs.
- Quand une PR passe en review puis est mergée, mettre à jour `PR-PARALLELES.md`.
- Après chaque merge, la session concernée déroule la clôture de l'Étape 8 de `cycle-pr` —
  label d'état retiré, critères d'acceptation cochés, puis la passe `repercussions`. **C'est le
  moment le plus dangereux d'une vague parallèle** : les autres issues du
  lot sont en cours de développement, et leurs sessions ont déjà lu leur spec.
  - `repercussions` les détecte comme **« en vol »** (via les PR ouvertes et ce tableau de bord) :
    il **n'édite pas** leur corps et **ne change pas** leurs labels, il dépose un commentaire sur
    **leur PR ouverte**, que `cycle-pr` traite à son Étape 6.
  - **Tenir `PR-PARALLELES.md` à jour est donc fonctionnel, pas décoratif** : une ligne périmée
    (issue mergée encore marquée en cours, ou worktree actif absent du tableau) fait mal classer
    une issue — et une issue en vol traitée comme dormante se fait réécrire sa spec sous les pieds.
  - Un signalement **bloquant** sur une issue du lot : le lead **interrompt la session** par
    `SendMessage` (« arrête-toi après l'outil en cours, signalement bloquant : … ») — une session
    occupée lit ses messages entre deux appels d'outils, pas seulement en fin de tâche. Le temps
    d'arbitrer, elle ne produit pas de travail à jeter.
- **Après chaque merge du lot, avant toute consigne aux sessions encore en vol** : croiser les
  fichiers **réellement mergés** (`gh pr diff <PR> --name-only`) avec ceux de chaque branche en vol
  (`git diff --name-only origin/main...<branche>`). La consigne se fonde sur ce croisement, jamais
  sur la carte de recouvrement de l'étape 2 : elle décrit des issues entières, un merge livre un
  lot. Une branche qui recouvre **fusionne `origin/main` dans sa branche** — pas de rebase d'une
  branche poussée sans demande explicite, `contraintes.md` — et relance ses gates sur l'état
  combiné.

### 8. Nettoyer après merge

Une fois une PR mergée et sa branche supprimée côté distant, **d'abord détacher ce qui n'appartient
pas au worktree** : énumérer les liens et jonctions qu'il contient avec un détecteur qui **prouve
d'abord qu'il voit** — le filtre `Where-Object LinkType` de PowerShell a rendu une liste vide sur
une jonction connue du système, et une liste vide autorise une suppression :

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
traverser une jonction et vider la ressource partagée qu'elle vise — c'est arrivé au SDK Flutter
global, sans aucun avertissement. Puis seulement :

```
git worktree remove ../<repo>--<numéro-issue>
git branch -d <type>/<slug>
```

Tout contrôle qui autorise une suppression (« cette branche est bien dans `main` ») se valide
d'abord sur un **témoin positif**, un cas dont la réponse « oui » est connue : `cmd && ok || ko`
confond condition fausse et commande en erreur, et c'est l'outil qu'on suspecte en premier.

Vérifier ensuite que les ressources partagées répondent encore : le dépôt principal passe sa
commande de fumée, et le hook partagé pointe toujours sur lui — le chemin d'interpréteur figé
dans `.git/hooks/pre-commit` (`grep INSTALL_PYTHON .git/hooks/pre-commit` pour pre-commit) est
sous le clone principal, sinon relancer la commande `hooks` de la config **depuis sa racine**.
Un worktree supprimé qui avait installé les hooks laisse ce chemin mort, et la vague sabote le
dépôt qu'elle servait.

Marquer la ligne `⚪ worktree nettoyé` dans le tableau. Quand tout le lot est nettoyé, supprimer
`PR-PARALLELES.md` (ou archiver le tableau dans les notes du projet).

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
