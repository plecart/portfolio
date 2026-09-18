# 0006 — Redis dès la phase 1

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D20 (`docs/cadrage-technique.md` §7)

## Contexte

À un ou deux visiteurs occasionnels, aucun cache n'est nécessaire aux performances. La
recommandation initiale du cadrage était donc de se passer de Redis en phase 1 et de l'introduire
en phase 2, quand le worker d'ingestion et le rate limiting du chatbot l'exigent. L'auteur a
souhaité Redis dès la phase 1 pour montrer une gestion de cache optimisée. La question « confort ou
nécessité ? » a été posée et tranchée.

## Facteurs de décision

- Valeur de démonstration : le cache est facile, l'invalidation est difficile ; c'est le motif
  intéressant à montrer.
- Trois usages réels sur les trois phases, pour une seule brique.
- Coût en RAM et en exploitation d'un conteneur de plus.
- Redis ne doit jamais devenir une source de vérité.

## Options considérées

1. **Pas de Redis en phase 1** : cache Django en mémoire locale ou en base, rate limiting en
   Postgres ; Redis en phase 2.
2. **Redis dès la phase 1**, avec un rôle utile immédiatement.

## Décision

**Redis 7 en conteneur dès la phase 1**, une brique pour trois rôles :

1. **Cache applicatif** (phase 1) via `django-redis` : réponses d'API, pages projets, plus tard
   statistiques LangSmith de la page « LangGraph » et embeddings des questions fréquentes.
   **Invalidation à la sauvegarde** par les signaux Django : modifier un projet dans l'admin purge
   les entrées concernées. TTL courts, invalidation explicite.
2. **Broker de la file de tâches** (phase 2) du worker d'ingestion : Celery comme arq l'exigent.
3. **Compteurs atomiques du rate limiting** (phases 2 et 3) du chatbot et du MCP, en complément des
   règles au bord (ADR 0003).

Règles : le cache n'est jamais une source de vérité ; toute donnée dans Redis est régénérable ; les
événements qui déclenchent le worker vivent dans la table outbox de Postgres (ADR 0005), Redis n'en
est que le transport. Redis n'est donc pas sauvegardé.

Complément « optimisation » côté HTTP, hors Redis : en-têtes `Cache-Control` et `ETag`, images
redimensionnées en WebP, cache CDN de Cloudflare pour les fichiers statiques.

## Conséquences

**Positives**

- Un motif de cache avec invalidation à montrer dès la première fiche.
- La brique est en place quand la phase 2 en a besoin ; aucune migration d'un cache local vers
  Redis à ce moment-là.
- Aucune persistance à gérer.

**Négatives, assumées**

- Un conteneur de plus dès la phase 1, pour un bénéfice de performance nul à ce trafic.
- Une classe de bugs à surveiller : cache non invalidé. Les TTL courts bornent le dégât.

## Comparaison des options

| | Sans Redis en phase 1 | Redis dès la phase 1 |
|---|---|---|
| Conteneurs | Un de moins | Un de plus |
| Démonstration | Aucune | Cache avec invalidation |
| Phase 2 | Introduction de Redis et migration du cache | Rien à changer |
| Rate limiting | Compteurs en Postgres, moins adaptés | Compteurs atomiques natifs |

## Conditions de réexamen

- Si le cache ne sert à rien de démontrable une fois le site en ligne, le rôle 1 peut être retiré
  sans toucher aux rôles 2 et 3.
