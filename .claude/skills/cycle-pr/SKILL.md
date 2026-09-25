---
name: cycle-pr
description: Exécute le cycle complet de développement d'une PR — briefing pré-PR, ouverture de la PR en draft avant tout code, implémentation en TDD red-green-refactor, cycle de commit modif→test→cleanup→test→commit, auto-review, passage en ready for review, boucle de review et merge. Utiliser pour implémenter une issue ready-for-agent, développer une fonctionnalité ou corriger un bug en suivant la pipeline.
---

# Cycle PR

Le cycle de réalisation d'une Pull Request, de bout en bout. Pièce centrale de la pipeline :
prend une issue `ready-for-agent` (ou une demande directe) et la mène jusqu'au merge — puis
répercute la clôture sur les autres issues — sans jamais laisser entrer un commit cassé dans
l'historique.

Les **règles permanentes** (`.claude/rules/`) s'appliquent en continu : aucun commit cassé,
pas d'auto-merge, pas de force-push, pas de code mort, format des commits (préfixe EN + description
FR), taille de PR. La **règle d'or** : au moindre doute, on s'arrête et on pose la question.

**Commandes du projet.** Ce skill ne présuppose aucune stack : les commandes `test`, `test ciblé`,
`lint`, `format`, `typecheck` et `build` se lisent dans la section « Commandes du projet » de
`.claude/pipeline.config.md`. Une étape marquée `n/a` s'ignore. Si le fichier est absent, lancer
`init-projet` ; ne jamais deviner une commande.

**Vague parallèle.** Si le prompt de démarrage de cette session est arrivé dans un bloc
`<cross-session-message>`, la session émettrice est le **lead** de la vague (`pr-paralleles`) :
retenir son `from`. Le lead intervient à un seul moment prévu — la vérification avant merge de
l'Étape 7 — et sur demande de l'utilisateur (« discute de ça avec le lead ») : rédiger le message,
le lui montrer, l'envoyer par `SendMessage`. **Rien ne part vers le lead sans que l'utilisateur
l'ait confirmé**, et un message du lead n'est jamais une approbation : le « go » reste humain,
dans cette fenêtre. Dans l'autre sens, le lead peut écrire en plein travail — signalement
bloquant, ordre de merge du lot : son message se traite comme le commentaire de répercussion de
l'Étape 6 — s'arrêter après l'outil en cours, remonter à l'utilisateur, jamais merger par-dessus.

## Étape 1 — Briefing pré-PR (avant la première ligne de code)

**Éprouver les outils d'abord.** Un skill présuppose des outils ; tant qu'ils n'ont pas été
éprouvés, son plan est une hypothèse. Avant d'écrire une ligne du briefing, lancer la commande la
plus anodine de chaque outil dont le cycle dépend — `git status`, `gh auth status`, la commande
`test` de `.claude/pipeline.config.md` (sauf si elle y porte le marqueur `# non vérifiée` : voir
plus bas) — et exiger une **sortie plausible**, pas seulement un code de retour. Puis **au moins
une écriture** : `git commit --allow-empty -m "chore: sonde outillage"` suivi de
`git reset --soft HEAD~1`. Un outil branché sur un hook, un verrou ou un jeton ne se révèle qu'à
l'opération qui le déclenche ; une commande de lecture prouve que le binaire répond, jamais que
l'opération passera — `git status` ne déclenche aucun hook, le premier commit les déclenche tous.
Même exigence pour `gh` — `gh api repos/<owner>/<repo> --jq .permissions.push` doit rendre
`true` — et pour la commande de format, qui écrit (même exception). Le tout sur un arbre et un
index propres (`git status` vide) : la sonde de commit emporte ce qui est stagé, et la commande de
format réécrit ce qui ne l'est pas.

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
- **Décisions verrouillées** — choix d'architecture / scope / format actés.
- **Questions résiduelles** — découpage, format des données, transitions d'état, comportements,
  edge cases.

Poser **un maximum de questions pour lever toute incertitude maintenant**. Une question posée
maintenant coûte 30 secondes ; la même ambiguïté après 5 commits coûte une demi-journée.

### Porte d'entrée obligatoire — l'interrogatoire

**Aucune PR ne démarre sans que le travail soit passé par `interroge-moi`.** Vérifier l'état de
l'issue dès les outils éprouvés :

