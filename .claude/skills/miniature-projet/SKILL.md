---
name: miniature-projet
description: "Produit la miniature d'un projet — la couverture carrée de sa carte sur l'accueil, image PNG de 2400 × 2400 px sans texte — en gabarit « chantier » (quatre icônes des éléments phares devant un cône de travaux) ou « mise en scène » (fond teinté, disque, et un téléphone, une capture ou un schéma au premier plan) : lire le projet, faire valider les quatre icônes ou choisir le premier plan, écrire `docs/miniature/miniature.json`, dessiner quatre propositions montrées sur une planche d'aperçu, inscrire le choix du mainteneur, puis exporter l'image choisie. À utiliser dans le dépôt du projet quand l'utilisateur demande sa miniature, sa couverture ou l'image de sa carte — « fais la miniature du projet », « image de couverture pour la carte », « miniature chantier », « régénère la miniature »."
---

# Miniature de projet

Le skill se lance dans le dépôt du projet, depuis sa racine. Il produit la **miniature** : la
couverture carrée de la carte du projet sur l'accueil, lisible une fois réduite à la photo de la
carte, 220 px en desktop et 160 px en mobile (spec UX §4.1). Il **s'arrête à l'étape 2**, le temps
que le mainteneur valide le contenu — rien ne s'écrit avant —, puis **à l'étape 4**, le temps
qu'il choisisse une proposition.

**Plusieurs propositions, jamais une seule image** (`CLAUDE.md`, « Skills de la pipeline ») :
chaque lancement dessine quatre propositions du gabarit, chacune d'une teinte de la palette et
d'une composition différentes, montrées numérotées sur une planche d'aperçu ; le mainteneur
choisit, et seule l'image choisie s'exporte.

La session fait tout elle-même ; deux scripts du dossier du skill, en bibliothèque standard,
valident et exportent. Ils réutilisent par leur chemin, sans copie, ceux de `schema-architecture`
— validation, assemblage, capture, planche, icônes — : ce skill doit être présent à côté. Ils se
lancent par `python`, sans `-I`, comme ceux du schéma (`schema-architecture/SKILL.md`).

## Les deux gabarits

Sans texte sur l'image, au trait net et en aplats : les icônes Lucide telles quelles, sans
rough.js.

- **chantier** — un projet en cours, sans image : quatre icônes en grille 2 × 2 centrée, chacune
  sur un badge clair, devant le cône de travaux de Lucide, agrandi, d'un ton plus clair que le
  fond.
- **mise en scène** — un fond teinté, un disque d'un ton voisin, et centré sur lui le premier
  plan : un **téléphone** générique, dessiné par le rendu, l'image à l'écran ; une **capture**,
  l'image dans un cadre de fenêtre ; ou un **schéma**, l'image telle quelle.

La palette, ses six teintes et leur contraste, et les quatre compositions de chaque gabarit
vivent dans `scripts/miniature.py` (`PALETTE`, `COMPOSITIONS`), **seule source**.

## Les cinq étapes

### 1. Lire le projet

Le `README`, la documentation, les manifestes, les captures déjà présentes. En tirer le gabarit
qui convient — « chantier » pour un projet en cours sans image, « mise en scène » sinon — et son
contenu. Une description déjà écrite, `docs/miniature/miniature.json`, est le point de départ.
Rien ne s'écrit à cette étape.

### 2. Faire valider le contenu — arrêt

Montrer au mainteneur le gabarit retenu et son contenu :

- **chantier** : proposer quatre éléments phares du projet — pas forcément ses technologies —,
  chacun avec son icône, Lucide ou Simple Icons, et le fichier qui l'établit, puis **s'arrêter**
  jusqu'à l'accord du mainteneur. Ses corrections reviennent dans la liste, qui se remontre.
- **mise en scène** : faire choisir le premier plan — téléphone, capture ou schéma — et son image,
  un PNG ou un JPEG sous la racine du projet, puis **s'arrêter** jusqu'au choix. Un petit schéma se
  fait d'abord par `schema-architecture`, sur une description réduite à trois ou quatre cartes :
  son PNG devient l'image.

Une icône est le nom, sans extension, d'un SVG du dossier d'icônes de `schema-architecture`. Une
icône de la liste acceptée qui manque à ce dossier se tire par son script, jamais en la remplaçant
par une icône présente :

```
python <répertoire de ce skill>/../schema-architecture/scripts/icones.py <nom> --lucide
python <répertoire de ce skill>/../schema-architecture/scripts/icones.py <slug> --simple-icons
```

### 3. Écrire et valider la description

Écrire `docs/miniature/miniature.json`, sans `teinte` ni `composition` : le choix vient à
l'étape 4. La forme complète vit dans la docstring de `scripts/miniature.py`, **seule source** :
elle ne se recopie pas ici. Puis, depuis la racine du projet :

```
python <répertoire de ce skill>/scripts/miniature.py
```

Sortie 1 et une ligne `<chemin> : <message>` par erreur : les corriger toutes, puis relancer.

Ni l'image ni les propositions ne sont versionnées : si le `.gitignore` du projet ne les ignore
pas encore, y ajouter les lignes `docs/miniature/miniature.png` et `docs/miniature/propositions/`.

### 4. Montrer les propositions — arrêt

Depuis la racine du projet, la description encore sans choix :

```
python <répertoire de ce skill>/scripts/exporter.py
```

Le script valide d'abord, puis retire du dossier les propositions et la planche d'un lancement
précédent, écrit les quatre propositions, `docs/miniature/propositions/proposition-<k>.png`, et
leur planche, `docs/miniature/propositions/planche.png` : chaque proposition numérotée, dans le
cadre d'une carte polaroid de 220 et de 160 px, sur le fond clair puis sombre. La proposition k
porte la k-ième teinte de `PALETTE` et la k-ième composition du gabarit ; `--teintes a,b,c,d`
nomme les quatre teintes de la palette à montrer, dans cet ordre. Ses sorties sont dans sa
docstring.

Montrer la planche au mainteneur, et **s'arrêter** jusqu'à son choix : un numéro, ou la teinte
d'une proposition et la composition d'une autre. L'inscrire dans la description, `teinte` et
`composition` séparément — les noms de la teinte et de la composition retenues —, puis la valider
de nouveau. Une retouche qu'il demande revient dans la description, qui s'exporte de nouveau,
sans choix.

### 5. Exporter l'image choisie et la montrer

Depuis la racine du projet, la même commande : la description porte maintenant le choix, et le
script écrit la seule image choisie, `docs/miniature/miniature.png`, 2400 × 2400 px.

```
python <répertoire de ce skill>/scripts/exporter.py
```

Montrer l'image au mainteneur. L'auteur la dépose ensuite en tête de la galerie de la fiche,
depuis l'admin.

## Prérequis, versions et licences

Ceux de `schema-architecture`, dont ce skill réutilise la capture et les icônes : ses sections
« Prérequis, une fois par poste », « Versions épinglées à la main » et « Licences »
(`schema-architecture/SKILL.md`). Le rendu de la miniature, `rendu/miniature.html`, ne charge ni
police ni rough.js.
