# Règle — Contraintes permanentes (à chaque commit)

Ces contraintes sont actives en continu, sur **chaque** commit, sans qu'on ait à les rappeler.

## Intégrité de l'historique
- **Aucun commit cassé n'entre dans l'historique.** La qualité est garantie *à chaque commit*,
  pas seulement à la fin. Si les tests sont rouges → pas de commit.
- **Jamais de force-push** sur une PR ouverte (sauf rebase/squash explicitement demandé), et
  **jamais** sur `main`.
- **Jamais d'auto-merge.** Même avec CI verte et audit propre, toujours attendre un « go » /
  « merge » humain explicite.

## Propreté du code
- **Aucun code mort, aucun scaffold inutilisé.** Supprimer les imports / classes /
  commentaires-tutoriels générés par les outils ; ne garder que ce qui sert *maintenant*.
- **Pas de fichiers placeholder « au cas où ».**
- **Pas d'imports wildcard / glob**, quelle que soit la forme qu'ils prennent dans le langage.
- **Aucune sortie de debug laissée en place** (log/print/console temporaire), ni `TODO`/`FIXME`
  sans propriétaire et explication.

## Qualité de conception
Le code visé est **modulaire, scalable, fractionné** — objectif permanent, pas une option :

- **Modulaire** : modules à responsabilité unique, derrière des interfaces petites et stables.
  Viser des **modules profonds** — petite interface, implémentation riche
  (`cycle-pr/references/modules-profonds.md`), jamais des modules qui passent-plat.
- **Fractionné** : décomposer les fonctions, séparer les responsabilités. Pas de fonction
  fourre-tout, pas de fichier monolithique.
- **Scalable** : concevoir pour que l'ajout d'un cas se fasse par **extension** plutôt que par
  modification invasive. Éviter le couplage fort et les hypothèses qui ne tiennent qu'à petite
  échelle (boucles N+1, état global, limites en dur non justifiées).

## Règle d'or — toujours poser un maximum de questions
- **Poser systématiquement un maximum de questions pour lever toute incertitude**, le plus tôt
  possible. Une question posée maintenant coûte 30 secondes ; la même ambiguïté découverte plus
  tard coûte une demi-journée.
- **Au moindre doute, on s'arrête et on demande.** Jamais de supposition silencieuse sur le scope,
  le format des données, les transitions d'état, les comportements attendus.
- **Toute prise de décision non triviale dans le doute → demander avant de trancher.** Choix
  d'architecture, de découpage, de format, de dépendance, de comportement : on ne décide pas en
  silence à la place de l'utilisateur. Présenter les options + une reco, puis demander.
- Exception : si la réponse se trouve dans le code, **explorer le code plutôt que demander**. Pour
  un grilling approfondi, utiliser `interroge-moi`. L'exploration ne s'arrête pas au dépôt : pour
  un comportement d'outil **non documenté**, les logs applicatifs, l'arborescence de données
  locale et les horodatages sont des sources de premier ordre — la documentation décrit
  l'intention, les logs enregistrent le comportement. Distinguer explicitement ce qui est
  **prouvé** (cité, horodaté) de ce qui n'a pas pu être vérifié.
- **Un « go » autorise l'exécution, il n'éteint pas le cadrage.** En particulier pour
  l'installation d'un outil : une demande qui nomme un outil précis est une solution déjà choisie,
  qui masque le problème qui l'a motivée. Faire remonter l'objectif avant d'installer — l'outil
  demandé peut ne pas le résoudre, ou le besoin peut être déjà couvert sans rien installer.
- **« Comment faire X » présuppose que X existe.** Avant de répondre par un mode d'emploi, vérifier
  la prémisse — en source officielle, jamais de mémoire — dès que X touche aux capacités, quotas,
  identifiants ou facturation d'un service tiers : une prémisse fausse y coûte de l'argent réel.
- **Jamais d'information dérivée d'un secret.** En guidant une action humaine sur un secret (jeton,
  clé, mot de passe), ne jamais demander un extrait de sa valeur — préfixe, longueur, derniers
  caractères, empreinte : une question dont la réponse s'obtient en regardant le secret sera
  satisfaite en collant le secret. Demander une **assertion binaire** (« commence-t-il par `sk.` ?
  oui / non »), annoncer l'attendu avant l'action, et précéder toute création de secret d'un
  « ne colle jamais la valeur ici ».

