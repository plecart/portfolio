# 0015 — Moteur du worker : Celery

- **Statut** : accepté
- **Date** : 2026-10-16
- **Décisions du cadrage** : D59 (`docs/cadrage-technique.md` §7) ; remplace le point
  « `django-imagekit` » de l'ADR 0001 (§ Décision, « Bibliothèques retenues autour de Django ») et
  de l'ADR 0004 (§ Décision, « Traitement des images à l'upload »), et, pour le seul worker
  d'images, la règle « les événements qui déclenchent le worker vivent dans la table outbox » de
  l'ADR 0006 (§ Décision, « Règles ») ; avance en phase 1, avec le worker d'images, le rôle 2
  « broker » que l'ADR 0006 (§ Décision) plaçait en phase 2 avec l'ingestion ; les trois ADR
  restent acceptés pour tout le reste

## Contexte

Une image de galerie téléversée dans l'admin naît « en attente » (`pending`), sans variante. Elle
attend un traitement qui ne doit pas tenir la requête de l'admin : convertir l'original en WebP aux
largeurs que le site affiche, puis écrire l'état « prêt » (`ready`) et la liste des variantes, ou
l'état « échec » (`failed`). Le contrat est en code depuis #9 : `GalleryImage.state`,
`GalleryImage.variants` (`{name, width, height}`), et une contrainte de base qui refuse des
variantes hors de l'état « prêt ». L'ADR 0004 confie ce traitement au worker. En phase 2, ce même
worker ingérera les documents du RAG (cadrage §6.3).

L'annexe A du cadrage laissait le moteur ouvert : « Celery (compétence reconnue) ou arq (légèreté) ;
ADR en phase 1 ou 2 ». Les images le font entrer en phase 1. Django 6.0 a ajouté depuis son propre
cadre de tâches, `django.tasks` : c'est une troisième option.

Trois points d'ADR antérieurs sont à revoir :

- les ADR 0001 et 0004 nomment `django-imagekit` à côté de `Pillow` ;
- l'ADR 0006 place les événements qui déclenchent le worker dans une table outbox de Postgres, Redis
  n'en étant que le transport.

Ces lignes ont été écrites avant le premier modèle. Le code de #9 fixe aujourd'hui un modèle que
l'un et l'autre point ne servent pas (ci-dessous).

## Facteurs de décision

- P1, D27 : la brique la plus simple qui remplit le besoin ; une seule chaîne de traitement d'image
  dans le dépôt.
- `pyright` strict (cadrage §8.4) : chaque dépendance doit être typée, ou avoir ses stubs.
- L'ORM de Django est synchrone ; Pillow travaille sur le processeur.
- Un VPS de 4 Go partagé avec Postgres, Redis et `api` (ADR 0002).
- Redis n'est jamais une source de vérité (ADR 0006) : l'état d'une image vit en base.
- La phase 2 réutilisera le moteur pour l'ingestion : réessais, échecs visibles (cadrage §6.3).
- Valeur de démonstration (cadrage §1, « workers ») : l'annexe A retient Celery pour la compétence
  reconnue, arq pour la légèreté.

## Options considérées

**Moteur**

1. **Celery**, broker Redis.
2. **arq** : file asyncio sur Redis.
3. **`django.tasks`** (Django 6.0) : Django ne fournit que des backends de développement et de test
   (`ImmediateBackend`, `DummyBackend`) ; la production demande un backend tiers, `django-tasks`
   (file en base de données).

**Variantes**

- a. `Pillow` seul.
- b. `Pillow` et `django-imagekit` (ADR 0001, 0004).

**Déclenchement**

- i. La tâche est enfilée une fois la transaction validée (`transaction.on_commit`), sans table
  outbox.
- ii. Un événement écrit dans une table outbox, puis publié vers Redis par un relais (ADR 0006).

## Décision

**Option 1, a, i : Celery, broker Redis, variantes par `Pillow` seul, enfilement après validation de
la transaction.**

- **Application** : `celery[redis]`, dans le projet Django (`config`), configurée par les réglages
  Django sous l'espace de noms `CELERY_`, eux-mêmes lus dans `Env` (ADR 0001, 12-factor). Le broker
  est `REDIS_URL` : le rôle 2 de l'ADR 0006 commence en phase 1. Sérialisation JSON (défaut).
