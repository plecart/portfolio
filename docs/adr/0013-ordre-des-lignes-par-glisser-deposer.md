# 0013 — Ordre des lignes de l'admin par glisser-déposer

- **Statut** : accepté
- **Date** : 2026-09-27
- **Décisions du cadrage** : D55 (`docs/cadrage-technique.md` §7) ; amende la décision 2 du brief
  de #7 (« champ entier `position` saisi dans la ligne […] ; aucune bibliothèque de tri ni
  JavaScript »), et avec elle le critère de la galerie de #9 qui la reprenait

## Contexte

Les technologies d'un projet sont ordonnées : les trois premières de type langage, framework ou
infra vont sur la carte (spec §7, « Technologies »). Le brief de #7 avait fixé le geste : un
entier `position` saisi dans chaque ligne de l'écran Projet, sans bibliothèque ni JavaScript. La
galerie de #9 reprenait le même geste.

À l'arrêt visuel de #7 (lot 2), le mainteneur l'a refusé : pour déplacer la huitième technologie
d'une liste de dix en sixième position, il faut réécrire trois positions. Le geste attendu est de
faire glisser la ligne, y compris une ligne qu'on vient d'ajouter : choisir les technologies, les
placer, puis enregistrer une fois.

## Facteurs de décision

- Le geste : déplacer une ligne, enregistrée ou neuve, avant d'enregistrer.
- L'ordre stocké reste l'ordre affiché : l'API de #10 l'expose tel quel.
- Les règles de l'écran restent tenues par le formulaire, à l'enregistrement : au moins une
  technologie, pas deux fois la même.
- Du code et des dépendances à maintenir le moins possible.

## Options considérées

1. Garder la position saisie, pré-remplie avec la suivante.
2. `django-admin-sortable2`, la bibliothèque de référence pour trier les lignes de l'admin.
3. Un script du projet sur le glisser-déposer natif du navigateur.
4. Flèches « monter » et « descendre » par ligne.

## Décision

**Un tableau en ligne ordonnable du projet** (`SortableInline`, `content/inlines.py`), dont le
script (`content/admin/inline_rows.js`) s'appuie sur le glisser-déposer natif du navigateur, sans
bibliothèque :

- chaque ligne, enregistrée ou neuve, porte une poignée que l'admin rend côté serveur, libellé du
  catalogue ; on fait glisser la ligne par sa poignée, ou on la déplace par les flèches haut et bas
  quand la poignée a le focus ;
- le champ `position` reste en base, caché et facultatif dans le formulaire ; à l'envoi, le script
  le remplit dans l'ordre affiché, pour chaque ligne gardée, et une ligne neuve dont seule la
  position est remplie reste ignorée, comme une ligne vide, la première comprise (`InlineRowForm`,
  `SortableFormSet` : « au moins une » se compte sur les lignes remplies) ; le script remet aussi
  les index des lignes là où Django les lit, les lignes enregistrées d'abord — l'ordre affiché n'en
  porte aucun ;
- quand l'écran revient en erreur, les lignes reprennent l'ordre de leurs positions : l'ordre donné
  avant le refus n'est pas perdu ;
- sans le script — désactivé ou en échec —, une ligne neuve arrive sans position et
  l'enregistrement la range après les autres (`SortableFormSet.save_new`) ;
- on retire une ligne, on la rajoute, on la déplace, on échange les objets de deux lignes, puis on
  enregistre une fois : l'unicité (parent, objet) se juge entre les lignes gardées, et avec les
  lignes enregistrées ailleurs depuis l'ouverture de l'écran (`InlineRowForm`, `SortableFormSet`) ;
  la base la vérifie à la fin de l'enregistrement — elle y est différée, car Django écrit les lignes
  l'une après l'autre ;
- générique : tout tableau en ligne de l'admin qui hérite de `SortableInline` s'ordonne ainsi, la
  galerie de #9 comprise.

`django-admin-sortable2` a été essayée puis écartée, sur deux constats lus dans ses sources et
mesurés sur Django 6.1.1 : son script ne déplace que les lignes enregistrées (poignée posée sur le
libellé d'une ligne enregistrée, déplacement refusé à côté d'une ligne neuve) ; et sa version 2.3.1
ne suit pas Django 6.1 — son `SortableAdminBase.media` demande un fichier qui n'existe pas pour
cette version (jrief/django-admin-sortable2#442), qu'il fallait contourner.

## Conséquences

**Positives**

- Choisir les technologies, les placer, enregistrer : un seul enregistrement, quelle que soit la
  longueur de la liste.
- Le tri se fait aussi au clavier.
- Aucune dépendance ; #9 réutilise le même script pour la galerie.

**Négatives, assumées**

- Un script à maintenir (`inline_rows.js` : tri, index et bouton de suppression). Le serveur est
  tenu par les tests, avec les prises que le script lit dans la page ; le geste lui-même ne l'est
  pas, faute de navigateur dans la suite du back : il se vérifie à l'écran, à chaque changement du
  script.
- Le glisser-déposer natif ne fonctionne pas au doigt sur écran tactile ; le clavier reste. L'admin
  a un seul utilisateur, l'auteur, sur un poste.

## Comparaison des options

| | Position pré-remplie | `django-admin-sortable2` | Script du projet | Flèches |
|---|---|---|---|---|
| Déplacer une ligne neuve avant d'enregistrer | en réécrivant des positions | non | oui | oui, une ligne à la fois |
| Déplacer la 8e ligne en 6e | trois positions réécrites | un geste | un geste | deux gestes |
| Clavier | oui | non | oui | oui |
| Dépendance | aucune | une, sans support de Django 6.1 | aucune | aucune |
| Code à maintenir | aucun | un contournement et des types | un script | un script |

## Conditions de réexamen

- L'admin reçoit un second auteur, ou s'utilise sur tablette : le tactile devient un besoin, et une
  bibliothèque qui le gère (SortableJS) se rediscute.
- Le script grossit au-delà du tri et de la suppression des lignes : le remplacer par une
  bibliothèque maintenue plutôt que l'étendre.
