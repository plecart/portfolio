# Portfolio — Cadrage technique

_Version 1.5 · 2026-09-23 · Remplace le brouillon v0 du 2026-09-10 et son journal de questions-réponses, supprimés le 2026-09-18 une fois leur matière (pourquoi, options écartées) reprise dans les ADR de `docs/adr/`. Les décisions gardent les identifiants du v0 (D1 à D38) ; D39 et suivantes sont nées avec la v1._
_Le design (UI/UX) est hors périmètre de ce document._

---

## 1. Finalité

- Portfolio personnel de Pacôme Bernier, publié sur `pacome.dev`, destiné à **prouver la capacité à monter un projet de bout en bout** : conception, backend, sécurité, données, workers, IA, déploiement, exploitation.
- Contenant conçu pour être rempli au fil du temps : ajouter un projet ne demande jamais de toucher au code.
- **Le portfolio est lui-même le premier projet présenté** (méta-projet). Sa fiche décrit le site, le RAG et le MCP ; les ADR (Architecture Decision Records) en sont la matière première.

## 2. Principes directeurs

| # | Principe | Conséquence concrète |
|---|---|---|
| P1 | Simplicité d'abord | Pas de sur-ingénierie gratuite ; la brique la plus simple qui remplit le besoin. |
| P2 | Plusieurs briques modulaires et génériques | Chaque brique est remplaçable et son choix est justifié par un ADR : « pourquoi celle-ci plutôt qu'une autre ». |
| P3 | Outils et services managés plutôt qu'auto-hébergement | Quand le coût le permet. Exception assumée : un VPS unique pour le calcul et Postgres. |
| P4 | Code minimal | Chaque ligne sert un but. Aucun résidu de squelette, aucune abstraction « au cas où », aucune fonctionnalité inutilisée. |
| P5 | Sécurité maximale sur les surfaces publiques | Chatbot et MCP exposés au public : la sécurisation est une démonstration en soi. |
| P6 | Incassable | Tests, CI, supervision, sauvegardes testées, dégradation gracieuse : le site vit sans le service IA. |
| P7 | Conçu comme si le code était public | Aucun secret dans le code ; sécurité par authentification et limitations, jamais par obscurité. Le dépôt reste privé, décision révisable. |
| P8 | Pédagogique | Apprendre LangGraph et LangSmith en les utilisant ; chaque concept expliqué au moment où il sert, dans `docs/learning/`. |
| P9 | Livraison incrémentale | Pas de délai ; blocs livrés un par un via des issues ; première version en production tôt. |

## 3. Contraintes

- **Budget** : environ 50 € par mois maximum. Estimation actuelle : 10 à 30 € (§6.7).
- **Langue** : contenu en français uniquement. Rien en dur dans le code : libellés dans un catalogue de chaînes unique, contenu en base. Pas de plomberie multilingue (champs traduits, sélecteur de langue) tant que l'anglais n'est pas demandé.
- **Email** : aucun envoi d'email, nulle part. Sujet post-MVP, peut-être jamais.
- **Trafic** : un ou deux visiteurs occasionnels. On conçoit pour un faible trafic avec des protections robustes.
- **Contenu** : public par nature. Les projets privés ne montrent que captures d'écran, langages et outils, sans lien. Le CV fourni au chatbot est une version publique, sans téléphone ni adresse.
- **Frontend** : application statique compilée en CI et servie par Caddy ; aucun runtime Node en production (D44).
- **Dépôt** : privé.

## 4. Phases

Strictement séquentielles : on n'attaque la suivante que lorsque la précédente est solide et en production.

### Phase 1 — MVP portfolio (back + front)

- Accueil : grille de cartes, une par projet (image, titre, technologies principales) ; une carte s'ouvre en fiche. Style et mouvement : `docs/specification-ux.md`.
- Fiche projet (modal) : titre, description, tags de technologies, images et texte, et **la fiche technique en sections libres** (§6.1).
- Back-office : Django admin personnalisé, un seul utilisateur.
- Premier contenu : la fiche du méta-projet.
- Socle d'exploitation complet dès cette phase : VPS, Docker Compose, Cloudflare, R2, CI/CD, sauvegardes et plan de reprise, supervision, Redis (cache).

### Phase 2 — Chatbot RAG intégré au site

