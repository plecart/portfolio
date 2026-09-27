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
faire glisser la ligne.

## Facteurs de décision

- Le geste : déplacer une ligne, pas renuméroter la liste.
- L'ordre stocké reste l'ordre affiché : l'API de #10 l'expose tel quel.
- Du code à maintenir le moins possible, et aucun écart avec l'admin de Django au-delà du tri.
- Les règles de l'écran restent tenues par le formulaire, à l'enregistrement : au moins une
  technologie, pas deux fois la même.

## Options considérées

1. Garder la position saisie, pré-remplie avec la suivante.
2. Glisser-déposer par `django-admin-sortable2`.
3. Glisser-déposer écrit pour le projet (script maison).
4. Flèches « monter » et « descendre » par ligne, script maison.

## Décision

**`django-admin-sortable2`** (MIT, version 2.3.1) ordonne les lignes de l'écran Projet par
glisser-déposer :

- le champ `position` reste en base, caché dans l'écran ; le script de la bibliothèque le réécrit
  dans l'ordre des lignes, et l'ordre stocké suit (`Meta.ordering`, puis l'ordre de saisie) ;
- seules les lignes enregistrées se déplacent : une ligne neuve arrive sans position et
  l'enregistrement la range après les autres, dans l'ordre du formulaire ;
- le formset du projet garde ses règles et ses messages du catalogue ; il hérite du mélange de la
  bibliothèque qui cache la position (`CustomInlineFormSetMixin`).

La bibliothèque déclare Django 4.2 à 5.2 et prépare 6.0 ; elle ne livre rien de propre à 6.1. Sur
Django 6.1, son `SortableAdminBase.media` remplace `admin/js/actions.js` par une copie par version
de Django, absente pour 6.1 (jrief/django-admin-sortable2#442) : l'écran demanderait un fichier
inexistant, et le stockage à manifeste de la production refuserait la page. L'écran Projet part
donc des fichiers de l'admin de Django et n'y ajoute que la feuille et le script de tri. Mesuré sur
Django 6.1.1 : le tri fonctionne sur le gabarit en tableau de Django, l'ordre se réécrit et se
stocke.

## Conséquences

**Positives**

- Réordonner une ligne est un seul geste, quelle que soit la longueur de la liste.
- Aucun script à écrire pour le tri ; #9 réutilise le même mécanisme pour la galerie.

**Négatives, assumées**

- Une dépendance d'exécution de plus, sous `pip-audit` et Dependabot comme les autres.
- Un contournement tant que la bibliothèque ne livre pas sa copie pour 6.1 ; un test rougit le
  jour où elle la livre, pour qu'on le retire.
- Des types écrits pour le projet (`apps/api/typings/adminsortable2/`) : la bibliothèque n'en
  publie pas, et pyright strict refuse une base de classe inconnue.
- Le glisser-déposer se fait à la souris ; le tri au clavier n'existe pas dans l'admin. L'admin n'a
  qu'un utilisateur, l'auteur.

## Comparaison des options

| | Position pré-remplie | `django-admin-sortable2` | Script maison | Flèches |
|---|---|---|---|---|
| Déplacer la 8e ligne en 6e | trois positions réécrites | un geste | un geste | deux clics, une ligne à la fois |
| Code à maintenir | aucun | un contournement et des types, jusqu'au correctif | un script et ses cas limites | un script |
| Dépendance | aucune | une, maintenue, MIT | aucune | aucune |
| Réutilisable par #9 | oui | oui | à écrire pour être générique | à écrire pour être générique |

## Conditions de réexamen

- Une version de `django-admin-sortable2` livre sa copie d'`actions.js` pour la version de Django
  en place : retirer le contournement de `ProjectAdmin.media` (le test d'expiration le signale).
- La bibliothèque cesse d'être maintenue, ou ne suit plus une majeure de Django : revenir à
  l'option 1, sans perte de données — la colonne `position` ne change pas.
