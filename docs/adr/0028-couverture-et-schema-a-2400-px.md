# 0028 — La couverture et le schéma d'architecture à 2400 px de côté

- **Statut** : accepté
- **Date** : 2026-11-08
- **Décisions du cadrage** : D72 (`docs/cadrage-technique.md` §7), qui remplace le point du côté
  de D70 ; décisions de l'interrogatoire de #242 (2026-11-08)
- **Remplace** : le point « échelle … dont les 1200 px plafonnent l'échelle » de l'ADR 0015 ; les
  points « 1200 × 1200 px » et « facteur d'échelle 1 » de l'ADR 0026

## Contexte

La couverture d'un projet — photo de la carte, première image de la galerie, `og:image` — est
carrée et fait 1200 px de côté au moins (spec §1.11). Le worker en produit des variantes WebP sur
une échelle unique, 320, 480, 720, 960 et 1200 px, dont les 1200 px plafonnent tout
(ADR 0015 § Décision) : une image plus grande n'est jamais servie au-delà. Le skill
`schema-architecture` exporte son image à 1200 × 1200 px, facteur d'échelle 1 (ADR 0026
§ Décision).

Le plein écran de la fiche (#243) doit montrer le détail d'un schéma, et un écran 2× qui affiche
la galerie à 660 px CSS (spec §3.2) demande 1320 px : 1200 ne sert ni l'un ni l'autre. La condition
de réexamen de l'ADR 0015 — « la spec change les largeurs affichées : l'échelle se réécrit » —
s'exerce ici.

## Facteurs de décision

- Chaque largeur affichée reçoit une variante à sa densité : le navigateur prend la plus petite
  candidate au moins égale à la largeur CSS multipliée par la densité.
- Pas de pixels servis pour rien : un barreau trop grand pour l'écran est signalé par l'audit
  « images correctement dimensionnées » de Lighthouse (seuils spec §1.16).
- L'aperçu de lien garde sa taille, 1200 px (ADR 0011 § Décision).
- Le schéma garde sa mise en page de 1200 px : seule la finesse double.
- L'export reste en bibliothèque standard, sans `import playwright` (ADR 0026, point conservé).

## Options considérées

L'échelle :

1. **`(320, 480, 720, 960, 1200, 1320, 2400)`** : la galerie doublée, 1320, et le plein écran, 2400.
2. **`(320, 480, 720, 960, 1200, 1600, 2400)`**.
3. **2400 seul** ajouté au-dessus de 1200.

Les couvertures déjà enregistrées sous 2400 px :

1. **Refus strict** à tout enregistrement du projet, comme aujourd'hui.
2. Tolérance tant que l'original ne change pas.

L'export du schéma à 2× :

1. **Un descripteur de facteur 2 sur la fenêtre de 1200** : `--device "Desktop Chrome HiDPI"` et
   `--viewport-size 1200,1200`.
2. Une fenêtre de 2400 × 2400, la page mise à l'échelle.
3. L'API Python de Playwright, qui fixe `device_scale_factor`.

## Décision

**Option 1 pour chacune des trois questions.**

- **Échelle `(320, 480, 720, 960, 1200, 1320, 2400)`.** 1320 = 2 × 660, le plafond de la galerie
  (spec §3.2) : sans lui, un écran 2× au plafond téléchargerait le 2400, 3,3 fois les pixels
  utiles. 1200 reste un barreau : c'est l'aperçu de lien. 2400 sert le plein écran (#243). Une
  image sous un barreau reçoit, comme avant, les barreaux inférieurs plus sa propre largeur ; une
  image n'est jamais agrandie.
- **La variante de l'aperçu de lien vaut 1200 px en propre**, découplée du dernier barreau : le
  barreau de 1200 doit rester dans l'échelle, et un test le tient.
- **Couverture de 2400 px de côté au moins, refus strict.** L'admin juge la couverture à chaque
  enregistrement du projet, comme avant : un projet dont la couverture fait moins de 2400 px ne
  s'enregistre plus tant qu'une image conforme n'est pas téléversée. Aucune détection de
  changement de fichier, aucune tolérance, aucune commande de régénération des variantes : chaque
  couverture concernée se re-téléverse dans l'admin.
- **Export du schéma en 2400 × 2400 px** par la CLI de Playwright Python 1.64.1, inchangée sinon :
  `--device "Desktop Chrome HiDPI"` fixe le facteur d'échelle à 2, `--viewport-size 1200,1200`
  l'emporte sur la fenêtre du descripteur. Mesuré le 2026-11-08 sur le poste : PNG de
  2400 × 2400 (IHDR), un carré de 600 px CSS y occupe 1200 px ; la même page sans descripteur
  rend 1200 × 1200. Le script porte la fenêtre (1200) et le facteur (2), et relit dans l'en-tête
  du PNG leur produit. Le descripteur fixe aussi un `userAgent` et `isMobile: false`, sans effet
  sur une page hors ligne.

Les options écartées :

- **1600 au lieu de 1320** : 47 % de pixels de trop au plafond de la galerie, et aucun écran
  courant ne le demande sans demander 2400 (mobile 3× : 3 × 414 = 1242 ≤ 1320) ;
- **2400 seul** : un écran 2× télécharge le 2400 pour une galerie de 660 px ;
- **la tolérance** : un état que l'admin ne refuse pas sans en garder la trace, et deux règles
  de couverture à la fois ;
- **la fenêtre de 2400** : la mise en page du dessin changerait ;
- **l'API Python** : un `import playwright`, que l'ADR 0026 écarte.

## Conséquences

**Positives**

- Le plein écran et les écrans denses reçoivent une image à leur densité, sans servir le 2400 à
  la galerie.
- L'aperçu de lien ne bouge pas, et ne dépend plus de l'ordre de l'échelle.
- Le schéma garde sa mise en page et double sa finesse.

**Négatives, assumées**

- Un projet existant dont la couverture fait moins de 2400 px ne s'enregistre plus : sa
  couverture se re-téléverse avant toute autre modification.
- Les autres images de galerie gardent leurs variantes ≤ 1200 jusqu'à leur re-téléversement,
  faute de commande de régénération (ADR 0015 § Conséquences).
- Un original de 2400 px de côté porte quatre fois les pixels d'un original de 1200 px, dans R2
  et au traitement du worker.

## Comparaison des options

| | Échelle | Couverture sous 2400 | Export 2× |
|---|---|---|---|
| Option 1 | **chaque largeur à sa densité, 1200 conservé** | **refusée, une seule règle** | **mise en page de 1200, bibliothèque standard** |
| Option 2 | 47 % de pixels de trop au plafond de la galerie | tolérée, deux règles | mise en page changée |
| Option 3 | le 2400 servi à la galerie 2× | — | `import playwright` |

## Conditions de réexamen

- La spec change les largeurs affichées, plein écran compris : l'échelle se réécrit.
- La CLI `screenshot` de Playwright perd une option dont l'export dépend — taille de fenêtre,
  descripteur `--device`, attente d'un sélecteur, délai —, ou le descripteur
  « Desktop Chrome HiDPI » change de facteur d'échelle.
- Une commande de régénération des variantes entre dans le projet : les images déjà prêtes
  peuvent rattraper l'échelle sans re-téléversement.