- Sources : fiches projets, profil structuré, documents « sur moi » (CV public, récits d'expérience), ADR.
- Pipeline : ingestion événementielle (ajout, modification, suppression), extraction, découpage, embeddings, index hybride pgvector, retrieval avec reranking, génération avec citations.
- Orchestration LangGraph, composants LangChain, observabilité et évaluation LangSmith (cloud, région UE).
- Page « LangGraph » publique : statistiques agrégées, trace de la conversation du visiteur.
- Garde-fous, rate limiting, plafond de coût, page de confidentialité.

### Phase 3 — MCP public

- Serveur MCP distant (Streamable HTTP) : un visiteur branche son Claude ou tout client MCP et interroge le portfolio depuis son outil.
- Option « recherche » : le MCP renvoie les données (fiches, passages pertinents), c'est le LLM du visiteur qui rédige.
- Outils de lecture + une seule action, `send_message`, qui écrit en base (lecture dans l'admin).
- Lecture anonyme limitée, écriture authentifiée, anti-abus.

### Hors périmètre

Email (post-MVP, peut-être jamais) · anglais · commentaires (retirés) · MCP d'édition de contenu (rejeté) · Kubernetes · CMS headless · content-as-code · Postgres managé.

## 5. Architecture cible

### 5.1 Vue d'ensemble

- **Bordure** : le visiteur atteint Cloudflare (DNS, proxy, CDN, WAF, rate limiting, Access ; Turnstile en phase 2), qui transmet au VPS par Cloudflare Tunnel : le conteneur `cloudflared` sort vers Cloudflare, aucun port web n'est ouvert ; Caddy, derrière lui, route et sert les statiques.
- **VPS** (Docker Compose, réseau privé) : Caddy sert le frontend en statique (compilé en CI, copié dans son image) et route vers `api` (Django et admin), `ai` (FastAPI + LangGraph, phase 2) et `mcp` (phase 3).
- **Données** : `api`, `ai` et `mcp` lisent et écrivent Postgres (pgvector en phase 2) ; `api` et `ai` utilisent Redis. Le `worker` (vignettes, puis ingestion) travaille sur Postgres et Redis ; le conteneur `embeddings` (phase 2, modèles locaux) sert `ai` et le `worker`.
- **Stockage** : `api` et le `worker` déposent médias et documents sur Cloudflare R2, servis via le CDN.
- **Sauvegardes** : le conteneur `backup` dump Postgres chaque nuit vers un bucket R2 dédié et signale sa réussite à healthchecks.io.
- **Services externes** : `ai` appelle l'API Claude et envoie ses traces à LangSmith (cloud UE) ; `api` remonte ses erreurs à Sentry. Ces trois dépendances sont non bloquantes (§6.7).

### 5.2 Briques et alternatives écartées

| Brique | Rôle | Phase | Écarté | ADR |
|---|---|---|---|---|
| Cloudflare | Registrar, DNS, proxy, CDN, WAF (fourni, sans implémentation), rate limiting, Access ; Turnstile optionnel en phase 2 | 1 | Caddy seul + Tailscale | 0003 |
| VPS x86 en UE (Hetzner, OVH, Scaleway), 1 vCPU et 2 Go au minimum en phase 1, 8 Go en phase 2 | Calcul, Postgres, modèles locaux | 1 | PaaS, tout managé, Kubernetes | 0002, 0023 |
| Docker Compose | Orchestration locale des conteneurs | 1 | — | 0002 |
| Caddy | Reverse proxy interne, statiques (TLS terminé par Cloudflare) | 1 | Traefik, nginx | 0002 |
| Django | Contenu, admin, API | 1 | FastAPI seul | 0001 |
| Django admin | Back-office | 1 | CMS headless, content-as-code, admin custom | 0001 |
| Postgres 16 + pgvector | Contenu, vecteurs, checkpoints, outbox | 1 (pgvector en 2) | Postgres managé, Qdrant | 0005 |
| Redis | Cache avec invalidation, puis broker et rate limiting | 1 | — | 0006 |
| Worker (Celery) | Tâches de fond | 1 | arq, `django.tasks`, Temporal | 0015 |
| Cloudflare R2 | Médias publics, documents privés, sauvegardes | 1 | Disque du VPS | 0004 |
| Vite + React + TypeScript + Tailwind CSS + shadcn/ui | Frontend statique, compilé en CI, servi par Caddy | 1 | Next.js, Flutter web | 0008 |
| GitHub Actions + GHCR | CI/CD : construction, scan et publication des images | 1 | Docker Hub, registre auto-hébergé ; agent de déploiement sur le VPS | 0014 |
| Sentry, healthchecks.io | Erreurs, sauvegardes | 1 | Surveillance de disponibilité SaaS, Prometheus + Grafana | à écrire (sauvegardes : 0007) |
| FastAPI + LangGraph + LangChain | Service IA | 2 | Django ASGI, sans framework | à sa phase |
| LangSmith cloud (région UE) | Traces, datasets, évaluations | 2 | Langfuse | à sa phase |
| API Claude | Génération et étapes bon marché | 2 | — | à sa phase |
| Embeddings et reranking locaux (`bge-m3`, `bge-reranker-v2-m3` servis par `text-embeddings-inference`) | Vectorisation, reranking | 2 | Voyage AI, OpenAI | à sa phase |
| SDK Python `mcp` (FastMCP) | Serveur MCP | 3 | SDK TypeScript | à sa phase |

La colonne ADR renvoie au numéro du fichier dans `docs/adr/` (index : `docs/adr/README.md`).

### 5.3 Conteneurs sur le VPS

| Conteneur | Rôle | Phase |
|---|---|---|
| `cloudflared` | Cloudflare Tunnel : connexion sortante vers Cloudflare, seule entrée du VPS (D45) | 1 |
| `caddy` | Reverse proxy interne ; sert le frontend compilé, copié dans son image (D43, D44) ; aucun port publié | 1 |
| `api` | Django : contenu, admin, API | 1 |
| `postgres` | Image `pgvector/pgvector` | 1 |
| `redis` | Cache, puis broker et rate limiting | 1 |
| `worker` | Vignettes, puis ingestion | 1 |
| `backup` | Cron nocturne : dump, chiffrement, envoi R2, ping | 1 |
| `ai` | LangGraph, chat en streaming | 2 |
| `embeddings` | Modèles d'embeddings et de reranking locaux (`text-embeddings-inference`, CPU) | 2 |
| `mcp` | Serveur MCP | 3 |

Réseau Docker privé ; aucun port de base de données exposé ; images construites en CI et publiées sur GHCR.

### 5.4 Flux clés

1. **Consultation** : visiteur → Cloudflare (CDN, WAF) → Caddy, qui sert le frontend statique ; le front appelle `api` ; les images viennent de R2 via le CDN ; les réponses d'API passent par le cache Redis.
2. **Publication** : l'auteur crée ou modifie un projet ou un document dans l'admin → Django écrit en base et envoie le fichier sur R2 dans la même opération → signal de sauvegarde → événement dans la table outbox → invalidation du cache → (phase 2) le worker ingère : extraction, découpage, embeddings, chunks en base. Suppression : événement inverse, purge des chunks. Aucun redéploiement : le contenu est de la donnée, pas du code. Un fichier déposé directement dans le bucket n'existe pas pour le site : la base est la source de vérité.
3. **Question au chatbot** (phase 2) : Turnstile et rate limiting → `ai` exécute le graphe LangGraph : routage, réécriture, retrieval hybride, reranking, génération avec citations, streaming SSE des étapes et des tokens → checkpoint Postgres → trace asynchrone vers LangSmith.
4. **Requête MCP** (phase 3) : client MCP du visiteur → `mcp` → outils de lecture sur la base et l'index ; `send_message` écrit en base.
5. **Sauvegarde et reprise** : §6.7.

## 6. Conception détaillée

### 6.1 Modèle de contenu

- **Projet** : slug, titre, résumé, description (Markdown), type (perso / pro / école), statut (en cours / terminé / archivé), dates, client, liens (dépôt, démo : absents pour les projets privés), technologies, galerie d'images avec légendes, fiche technique en sections, mise en avant (booléen « vitrine », un seul projet à la fois), état brouillon / publié.
- **Fiche technique, sections libres** (colonne vertébrale du site et du RAG) : l'auteur crée les sections de chaque projet, autant qu'il en veut, chacune un titre, une ancre stable et un corps en Markdown, et les ordonne ; aucune n'est obligatoire, aucun titre n'est imposé (D57).
- **Technologie** : nom, type (langage / framework / infra / outil), icône, site.
- **Document** (phase 2) : fichier sur R2, type, langue, visibilité (`public` téléchargeable, `rag_only` indexé mais jamais servi en entier, `private` jamais indexé), état d'indexation, hash de contenu.
- **Profil** : compétences, expériences, formation, langues, disponibilité ; faits exacts pour le RAG. Aucune page « à propos » : le site ne présente l'auteur que par deux liens (GitHub, LinkedIn), en colonne fixe en bas à droite de la fenêtre quand la marge à côté de la grille le permet, en pied de page sinon (`docs/specification-ux.md` §1.13) ; le CV public est servi par le chatbot (phase 2).
- **Message** (phase 3) : reçu via le MCP, lu dans l'admin.

### 6.2 Back-office

- Django admin, un seul superutilisateur créé par commande ; aucun groupe ni permission personnalisée ; écrans « Groupes », « Utilisateurs » et appareils OTP retirés (D64).
- Ajustements : éditeur Markdown, aperçus d'images, état d'indexation, bouton « ré-indexer », boîte de réception des messages, lignes ordonnées par glisser-déposer (D55).
- Accessible uniquement derrière Cloudflare Access (identité Google ou GitHub), mot de passe fort et 2FA.
- `INSTALLED_APPS`, middlewares et réglages limités au strict utilisé (l'admin impose `auth`, `contenttypes`, `sessions`, `messages`).

### 6.3 RAG (phase 2)

- **Centralisation** : Postgres est le point unique ; table de documents sources, table de chunks avec embeddings (pgvector) et métadonnées (projet, section, type de source, date). Les images ne sont pas des sources ; leurs légendes le sont.
- **Ingestion** : événementielle via outbox (§5.4), idempotente, hash de contenu (rien n'est ré-embeddé s'il n'a pas changé), version d'index par document avec remplacement atomique, retries et dead-letter, commande de ré-indexation complète. Pipeline linéaire en fonctions simples dans le worker, tracées dans LangSmith (pas de graphe pour l'ingestion). PDF parsés avec un outil conscient de la mise en page (Docling ou Unstructured) ; contextual retrieval (préfixe de contexte par chunk généré par LLM) en démonstration avancée.
- **Retrieval** : hybride (BM25 via `tsvector` + vecteurs) fusionné par RRF, filtres par métadonnées, reranking, réécriture de requête et multi-query en parallèle, 5 à 8 chunks finaux.
- **Génération** : Claude via l'API Anthropic ; `claude-opus-5` pour la réponse finale, `claude-haiku-4-5` pour les étapes bon marché (routage, réécriture, garde-fous) ; `claude-sonnet-5` en option si le coût par conversation doit baisser. Citations natives (blocs `document` + `citations`) avec liens profonds vers la fiche et la section. Prompt caching sur le system prompt.
- **Embeddings et reranking** : modèles open source auto-hébergés, `bge-m3` (multilingue) et `bge-reranker-v2-m3`, servis par un conteneur `text-embeddings-inference` sur CPU ; aucune API externe pour cette partie ; VPS porté à 8 Go en phase 2. La génération reste chez Claude : un LLM local sur un VPS sans GPU n'est pas réaliste.
- **Mémoire de conversation** : checkpointer LangGraph sur Postgres, identifiant de fil anonyme côté client, rétention 30 jours.
- **Streaming** : SSE token par token et étapes intermédiaires (« recherche », « reranking », « rédaction »).
- **Politique de réponse** : uniquement à partir des sources, refus poli du hors-sujet, langue du visiteur, aucune donnée personnelle hors contenu public.
- **Évaluation** : 30 à 50 questions-réponses de référence dans un dataset LangSmith ; évaluateurs de fidélité, pertinence et précision du contexte ; exécutés en CI à chaque changement de prompt ou de pipeline ; feedback pouce haut / bas renvoyé vers LangSmith.
- **Coûts** : limites par IP et par session, plafond global journalier avec coupe-circuit, `max_tokens` bornés.

### 6.4 LangGraph et LangSmith

- **LangChain** : bibliothèque de composants (chargeurs, découpeurs, connecteurs pgvector, wrapper Anthropic) ; utilisée pour ce qu'elle apporte, sans chaînes toutes faites héritées.
- **LangGraph** : orchestration du chat ; nœuds écrits par nous ; fonctionnalités mises en avant : état typé avec reducers, routage conditionnel, parallélisme (`Send`), sous-graphes, checkpointing Postgres, retries et fallbacks, streaming multi-modes, interruptions human-in-the-loop, time-travel pour le debug. Studio (`langgraph dev`) en local pour apprendre ; en production, graphe embarqué dans FastAPI.
- **LangSmith** : service d'observabilité hébergé par LangChain (cloud, région UE, offre gratuite avec quota mensuel, rétention courte). Notre code lui envoie des traces de chaque exécution : entrées et sorties de chaque nœud, durées, tokens, erreurs. Envoi asynchrone : le chatbot fonctionne si LangSmith est indisponible. Aucune IP ni identifiant nominatif dans les traces.
- **Page « LangGraph » publique** : (a) statistiques agrégées via l'API LangSmith servies par le backend avec cache, (b) trace de la conversation du visiteur (étapes, durées, chunks).
- **Apprentissage** : `docs/learning/langgraph.md`, document vivant expliquant chaque concept au moment où il est utilisé.

### 6.5 MCP (phase 3)

- Transport Streamable HTTP sur `mcp.pacome.dev` ; SDK Python `mcp` (FastMCP) dans un conteneur dédié partageant le package commun.
- Outils : `list_projects`, `get_project`, `search_portfolio` (retrieval seul : chunks + sources), `get_profile`, `send_message` (écrit en base). Ressources `portfolio://projects/{slug}` ; prompts prédéfinis.
- Le chatbot du site consomme les mêmes outils (une seule surface, dogfooding).
- Lecture anonyme avec rate limiting ; `send_message` authentifié (OAuth 2.1 selon le standard MCP, ou jeton délivré sur le site après Turnstile) ; limites de taille, préfiltre de modération.
- Page « comment se connecter » avec les configurations pour Claude.ai, Claude Desktop, Claude Code, ChatGPT, Cursor, VS Code.

### 6.6 Sécurité et confidentialité

- **Modèle de menace** : abus de coût du LLM, spam via `send_message`, injection de prompt via l'entrée utilisateur, fuite de données personnelles, XSS via le rendu Markdown, upload malveillant dans l'admin, SSRF, compromission de l'admin, fuite de secrets, dépendances vulnérables.
- **Périmètre** : Cloudflare (WAF et protection DDoS fournis sans implémentation, rate limiting, Access, IP du VPS masquée ; Turnstile optionnel en phase 2 si abus constatés) ; Cloudflare Tunnel (aucun port web ouvert sur le VPS) ; Caddy ; pare-feu du VPS (SSH seul) ; aucun port interne exposé.
- **Application** : rate limiting par IP et par session (compteurs Redis), plafond de budget journalier, system prompt durci, contenu récupéré traité comme donnée, sorties structurées pour le routage, filtrage de sortie, refus hors périmètre, journalisation des tentatives d'abus.
- **Admin** : Cloudflare Access + mot de passe fort + 2FA, un seul compte, journal d'audit.
- **Secrets** : 12-factor, `.env` en développement seulement, secrets hors serveur en production (gestionnaire de mots de passe, secrets GitHub Actions), rotation documentée.
- **Chaîne d'approvisionnement** : lockfiles, Renovate ou Dependabot, scan des images (Trivy), `pip-audit` et `npm audit` en CI (D44).
- **HTTP** : HTTPS partout (`.dev` est en HSTS préchargé), CSP stricte, CORS restreint, CSRF sur l'admin, en-têtes de sécurité.
- **Confidentialité** : page statique décrivant ce qui est collecté, pourquoi, les sous-traitants (Anthropic, LangChain, Cloudflare, hébergeur), les durées de conservation (30 jours pour les conversations) et les droits ; pas de cookie tiers ; hébergement en UE.

### 6.7 Exploitation

- **Déploiement** : VPS en UE, Docker Compose, Caddy ; images construites et publiées par GitHub Actions ; déploiement par SSH (`docker compose pull && up`), migrations automatiques ; pas d'environnement de staging (à réévaluer).
- **Environnements** : développement local complet en Docker Compose (Postgres, Redis, stockage disque, `langgraph dev`) ; production.
- **Observabilité** : logs structurés JSON, Sentry (erreurs), healthchecks.io (sauvegardes) ; surveillance de disponibilité externe écartée (surdimensionnée pour ce trafic) ; OpenTelemetry entre services et Prometheus + Grafana seulement si un besoin de démonstration apparaît.
- **Dégradation gracieuse** : le site fonctionne si `ai`, LangSmith ou l'API Claude est indisponible (chat masqué ou message clair) ; healthchecks, timeouts, circuit breaker, politiques de redémarrage.
- **Redis** : cache applicatif (réponses d'API, pages projets, statistiques de la page LangGraph) avec invalidation à la sauvegarde via les signaux Django, TTL courts, jamais source de vérité ; puis broker et rate limiting. Côté HTTP : `Cache-Control`, `ETag`, images WebP redimensionnées, CDN Cloudflare.
- **Sauvegardes et plan de reprise** : objectifs RPO 24 h (au pire, la journée écoulée est perdue) et RTO 1 h (site de nouveau en ligne en moins d'une heure). Postgres est l'unique composant stateful ; les fichiers sont sur R2, durable par construction. Plan en huit points :
  1. `infra/` versionné : `compose.yml`, `Caddyfile`, `bootstrap.sh` (Docker, utilisateur, pare-feu, images, `.env` à partir des secrets), `RUNBOOK.md`.
  2. Secrets hors du serveur : gestionnaire de mots de passe et secrets GitHub Actions ; la clé de chiffrement des sauvegardes n'est jamais uniquement sur le VPS.
  3. Sauvegarde nocturne : `pg_dump` → chiffrement `age` → `rclone` vers le bucket R2 `portfolio-backups` → ping healthchecks.io ; rétention 7 quotidiennes + 4 hebdomadaires.
  4. Restauration en une commande, `make restore BACKUP=<date>` : téléchargement, déchiffrement, `pg_restore`, vérification des migrations, test de fumée ; documentée dans le runbook.
  5. Test de restauration automatisé et mensuel dans un Postgres jetable, avec requête de contrôle et alerte en cas d'échec.
  6. Scénario « le VPS a disparu » : louer un VPS, `bootstrap.sh` — le Tunnel reprend les noms d'hôte avec son jeton (D45, D58) —, `make restore`, vérifier ; médias déjà sur R2.
  7. La configuration Cloudflare (DNS, Access, Turnstile) est un état : documentée dans le runbook ; Terraform avec le provider Cloudflare en option (ADR).
  8. Snapshots du fournisseur (~1 €/mois) en complément, jamais en remplacement.
- **Domaine** : `pacome.dev`, acheté chez Cloudflare Registrar avant le premier déploiement (tarif à vérifier, premium possible). Sous-domaines : `www` (ou apex) pour le site, `api`, `media` (R2), `mcp` ; admin derrière Access.
- **Estimation mensuelle** (à confirmer dans les ADR) :

| Brique | Solution | Par mois |
|---|---|---|
| VPS 1 vCPU / 2 Go | Hetzner CPX12 ; OVH VPS-1 quand il revient en stock | 5 à 15 € |
| VPS 8 Go à partir de la phase 2 (modèles locaux) | Hetzner CX32 ou équivalent | 7 à 12 € |
| Domaine `.dev` | Cloudflare Registrar | ~1 € |
| Cloudflare, R2, healthchecks.io, Sentry, LangSmith, GitHub Actions | Offres gratuites | 0 |
| API Claude + embeddings | Usage réel, trafic faible | 5 à 15 € |
| Snapshots du fournisseur (optionnel) | Hetzner, OVH | ~1 € |
| **Total** | | **11 à 32 €** |

## 7. Registre des décisions

Identifiants hérités du cadrage v0 (D1 à D38), sans trou ni renumérotation. Une décision remplacée reste ici, marquée « remplacée par » ; le pourquoi de chaque brique est dans l'ADR indiqué en §5.2.

**Périmètre et principes**

| # | Décision | Note |
|---|---|---|
| D1 | Un back-office est nécessaire | L'idée « éditer le contenu via le MCP » est abandonnée. |
| D3 | Le premier projet présenté est le portfolio lui-même | Fiche méta : site, RAG, MCP. |
| D6 | Simplicité d'abord, pas de sur-ingénierie gratuite | Mais une architecture décomposée en briques modulaires, chacune justifiée. |
| D7 | Services managés plutôt qu'auto-hébergement | Exception assumée : VPS unique (D19, D32). |
| D8 | ADR dès le début | Format MADR dans `docs/adr/`. |
| D9 | Budget global ≈ 50 € / mois maximum | Sans brider le projet. |
| D10 | Pas de délai, livraison incrémentale | Blocs assemblés via des issues. |
| D11 | Dépôt privé (révisable) | Conçu comme s'il était public. |
| D12 | Repartir de zéro | Ancien historique Django + Flutter supprimé localement le 2026-09-10 ; reste sur GitHub, sans valeur de référence. |
| D14 | Contenu public par nature | Projets privés : captures, langages, outils ; CV en version publique. |
| D15 | (remplacée par D44) | — |
| D24 | Pas d'email | Conçu sans ; post-MVP, peut-être jamais. |
| D27 | Code minimal | Chaque ligne sert un but ; règle de revue inscrite dans la configuration Claude Code. |
| D28, D34 | Contenu FR seul, jamais en dur | Catalogue de chaînes unique ; pas de plomberie multilingue anticipée. |
| D46 | Accueil = grille de cartes projet | Remplace « liste d'icônes façon écran d'accueil de téléphone » (2026-09-19) ; style et mouvement dans `docs/specification-ux.md`. |
| D47 | Pas de page « à propos » | Profil réservé au RAG ; GitHub et LinkedIn seuls liens vers l'auteur (placement : D49) ; CV public via le chatbot en phase 2 (2026-09-19). |
| D48 | Projet « vitrine » | Booléen sur Projet, un seul à la fois, choisi dans l'admin ; sa carte est double et ouvre la table, avant l'ordre automatique de `docs/specification-ux.md` §1.9 (2026-09-22). |
| D49 | Liens GitHub et LinkedIn en colonne fixe | En bas à droite de la fenêtre dès que la marge à côté de la grille le permet, en pied de page sinon ; seuil et valeurs dans `docs/specification-ux.md` §1.13 et §3 (2026-09-22). |
| D50 | Adresse de fiche inconnue → accueil | `/projets/<slug>` sans projet publié : redirection `302` vers `/`, aucune page 404 ; remplace le point « slug inconnu » de l'ADR 0008 (ADR 0009, 2026-09-22). |

**Stack et hébergement**

| # | Décision | Note |
|---|---|---|
| D17, D27 | Backend Django | Choisi pour ses mérites propres : admin, ORM, sécurité par défaut, écosystème. |
| D16 | Back-office = Django admin personnalisé | Content-as-code et CMS headless rejetés. |
| D19 | Hébergement = un VPS unique, Docker Compose | PaaS et tout managé écartés pour le coût ; Kubernetes hors de propos. |
| D23 | Cloudflare devant le VPS | DNS, proxy, CDN, WAF, Turnstile, Access. |
| D25, D30 | Médias et documents sur Cloudflare R2 | Via `django-storages` ; disque local en développement. Remplace D21. |
| D32 | Postgres reste sur le VPS | Unique composant stateful ; à réexaminer si perte tolérée < 24 h, plusieurs consommateurs de la base, ou besoin de plusieurs serveurs. |
| D20 | Redis dès la phase 1 | Cache avec invalidation, puis broker et rate limiting. |
| D26, D33, D38 | Sauvegardes et plan de reprise | Huit points, RPO 24 h, RTO 1 h (§6.7). |
| D36, D37 | Domaine `pacome.dev` chez Cloudflare Registrar | Sous-domaines `www`, `api`, `media`, `mcp`. |
| D39 | Embeddings et reranking en modèles open source locaux | `bge-m3` + `bge-reranker-v2-m3` via `text-embeddings-inference` ; Voyage AI écarté ; VPS 8 Go en phase 2. |
| D40 | Surveillance de disponibilité écartée | Surdimensionnée pour ce trafic ; healthchecks.io conservé pour les sauvegardes. |
| D41 | Turnstile optionnel | Produit Cloudflare, hors phase 1 ; en phase 2 seulement si abus constatés. WAF et DDoS : fournis par Cloudflare sans implémentation. |
| D42 | Conteneur `backup` dédié confirmé | Postgres fournit `pg_dump` mais rien ne l'ordonnance ; un conteneur cron isolé, versionné dans Compose, avec ses propres droits. |
| D43 | GHCR confirmé | Les images sont construites en CI et tirées par le VPS ; aucun build sur le serveur ; gratuit, sans exploitation. |
| D44 | Frontend = Vite + React + TypeScript + Tailwind CSS + shadcn/ui | Compilé en CI, servi en statique par Caddy, aucun Node en production ; Next.js écarté. Compléments : motion, react-bits, bklit-ui, Rive, `openapi-typescript` (`docs/frontend-outillage.md` §3). Remplace D15. |
| D45 | Origine reliée à Cloudflare par Tunnel | Aucun port web ouvert sur le VPS ; `cloudflared` sort vers Cloudflare ; Caddy reste reverse proxy interne, sans TLS. Remplace « Caddy seul conteneur exposé 80/443 » (2026-09-18). |
| D51 | Rendu du Markdown dans le front | L'API envoie la description et les sections en Markdown (JSON) ; le front les rend en éléments React avec `markdown-to-jsx`, HTML brut échappé ; `markdown-it-py` + `nh3` réservés à l'aperçu de l'admin ; Vitest entre en phase 1 pour la logique pure du front (ADR 0010, 2026-09-22). |
| D52 | Le squelette du monorepo est une structure d'accueil | Cible de §9 inchangée ; chaque dossier naît avec sa première brique, jamais avant (P4) ; `packages/` au premier module partagé par deux applications ; aucune importation entre applications, communication par Postgres et HTTP (2026-09-23). |
| D53 | Le bloc d'aperçu du gabarit porte cinq balises | `<title>`, `<meta name="description">`, `og:title`, `og:description` et `og:image` du projet, injectées par la vue de `/projets/<slug>` ; `description` et `og:description` portent le même texte, et le gabarit n'a pas d'`og:image` par défaut. Sans `description`, le score SEO tombe à 91, sous le seuil de la spec §1.16. Remplace le point « balises injectées » de D44 (ADR 0011, 2026-09-24). |
| D54 | Deux fichiers Compose, mêmes images | `infra/compose.dev.yml` sur le poste, `infra/compose.yml` en production ; mêmes images, même point d'entrée, mêmes services de données ; ce qui diverge est propre à l'environnement (ports, code monté, `runserver` / Caddy, Tunnel, backup) ; le worker est dans les deux fichiers (D60). Remplace le point « environnement identique » de D19 et l'argument « un seul fichier Compose » de D32 (ADR 0012, 2026-09-24). |
| D55 | Lignes de l'admin ordonnées par glisser-déposer | Technologies d'un projet, puis galerie de #9 : l'auteur fait glisser les lignes, enregistrées ou neuves, ou les déplace au clavier ; la position cachée suit l'ordre affiché à l'enregistrement ; script du projet, sans bibliothèque (ADR 0013, 2026-09-27). |
| D56 | CI/CD : GitHub Actions et GHCR | Une image par dossier `infra/<service>/` ; front compilé une fois, copié dans `caddy` et, pour `index.html`, dans `api` ; statiques de l'admin servis par WhiteNoise depuis `api`, qui repose sur Debian 13 ; Trivy bloque HIGH et CRITICAL, corrigeables ou non, et la fin de vie, toute exception étant datée et évaluée en trois points ; publication par un job `publish` sur `main`, SHA et `latest`, trois versions gardées, ni attestation ni SBOM ; confirme D43 (ADR 0014, 2026-09-27). |
| D57 | Fiche technique en sections libres | L'auteur crée, nomme, ordonne (glisser-déposer, D55) et retire les sections de chaque projet ; ancre en forme de slug, préremplie depuis le titre, modifiable, unique dans le projet, citée par `#s-<ancre>` ; remplace les onze sections normalisées de §6.1 (arrêt visuel de la PR #66, 2026-10-03). |
| D58 | Reprise d'un VPS sans geste DNS | Le Tunnel suit son jeton : un VPS neuf amorcé par `bootstrap.sh` reprend les noms d'hôte dès que `cloudflared` y est sain ; remplace « pointer le DNS Cloudflare » du scénario 6 de §6.7 et du point 6 de l'ADR 0007 (précision de D45, interrogatoire de #24, 2026-10-15). |
| D59 | Worker : Celery, variantes par Pillow seul | Celery, broker Redis, sans backend de résultats, concurrence 1, accusé de réception par défaut ; le Redis partagé n'évince jamais la file (politique `volatile-*`) ; tâche enfilée après validation de la transaction, sans outbox pour les images (l'outbox reste celle de l'ingestion, D31) ; variantes WebP par Pillow seul ; remplace le point `django-imagekit` des ADR 0001 et 0004 et, pour le worker d'images, la règle « outbox » de l'ADR 0006 ; rôle 2 « broker » de l'ADR 0006 avancé en phase 1 (ADR 0015, 2026-10-16). |
| D60 | Un worker vit dans les deux fichiers Compose | Tout worker est un service de `infra/compose.dev.yml` et de `infra/compose.yml`, défini de la même façon des deux côtés — image, commande, variables du service dont il partage l'image ; seul diverge ce qui est propre à l'environnement, et aucun worker n'est propre à un environnement. Remplace « le worker » parmi ce que la production porte en propre dans D54 et dans l'ADR 0012 (ADR 0016, 2026-10-16). |
| D61 | Les jobs de la CI selon le delta d'une PR | Sur une PR, `web` et `infra` ne tournent que si le delta touche leurs fichiers — règle de `infra/ci/changed_jobs.py`, lu par la première étape du job `api`, liste d'exclusion pour `infra` — et partent après `api`, même rouge ; sur un push vers `main`, tout tourne. Un push annule le run en cours de la même PR, jamais sur `main` ; le passage en ready ne déclenche plus de run. Remplace le point « Scan : Trivy, sur chaque PR » de l'ADR 0014 (ADR 0017, 2026-10-20). |
| D62 | Binaires Go compilés par le projet | `age`, `age-keygen`, `rclone` et `caddy` compilés dans un étage `golang:<x.y.z>-alpine` épinglé, que suit Dependabot : chaque montée de Go, une PR Dependabot par image, recompile ses binaires ; chacun sous la forme de sa release officielle, à sa version exacte, modules inchangés — on change le compilateur, jamais le graphe de dépendances ; `caddy` reste construit sur son image officielle, dont seul le binaire est remplacé, version compilée égale à son étiquette ; `supercronic` reste un fichier de release à somme épinglée ; modules téléchargés sous la base de sommes de Go, caches hors du layer ; exerce une condition de réexamen de l'ADR 0014 (D56), sans le remplacer (ADR 0018, 2026-10-21). |
| D63 | Runs de CI au passage en ready, portes d'avis planifiées | Une PR en draft ne déclenche aucun run : le premier vient du passage en ready, puis chaque push ; après ready, jamais de push sur une tête rouge sans tri. pip-audit, npm audit et Trivy sortent des jobs de PR : planifiés chaque jour sur `main`, joués sur une PR qui touche leurs entrées (manifestes, verrous, Dockerfiles, exceptions), et avant chaque publication ; `web` et `infra` attendent un `api` vert ; Dependabot passe en mensuel. Remplace, dans D61, « partent après `api`, même rouge » et « le passage en ready ne déclenche plus de run », et deux autres points de l'ADR 0017 — l'ouverture seule d'une draft sautée, le scan sur chaque PR hors harnais — ; renverse la décision « portes à base d'avis (…) sans horloge » de #77 (ADR 0019, 2026-10-28). |
| D64 | Ni comptes ni appareils dans l'admin | « Groupes », « Utilisateurs » et les appareils OTP — application TOTP, codes de secours — n'y ont pas d'écran : le compte unique vient d'une commande, son second facteur d'une autre, et un écran serait une autre voie d'en ajouter un. Précise « écran « Groupes » retiré » de §6.2 (vérification visuelle du lot 1 de #7, 2026-09-26 ; go du briefing de #6, 2026-10-28). |
| D65 | CSP et en-têtes de sécurité par la brique native de Django | `SECURE_CSP`, `ContentSecurityPolicyMiddleware` et le processeur de contexte `csp` au lieu de `django-csp` : les gabarits de l'admin (Django 6.1.2) ne lisent que le nonce natif (`{% csp_nonce_attr %}`) ; aucune source tierce, seul l'hôte des médias du projet entre en `img-src` sous R2 ; `SecurityMiddleware` aux défauts de Django. Remplace le point « `django-csp` » de l'ADR 0001 (go du briefing de #6, 2026-10-28 ; ADR 0020). |
| D66 | Noms des buckets R2 préfixés par le projet | `portfolio-<usage>` : `portfolio-medias`, `portfolio-backups`, pour lire le projet d'un bucket dans la liste du compte. Remplace le nom `backups` des ADR 0004 et 0007 (décision du mainteneur, #25, 2026-10-30 ; ADR 0021). |
| D67 | KeePassXC comme gestionnaire de mots de passe | Un fichier chiffré local, copié à la main hors du poste : sans cette copie, la perte du poste emporterait la clé `age` et donc les sauvegardes. Remplace la mention « Bitwarden ou 1Password » de l'ADR 0007 (décision du mainteneur, #25, 2026-10-31 ; ADR 0022). |
| D68 | VPS de phase 1 : x86, 1 vCPU et 2 Go au minimum | Hetzner CPX12 à 14,39 € TTC par mois : aucun VPS de 4 Go commandable en UE au prix prévu, et une pile mesurée à 262 Mio au repos. Remplace le point « Machine » de l'ADR 0002 pour la phase 1 (décision du mainteneur, #25, 2026-10-31 ; ADR 0023). |
| D29 | (remplacée par D36, D37) | — |
| D21 | (remplacée par D25) | — |

**Contenu et RAG**

| # | Décision | Note |
|---|---|---|
| D2, D18 | LangChain + LangGraph + LangSmith | Écosystème utilisé en entier ; LangGraph pour le chat ; ingestion en fonctions simples tracées. |
| D31 | Détection des ajouts et retraits de documents | Tout passe par l'admin ; outbox → worker ; hash de contenu ; la base est la source de vérité. |
| D35 | LangSmith cloud accepté | Région UE, rétention courte, page de confidentialité. |

**MCP**

| # | Décision | Note |
|---|---|---|
| D5, D13, D22 | MCP en lecture seule + `send_message`, option « recherche » | Le LLM du visiteur rédige ; commentaires retirés ; `send_message` écrit en base. |

## 8. Méthode de travail

1. **Avant toute ligne de code** : configuration Claude Code du projet (`CLAUDE.md`, règles dont « chaque ligne sert un but », skills, agents, hooks) et pipeline de développement.
2. **Flux** : issue → branche → pull request → CI (lint, types, tests, scans) → merge → déploiement. Conventional commits.
3. **ADR** : un fichier MADR par décision structurante dans `docs/adr/`, écrit au moment de la décision, indexé dans le RAG et cité par la fiche du méta-projet.
4. **Qualité** : Python 3.12+, `uv`, `ruff`, `pyright` strict, `pytest`, `pre-commit` ; TypeScript strict, ESLint avec `jsx-a11y`, Playwright + axe, Lighthouse CI (D44). Tests unitaires (découpage, parseurs, garde-fous), intégration (API + base via testcontainers), E2E Playwright (site et chat), évaluations RAG, tests de contrat MCP, scan sécurité.
5. **Apprentissage** : `docs/learning/` alimenté au fil de l'eau.

## 9. Prochaines étapes

1. Configuration Claude Code et pipeline de développement (§8.1).
2. Squelette du monorepo (D52) : une **structure d'accueil**, pas des dossiers vides. Cible : `apps/api`, `apps/web`, `apps/ai`, `apps/mcp`, `packages/`, `infra/`, `docs/`. Espace de travail `uv` à la racine dont les membres sont déclarés par motif (`apps/*`, `packages/*`) ; `infra/` avec un conteneur par service ; `docs/` unique. Chaque dossier naît avec sa première brique, jamais avant (P4) ; `packages/` naît avec le premier module partagé par deux applications. Les applications ne s'importent pas entre elles : elles communiquent par Postgres et par HTTP, et ce qu'elles partagent va dans `packages/`.
3. ADR initiaux — écrits le 2026-09-18 (`docs/adr/` 0001 à 0008) : Django, VPS + Compose, Cloudflare, R2, Postgres sur le VPS, Redis, sauvegardes, frontend (D44). Le worker n'en fait pas partie : ADR à sa phase, l'ADR 0015 (D59), en phase 1.
4. Modèle de contenu, admin personnalisé, API.
5. Première fiche : le méta-projet.
6. `infra/` : Compose, Caddy, bootstrap, sauvegardes, runbook ; CI/CD ; premier déploiement sur `pacome.dev`.
7. Frontend (`apps/web`, D44), puis mise en production de la phase 1.
8. Phase 2, puis phase 3.

---

## Annexe A — Questions résiduelles (non bloquantes)

Recos appliquées par défaut ; chaque point sera tranché par un ADR au moment où sa phase commence.

| Sujet | Reco par défaut |
|---|---|
| Worker : Celery ou arq | Tranché par l'ADR 0015 (D59) : Celery, broker Redis ; arq et `django.tasks` écartés. |
| Serveur des modèles locaux : `text-embeddings-inference` ou Ollama | TEI par défaut (CPU, embeddings et reranking dans un seul conteneur). |
| Répartition des modèles Claude | `claude-opus-5` réponse finale, `claude-haiku-4-5` étapes bon marché ; `claude-sonnet-5` en option coût. |
| Latence d'ingestion acceptable | Minutes. |
| Rétention des conversations | 30 jours. |
| Jeu d'évaluation | 30 à 50 questions-réponses, évaluateurs en CI. |
| Fonctionnalités LangGraph prioritaires | Routage, parallélisme, checkpointing, streaming, interruptions. |
| Déploiement du graphe | Embarqué dans FastAPI ; Studio en local. |
| Gestionnaire de secrets (Vault, Infisical) | Non ; gestionnaire de mots de passe + secrets GitHub. |
| SBOM, Trivy | Tranché par l'ADR 0014 (D56) : Trivy bloquant ; ni SBOM ni attestation de provenance. |
| Authentification `send_message` | OAuth 2.1 ou jeton après Turnstile ; ADR en phase 3. |
| Staging | Non ; à réévaluer. |
| Observabilité avancée (OpenTelemetry, Grafana) | Seulement si besoin de démonstration. |
| Objectif de couverture de tests | Pragmatique ; évaluations RAG et E2E prioritaires. |
| Contenu disponible au départ (nombre de projets, CV) | À inventorier au démarrage de la phase 1. |

## Annexe B — Glossaire

- **ADR** : Architecture Decision Record, court document qui consigne une décision, son contexte, les options écartées et les conséquences.
- **Cache** : copie temporaire d'un résultat coûteux (réponse d'API, page) gardée en mémoire (Redis) pour répondre plus vite ; doit être invalidée quand la donnée change.
- **CDN** : réseau de serveurs répartis qui gardent des copies des fichiers statiques au plus près des visiteurs.
- **Chunk** : fragment de texte de taille bornée, unité d'indexation et de recherche du RAG.
- **Conteneur** : processus isolé avec ses dépendances, lancé depuis une image Docker ; un conteneur par service (Caddy, Django, Postgres, Redis, worker, backup, IA, MCP).
- **Dead man's switch** : dispositif qui alerte quand un signal attendu ne vient pas (healthchecks.io pour les sauvegardes).
- **Embedding** : vecteur numérique représentant le sens d'un texte, comparé par similarité.
- **GHCR** : GitHub Container Registry, entrepôt d'images Docker lié au dépôt GitHub ; la CI y publie les images, le VPS les tire.
- **Headless CMS** : outil de gestion de contenu sans partie visible, consommé par API.
- **Idempotent** : rejouer la même opération produit le même résultat, sans doublon ni effet supplémentaire.
- **Infrastructure as code** : décrire serveurs, DNS, règles et buckets dans des fichiers versionnés qu'un outil (Terraform) applique ; reproductible et relisible.
- **Outbox** : table où l'application écrit des événements dans la même transaction que la donnée ; un worker les consomme ensuite. Garantit qu'aucun changement n'est perdu.
- **PaaS** : plateforme qui exécute des conteneurs sans qu'on gère de serveur.
- **RAG** : Retrieval-Augmented Generation ; le LLM répond à partir de passages retrouvés dans une base de connaissances.
- **Rate limiting** : plafond de requêtes par client et par fenêtre de temps (ex. 60 par minute par IP) ; au-delà, réponse 429. Appliqué au bord (Cloudflare) et dans l'application (compteurs Redis).
- **Reranking** : second tri des passages retrouvés par un modèle spécialisé, plus précis que la recherche initiale.
- **Reverse proxy** : serveur placé devant les services (Caddy) qui reçoit tout le trafic et route chaque requête vers le bon conteneur selon le nom d'hôte et le chemin.
- **RPO / RTO** : perte de données maximale tolérée / durée maximale de remise en service.
- **Stateful** : se dit d'une machine qui détient des données non régénérables.
- **Surveillance de disponibilité** : service externe (BetterStack, UptimeRobot) qui appelle le site toutes les quelques minutes depuis l'extérieur et alerte s'il ne répond plus ; externe, car un outil sur le VPS ne peut pas signaler que le VPS est tombé.
- **Terraform** : outil d'infrastructure as code ; en option ici pour la configuration Cloudflare.
- **Trace** : enregistrement complet d'une exécution (entrées, sorties, durées, tokens) envoyé à LangSmith.
- **Turnstile** : captcha invisible de Cloudflare ; un script dans la page produit un jeton vérifié côté serveur, sans énigme à résoudre pour un humain.
- **Voyage AI** : fournisseur d'API spécialisé dans les modèles d'embeddings et de reranking, recommandé par Anthropic qui n'en propose pas ; alternative locale : `bge-m3`.
- **VPS** : machine virtuelle louée, administrée par soi-même.
- **WAF** : Web Application Firewall, filtre devant le site qui inspecte chaque requête HTTP et bloque les attaques connues (injections, XSS, bots malveillants, exploits) ; distinct du pare-feu réseau qui ne voit que ports et adresses.
- **Worker** : processus de fond qui exécute les tâches longues ou différées (vignettes, ingestion) hors des requêtes web, en lisant une file de tâches.

## Annexe C — Bibliothèques pressenties (phases 2 et 3)

Non normatif : chaque ligne est à confirmer par l'ADR de sa brique au moment où sa phase commence. Les bibliothèques de la phase 1 sont fixées par les ADR de `docs/adr/`.

| Phase | Brique | Bibliothèques pressenties |
|---|---|---|
| 2 | Ingestion (worker) | Docling ou Unstructured, `pypdf`, `langchain-text-splitters`, `langchain-huggingface`, `langsmith`, `httpx` |
| 2 | Service IA (`ai`) | FastAPI, `uvicorn`, `sse-starlette`, LangGraph, `langgraph-checkpoint-postgres`, `langchain-core`, `langchain-anthropic`, `anthropic`, `langchain-postgres`, `langchain-huggingface`, `langsmith`, `redis`, `httpx` |
| 2 | Embeddings et reranking | `text-embeddings-inference`, `BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3` |
| 2 | Studio en local | `langgraph-cli` (`langgraph dev`) |
| 3 | MCP | `mcp` (FastMCP), `langchain-mcp-adapters` (le chat consomme les mêmes outils), MCP Inspector pour les tests de contrat, `PyJWT` si `send_message` passe par un jeton |
