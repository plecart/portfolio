# Démarrage, briefing et PR draft — détail de `cycle-pr`

Passages déplacés mot pour mot de `cycle-pr/SKILL.md` (issue #177), chacun sous le titre que
cite son renvoi. Les liens `references/…` qu'ils portent se lisent depuis le dossier du skill,
et leurs renvois de position (« ci-dessous », « plus bas ») depuis l'emplacement du renvoi.

## Vague parallèle

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

## Éprouver les outils d'abord

**Éprouver les outils d'abord.** Un skill présuppose des outils ; tant qu'ils n'ont pas été
éprouvés, son plan est une hypothèse. Un outil branché sur un hook, un verrou ou un jeton ne se
révèle qu'à l'opération qui le déclenche ; une commande de lecture prouve que le binaire répond,
jamais que l'opération passera — `git status` ne déclenche aucun hook, le premier commit les
déclenche tous. Avant d'écrire une ligne du briefing, lancer la sonde d'outillage, Python ≥ 3.11
sans dépendance, depuis la racine du dépôt. `<format>` et `<test>` sont des lignes de « Commandes
du projet » de `.claude/pipeline.config.md`, la pile au choix de la session ; une ligne `n/a`, ou
marquée `# non vérifiée` (voir plus bas), se passe en **omettant** son option, et la sonde sort
`SAUTÉE` :

## Six sondes, de la moins chère à la plus chère

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

## Estimation

- **Estimation** — comptée **par critère**, en artefacts que le critère doit laisser, jamais en
  prose qui le décrit : une porte ou un invariant → un test paramétré à témoins des deux côtés
  (~100-150 lignes) ; un script → le script et son fichier de test (~400) ; une règle de skill → sa
  ligne, plus la docstring de dénombrement si elle ferme une classe. Calibration mesurée : les
  lots 1, 2 et 3 de #77 ont dépassé la leur de 2 à 5×, tous du même côté — une estimation en
  prose est un plancher. C'est elle que consomme le seuil relatif de `taille-pr.md` (obs 78).

## Porte d'entrée obligatoire — l'interrogatoire

- **Issue interrogée** (passée par `needs-interrogation`, décisions consignées dans le brief
  d'agent) → relire ces décisions, et vérifier qu'elles tiennent encore (auto-challenge ci-dessous).
- **Brief portant `⚠️ Non interrogée au triage`**, ou aucune trace d'interrogatoire → **s'arrêter
  et proposer une session d'interrogatoire** (`interroge-moi`, numéro de l'issue en argument), avant
  la première ligne de code, puis reporter ses décisions, écrites dans l'issue, dans les
  « Décisions verrouillées » du briefing.
- **Demande directe sans issue** → l'interrogatoire s'applique aussi ; il n'y a pas de raccourci
  parce que le travail n'a pas de ticket. Un correctif évident — visible à la lecture, sans
  décision de comportement (`contraintes.md`, barreau 3) — n'a rien à interroger : sa
  qualification, écrite dans le body de la PR — draft, ou PR de la voie courte — avec sa preuve,
  en tient lieu.

Le point n'est pas de cocher une case : c'est que **les décisions tranchées soient écrites**, dans
l'issue — brief amendé s'il est contredit — et dans le briefing. Elles seront relues par une
autre session que celle-ci.

## Auto-challenge du plan — le plan est-il encore exact ?

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

## Une réponse `[V]` du go qui contredit le brief l'amende avant la première ligne de code

**Une réponse `[V]` du go qui contredit le brief l'amende avant la première ligne de code** —
décision verrouillée, critère ou interface : décision réécrite avec son motif et sa date, critères
déplacés, une ligne datée au « Journal de spec » du corps (`decisions-vs-doc`, sortie 2), relue
après écriture. Le corps de la PR ne remplace pas le brief : les lots suivants et `repercussions`
ne lisent que l'issue (obs 44).

## Découpage en plusieurs lots

**Découpage en plusieurs lots.** Quand le briefing découpe l'issue en n > 1 lots (`taille-pr.md`),
la session devient la **coordinatrice** de ses lots : elle n'écrit pas de code, et son go — le go
du découpage — fait démarrer les sessions de lot, ou chacune à son ouverture
([references/coordinatrice.md](references/coordinatrice.md)). Une issue à un seul lot ne change
rien : la session porte le cycle elle-même et délègue le code (3.1). Une session de lot attend
le go ci-dessous dans sa fenêtre comme toute session PR, et y démarre sa session de relecture
— sauf go délégué à la coordinatrice, qui lève l'attente et passe la relecture au repli
`relecteur` (même référence, « La session de lot »).

## La PR est le premier artefact produit, pas le dernier

**La PR est le premier artefact produit, pas le dernier.** C'est elle qui rend le travail
*visible comme en cours* pour le reste de la pipeline : `repercussions` s'en sert pour savoir
qu'une issue est « en vol » et ne pas réécrire sa spec sous les pieds de cette session, et
`pr-paralleles` pour tenir son tableau de bord. **Une branche locale sans PR est invisible** — le
travail existe, mais rien ne le sait.

## `Closes #<N>` dans le body

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

## Pour une demande directe sans issue

Pour une **demande directe sans issue**, ouvrir quand même la draft : sans `Closes`, mais le
travail reste visible du reste de la pipeline. Pour une draft née d'un échec de QA (case
` 🔴 correctif évident — …`), la session, une fois la draft ouverte, remplace ce marqueur par
` 🔴 PR #<M>` sur la case, par une paire
(`python .claude/skills/cycle-pr/scripts/ecriture-relue.py checkbox patch <plan> --paires <fichier>`,
`execution-qa/references/patch-checkbox-gh.md`) : c'est ce que lit la reprise de la QA.

## La CI tourne sur chaque push de la branche, draft comprise

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
