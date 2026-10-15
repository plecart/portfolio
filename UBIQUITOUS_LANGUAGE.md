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

## Image de galerie — `GalleryImage`

Une image de la galerie d'un projet (`project.gallery`), à sa place dans la galerie ; le site
l'affiche entière dans le cadre carré, sur fond neutre (spec §1.11). L'original est gardé tel que
téléversé, à l'octet près, jamais recadré ni réencodé ; le worker en produit les variantes.
Supprimer le projet supprime sa galerie. L'écran Projet la saisit dans un tableau, sous les
technologies, où l'auteur ajoute, retire et ordonne les images par glisser-déposer avant
d'enregistrer une fois ; une ligne neuve laissée vide n'enregistre rien, et un projet sans image
est refusé, brouillon compris. Il montre l'aperçu de chaque original enregistré et son état, qui
ne s'y modifie pas.

| Terme | Identifiant | Règle |
|---|---|---|
| original | `original` | image JPEG — à plusieurs images comprise, comme bien des photos de téléphone —, PNG ou WebP, reconnue à son contenu, jamais à son nom ; 10 Mo au plus ; stockée sous un nom engendré — `images/<identifiant aléatoire>/original.<extension du format>` —, nouveau à chaque téléversement ; validée et lue au téléversement seulement : un fichier stocké n'est jamais relu |
| largeur, hauteur | `width`, `height` | en pixels, lues dans l'original téléversé, jamais saisies |
| légende | `caption` | obligatoire, 50 caractères au plus, jamais faite d'espaces seulement ; elle sert de texte alternatif |
| état | `state` | en attente `pending` · prêt `ready` · échec `failed` ; une image naît en attente, et y revient quand son original est remplacé ; seul le worker le fait avancer |
| variantes | `variants` | liste d'objets `{name, width, height}` — `name` est le nom de stockage de la variante —, vide sauf à l'état prêt ; seul le worker l'écrit |
| projet | `project` | un projet en porte une au moins |
| position | `position` | comme celle d'une technologie de projet : cachée dans l'écran Projet, elle suit l'ordre affiché à l'enregistrement ; l'ordre stocké suit la position, puis l'ordre de saisie |

Supprimer une image, seule ou avec son projet, ou remplacer son original supprime du stockage
l'ancien original et ses variantes, une fois la transaction validée ; une transaction annulée
n'en supprime aucun.

## Couverture

La première image de la galerie d'un projet : la photo de sa carte, la première image de sa fiche
et son `og:image` (spec §1.11). Ce n'est pas un modèle : glisser une autre image en tête en fait
la couverture, et lui en applique les règles.

| Terme | Identifiant | Règle |
|---|---|---|
| forme | `width`, `height` | carrée — largeur égale à la hauteur —, 1200 px de côté au moins ; l'écran Projet la tient, la base ne le peut pas |

## API publique

L'unique point d'entrée de la phase 1 : `GET /api/projets`, la liste nue des projets publiés —
un tableau JSON, `[]` s'il n'y en a aucun, sans pagination ni route par slug (PRD « Hors
périmètre »). Un brouillon n'y figure jamais. Le site la charge en une fois et calcule le reste :
ordre des cartes, libellés, technologies de carte (ADR 0010). Son contrat est le schéma
`apps/api/openapi.json`, régénéré par `make openapi` ; le front en dérive ses types (#19).

| Terme | Identifiant | Règle |
|---|---|---|
| projet | `ProjectOut` | `slug`, `title`, `summary`, `description` (Markdown brut), `kind`, `status`, `started_on`, `finished_on` (`null` tant que le projet est en cours), `client`, `repository_url`, `demo_url` (chaîne vide quand absent, comme stocké), `showcase`, puis ses trois listes ; les projets sont triés par slug |
| technologie | `TechnologyOut` | `name`, `kind`, `icon` — l'adresse de l'icône SVG, jamais le SVG lui-même ; dans l'ordre de l'admin |
| image | `GalleryImageOut` | `caption`, `width`, `height`, `state`, `variants` ; dans l'ordre de l'admin ; une image en attente ou en échec figure avec son état et sans variante |
| variante | `VariantOut` | `url`, `width`, `height` — l'adresse à la place du nom de stockage |
| section | `SectionOut` | `title`, `anchor`, `body` (Markdown brut) ; dans l'ordre de l'admin |
| couverture | `gallery[0]` | aucune clé à part : c'est la première image de la galerie |
| adresse | — | chaque fichier par son adresse absolue : celle du stockage, complétée du schéma et de l'hôte de la requête quand elle est relative (disque en développement) |

Ne sont pas exposés : `published`, `created_at` et `updated_at`, `position` et `id` (l'ordre est
celui de la liste), le site d'une technologie (`website`) et l'original d'une image (`original`).
Ni HTML ni libellé : les valeurs stockées, en anglais, telles quelles.
