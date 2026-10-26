# Patcher les cases dans le corps d'une issue GitHub

Comment `execution-qa` met à jour l'issue du plan de QA sans perdre les éditions de l'utilisateur. L'état du plan est la forge : ni copie locale du corps, ni paire gardée hors d'un fichier — chaque mise à jour est un fichier de paires que `ecriture-relue.py` applique au corps courant, puis relit.

## Règle fondamentale

**Faire correspondre par texte de ligne exact, pas par index. Faire remonter un avertissement si la ligne que tu comptais mettre à jour a changé.** Le script lit le corps courant au moment d'écrire : aucune lecture à refaire avant le patch.

## Procédure

### 1. Écrire le fichier de paires

Pour chaque case à mettre à jour, une paire `(ancienne_ligne, nouvelle_ligne)` : une ligne `< <ancienne>`, puis une ligne `> <nouvelle>`, dans un fichier UTF-8. Exemple :

```text
< - [ ] L'utilisateur A liste ses propres ressources
> - [x] L'utilisateur A liste ses propres ressources — 200, 3 lignes, 2026-05-08
```

L'ancienne ligne se copie de la lecture du bloc que la session a faite elle-même (`SKILL.md` §2). Le format exact, ses refus et son rejeu sont le contrat du script — `python .claude/skills/cycle-pr/scripts/ecriture-relue.py --help` —, qu'on ne recopie pas ici.

### 2. Correspondance par ligne complète

Appliquer la substitution par **correspondance exacte de ligne complète**. Ne jamais faire correspondre par numéro de ligne. Ne jamais faire correspondre par préfixe seul — un préfixe `- [ ]` n'est pas unique.

### 3. Détecter les éditions concurrentes

Pour chaque paire, dans le corps courant :

- Si l'`ancienne_ligne` est trouvée exactement une fois → appliquer.
- Si trouvée zéro fois → l'utilisateur (ou un autre agent) a édité cette ligne. **S'arrêter et faire remonter un avertissement** à l'utilisateur avec l'`ancienne_ligne` originale et la ligne la plus ressemblante actuellement dans le corps. Demander s'il faut sauter cette mise à jour, forcer une version au mieux, ou abandonner.
- Si trouvée plus d'une fois → le corps a des lignes de case en double (ce que le gabarit de plan devrait empêcher, mais défends-toi quand même). S'arrêter et faire remonter un avertissement. Demander à l'utilisateur de désambiguïser avant de continuer.

Le script tient ces règles : il valide toutes les paires avant la première écriture, et refuse sans rien écrire en nommant la ligne la plus proche, ou le double.

### 4. Appliquer

```bash
python .claude/skills/cycle-pr/scripts/ecriture-relue.py checkbox patch <plan> --paires <fichier>
```

Appelé par la session elle-même. Un refus (§3) ou une relecture non conforme : s'arrêter et le dire au mainteneur.

### 5. Cadence

Patcher à la fin d'une phase ou d'un bloc par issue (ou à la fin d'un sous-groupe significatif au sein d'un bloc long). Ne pas patcher après chaque bascule de case — cela gonfle l'historique de l'issue et augmente la surface de risque d'édition concurrente.

Pour un bloc de longue durée, patcher périodiquement de toute façon (toutes les ~5-10 minutes d'activité), afin que si la session est interrompue, la progression de l'utilisateur soit reflétée sur l'issue.

## Mode de repli markdown

Si le plan de QA est un fichier `docs/qa/qa-plan-*.md` (pas de `gh` disponible, ou pas de remote GitHub) :

- Lire le fichier avec `Read` avant chaque lot de patches.
- Utiliser l'outil `Edit` avec la même règle de correspondance exacte de ligne (§2 et §3).
- Pas de script : le fichier est local.
- Suggérer à l'utilisateur de committer le fichier périodiquement pour que la progression soit durable.

## Ce que cela ne fait PAS

Ce que le script ne garantit pas — il ne verrouille rien : une édition faite par un tiers entre sa lecture et son écriture est écrasée — est écrit dans sa docstring, « Ce qu'il ne prouve pas » (`--help`), seule source.