- **Aucun backend de résultats.** Le résultat d'un traitement est l'état de l'image, écrit en base ;
  Celery ne met dans Redis que des messages, et un message perdu laisse l'image « en attente », état
  vrai en base.
- **Le Redis partagé n'évince jamais la file du broker.** Une limite de mémoire posée pour le cache
  (#11) prend une politique `volatile-*`, qui n'évince que les clés à durée de vie (doc Redis,
  « Eviction policies ») : celles du cache (ADR 0006, TTL courts ; aucune clé de cache sans durée
  de vie), jamais la file.
- **Worker** : un conteneur `worker`, même image qu'`api` (ADR 0012), autre commande,
  `celery -A config worker --concurrency 1`. Un seul processus de traitement, ce qui borne la
  mémoire. Il ne joue pas les migrations, qu'`api` joue au démarrage. En production, sa sonde est
  `celery inspect ping` sur son propre nœud : elle prouve que le processus répond et que le broker
  est joignable.
- **Accusé de réception par défaut** : Celery accuse réception d'un message « just before » son
  exécution (doc Celery 5.6, guide « Tasks », `Task.acks_late` ; réglage `task_acks_late`,
  désactivé par défaut). Une tâche commencée n'est jamais redistribuée après un arrêt du
  worker ; seuls ses réessais la ré-exécutent.
- **Déclenchement** : `GalleryImage.save` enfile la tâche après validation de la transaction, quand
  l'enregistrement crée l'image ou remplace son original. La tâche reçoit l'identifiant de l'image
  et le nom de l'original à traiter. Un broker injoignable à ce moment n'empêche pas
  l'enregistrement : l'image reste « en attente ».
- **Pas d'outbox pour les images.** L'état « en attente », écrit dans la même transaction que
  l'image, en est le registre durable ; Redis ne transporte que le message. Ce point remplace,
  pour le seul worker d'images, la règle de l'ADR 0006. L'outbox reste la voie de l'ingestion de
  la phase 2 (D31), qui a besoin d'idempotence, d'empreintes de contenu et d'une file de rejet.
- **Écriture** : une seule requête conditionnelle pose ensemble l'état « prêt » et les variantes,
  sur l'identifiant **et** le nom de l'original traité. Si l'original a été remplacé ou l'image
  supprimée entre-temps, rien n'est écrit et les variantes produites sont supprimées.
- **Échecs** : trois réessais à délai croissant. Réessais épuisés, l'image passe à « échec », sans
  variante, par la même requête conditionnelle — si la base est joignable ; sinon elle reste « en
  attente ». Les fichiers partiels sont supprimés et l'exception sort de la tâche : le worker la
  journalise, et Sentry la recevra avec #17. L'admin affiche « Échec », sans motif.
- **Variantes par `Pillow` seul**, dans un module de conversion, second et dernier module de
  l'application à importer Pillow après celui qui lit l'original au téléversement. WebP, échelle
  unique de largeurs 320, 480, 720, 960 et 1200 px : la photo de carte (spec §4.1), la galerie
  (spec §3.2), largeurs doublées pour les écrans denses, et l'aperçu de lien (spec §1.11,
  ADR 0011), dont les 1200 px plafonnent l'échelle. Une image n'est jamais agrandie ni recadrée ;
  l'orientation EXIF est appliquée ; l'original n'est jamais réécrit.
- **Tests** : le harnais de test met l'application Celery en mode synchrone (`task_always_eager`,
  `task_eager_propagates`) ; les réglages de production n'ont aucune branche « si test ». La suite
  n'a besoin d'aucun Redis.

## Conséquences

**Positives**

- Une seule chaîne d'image : deux modules nommés importent Pillow, et le même test le tient.
- Le contrat de #9, une liste écrite une fois par le worker, est servi tel quel.
- Rien à purger ni à sauvegarder dans Redis ; l'état d'une image se lit dans l'admin.
- Le moteur est en place pour l'ingestion de la phase 2 : réessais, files, routage.

**Négatives, assumées**

