# Règle — Taille et format des PR

## Découpage
- **Une PR = une unité de travail cohérente et reviewable.**
- Au-delà de **~10 fichiers** ou **~500 lignes de diff**, découper la PR.
- **Ne jamais raboter la qualité pour tenir dans le gabarit.** Si le bon choix technique dépasse
  ces bornes, découper en lots (`cycle-pr`, cas découpé) — pas rogner la solution.
- **Le gabarit se re-mesure à chaque commit** (`git diff --stat main...HEAD`, `cycle-pr` 3.5), pas
  à la fin. Le `developpeur` rend le chiffre avec chaque commit et s'arrête au seuil que porte son
  brief ; la session PR le relit contre les deux seuils. Deux seuils, deux effets : l'**absolu**
  ci-dessus mesure la relisabilité et **découpe** ; le **double de l'estimation du briefing**
  mesure que le plan était faux et **rouvre** le découpage — un lot de plus, ou une ligne qui
  nomme ce qui, dans le bon choix technique, impose le dépassement ; jamais la seule déclaration
  du chiffre.
- **Un découpage déjà décidé borne le périmètre d'un lot, pas son volume** : « un lot = une PR »
  n'autorise pas un lot à doubler son estimation — il se re-découpe comme une PR, en sous-lots.
- **Le seuil relatif vaut ce que vaut l'estimation** : elle se compte en épingles, pas en lignes
  de prose (`cycle-pr` Étape 1, « Estimation »).

## Format des messages
- **Commits et titre de PR** au format conventional commit : `type(scope): description`.
  - Types : `feat` `fix` `chore` `docs` `refactor` `test` `ci`.
  - **Préfixe en anglais, description en français.** Ex : `feat(auth): ajoute la connexion par e-mail`.
  - Breaking change : `!` dans le titre (`feat!: …`), pas de footer.
- Message de commit = **titre seul**. Pas de corps, pas de footer, pas de `Co-Authored-By`,
  pas de préfixe de phase ni de numéro de PR (traçables via l'outil de suivi).
- **Aucune ligne d'attribution**, ni `Co-Authored-By` dans un commit ni pied « Generated with … »
  dans un body de PR : `attribution.commit` et `attribution.pr` valent `""` dans
  `.claude/settings.json`.
- **Exception : les commits et PR d'un bot de dépendances** (Dependabot, Renovate…). Seul le
  préfixe conventional est tenu, réglé dans la configuration du bot (`chore(deps)`,
  `chore(deps-dev)`) ; la description et le corps viennent du bot — en anglais pour Dependabot,
  qui ne sait pas les écrire autrement. Même exemption que pour les métadonnées de PR
  (`.claude/pipeline.config.md`, « Métadonnées d'une PR »).
- **Refuser une PR de bot sans laisser d'état hors du dépôt.** Jamais de fermeture à la main ni
  de commande `@dependabot ignore …` : l'une et l'autre mémorisent un refus côté forge, invisible,
  et la seconde bloque aussi les mises à jour de sécurité. Le refus s'écrit en règle `ignore` du
  fichier de configuration du bot — raison et condition de réexamen en commentaire, liste figée
  par un test — et un second test lit la cause du refus là où elle vit (verrou, plage de pairs)
  avec l'analyseur de l'écosystème, puis rougit le jour où elle tombe, vu rouge par mutation. Le
  bot ferme ses PR de lui-même au push de la configuration : le constater, puis commenter chacune
  en citant le commit. Exemple en place : `docs/frontend-outillage.md` §2.4 (obs 31).

## Branches
- Trunk-based depuis `main` : `git checkout -b <type>/<description>`, **derrière la porte de
  fraîcheur** de `cycle-pr` Étape 1, qui chaîne deux prédicats `git merge-base --is-ancestor` (une
  par direction) à la création. La commande nue crée la branche sur le `main` qu'elle trouve, à
  jour ou non.
- Une session démarrée par une autre, dans un worktree de l'application, crée la sienne par le
  premier geste de `.claude/skills/cycle-pr/references/sessions-liees.md`, depuis le distant : la
  porte vaut pour une branche créée sur `main`.