## Création d'issues en cours de cycle
- **Un cycle n'ouvre jamais d'issue seul.** Chaque skill a sa porte de sortie « nouvelle issue »
  (résidu de relecture, « ce que cette PR ne couvre pas », vide relevé par `repercussions`,
  échappatoire de `decisions-vs-doc`) ; chacune est raisonnable seule, leur somme ne l'est pas —
  une vague de deux issues en a ouvert cinq. La borne vit ici, au-dessus des skills.
- Tout vide, résidu ou hors-périmètre relevé en cours de cycle suit cet ordre et s'arrête au
  **premier barreau qui tient** :
  1. **il tient dans la PR courante en moins d'un commit** → le faire ;
  2. **une issue ouverte possède le sujet** — en critère, en journal, en brief, ou parce qu'une PR
     fermée le lui a renvoyé → y **ajouter un critère** : édition du corps avec sa ligne de
     journal, jamais un commentaire ; c'est la passe `repercussions` de l'Étape 8 qui le fait. Une
     automatisation qui possède le sujet (bot, workflow planifié) se répare, elle ne se doublonne
     pas ;
  3. **sinon** → un **brouillon** par `bug-vers-issue` ou `vers-issues`, montré au mainteneur, qui
     décide. Jamais de `gh issue create` sans ce brouillon validé.
- Une issue ouverte par le barreau 3 porte **dès sa création** son gabarit, sa catégorie et son
  thème.

## Écritures sur un artefact distant
- **Toute écriture sur un artefact distant se relit après écriture** — corps ou commentaire
  d'issue, body de PR, label, milestone : re-télécharger et vérifier que ce qu'on voulait y est,
  une **ancre** du contenu pour un texte, l'élément lui-même pour un label ou un milestone,
  **et** pour un texte que la **longueur** est plausible. Le code de retour atteste que la
  requête a abouti, jamais que le contenu écrit est celui qu'on voulait : une forme destructrice
  (un chemin pris pour un contenu, un `-f` tapé pour `-F`) rend exactement le même succès qu'une
  édition, et c'est un brief de 5 000 caractères remplacé par 120 qui l'a montré.

## Maintenance continue
- Tenir à jour, sans qu'on le redemande, les supports d'exécution du projet : fichier de commandes
  (`Makefile` / `justfile` / scripts du manifeste) et `.env.example`.
- Si une commande du projet change (test, lint, build…), mettre à jour la section « Commandes du
  projet » de `.claude/pipeline.config.md` **dans le même commit** — c'est elle que les skills lisent.
- **Tenir la documentation à jour dans le même commit que le changement** : `README`, `docs/`,
  `CLAUDE.md`, glossaire de domaine (`UBIQUITOUS_LANGUAGE.md`), docstrings/commentaires. Si un
  commit change un comportement, une commande, une interface ou l'architecture, la doc
  correspondante est mise à jour *dans ce commit* — jamais « plus tard ». Une doc fausse est pire
  qu'une doc absente.

## Points d'arrêt humains
- Seule zone sensible par défaut : l'**UI à valider visuellement**. Un projet peut en déclarer
  d'autres dans `.claude/pipeline.config.md` (section « Périmètre ») ; sans déclaration, aucun
  autre changement — schéma, migration, authentification — ne provoque d'arrêt.
- **Cadence : une fois par PR**, avant `gh pr ready`, sur l'écran monté et regardé dans les deux
  modes — pas avant chaque commit. Un écran n'existe pas avant d'être assemblé : au commit qui pose
  un composant, un jeton de thème ou une clé de texte, il n'y a rien à regarder, et demander de
  valider à l'aveugle transforme le point d'arrêt en formalité qu'on apprend à expédier. C'est le
  contraire de ce qu'il sert.
- Une zone sensible **ajoutée** par le projet suit la même cadence, sauf si sa ligne dans
  `.claude/pipeline.config.md` en déclare une autre.
