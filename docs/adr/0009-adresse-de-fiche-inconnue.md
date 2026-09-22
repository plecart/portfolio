# 0009 — Adresse de fiche inconnue : redirection vers l'accueil

- **Statut** : accepté
- **Date** : 2026-09-22
- **Décisions du cadrage** : D50 (`docs/cadrage-technique.md` §7) ; remplace le point « slug inconnu » de
  l'ADR 0008 (« Aperçus de lien »), qui reste accepté pour tout le reste

## Contexte

L'ADR 0008 fait servir `/projets/<slug>` par une vue Django qui injecte les balises d'aperçu du
projet dans `index.html`. Pour un slug inconnu, elle prévoyait le gabarit sans balises, un statut
404 et une page 404 dessinée par le front. Le site n'a que deux écrans, la table et la fiche
(`docs/specification-ux.md` §3) : un écran de plus pour dire « rien ici » est de la logique sans
usage (P1, D27).

## Facteurs de décision

- Aucun état ni écran supplémentaire dans le front (D27).
- Même comportement pour un humain et pour un robot d'aperçu de lien.
- Un slug peut redevenir valide (projet dépublié puis republié) : rien ne doit être mémorisé
  comme définitif.

## Options considérées

1. **Redirection `302` vers `/`** par la vue Django.
2. Statut 404 et page 404 du front (ADR 0008).
3. Statut 404, et le front renvoie lui-même vers `/`.

## Décision

**Option 1.** Quand aucun projet publié ne porte le slug, la vue répond `302 Found` vers `/`. Le
front n'a aucun état « adresse inconnue » (`docs/specification-ux.md` §5.4). Caddy continue de
router `/projets/*` vers `api` (ADR 0008).

## Conséquences

**Positives**

- Rien à dessiner, à tester ni à maintenir côté front.
- Un lien mort prévisualise l'accueil au lieu d'une page vide.

**Négatives, assumées**

- Un moteur de recherche reçoit un `302` au lieu d'un `404` pour une adresse morte ; sans effet
  pour un portfolio d'une page.

## Comparaison des options

| | `302` vers `/` | 404 + page du front | 404 + renvoi par le front |
|---|---|---|---|
| Code front | aucun | un écran et un état | un état |
| Robots d'aperçu | aperçu de l'accueil | aperçu vide | aperçu vide |
| Verdict | **Retenu** | Remplacé | Écarté : deux mécanismes pour le même résultat |

## Conditions de réexamen

- Un besoin de référencement fin des adresses mortes (statut 404 exigé) rouvrirait les options 2
  ou 3.
