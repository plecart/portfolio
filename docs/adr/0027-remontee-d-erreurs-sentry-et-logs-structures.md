# 0027 — Remontée d'erreurs Sentry et logs structurés

- **Statut** : proposé
- **Date** : 2026-11-05
- **Décisions du cadrage** : D71 (`docs/cadrage-technique.md` §7) ; précise « Observabilité » de
  §6.7 et la ligne « Sentry, healthchecks.io » de §5.2 ; healthchecks.io reste celui de l'ADR 0007
  (D33, D40)

## Contexte

Le cadrage prévoit des logs structurés JSON et Sentry pour les erreurs (§6.7, « Observabilité ») ;
l'ADR 0001, « Bibliothèques », nomme `structlog` et `sentry-sdk` sans qu'aucun ne soit installé.
Aujourd'hui, ni réglage `LOGGING` de Django ni configuration de la journalisation : les incidents
existent déjà sous forme de loggers standard — `django_redis.cache` (Redis injoignable, liste servie
depuis la base, #11), `django.db.backends.base` (rappel `on_commit(robust=True)` en échec),
`django.request`, et l'exception qu'une tâche d'images laisse sortir aux réessais épuisés (ADR 0015,
« Échecs ») —, mais ils sortent au format par défaut de chaque bibliothèque, et personne n'est
prévenu d'un échec en production.

healthchecks.io n'est pas rediscuté ici : l'ADR 0007, « Décision », en fait le dead man's switch
de la sauvegarde, et #23 l'a branché (`BACKUP_PING_URL`).

## Facteurs de décision

- Être prévenu d'une erreur de `api` ou de `worker` sans surveiller les journaux à la main.
- Aucun service de plus à exploiter sur un VPS de 2 Go (ADR 0023), aucun coût (cadrage §6.7,
  table des coûts : « Offres gratuites … 0 »).
- Données en Union européenne, comme LangSmith (cadrage §5.1), et aucune donnée personnelle
  envoyée.
- Un seul format de journal pour Django, Celery, les bibliothèques et l'application.

## Options considérées

**Remontée d'erreurs**

1. **Sentry SaaS**, offre *Developer* gratuite, organisation en région UE.
2. **GlitchTip auto-hébergé**, compatible avec le protocole et le SDK de Sentry.

**Journaux structurés**

1. **`structlog`** branché sur le module `logging` de la bibliothèque standard.
2. **`logging` seul**, avec un formateur JSON écrit par le projet.

## Décision

**Sentry SaaS et `structlog`.**

- **Sentry** reçoit les erreurs de `api` et de `worker`, rien de `apps/web/`. Erreurs seulement :
  ni traces de performance (`traces_sample_rate` absent) ni OpenTelemetry (cadrage §6.7). Le SDK
  s'initialise depuis un DSN lu par `Env` ; sans DSN, il ne s'initialise pas — développement, tests,
  CI. `send_default_pii` reste faux : ni adresse IP, ni cookie, ni en-tête d'autorisation, ni corps
  de requête, ni identifiant de l'auteur. L'environnement Sentry se déduit de `DEBUG`.
- **Organisation en région UE (Francfort)**, choisie à sa création : « once selected, your data
  storage location can't be changed » ; « The only way to switch it is by creating a new
  organization » ([Data Storage Location](https://docs.sentry.io/organization/data-storage-location/),
  lue le 2026-11-05).
- **Offre *Developer***, gratuite : 5 000 erreurs, un utilisateur, 30 jours d'historique, « Data
  Residency : Yes » ([Pricing](https://sentry.io/pricing/), lue le 2026-11-05 ; la page ne précise
  pas la période du quota). Au dépassement, rien n'est facturé sur cette offre : « Events and
  attachments that exceed your quota will not be accepted »
  ([Quotas](https://docs.sentry.io/pricing/quotas/), lue le 2026-11-05).
- **`structlog`** porte un seul point de configuration, appelé une fois au démarrage de `api` comme
  de `worker` : une ligne JSON par événement en production, un rendu lisible en développement
  (`DEBUG`). Les loggers standard — Django, Celery, `django_redis`, ceux de l'application — passent
  par le même rendu. Chaque requête HTTP et chaque exécution de tâche portent un identifiant de
  corrélation, attaché aussi à l'événement Sentry.

## Conséquences

**Positives**

- Une erreur de production arrive dans le projet Sentry, avec sa trace, sans service à exploiter ;
  les alertes sont celles que Sentry crée par défaut, aucune règle de plus.
- Un seul format de journal, lisible par une machine en production (`docker compose logs`).
- L'échec de tâche que l'ADR 0015, « Échecs », réservait à #17 arrive dans Sentry.

**Négatives, assumées**

- Un tiers reçoit les traces d'erreur : le filtrage des données personnelles est à la charge du
  projet, et un test le tient.
- Au-delà de 5 000 erreurs sur la période, les suivantes sont perdues jusqu'au renouvellement du
  quota : une boucle d'erreurs masquerait les suivantes. Assumé pour ce trafic.
- Un seul utilisateur : le mainteneur.
- La région ne se change plus : une erreur de choix coûte une nouvelle organisation.

## Comparaison des options

| | Sentry SaaS | GlitchTip auto-hébergé |
|---|---|---|
| Service à exploiter sur le VPS | aucun | un service web, son worker et sa base |
| Mémoire sur un VPS de 2 Go | aucune | à prendre sur la pile |
| Coût | 0 $, offre *Developer* | 0 $, hors temps d'exploitation |
| Données en UE | oui, région Francfort | oui, sur le VPS |
| Verdict | **Retenue** | Écartée |

| | `structlog` | `logging` seul |
|---|---|---|
| Rendu JSON et rendu lisible | fournis | à écrire |
| Contexte par requête (`contextvars`) | fourni | à écrire |
| Dépendance de plus | une, déjà nommée par l'ADR 0001 | aucune |
| Verdict | **Retenue** | Écartée |

## Conditions de réexamen

- Le quota de l'offre gratuite atteint en usage normal, ou l'offre retirée.
- Un second contributeur à prévenir des erreurs.
- La phase 2 (`ai`) : ses erreurs suivent cet ADR, ses traces vont à LangSmith (cadrage §5.1).
