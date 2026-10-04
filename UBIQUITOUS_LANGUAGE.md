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
| description | `description` | obligatoire, en Markdown, gardée telle que saisie ; jamais faite d'espaces seulement — une espace insécable seule y compte comme un texte (locale de l'image) |
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
moins une ; l'écran Projet les saisit en ligne et les ordonne par glisser-déposer (ADR 0013).

| Terme | Identifiant | Règle |
|---|---|---|
| projet | `project` | supprimer le projet supprime ses technologies de projet |
| technologie | `technology` | une fois au plus par projet ; une technologie employée ne se supprime pas |
| position | `position` | entier de 0 à 32 767, caché dans l'écran Projet : l'auteur fait glisser les lignes, enregistrées ou neuves, et la position suit l'ordre affiché à l'enregistrement ; l'ordre stocké suit la position, puis l'ordre de saisie |

## Section — `Section`

Une section de la fiche technique d'un projet, à sa place dans la fiche (cadrage §6.1, D57).
L'auteur en crée autant qu'il veut, sans titre imposé, toutes facultatives : une section sans
texte n'est pas enregistrée, et le site l'omet (spec §7). L'écran Projet les saisit en ligne, sous
les technologies, et les ordonne par glisser-déposer (ADR 0013) : une ligne neuve laissée vide
n'enregistre rien, une ligne titrée sans texte est refusée.

| Terme | Identifiant | Règle |
|---|---|---|
| projet | `project` | supprimer le projet supprime ses sections |
| titre | `title` | obligatoire, 40 caractères au plus |
| ancre | `anchor` | lettres sans accent, chiffres et traits d'union, une fois au plus par projet ; préremplie depuis le titre d'une ligne neuve, toujours modifiable, elle ne suit pas un titre retouché — le site et le RAG y renvoient par `#s-<ancre>` |
| corps | `body` | Markdown, sans borne de longueur, gardé tel que saisi ; jamais vide ni fait d'espaces seulement — une espace insécable seule y compte comme un texte (locale de l'image) |
| position | `position` | comme celle d'une technologie de projet : cachée dans l'écran Projet, elle suit l'ordre affiché à l'enregistrement ; l'ordre stocké suit la position, puis l'ordre de saisie |

## Image — `ProjectImage`

Ce que la couverture et l'image de galerie ont en commun, défini une fois. L'original est gardé
tel que téléversé, à l'octet près, jamais recadré ni réencodé (spec §1.11) ; le worker en produit
les variantes.

| Terme | Identifiant | Règle |
|---|---|---|
| original | `original` | image JPEG, PNG ou WebP, reconnue à son contenu, jamais à son nom ; 10 Mo au plus ; stockée sous un nom engendré — `images/<identifiant aléatoire>/original.<extension du format>` —, nouveau à chaque téléversement |
| largeur, hauteur | `width`, `height` | en pixels, lues dans l'original téléversé, jamais saisies |
| légende | `caption` | obligatoire, 50 caractères au plus, jamais faite d'espaces seulement ; elle sert de texte alternatif |
| état | `state` | en attente `pending` · prêt `ready` · échec `failed` ; une image naît en attente ; seul le worker le fait avancer |
| variantes | `variants` | liste d'objets `{name, width, height}` — `name` est le nom de stockage de la variante —, vide sauf à l'état prêt ; seul le worker l'écrit |

## Couverture — `Cover`

L'image d'un projet : la photo de sa carte, la première image de sa galerie et son `og:image`
(spec §1.11). Une par projet (`project.cover`) ; supprimer le projet la supprime.

| Terme | Identifiant | Règle |
|---|---|---|
| projet | `project` | une couverture par projet |
| forme | `width`, `height` | carrée — largeur égale à la hauteur —, 1200 px de côté au moins |

## Image de galerie — `GalleryImage`

Une image de la galerie d'un projet (`project.gallery`), à sa place dans la galerie ; le site
l'affiche entière dans le cadre carré, sur fond neutre (spec §1.11). Supprimer le projet supprime
sa galerie.

| Terme | Identifiant | Règle |
|---|---|---|
| projet | `project` | un projet en porte autant qu'il veut |
| position | `position` | comme celle d'une technologie de projet : l'ordre stocké suit la position, puis l'ordre de saisie |
