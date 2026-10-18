# Pipeline de développement

Ce projet suit une pipeline de dev pilotée par les issues. Le cycle de réalisation d'une PR est
décrit dans [CONTRIBUTING.md](CONTRIBUTING.md) et exécutable via le skill `cycle-pr`.

## Règles permanentes (toujours actives)

Les fichiers de `.claude/rules/` — sans frontmatter `paths:`, qui les rendrait conditionnels — sont
chargés à chaque session, au même rang que ce fichier :
`contraintes.md`, `taille-pr.md`, `cleanup-verbatim.md`, `decisions-vs-doc.md`.

## Configuration du projet

`.claude/pipeline.config.md` est la **source unique** pour : le dépôt GitHub, le mapping de labels,
la stack, les **commandes du projet** (test / lint / format / typecheck / build), les seuils de
qualité, les **sources de vérité**, les **domaines**, les **zones sensibles** et les **surfaces
exposées**. Ne jamais deviner une commande ni un label — les lire là. Pour créer ou modifier ce
fichier : skill `init-projet`.

Les **sources de vérité** (documents de référence, puis les issues ouvertes) y sont classées par
**rang de normativité**. C'est cette table que lisent la règle `decisions-vs-doc` et le skill
`contradiction` : une décision qui contredit un rang s'arrête, et soit elle est abandonnée — ou
son effet déplacé hors de ce que le document affirme —, soit le document est amendé dans la même
session.

Les **domaines** servent aussi de thèmes (milestones GitHub). Les **surfaces visibles par un
utilisateur** déclenchent la vérif de fumée avant merge et la proposition de campagne QA en fin de
thème — si ce champ est vide, ces deux propositions ne se déclenchent jamais.

## Vocabulaire

