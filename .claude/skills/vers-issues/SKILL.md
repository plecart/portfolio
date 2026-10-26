---
name: vers-issues
description: Découpe un PRD ou un plan publié, passé en argument, en issues indépendamment récupérables sur GitHub en utilisant des tranches verticales tracer-bullet. À utiliser quand l'utilisateur veut convertir un plan en issues, créer des tickets d'implémentation, ou découper le travail en issues.
argument-hint: "[#issue-prd | chemin/vers/plan.md]"
---

# Vers Issues

Découpe un plan en issues indépendamment récupérables en utilisant des tranches verticales (tracer bullets).

Le dépôt GitHub et le mapping de labels sont dans `.claude/pipeline.config.md` — sinon s'arrêter et proposer une session `init-projet` distincte (`init-projet`, « Note pour les autres skills »).

## Délégation

La session garde le découpage, le dialogue de l'étape 4 et la rédaction des corps. Le reste change de main :

- **`releveur`** — la lecture de la source (corps, et commentaires filtrés par les critères que la session donne) et du code autour des ancres données (« Lectures bornées »), les dénombrements par commande donnée (« Collectes »), la publication en série (étape 5), et une capacité de fournisseur par `context7` (« Questions de documentation ») ; une doc absente de l'index, ou plusieurs candidates, remonte à la session, qui la lit à la source ;
- **script** — `issue create`, `issue edit`, `milestone attach`, par `python .claude/skills/cycle-pr/scripts/ecriture-relue.py <sous-commande> …`, qui relit ce qu'il écrit.

Une session démarrée par une autre — par `vers-prd` — suit le protocole commun de `.claude/skills/cycle-pr/references/sessions-liees.md`, message de fin « terminé — \<livrable> » compris.

## Processus

### 1. Rassembler le contexte

Le découpage part d'une source écrite : la source se passe en argument — `#issue-prd` ou son URL, dont un `releveur` rend le corps et les commentaires tels quels, filtrés par les critères que la session donne (« Lectures bornées »), ou le chemin d'un plan écrit, que la session lit. Un résidu de cycle sans PRD (`contraintes.md`, « Création d'issues en cours de cycle », barreau 3) s'écrit d'abord dans un fichier de plan, passé par son chemin. Sans argument, la session s'arrête et demande la référence.

### 2. Explorer la base de code (optionnel)

Si la base de code n'a pas encore été explorée, un `releveur` l'explore sur les ancres que la session lui donne, pour l'état actuel du code. Les titres et descriptions d'issues doivent utiliser le vocabulaire du glossaire métier du projet, et respecter les ADR de la zone que tu touches.

### 3. Esquisser les tranches verticales

Découpe le plan en issues **tracer bullet**. Chaque issue est une fine tranche verticale qui traverse TOUTES les couches d'intégration de bout en bout, et NON une tranche horizontale d'une seule couche.

Les tranches peuvent être 'HITL' ou 'AFK'. Les tranches HITL nécessitent une interaction humaine, par exemple une décision d'architecture ou une revue de design. Les tranches AFK peuvent être implémentées et mergées sans interaction humaine. Préfère AFK à HITL lorsque c'est possible.

<vertical-slice-rules>
- Chaque tranche livre un chemin étroit mais COMPLET à travers chaque couche (schéma, API, UI, tests)
- Une tranche terminée est démontrable ou vérifiable à elle seule
- Préfère de nombreuses tranches fines à quelques tranches épaisses
- Chaque élément visible qu'une tranche ajoute à un écran nomme le comportement — de cette tranche ou d'une tranche déjà livrée — qui le fait changer ; un élément dont le seul comportement arrive avec une autre tranche va dans celle-ci, en critère, et la tranche courante n'en pose que la donnée (obs 65)
</vertical-slice-rules>

**Ne jamais découper une tranche pour la seule taille de PR** quand ses morceaux se valident ensemble — même écran, même point d'arrêt visuel, même ADR : les séparer fait valider deux fois le même écran, ou un demi-écran. La règle de taille (`taille-pr.md`) est une règle de PR, pas de découpage fonctionnel : la tranche reste **une** issue, et si elle dépasse la taille de référence, `cycle-pr` la livre en plusieurs PR (son « cas découpé », Étape 2) — les lots d'une même issue, ci-dessous.

**Un dépassement prévisible se découpe dès la création** (obs 120). Quand une tranche dépasse de façon prévisible le gabarit de `taille-pr.md` — fichiers et lignes estimables par critère (`cycle-pr` Étape 1, « Estimation ») —, l'issue porte ses lots dès sa création, un bloc chacun, et un lot qui dépasse lui-même le gabarit porte ses sous-lots de même : un sous-lot est un lot (`cycle-pr` 3.5). Le re-découpage au briefing reste la voie d'un dépassement découvert, jamais d'un dépassement prévisible.

### 4. Interroger l'utilisateur

Présente le découpage proposé sous forme de liste numérotée. Pour chaque tranche, montre :

- **Titre** : nom court et descriptif
- **Type** : HITL / AFK
- **Bloquée par** : quelles autres tranches (le cas échéant) doivent être terminées d'abord
- **User stories couvertes** : quelles user stories cette tranche adresse (si le matériel source en contient)

Demande à l'utilisateur :

- Quelles tranches ont été séparées pour la seule taille de PR, et se valident-elles ensemble ? (si oui, les refusionner)
- Les relations de dépendance sont-elles correctes ?
- Faut-il fusionner ou découper davantage certaines tranches ?
- Les bonnes tranches sont-elles marquées comme HITL et AFK ?

Itère jusqu'à ce que l'utilisateur approuve le découpage.

### 5. Publier les issues sur GitHub

Pour chaque tranche approuvée, la session écrit le corps de l'issue dans un fichier, d'après le template ci-dessous, marqueurs `{{T<k>}}` compris. Chaque issue entre dans le flux de triage normal sous le label `needs-triage` du mapping.

**Rattache chaque issue à son thème** quand le domaine est évident : le découpage vient d'un plan, tu sais donc de quel domaine relève chaque tranche. Utilise les **domaines** de `.claude/pipeline.config.md` et le milestone homonyme, décrit par le périmètre du domaine — voir `triage/themes-milestones.md`. Si aucun domaine ne couvre une tranche, laisse le thème vide et signale-le : c'est soit du hors-périmètre, soit un domaine manquant dans la config. Rattacher ici évite à `triage` de le refaire issue par issue.

Les issues se publient dans l'ordre des dépendances (bloqueurs d'abord) afin de pouvoir référencer les identifiants d'issues réels dans le champ « Bloquée par ».

