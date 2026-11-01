# 0024 — `markdown-to-jsx` : poids mesuré et HTML brut désactivé

- **Statut** : accepté
- **Date** : 2026-11-01
- **Décisions du cadrage** : D51 (`docs/cadrage-technique.md` §7), inchangée ; corrige deux énoncés
  de l'ADR 0010, « Facteurs de décision » et « Options considérées », sans en changer la décision

## Contexte

L'ADR 0010 retient `markdown-to-jsx` pour rendre la description et les sections d'un projet en
éléments React. Il choisit cette bibliothèque pour deux propriétés, écrites avant son installation :
« quelques Ko », et « HTML brut échappé » par défaut. La fiche projet (#170) l'installe : aucune des
deux ne tient telle quelle en version 9.

## Facteurs de décision

- Le poids de page reste jugé par la porte Lighthouse (spec §1.16, §6.4), pas par une estimation.
- Une bibliothèque de rendu de contenu doit rester maintenue.
- Aucun HTML du contenu ne doit être interprété (cadrage §6.6, XSS) : c'est la raison d'être de
  l'ADR 0010.

## Options considérées

Poids mesuré le 2026-11-01, bundler du front, React externe :

1. `markdown-to-jsx` 9.10.4 : 77 Ko, 28,1 Ko gz.
2. `markdown-to-jsx` 8.x : 7,5 Ko gz.
3. `markdown-to-jsx` 7.x : 6,5 Ko gz.

## Décision

**Option 1, sur go du mainteneur au briefing de la PR #205.** La version maintenue l'emporte, à
28 Ko gz et non « quelques Ko ». La décision de l'ADR 0010 reste vraie : Markdown rendu au front, en
éléments React, sans insertion d'HTML.

**`disableParsingRawHTML` est obligatoire.** En 9.10.4, seuls `script`, `iframe`, `style` et leurs
pareils sont échappés par défaut (lecture de la bibliothèque, 2026-11-01) : l'option rend tout le
HTML brut en texte, ce que l'ADR 0010 attendait du défaut. Un scénario de bout en bout tient le
comportement. Le filtrage des schémas d'URL `javascript:` reste celui du `sanitizer` par défaut.

## Conséquences

**Positives**

- La promesse de l'ADR 0010, HTML brut jamais interprété, repose sur une option écrite et testée,
  et non sur un défaut de la bibliothèque.
- Lighthouse a passé ses assertions avec cette version en CI (PR #205).

**Négatives, assumées**

- 28 Ko gz de plus sur un bundle de 74 Ko gz, à l'accueil comme sur la fiche, le dialogue n'étant pas
  chargé à la demande.

## Comparaison des options

| | 9.10.4 | 8.x | 7.x |
|---|---|---|---|
| Poids gz | 28,1 Ko | 7,5 Ko | 6,5 Ko |
| Branche maintenue | oui | non | non |
| Verdict | **Retenu** | Écarté | Écarté |

## Conditions de réexamen

- La porte Lighthouse rougit à cause du poids : le dialogue passe en chargement à la demande.
