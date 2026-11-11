# 0030 — Routes de l'hôte du site : fichiers de découverte servis par Django, statut 404

- **Statut** : accepté
- **Date** : 2026-11-11
- **Décisions du cadrage** : D74 (`docs/cadrage-technique.md` §7) ; remplace deux points de l'ADR
  0008 : le repli « `try_files {path} /index.html` pour les routes côté client » (§ Décision,
  « Servi en statique ») et la phrase « Caddy route `/projets/*` vers `api` et sert tout le reste en
  statique » (§ Points ouverts tranchés, « Aperçus de lien ») ; l'ADR 0008 reste accepté pour tout
  le reste

## Contexte

Un robot qui n'exécute pas le JavaScript — robots de recherche des assistants IA, agents qui
lisent une page — découvre un site par `/sitemap.xml` et `/llms.txt`, et juge une adresse à son
statut HTTP (issue #265, audits du 2026-11-10). Ces deux fichiers listent les fiches publiées, qui
vivent en base. Sur l'hôte du site, Caddy ne relaie que `/projets/*` vers `api` et sert tout le
reste en statique, avec un repli sur `index.html` : `/sitemap.xml`, `/llms.txt` et toute adresse
inconnue répondent `200` avec la coquille du front (« soft 404 »).

## Facteurs de décision

- « Le contenu vit en base : le modifier dans l'admin ne doit pas déclencher de rebuild » (ADR
  0008, § Facteurs de décision) : une publication doit se voir dans les deux fichiers sans
  recompilation.
- Pas d'état partagé de plus entre conteneurs.
- Un statut juste pour un robot, sans écran de plus pour un humain : le front n'a pas de page 404
  (ADR 0009, `docs/specification-ux.md` §1.15).
- Les fichiers hachés de `/assets/` ne doivent jamais recevoir `index.html` : servie sous un nom de
  script, la page resterait un an dans les caches.

## Options considérées

1. **Django sert `/sitemap.xml` et `/llms.txt` sur l'hôte du site, relayés par Caddy comme
   `/projets/*` ; une adresse que ni un fichier ni une route relayée ne sert rend `404` avec le
   corps d'`index.html`.**
2. Les deux fichiers générés au build du front.
3. Les deux fichiers écrits dans un volume partagé par `api` à chaque publication.
4. Adresse inconnue : `200` et `index.html`, comme avant.
5. Adresse inconnue : `404` sans corps.

## Décision

**Option 1.** Caddy relaie `/projets/*`, `/sitemap.xml` et `/llms.txt` vers `api`, et sert tout le
reste en statique. Une adresse qu'aucun fichier du front ne porte rend `404` : `try_files {path}
{path}/index.html =404` — le second candidat sert l'accueil sous `/`, que `try_files {path} =404`
seul rendait en `404` (mesuré le 2026-11-11, Caddy 2.11.9) —, puis `handle_errors 404` sert
`index.html` par `file_server`, qui garde le statut de l'erreur (doc Caddy, directive
`handle_errors`, lue le 2026-11-10 : « `file_server` preserves the error's HTTP status code when
run in `handle_errors` »), avec les en-têtes de sécurité et le
`Cache-Control: no-cache` d'`index.html`. Sous `/assets/`, une adresse absente reste un `404` sans
`index.html`. L'accueil reste statique.

## Conséquences

**Positives**

- Une publication ou une dépublication se voit dans `/sitemap.xml` et `/llms.txt` à la requête
  suivante, sans recompilation ni état partagé.
- Un robot lit `404` sur une adresse morte ; un humain y voit l'accueil, comme avant.

**Négatives, assumées**

- Deux routes de plus vers `api` sur l'hôte du site : si `api` tombe, les deux fichiers tombent
  avec lui, comme les fiches.
- Le front ne route plus lui-même une adresse sans fichier : une route côté client autre que `/`
  et `/projets/<slug>` rendrait `404`. Le site n'en a pas d'autre (`docs/specification-ux.md` §3).

## Comparaison des options

| | Django + `404` | Fichiers au build | Volume partagé | `200` + `index.html` | `404` nu |
|---|---|---|---|---|---|
| Publication visible sans rebuild | oui | non | oui | — | — |
| État partagé | aucun | aucun | un volume | — | — |
| Statut d'une adresse inconnue | `404` | — | — | `200` (soft 404) | `404` |
| Ce que voit un humain | l'accueil | — | — | l'accueil | une page vide |
| Verdict | **Retenu** | Écarté : contredit l'ADR 0008 | Écarté : état partagé | Remplacé | Écarté |

## Conditions de réexamen

- Une route côté client de plus dans le front (un troisième écran) : elle devra exister comme
  fichier ou comme route relayée, ou rendre `404`.