**Cet ordre ne résout pas les références croisées hors « Bloquée par ».** Les corps se citent aussi entre eux (« le contrat est fixé avec la tranche X », « s'applique aussi à Y »), dans les deux sens : un ordre topologique sur les seuls bloqueurs laisse forcément des références « en avant » sans numéro. D'où les **marqueurs symboliques** (`{{T3}}`) des corps, et une publication en deux passes suivie d'une **vérification mécanique** — l'ordre de création seul donne une fausse impression de complétude.

**La publication en série part à un `releveur`.** Il reçoit la table ordonnée — fichier, titre, label `needs-triage` du mapping, thème et description du domaine — et, par l'écriture relue (« Délégation ») :

1. publie dans l'ordre des bloqueurs par `issue create --title <titre> --body-file <fichier> --label <label>`, dont la sortie porte le numéro, substitue dans les fichiers suivants les marqueurs dont le numéro est connu, et rattache chaque issue qui a un thème par `milestone attach <N> --title <Domaine> --description <périmètre>` ;
2. seconde passe, une fois tous les numéros attribués : `issue edit <N> --body-file <fichier>` sur chaque issue dont un marqueur restait ;
3. relit chaque corps publié et compte les `{{` — 0 attendu.

Il rend la table marqueur → numéro et ce décompte.

**Critères reposant sur un service tiers.** Quand un critère d'acceptation suppose une capacité d'un fournisseur (restriction d'usage, plafond, quota, révocation, rotation), ne jamais la recopier d'un document du projet sans l'avoir vérifiée à la source — un `releveur` par `context7`, la session à défaut (« Délégation ») : ajouter la ligne « vérifié à la source le <date> : <doc du fournisseur> », ou marquer le critère « ⛔ à vérifier avant engagement ». Une contre-mesure copiée sans vérification survit à tous les rangs de doc et n'éclate qu'au moment le plus coûteux — la console ouverte.

**Une issue qui pose une infrastructure de test porte sa barre.** Un harnais (conteneurs jetables, greffon de réglages, fabriques) attire les tests de ses propres tests : sans barre écrite, le harnais grossit plus vite que la fonctionnalité qu'il sert. La barre par défaut, à inscrire dans ses critères : (1) sans le service, la suite échoue en disant pourquoi, en une ligne ; (2) réglages et image viennent du dépôt, jamais du shell, tenus par un seul garde ; (3) un test de fumée démarre le service et exécute une requête. Tout le reste — sessions de test imbriquées, épinglage par empreinte sans incident, tests des gardes — est hors barre tant qu'un défaut réel ne l'a pas demandé. Et un socle de test est une tranche à part, jamais fondue dans la première fonctionnalité qui en a besoin.

**Un critère chiffré, ou qui décrit une sortie, suit « Critères d'acceptation complets » de `triage/brief-agent.md`** : un dénombrement porte sa population et la commande qui la recense ; une sortie, sa valeur attendue sur une entrée nommée. Écrit ici pour la première fois, un chiffre sans population se recopie dans chaque issue, ou chaque lot, qui en dérive (obs 68, 72).

<issue-template>
## Parent

Une référence à l'issue parente sur GitHub (si la source était une issue existante, sinon omettre cette section).

## Quoi construire

Une description concise de cette tranche verticale. Décris le comportement de bout en bout, pas l'implémentation couche par couche.

## Critères d'acceptation

- [ ] Critère 1
- [ ] Critère 2
- [ ] Critère 3

## Bloquée par

- Une référence au ticket bloquant (le cas échéant)

Ou « Aucun - peut démarrer immédiatement » s'il n'y a aucun bloqueur.

</issue-template>

Ne ferme NI ne modifie aucune issue parente.
