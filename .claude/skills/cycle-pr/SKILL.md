---
name: cycle-pr
description: Exécute le cycle complet de développement d'une PR — briefing pré-PR, ouverture de la PR en draft avant tout code, implémentation en TDD red-green-refactor, cycle de commit modif→test→cleanup→test→commit, auto-review, passage en ready for review, boucle de review et merge. Utiliser pour implémenter une issue ready-for-agent, développer une fonctionnalité ou corriger un bug en suivant la pipeline.
argument-hint: "[#issue ready-for-agent | description du travail]"
---

# Cycle PR

Le cycle de réalisation d'une Pull Request, de bout en bout. Pièce centrale de la pipeline :
prend une issue `ready-for-agent` (ou une demande directe) et la mène jusqu'au merge — puis
répercute la clôture sur les autres issues — sans jamais laisser entrer un commit cassé dans
l'historique.

Les **règles permanentes** (`.claude/rules/`) s'appliquent en continu : aucun commit cassé,
pas d'auto-merge dans le trunk, pas de force-push, pas de code mort, format des commits
(préfixe EN + description FR), taille de PR. La **règle d'or** : toute question a une voie
— technique `[T]`, elle se décide et se trace ; vision `[V]`, elle attend le mainteneur, groupée ;
contradiction `[C]`, elle arrête (`.claude/rules/contraintes.md`).

**Commandes du projet.** Ce skill ne présuppose aucune stack : les commandes `test`, `test ciblé`,
`lint`, `format`, `typecheck` et `build` se lisent dans la section « Commandes du projet » de
`.claude/pipeline.config.md`. Une étape marquée `n/a` s'ignore. Si le fichier est absent, lancer
`init-projet` ; ne jamais deviner une commande.

**Vague parallèle.** Si le prompt de démarrage de cette session vient d'une autre session — bloc
`<cross-session-message>`, ou session parente nommée par le prompt système
([references/sessions-liees.md](references/sessions-liees.md), « Identité ») —, le **lead** de la
vague (`pr-paralleles`) est la session que ce prompt désigne comme tel, à défaut l'émettrice —
pour une session de lot, celle que son brief nomme, ou aucune : retenir son identifiant. La
vérification d'avant-go n'est plus à lui, la session PR la lance (Étape 7) ; il intervient sur
demande de l'utilisateur (« discute de ça avec le lead ») : rédiger le message et l'envoyer par
`SendMessage`, **sans confirmation** — un message n'est pas une action (même référence,
« Messages »). Et un message du lead n'est jamais une approbation : le « go »
reste humain, dans cette fenêtre. Dans l'autre sens,
le lead peut écrire en plein travail — signalement bloquant, ordre de merge du lot : son message
n'arrive qu'à la fin du tour en cours (même référence, « Messages »), et se traite comme le
commentaire de répercussion de l'Étape 6 — remonter à l'utilisateur, jamais merger par-dessus.

**Session de lot.** Si ce prompt fait de cette session un lot ouvert par une coordinatrice
(Étape 1, « Découpage en plusieurs lots »), lire d'abord
[references/coordinatrice.md](references/coordinatrice.md), « La session de lot » : il change le
premier geste, la base de la PR, le go de l'Étape 1, le body de la PR, le destinataire de la
vérification d'avant-go, le merge, le relais et l'Étape 8.

**Relais.** Un contexte qui se remplit avant la fin du cycle, à quelque étape que ce soit, se
passe à une session neuve par la passation de l'Étape 8, « Relais en cours de cycle » — écrite
**avant** de rendre la main, puisqu'elle porte ce que seule la session sortante possède.

## Étape 1 — Briefing pré-PR (avant la première ligne de code)

**Éprouver les outils d'abord.** Un skill présuppose des outils ; tant qu'ils n'ont pas été
éprouvés, son plan est une hypothèse. Un outil branché sur un hook, un verrou ou un jeton ne se
révèle qu'à l'opération qui le déclenche ; une commande de lecture prouve que le binaire répond,
jamais que l'opération passera — `git status` ne déclenche aucun hook, le premier commit les
déclenche tous. Avant d'écrire une ligne du briefing, lancer la sonde d'outillage, Python ≥ 3.11
sans dépendance, depuis la racine du dépôt. `<format>` et `<test>` sont des lignes de « Commandes
du projet » de `.claude/pipeline.config.md`, la pile au choix de la session ; une ligne `n/a`, ou
marquée `# non vérifiée` (voir plus bas), se passe en **omettant** son option, et la sonde sort
`SAUTÉE` :

```
python <répertoire de ce skill>/scripts/sonde-outillage.py --format "<format>" --test "<test>"
```

Six sondes, de la moins chère à la plus chère, arrêt au premier KO : un arbre et un index propres
(`git status` vide, fichiers non suivis compris) — la sonde de commit emporte ce qui est stagé, et
la commande de format réécrit ce qui ne l'est pas ; `gh auth status --active` en 0 ;
`gh api repos/{owner}/{repo} --jq .permissions.push` à `true` ; **une écriture**,
`git commit --allow-empty -m "chore: sonde outillage"` puis `git reset --soft HEAD~1`, la tête
revenue au SHA d'avant ; la commande de format, qui écrit, sans qu'elle réécrive l'arbre ; la
commande de test. Sortie 0 : tout OK ou sauté ; 1 : premier KO, avec la fin de la sortie
fautive ; 2 : appel mal formé. **Ce qu'elle ne couvre pas** : un dépôt sans commit, où elle rend
KO avant d'écrire ; le premier push et la CI ; la ligne « validation » ; les hooks côté serveur ;
le choix des commandes, qui reste à la session.

Un échec ici se remonte à l'utilisateur **avant** le briefing, avec les cibles de correction
possibles et leur portée (session, projet, machine) : c'est un arbitrage de configuration, jamais
une décision du skill — **un skill ne modifie pas la configuration de l'utilisateur pour se
débloquer lui-même**. Un même message de refus quelle que soit la commande se lit comme un
problème de permissions alors que c'est l'outillage ; éprouver coûte quelques commandes avant le
briefing, et une demi-session après le « go ».

**Une commande marquée `# non vérifiée`** dans `.claude/pipeline.config.md` signale un projet
initialisé sans code. Si cette PR pose du code, elle porte aussi ce que `init-projet` a reporté —
la génération CI et Dependabot de son étape 7, paragraphe « Runtime épinglé » compris, la
vérification des commandes de son étape 11, puis le retrait des marqueurs. L'inscrire au
briefing ; sans elle, le projet resterait sans CI.

Produire un briefing écrit AVANT de créer la branche :

- **Liste précise des fichiers** à créer/modifier — le chemin exact de chacun.
- **Estimation** — comptée **par critère**, en artefacts que le critère doit laisser, jamais en
  prose qui le décrit : une porte ou un invariant → un test paramétré à témoins des deux côtés
  (~100-150 lignes) ; un script → le script et son fichier de test (~400) ; une règle de skill → sa
  ligne, plus la docstring de dénombrement si elle ferme une classe. Calibration mesurée : les
  lots 1, 2 et 3 de #77 ont dépassé la leur de 2 à 5×, tous du même côté — une estimation en
  prose est un plancher. C'est elle que consomme le seuil relatif de `taille-pr.md` (obs 78).