- Celery est le plus lourd des trois moteurs : il tire plusieurs paquets (`kombu`, `billiard`,
  `vine`…) et ses stubs (`celery-types`) en dépendance de développement.
- Un processus de plus qui charge Django, sur un VPS de 4 Go ; avec une concurrence de 1, une série
  de téléversements se traite à la suite.
- **Accusé de réception avant exécution** : un worker tué en plein traitement perd la tâche, et
  l'image reste « en attente », visible dans l'admin. Remplacer le fichier relance le traitement.
- **Sans outbox** : un traitement perdu se rattrape de la même façon. La classe est « ni « prêt »
  ni « échec » ne s'écrit » ; cinq chemins recensés le 2026-10-16, liste non close : le worker tué
  ci-dessus ; le broker injoignable à l'enregistrement ; un message perdu par Redis (redémarrage,
  éviction) ; le processus `api` arrêté entre la validation et l'enfilement ; la base injoignable
  pendant toute la fenêtre de réessais, écriture de « échec » comprise. Aucune donnée n'est perdue :
  l'état en base reste vrai, seul le traitement manque, et rien ne le relance sans geste humain.
- **Le mode synchrone est une émulation.** La doc Celery le dit « by definition not suitable for
  unit tests » (« Testing with Celery »). La tâche reste donc mince, la conversion se teste
  directement, et le vrai worker est éprouvé par la fumée sur la pile complète (#26).
- Régénérer les variantes d'images déjà prêtes, si l'échelle change, demande un geste (une commande
  de gestion) qui n'existe pas en phase 1.

## Comparaison des options

**Moteur**

| | Celery | arq | `django.tasks` |
|---|---|---|---|
| Fonction de tâche | synchrone, ORM et Pillow tels quels | coroutine obligatoire ; le travail bloquant passe par un exécuteur (doc arq, « Synchronous Jobs ») | synchrone |
| File en production | Redis (ADR 0006) | Redis | aucune dans Django ; backend tiers `django-tasks` en base |
| Réessais à délai croissant | intégrés (`autoretry_for`, `retry_backoff`) | à la main (exception `Retry`, `max_tries`) | aucun dans l'API de `Task` (doc Django 6.1) |
| Outbox | non | non | native avec un backend en base |
| Démonstration | compétence reconnue (annexe A) | légèreté (annexe A) | la plus récente, écosystème jeune |
| Verdict | **Retenu** | Écarté : asynchrone autour d'un ORM et d'un traitement synchrones | Écarté : backend de production et réessais hors de Django |

**Variantes**

| | `Pillow` seul | `Pillow` + `django-imagekit` |
|---|---|---|
| Modèle | une liste écrite une fois par le worker (contrat de #9) | génération à l'accès et cache de fichiers |
| Typage strict | Pillow est typé | ni `py.typed` ni stubs pour `django-imagekit` 6.1.1 et `pilkit` 3.0 (mesuré le 2026-10-16) |
| Paquets | aucun de plus | trois (`django-imagekit`, `pilkit`, `django-appconf`) |
| Verdict | **Retenu** | Écarté : un second modèle d'image pour une dizaine de lignes de Pillow |

**Déclenchement**

| | `on_commit`, sans outbox | Outbox + relais |
|---|---|---|
| Déclenchement perdu si Redis tombe | l'image reste « en attente », visible ; remplacer le fichier relance | jamais à l'enfilement ; un message perdu par Redis après publication l'est aussi |
| Coût | aucun mécanisme de plus | une table, une migration, un relais et un processus |
| Verdict | **Retenu** pour les images | Gardé pour l'ingestion (D31), construit avec elle |

## Conditions de réexamen

- **L'outbox de l'ingestion existe** (phase 2) : le déclenchement des images y passe, pour n'avoir
  qu'un mécanisme.
- **L'ingestion exige qu'une tâche commencée ne se perde pas** : rouvrir l'accusé de réception
  tardif (`task_acks_late`), avec des tâches idempotentes.
- **La spec change les largeurs affichées** : l'échelle se réécrit, et les variantes des images
  déjà prêtes se régénèrent.
- **La mémoire du VPS ne tient plus la concurrence de 1**, ou une file d'attente visible s'allonge :
  revoir la concurrence avec la taille du VPS (8 Go en phase 2).
