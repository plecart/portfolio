# Langage du domaine

Les termes du portfolio, en français, et leurs identifiants dans le code, en anglais
(`.claude/pipeline.config.md`, section « Langue »). Les noms de tests, les titres d'issues et de
PR emploient ces termes ; le code, ces identifiants. Les valeurs stockées sont en anglais et
l'API les expose telles quelles (ADR 0010) : les libellés français vivent dans le catalogue de
chaînes du back (`apps/api/config/strings.py`).

## Technologie — `Technology`

Un langage, un framework, une brique d'infrastructure ou un outil qu'un projet emploie (cadrage
§6.1). Les technologies se saisissent une fois, puis se rattachent aux projets.

| Terme | Identifiant | Règle |
|---|---|---|
| nom | `name` | obligatoire, unique — majuscules et minuscules confondues ; 50 caractères au plus |
| type | `kind` | langage `language` · framework `framework` · infra `infrastructure` · outil `tool` |
| icône | `icon` | fichier SVG, obligatoire |
| site | `website` | adresse facultative, 200 caractères au plus ; stockée, ni exposée ni affichée en phase 1 |
