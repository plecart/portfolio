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
| site | `website` | adresse facultative, 200 caractères au plus ; stockée, ni exposée par l'API ni affichée sur le site en phase 1 |

## Projet — `Project`

Un projet du portfolio : une carte de la table, une fiche (cadrage §6.1). « En ligne » n'est pas
un champ : le front le déduit de la présence du lien de la démo.

| Terme | Identifiant | Règle |
|---|---|---|
| titre | `title` | obligatoire, 30 caractères au plus |
| slug | `slug` | obligatoire, unique ; lettres sans accent, chiffres, traits d'union et soulignés, 50 caractères au plus ; prérempli depuis le titre, toujours modifiable |
| résumé | `summary` | obligatoire, 120 caractères au plus ; aucun mot — segment entre espaces ou traits d'union, l'espace insécable ne séparant pas — de plus de 20 caractères |
| description | `description` | obligatoire, en Markdown |
| type | `kind` | perso `personal` · pro `professional` · école `school` |
| statut | `status` | en cours `ongoing` · terminé `finished` · archivé `archived` |
| date de début | `started_on` | obligatoire |
| date de fin | `finished_on` | obligatoire dès que le projet n'est plus en cours, absente tant qu'il l'est ; jamais avant la date de début |
| client | `client` | facultatif, 100 caractères au plus |
| lien du dépôt | `repository_url` | adresse facultative, 200 caractères au plus |
| lien de la démo | `demo_url` | adresse facultative, 200 caractères au plus ; sa présence rend le projet « en ligne » |
| vitrine | `showcase` | un seul projet au plus |
| publié | `published` | faux par défaut : un projet naît brouillon |
| créé le, modifié le | `created_at`, `updated_at` | « créé le » posé au premier enregistrement, « modifié le » à chaque enregistrement |

## Technologie de projet — `ProjectTechnology`

Une technologie qu'un projet emploie, à sa place dans la liste du projet. Un projet en porte au
moins une ; l'écran Projet les saisit en ligne.

| Terme | Identifiant | Règle |
|---|---|---|
| projet | `project` | supprimer le projet supprime ses technologies de projet |
| technologie | `technology` | une fois au plus par projet ; une technologie employée ne se supprime pas |
| position | `position` | entier de 0 à 32 767, saisi ; l'ordre stocké suit la position, puis l'ordre de saisie |
