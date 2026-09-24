# 0011 — Balises d'aperçu du gabarit : cinq, dont la description SEO

- **Statut** : accepté
- **Date** : 2026-09-24
- **Décisions du cadrage** : D53 (`docs/cadrage-technique.md` §7) ; remplace le point
  « balises injectées » du § « Aperçus de lien » de l'ADR 0008, qui reste accepté pour tout le
  reste ; corrige le décompte « quatre balises » des Conséquences de l'ADR 0010

## Contexte

L'ADR 0008 fait servir `/projets/<slug>` par une vue Django qui remplace, dans l'`index.html`
compilé, un bloc marqué par les balises du projet. Il énumérait quatre balises : `<title>`,
`og:title`, `og:description` et `og:image`.

Le gabarit a été écrit en posant `apps/web` (#3). Sa mise en œuvre a fait apparaître une
cinquième balise que l'énumération ne prévoyait pas : `<meta name="description">`. Elle n'est pas
un ornement — sans elle, l'audit SEO de Lighthouse rend **91**, sous le seuil bloquant de 95 fixé
par `docs/specification-ux.md` §1.16 (mesuré le 2026-09-23 sur la page compilée, Lighthouse
12.6.1 ; avec elle, 100).

La question n'était donc pas de savoir si la balise existe — le seuil l'impose — mais **où** elle
vit : dans le bloc que la vue remplace, ou hors de lui.

## Facteurs de décision

- **Une description unique par page** est la pratique documentée ; une description identique sur
  toutes les fiches est l'anti-pattern « duplicate meta descriptions », avec un effet mesuré sur
  le taux de clic.
- `docs/specification-ux.md` §1.17 fait déjà du résumé du projet la source d'`og:description` :
  la même phrase sert naturellement les deux consommateurs, moteur de recherche et robot
  d'aperçu.
- Le bloc marqué existe pour porter **ce qui est propre à la page**. Y mettre `og:description`
  sans `description` coupe le groupe au milieu.
- **Le seuil de la spec §1.16 ne protège pas contre ce défaut** : l'audit `meta-description` de
  Lighthouse vérifie qu'une description existe, jamais qu'elle est unique. Les deux options
  ci-dessous rendent 100.

## Options considérées

1. **Cinq balises dans le bloc** — la vue injecte aussi `description`, avec le résumé du projet.
2. **`description` hors du bloc**, valeur du site, jamais remplacée : l'énumération de l'ADR 0008
   reste vraie sans amendement.
3. Retirer `description` : écartée d'emblée, le seuil de la spec §1.16 devient intenable.

## Décision

**Option 1.** Le bloc marqué du gabarit porte **cinq** balises, et la vue Django les produit
toutes pour `/projets/<slug>` :

| Balise | Valeur sur une fiche projet | Valeur du gabarit servi tel quel |
|---|---|---|
| `<title>` | titre du projet | nom du site |
| `<meta name="description">` | résumé du projet (spec §1.17) | description du site |
| `og:title` | titre du projet | nom du site |
| `og:description` | résumé du projet, même texte que `description` | description du site |
| `og:image` | couverture du projet, 1200 px (spec §1.11) | **absente** — aucune image de site n'existe |

`description` et `og:description` portent **le même texte** : un test de bout en bout de #3
verrouille leur égalité sur le gabarit, et la vue doit la préserver.

Inchangé de l'ADR 0008 : la CI copie `dist/index.html` dans l'image `api`, Caddy route
`/projets/*` vers `api`, et un slug inconnu redirige en `302` vers `/` (ADR 0009).

## Conséquences

**Positives**

- Chaque fiche projet porte sa propre description : extrait de recherche et carte sociale
  disent la même chose, et disent le projet.
- Le contrat du gabarit est entier dans un seul bloc — rien à réconcilier entre deux endroits
  quand la vue est écrite (#14).

**Négatives, assumées**

- La vue de #14 produit cinq balises au lieu de quatre : une de plus à écrire et à tester.
- Le gabarit ne porte aucun `og:image` par défaut. Un partage de l'accueil sur un réseau social
  affiche une carte sans image tant que #18 n'en fournit pas une.

## Comparaison des options

| | Cinq dans le bloc | `description` hors du bloc | Retirer `description` |
|---|---|---|---|
| Score SEO Lighthouse | 100 | 100 | **91 — sous le seuil** |
| Description des fiches | propre au projet | identique partout | absente |
| Conforme à la pratique | oui | non (duplicate meta descriptions) | non |
| Coût | cet ADR | deux lignes | une ligne |
| Verdict | **Retenu** | Écartée : gratuite, mais installe un défaut que la porte ne voit pas | Écartée |

## Conditions de réexamen

- Si une image d'ouverture propre au site est produite (#18), l'`og:image` par défaut du gabarit
  se rouvre — sans toucher aux cinq balises décidées ici.
