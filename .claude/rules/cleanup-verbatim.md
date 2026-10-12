# Règle — Le prompt de relecture (cleanup pass)

**Dès que le travail demande de relire, nettoyer ou améliorer du code**, exécuter **ce prompt mot
pour mot**. Ne jamais le paraphraser, ne jamais le raccourcir, ne jamais le recopier ailleurs.

Cela couvre aussi bien les étapes de la pipeline (cycle de commit, cleanup holistique de PR,
refactor TDD, relecture indépendante) qu'une **demande directe et informelle** de l'utilisateur — « relis ça »,
« nettoie ce fichier », « améliore ce code », « tu peux revoir ce que tu viens d'écrire ? ».
Il n'y a pas de relecture « informelle » qui échapperait à ce prompt : s'il s'agit de repasser sur
du code, c'est ce prompt qui s'applique.

**Relire un document normatif** (spec UX/UI, cadrage, PRD) n'est **pas** ce prompt : c'est le
skill `audit-spec-ui` — passes mécaniques (jetons, tables, arithmétique, contraste, cohérence)
avant tout jugement, chaque finding cité par §.

> Veuillez examiner l'ensemble du code ajouté et des modifications apportées aux fichiers
> existants. Réorganisez, structurez, optimisez et nettoyez ces modifications pour produire un
> code clair, cohérent et facilement maintenable. Éliminez tout code dupliqué, inutile ou
> obsolète. Décomposez les fonctions et séparez les responsabilités en suivant les principes
> KISS, DRY et YAGNI. Rendez le code le plus **générique et modulaire** possible : des unités à
> responsabilité unique, découplées de leur contexte d'appel, réutilisables telles quelles, et
> conçues pour que l'ajout d'un cas se fasse par extension plutôt que par modification — sans
> pour autant anticiper un besoin non avéré. L'objectif est d'obtenir un code propre, clair,
> concis, générique, modulaire et optimisé.

## Comment l'appliquer

- **Examen fichier par fichier**, pas un regard global vague. Pour chaque fichier modifié, lister
  les findings concrets : magic numbers, duplication, naming douteux, fonction trop longue,
  responsabilité mal séparée, code mort.
- **Rapporter à voix haute** sous un titre `## 🧹 Cleanup pass`, pour que le relecteur vérifie
  d'un coup d'œil que l'étape n'a pas été sautée.
- **Même rigueur sur les deltas triviaux.** Si « rien à corriger », dire ce qui a été repassé —
  fichiers, points contrôlés, dénombrement — en quelques lignes, pas ligne par ligne : la preuve
  est dans ce qui a été vérifié, pas dans la longueur du compte rendu.
- **Un constat qui décrit une classe de défaut se traite en balayant toute la population
  concernée**, jamais les seules occurrences citées — un constat de relecture est un échantillon,
  pas un inventaire. Le rapport énonce le dénombrement (« N éléments repassés, k corrigés, N−k
  vérifiés indemnes »), pas « les 2 constats sont corrigés ». Quand la classe est reconnue,
  inscrire le critère dans l'artefact lui-même pour qu'il tienne sans relecteur.
- **La population d'un constat sur une étape, une section ou une liste numérotée inclut ses
  renvois entrants.** Quand l'édition change ce qu'une étape exige, `grep` son nom (« Étape N »,
  titre de section) dans `.claude/` (skills, rules, `pipeline.config.md`), `CLAUDE.md`,
  `CONTRIBUTING.md` et `.github/`, puis vérifier
  pour chaque hit que la cible dit bien ce que le renvoi lui prête — une paraphrase paraît à jour
  en ayant perdu la moitié du contenu.
- **Un correctif qui ferme un chemin se déclare clos sur une classe, jamais sur l'occurrence qui
  l'a révélée.** Le déclencheur est la **structure** du défaut — N chemins vers un même état —,
  jamais son sujet : fuite d'une donnée, voie par laquelle un état arrive ou sort (chargement,
  cache, signal, écriture partielle), cas d'un dispatch, **frontière d'entrée écrite à la main**.
  Cette liste est ouverte à dessein : une règle qui se re-formule à chaque domaine ne se
  déclenche jamais sur le suivant, et c'est ainsi que celle-ci est passée à côté d'une détection
  d'état parce qu'elle était écrite pour la sécurité, puis à côté de cinq défauts de validation
  d'entrée découverts un par un sur trois relectures. Conséquence directe : quand un delta
  introduit un **format saisi par un humain** — fichier de configuration, JSON de paramétrage,
  argument de ligne de commande —, tous ses champs se balayent pour le type et la présence en
  **une** passe, pas au fil des constats.

  « La seule voie », « le seul cas », « le dernier endroit » sont interdits tant qu'un
  **dénombrement** ne les accompagne pas — N formes recensées, k fuyaient — écrit **avant le
  premier correctif** et épinglé dans l'artefact par un test paramétré, pas par une phrase de
  docstring : la preuve que le chemin connu est fermé se lit spontanément comme la preuve qu'il
  n'y en avait qu'un. Écrit après, le dénombrement se fait par morceaux, un correctif par
  relecture.
- **Passe « affirmations » — ce que le delta dit de lui-même.** Le prompt ci-dessus fait relire le
  **code** : duplication, naming, responsabilités. Il ne fait jamais relire les **affirmations
  attachées au code**, et c'est là que l'angle mort de l'auteur est maximal — une affirmation est
  précisément ce qu'on ne re-dérive pas une fois écrite. Mesuré : au lot 1 de #77, quatre
  bloquants, **zéro** trouvé par le cleanup de commit ni par le cleanup holistique (un seul
  constat sur 2923 lignes), et les quatre portaient sur une affirmation.

  La passe est **mécanique et dénombrable**, dans l'esprit des passes d'`audit-spec-ui` :
  énumérer chaque assertion que le delta fait sur lui-même — propriété annoncée dans un
  docstring, commentaire « mesuré », ligne de `pipeline.config.md`, case de Test plan, message
  d'assertion — puis, pour chacune, **nommer la commande qui l'établit**, ou la marquer « non
  vérifiée ». Rendre le dénombrement : N affirmations, k établies par une commande citée, N−k non
  vérifiées. Les messages d'assertion se comptent par analyse syntaxique (`ast`), jamais par
  expression régulière : une regex qui franchit les lignes a rendu deux dénombrements faux avant
  le bon.

  **Une exception, mesurée** : une **chronométrie** n'a pas de commande qui l'établisse — quatre
  bornes publiées, quatre dépassées au relevé suivant. Pour une grandeur que le poste et le
  nombre de runs font varier, l'**ordre de grandeur est la mesure**, et c'est l'invariant sous
  test qui rougit, jamais le relevé. La forme « population + commande » vaut pour une population
  **figée par un commit**, pas pour un temps.
- **Vérifier aussi les 3 axes de conception** de `.claude/rules/contraintes.md` (modulaire /
  fractionné / scalable), en plus de KISS / DRY / YAGNI.
- **Relancer les tests après le cleanup** : il a pu casser quelque chose.