- **Issue interrogée** (passée par `needs-interrogation`, décisions consignées dans le brief
  d'agent) → relire ces décisions, et vérifier qu'elles tiennent encore (auto-challenge ci-dessous).
- **Brief portant `⚠️ Non interrogée au triage`**, ou aucune trace d'interrogatoire → **lancer
  `interroge-moi` immédiatement**, avant la première ligne de code, et reporter les décisions
  tranchées dans les « Décisions verrouillées » du briefing.
- **Demande directe sans issue** → l'interrogatoire s'applique aussi ; il n'y a pas de raccourci
  parce que le travail n'a pas de ticket.

Le point n'est pas de cocher une case : c'est que **les décisions tranchées soient écrites**, dans
l'issue ou dans le briefing. Elles seront relues par une autre session que celle-ci.

### Auto-challenge du plan — le plan est-il encore exact ?

Avant de présenter le briefing comme acté, **se challenger explicitement** : le plan a pu être
écrit (issue, agent brief, conversation) *avant* que d'autres PR ne soient mergées. Le terrain a
peut-être bougé. Confronter le plan à la réalité **actuelle** du code :

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

Attendre un **« go » explicite**, puis créer la branche — trunk-based depuis `main`, après avoir
vérifié que `main` local et `origin/main` sont le même commit (`git fetch origin`, puis
`git rev-parse main origin/main` rend deux fois le même SHA ; `main` local en avance → demander
à l'utilisateur de pousser, ou l'autorisation de le faire ; `origin/main` en avance → sur `main`,
`git pull --ff-only` d'abord) :

```
git checkout -b <type>/<description>   # feat/  fix/  chore/  docs/  refactor/
```

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
  l'Étape 8, une fois l'issue close.
- Le **briefing de l'Étape 1** comme corps provisoire — le plan devient lisible par le mainteneur
  et par les autres sessions, avant que le code n'existe.
- **Assignee**, **labels** et **milestone** (mapping de `.claude/pipeline.config.md`).
- Le marqueur **draft**, qui dit « en cours, ne pas reviewer » et interdit le merge accidentel.

Pour une **demande directe sans issue**, ouvrir quand même la draft : sans `Closes`, mais le
travail reste visible du reste de la pipeline.

> **La CI ne tourne pas sur une draft** (garde `if:` dans le `ci.yml` du template). C'est voulu :
> les étapes 3.2 et 3.4 imposent une suite verte en local avant chaque commit, donc le filet est
> déjà tendu — inutile de dépenser des runs sur du code incomplet. La CI démarre au `gh pr ready`
> de l'Étape 5. **Ne pas interpréter l'absence de run comme une CI cassée.**

En vague parallèle (`pr-paralleles`), le lead relève lui-même le numéro de PR (`gh pr list`) pour
son tableau de bord : rien à lui envoyer.

## Étape 3 — Le cycle de commit (jamais sauté, jamais raccourci)

Chaque commit suit **exactement** :

```
1. modif (TDD)  →  2. test (vert)  →  3. cleanup pass  →  4. test (vert)  →  5. commit
```

**La boucle s'enchaîne sans rendre la main.** Un cycle AFK va de 3.1 à 3.5 puis repart en 3.1
jusqu'à l'Étape 4 — en lançant au passage la **première passe de relecture 4.2** dès que le
commit qui vient d'être fait pose un invariant que les suivants supposeront vrai ; l'annonce de
l'étape suivante (« Next : commit 2/3 ») est un **titre**, pas une demande d'autorisation. Les
seuls arrêts légitimes du cycle : une question dont la réponse change le travail, un arrêt
`decisions-vs-doc`, le point d'arrêt humain de l'Étape 5 (zone sensible, une fois par PR) et le
« go » de l'Étape 7. Ailleurs, s'arrêter est une remise de main que personne n'a demandée.

### 3.1 Modification — en TDD (tracer bullet vertical)

**Frontières tierces : on vérifie, on ne suppose pas.** Avant d'appuyer un comportement sur une
bibliothèque ou un framework tiers à une frontière (réseau, encodage, secrets, fusion avec un
thème ou une config par défaut, cycle de vie de ressources), lire ce que fait réellement l'API —
documentation via `context7` ou sources du paquet — et le noter dans les `Notes` de la PR avec sa
référence. Les défauts les plus coûteux d'une PR « verte » sont des suppositions sur un paquet :
un décodage par défaut, un retry silencieux, une fusion de valeurs, un `repr` qui affiche un secret.

**Un avis de sécurité sans correctif n'est pas une impasse.** Une plage d'avis `*` — toutes les
versions publiées affectées, paquet abandonné — ne clôt pas l'analyse, elle la déplace d'un
étage : avant de conclure qu'un avis est irréductible, remonter la chaîne de dépendance et
vérifier, pour **chaque** parent, s'il a cessé de dépendre du paquet fautif dans une version
ultérieure — le correctif d'un paquet abandonné vient presque toujours de son consommateur. Puis
regarder comment d'autres projets ont traité le même avis : un mur atteint par tout le monde a
souvent une issue de sortie publiée. Dix avis dont sept `high` sont tombés à zéro en forçant un
parent d'une majeure. Et un `override` qui saute une majeure sous un consommateur non prévu pour
elle **s'éprouve en exécutant réellement l'outil**, pas en relançant l'audit.

Implémenter **un comportement à la fois** en red-green-refactor. **Ne jamais** écrire tous les
tests d'abord puis toute l'implémentation (slicing horizontal = mauvais tests) :

```
ROUGE : écrire UN test du prochain comportement → il échoue
VERT  : écrire le minimum de code pour le faire passer → il passe
```

Règles : un test à la fois ; juste assez de code pour passer le test courant ; ne pas anticiper
les tests futurs ; tester le comportement observable via l'interface publique.

**Le rouge se constate, il ne se suppose pas — un test qui n'a pas été vu rouge n'est pas un
test.** Cinq cas à traiter explicitement :

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
  les deux divergent.
- **Le test est dicté par un tiers** (relecteur, lead de vague, issue) → même règle que pour un
  test écrit soi-même : mutation avant de le garder. L'autorité de la source ne remplace pas le
  rouge observé.
- **L'assertion est une absence** (`findsNothing`, `is None`, `not called`, « aucun X quel que
  soit l'état ») → le test doit être vu rouge sur un état où la chose **est présente** : le code
  inchangé, avant le correctif. Une recherche qui ne trouve rien et une recherche mal formée
  rendent le même résultat (un sélecteur sur la classe de base ne voit pas la sous-classe) ; s'il
  passe à ce moment-là, le défaut est dans le sélecteur, jamais dans le sujet. Un garde d'absence
  jamais vu rouge n'est pas un garde, c'est un commentaire exécutable.

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

Lancer la suite rapide. **Si rouge → pas de commit.** On répare. Six contrôles complémentaires :

- **Échec d'outillage ≠ échec de code.** Un échec « exécutable introuvable », « fichier utilisé
  par un autre processus » ou un compilateur qui sort brutalement après une commande tuée n'est
  pas un test rouge : vérifier d'abord l'environnement — processus orphelins laissés par un run
  interrompu (les lister **filtrés sur le chemin du worktree** avant de les tuer), worktree non
  provisionné — et ne diagnostiquer le code que sur un environnement propre.
- **Un résumeur n'est pas un verdict.** Quand la commande de test passe par un filtre ou un
  résumeur — proxy de sortie, hook de réécriture —, tout bilan qui annonce **zéro test collecté**,
  ou tout état autre que le rouge nommé à l'avance, se relit sur la **sortie brute du lanceur**
  avant d'être interprété : la commande `test brut` de `.claude/pipeline.config.md`, ou à défaut
  le contournement que le résumeur documente. Un résumeur a déjà rendu « aucun test collecté »
  sur un `1 failed, 3 passed` dont le message d'assertion portait un accent, et un rouge attendu
  lu comme « rien collecté » se conclut « environnement cassé ». Tant qu'il n'a pas montré qu'il
  distingue « zéro test » d'« un test rouge », son bilan n'est pas un verdict.
- **Une porte verte ne vaut que pour la plateforme qui l'a rendue.** Quand le poste et la CI n'ont
  pas le même OS, recenser une fois, au premier scaffold, les règles de qualité sensibles à la
  plateforme — bit exécutable, fins de ligne, sensibilité à la casse des chemins, séparateur de
  chemin, encodage par défaut — dans la section « Qualité » de `.claude/pipeline.config.md`, et
  dire dans les `Notes` de la PR lesquelles ne sont vérifiées qu'en CI. Quatorze commits verts
  sous Windows ont rougi en onze secondes sous Linux, sur une règle de lint que NTFS ne peut pas
  déclencher ; l'inverse existe aussi, un fichier que `.gitattributes` pinne en LF et qu'une copie
  de travail CRLF fait rougir sur le seul poste.
- **Une commande du projet que la suite n'exécute pas est invisible à toutes les portes.** Si le
  delta touche le fichier de commandes du projet (`Makefile`, `justfile`, scripts du manifeste)
  ou la définition d'une commande listée dans `.claude/pipeline.config.md`, **exécuter cette
  commande** — pas seulement la suite de tests : une cible qu'aucune porte n'appelle n'est
  vérifiée par personne, et sa cohérence à la lecture est précisément ce qui rend le défaut
  invisible (un `export` posé avant un `?=` vide la variable, et le fichier reste lisible). Une
  cible qui ne peut pas tourner ici — Docker, jeton, réseau — se vérifie sur la commande **après
  expansion** (`make --dry-run <cible>`, ou l'équivalent du lanceur du projet), jamais sur le
  texte du fichier.
- **Couverture par commit.** Lire le rapport de couverture du delta : une ligne non couverte est
  d'abord une hypothèse de **code écrit trop tôt**, à déplacer vers le commit de son premier
  appelant — avant d'être un test manquant. C'est le seul instrument qui rende opposable
  l'interdiction du scaffold inutilisé.
- **Atteignabilité.** Une suite verte ne prouve que ce qu'elle compile : un fichier ajouté que ni
  la production ni les tests n'importent est invisible à toutes les gates à la fois (profil
  typique d'une PR foundation qui pose jetons ou constantes). Exiger au moins un point d'appel
  depuis les tests, et l'avoir vu rougir en cassant ce qu'il référence.

### 3.3 Le « cleanup pass » — relecture distincte du delta

Une fois le delta fonctionnel et vert, faire une **relecture distincte** (pas du nettoyage au fil
de l'eau).

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

Le cleanup a pu casser quelque chose. Relancer les tests → **vert obligatoire** — et la commande
du projet que 3.2 a fait exécuter, si le delta la touche.

### 3.5 Commit

Uniquement si tout passe. Message = **titre conventional commit seul** (préfixe EN, description FR) :

```
git commit -m "type(scope): description"
```

Pas de corps, pas de footer, pas de `Co-Authored-By`, pas de numéro de PR. Breaking change : `!`
dans le titre. Puis enchaîner sur le commit suivant (retour 3.1) — ou, si ce commit vient de poser
le socle, lancer d'abord la première passe de relecture (4.2, « En deux temps »).

## Étape 4 — Relecture indépendante (avant `git push`)

Deux relectures. L'auto-review (4.1) quand tous les commits sont faits. La relecture à contexte
vierge (4.2) **en deux temps** : une première fois dès que le socle est posé, en plein cycle de
commit ; une seconde après 4.1, sur ce qui a été écrit depuis la première — ou sur `main..HEAD`
si aucun commit n'a posé de socle.

**4.1 Auto-review** — revue critique du **diff complet de la branche** (`main..HEAD`), en vision
d'ensemble : problèmes d'architecture (couplage, frontières), naming incohérent entre commits,
edge cases / erreurs / race conditions, KISS/DRY/YAGNI à l'échelle de la PR — notamment la
**duplication inter-commits**.

**4.2 Relecture par un contexte vierge — obligatoire.** L'auto-review est faite par la session qui
a écrit le code, avec les hypothèses qui l'ont produit ; elle ne les met pas à l'épreuve.
**L'exigence** : le diff est relu par un lecteur qui n'a pas ces hypothèses. **Le moyen par
défaut** : un **agent de relecture** (sous-agent sans accès à cette conversation — rôle
`developpeur` s'il est disponible ; un rôle ajouté dans `.claude/agents/` pendant cette session
n'existe pas encore pour l'outil Agent → repli `general-purpose` avec le modèle du rôle, jamais
sauter l'étape).
L'invocation de `cycle-pr` — `/cycle-pr` tapé par l'utilisateur, ou prompt de démarrage d'une
vague `pr-paralleles` — **vaut demande** pour cet agent : une consigne de session « pas de
sous-agent sans demande de l'utilisateur » est déjà satisfaite, ne pas re-demander. **Repli** si
le harness ne permet réellement pas de lancer un sous-agent : rendre la main au relecteur humain
avec le diff et le prompt de relecture verbatim, et le noter dans la section « Relecture
indépendante » du body de PR — jamais de saut silencieux. L'agent reçoit **uniquement** :

- le corps de l'issue et son brief d'agent (ou le briefing de l'Étape 1) ;
- le diff `main..HEAD` et le droit de lire les fichiers touchés — en seconde passe, le diff
  `<sha de fin de la première passe>..HEAD` (ou `main..HEAD` sans première passe) et les constats
  de la première, corrigés ou écartés ;
- `.claude/rules/contraintes.md`, `.claude/rules/cleanup-verbatim.md` et le prompt de relecture
  **verbatim** ;
- la consigne **frontières tierces** : pour chaque appel à une bibliothèque ou un framework tiers à
  une frontière — réseau, sérialisation/encodage, secrets, fusion avec un thème ou une config par
  défaut, cycle de vie de ressources — **vérifier le comportement réel** dans la documentation
  (`context7`) ou dans les sources du paquet, jamais de mémoire, et signaler tout écart avec ce que
  le code suppose ; un avis de sécurité sans version corrigée se remonte par la chaîne de
  dépendance (3.1) et ne se rapporte jamais « irréductible » sans ce parcours ;
- la consigne **provenance** : chaque constat porte son marqueur — **mesuré** (commande exécutée,
  sortie citée), **lu** (fichier et ligne ouverts), **supposé** (à vérifier). Un chiffre sans
  marqueur « mesuré » est interdit ; un résultat attendu d'un sous-agent qui n'est pas arrivé se
  rapporte « non vérifié », jamais comme un résultat — dans une chaîne de délégation, la preuve ne
  se transmet pas, elle se produit ;
- la consigne **mutation des décisions verrouillées** : pour chaque décision verrouillée qui est un
  invariant de protocole (ordre d'opérations, atomicité, option d'une commande, confirmation avant
  usage), **retirer ou inverser la décision dans le code** et exiger un test rouge ; une décision
  dont la mutation passe au vert reçoit un test avant merge — un invariant que seule la lecture
  garantit n'est pas garanti. Trois mutations obligatoires en plus :
  - **séparation** — quand un correctif rend distincts deux identifiants jusque-là confondus
    (clé, adresse, chemin, espace de noms), chercher ce qui **comparait par égalité exacte** sur
    l'ensemble qui les contenait et l'éprouver sous un écrivain concurrent : « qu'est-ce qui tirait
    profit de la confusion ? » ;
  - **défaut injectable** — pour toute fonction injectable dont le défaut est une implémentation
    réelle, muter **ce défaut** (retirer la ligne qui branche le filtre, le réglage, le hook), pas
    seulement la logique qui choisit entre le vrai et le faux — une suite entière est déjà restée
    verte après la suppression d'un filtre PII ;
  - **correctif de fuite** — exiger le dénombrement de `cleanup-verbatim.md` : « sous combien de
    formes cette donnée voyage-t-elle, et combien en as-tu mesurées ? ».
- la consigne **commande non exercée** : pour toute cible du fichier de commandes touchée par le
  delta et que la suite n'appelle pas, exiger qu'elle ait été exécutée (3.2) ou, si elle ne peut
  pas tourner ici, un test sur sa forme expansée (`make --dry-run <cible>`, ou l'équivalent du
  lanceur du projet) — la différence entre vérifier ce qui est écrit et ce qui s'exécutera.

Il rend : chaque critère d'acceptation ✅ / ❌ / ⚠️ avec preuve, puis ses constats classés
bloquant / important / mineur, chacun avec fichier, raison et marqueur de provenance. **Ne pas
discuter un constat depuis la mémoire de la session : le vérifier dans le code** — et re-mesurer
tout constat bloquant avant d'éditer sur sa base.

**En deux temps, jamais par commit.** Une première passe dès qu'un commit pose un **invariant que
les commits suivants supposeront vrai** — par exemple le contrat d'infrastructure : image, point
d'entrée, fichier de composition, contrat de configuration ; pour une PR de règles, les règles —
et une seconde, plus courte, à la fin, sur ce qui a été écrit après la première. Le déclencheur
est le **contenu** du commit, jamais son rang : sur une PR, les deux premiers commits ne portaient
qu'une constante et deux dépendances, et tous les invariants non gardés vivaient dans les
troisième et quatrième. Placée seulement à la fin, la
relecture rend ses constats à la distance maximale du moment où ils auraient pu être absorbés —
19 commits dont 13 en réaction à des constats arrivés après le vert, 25 tests dont 18 après la
relecture : un travail juste, rendu cher par sa position dans le temps. Un constat de la première
passe se fond dans un commit qui restait à écrire ; un constat qui arrive après le passage en
ready coûte un run de CI complet et le rejeu des vérifications manuelles (Étape 7). Au plus deux
passes par PR.

**La relecture n'est pas en lecture seule au sens strict.** Éprouver un test sérieusement, c'est
casser la garde qu'il protège et la voir rougir — donc **modifier le code de production**, puis le
restaurer — et le relecteur partage l'arbre de travail de cette session. Pendant toute la passe :
**ne rien stager, ne rien committer**, et vérifier `git status` juste avant le premier `git add`
qui suit. Le relecteur rapporte `git status --porcelain` en fin de passe — c'est le point de
reprise sûr.

**Éprouver un test par mutation est une procédure, pas un rappel.** Un harnais dont l'échec attendu
et la panne d'outil produisent le même signal ne mesure rien — et une rangée de rouges se lit
comme un travail rigoureux. Trois exigences structurelles, à chaque passe :

1. **Un témoin de non-mutation** : le harnais tourne d'abord sur l'arbre propre et doit produire un
   vert. Un harnais qui ne sait pas produire de vert ne sait rien produire.
2. **Trois états, jamais deux** : ROUGE (assertion) / VERT (trou) / **PANNE D'OUTIL**. Le verdict se
   lit dans la ligne de bilan du lanceur (`failed` vs `error`), jamais dans le code de retour ni
   dans un `cmd && ok || ko` — ni dans le bilan d'un résumeur qui n'a pas encore montré un rouge
   nommé : la ligne de bilan se lit sur la sortie brute (3.2), et le harnais doit avoir produit
   **au moins une fois un ROUGE lisible avec son nom de test** avant qu'on accorde du crédit à
   ses VERTS.
3. **Le rouge attendu est nommé avant le run** — quel test, quel paramètre — et le harnais vérifie
   que ce nom figure parmi les échecs. C'est le seul contrôle qui distingue « le garde a mordu »
   de « tout est tombé ».

Et **lancer les tests par la commande du projet** (`.claude/pipeline.config.md`), jamais par un
appel direct au lanceur : c'est elle qui porte l'environnement ; un sous-processus qui la
court-circuite ne teste pas la même chose que la CI.

Un constat retenu de la **première** passe s'absorbe dans le commit à venir qui touche sa zone,
sinon il reçoit un commit de fix dédié ; un constat de la **seconde** passe → **un commit de fix
dédié** (cycle complet 3.1→3.5). La relance n'est pas une répétition de la revue, ni une passe au
sens du plafond « au plus deux » : c'est une **revue des commits de correction**, ciblée par un diff
explicite (`<sha avant>..<sha après>`) et par la liste de ce que chaque commit prétend régler,
avec la question obligatoire : « qu'est-ce que ce correctif a cassé, ou fait rougir à tort, que la
version précédente voyait ? ». Un correctif est du code neuf écrit sous pression de conclure —
c'est la partie la moins éprouvée de la PR, pas la plus sûre. Boucler tant qu'il reste un bloquant
ou un important. Les constats écartés sont notés avec leur raison — ils iront dans les `Notes` de
la PR (Étape 5).

Une fois la seconde passe propre → `git push`.

## Étape 5 — Finalisation de la PR (passage en ready for review)

La PR **existe déjà** depuis l'Étape 2. Il s'agit ici de remplacer le briefing provisoire par le
body définitif, puis de sortir du draft.

- **Titre** conventional commit (préfixe EN + description FR) — le réajuster si le scope a bougé
  en cours de route.
- **Assignee**, **labels**, **milestone** : vérifier qu'ils sont toujours justes.
- **Conserver la ligne `Closes #<N>`** — la perdre en réécrivant le body casserait à la fois la
  fermeture automatique de l'issue et la détection « en vol ».
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
      la tête et la base `git merge-base origin/main HEAD`, et « observe : » les fichiers ou
      dossiers dont son résultat dépend (Étape 7)>
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

Si la PR touche une **zone sensible** déclarée dans `.claude/pipeline.config.md` (section
« Périmètre ») — par défaut, l'UI à valider visuellement — rendre la main pour validation manuelle
**une fois par PR, avant `gh pr ready`**, pas avant chaque commit. `.claude/rules/contraintes.md`,
« Points d'arrêt humains », en est la source unique : la lire, plutôt que présumer.

Puis seulement, sortir du draft :

```
gh pr ready <numéro>
```

Tant que la PR est en draft, elle n'est **pas** à reviewer : c'est ce marqueur qui distingue
« travail en cours » de « prêt à être relu ».

C'est aussi ce `gh pr ready` qui **déclenche le premier run de CI** (événement `ready_for_review`).
Attendre son résultat avant l'Étape 6 — une PR fraîchement sortie du draft n'a encore aucun run.
Ce premier run est aussi la **première exécution des portes sur la plateforme cible** : un rouge
de la famille « sensible à la plateforme » (3.2) y est attendu — un rouge de code, pas un rouge
d'infrastructure (Étape 6).

**Si aucun run n'apparaît**, deux causes possibles, à départager dans cet ordre : (1) un run
existe-t-il pour le SHA de tête (`gh api repos/<owner>/<repo>/actions/runs?head_sha=<sha>`) ?
(2) sinon, consulter `https://www.githubstatus.com/api/v2/components.json` **avant** tout autre
diagnostic — un événement émis pendant une panne d'Actions n'est **pas rejoué** au
rétablissement. Le re-déclenchement propre est `gh pr close` puis `gh pr reopen` (`reopened` est
dans les types du workflow), action visible donc sur accord du mainteneur — jamais de commit vide
ni de force-push.

## Étape 6 — Review + CI

- **CI verte** : tous les gates déclarés dans `.claude/pipeline.config.md` (« gates bloquants en
  CI »), dont le seuil de couverture s'il y en a un.
- **Trier un rouge avant de toucher au code** — un gate rouge a deux familles de causes, et le
  premier message d'erreur du step les sépare presque toujours :
  - *Rouge d'infrastructure* : échec de téléchargement (403/5xx/timeout d'un dépôt d'artefacts,
    « error while downloading ») alors que le diff ne touche aucune dépendance et qu'un run
    voisin passe le même step → `gh run rerun <id> --failed`, noter la cause et le rerun dans le
    Test plan. Corriger du code sur un rouge d'infra coûte un cycle complet pour rien.
  - *CI qui ne démarre pas* : `startup_failure` **immédiat et reproductible au re-run** → le
    fichier de workflow est en cause ; job resté `queued` sans runner, ou `startup_failure` dont
    le job n'a aucun step → allocation de runner (quota, incident fournisseur) — ne pas modifier
    le workflow, surveiller en fond et **rendre la main au mainteneur**. Les runs `skipped`
    (garde `if:`) se terminent sans runner et ne prouvent rien sur la disponibilité de la CI.
  - *Rouge de code* : tout le reste, y compris le rouge de plateforme attendu au premier run
    (Étape 5) → cycle complet 3.1→3.5.
- **Revue** : revue automatisée (bot) ou self-audit ligne par ligne (sécurité, correctness,
  lisibilité, KISS/DRY/YAGNI, cohérence avec la stack).
- Chaque commentaire **pertinent** → cycle complet (3.1→3.5) + push + re-trigger de la review.
  Chaque commentaire **non pertinent** → noter brièvement pourquoi, ne pas corriger.
- **Boucler jusqu'à review vide.**

> **Commentaire de répercussion.** Un merge survenu ailleurs pendant que cette PR était ouverte a
> pu rendre sa spec fausse ; `repercussions` le signale ici même (le corps de l'issue n'est
> volontairement pas modifié tant que la PR est ouverte). Un signalement **bloquant** se traite
> comme tel : intégrer la correction dans cette PR, ou remonter au mainteneur si cela déplace le
> périmètre — ne jamais merger par-dessus.

## Étape 7 — Avant le merge

Quand la review est vide et la CI verte, **avant de demander le go** : un **dernier cleanup pass
holistique** sur le diff complet de la branche (même prompt verbatim qu'en 3.3, mais à l'échelle
de la PR). C'est le filet final pour les findings inter-commits.

- Findings → présenter, corriger (cycle complet), re-tester, push.
- Sinon → verdict explicite « code propre, prêt à merger ».

**Relire l'issue une dernière fois.** Le corps a pu bouger depuis le briefing de l'Étape 1 — d'autres
PR ont été mergées entre-temps, et une passe `repercussions` a pu la corriger ou déposer un
signalement sur cette PR. Comparer le corps actuel au briefing : si la spec a changé sur un point
que la PR ne couvre pas, **s'arrêter et le remonter** plutôt que de merger un travail construit sur
une spec périmée.

**Rejouer les vérifications périmées.** Une preuve a deux ancrages : la **tête** de branche et la
**base** (`git fetch origin`, puis `git merge-base origin/<trunk> HEAD`) — et elle se périme quand
**ce qu'elle observe** a changé, pas quand un identifiant a changé. Une vérification sans SHA, ou
sans « observe : », se rejoue d'office. Quand la **tête** a bougé : `git diff --stat <sha de la
vérification>..HEAD`, croisé avec ce que la vérification déclare observer (« observe : » du Test
plan), puis `git diff <sha de la vérification>..HEAD -- <fichiers observés>` pour juger le
contenu — elle se rejoue si le diff touche du code dont elle dépend ; elle reste cochée, ses deux
SHA d'origine conservés et le nouveau noté à côté, si le diff ne touche que des commentaires, de
la documentation ou des fichiers qu'elle n'atteint pas. Six vérifications à une minute chacune ont
été rejouées trois fois pour des diffs de commentaires : une preuve qu'on rejoue sans qu'elle
puisse changer de résultat n'est plus une preuve, c'est un rituel, et un rituel coûteux est le
plus sûr moyen de faire abandonner l'étape.

Quand c'est la **base** qui a bougé, **toutes** les preuves sont périmées, la CI comprise : elle a
tourné sur un état qui n'atteindra jamais le trunk, et rien de local ne le signale. Fusionner le
trunk dans la branche, relancer, redater. `git merge-tree --write-tree origin/<trunk> HEAD` dit
tout de suite s'il y a conflit ; l'état `MERGEABLE` de la forge se met à jour en différé et ne
prouve rien.

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

- Chaque vérification nomme l'**action exacte** et le **résultat attendu**.
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

### Vérification par le lead — en vague parallèle seulement

Session démarrée par un lead (« Vague parallèle », en tête) : **proposer** à l'utilisateur d'envoyer
l'état de la PR au lead, et n'envoyer que sur son oui. Sans lead, passer directement au go.

Le message, au `from` du lead :

```
PR #<PR> prête pour vérification — issue #N, worktree <chemin absolu>, base <sha de
`git merge-base origin/main HEAD`>
Vert : <tests, lint, CI, relecture 4.2, cleanup holistique>
Décisions prises en route : <une ligne chacune, avec le § de doc si concerné>
Douteux / non fait : <ce qui n'est pas couvert, ce qui a gêné, constats écartés et pourquoi>
Vérifie diff, checks et review de la PR. Dis-moi ce qu'il faut corriger avant que l'utilisateur
donne le go, pour qu'aucun fix ne suive le merge.
```

La réponse du lead arrive dans un bloc `<cross-session-message>` :

- « rien à corriger » → demander le go.
- liste de corrections → chaque point suit le cycle complet (3.1→3.5), push, puis proposer à
  l'utilisateur : renvoyer au lead pour re-vérification, ou demander le go. Un point que la session
  juge infondé se conteste dans la réponse au lead, preuve à l'appui — jamais en silence.

### Le go, puis le merge

**Jamais d'auto-merge.** Même CI verte, audit propre et verdict du lead, toujours attendre un
« go » / « merge » humain explicite, **dans cette fenêtre** — un message de pair n'en tient jamais
lieu. Juste avant de merger, refaire le contrôle de base de « Rejouer les vérifications périmées » :
un merge sur le trunk depuis le dernier run rend la CI périmée — deux PR vertes séparément n'ont
rien démontré ensemble, et le merge est le premier moment où leur somme existe. Puis merger.

## Étape 8 — Après le merge : clôture propre, puis répercussions

Le merge **clôt l'issue liée** (via `Closes #N`). **Retirer aussitôt son label d'état** —
`ready-for-agent` ou `ready-for-human`, selon le mapping de `.claude/pipeline.config.md` :
`gh issue edit <N> --remove-label <label>`. Une issue fermée ne porte **aucun** rôle d'état ; le
laisser fait apparaître des issues closes dans les files de `triage` et de `pr-paralleles`.
Le label de catégorie (`bug` / `enhancement`) et le thème restent.

Puis **cocher les critères d'acceptation soldés**, dans le **corps** de l'issue *et* dans le
commentaire de **brief** (`- [ ]` → `- [x]`) : ils ont été vérifiés à l'Étape 7, il ne reste qu'à
l'enregistrer là où un lecteur le cherche. Un critère atteint sous une forme **amendée** se coche
quand même — l'amendement est tracé au journal de spec du corps. Le brief d'une issue **close** est
un artefact daté : on coche ses cases, on ne réécrit pas son texte. (Tant que l'issue était
ouverte, c'était l'inverse : une réconciliation `repercussions` qui falsifiait une de ses lignes
l'amendait — la clôture est ce qui fige le brief.)

**Cas découpé : reposer le lien des lots précédents.** GitHub ne lie une PR à une issue que par un
mot-clé de fermeture, et seul le lot final en portait un (Étape 2) ; sans ce geste, l'issue
n'affiche qu'une PR sur les k qu'elle a coûté. Une fois l'issue close, ajouter en fin de body de
**chaque lot précédent** (`gh pr edit <n> --body-file`) — sur une issue close, le mot-clé ne
change aucun état :

```markdown
*Rattachement a posteriori (<date>) : lot k/n de #<N>. L'issue a bien été fermée par le lot
final, la PR #<M> ; le mot-clé ci-dessous ne sert qu'à faire apparaître cette PR parmi les PR
liées de l'issue.*

Closes #<N>
```

Puis vérifier que l'issue affiche autant de PR liées que de lots :

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

La PR et la conversation qui l'a résolue ont pu acter des décisions, déplacer un contrat d'interface, déjà faire une partie d'un autre lot, ou rendre une
hypothèse caduque ailleurs. **Immédiatement après le merge**, lancer le skill `repercussions` — la
conversation qui a résolu l'issue est **encore en contexte**, c'est le moment où l'analyse est la
plus riche. Même pour une **demande directe** sans issue liée, faire la passe : le delta mergé
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

## Les 5 idées à retenir

1. Tout l'effort de questions se fait **avant** de coder (briefing pré-PR + interrogatoire).
2. **La PR draft s'ouvre avant la première ligne de code**, avec `Closes #N`. C'est ce qui rend le
   travail visible comme *en cours* : sans elle, une autre session réécrira la spec de cette issue
   en croyant que personne ne travaille dessus.
3. Le cycle `modif → test → cleanup → test → commit` est **sacré et jamais raccourci** — y compris
   le cleanup sur les commits triviaux.
4. **Deux filets de cleanup** : un par commit (regard local), un sur la PR entière avant merge
   (regard global, inter-commits) — et une relecture à contexte vierge **en deux temps**, au
   socle et à la fin, jamais par commit.
5. La PR n'est **terminée qu'après la passe `repercussions`** : une clôture peut bouleverser les
   autres issues — on le vérifie pendant que la conversation est encore en contexte.