- **Décisions verrouillées** — choix d'architecture / scope / format actés.
- **Questions résiduelles** — découpage, format des données, transitions d'état, comportements,
  edge cases — **chacune avec sa voie** (`contraintes.md`, règle d'or) : une `[T]` se tranche
  ici même, avec sa source, et rejoint les décisions verrouillées ; les `[V]` se posent toutes
  ensemble, au go du briefing — l'accord pour démarrer sa session de relecture et l'archiver à
  l'Étape 8 en fait partie, puisque `start_session` ne part que dans ce tour
  ([references/session-relecture.md](references/session-relecture.md)), et hors vague
  l'accord pour lancer soi-même le `verificateur` d'avant-go (Étape 7) ; une `[C]` arrête.

Lever les incertitudes **maintenant** : une `[V]` découverte après cinq commits coûte une
demi-journée d'attente ; une `[T]` ne se pose jamais, elle se décide — la plupart appellent la
réponse que le mainteneur donne toujours.

### Porte d'entrée obligatoire — l'interrogatoire

**Aucune PR ne démarre sans que le travail soit passé par `interroge-moi`.** Vérifier l'état de
l'issue dès les outils éprouvés :

- **Issue interrogée** (passée par `needs-interrogation`, décisions consignées dans le brief
  d'agent) → relire ces décisions, et vérifier qu'elles tiennent encore (auto-challenge ci-dessous).
- **Brief portant `⚠️ Non interrogée au triage`**, ou aucune trace d'interrogatoire → **s'arrêter
  et proposer une session d'interrogatoire** (`interroge-moi`, numéro de l'issue en argument), avant
  la première ligne de code, puis reporter ses décisions, écrites dans l'issue, dans les
  « Décisions verrouillées » du briefing.
- **Demande directe sans issue** → l'interrogatoire s'applique aussi ; il n'y a pas de raccourci
  parce que le travail n'a pas de ticket.

Le point n'est pas de cocher une case : c'est que **les décisions tranchées soient écrites**, dans
l'issue — brief amendé s'il est contredit — et dans le briefing. Elles seront relues par une
autre session que celle-ci.

### Auto-challenge du plan — le plan est-il encore exact ?

Avant de présenter le briefing comme acté, **se challenger explicitement** : le plan a pu être
écrit (issue, agent brief, conversation) *avant* que d'autres PR ne soient mergées. Le terrain a
peut-être bougé. Confronter le plan à la réalité **actuelle** du code — les relevés (`git log`,
`grep` des ancres, dénombrements) à un `releveur`, la cartographie de la zone touchée (fichiers,
interfaces, appelants) à l'`executant`, le jugement à la session PR :

- **Relire l'état réel** de la zone touchée (`git log` récent sur `main`, fichiers concernés) — pas
  l'état supposé au moment où l'issue a été écrite.
- **Pour chaque décision verrouillée et chaque fichier listé**, vérifier qu'elle tient toujours :
  l'interface existe-t-elle encore sous cette forme ? une PR récente a-t-elle déjà fait une partie
  du travail, déplacé un module, changé un contrat, rendu une hypothèse caduque ?
- **Confronter le brief au « Journal de spec » du corps de l'issue** : toute entrée du journal
  postérieure à la **dernière édition** du brief (date de modification du commentaire, pas sa date
  de création) se lit comme un erratum potentiel — une réconciliation a pu ne pas atteindre le
  brief. En cas d'écart entre les deux, le journal (adossé aux sources de vérité) l'emporte, et
  l'écart se signale dans le briefing.
- **Reproduire chaque chiffre de référence qu'un critère demande de retrouver**, par la commande
  qui recense sa population (`triage/brief-agent.md`, « Critères d'acceptation complets »), avant
  la première ligne de code. Un chiffre qui ne se reproduit pas fait amender le critère, avec sa
  ligne au « Journal de spec » — **partout** où la phrase se répète, sinon chaque lot suivant hérite
  d'une base fausse. Un critère muet sur sa population : prendre celle que son intention désigne et
  l'écrire dans l'amendement, jamais chercher celle qui rend le chiffre annoncé (obs 68).
- **Vérifier que la suite du dev tient** : ce que cette PR prépare pour les issues suivantes est-il
  toujours cohérent, ou l'ordre / le découpage doit-il être revu ?
- **Vérifier la faisabilité de l'ordre des commits** : pour chaque commit prévu, ce dont ses tests
  ont besoin pour tourner en local (services, schéma, compose, fixtures) existe-t-il déjà, ou
  est-il introduit par un commit ultérieur ? Si « ultérieur » → remonter ce commit. L'ordre de
  livraison suit les **dépendances d'exécution**, pas la logique de présentation du plan — un
  découpage peut être juste sur le contenu et infaisable sur l'ordre.
- **Chercher le numéro de l'issue dans tout le dépôt** — `grep -rn "#<N>"` sur les sources, la
  doc et la config, hors `.git/` et dépendances. Chaque occurrence est une **dette adressée à ce
  lot par un lot précédent** (« le lot 3 de #N y branchera X », « viendra avec #N ») : à honorer
  ou à amender dans ce lot. Le corps et le brief ne les connaissent pas, elles vivent dans le code.
- **Les consignes reçues d'un lead de vague font partie de la population confrontée**, au même
  titre que les décisions verrouillées : une consigne présentée comme un invariant se vérifie
  contre l'artefact qui le garde — le test, sa docstring, le § de l'issue — jamais contre son
  énoncé, une reformulation dérivant toujours vers le plus strict. Divergence → arrêt
  `decisions-vs-doc` ordinaire, à remonter.
- **Un ordre de gestes chez un tiers** (console, registrar, fournisseur de paiement) est une
  hypothèse à re-vérifier en source officielle, comme une interface qui a pu bouger : aucune gate
  ne rougit quand il devient faux.
- **Énoncer à voix haute** sous un titre `## 🔍 Auto-challenge du plan` : ce qui reste valable, ce
  qui a changé, et les ajustements proposés (fichiers en plus/en moins, décision à rouvrir, scope à
  resserrer ou re-découper).

S'il y a un écart qui change le cours du dev, **s'arrêter et le remonter à l'utilisateur** avant le
« go » — ne pas dérouler un plan périmé en silence. Si tout tient, le dire explicitement (« plan
confirmé contre l'état actuel »).

**Une réponse `[V]` du go qui contredit le brief l'amende avant la première ligne de code** —
décision verrouillée, critère ou interface : décision réécrite avec son motif et sa date, critères
déplacés, une ligne datée au « Journal de spec » du corps (`decisions-vs-doc`, sortie 2), relue
après écriture. Le corps de la PR ne remplace pas le brief : les lots suivants et `repercussions`
ne lisent que l'issue (obs 44).

**Découpage en plusieurs lots.** Quand le briefing découpe l'issue en n > 1 lots (`taille-pr.md`),
la session devient la **coordinatrice** de ses lots : elle n'écrit pas de code, et son go — le go
du découpage — fait démarrer les sessions de lot
([references/coordinatrice.md](references/coordinatrice.md)). Une issue à un seul lot ne change
rien : la session porte le cycle elle-même et délègue le code (3.1). Une session de lot attend
le go ci-dessous dans sa fenêtre comme toute session PR : elle y démarre sa session de relecture
(même référence, « La session de lot »).

Attendre un **« go » explicite**, puis créer la branche — trunk-based depuis `main`, derrière une
**porte**, c'est-à-dire une commande dont le code de sortie porte la condition :

```
git fetch origin
git merge-base --is-ancestor main origin/<trunk> && git merge-base --is-ancestor origin/<trunk> main && git checkout -b <type>/<description>
```

Cette porte suppose d'être **sur `main`**, dans le clone principal. Une session placée dans le
worktree d'une issue en lots est sur la branche **mergée** du lot précédent : elle ne compare
rien, elle part d'`origin/<trunk>` explicitement — `git fetch origin`, puis
`git checkout -b <type>/<description> origin/<trunk>`. Sans point de départ, `checkout -b` part
de la branche morte et emporte ses commits réécrits (mesuré ; la voie complète est dans
[references/prompt-lot-suivant.md](references/prompt-lot-suivant.md)). Une session **démarrée
par une autre** dans un worktree de l'application ne compare rien non plus : son premier geste
est celui de [references/sessions-liees.md](references/sessions-liees.md), « Premier geste ».

**Deux prédicats, pas un.** `--is-ancestor` dit « ancêtre **ou égal** » : une seule direction ne
distingue donc pas l'égalité du retard, et la porte laisserait passer l'autre cas. Les deux
ensemble valent l'égalité — `main` ancêtre d'`origin/<trunk>` **et** l'inverse ⇔ même commit.
`git fetch` est **sa propre commande** et précède les deux : c'est lui qui rend `origin/<trunk>`
significatif. Et c'est `&&` qui rend la porte bloquante — une chaîne de trois commandes passe le
garde de permissions, **en worktree isolé compris** (mesuré le 2026-10-13 : ce que le garde refuse
est la **substitution de commande**, pas la longueur de la chaîne — obs 60). **Non vérifié** :
cette mesure a été prise avec une troisième commande **en lecture** ; la forme écrivante n'a pas
été provoquée, parce qu'elle n'est pas inoffensive. Un refus à cet endroit se reconnaîtrait tout
seul, et la sortie serait de jouer les deux prédicats en une commande chacun, puis l'action — en
acceptant que la porte redevienne alors une lecture, et en le disant.

Les deux directions, mesurées le 2026-10-13 sur un dépôt jetable avec un vrai distant : branche
**en retard**, `--is-ancestor main origin/<trunk>` rend 0 et `--is-ancestor origin/<trunk> main`
rend **1** ; branche **en avance**, c'est l'inverse. Chaque prédicat bloque donc exactement sa
direction, et aucun des deux ne suffit seul.

La forme précédente, `git rev-parse main origin/main`, voyait les deux directions mais
**imprimait** au lieu de garder — c'est l'incident d'obs 69, et la classe entière vit à l'Étape 7,
« Le go, puis le merge ». Une porte à **un** prédicat aurait fermé ce cas en rouvrant l'autre :
c'est tout l'intérêt d'en mettre deux.

**Au blocage**, laquelle des deux a mordu se lit par `git status -sb`, qui écrit `[ahead n]` /
`[behind n]`. Pas `git status` nu, qui le dit en prose, et **surtout pas**
`git status --porcelain`, **vide** sur une branche en avance (mesuré) — c'est pourquoi la sonde
d'outillage ci-dessus, qui exige un `git status` vide, ne voit pas ce cas et ne peut pas servir de
contrôle compensatoire. Rattrapages : `main` local en avance → demander à l'utilisateur de
pousser, ou l'autorisation de le faire ; `origin/<trunk>` en avance → sur `main`,
`git pull --ff-only`. Dans les deux cas, rejouer la porte.

## Étape 2 — Ouvrir la PR en draft (toujours avant la première ligne de code)

**La PR est le premier artefact produit, pas le dernier.** C'est elle qui rend le travail
*visible comme en cours* pour le reste de la pipeline : `repercussions` s'en sert pour savoir
qu'une issue est « en vol » et ne pas réécrire sa spec sous les pieds de cette session, et
`pr-paralleles` pour tenir son tableau de bord. **Une branche locale sans PR est invisible** — le
travail existe, mais rien ne le sait.

GitHub refuse une PR sans commit : amorcer avec un commit vide, pousser, ouvrir en draft. Le
message d'amorce suit `taille-pr.md` comme tout autre commit — **pas de numéro d'issue dans le
titre**, le lien vit dans le `Closes #N` de la PR.

```
git commit --allow-empty -m "chore: amorce <description courte>"
git push -u origin <type>/<description>
gh pr create --draft --assignee @me \
  --title "<type>(<scope>): <description FR>" \
  --body "$(cat <<'EOF'
Closes #<N>

## Briefing (provisoire — remplacé à l'Étape 5)
<le briefing validé à l'Étape 1>
EOF
)"
```

La PR draft porte **dès sa création** :

- **`Closes #<N>`** dans le body. C'est **la** ligne qui rend l'issue détectable comme en vol.
  Sans elle, `repercussions` la croira dormante et éditera sa spec en cours de développement.
  **Cas découpé** (taille-pr impose plusieurs PR pour la même issue) : seule la **dernière** PR du
  lot porte `Closes #<N>` — un `Closes` sur la première fermerait l'issue trop tôt. Chaque autre
  PR du lot ouvre son body par la ligne **`En vol pour #<N> (lot k/n)`**, que `repercussions` lit
  au même titre que `Closes` : sans elle, l'issue paraît dormante précisément pendant qu'on
  travaille dessus. GitHub, lui, ne lit que le mot-clé : le lien des lots précédents se repose à
  l'Étape 8, une fois l'issue close. Avec une coordinatrice, le `Closes` passe à la PR
  d'intégration et **toutes** les PR de lot portent la ligne « En vol »
  ([references/coordinatrice.md](references/coordinatrice.md)).
- Le **briefing de l'Étape 1** comme corps provisoire — le plan devient lisible par le mainteneur
  et par les autres sessions, avant que le code n'existe.
- **Assignee**, **labels** et **milestone** (mapping de `.claude/pipeline.config.md`).
- Le marqueur **draft**, qui dit « en cours, ne pas reviewer » et interdit le merge accidentel.

Pour une **demande directe sans issue**, ouvrir quand même la draft : sans `Closes`, mais le
travail reste visible du reste de la pipeline.

> **La CI tourne sur chaque push de la branche, draft comprise** — sauf à l'ouverture de la draft
> elle-même, dont l'amorce vide n'a rien à vérifier (garde `if:` du `ci.yml` du template). Le
> premier run arrive donc au premier push de code (3.5), et c'est là que se voit un rouge de la
> famille « sensible à la plateforme » (3.2) — au cycle courant, pas après le passage en ready, où
> chaque constat coûte un run complet et le rejeu des vérifications manuelles. **Une draft sans
> push de code n'a aucun run : ce n'est pas une CI cassée.**

En vague parallèle (`pr-paralleles`), le lead relève lui-même le numéro de PR (`gh pr list`) pour
son tableau de bord : rien à lui envoyer. Une session démarrée par une autre lit ensuite
`get_status` ; `bind_pr` n'y sert qu'en repli
([references/sessions-liees.md](references/sessions-liees.md), « Premier geste »).

## Étape 3 — Le cycle de commit

Chaque commit suit :

```
1. modif (TDD)  →  2. test (vert)  →  3. cleanup pass  →  4. test (vert)  →  5. commit
```

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

### 3.1 Modification — en TDD (tracer bullet vertical)

**La session PR écrit le bloc ; un `developpeur` neuf le code** (`.claude/agents/developpeur.md`).
Le brief d'un bloc porte ses fichiers, ses signatures, ses tests attendus et leur rouge, son
comportement, son estimation en épingles (Étape 1), la base et le seuil du gabarit (3.5) et le
niveau `ponytail` ; le `developpeur` part à `xhigh` quand le bloc écrit des tests. Il fait le TDD
de cette étape, le cycle 3.2 à 3.5, la doc descriptive et le commit — jamais le push, que la
session PR fait après chaque remise, derrière la ligne « validation » quand le delta la demande
(3.2). Arrêté sur une `[C]` ou sur une question dont dépend tout le bloc, il est **repris par
`SendMessage`** avec la réponse — `[T]` tranchée par la session PR, ou
question portée au mainteneur —, jamais remplacé (mesuré le 2026-10-20 sur une `[C]` fabriquée,
Notes de la PR #139) ; ses `[V]` rejoignent « Questions en attente ». Un `developpeur` neuf
seulement au bloc suivant, jamais pour une retouche du même bloc.

**Frontières tierces : on vérifie, on ne suppose pas.** Avant d'appuyer un comportement sur une
bibliothèque ou un framework tiers à une frontière (réseau, encodage, secrets, fusion avec un
thème ou une config par défaut, cycle de vie de ressources), lire ce que fait réellement l'API —
documentation via `context7` ou sources du paquet — et le noter dans les `Notes` de la PR avec sa
référence. Les défauts les plus coûteux d'une PR « verte » sont des suppositions sur un paquet :
un décodage par défaut, un retry silencieux, une fusion de valeurs, un `repr` qui affiche un secret.

Deux cas de cette frontière se paient plus cher que les autres. **Un comportement par défaut
invoqué pour écarter un risque de sécurité** — un protocole inactif, une option refusée — se
mesure sur le **binaire livré**, jamais sur sa documentation ou sa réputation : une exception de
scan adossée à « inactif par défaut » est tombée au premier test sur l'image (obs 57). **Une
limite du geste** se pose avant l'intégration : quand une bibliothèque est retenue pour un
comportement visible, dresser d'abord, depuis ses sources, la liste de ce qu'elle ne fait pas du
geste demandé — cas non couverts, états refusés ; chaque entrée est une question `[V]`, posée
avant la première ligne avec l'alternative chiffrée, jamais une note découverte après l'ADR
(obs 38).

**Un zéro rendu par un outil de contrôle se lit avec son inventaire** — types de cibles, nombre
de composants analysés : un composant que l'outil n'a pas ouvert n'est pas mesuré, et se
contre-éprouve sous une forme que l'outil lit (règle complète : `interroge-moi`, « Avant de
verrouiller », obs 61).

**Un avis de sécurité sans correctif n'est pas une impasse.** Une plage d'avis `*` — toutes les
versions publiées affectées, paquet abandonné — ne clôt pas l'analyse, elle la déplace d'un
étage : avant de conclure qu'un avis est irréductible, remonter la chaîne de dépendance et
vérifier, pour **chaque** parent, s'il a cessé de dépendre du paquet fautif dans une version
ultérieure — le correctif d'un paquet abandonné vient presque toujours de son consommateur. Puis
regarder comment d'autres projets ont traité le même avis : un mur atteint par tout le monde a
souvent une issue de sortie publiée. Et un `override` qui saute une majeure sous un consommateur
non prévu pour elle **s'éprouve en exécutant réellement l'outil**, pas en relançant l'audit.

Implémenter **un comportement à la fois** en red-green-refactor — pas tous les tests d'abord puis
toute l'implémentation, le découpage horizontal produit de mauvais tests :

```
ROUGE : écrire UN test du prochain comportement → il échoue
VERT  : écrire le minimum de code pour le faire passer → il passe
```

Règles : un test à la fois ; juste assez de code pour passer le test courant ; ne pas anticiper
les tests futurs ; tester le comportement observable via l'interface publique.

**Le rouge se constate, il ne se suppose pas — un test qui n'a pas été vu rouge n'est pas un
test.** Sept cas à traiter explicitement :

- **Le test passe du premier coup, avant tout changement de production** → il mesure autre chose ;
  ne jamais conclure « le défaut n'existe pas ». Cas fréquent : lire une configuration statique
  alors que le défaut naît d'une fusion ou d'une résolution à l'exécution. Instrumenter d'abord
  (sonde jetable qui imprime les valeurs au point où l'utilisateur les subit), corriger le point
  de mesure, obtenir le rouge, puis écrire le correctif. Supprimer la sonde avant le commit.
- **Le test dérive d'un critère d'acceptation ou d'un rapport de bug et passe avant le correctif**
  → la prémisse a pu vieillir sous les dépendances : la vérifier contre les versions **réellement
  épinglées** (changelog + exécution), re-spécifier le test sur le déclencheur qui échoue
  vraiment, et signaler l'écart dans l'auto-challenge de l'Étape 1 — le correctif reste souvent
  bon, c'est le critère qui est faux.
- **La garde protège une ligne existante** (délégation, `override`, clause de `catch`) → la faire
  rougir en **supprimant cette ligne**, pas en raisonnant. Si le test reste vert, son montage fait
  converger le chemin nominal et le chemin fautif vers la même observation : trouver un point où
  les deux divergent. Quand la ligne gardée est un **réglage de sécurité** — option d'un scanner,
  épingle, permission, porte de CI —, on ne mute pas le dépôt : on écrit la garde en fonction sur
  du texte, vue rouge sur un recueil de formes fautives construites en mémoire (modèle :
  `WORKFLOW_FORMS` de `apps/api/tests/test_supply_chain.py`). Le classifieur du mode auto refuse de
  lancer une suite sur une configuration de sécurité affaiblie, par quelque voie que ce soit
  (obs 53). `mutation.py` refuse ce que ses motifs de chemin et de contenu
  reconnaissent et renvoie à cette forme ; un réglage rangé ailleurs y ajoute son motif.
- **Le test est dicté par un tiers** (relecteur, lead de vague, issue) → même règle que pour un
  test écrit soi-même : mutation avant de le garder. L'autorité de la source ne remplace pas le
  rouge observé.
- **L'assertion est une absence** (`findsNothing`, `is None`, `not called`, « aucun X quel que
  soit l'état ») → le test doit être vu rouge sur un état où la chose **est présente** : le code
  inchangé, avant le correctif. Une recherche qui ne trouve rien et une recherche mal formée
  rendent le même résultat (un sélecteur sur la classe de base ne voit pas la sous-classe) ; s'il
  passe à ce moment-là, le défaut est dans le sélecteur, jamais dans le sujet. Un garde d'absence
  jamais vu rouge n'est pas un garde, c'est un commentaire exécutable.
- **L'assertion ne distingue pas quelle branche a mordu** — jointe par `or`, ou réduite à « ça
  lève » (`assertRaises` sans vérifier le type ni le message, `assert a or b`, une appartenance à
  un ensemble de valeurs acceptables) → elle reste verte quand la garde qu'elle croit éprouver
  disparaît, parce que l'autre branche la satisfait. Le rouge se constate en **retirant une
  branche à la fois** : si le test tient dans les deux cas, il n'éprouve aucune des deux. Trois
  occurrences au lot 1 de #77, trouvées chaque fois par le harnais de mutation (une mutation
  `VERT` sur une garde retirée), jamais par relecture — une assertion jointe se lit exactement
  comme une assertion forte.
- **La table de cas est dérivée de l'artefact sous test** (`for x in module.CONSTANTE`) → retirer
  un élément de l'artefact retire son cas au lieu de le faire rougir : le test et le code ont la
  même source, le test ne peut contredire le code sur rien. Les cas s'écrivent en **littéraux**,
  dans l'orthographe réelle ; l'égalité entre la table et la constante est un **second** test, qui
  garde l'autre sens. Mesuré au lot 3 de #77 : la mutation « préfixe retiré » est restée `VERT`
  après un correctif qui construisait ses cas depuis le tuple du script (obs 80).

- Bons vs mauvais tests : [references/tests.md](references/tests.md)
- Quand mocker (frontières du système uniquement) : [references/mocking.md](references/mocking.md)
- Concevoir des interfaces testables : [references/design-interface.md](references/design-interface.md)
- Viser des modules profonds : [references/modules-profonds.md](references/modules-profonds.md)

**Documentation maximale** : chaque fonction écrite est documentée à fond (intention, params,
valeur de retour, erreurs, effets de bord, pré/postconditions, exemples, edge cases) au format
idiomatique du langage. La doc explique le contrat, les tests prouvent le comportement.

**Doc projet en sync** : si le delta change un comportement, une commande, une interface ou
l'architecture, mettre à jour la doc concernée (`README`, `docs/`, `CLAUDE.md`, glossaire) **dans
le même commit** — voir `.claude/rules/contraintes.md`. La doc ne se met jamais à jour « plus tard ».

### 3.2 Premier passage de tests

Le `developpeur` lance la suite rapide. **Si rouge → pas de commit.** Il répare. Contrôles
complémentaires :

- **Échec d'outillage ≠ échec de code.** Un échec « exécutable introuvable », « fichier utilisé
  par un autre processus » ou un compilateur qui sort brutalement après une commande tuée n'est
  pas un test rouge : vérifier d'abord l'environnement — processus orphelins laissés par un run
  interrompu (les lister **filtrés sur le chemin du worktree** avant de les tuer), worktree non
  provisionné — et ne diagnostiquer le code que sur un environnement propre.
- **Un résumeur n'est pas un verdict.** Quand la commande de test passe par un filtre ou un
  résumeur — proxy de sortie, hook de réécriture —, tout bilan qui annonce **zéro test collecté**,
  ou tout état autre que le rouge nommé à l'avance, se relit sur la **sortie brute du lanceur**
  avant d'être interprété : la commande `test brut` de `.claude/pipeline.config.md`, ou à défaut
  le contournement que le résumeur documente. Un résumeur peut rendre « aucun test collecté »
  sur une suite qui a un rouge — un accent dans un message d'assertion suffit —, et ce rouge se
  conclut alors « environnement cassé ». Tant qu'il n'a pas montré qu'il
  distingue « zéro test » d'« un test rouge », son bilan n'est pas un verdict.
- **Une porte verte ne vaut que pour la plateforme qui l'a rendue.** Quand le poste et la CI n'ont
  pas le même OS, recenser une fois, au premier scaffold, les règles de qualité sensibles à la
  plateforme — bit exécutable, fins de ligne, sensibilité à la casse des chemins, séparateur de
  chemin, encodage par défaut — dans la section « Qualité » de `.claude/pipeline.config.md`, et
  dire dans les `Notes` de la PR lesquelles ne sont vérifiées qu'en CI. Une règle de lint que
  NTFS ne peut pas déclencher ne rougit qu'en CI ; l'inverse existe aussi, un fichier que
  `.gitattributes` pinne en LF et qu'une copie de travail CRLF fait rougir sur le seul poste.
- **Une commande du projet que la suite n'exécute pas est invisible à toutes les portes.** Si le
  delta touche le fichier de commandes du projet (`Makefile`, `justfile`, scripts du manifeste)
  ou la définition d'une commande listée dans `.claude/pipeline.config.md`, **exécuter cette
  commande** — pas seulement la suite de tests : une cible qu'aucune porte n'appelle n'est
  vérifiée par personne, et sa cohérence à la lecture est précisément ce qui rend le défaut
  invisible (un `export` posé avant un `?=` vide la variable, et le fichier reste lisible). Une
  cible qui ne peut pas tourner ici — Docker, jeton, réseau — se vérifie sur la commande **après
  expansion** (`make --dry-run <cible>`, ou l'équivalent du lanceur du projet), jamais sur le
  texte du fichier.
- **Un exécutable livré se lance sur une entrée réelle.** Si le delta livre un exécutable —
  script, commande, rapport —, le lancer au moins une fois sur une entrée **réelle**, pas
  seulement sur les fixtures de ses tests, et lire sa sortie ligne à ligne contre les critères qui
  la décrivent ; entrée et sortie vont au Test plan (Étape 5) avant `gh pr ready`. Un test écrit
  par l'auteur assère ce que le code calcule ; seule l'exécution le confronte à ce que le critère
  demandait. Mesuré : 38 tests verts autour d'un script dont la première sortie réelle divisait
  chaque pourcentage par la durée totale, absences comprises — 2 % affichés là où le critère
  demandait la part hors absences, 13 % (obs 72).
- **Un delta sur `.claude/` ou `CLAUDE.md` passe par le validateur du harnais avant tout push**
  — ligne « validation » de `.claude/pipeline.config.md`, que joue un `releveur` avant chaque push.
  C'est la porte la plus large de ce que Claude Code charge : un frontmatter de skill absent, une
  `description` non textuelle, un manifeste, une entrée MCP. **Avec `--strict`**, sans quoi un
  avertissement sort en 0. Elle ne dispense pas de la suite : mesuré le 2026-10-09 (v2.1.295),
  elle est **muette** sur un
  frontmatter de rôle absent ou illisible — un ` : ` non cité dans une `description` fait charger
  le rôle sans aucun champ, en silence —, et ce sont les tests de frontmatter du projet qui
  gardent cette classe. Deux portes, deux populations : ni l'une ni l'autre ne couvre tout.
- **Couverture par commit.** Lire le rapport de couverture du delta : une ligne non couverte est
  d'abord une hypothèse de **code écrit trop tôt**, à déplacer vers le commit de son premier
  appelant — avant d'être un test manquant. C'est le seul instrument qui rende opposable
  l'interdiction du scaffold inutilisé.
- **Atteignabilité.** Une suite verte ne prouve que ce qu'elle compile : un fichier ajouté que ni
  la production ni les tests n'importent est invisible à toutes les gates à la fois (profil
  typique d'une PR foundation qui pose jetons ou constantes). Exiger au moins un point d'appel
  depuis les tests, et l'avoir vu rougir en cassant ce qu'il référence. Symétrique, côté porte :
  un fichier ajouté dans un dossier que la PR crée, ou qu'aucune porte ne couvrait encore, se
  prouve **lu** par chaque porte qui prétend le couvrir — lint, typecheck, format — en y injectant
  une faute délibérée, vue rouge, puis restaurée. Les exclusions par défaut des outils (dossiers
  cachés, `node_modules`, environnements virtuels) priment souvent sur l'`include` du projet :
  pyright a rendu « 0 errors » sur un script de `.github/scripts/` qu'il n'avait pas analysé, et
  y a trouvé 11 erreurs une fois le script déplacé (obs 27).

### 3.3 Le « cleanup pass » — relecture distincte du delta

Une fois le delta fonctionnel et vert, le `developpeur` en fait une **relecture distincte** (pas
du nettoyage au fil de l'eau).

**Le prompt à exécuter et la façon de l'appliquer vivent dans `.claude/rules/cleanup-verbatim.md`**
— règle permanente, donc déjà chargée. Le prompt s'exécute **mot pour mot** depuis ce fichier ; ne
jamais le recopier ici, une copie finit toujours par diverger de l'original.

Spécifique à cette étape :

- Pistes de refactor : [references/refactoring.md](references/refactoring.md).
- Vérifier aussi les 3 axes de conception de `.claude/rules/contraintes.md` (modulaire /
  fractionné / scalable), en plus de KISS, DRY et YAGNI.
- **PR « foundation »** : YAGNI peut être suspendu ponctuellement (scaffold pour la suite), mais
  le **noter explicitement**. KISS, DRY et la structure restent actifs.
- **La doc voyage avec le delta — question instrumentée, pas rappel** : « ce delta change-t-il un
  comportement, une commande, une interface ou l'architecture ? si oui, quel fichier de doc est
  dans le même `git add` ? ». Répondre en listant l'index (`git diff --cached --name-only`) —
  une doc rattrapée « en fin de PR » est la violation la plus répétée du cycle.

### 3.4 Second passage de tests

Le cleanup a pu casser quelque chose. Le `developpeur` relance les tests, et la commande du projet
que 3.2 a fait exécuter si le delta la touche ; rouge → pas de commit.

### 3.5 Commit

Uniquement si tout passe. Message = **titre conventional commit seul** (préfixe EN, description FR) :

```
git commit -m "type(scope): description"
```

Pas de corps, pas de footer, pas de `Co-Authored-By`, pas de numéro de PR. Breaking change : `!`
dans le titre.

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

Puis la session PR pousse et enchaîne sur le bloc suivant (retour 3.1) — ou, si ce commit vient de
poser le socle, lance d'abord la première passe de relecture (4.2). Si ce commit assemble un écran
d'une zone sensible, c'est maintenant qu'elle prend le point d'arrêt humain — cadence et forme
dans `.claude/rules/contraintes.md`, « Points d'arrêt humains », source unique.

## Étape 4 — Relecture indépendante

Deux relectures. Le cleanup pass holistique (4.1) quand tous les commits sont faits. La relecture
à contexte vierge (4.2) **en deux temps** : une première fois dès que le socle est posé, en plein
cycle de commit ; une seconde après 4.1, sur ce qui a été écrit depuis la première — ou sur toute
la branche, `<base>..HEAD`, si aucun commit n'a posé de socle. `<base>` est le point de fork,
`git merge-base origin/main HEAD`, jamais le nom du trunk : une plage adossée à un trunk qui
avance se diffe à l'envers.

**4.1 Cleanup pass holistique** — le prompt de `.claude/rules/cleanup-verbatim.md` sur le **diff
complet de la branche** (`git diff main...HEAD`), à l'échelle de la PR : architecture (couplage,
frontières), naming entre commits, edge cases / erreurs / race conditions, **duplication
inter-commits**. C'est le seul regard global sur le code avant la relecture à contexte vierge — le
regard local, c'est 3.3, à chaque commit ; il n'y en a pas de troisième avant le merge. La session
PR le confie à un `developpeur` neuf, qui ne rend que des commits ; son brief exige aussi la passe
« affirmations » de `cleanup-verbatim.md` sur tout le delta, dont il rend le dénombrement
(N affirmations, k établies, N−k non vérifiées), que la session PR inscrit dans les Notes avant la
première vérification d'avant-go (obs 113). Puis la seconde passe 4.2.

**4.2 Relecture par un contexte vierge.** Le cleanup holistique est fait sous le brief de la
session PR, avec les hypothèses qui ont produit le code ; il ne les met pas à l'épreuve. Le diff est donc
relu par un lecteur qui ne les a pas : la **session de relecture** de la PR, que la session PR
démarre au go du briefing, réveille par message et nettoie — protocole dans
[references/session-relecture.md](references/session-relecture.md) —, et qui suit
`.claude/agents/relecteur.md` : ce qu'elle reçoit, ce qu'elle vérifie, ce qu'elle rend. Le
sous-agent `relecteur` en est le repli écrit (même référence, « Repli »). Un rôle ajouté
dans `.claude/agents/` pendant cette session n'existe pas encore pour l'outil Agent : le repli
`general-purpose` ne vaut que pour un rôle sans liste `tools:`, et `relecteur` en a une — un rôle à
outils réduits se lance depuis une session neuve (`CLAUDE.md`, « Orchestration »), que la session PR
ne démarre pas hors d'un tour humain : d'ici là, la relecture passe au relecteur humain,
ci-dessous.
L'invocation de `cycle-pr` — `/cycle-pr` tapé par l'utilisateur, ou prompt de démarrage d'une vague
`pr-paralleles` — **vaut demande** pour ce sous-agent : une consigne de session « pas de
sous-agent sans demande de l'utilisateur » est déjà satisfaite. S'il ne peut pas même être lancé,
la relecture passe au relecteur humain (même référence, « Repli »).

**Les portes bon marché d'abord.** Un relecteur coûte un contexte entier ; ce qu'une commande
trouve en dix secondes ne se paie pas en jetons. Avant chaque appel, dans cet ordre :

Chaque commande se lit dans « Commandes du projet » de `.claude/pipeline.config.md`, avec ce
qu'elle couvre et ce qu'elle ne voit pas — jamais de mémoire :

1. **`lint`, `typecheck` et la suite** verts, et la ligne **validation** si le delta touche
   `.claude/` ou `CLAUDE.md` — un `releveur` lancé par la session PR, qui rend le verdict et les
   lignes en échec ; sur zéro test collecté, la sortie brute du lanceur (3.2).
2. La ligne **relecture**, en balayage mécanique du diff. C'est la session de relecture qui
   l'invoque, à chaque réveil — à la différence de `/code-review ultra`, qui demande un geste du
   mainteneur et reste hors pipeline.
3. La ligne **sécurité**, quand le diff touche une zone sensible ou une surface exposée
   (section « Périmètre » de la config), jouée par la session de relecture. Sinon, le dire en une
   ligne et passer. Un échec d'outillage de la porte — précondition absente, commande qui échoue
   avant toute analyse — se dit dans « Relecture indépendante » du body, jamais en saut
   silencieux (obs 84).

**Ces deux commandes closent un tour — celui de la session de relecture.** Leur prompt exige
une réponse finale faite de leur seul rapport — `/security-review` : « Your final reply must
contain the markdown report and nothing else » ; `/code-review` : son outil de rapport, seule
sortie. Jouées par la session PR, elles ont arrêté son cycle trois fois, la dernière après qu'une
phrase les avait bornées (obs 94, 98, 115) ; dans la session de relecture, l'arrêt ne coûte rien
(`session-relecture.md`, « Réveil »). En repli seulement, la session PR les joue : la consigne vaut
alors pour la forme du rapport, pas pour l'arrêt du cycle, et elle enchaîne dans le même tour.

Ces portes sont **additives**. Aucune ne remplace le prompt de
`.claude/rules/cleanup-verbatim.md`, que la règle exige mot pour mot, ni la relecture à contexte
vierge : elles retirent du plateau du relecteur ce qu'un outil sait trouver, pour qu'il dépense
son contexte sur ce qu'aucun outil ne voit — les hypothèses qui ont produit le code et les
affirmations attachées au code. Mesuré sur le delta de cette PR : la relecture mécanique a rendu
**un** défaut de correction que les deux passes à contexte vierge n'avaient pas vu, et **zéro**
constat sur la prose de protocole, où vivaient leurs neuf constats. Une porte neuve s'inscrit dans
la config avec ses deux populations — ce qu'elle couvre, ce qu'elle rate — avant d'être rendue
obligatoire.

La session PR **pousse**, puis réveille la session de relecture par le message de
`session-relecture.md` (« Réveil »), qui porte la plage et le SHA. À la première passe, celle-ci
ne lit **que** le corps de l'issue et son brief d'agent (ou le briefing de l'Étape 1), la plage
`<base>..HEAD` et le SHA complet de tête. À la seconde, elle a déjà tout cela : elle ne reçoit que
la plage `<sha de fin de la première passe>..HEAD` et les constats de la première, corrigés ou
écartés. Elle rend chaque critère d'acceptation ✅ / ❌ / ⚠️ avec preuve, puis ses constats
classés bloquant / important / mineur, chacun avec fichier, raison et marqueur de provenance.

**Une seule session de relecture pour la PR — les deux passes et la relance.** Pas de relecteur
par préoccupation, pas de contre-vérificateur par constat, pas de workflow : chaque agent de plus
repaye le contexte entier et rend ses constats à la même distance du code. Un constat bloquant se
re-mesure par la session PR, dans son arbre, en une commande, avant d'en écrire le brief — jamais par
un agent de plus.

**La seconde passe revient à la session de la première, réveillée par message** — jamais à une
session ni à un agent neufs. Son contexte est intact : elle a déjà lu le brief, les critères et le
socle, et son worktree est en place. Au lot 1b de #77, la passe 2 confiée à un agent neuf a
repayé **un contexte entier** pour un diff que le relecteur de la passe 1 connaissait déjà. Le
coût se compare **par contact** — passe, reprise, relance —, tel que `bilan-session.py` le lit
dans son transcript.

**En deux temps, jamais par commit.** Une première passe dès qu'un commit pose un **invariant que
les commits suivants supposeront vrai** — par exemple le contrat d'infrastructure : image, point
d'entrée, fichier de composition, contrat de configuration ; pour une PR de règles, les règles —
et une seconde, plus courte, à la fin, sur ce qui a été écrit après la première. Le déclencheur
est le **contenu** du commit, jamais son rang : les premiers commits d'une PR portent souvent une
constante et deux dépendances, et les invariants non gardés arrivent plus tard. Placée seulement
à la fin, la relecture rend ses constats à la distance maximale du moment où ils auraient pu
être absorbés. Un constat de la première
passe se fond dans un commit qui restait à écrire ; un constat qui arrive après le passage en
ready coûte un run de CI complet et le rejeu des vérifications manuelles (Étape 7).

**Un worktree de relecture par PR, jamais l'arbre de la session PR.** Éprouver un test
sérieusement, c'est casser la garde qu'il protège et la voir rougir — donc **modifier le code de
production**, puis le restaurer ; dans l'arbre partagé, cela gèlerait la session PR et ses
équipiers pendant toute la passe, sur un arbre qui bouge. Ils continuent ici pendant ce temps,
sans rien attendre. Une session de relecture qui commit ou pousse depuis ce worktree a dépassé
son rôle. Son worktree est celui de l'application, né à son démarrage et nettoyé par la session
PR à son Étape 8 ; celui du sous-agent de repli a ses trois gestes — naissance, réutilisation,
retrait — au même fichier, « Repli ».

**La mutation s'appelle, elle ne se décrit pas.** Le harnais existe et il est versionné :

```
python <répertoire de ce skill>/scripts/mutation.py <racine du dépôt> <mutations.json>
```

Son `--help` porte le contrat complet — le JSON `{targets, reporter, label, stack, mutations}`,
les trois verdicts `ROUGE` / `VERT` / `PANNE`, le témoin joué **une seule fois** sur l'arbre
propre avant toute mutation, les fins de ligne du fichier muté appliquées à `old`, la
restauration octet pour octet. Il l'imprime en **sortant en 2** : le lire seul, jamais enchaîné
derrière un `&&`. Ni 4.2 ni `relecteur.md` ne le redécrivent : un harnais décrit est un harnais
réécrit, et celui-ci l'a été **sept fois**, deux fois faux dans le sens qui mente.

Deux réglages tiennent tout l'écart de coût : `targets` reçoit le **fichier de test visé**, pas
la suite entière, et `file` est indépendant de `targets` — muter un fichier en lançant le test
d'un autre ne demande donc aucune cérémonie, ce qui rend bon marché la preuve d'un épinglage
inter-fichiers. Trois pièges d'usage, payés : une ancre `old` se relit dans le fichier
**formaté** (une ancre tapée avant la commande de format rend `PANNE`) ; un `expect` qui nomme
un test absent des `targets` rend « apparie 0 tests de la suite témoin » — ce n'est pas une faute
de frappe, c'est une mauvaise cible ; et une ancre se choisit **dans le code**, jamais dans la
prose qui le cite — le harnais vérifie qu'elle est unique, pas qu'elle est du code. Prise dans un
commentaire, l'ancre mute le commentaire et rend `VERT` sans rien prouver — seul le cas où elle
ne mute rien du tout est refusé en `PANNE` par le harnais (obs 77).

Un couple **VERT sur arbre propre, ROUGE avec une sonde plantée** n'est pas un échec du harnais :
c'est la mesure qu'un invariant *non gardé* est *gardable*, donc le signal qu'il faut écrire le
test.

**Sévérité — trois définitions, pas trois nuances.** *Bloquant* : un défaut de comportement en
production, une faille, une perte de données possible. *Important* : une régression que la CI ne
verrait pas et qu'un changement plausible du code déclencherait. *Mineur* : tout le reste —
lisibilité, nommage, doc, et « ce test pourrait tenir davantage ». Un constat qui n'entre dans
aucune des deux premières est mineur, quelle que soit sa longueur — « ce test pourrait tenir
davantage » en est le cas le plus fréquent. La session de relecture rend chaque mineur sous
forme d'**édit précis** — fichier, ligne, remplacement — ou l'écarte elle-même avec sa raison.

**Traitement — par passe, jamais par constat.** La session PR trie et vérifie le diff rendu ; elle
ne corrige pas. Les bloquants et importants d'une passe partent **ensemble** à un `developpeur`
neuf — jamais un par constat —, avec leur classe, le dénombrement déjà écrit (le cliquet,
ci-dessous) et le test qui doit tenir chaque fermeture : **un commit par passe** (ou par zone, si
deux correctifs n'ont rien en commun), un cycle complet 3.1→3.5 pour le groupe. Les mineurs d'une
passe s'appliquent en **un commit groupé** — un remplacement verbatim au `releveur`, une
reformulation à l'`executant`, en fond pendant que la session PR lit les importants et écrit leur
brief, sans éditer avant leur retour puisque l'arbre est partagé —, ou s'écartent avec leur
raison dans le body (Étape 5). Aucun registre ailleurs : un mineur écarté qui compte
encore reviendra à la prochaine relecture de la zone ; s'il ne revient pas, il ne comptait pas. Un
constat de la **première** passe s'absorbe de préférence dans le commit à venir qui touche sa
zone.

**Un bloquant ou un important se ferme par un test, jamais par une édition de prose seule.**
Avant la passe suivante ou la relance, chaque constat corrigé nomme le test qui tient sa
fermeture — identifiant de cas — et joue la **mutation inverse du correctif**, la forme fautive
remise, qui doit rendre `ROUGE`. Une fermeture que la mutation inverse laisse `VERT` est une
lecture, et c'est le relecteur qui la paie à la passe suivante — deux fois au lot 3 de #77, un
contact de relecture chacune (obs 79).

**Le cliquet — dénombrer avant de corriger, pas après.** Un constat de relecture est un
échantillon, jamais un inventaire : dès qu'un correctif ferme **un chemin** d'une classe (voir le
déclencheur de `cleanup-verbatim.md`), le dénombrement des chemins de cette classe s'écrit
**avant** le premier correctif, dans la **docstring du test paramétré** qui les éprouve — N
recensés, k fuyaient —, et la relance reçoit ce dénombrement avec la consigne de chercher celui
qui manque. Écrit après, il se fait par morceaux : trois correctifs de suite sur une même classe,
chacun rouvert par la relecture suivante, et le dénombrement rendu à la quatrième — par le
relecteur. Le cliquet est ce qui empêche la classe de se re-payer.

**Quand une garde imite un analyseur, c'est l'analyseur qui la corrige.** Si une passe renvoie
**plusieurs** formes qui échappent à une garde lisant un format structuré par motif — YAML, TOML,
Dockerfile, HTML, prose —, ne pas élargir le motif : lire le fichier avec l'analyseur du format,
ou avec la règle exacte de l'outil que la garde protège, et comparer les décomptes des deux
lectures. Un élargissement par constat est un correctif de symptôme, et chacun introduit sa
régression — mesuré : trois tours, une vingtaine de formes, des décomptes cassés par
l'élargissement précédent. La classe n'est pas « le motif est trop étroit », c'est « le motif
n'est pas l'analyseur ». Quand aucun analyseur ne s'applique, la sortie est le **retrait** de la
garde, sa population explicitement bornée dans sa docstring, jamais un motif de plus.
Le déclencheur est la **structure** du correctif, jamais sa direction : tout correctif qui
**change la population appariée** par un motif — l'élargir comme la rétrécir — relève de ce
paragraphe, et une mutation de **chaque** occurrence réelle de la classe doit rester `ROUGE`
après lui. Le **rejeu des mutations déjà jouées** est la seule mesure qui distingue un correctif
d'un défaut déplacé : au lot 2 de #77, un ancrage ajouté pour fermer un faux positif tuait la
détection de la seule occurrence réelle, et seul ce rejeu l'a vu (obs 76).

**Une lentille navigateur, dès qu'un script client entre dans le delta.** Un comportement vérifié
« à l'écran » l'est sur le parcours où il a été conçu ; ses défauts vivent sur les autres. La
lentille est un **script de navigateur rejouable** — la commande `e2e ciblé` de
`.claude/pipeline.config.md`, cache HTTP désactivé, données jetables —, jamais une démonstration
regardée : un parcours joué à la main ne se rejoue pas au commit suivant, et c'est la session de
relecture qui le lance, dans son worktree, parce que la session PR l'a déjà fait vérifier sur le
chemin qu'elle a choisi. Matrice minimale, quatre points :

1. chaque geste sur l'écran **renvoyé en erreur par le serveur** ;
2. chaque geste **combiné aux gestionnaires que le framework pose sur les mêmes éléments** ;
3. les combinaisons de gestes qui atteignent le même état final **par des chemins différents** ;
4. la **console**.

Mesuré : quatre bloquants sortis de cette seule matrice, tous hors du parcours nominal, sur un
script que l'auteur avait vérifié à l'écran et le mainteneur validé à l'arrêt visuel — et dont un
correctif de lot précédent s'était déclaré clos sur le geste nominal.

**Plafond — deux passes et une relance.** La relance n'est pas une passe : c'est une **revue des
commits de correction**, ciblée par un diff explicite (`<sha avant>..<sha après>`) et par la liste
de ce que chaque commit prétend régler et du test qui épingle chacun, avec la question
obligatoire : « qu'est-ce que ce correctif a cassé, ou fait rougir à tort, que la version
précédente voyait ? ». Elle revient à la **session de relecture de la PR**, réveillée par message
— son contexte est intact, elle n'a rien à relire —, jamais à un agent neuf. Un correctif est du
code neuf écrit sous pression de conclure — c'est la partie la moins éprouvée de la PR, pas la plus
sûre. Après la relance : un bloquant qu'elle trouve se corrige et rouvre une relance ; un important
se corrige, se prouve par un test vu rouge (3.1), et n'est pas relu par un tiers ; un mineur suit la
règle ci-dessus. La boucle s'arrête là, et le body le dit. Les constats écartés sont notés avec
leur raison dans le body (Étape 5).

C'est **cette fermeture** — et elle seule — qui autorise le nettoyage de la session de relecture
(Étape 8) ou le retrait du worktree du sous-agent de repli : tant que la boucle peut rouvrir une
relance, ils en sont le destinataire, et les retirer n'est pas un nettoyage, c'est une
terminaison.

**Pousser avant chaque réveil** — première passe, seconde passe, relance —, jamais en force :
`/code-review --comment` commente la tête poussée, et la CI éprouve la plateforme cible pendant
que la relecture tourne ; un rouge de plateforme (3.2) se corrige dans le commit groupé de la
passe en cours.

## Étape 5 — Finalisation de la PR (passage en ready for review)

La PR **existe déjà** depuis l'Étape 2. Il s'agit ici de remplacer le briefing provisoire par le
body définitif, puis de sortir du draft.

- **Titre** conventional commit (préfixe EN + description FR) — le réajuster si le scope a bougé
  en cours de route.
- **Assignee**, **labels**, **milestone** : vérifier qu'ils sont toujours justes.
- **Conserver la ligne `Closes #<N>`** — la perdre en réécrivant le body casserait à la fois la
  fermeture automatique de l'issue et la détection « en vol ».
- **Vider « Questions en attente »** : toute `[V]` encore ouverte se pose maintenant, groupée avec
  le point d'arrêt humain s'il reste à prendre ; sa réponse rejoint les Notes, et l'hypothèse
  retenue d'ici là se confirme ou se défait en un commit.
- Remplacer le corps par un **body structuré** :

```markdown
## Summary
<1-3 phrases : l'intention de la PR>

## Changes
<commits regroupés par thème : infra / feature / tests / docs>

## Test plan
- [x] CI locale verte
- [x] CI verte
- [x] <vérifs manuelles si pertinent — chacune porte les deux SHA sur lesquels elle a été prise,
      la tête et la base de branche `git merge-base origin/main HEAD`, et « observe : » les fichiers ou
      dossiers dont son résultat dépend (Étape 7)>
- [x] <exécutable livré : sa sortie réelle (entrée : <nommée>), chaque ligne confrontée au
      critère qui la décrit (3.2) — avec les deux SHA et « observe : », comme ci-dessus>
- [x] <étape non applicable — cochée avec sa raison (« sans objet »), jamais laissée décochée>

## Relecture indépendante
<verdicts des deux passes de l'Étape 4.2 : constats corrigés (commit) / écartés (raison)>

## Notes
<décisions, follow-ups différés, hors-scope, comportements tiers vérifiés (doc citée)>
```

Au-delà de **~10 fichiers** ou **~500 lignes** de diff, découper la PR.

**Preuves visuelles exigées par un HITL** : ni l'API GitHub ni `gh` ne savent joindre une image à
un body ou un commentaire. Le canal est une **branche orpheline `captures/pr-<n>`** poussée par
plomberie git (zéro fichier dans la PR), référencée par liens `?raw=true` dans le body, supprimée
à l'Étape 8.

**Un jeu de captures est jugé par comparaison, pas capture par capture.** Quand des captures
s'ajoutent à un jeu déjà partiellement validé (reprise, autre session), **ouvrir une capture
validée avant d'en produire une nouvelle** et aligner sur elle les paramètres de rendu : mode de
compilation (le bandeau DEBUG), appareil et densité, résolution, thème, barre d'état. La consigne
écrite n'énumère que ce que son auteur a pensé à fixer ; l'artefact validé est complet.

### Point d'arrêt humain

Sur une zone sensible, il a été pris au commit qui assemble l'écran (3.5). Si l'écran a bougé
depuis, rejouer la vérification sur ce qui a changé (Étape 7, « Rejouer les vérifications
périmées ») **avant `gh pr ready`**.

**Avant de sortir du draft, lire le run du SHA de tête.** `gh pr ready` ne déclenche aucun run
(ADR 0017) : la preuve d'une PR prête est le run de son dernier push (Étape 4). Le lire, verdict
compris, sur le SHA complet de tête — une ligne par run, la plus récente en premier (mesuré le
2026-10-20), son identifiant en dernier :

```
gh api "repos/<owner>/<repo>/actions/runs?head_sha=<sha complet>&event=pull_request" --jq '.workflow_runs[] | select(.name == "CI") | "\(.created_at) \(.status) \(.conclusion) \(.id)"'
```

Seule la **première ligne** décide : une réouverture ajoute un run sur la même tête, et les plus
anciens ne comptent plus. Sa conclusion :

- `success` → sortir du draft ;
- `in_progress` ou `queued`, conclusion `null` → le run tourne : **l'attendre** avant de passer à
  la suite, par une commande lancée en fond, dont la fin réveille la session —
  `timeout 1800 gh run watch <id> --exit-status -i 30`, `<id>` étant le dernier champ de la
  première ligne —, puis relire le run comme ci-dessus ; sortie 124, délai dépassé : Étape 6, « CI
  qui ne démarre pas ». Jamais une fin de tour nue : le moniteur de PR de l'application ne réveille
  que sur un échec, un conflit ou un commentaire (description de `set_monitor`, lue le
  2026-10-20), jamais sur un succès — mesuré le même jour, PR #141 : run vert à 19:21:01Z, aucun
  réveil en 14 min. C'est la seule surveillance de la CI que la session lance elle-même, le
  moniteur ne couvrant pas le succès ; jamais une sonde planifiée. Le lot 4b de l'issue #134 la
  remplace par `attente-ci.py` ;
- `cancelled` → relire le SHA de tête (`gh pr view <numéro> --json headRefOid`) : s'il a changé,
  lire le run du nouveau ; sinon, annulé sans remplaçant, « Si aucun run n'apparaît », ci-dessous ;
- `skipped` → l'ouverture d'une draft jamais repoussée depuis, que le garde du job `api` saute
  (mesuré le 2026-10-20 sur l'amorce de la PR #137) : « Si aucun run n'apparaît », ci-dessous ;
- aucune ligne → aucun run pour cette tête, un push émis pendant une panne d'Actions : même
  paragraphe ;
- toute autre conclusion (`failure`, `timed_out`, `startup_failure`…) → Étape 6, « Trier un
  rouge ».

Ce run a tourné sur la référence de fusion calculée à son push, que GitHub ne recalcule ni à chaque
merge sur le trunk ni au passage en ready : il peut combiner la tête à un trunk vieux de plusieurs
merges — mesuré, 8 des 30 commits de `main` (obs 51). Ce qu'il prouve de l'état combiné se lit
dans les parents de cette référence, à l'Étape 7.

**Si aucun run n'apparaît** pour le SHA de tête — `skipped`, `cancelled` sans run plus récent, ou
aucune ligne —, consulter d'abord `https://www.githubstatus.com/api/v2/components.json`, sauf
pour une draft jamais repoussée, qui se reconnaît à son seul run `skipped` : un événement émis pendant une panne d'Actions n'est **pas
rejoué** au rétablissement. Le re-déclenchement propre est `gh pr close` puis `gh pr reopen`
(`reopened` est dans les types du workflow), action visible donc sur accord du mainteneur —
jamais de commit vide ni de force-push. Puis relire le run du SHA de tête, comme ci-dessus : sa
première ligne est celle de la réouverture.

Puis seulement, sortir du draft :

```
gh pr ready <numéro>
```

Tant que la PR est en draft, elle n'est **pas** à reviewer : c'est ce marqueur qui distingue
« travail en cours » de « prêt à être relu ».

## Étape 6 — Review + CI

- **CI verte** : tous les gates déclarés dans `.claude/pipeline.config.md` (« gates bloquants en
  CI »), dont le seuil de couverture s'il y en a un.
- **Trier un rouge avant de toucher au code** — chaque famille de causes a son remède, et le
  premier message d'erreur du step les sépare presque toujours. La session PR lance elle-même
  `python <répertoire de ce skill>/scripts/erreurs-ci.py <id>`, une commande à la sortie courte :
  une ligne par step en échec — job, step et première ligne d'erreur du journal —, ou le job en
  échec sans step. Le script ne classe rien et ne lit pas les annotations ; une erreur sans
  marqueur d'outil retombe sur la première ligne qui nomme une erreur, sinon sur l'annotation de
  fin du step (`##[error]Process completed…`), qui ne dit rien : ce step-là se relit au journal.
  Le tri est une décision, à la session PR ; un correctif, à un `developpeur` :
  - *Rouge d'infrastructure* : échec de téléchargement (403/5xx/timeout d'un dépôt d'artefacts,
    « error while downloading ») alors que le diff ne touche aucune dépendance et qu'un run
    voisin passe le même step → `gh run rerun <id> --failed`, noter la cause et le rerun dans le
    Test plan. Corriger du code sur un rouge d'infra coûte un cycle complet pour rien.
  - *CI qui ne démarre pas* : `startup_failure` **immédiat et reproductible au re-run** → le
    fichier de workflow est en cause ; job resté `queued` sans runner, ou `startup_failure` dont
    le job n'a aucun step → allocation de runner (quota, incident fournisseur) — ne pas modifier
    le workflow, surveiller en fond et **rendre la main au mainteneur**. Les runs `skipped`
    (garde `if:`) se terminent sans runner et ne prouvent rien sur la disponibilité de la CI.
  - *Rouge d'avis* : le step d'audit ou de scan rougit sur un paquet que le diff ne touche pas →
    une base d'avis a changé sans commit. Vérifier que le trunk rougit aussi — son dernier run
    planifié ou un `workflow_dispatch` s'il en a, sinon la porte elle-même, sa commande du projet
    lancée sur `origin/<trunk>` dans un worktree jetable — et pour un scan d'images, précédée de
    leur construction depuis ce worktree sous un nom propre au trunk : le démon de conteneurs est
    partagé, et un scan sous le nom par défaut lirait les images de la branche, celles mêmes qu'il
    s'agit de mettre hors de cause. Jamais un rerun d'un run du trunk :
    `--job` comme le run entier relancent les jobs qui en dépendent (REST : « Re-run a job and
    its dependent jobs »), publication et déploiement compris. Puis appliquer « Création
    d'issues en cours de cycle » (`.claude/rules/contraintes.md`), barreau par barreau. Un rerun
    de la PR, lui, ne prouve rien : l'avis ne part pas (obs 56).
  - *Rouge de code* : tout le reste, y compris un rouge de plateforme (3.2) → cycle complet
    3.1→3.5.
- **Revue** : les commentaires d'une revue automatisée (bot), s'il y en a une. Un `developpeur` a
  relu la PR entière en 4.1, un tiers en 4.2 : pas de troisième lecture ici.
- Chaque commentaire **pertinent** → cycle complet (3.1→3.5) + push + re-trigger de la review.
  Chaque commentaire **non pertinent** → noter brièvement pourquoi, ne pas corriger.
- **Boucler jusqu'à review vide.**

> **Commentaire de répercussion.** Un merge survenu ailleurs pendant que cette PR était ouverte a
> pu rendre sa spec fausse ; `repercussions` le signale ici même (le corps de l'issue n'est
> volontairement pas modifié tant que la PR est ouverte), par un commentaire que
> `python <répertoire de ce skill>/scripts/ecriture-relue.py comment <n> --body-file <fichier>`
> publie puis relit en entier (Étape 8). Un signalement **bloquant** se traite comme tel :
> intégrer la correction dans cette PR, ou remonter au mainteneur si cela déplace le périmètre —
> ne jamais merger par-dessus.

## Étape 7 — Avant le merge

Quand la review est vide et la CI verte, **avant de demander le go** — sans nouvelle relecture du
code : le regard global a eu lieu en 4.1, la relecture indépendante en 4.2.

**Relire l'issue une dernière fois.** Le corps a pu bouger depuis le briefing de l'Étape 1 — d'autres
PR ont été mergées entre-temps, et une passe `repercussions` a pu la corriger ou déposer un
signalement sur cette PR. Comparer le corps actuel au briefing : si la spec a changé sur un point
que la PR ne couvre pas, **s'arrêter et le remonter** plutôt que de merger un travail construit sur
une spec périmée.

**Rejouer les vérifications périmées.** Une preuve a deux ancrages : la **tête** de branche et la
**base de branche** (`git fetch origin`, puis `git merge-base origin/<trunk> HEAD` — le point de
fork) — et elle se périme quand **ce qu'elle observe** a changé, pas quand un identifiant a
changé. « Base » désigne ici **cette** grandeur, et elle seule ; la grandeur voisine qui lui
ressemble tant que le trunk n'a pas avancé — le **trunk éprouvé**, ce que la CI a réellement
combiné — porte son propre nom, au paragraphe de la référence de fusion ci-dessous, parce qu'un
paramètre de porte dont le nom désigne deux valeurs se remplit un jour avec la mauvaise. Une vérification sans SHA, ou
sans « observe : », se rejoue d'office. Quand la **tête** a bougé : `git diff --stat <sha de la
vérification>..HEAD`, croisé avec ce que la vérification déclare observer (« observe : » du Test
plan), puis `git diff <sha de la vérification>..HEAD -- <fichiers observés>` pour juger le
contenu — elle se rejoue si le diff touche du code dont elle dépend ; elle reste cochée, ses deux
SHA d'origine conservés et le nouveau noté à côté, si le diff ne touche que des commentaires, de
la documentation ou des fichiers qu'elle n'atteint pas. Une preuve qu'on rejoue sans qu'elle
puisse changer de résultat n'est pas une preuve, c'est un rituel, et un rituel coûteux est le
plus sûr moyen de faire abandonner l'étape.

Quand c'est le **trunk** qui a bougé, les preuves locales sont périmées : prises sur un état qui
n'atteindra jamais le trunk, et rien de local ne le signale. La CI d'une PR, elle, tourne sur la
**référence de fusion** avec le trunk du moment : si le trunk a bougé **avant** le dernier run, ce
run éprouve déjà l'état combiné — **à condition de le lire**, parce que GitHub ne recalcule cette
référence ni à chaque merge sur le trunk ni au passage en ready (obs 51) :

```
gh api repos/<owner>/<repo>/git/ref/pull/<n>/merge --jq .object.sha
gh api repos/<owner>/<repo>/commits/<sha de la référence> --jq ".parents[].sha"
```

Le **premier parent** est le **trunk éprouvé** — ce que le dernier run a réellement combiné à la
tête —, et c'est **lui** que la porte de merge consomme, sous le nom `<SHA du trunk éprouvé>`. Il
doit valoir `git rev-parse origin/<trunk>` ; le second parent doit être la tête de la PR. Si le
premier parent n'est pas la tête du trunk, le run ne prouve rien de l'état combiné : relancer par
un commit réel, ou `close`/`reopen` sur accord, puis relire les parents. Le `--jq` se cite, `[]`
étant un motif de glob pour le shell. Puis vérifier l'absence de conflit par
`git merge-tree --write-tree origin/<trunk> HEAD`, qui est un **prédicat** : il sort en 0 sans
conflit et en 1 avec (mesuré le 2026-10-13, témoin de chaque côté), donc il s'enchaîne par `&&`,
et ce qu'il imprime n'est qu'un détail de diagnostic. L'état `MERGEABLE` de la forge, lui, se met
à jour en différé et ne prouve rien. Puis redater les preuves locales sur cette base. Si elle a bougé
**après**, relancer la CI — un commit réel, ou `gh pr close` puis `reopen` sur accord. Sur un
trunk fusionné par rebase ou squash, jamais de commit de fusion : il ne respecte pas le format
des messages et tombe au merge.

**Un critère qui nomme une commande se solde par cette commande, verbatim.** « `just run` démarre
l'app » ne se satisfait pas par `flutter build` + `adb install` : une équivalence est un résultat
*non vérifié*, pas un résultat — défendable par lot, et c'est ainsi qu'un critère transverse se
perd, chaque lot substituant en croyant qu'un autre a joué la recette.

### Vérif de fumée — regarder le logiciel tourner

Tout ce qui précède examine du **code** : tests, diffs, specs. Personne n'a encore vu la
fonctionnalité fonctionner. Pour tout ce qui est visible par un utilisateur, c'est un angle mort
qu'aucun test unitaire ne couvre.

**Condition de déclenchement** : la PR touche une surface visible du projet (une des surfaces
déclarées dans `.claude/pipeline.config.md` — interface, API publique, sortie de commande, format
de fichier produit). Une PR de refacto interne, de doc ou d'outillage **saute cette étape** — le
dire en une ligne et passer.

Si elle se déclenche, proposer **3 à 5 vérifications, pas plus**, dérivées des critères
d'acceptation de l'issue et exécutables sur l'application qui tourne (commande `run local` de la
config) :

- Chaque vérification nomme l'**action exacte** et le **résultat attendu**, et porte son **type**,
  écrit par la session PR : « commande + attendu », jouée par un `releveur`, qui rend le code de
  sortie et la sortie brute ; « observation humaine » (rendu, état affiché, console), jouée par le
  mainteneur au go de merge, dans la fenêtre de la session PR (#134, `[V]` 5) — aucun rôle de
  sous-agent n'a `playwright`.
- Ne vérifier que ce qu'un **test automatisé ne peut pas voir** : rendu réel, état d'erreur affiché,
  console propre, comportement d'un job jusqu'à son état terminal, fichier réellement produit.
  Si la CI le couvre déjà, ce n'est pas une vérif de fumée — c'est du doublon.
- **Aucune issue n'est créée**, aucune checklist n'est publiée. C'est une passe de deux minutes,
  pas une campagne : la campagne, c'est `plan-qa`, au niveau du thème.

Un écart constaté → le traiter comme un finding de l'Étape 7 (corriger, re-tester, push). S'il
sort du périmètre de la PR, appliquer « Création d'issues en cours de cycle »
(`.claude/rules/contraintes.md`) — PR courante, puis propriétaire ouvert (une automatisation qu'on
a fait taire se répare, elle ne se doublonne pas), puis brouillon soumis au mainteneur. Jamais un
`gh issue create` de la session.

### Vérification d'avant-go — le `verificateur`

**La session PR lance son `verificateur`** (`.claude/agents/verificateur.md`), sous-agent éphémère,
un par (PR, go), qui ne rend qu'un verdict (#134, décision 2) — en vague comme hors vague, le lead
ne le lance plus (`pr-paralleles` Étape 6). Il reçoit le numéro de la PR, celui de l'issue, le
chemin absolu du worktree et la liste des autres branches en vol (`gh pr list`), jamais le récit
de la session. Hors vague et hors lot, l'accord du mainteneur se demande **avec les `[V]` du
go du briefing** (Étape 1) — demandé à la fin, il attend la prochaine présence : 6 h 37 d'absence
au lot 4b de #77 sur cette seule question, à un moment où il ne restait rien d'indépendant à faire.
En vague, l'accord est celui du lot validé (`pr-paralleles` Étape 2) ; une session de lot : son
accord est à [references/coordinatrice.md](references/coordinatrice.md), « La session de lot ».

**Le verdict s'inscrit dans les Notes du body avant le go**, relu après écriture
(`contraintes.md`, « Écritures sur un artefact distant ») — au moins sa ligne d'en-tête (base,
tête) et ses lignes « Fichiers croisés » et « Non vérifié », qui parlent d'**autres** branches et
d'autres lots. Rendu seulement à
la session qui l'a commandé, il ne survit que par sa mémoire, et la passation suivante le relaie
comme un énoncé sans source : deux lots de suite, le prompt du lot suivant a cité un verdict que ni
le corps ni les commentaires de la PR ne portaient (obs 81).

Le verdict rendu :

- « rien à corriger » → demander le go, dans cette fenêtre ; en vague, le lead ne le redemande pas
  (`pr-paralleles` Étape 6).
- liste de corrections → les points partent ensemble à un `developpeur` neuf (3.1) ; le correctif
  se relit lui-même par la passe « affirmations » de `cleanup-verbatim.md` — chaque ligne de prose
  qu'il ajoute ou modifie porte sa provenance (obs 113) —, puis push et un `verificateur` neuf sur
  la nouvelle tête. Un point que la session PR juge infondé se conteste dans les Notes, preuve à
  l'appui — jamais en silence.

### Le go, puis le merge

**Jamais d'auto-merge dans le trunk.** Même CI verte, audit propre et verdict vert, toujours
attendre un « go » / « merge » humain explicite, **dans cette fenêtre** — un message de pair n'en
tient jamais lieu. Une PR de lot vers la branche d'intégration de son issue suit « Le merge d'un
lot », plus bas.

**Puis merger derrière une porte, pas derrière une lecture.** Un merge arrivé sur le trunk depuis
le dernier run rend la CI périmée : deux PR vertes séparément n'ont rien démontré ensemble, et le
merge est le premier moment où leur somme existe. `git fetch origin` d'abord, **seul**, puis :

```
git merge-base --is-ancestor origin/<trunk> <SHA du trunk éprouvé> && gh pr merge <n> --rebase --match-head-commit <SHA de tête vérifié>
```

Le `<SHA du trunk éprouvé>` est **le premier parent de la référence de fusion**, obtenu par les
deux commandes de « Rejouer les vérifications périmées » — lu dans ce que la forge a construit,
jamais supposé égal à la base de branche, et inscrit au Test plan. `--match-head-commit` ferme le
même trou côté tête. Si le trunk a avancé depuis, la commande **ne part pas** : rejouer « Rejouer
les vérifications périmées », relire les parents de la référence de fusion, puis un `verificateur`
neuf.

**Une porte est une commande dont le code de sortie porte la condition ; `&&` est ce qui la rend
bloquante.** Trois incidents, une seule classe. Une commande qui **imprime** n'est pas une porte,
enchaînée ou non — `git rev-parse main origin/main` a affiché deux SHA différents en sortant en 0,
et la branche a été créée quand même (obs 69) ; `git fetch && git rev-parse origin/main &&
gh pr merge` a affiché une base nouvelle, puis mergé (obs 60). Et **une lecture suivie d'une
seconde commande n'en est pas une non plus** : la fenêtre entre les deux est exactement là où
l'état change quand plusieurs écrivains visent la même cible (obs 59). La forme à substitution de
commande — `test "$(git rev-parse origin/<trunk>)" = "<sha>" && …` — est **refusée** par le garde
d'une session isolée en worktree ; `--is-ancestor` est la forme acceptée, et elle vaut l'égalité
parce que le trunk n'avance que vers l'avant. Mesuré le 2026-10-13, témoin de chaque côté : **1**
quand le trunk a avancé, **0** sur deux références égales — table `FRESHNESS_GATE_FORMS` de
`apps/api/tests/test_agent_skills.py`.

**Et cinq contrôles de ce skill et de `pr-paralleles` restent des lectures, par construction.**
Une porte n'a de sens que devant **une commande** : les deux auto-vérifications du `relecteur`
(4.2) précèdent une **phase entière** de travail, il n'y a rien à quoi se chaîner ; la
comparaison entre l'état de la forge et une référence locale avant `git branch -D` (`pr-paralleles`
Étape 8) porte sur les valeurs
de **deux outils**, donc exige la substitution que le garde refuse ; et les deux contrôles que la
coordinatrice lit avant d'ouvrir un lot — passation présente, `merge-tree` à 0 — précèdent un
`SendMessage`, un outil et non une commande
([references/coordinatrice.md](references/coordinatrice.md)). Elles se lisent, et elles le disent.
Le dénombrement de la classe, pris avant ces deux derniers — 15 sites, 10 portes, 6 qui fuyaient —
vit dans la docstring de `test_la_porte_de_fraicheur_porte_sa_condition_dans_son_code_de_sortie`,
avec la commande qui le re-dérive et la raison pour laquelle ce motif sous-compte.

### Le merge d'un lot — sans go, hors du trunk

Une PR de lot dont la base est la **branche d'intégration** de son issue, et non le trunk, se merge
**sans go humain** une fois verte : CI verte sur sa tête, boucle de relecture fermée et PR sortie
du draft (Étapes 4 et 5), verdict d'avant-go « rien à corriger ». Ce verdict s'inscrit dans les
Notes du body comme tout verdict (« Vérification d'avant-go »), plus une ligne de forme figée, que
le script lit :

```
Verdict d'avant-go (<SHA complet de tête>) : rien à corriger
```

Puis une seule commande, qui récupère elle-même la base :

```
python .claude/skills/cycle-pr/scripts/merge-lot.py <n> <SHA de tête vérifié> <branche d'intégration>
```

C'est la **seule** voie de merge que `.claude/settings.json` autorise sans invite ; `gh pr merge`
reste en `ask`, épinglé par `apps/api/tests/test_agent_permissions.py`. Le script porte lui-même
les portes de « Le go, puis le merge » — trunk refusé, base qui doit être la tête d'une PR
d'intégration ouverte, tête comparée au SHA vérifié — et une plus stricte : la tête du lot doit
**contenir** la tête actuelle de sa base, par un historique sans commit de merge. La CI de la tête
a alors éprouvé l'arbre exact que le `--rebase` rejouera, sans lire la référence de fusion, que la
forge recalcule à son rythme (obs 51). Puis `--rebase --match-head-commit`. Ses refus, et ce qu'il
ne prouve pas, sont dans sa docstring ; son contrat, dans `apps/api/tests/test_merge_lot.py`. Un
refus sort en une ligne et se traite comme une porte qui ne part pas : rejouer « Rejouer les
vérifications périmées », jamais le contourner par `gh pr merge` — sauf un refus de contenance ou
de commit de merge, que ces vérifications ne lèvent pas et qui suit la phrase suivante. **Un lot en
retard sur sa base** — ce que des lots ouverts l'un après l'autre ne devraient pas rencontrer (non
mesuré) — ne se remet pas à jour par `gh pr update-branch` : son commit de merge, que le script
refuse, serait abandonné par le `--rebase` (relecture de la PR #117, non mesuré). C'est un rebase
de branche ouverte, qui attend la demande explicite du mainteneur (`contraintes.md`). Un refus « CI
pas entièrement verte » alors que le dernier run est vert vient d'un run plus ancien sur la même
tête, que le script lit aussi (le rollup d'une tête porte un run par événement — cinq par job
relevés sur la PR #109) : un commit réel en ouvre un neuf, sur sa propre tête ; qu'un rerun du run
rouge lui-même suffise n'est pas mesuré.

## Étape 8 — Après le merge : clôture propre, puis répercussions

**Les écritures de la clôture passent par la famille « écriture distante relue »** — un script à
sous-commandes, Python ≥ 3.11 sans dépendance, lancé depuis le dépôt :

```
python <répertoire de ce skill>/scripts/ecriture-relue.py <sous-commande> …
```

Il lit la forge en octets, écrit, puis relit : un label retiré doit s'y relire absent, un texte
écrit s'y compare **entier** à l'attendu — une relecture qui ne compare qu'une ancre ou une
longueur laisse passer une conversion des fins de ligne qui les préserve (obs 106). Sortie 0 :
écrit et relu, ou rien à écrire ; 1 : refus sans rien écrire, ou relecture non conforme — motif
en une ligne ; 2 : appel mal formé.
**Ce qu'il ne couvre pas** : il ne choisit pas les cases, la session PR les nomme ; il ne compte
pas les PR liées, la requête GraphQL du cas découpé reste ; poser un milestone, créer une issue
viennent avec les lots 6 à 8 de #134. Toute écriture qu'il ne fait pas reste sous la règle
« Écritures sur un artefact distant » de `.claude/rules/contraintes.md`, relue à la main.

Le merge **clôt l'issue liée** (via `Closes #N`). **Retirer aussitôt son label d'état** —
`ready-for-agent` ou `ready-for-human`, selon le mapping de `.claude/pipeline.config.md` :
`ecriture-relue.py label <N> --remove <label>`. Une issue fermée ne porte **aucun** rôle d'état ;
le laisser fait apparaître des issues closes dans les files de `triage` et de `pr-paralleles`.
Le label de catégorie (`bug` / `enhancement`) et le thème restent.

Puis **cocher les critères d'acceptation soldés**, dans le **corps** de l'issue *et* dans le
commentaire de **brief** (`- [ ]` → `- [x]`) : ils ont été vérifiés à l'Étape 7, il ne reste qu'à
l'enregistrer là où un lecteur le cherche. Le corps par
`ecriture-relue.py checkbox patch <N> --case <ancre> …`, puis le brief par
`ecriture-relue.py brief patch <N> --case <ancre> …`, une ancre par critère : un extrait de son
texte, sans le marqueur `- [ ]`, qu'aucune autre case ne porte. Une ancre introuvable ou ambiguë
refuse l'appel entier sans rien écrire ; une case déjà cochée se dit.
Un critère atteint sous une forme **amendée** se coche
quand même — l'amendement est tracé au journal de spec du corps. Le brief d'une issue **close** est
un artefact daté : on coche ses cases, on ne réécrit pas son texte. (Tant que l'issue était
ouverte, c'était l'inverse : une réconciliation `repercussions` qui falsifiait une de ses lignes
l'amendait — la clôture est ce qui fige le brief.)

Puis **nettoyer la session de relecture** — archivage sur l'accord donné au go, worktree,
échafaudage —, la boucle de 4.2 étant fermée
([references/session-relecture.md](references/session-relecture.md), « Nettoyage »).

**Cas découpé : reposer le lien des lots précédents.** GitHub ne lie une PR à une issue que par un
mot-clé de fermeture, et seul le lot final en portait un (Étape 2) ; sans ce geste, l'issue
n'affiche qu'une PR sur les k qu'elle a coûté. Une fois l'issue close, ajouter en fin de body de
**chaque lot précédent** mergé dans le trunk le bloc ci-dessous, écrit dans un fichier :
`ecriture-relue.py issue edit <n> --append <fichier>`, qui le sépare du body par une ligne vide —
le body d'une PR s'écrit par l'endpoint des issues. Sur une issue close, le mot-clé ne change aucun
état ; une PR de lot vers une branche d'intégration n'en reçoit pas, il y serait ignoré :

```markdown
*Rattachement a posteriori (<date>) : lot k/n de #<N>. L'issue a bien été fermée par le lot
final, la PR #<M> ; le mot-clé ci-dessous ne sert qu'à faire apparaître cette PR parmi les PR
liées de l'issue.*

Closes #<N>
```

Puis vérifier que l'issue affiche autant de PR liées que de lots vers le trunk — avec une
coordinatrice, plus la seule PR d'intégration : une PR de lot vise une autre branche, où GitHub
ignore le mot-clé ([references/coordinatrice.md](references/coordinatrice.md), « Après le
dernier lot ») :

```
gh api graphql -f query='{ repository(owner:"<owner>",name:"<repo>"){ issue(number:<N>){
  closedByPullRequestsReferences(first:20, includeClosedPrs:true){ nodes{ number } } } } }'
```

**Un critère soldé par un autre lot se coche avec la trace de qui l'a joué** — le lot et le SHA.
Un critère transverse à plusieurs lots n'appartient à aucun ; sans cette trace, chaque lot croit
qu'un autre l'a fait et l'issue se ferme sur une case que personne n'a jouée.

**Relire le plan de test de la PR** et cocher toute case devenue vraie depuis son écriture —
« CI verte » d'abord, vérifiée par le rollup (`gh pr checks`), pas de mémoire ; puis les gates
délégués à la CI. Une case qui reste décochée après le merge l'est **par décision** et le dit sur
sa ligne, jamais par oubli : un compteur d'inachèvement allumé sur du travail fini s'éteint dans
les têtes avant de s'éteindre à l'écran.

Si la PR a porté des **preuves visuelles**, supprimer enfin la branche orpheline promise à
l'Étape 5 : `git push origin --delete captures/pr-<n>`.

**Bilan chiffré du cycle.** Mesurer la session sur **tous** ses transcripts — Python 3, sans
dépendance :

```
python <répertoire de ce skill>/scripts/bilan-session.py <transcript .jsonl> [<relais .jsonl> …]
```

Les transcripts vivent sous `~/.claude/projects/<projet>/<uuid de session>.jsonl` — l'uuid est
celui du répertoire scratchpad de la session. **Un cycle qui a rempli un contexte en a
plusieurs** : les donner tous, relais compris, dans n'importe quel ordre ; un bilan à un seul
transcript manque la moitié du cycle, et c'est la moitié la plus chère. Un transcript introuvable
se dit en tête de sortie — « transcripts demandés N, lus M — absents : … » — au lieu de rendre un
bilan partiel muet : le harnais a le droit de libérer un transcript entre deux sessions (obs 73),
et le relevé que la session sortante a déposé avant de passer la main (« Relais en cours de
cycle », plus bas) s'additionne alors à la main. Le script rend la durée,
l'attente **scindée** en réactivité et absences — celle du mainteneur comme celle d'un pair, un
écart entre deux transcripts compris —, le temps des sous-agents et des
workflows, le temps d'agent seul, le cache que chaque sous-agent a lu et écrit **contact par
contact** — lu dans son propre transcript, sous `<uuid>/subagents/`, reprises et agents au premier
plan compris ; pas sa sortie, que ce transcript sous-compte —, les points de contact humains et
les appels d'outils.

Écrire ces lignes, plus trois à la main — commits prévus contre commits de correction, constats
par passe, correctifs qui ont cassé quelque chose — dans `retrospectives/<date>-<issue>.md`,
dossier voisin du journal d'observations (chemin dans `CLAUDE.md`), hors du dépôt. C'est la seule
mesure qui dise si un changement de la pipeline a marché : l'attente et le coût des relectures ne
se voient dans aucun compte rendu.

**La ligne de comparaison au cycle précédent porte l'attente hors absences**, jamais l'agrégat.
Les deux n'ont ni la même cause ni le même remède : la réactivité relève de la pipeline —
questions groupées, arrêt au bon moment —, une absence relève du calendrier, et un cycle lancé le
soir rencontre une nuit. Une absence se commente **à part**, en disant ce que l'agent n'avait
plus d'indépendant à faire à ce moment-là. Mêlées, elles font lire un succès comme un échec.
Un bilan pris avant la PR #91 ne se compare pas tel quel : les attentes closes par un pair, les
commandes tapées et les écarts entre transcripts y comptaient en travail d'agent ; la durée d'un
outil suivi d'un message y comptait en attente, et les commandes tapées, les injections
`isMeta` et les chargements de skill citant une balise de pair y changeaient le compte des
contacts humains et des pairs. Re-mesurer le cycle précédent avec le script courant, si ses
transcripts existent encore, ou le dire sur la ligne de comparaison.

La PR et la conversation qui l'a résolue ont pu acter des décisions, déplacer un contrat d'interface, déjà faire une partie d'un autre lot, ou rendre une
hypothèse caduque ailleurs. **Immédiatement après le merge**, la session PR lance le skill
`repercussions` — elle tient le brief, les Notes et les constats de la PR, c'est le moment où
l'analyse est la plus riche. La collecte (delta, issues du thème, briefs pré-filtrés par ancre)
part à un `releveur` ; le go d'édition se demande au mainteneur dans la fenêtre de la session PR.
Même pour une **demande directe** sans issue liée, faire la passe : le delta mergé
peut impacter des issues ouvertes.

Il confronte le **delta réel** de la PR aux issues du **même thème** et à celles qui **mentionnent
une ancre** du delta (symbole, format, module, décision), puis **corrige le corps** de celles dont
la planification est devenue fausse — après un « go » explicite, et sans publier le moindre
commentaire. C'est le pendant *sortant* de l'auto-challenge *entrant* de l'Étape 1.

Si une issue déjà `ready-for-agent` voit son **périmètre** ou une **décision verrouillée** modifié
par cette passe, elle repasse en `needs-interrogation` : son interrogatoire portait sur une spec
qui n'existe plus.

Ne pas considérer la PR « terminée » tant que cette passe n'a pas été faite (même si la conclusion
est « aucune répercussion »).

**Cas découpé : la frontière de lot se franchit par la session sortante.** Sur un lot
intermédiaire, écrire le prompt du lot suivant depuis
[references/prompt-lot-suivant.md](references/prompt-lot-suivant.md), au chemin fixe de
[references/sessions-liees.md](references/sessions-liees.md) (« Passation »), et le remettre par ce
chemin, dans le message de fin, **à la coordinatrice**, qui ouvre la session du lot suivant sur ce
pointeur — une session de lot l'écrit sans passe `repercussions`, qui tourne au merge de la PR
d'intégration ([references/coordinatrice.md](references/coordinatrice.md)). Sans coordinatrice,
ou en repli, **après** la passe `repercussions`, au **mainteneur**, qui ouvre la session neuve et
lui donne le prompt. Pas le lead : sur une vague de cinq lots, chaque frontière passée par lui lui
coûte un brief relu et un prompt écrit, et son contexte a grossi jusqu'à devoir être relayé
lui-même (obs 62). La session sortante tient les artefacts de son lot ; le lead connaît la vague,
et c'est ce
qu'il garde — croisement des fichiers après merge, tableau de bord, vigilance de vague. Quand la
session sortante a disparu, deux replis de `pr-paralleles` : Étape 7, « Session disparue », pour
reconstituer ce qu'elle n'a pas remis, et Étape 8, « Issue en plusieurs lots », où c'est le lead
qui démarre la session du lot suivant.

**La passation s'écrit en dernier, depuis les artefacts** — SHA, PR, brief, constats —, jamais de
mémoire de code. Chaque point encore ouvert du lot — question au
mainteneur, correctif, message en attente — se pose d'abord, en une fois, puis se fait ou se laisse
sur une décision explicite : la passation ne part qu'avec une liste vide ou arbitrée. Mesuré : un
prompt remis à côté de trois questions ouvertes a fait démarrer le lot suivant aussitôt, et deux de
ses lignes sont devenues fausses à la réponse (obs 85).

Le gabarit ne porte que des **pointeurs** vers les artefacts, jamais une règle recopiée : un énoncé
recopié hérite des erreurs de son auteur en empruntant la crédibilité de la source qu'il cite
(obs 52).

**Une session neuve par lot.** Le lot suivant ne se déroule pas dans cette session, même si son
contexte le permettrait — un sous-lot né d'un re-découpage non plus (3.5, D-9) : #12 lot 2 a livré
ses deux sous-lots dans une même session, le cycle le plus cher relevé (107 M de jetons relus,
étude du 2026-10-19, §2.2). Deux raisons :

- le contexte d'un lot porte les **hypothèses** qui l'ont produit, et les relire au lot suivant,
  c'est se priver du seul regard neuf gratuit du cycle — le même argument qui fonde la relecture à
  contexte vierge de 4.2 ;
- **mesuré** : un lot **seul** a rempli un contexte en plein Étape 4 et a dû être relayé, ce qui a
  coûté deux artefacts — `bilan-session.py` accepte N transcripts, `pr-paralleles` Étape 5 a son
  paragraphe « Session relayée » (obs 40). Une session qui *entame* un lot avec un contexte à
  moitié plein part donc plus près de cette limite. Ce second point est une déduction de la
  mesure, pas une mesure : aucun cycle n'a enchaîné deux lots dans une session, précisément parce
  que la règle l'interdit.

Avec une coordinatrice, chaque lot a aussi son worktree neuf : la branche mergée d'un lot n'est
jamais un point de départ ([references/coordinatrice.md](references/coordinatrice.md), « La
session de lot »).

C'est aussi pourquoi le prompt du lot suivant est un **artefact remis**, et pas une consigne qu'on
se donne à soi-même.

**Relais en cours de cycle — la session sortante passe ce qu'elle seule possède.** Un cycle peut
remplir un contexte avant son Étape 8, et une session neuve reprend alors le même lot — la roue de
secours depuis que la session PR délègue son code (#134, A1). La session sortante écrit sa
passation, depuis les artefacts, dans la variante « relais » de
[references/prompt-lot-suivant.md](references/prompt-lot-suivant.md), au chemin fixe de
[references/sessions-liees.md](references/sessions-liees.md) (« Passation »), et la remet par ce
chemin à la coordinatrice pour une session de lot
([references/coordinatrice.md](references/coordinatrice.md), « Relais en cours de lot »), sinon au
mainteneur.
Trois choses que le relais ne peut pas reconstituer, chacune payée :

- **son bilan, déposé avant de rendre la main** — `bilan-session.py` sur son propre transcript,
  sortie écrite dans `retrospectives/<date>-<issue>-relais-<k>.txt`, **hors du dépôt** (dossier
  voisin du journal, chemin dans `CLAUDE.md`) : un relevé écrit dans un worktree part avec lui.
  Le harnais a libéré le transcript d'une session sortante 50 minutes avant que son relais ne
  commence (obs 73) ; ses marqueurs de libération ne visent que des transcripts de session — 15
  sur 15 au 2026-10-14, et `retrospectives/` garde ses fichiers depuis le 2026-09-26. Que le
  harnais ne libère jamais un fichier déposé n'est écrit nulle part : c'est un constat, pas une
  garantie ;
- **les numéros des entrées du journal d'observations déjà écrites pour ce cycle** — le plafond
  de `CLAUDE.md` se compte par cycle, relais compris, et un relais qui ignore le compte le
  recommence : le lot 1 de #77, sur trois sessions, a versé sept entrées sous un plafond de
  trois par session (obs 75) ;
- en vague, **l'adresse du lead**, à qui la session sortante demande le relais et à qui le relais
  envoie son état (`pr-paralleles` Étape 5, « Session relayée ») : c'est la session sortante qui
  sait que son contexte se remplit, pas le lead (obs 40).

**Le message de clôture prend une forme figée**, chemin de la passation compris
([references/sessions-liees.md](references/sessions-liees.md), « Fin de travail ») : jamais une
fin de tour. **En vague parallèle, il part au lead** : c'est sur lui que le lead archive la
session, ce qui libère son worktree (mesuré le 2026-10-18), puis retire celui-ci — un dossier
qui est le répertoire courant d'un processus ne s'efface pas (obs 42, `pr-paralleles` Étape 8).
Une session sait qu'elle a fini avant que le lead ne le sache : c'est elle qui porte ces faits.

## Les 5 idées à retenir

1. Tout l'effort de questions se fait **avant** de coder (briefing pré-PR + interrogatoire) — et
   une question technique ne se pose pas : elle se décide et se trace (`[T]`).
2. **La PR draft s'ouvre avant la première ligne de code**, avec `Closes #N`. C'est ce qui rend le
   travail visible comme *en cours* : sans elle, une autre session réécrira la spec de cette issue
   en croyant que personne ne travaille dessus.
3. Le cycle `modif → test → cleanup → test → commit` s'applique à chaque commit, triviaux
   compris.
4. **Deux filets de cleanup** : un par commit (regard local), un sur la PR entière avant la
   seconde relecture (4.1, regard global, inter-commits) — et une relecture à contexte vierge
   **en deux temps**, au socle et à la fin, jamais par commit, par **une seule session de
   relecture pour toute la PR**, démarrée au go et réveillée par message, dans son propre
   worktree, plafonnée à deux passes et une relance qui lui reviennent. Elle ne se nettoie qu'à
   la fermeture de la boucle : plus tôt, la relance n'a plus de destinataire.
5. La PR n'est **terminée qu'après la passe `repercussions`** : une clôture peut bouleverser les
   autres issues — la session PR le vérifie tant qu'elle tient le brief, les Notes et les constats.
