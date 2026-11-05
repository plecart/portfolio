# 0026 — Le schéma d'architecture : rendu hors ligne, export par Playwright Python

- **Statut** : accepté
- **Date** : 2026-11-05
- **Décisions du cadrage** : D70 (`docs/cadrage-technique.md` §7) ; décisions de
  l'interrogatoire de #217 (2026-11-05)

## Contexte

Le schéma d'architecture de pacome.dev, image carrée de la galerie de sa fiche, a été dessiné à la
main le 2026-11-03 (version 13) depuis un matériel hors dépôt : une page qui charge rough.js 4.6.6
d'un CDN et ses deux polices de Google Fonts, la description en JavaScript, et un export manuel —
la capture de la fenêtre par le navigateur du serveur MCP `playwright`, qui tournait à un zoom de
0,75 (mesuré le 2026-11-03) : le côté de l'image n'était pas garanti.

L'issue #217 en fait un skill maison, `schema-architecture`, qui sert tout projet : la
description du schéma s'écrit en `docs/schema/architecture.json`, documentation du dépôt (D16 ;
ADR 0001 § Décision), et l'image s'exporte à côté, sans être versionnée. Restait à choisir avec
quoi le rendu dessine, et ce qui capture la page.

## Facteurs de décision

- L'image fait 1200 × 1200 px quels que soient le zoom et l'écran du poste.
- Le skill sert aussi un projet sans front ni Node : il ne demande que ce qu'a tout poste de la
  pipeline, Python et `uv`.
- Le rendu ne fait aucune requête : il se refait hors ligne, et rien ne dérive avec un CDN.
- La suite de la pipeline garde `pytest` et `pyyaml` (ADR 0025), et pyright strict, qui couvre
  les scripts des skills (`.claude/pyrightconfig.json`), n'y voit aucun module manquant.
- Ce qui se copie porte sa licence.

## Options considérées

Le rendu :

1. **Les dépendances copiées dans le dossier du skill** : rough.js, les deux polices en woff2,
   les seules icônes utilisées et la couleur de leurs logos.
2. **Le CDN au rendu** : rough.js de jsDelivr, les polices de Google Fonts, comme la version 13.
3. **Tout le `data.json` de Simple Icons** copié pour en lire les couleurs, avec les icônes
   utilisées.

La capture :

1. **La CLI de Playwright Python**, à une version épinglée, lancée par
   `uv run --no-project --with` depuis un script de bibliothèque standard du dossier du skill.
2. **Le Playwright npm d'`apps/web`**, déjà installé pour les tests E2E du front.
3. **La capture manuelle** par le navigateur du serveur MCP `playwright`.

## Décision

**Option 1 pour chacune des deux questions.**

- **Rendu hors ligne.** Le dossier du skill porte rough.js 4.6.6 (MIT), Manrope (Google Fonts
  v20) et Shantell Sans (`@fontsource-variable/shantell-sans` 5.3.0) en woff2, sous-ensemble
  latin, avec la notice et le texte de l'OFL 1.1 ; seules les icônes utilisées, tirées de
  Simple Icons 15.0.0 (CC0, avec la note « les logos restent des marques ») et de Lucide 0.460.0
  (ISC, mention gardée), et la seule couleur des logos utilisés, dans `couleurs.json`. Une icône
  qui manque à un autre projet se tire de la version épinglée, par son URL versionnée, avec le
  script d'icônes du skill. L'export assemble une page autonome — polices en `data:`, tout le
  reste en ligne — qui ne fait aucune requête.
- **Capture par la CLI de Playwright Python 1.64.1**, lancée par
  `uv run --no-project --with playwright==1.64.1 playwright screenshot` : Chromium sans fenêtre,
  fenêtre de 1200 × 1200 px, facteur d'échelle 1, capture après le marqueur que la page pose une
  fois rendue ; puis le script relit la taille dans l'en-tête du PNG et échoue si elle n'est pas
  1200 × 1200. **Aucun `import playwright`** : le script reste en bibliothèque standard, et
  Playwright Python n'entre ni dans les dépendances du projet ni dans celles de la suite.
  Prérequis une fois par poste, dit par le `SKILL.md` : `playwright install chromium` par le même
  `uv run --no-project --with`.
- **Versions épinglées à la main.** Dependabot ne lit ni le `--with` de `uv run` ni les fichiers
  copiés : le `SKILL.md` du skill dit où vit chaque version et comment la monter, comme pour
  `.mcp.json` (`.claude/pipeline.config.md`, « Serveurs MCP ») et Trivy (ADR 0014 § Décision).

Les options écartées :

- **le CDN au rendu** : une image qui dépend du réseau et d'une version servie ailleurs ;
- **tout le `data.json` de Simple Icons** : 370 Ko à la version 15.0.0 (369 263 octets, mesuré le 2026-11-05) pour la couleur de quelques logos ;
- **le Playwright npm d'`apps/web`** : le skill dépendrait d'un front, et Playwright y reste
  l'outil E2E (ADR 0008) ;
- **la capture manuelle par le navigateur du MCP** : zoom de 0,75 mesuré le 2026-11-03, côté non
  garanti, et un geste à refaire à la main.

## Conséquences

**Positives**

- Le côté de l'image ne dépend plus du zoom ni de l'écran du poste, et l'export le vérifie.
- Un projet sans front a le skill : Python et `uv` suffisent.
- Le rendu se refait hors ligne, à l'identique tant que rien n'est monté.
- Ni la suite de la pipeline ni pyright n'y gagnent de dépendance.

**Négatives, assumées**

- Chaque version se monte à la main, et aucune alerte de dépendance ne vise ce qui est copié.
- Chromium se télécharge une fois par poste et par version de Playwright, et le premier
  `uv run` d'une version tire Playwright Python dans le cache d'`uv` : le réseau, une fois.
- Une icône absente du dossier demande le réseau, une fois, par le script d'icônes.

## Comparaison des options

| | Rendu | Capture |
|---|---|---|
| Option 1 | **hors ligne, licences jointes, quelques Ko d'icônes** | **1200 × 1200 vérifié, Python et `uv` seuls** |
| Option 2 | réseau à chaque rendu, version servie par un tiers | dépend d'un front et de Node |
| Option 3 | 370 Ko de données pour quelques couleurs | zoom 0,75, côté non garanti, geste manuel |

## Conditions de réexamen

- Un bot de dépendances sait lire un `uv run --with` ou un fichier copié : les épingles passent
  sous lui.
- La CLI `screenshot` de Playwright perd une option dont l'export dépend — taille de fenêtre,
  attente d'un sélecteur, délai.
- Un schéma demande un dessin que rough.js ne fait pas.
