---
name: miniature-projet
description: "Produit la miniature d'un projet — la couverture carrée de sa carte sur l'accueil, image PNG de 2400 × 2400 px sans texte — en gabarit « chantier » (trois icônes des éléments phares devant un cône de travaux) ou « mise en scène » (un anneau, et au premier plan un téléphone, une capture ou un schéma) : lire le projet, faire valider les trois icônes ou choisir le premier plan, écrire `docs/miniature/miniature.json`, dessiner quatre propositions montrées sur une planche d'aperçu, inscrire le choix du mainteneur, puis exporter l'image choisie. À utiliser dans le dépôt du projet quand l'utilisateur demande sa miniature, sa couverture ou l'image de sa carte — « fais la miniature du projet », « image de couverture pour la carte », « miniature chantier », « régénère la miniature »."
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

Calqués sur les couvertures en ligne de pacome.dev : un fond pâle fixe, le même pour les deux,
et un trait d'accent à peine plus soutenu, de la teinte choisie. Sans texte sur l'image, au trait
net et en aplats : les icônes Lucide telles quelles, sans rough.js.

- **chantier** — un projet en cours, sans image : le cône de travaux de Lucide en grand trait
  d'accent, qui remplit presque l'image, et devant lui trois icônes grandes, sans cadre, en
  triangle — une en haut, deux en bas —, chaque logo à sa couleur, chaque icône Lucide à l'encre.
  Modèles : les couvertures de Spell Army et de l'assistant IA.
- **mise en scène** — un anneau en trait d'accent, et devant lui le premier plan, grand : un
  **téléphone** générique, dessiné par le rendu, l'image à l'écran ; une **capture**, l'image
  dans un cadre de fenêtre sans texte — l'un et l'autre descendus et coupés par le bas, l'image
  couvrant le cadre depuis son haut ; ou un **schéma**, l'image telle quelle et entière. Modèle :
  la couverture de Badge Mie.

Le fond, la palette — six teintes, chacune un trait d'accent — et les quatre compositions de
chaque gabarit, la première calquée sur son modèle, vivent dans `scripts/miniature.py` (`FOND`,
`PALETTE`, `COMPOSITIONS`), **seule source**.

## Les cinq étapes

### 1. Lire le projet

Le `README`, la documentation, les manifestes, les captures déjà présentes. En tirer le gabarit
qui convient — « chantier » pour un projet en cours sans image, « mise en scène » sinon — et son
contenu. Une description déjà écrite, `docs/miniature/miniature.json`, est le point de départ.
Rien ne s'écrit à cette étape.

### 2. Faire valider le contenu — arrêt

Montrer au mainteneur le gabarit retenu et son contenu :

- **chantier** : proposer trois éléments phares du projet — pas forcément ses technologies —,
  chacun avec son icône, Lucide ou Simple Icons, et le fichier qui l'établit, puis **s'arrêter**
  jusqu'à l'accord du mainteneur. Ses corrections reviennent dans la liste, qui se remontre.
- **mise en scène** : faire choisir le premier plan — téléphone, capture ou schéma — et son image,
  un PNG ou un JPEG sous la racine du projet, puis **s'arrêter** jusqu'au choix. L'image est un
  fichier du dépôt, que la description nomme : elle se **versionne**.

Un petit schéma se fait d'abord par `schema-architecture`, sur sa propre description, réduite à
trois ou quatre cartes, `docs/miniature/schema.json` ; puis, depuis la racine du projet, son
export la dessine seule à son propre chemin, qui devient l'image du premier plan :

```
python <répertoire de ce skill>/../schema-architecture/scripts/export.py docs/miniature/schema.json docs/miniature/schema.png
```

Jamais à ses chemins par défaut : la description réduite écraserait celle du schéma
d'architecture du projet, `docs/schema/architecture.json`, et l'export son image.

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
