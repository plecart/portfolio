# 0010 — Rendu du Markdown dans le front ; Vitest en phase 1

- **Statut** : accepté
- **Date** : 2026-09-22
- **Décisions du cadrage** : D51 (`docs/cadrage-technique.md` §7) ; remplace le point « Rendu Markdown
  et assainissement HTML » de l'ADR 0001, qui reste accepté pour tout le reste ; lève la condition de
  réexamen « Vitest » de l'ADR 0008

## Contexte

La description et les onze sections d'un projet sont saisies en Markdown (cadrage §6.1, spec §7 :
paragraphes et listes). L'ADR 0001 confiait au back leur transformation en HTML assaini
(`markdown-it-py`, `nh3`) ; le front aurait inséré cette chaîne dans la page. Règle retenue au
cadrage du PRD de la phase 1 : le back envoie des données, le front dessine. Les libellés de dates,
l'ordre des cartes (spec §1.9) et les trois technologies de carte (spec §1.4) sont aussi calculés
au front, à partir de dates ISO, du statut et de technologies typées et ordonnées.

## Facteurs de décision

- Le front possède toute la présentation (marges, liens, ancres de sections de spec §4.3).
- Aucune insertion de chaîne HTML dans React (`dangerouslySetInnerHTML`), aucun assainisseur à
  maintenir : le HTML brut du Markdown est échappé par construction (cadrage §6.6, XSS).
- Poids de page (spec §1.16, §6.4) et D27 : une bibliothèque de quelques Ko pour un sous-ensemble
  de Markdown réduit.
- Le RAG (phase 2) et le MCP (phase 3) lisent le Markdown brut : l'API doit l'exposer tel quel.

## Options considérées

**Lieu du rendu**

1. Back : Markdown → HTML assaini, inséré par le front (ADR 0001).
2. Front : Markdown → éléments React, HTML brut échappé.
3. Front : Markdown → chaîne HTML + assainisseur (DOMPurify) + insertion.

**Bibliothèque de l'option 2**

- a. `markdown-to-jsx` : quelques Ko, éléments React, HTML brut échappé et schémas d'URL
  `javascript:` filtrés par défaut.
- b. `react-markdown` : conforme CommonMark, pipeline `unified`, plus lourd.

## Décision

**Option 2 avec `markdown-to-jsx`.** L'API envoie la description et les sections en Markdown, en
JSON. Le front les rend en éléments React ; le HTML brut est échappé, jamais interprété. La mise
en forme (spec §4.3) se fait par les composants de remplacement de la bibliothèque.

`markdown-it-py` et `nh3` restent dans le back pour un seul usage : l'aperçu du Markdown dans
l'admin (cadrage §6.2). L'aperçu est indicatif ; le rendu de référence est celui du site.

**Vitest entre en phase 1** : la condition de réexamen de l'ADR 0008 est atteinte, le front porte
de la logique pure (format des dates, ordre des cartes, technologies de carte). Playwright + axe
restent le test des écrans.

## Conséquences

**Positives**

- Le back ne produit aucun HTML pour le contenu ; la seule sortie HTML du back reste la vue
  d'aperçus de lien de l'ADR 0008, qui remplit quatre balises du `index.html` construit par le front.
- Aucun vecteur XSS par insertion d'HTML dans le front ; CSP stricte inchangée.
- Le même Markdown alimente le site, le RAG et le MCP.

**Négatives, assumées**

- Deux moteurs de Markdown (aperçu admin en Python, site en TypeScript), sur un sous-ensemble
  réduit : un écart d'affichage est possible et sans gravité, le site fait foi.
- Une dépendance `npm` de plus et un outil de test de plus (Vitest).

## Comparaison des options

| | Back (HTML) | Front (éléments React) | Front (HTML + DOMPurify) |
|---|---|---|---|
| Insertion d'HTML dans React | oui | non | oui |
| Assainisseur à maintenir | `nh3` | aucun | DOMPurify |
| Présentation pilotée par le front | partielle | totale | partielle |
| Verdict | Remplacé | **Retenu** | Écarté : deux mécanismes pour un résultat |

## Conditions de réexamen

- Un besoin de Markdown étendu (tableaux, HTML embarqué) qui dépasserait `markdown-to-jsx`.
- Un contenu saisi par un tiers non fiable : l'aperçu admin reprendrait un assainissement strict.