Utiliser le glossaire de domaine du projet (`UBIQUITOUS_LANGUAGE.md` s'il existe) dans les
noms de tests, les titres d'issues et de PR. Respecter les ADR de la zone touchée.

## Documentation des bibliothèques

Pour toute question sur une lib/framework de la stack (API, config, migration de version),
**utiliser en priorité le serveur MCP `context7`** plutôt que la mémoire ou une recherche web :
il renvoie la doc à jour de la lib demandée, ce qui économise des tokens et évite les réponses
périmées. Installé par `init-projet` (`claude mcp list` pour vérifier).

## Minimalisme (`ponytail`)

Invoquer le skill `ponytail` **avant d'écrire du code** — écriture, ajout, refactor, correctif,
choix d'une dépendance ou d'une lib. Sa description seule ne suffit pas à le déclencher de façon
fiable : c'est cette ligne qui l'active. Aligné sur la doctrine KISS/DRY/YAGNI de
`.claude/rules/contraintes.md`.

Niveau par défaut : `full`. Se change par `/ponytail lite|full|ultra` et persiste jusqu'à la fin
de la session. Ponctuellement : `/ponytail-review` (relecture anti-sur-ingénierie d'un diff),
`/ponytail-audit` (dépôt entier), `/ponytail-debt` (raccourcis marqués `ponytail:` à reprendre).

**Ce qu'il ne simplifie jamais** : validation aux frontières de confiance, gestion d'erreurs qui
évite une perte de données, sécurité, accessibilité, et tout ce qui est explicitement demandé.
Il raccourcit la solution, jamais la lecture : tracer le flux complet avant de choisir un barreau.

`ponytail` gouverne **ce qu'on construit** ; `.claude/rules/cleanup-verbatim.md` gouverne **la
relecture de ce qui a été construit**. Les deux s'appliquent, à des moments différents — ponytail
en amont de l'écriture, le prompt de relecture après. L'un ne dispense pas de l'autre.

## Observation continue (`task-observer`)

Invoquer le skill `task-observer` au début d'une session **longue ou structurée** — un cycle de PR,
un audit, une passe de spec. Pas pour une question, une commande isolée ou un correctif court.

**Seuil de consignation — haut.** Ne consigner que ce qui changerait le comportement d'un skill :
une règle violée de façon répétée, une correction de l'utilisateur qui se généralise, un manque
rencontré sur plusieurs sessions. Une friction isolée ne se consigne pas. **Maximum 3 entrées par
cycle** — une PR, relais compris, la passation de relais portant le compte déjà écrit ; hors PR,
une session. Au-delà, ne garder que les plus fortes.

**Ne jamais interrompre pour le journal.** Pas de proposition de revue spontanée, pas de résumé
d'observations en fin de session, pas de relance sur le retard de revue. Le journal ne se surface
que si l'utilisateur le demande explicitement.

Au chargement de **n'importe quel skill**, consulter le journal d'observations pour les entrées
OPEN rattachées à ce skill et en appliquer les enseignements au travail en cours — même si le
fichier du skill n'a pas encore été mis à jour.

**Emplacement du journal, à ne pas laisser deviner :** `C:\Users\pacom\.claude\projects\e--Projets-Portfolio\skill-observations\log.md`. C'est un
chemin **stable**, hors du dépôt. Ne jamais l'ancrer sur le répertoire courant : `pr-paralleles`
travaille dans des **git worktrees** éphémères, et un journal écrit là disparaît avec le worktree.

## Orchestration — équipiers par rôle

La session principale est le **lead**. Elle garde ce qui demande le plus de jugement : briefing,
planification, arbitrages `decisions-vs-doc`, cleanup pass, review avant merge, dialogue avec
l'utilisateur. Le reste se délègue à des équipiers définis dans `.claude/agents/` — **le modèle
n'est pas choisi par tâche, il est choisi par rôle** au moment de créer l'équipier :

| Rôle | Modèle | Confier |
|---|---|---|
| `developpeur` | Opus | l'implémentation TDD d'un brief borné, la correction de tests rouges |
| `relecteur` | Opus, effort `medium` | la relecture à contexte vierge d'un diff (`cycle-pr` 4.2), seul, dans son propre worktree |
| `executant` | Sonnet, effort `max` | tests / lint / format, exploration et cartographie du code, edits entièrement spécifiés, codage d'une tranche entièrement spécifiée |
| `verificateur` | Opus, effort `medium` | la vérification d'avant-go d'une PR (`pr-paralleles` Étape 6), **éphémère, un par (PR, go)**, sans worktree et sans lancer de commande du projet |

**Ce qui rend un rôle éligible au modèle le moins cher : un mandat sans aucune décision** — pas
une tâche qui paraît facile. Le mandat (ce que le rôle peut trancher) et l'effort (la profondeur
de réflexion) sont deux axes : un rôle sans décision peut porter un effort élevé, qui paie alors
de la vérification et non de l'architecture. Déléguer à un tel rôle suppose que le lead ait écrit
la tranche entièrement — fichiers, signatures, tests attendus, comportement — avant l'envoi : si
la spécifier demande encore de réfléchir, c'est le travail du lead. Chaque rôle dit en tête de
son fichier s'il tranche.

L'effort d'un rôle se fixe dans son frontmatter (`effort`) ; celui de la session, par `/effort`.

**Une commande ponctuelle se lance soi-même.** Un équipier démarre avec un contexte complet ; le
déléguer coûte plus qu'un `git status` ou un test isolé. La délégation ne paie que pour un **bloc
de travail** : une tranche d'issue, une suite à faire passer au vert, une cartographie.

Un rôle ajouté ou modifié dans `.claude/agents/` n'est visible qu'à la session suivante (la liste
des types est figée au démarrage — repli : `general-purpose` avec le modèle du rôle).

**Sessions liées.** Les équipiers ci-dessus sont des sous-agents d'une session. Une session peut
aussi en démarrer d'autres, complètes, dans l'application de bureau (`start_session`) : le lead
d'une vague `pr-paralleles`, une par issue ; la coordinatrice d'une issue en lots, une par lot.
Leur protocole — héritage, identité, premier geste, messages, fin de travail, passation,
nettoyage — vit dans `.claude/skills/cycle-pr/references/sessions-liees.md`, seule source.

## Skills de la pipeline

Chaque skill s'invoque par `/<nom>` (`/triage`, `/cycle-pr`, `/plan-qa`…) ou se déclenche
automatiquement sur sa description.

| Commande | Rôle |
|---|---|
| `/init-projet` | Setup et reconfiguration de la pipeline |
| `/vers-prd` | Conversation → PRD |
| `/vers-issues` | PRD/plan → issues |
| `/triage` | Machine à états + thèmes + brief d'agent |
| `/interroge-moi` | Lever les ambiguïtés d'un plan |
| `/cycle-pr` | Cycle complet d'une PR (TDD → merge) |
| `/contradiction` | Une décision contredit la doc → amende le document, puis propage |
| `/repercussions` | Impact d'un merge sur les sources de vérité (→ `contradiction`), puis sur les issues ouvertes |
| `/pr-paralleles` | Plusieurs PR en parallèle (worktrees) |
| `/plan-qa` | Écrire un plan de QA |
| `/execution-qa` | Dérouler le plan de QA |
| `/bug-vers-issue` | Consigner un bug en issue |
| `/audit-spec-ui` | Audit mécanique d'une spec d'interface ou d'un document normatif |
