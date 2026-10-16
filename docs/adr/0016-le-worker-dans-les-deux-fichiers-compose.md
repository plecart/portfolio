# 0016 — Le worker dans les deux fichiers Compose

- **Statut** : accepté
- **Date** : 2026-10-16
- **Décisions du cadrage** : D60 (`docs/cadrage-technique.md` §7) ; remplace « le worker » parmi
  ce que la production porte en propre dans l'ADR 0012 (§ Contexte ; § Décision, table « Porte en
  propre ») et dans D54 ; l'ADR 0012 reste accepté pour tout le reste

## Contexte

L'ADR 0012 a été écrit le 2026-09-24, quand aucun moteur de worker n'était choisi. Il range le
worker du côté de la production, avec `cloudflared`, Caddy et `backup` : ce que le poste n'a pas.

Le worker d'images (ADR 0015, #12) en a fait un service réel, et il ne ressemble pas à ces trois-là.
Il n'a rien de propre à un environnement : même image qu'`api`, même commande, mêmes variables,
même stockage. Le poste en a besoin autant que la production — sans lui, une image téléversée y
reste « en attente » pour toujours, et l'état de traitement ne peut pas y être regardé. Le corps de
#12 et le PRD #1 le plaçaient déjà dans les deux fichiers.

## Facteurs de décision

- **Unicité** (décision du mainteneur, 2026-10-16) : tous les workers suivent la même règle, sans
  cas particulier selon le worker ou selon l'environnement — le worker d'images aujourd'hui,
  l'ingestion de la phase 2 demain.
- Ce qui rend un défaut reproductible du poste à la production (ADR 0012, § Facteurs de décision) :
  un worker qui ne tourne qu'en production ne se reproduit nulle part.
- Lisibilité (même §) : un fichier Compose se lit seul ; un service qui n'existe que par une
  surcouche ne se lit nulle part.

## Options considérées

1. **(a) Pas de worker sur le poste** — le document reste vrai.
2. **(b) Le worker du poste dans un fichier de surcouche**, ajouté par `make dev`.
3. **(c) Le worker dans les deux fichiers**, défini de la même façon des deux côtés.

## Décision

**Option c.** Un worker est un service de `infra/compose.dev.yml` et de `infra/compose.yml`,
défini de la même façon des deux côtés : image, commande, variables du service dont il partage
l'image — l'environnement d'`api`, repris par ancre YAML pour le worker d'images. Seul diverge ce
qui est propre à l'environnement : ports, code monté, `runserver` ou `gunicorn`, Tunnel, Caddy,
`backup`. Aucun worker n'est propre à un environnement.

L'invariant de l'ADR 0012 — mêmes images, même point d'entrée, mêmes services de données —
s'étend donc aux workers.

## Conséquences

**Positives**

- Une règle pour tous les workers, vérifiable : un test compare le worker à `api` dans les deux
  fichiers (`apps/api/tests/test_compose.py`).
- Le poste traite les images comme la production ; l'arrêt visuel du lot 3 de #12 se fait sous
  `make dev`.

**Négatives, assumées**

- Un conteneur de plus sur le poste, qui ne recharge pas le code modifié :
  `docker compose restart worker`.

## Comparaison des options

| | (a) Production seulement | (b) Surcouche du poste | (c) Les deux fichiers |
|---|---|---|---|
| Cas particulier | oui — un service d'un seul environnement | oui — un service défini à deux endroits, sous deux formes | non |
| Poste | images jamais traitées | traité | traité |
| Fichiers | deux | trois, un `-f` de plus dans `make dev` | deux |
| Workers à venir | la question se repose | la question se repose | règle déjà écrite |
| Verdict | Écartée | Écartée : l'unicité, et la lisibilité de l'ADR 0012 | **Retenue** |
