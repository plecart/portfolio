# 0012 — Deux fichiers Compose, mêmes images

- **Statut** : accepté
- **Date** : 2026-09-24
- **Décisions du cadrage** : D54 (`docs/cadrage-technique.md` §7) ; remplace le point « un seul
  fichier Compose, environnement de développement identique à la production » de l'ADR 0002
  (§ Facteurs de décision, § Décision « Développement local », § Conséquences) et l'argument du
  même nom de l'ADR 0005 (§ Facteurs de décision, § Décision, table de comparaison) ; les deux
  ADR restent acceptés pour tout le reste

## Contexte

Les ADR 0002 et 0005 promettaient « un seul fichier Compose, environnement de développement
identique à la production ». La promesse a été écrite avant tout code, quand `infra/` n'existait
pas.

`infra/` est né avec #4 (2026-09-24) : `infra/compose.dev.yml` démarre Postgres, Redis et `api`
sur un poste, avec ce qu'un poste exige et que la production n'aura jamais — ports publiés sur
`localhost`, code monté depuis l'hôte, serveur de développement de Django à la place de
`gunicorn`. La production (#16) aura ce que le poste n'a pas : `cloudflared`, Caddy, le worker,
le conteneur de sauvegarde, aucun port publié. Un fichier unique devrait porter les deux
ensembles, ou l'un des deux environnements devrait renoncer au sien.

La question n'était donc pas « un fichier ou deux » — la divergence existe, quel que soit le
nombre de fichiers — mais **quel est l'invariant qui vaut d'être tenu** entre le poste et la
production.

## Facteurs de décision

- Ce qui rend un défaut reproductible du poste à la production : l'image, le point d'entrée, les
  services de données. Pas les ports, ni le montage du code, ni le reverse proxy.
- Lisibilité : un fichier Compose se lit seul, de haut en bas ; un fichier qui n'existe que par
  ses surcouches ne se lit nulle part.
- Charge pour un seul développeur : chaque mécanisme Compose supplémentaire (surcouches,
  profils, `include`) est un mécanisme de plus à connaître au moment où quelque chose casse.
- Les six lignes remplacées servaient d'argument contre un Postgres managé (ADR 0005). Cet
  argument tient toujours sous sa forme exacte : le Postgres du poste et celui de la production
  sont **la même image**, `pgvector/pgvector`, ce qu'un service managé ne garantit pas.

## Options considérées

1. **Deux fichiers, un par environnement**, chacun complet et lisible seul ; l'invariant est
   porté par ce qu'ils ont en commun — images, point d'entrée, services de données.
2. **Un fichier de base et des surcouches** (`compose.yml` + `compose.dev.yml` +
   `compose.prod.yml`, empilés par `-f`) : Postgres et Redis écrits une fois ; « un seul fichier »
   reste vrai au sens « un fichier de base ».
3. **Un seul fichier avec profils** (`profiles: [dev]`, `[prod]`) : tout dans un fichier, chaque
   service activé par profil.

## Décision

**Option 1.** Deux fichiers Compose dans `infra/` :

| Fichier | Environnement | Porte en propre |
|---|---|---|
| `compose.dev.yml` (#4) | poste de développement | ports publiés sur `127.0.0.1`, code de `apps/api` monté, `runserver`, valeurs de `infra/dev.env` |
| `compose.yml` (#16) | production, VPS | `cloudflared`, Caddy, `worker`, `backup`, aucun port publié, `.env` écrit par `bootstrap.sh` |

**Invariant tenu entre les deux**, et c'est lui qui remplace « identique à la production » :

- **mêmes images** — `api` construite par `infra/api/Dockerfile`, publiée par #15, jamais
  reconstruite pour un environnement ; `pgvector/pgvector` ; `redis` ;
- **même point d'entrée** — `infra/api/entrypoint.sh`, migrations puis commande, dans les deux ;
- **mêmes services de données** — Postgres et Redis, mêmes versions, joints par les mêmes noms
  de service.

Ce qui diverge est **propre à l'environnement** et ne se reproduit pas de l'un à l'autre par
construction : un port publié n'a pas d'équivalent en production, Caddy n'en a pas sur le poste.

Inchangé des ADR 0002 et 0005 : VPS unique, Caddy, Tunnel, images construites en CI (D43),
Postgres sur le VPS avec pgvector, aucun port de base exposé en production.

## Conséquences

**Positives**

- Chaque fichier se lit seul et dit tout de son environnement ; `make dev` reste
  `docker compose -f infra/compose.dev.yml`, sans empilement.
- L'invariant est nommé, donc vérifiable : un test peut comparer les images et le point d'entrée
  des deux fichiers, ce qu'« identique » n'a jamais permis.

**Négatives, assumées**

- Postgres et Redis sont déclarés deux fois. Un changement de version d'image se fait aux deux
  endroits — c'est le prix de deux fichiers lisibles seuls, et un test de #16 peut tenir cette
  égalité.

## Comparaison des options

| | Deux fichiers | Base + surcouches | Profils |
|---|---|---|---|
| Lisible seul | oui | non — la base ne démarre rien, une surcouche ne dit pas tout | non — chaque lecture filtre mentalement |
| Postgres / Redis | écrits deux fois | une fois | une fois |
| `make dev` | inchangé | change (`-f base -f dev`) | change (`--profile dev`) |
| « Identique à la production » | faux, remplacé par l'invariant | faux aussi : les surcouches divergent | faux aussi : les profils divergent |
| Verdict | **Retenu** | Écartée : sauve une phrase, pas une propriété | Écartée : un fichier long pour deux environnements qui ne se ressemblent pas |

## Conditions de réexamen

- Si un troisième environnement apparaît (préproduction, cadrage §6.7 « pas de staging, à
  réévaluer »), la duplication de Postgres et Redis passe de deux à trois copies : rouvrir
  l'option base + surcouches à ce moment-là.
