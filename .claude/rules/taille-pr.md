# Règle — Taille et format des PR

## Découpage
- **Une PR = une unité de travail cohérente et reviewable.**
- Au-delà de **~10 fichiers** ou **~500 lignes de diff**, découper la PR.

## Format des messages
- **Commits et titre de PR** au format conventional commit : `type(scope): description`.
  - Types : `feat` `fix` `chore` `docs` `refactor` `test` `ci`.
  - **Préfixe en anglais, description en français.** Ex : `feat(auth): ajoute la connexion par e-mail`.
  - Breaking change : `!` dans le titre (`feat!: …`), pas de footer.
- Message de commit = **titre seul**. Pas de corps, pas de footer, pas de `Co-Authored-By`,
  pas de préfixe de phase ni de numéro de PR (traçables via l'outil de suivi).
- **Exception : les commits et PR de Dependabot.** Seul le préfixe conventional est tenu
  (`chore(deps)`, `chore(deps-dev)`, réglé dans `.github/dependabot.yml`) ; la description en
  anglais et le corps viennent du bot, qui ne sait pas les écrire autrement. Même exemption que
  pour les métadonnées de PR (`.claude/pipeline.config.md`, « Métadonnées d'une PR »).

## Branches
- Trunk-based depuis `main` : `git checkout -b <type>/<description>`.
