> Archive : brouillon v0 du cadrage et journal complet des six tours de questions-réponses (2026-09-10 et 11). Remplacé par [../cadrage-technique.md](../cadrage-technique.md) (v1). Conservé pour la traçabilité des décisions D1-D38 ; ne plus modifier.

# Portfolio — Cadrage technique (v0)

_Date : 2026-09-10 · Version 0.1 : premières réponses intégrées (section 8). Questions restantes en 8.3._
_Le design (UI/UX) est volontairement hors périmètre de ce document._

---

## 1. Finalité

- Portfolio personnel dont l'objectif est de **prouver la capacité à monter un projet de bout en bout** (conception, backend, sécurité, workers, IA, déploiement) et à produire un visuel correct.
- Peu de projets au départ : le portfolio est un **contenant conçu pour être rempli au fil du temps**. Ajouter un projet ne doit jamais nécessiter de toucher au code.
- **Le portfolio est lui-même le premier projet présenté** (méta-projet). Sa fiche décrit le fonctionnement du site, du RAG et du MCP, et sert de gabarit pour toutes les fiches suivantes.

## 2. Phases

Les phases sont strictement séquentielles : on n'attaque la suivante que lorsque la précédente est solide et en place (réponse du 2026-09-10).

### Phase 1 — MVP portfolio (back + front, contenu + fiche technique)

- Accueil : liste d'icônes représentant les projets (façon écran d'accueil de téléphone).
- Clic sur une icône → fiche projet (modal) contenant :
  - un titre, un texte de description, des tags (langages / technologies) ;
  - des images et du texte ;
  - une véritable fiche technique : où est le backend, où est la sécurité, y a-t-il des workers et où sont-ils, etc.
- Un moyen d'ajouter et d'éditer des projets (back-office). Décision prise : nécessaire (voir §4).

### Phase 2 — Chatbot RAG intégré au site

- Chatbot « volontairement trop complexe » : vitrine de compétences, le plus propre, le plus solide et le plus sécurisé possible.
- Sources de connaissance :
  1. les données des projets (base du site) ;
  2. des documents stockés côté backend : CV, récits d'expériences professionnelles, autres documents « sur moi ».
- Périmètre des questions : les projets du site et l'auteur en tant que personne.
- Pipeline complet : récupération → centralisation → chunking → embedding → indexation → retrieval → génération.
- **Ré-indexation automatique** à chaque projet ajouté ou modifié, et à chaque document modifié.
- **LangGraph** imposé pour l'orchestration, **LangSmith** pour le monitoring. Objectif d'apprentissage explicite : exploiter le framework au maximum.
- Une **page « LangGraph » visible** sur le site pour montrer l'usage de l'outil.

### Phase 3 — MCP public (périmètre encore flou)

- Serveur MCP ouvert : un visiteur connecte son Claude (ou tout autre client MCP) et interroge le RAG directement depuis son outil.
- Lecture seule : le LLM du visiteur lit les fiches et interroge la base de connaissances comme s'il était sur le chatbot du site ; c'est lui qui rédige la réponse.
- Une seule action d'écriture : m'envoyer un message (email automatique). Les commentaires sont retirés du périmètre (réponse du 2026-09-10).
- Objectif : montrer que je sais **donner de l'information et en recevoir**, toujours filtrée correctement.
- Décision prise : le MCP **ne sert pas** à éditer le contenu du site.

## 3. Exigences transverses (non fonctionnelles)

- **Incassable** : robustesse, résilience, tests.
- **Sécurité maximale**.
- **Propre, générique, modulaire** : chaque brique doit être remplaçable.
- **Scalable côté contenu** : n projets, n documents, sans refonte.
- **Pédagogique pour l'auteur** : apprendre LangGraph et LangSmith en les utilisant.

## 4. Décisions déjà prises

| # | Décision | Note |
|---|----------|------|
| D1 | Un back-office est nécessaire | L'idée « éditer le contenu via le MCP » est abandonnée. |
| D2 | LangGraph + LangSmith | Framework imposé, usage maximal, objectif d'apprentissage. |
| D3 | Le premier projet présenté est le portfolio lui-même | Fiche méta : site, RAG, MCP. |
| D5 | Le MCP public n'édite pas le contenu | Lecture + envoi d'un message uniquement (commentaires retirés le 2026-09-10). |
| D6 | Simplicité d'abord, pas de sur-ingénierie gratuite | Mais une architecture décomposée en plusieurs briques modulaires et génériques, chacune justifiée. |
| D7 | Préférer les services managés à l'auto-hébergement | Montre une architecture à plusieurs briques ; l'ADR explique chaque choix. |
| D8 | ADR dès le début | Format MADR dans `docs/adr/`. |
| D9 | Budget global d'environ 50 € / mois maximum | Sans brider le projet pour autant. |
| D10 | Pas de délai imposé, livraison incrémentale | Au plus simple et au plus court ; blocs assemblés via des issues, effectifs ajoutés au fil de l'eau. |
| D11 | Dépôt privé (révisable) | Conçu comme s'il était public : aucun secret dans le code, sécurité par authentification et limitations, jamais par obscurité. |
| D12 | Repartir de zéro | D'abord documenter ; avant tout code : skills Claude Code, personnalisation, pipeline de développement. |
| D13 | Phase 3 = lecture seule + `send_message` | Le LLM du visiteur rédige lui-même les réponses à partir des données renvoyées. |
| D14 | Contenu public par nature | Projets privés : screenshots, langages, outils seulement ; pas de liens ; CV fourni en version publique (sans téléphone ni adresse). |
| D15 | Décision frontend reportée en tout dernier | Après le choix des skills et outils de design. |
| D16 | Back-office = Django admin personnalisé | Content-as-code et CMS headless rejetés : images, icônes et tags méritent une vraie interface. |
| D17 | Backend Django (retenu sauf objection) | Choisi pour ses mérites propres (admin, ORM, sécurité par défaut, écosystème), pas par héritage de l'ancien dépôt. |
| D18 | Écosystème LangChain utilisé en entier | LangChain (composants), LangGraph (orchestration), LangSmith (observabilité) : représentatif du travail réel sur un RAG. |
| D19 | Hébergement = un VPS unique, Docker Compose | Tous les services en conteneurs sur la même machine ; coût réduit, assumé malgré D7. |
| D20 | Redis dès la phase 1 | Cache applicatif avec invalidation (vitrine « optimisation »), puis broker de tâches et compteurs de rate limiting en phase 2. |
| D21 | Médias sur le disque du VPS | Via l'abstraction de stockage de Django ; bascule S3 possible par configuration. |
| D22 | MCP = option « recherche » | Le LLM du visiteur rédige ; outils de lecture + `send_message`. |
| D23 | Cloudflare devant le VPS | Confirmé : DNS, proxy, WAF, Turnstile, Access. |
| D24 | Pas d'email | Tout est conçu sans envoi d'email ; sujet post-MVP, peut-être jamais. Le `send_message` du MCP écrit en base, lecture dans l'admin. |
| D25 | Médias et documents sur Cloudflare R2 (sauf objection) | Via `django-storages` ; disque local en développement. Remplace D21. |
| D26 | Sauvegardes acceptées | Dump Postgres nocturne chiffré vers un bucket R2 privé, rétention, restauration testée ; snapshot du fournisseur en option. |
| D27 | Django confirmé, code minimal | Un seul superutilisateur, pas de rôles ni de groupes ; apps, middlewares et réglages inutilisés retirés ; « chaque ligne sert un but » devient une règle de revue. |
| D28 | Contenu FR seul, jamais en dur | Tout le contenu vient de la base ; libellés d'interface centralisés et prêts pour une langue supplémentaire ; aucune valeur magique dans le code. Interprétation à confirmer (8.6). |
| D29 | Nom de domaine à acheter | Aucun domaine existant ; reco : Cloudflare Registrar si l'extension est proposée, sinon OVH ou Gandi avec DNS chez Cloudflare. |
| D30 | R2 confirmé | D25 devient ferme. |
| D31 | Détection des ajouts et retraits de documents | Tout fichier passe par l'admin (la base est la source de vérité) ; à la sauvegarde ou à la suppression, un événement déclenche le worker : ingestion, ou purge des chunks et embeddings. Hash de contenu pour ne pas ré-embedder l'inchangé. |
| D32 | Postgres reste sur le VPS | Unique composant stateful, sauvegardé vers R2. Le reste du VPS est reproductible depuis le dépôt (script d'amorçage + Compose). Postgres managé écarté (coût ou mise en veille, latence). |
| D33 | Sauvegardes : garde-fous | Ping healthchecks.io après chaque sauvegarde (alerte si absente) ; test de restauration automatisé et périodique. |
| D34 | FR seul, interprétation confirmée | Catalogue de chaînes unique, contenu en base, pas de champs traduits ni de sélecteur de langue tant que l'anglais n'est pas demandé. |
| D35 | LangSmith cloud accepté | Région UE, rétention courte, page de confidentialité. |
| D36 | Domaine acheté chez Cloudflare Registrar | Sous-domaines `www`, `api`, `media`, `mcp`. |
| D37 | Nom de domaine : `pacome.dev` | Retenu le 2026-09-11 ; achat avant le premier déploiement, tarif à vérifier (premium possible). |
| D38 | Plan de reprise explicite | Objectifs : perte de données max 24 h (RPO), remise en service en moins d'une heure (RTO). Moyens : dossier `infra/` versionné (Compose, Caddyfile, script d'amorçage, runbook), secrets dans un gestionnaire de mots de passe, commande de restauration, test de restauration mensuel automatisé, ping healthchecks.io. Détail en 8.12. |

## 5. Contexte existant (dépôt)

- Tentative précédente (commits jusqu'à `4621483`) : backend Django + Django REST Framework + SQLite (modèles `Project` et `Technology`, API en lecture seule), frontend Flutter web (cartes projet, dialog de détail, thème Inter Tight).
- Le 2026-09-10, à la demande de l'auteur, l'historique Git local a été supprimé (`rm -rf .git`) et un dépôt vierge a été initialisé (branche `main`, aucun commit). L'ancien historique reste sur GitHub (`https://github.com/plecart/Portfolio.git`, dernier commit `4621483`, entièrement poussé) : ne pas s'en servir comme référence. `backend/venv/` y avait été commité (à ne pas reproduire).
- Confirmé le 2026-09-10 : on repart de zéro (D12).

## 6. Mon avis

1. **La force du projet, c'est le méta-projet.** Une complexité volontaire n'est convaincante que si elle est expliquée. Chaque brique doit avoir un « pourquoi » écrit : je propose des ADR (Architecture Decision Records) dès le premier jour dans `docs/adr/`. Ils alimentent la fiche du méta-projet et le RAG (le chatbot pourra répondre « pourquoi pgvector plutôt que Qdrant ? »). Sans cela, un lecteur technique verra de la complexité accidentelle, pas de la maîtrise.

2. **LangGraph n'est pas LangSmith.** LangGraph = orchestration : graphe de nœuds, état partagé typé, persistance et checkpoints, branches conditionnelles, parallélisme, interruptions human-in-the-loop, streaming. LangSmith = observabilité : traces, datasets, évaluations, monitoring. C'est un SaaS de LangChain : les traces sortent de ton infrastructure, il y a un quota gratuit mensuel, et son interface n'est pas embarquable publiquement. Conséquence : la page « LangGraph » du site est à construire toi-même à partir (a) de statistiques agrégées récupérées via l'API LangSmith par ton backend et (b) de la trace de la conversation du visiteur lui-même (étapes, durées, chunks retrouvés). C'est une meilleure vitrine qu'un lien. Je recommande de faire tourner **deux graphes** LangGraph, le chat et le pipeline d'ingestion, tous deux tracés dans LangSmith.

3. **Le vrai risque est le périmètre, pas la technique.** Trois phases avec « sécurité et modularité maximales » peuvent s'étaler indéfiniment. Je recommande une tranche verticale fine dès la phase 1 : site déployé en production, un projet saisi, CI/CD, sauvegardes, supervision. « Incassable » vient des tests, de la CI, de la supervision et de la dégradation gracieuse (le site fonctionne même si le service IA est en panne), pas de couches supplémentaires.

4. **Monolithe modulaire d'abord, services ensuite.** Proposition : un monorepo ; en phase 1 seulement `web` + `api` + Postgres. En phase 2 s'ajoutent `ai` (LangGraph), `worker` (ingestion), Redis, pgvector. En phase 3, `mcp`. Chaque service est un package aux frontières claires, ce qui donne exactement l'architecture attendue pour le méta-projet.

5. **Frontend : je déconseille Flutter web pour ce site**, pour des raisons techniques et non visuelles : pas de rendu côté serveur donc SEO et aperçus de partage pauvres, bundle initial lourd, sélection de texte et accessibilité médiocres, intégration Markdown / streaming moins naturelle. Un framework web (Next.js, SvelteKit, Astro) est plus adapté. Exception : si Flutter est une compétence que tu veux montrer, garde-le pour une application mobile compagnon plus tard.

6. **La fiche technique est la colonne vertébrale.** Un schéma de fiche normalisé (sections fixes : contexte, stack, architecture, sécurité, données, asynchrone / workers, déploiement, décisions, bilan) sert à la fois l'affichage et le chunking du RAG (un chunk = une section avec ses métadonnées). Définir ce schéma est la première tâche de la phase 1.

7. **Sécurité : les vraies expositions d'un chatbot public et d'un MCP public sont l'abus de coût et le spam**, bien plus que « le piratage ». Plafond de budget quotidien avec coupe-circuit, rate limiting par IP et par session, Turnstile, file de modération pour messages et commentaires, admin non exposé publiquement (Cloudflare Access ou Tailscale, plus 2FA). Et une **rédaction des données personnelles** (téléphone, adresse) avant indexation du CV.

8. **MCP : exposer la recherche, pas forcément la réponse.** Le client MCP a déjà son propre LLM. Exposer `search` et `get` (retrieval + ressources) ne coûte presque rien ; exposer `ask` (réponse générée par ton LLM) coûte à chaque appel. Je propose : lecture anonyme limitée, écriture (message, commentaire) authentifiée et modérée. Et que ton propre chatbot web consomme les mêmes outils : une seule surface d'outils, du dogfooding.

9. **Deux décisions à prendre tôt car elles irriguent tout** : le multilingue (FR seul ou FR + EN) et le caractère public ou privé du dépôt (si public : aucun document personnel dans le repo, hygiène des secrets stricte, historique nettoyé).

## 7. Questions

Format : chaque question porte une **reco** quand j'en ai une. Réponds par numéro (« Q3 : OK », « Q3 : non, plutôt X »). Une réponse « OK » vaut acceptation de la reco.

### 7.0 À trancher en premier (bloquant pour démarrer la phase 1)

Q1, Q2, Q3, Q11, Q15, Q54, Q66, Q67, Q68, Q70, Q72.

### A. Socle et stack

- **Q1. Backend en Python ?** LangGraph est natif Python (la version JS existe, mais l'écosystème RAG est plus riche en Python) et ta tentative précédente était en Django. Reco : Python 3.12+, dépendances gérées avec `uv`.
- **Q2. Framework backend : Django, FastAPI, ou les deux ?** Django apporte l'admin (back-office gratuit), l'ORM, les migrations, l'auth. FastAPI est plus naturel pour l'async, le streaming SSE du chat et l'intégration LangGraph. Reco : Django pour le contenu et l'admin (`api`), FastAPI pour le service IA (`ai`), dans le même monorepo, avec un package commun (schémas Pydantic, accès aux données). Alternative plus homogène : tout FastAPI avec un admin custom, plus de travail en phase 1.
- **Q3. Frontend : quel framework ?** Voir avis n°5. Options : Next.js (React), SvelteKit, Astro (avec îlots React ou Svelte pour le chat), ou conserver Flutter web. Reco : Astro ou Next.js, à décider aussi selon ce que tu veux montrer (React reste le plus demandé sur le marché).
- **Q4. Monorepo ?** Reco : oui. `apps/web`, `apps/api`, `apps/ai`, `apps/mcp`, `packages/`, `infra/`, `docs/`, `content/`.
- **Q5. Base de données : Postgres partout ?** Reco : Postgres 16 + extension pgvector. Une seule base pour le contenu, les vecteurs, les checkpoints LangGraph et la file d'événements. SQLite abandonné.
- **Q6. Cache et broker : Redis ?** Nécessaire pour le rate limiting, les files de tâches et le cache. Reco : oui à partir de la phase 2, on s'en passe en phase 1.
- **Q7. Outillage qualité ?** Reco : `ruff`, `pyright` strict, `pytest`, `pre-commit` ; TypeScript strict, ESLint, Vitest, Playwright ; conventional commits. Des préférences ou des habitudes ?
- **Q8. Conteneurisation dès le jour 1 ?** Reco : Docker + Docker Compose pour le dev et la prod (mêmes images), `Makefile` ou `justfile` pour les commandes.

### B. Contenu et back-office

- **Q9. Modèle de données d'un projet : valides-tu cette base ?** slug, titre, résumé court, description (Markdown), type (perso / pro / école), statut (en cours / terminé / archivé), dates de début et fin, client, liens (dépôt, démo), technologies (tags typés : langage / framework / infra / outil), galerie d'images avec légendes, et la **fiche technique en sections normalisées** (Q10). Manque-t-il quelque chose : équipe, rôle tenu, métriques, durée ?
- **Q10. Sections normalisées de la fiche technique ?** Proposition : Contexte et objectif · Stack · Architecture (explication) · Données · Sécurité · Asynchrone et workers · API et intégrations · Déploiement et exploitation · Tests et qualité · Décisions (ADR) · Bilan et ce que je referais autrement. Toutes obligatoires, ou certaines optionnelles ?
- **Q11. Back-office : quelle approche ?** (a) Django admin : immédiat, sobre, facile à sécuriser. (b) Admin custom dans le frontend : plus de travail, plus de vitrine. (c) CMS headless (Strapi, Payload, Directus). (d) **Content-as-code** : chaque projet est un dossier versionné (`project.yaml`, `fiche.md`, `images/`), validé par un schéma en CI, publié au merge. (e) Mix : content-as-code pour les projets, admin pour le reste (messages, commentaires, documents privés, modération). Reco : (e), car le versioning Git et la revue par diff s'emboîtent naturellement, et l'admin reste utile pour la modération. Voir aussi Q72.
- **Q12. Documents « sur moi » : comment sont-ils ajoutés et dans quels formats ?** PDF, DOCX, Markdown ? Upload via l'admin, ou dossier privé versionné hors du dépôt public ? Reco : Markdown ou PDF, stockage objet privé, upload via l'admin avec métadonnées (type, visibilité, langue).
- **Q13. Niveaux de visibilité des documents ?** Proposition : `public` (téléchargeable, ex. CV public), `rag_only` (utilisé par le chatbot, jamais servi en entier), `private` (jamais indexé). Suffisant ?
- **Q14. Profil structuré en plus des documents ?** Un objet « profil » (compétences, expériences, formation, langues, disponibilité) en base, distinct des PDF, donne des faits exacts au RAG et alimente une page « à propos ». Reco : oui.
- **Q15. Multilingue ?** Contenu FR seul, FR + EN, ou FR avec un chatbot qui répond dans la langue du visiteur ? Impacte le modèle d'embeddings, le schéma de contenu (champs traduits) et les prompts. Reco : FR + EN si tu vises l'international, sinon FR avec chatbot multilingue.
- **Q16. Workflow de publication ?** États brouillon / publié, historique des versions d'un projet, publication programmée ? Reco : brouillon / publié + historique simple (audit), pas de programmation.
- **Q17. Stockage des médias ?** Disque local, ou stockage objet compatible S3 (MinIO en local, Cloudflare R2 ou Scaleway en prod) ? Traitement des images à l'upload (redimensionnement, WebP, vignettes) ? Reco : S3-compatible dès le début + traitement asynchrone.

### C. RAG

- **Q21. Fournisseur LLM : Claude (Anthropic) ?** Si oui, répartition proposée : `claude-opus-5` pour la génération finale, `claude-haiku-4-5` pour les étapes bon marché (classification de la question, réécriture, garde-fous, modération). `claude-sonnet-5` est l'option intermédiaire si tu veux réduire le coût par conversation ; c'est ton arbitrage. Tarifs par million de tokens :

  | Modèle | Entrée | Sortie |
  |---|---|---|
  | claude-opus-5 | 5 $ | 25 $ |
  | claude-sonnet-5 | 2 $ | 10 $ |
  | claude-haiku-4-5 | 1 $ | 5 $ |

- **Q22. Embeddings : cloud ou local ?** À ma connaissance Anthropic ne fournit pas de modèle d'embeddings et renvoie vers Voyage AI (à vérifier au moment de l'implémentation). Options : Voyage AI (famille `voyage-3`, multilingue, API peu coûteuse), OpenAI `text-embedding-3`, ou un modèle open source hébergé chez toi (`bge-m3`, `multilingual-e5`) : gratuit mais consomme CPU et RAM sur le serveur. Reco : Voyage AI pour rester léger côté serveur, `bge-m3` si tu veux tout auto-héberger.
- **Q23. Base vectorielle : pgvector ou dédiée ?** pgvector = une seule base, recherche hybride facile avec `tsvector`, sauvegardes unifiées. Qdrant ou Weaviate = brique dédiée, plus « vitrine » mais un service de plus à exploiter. Reco : pgvector, avec un ADR qui explique pourquoi.
- **Q24. Stratégie de chunking ?** Reco : découpage structurel (une section de fiche = un ou plusieurs chunks de 300 à 800 tokens, léger chevauchement) avec métadonnées (projet, section, langue, date, type de source) ; PDF parsés avec un outil conscient de la mise en page (Docling ou Unstructured) ; **contextual retrieval** (préfixe de contexte généré par LLM pour chaque chunk) comme démonstration avancée. D'accord pour dépenser des tokens à l'ingestion pour cela ?
- **Q25. Retrieval ?** Reco : hybride (BM25 via `tsvector` + vecteurs) fusionné par RRF, filtres par métadonnées (périmètre projet, langue), reranking (Voyage rerank, Cohere rerank ou cross-encoder local), réécriture de requête et multi-query en parallèle. Top-k final de 5 à 8 chunks. Des préférences ?
- **Q26. Citations dans les réponses ?** Reco : oui, chaque réponse cite ses sources avec un lien profond vers la fiche et la section. L'API Claude propose des citations natives (blocs `document` + `citations`), bonne démonstration de fidélité aux sources.
- **Q27. Déclenchement de la ré-indexation ?** Reco : événementiel (sauvegarde → événement dans une table outbox → worker), idempotent, basé sur un hash de contenu (on ne ré-embedde que ce qui a changé), version d'index par document avec remplacement atomique, commande de ré-indexation complète, retries et dead-letter, statut visible dans l'admin (« indexé le… », « en attente »). Latence acceptable entre modification et prise en compte : secondes ou minutes ?
- **Q28. Moteur de tâches asynchrones ?** Celery + Redis (classique, très demandé), arq ou Dramatiq (plus légers), Temporal (lourd). Reco : Celery pour la compétence la plus reconnue, arq pour la légèreté. Et le pipeline d'ingestion lui-même modélisé comme un graphe LangGraph (parse → chunk → enrich → embed → upsert) exécuté par le worker.
- **Q29. Mémoire de conversation ?** Multi-tour avec checkpointer LangGraph sur Postgres, identifiant de fil côté client (cookie), sessions anonymes, purge après N jours. Reco : oui, rétention 30 jours. Accord ?
- **Q30. Streaming des réponses et des étapes ?** Reco : SSE token par token + affichage des étapes intermédiaires (« recherche », « reranking », « rédaction »), ce qui exploite les modes de streaming de LangGraph.
- **Q31. Politique de réponse ?** Répondre uniquement à partir des sources, refuser poliment le hors-sujet, répondre dans la langue du visiteur, ne jamais divulguer certaines données personnelles. **Quelles informations personnelles le bot peut-il donner** : email pro, téléphone, ville, âge, disponibilité ?
- **Q32. Jeu d'évaluation ?** Reco : 30 à 50 questions / réponses de référence dans un dataset LangSmith, évaluateurs (fidélité, pertinence, précision du contexte) exécutés en CI à chaque changement de prompt ou de pipeline. C'est ce qui rend le RAG « professionnel ». OK ?
- **Q33. Maîtrise des coûts ?** Reco : limites par IP et par session, plafond global journalier avec coupe-circuit, `max_tokens` bornés, prompt caching sur le system prompt, petit modèle pour les étapes intermédiaires. As-tu un budget mensuel cible pour l'API ?

### D. LangGraph et LangSmith

- **Q34. Compte LangSmith cloud acceptable ?** Les traces (questions des visiteurs, chunks retrouvés) partent chez LangChain, hébergement US par défaut (une région UE existe). Quota gratuit mensuel puis facturation à la trace. Alternative auto-hébergée : Langfuse (open source, compatible OpenTelemetry). Reco : LangSmith (objectif d'apprentissage) avec mention dans la politique de confidentialité ; Langfuse en plus seulement si tu veux montrer l'auto-hébergement.
- **Q35. Que doit montrer la page « LangGraph » du site ?** (a) des statistiques agrégées via l'API LangSmith (volume, latence p50 / p95, tokens, coût, notes de feedback), servies par ton backend avec cache ; (b) la trace de la conversation du visiteur (étapes, durées, chunks) ; (c) des liens vers des traces partagées publiquement. Reco : a + b.
- **Q36. Fonctionnalités LangGraph à mettre en avant volontairement ?** Proposition : état typé avec reducers, routage conditionnel (hors-sujet / bavardage / besoin de retrieval), parallélisme (`Send` pour le multi-query), sous-graphes (retrieval, garde-fous), checkpointing Postgres, interruptions human-in-the-loop (modération des messages MCP), nœuds de retry et de fallback, streaming multi-modes, time-travel pour le debug. Lesquelles en priorité ?
- **Q37. Déploiement du graphe ?** LangGraph Server (API Agent Protocol, threads intégrés, `langgraph dev` + Studio en local) ou graphe embarqué dans FastAPI ? Reco : Studio en local pour apprendre ; en prod, graphe embarqué dans FastAPI (contrôle total, pas de dépendance à la plateforme) ; à réévaluer si l'offre auto-hébergée gratuite convient.
- **Q38. Feedback utilisateur ?** Pouce haut / bas sur les réponses, renvoyé vers LangSmith pour alimenter les évaluations. Reco : oui.
- **Q39. Notes d'apprentissage ?** Souhaites-tu un document vivant `docs/learning/langgraph.md` où j'explique chaque concept au moment où on l'utilise ? Reco : oui.

### E. Sécurité

- **Q40. Modèle de menace : d'accord avec cette liste ?** Abus de coût (LLM), spam via messages et commentaires, injection de prompt via l'entrée utilisateur (les documents sont sous ton contrôle), fuite d'informations personnelles, XSS via le rendu Markdown, upload malveillant dans l'admin, SSRF, compromission de l'admin, fuite de secrets, dépendances vulnérables. Autre chose (scraping, dénigrement via commentaires) ?
- **Q41. Protection de l'admin ?** Reco : admin non exposé publiquement (Cloudflare Access ou Tailscale) + mot de passe fort + 2FA (TOTP ou passkey), un seul compte, journal d'audit. Accord ?
- **Q42. Anti-abus du chat ?** Reco : Cloudflare Turnstile invisible, rate limiting par IP et par session, taille maximale des messages, coupe-circuit budget, détection d'injection (petit modèle + règles), journalisation des tentatives. Accord ?
- **Q43. Garde-fous LLM ?** Reco : system prompt durci, contenu récupéré traité comme donnée et non comme instruction, sorties structurées pour les décisions de routage, filtrage de sortie (aucune donnée personnelle interdite), refus hors périmètre.
- **Q44. Secrets et configuration ?** Reco : 12-factor, `.env` uniquement en dev, secrets Docker ou SOPS en prod, rotation documentée. Un gestionnaire de secrets (Vault, Infisical) serait de la sur-ingénierie assumée : oui ou non ?
- **Q45. Chaîne d'approvisionnement ?** Reco : lockfiles, Renovate ou Dependabot, scan des images (Trivy), `pip-audit` et `npm audit` en CI, SBOM. Jusqu'où ?
- **Q46. RGPD et confidentialité ?** Journaux de chat, traces LangSmith, messages reçus : durée de conservation, page de confidentialité, bannière si cookies non essentiels. Hébergement en UE ? Reco : UE, rétention 30 jours, pas de cookie tiers.
- **Q47. Sécurité HTTP ?** HTTPS partout, CSP stricte, CORS restreint, CSRF sur l'admin, en-têtes de sécurité, TLS géré par Caddy ou Cloudflare. Rien de particulier à ajouter ?

### F. MCP

- **Q48. Transport et authentification ?** Un MCP public doit être distant (Streamable HTTP) ; `stdio` n'existe qu'en local. Le standard prévoit OAuth 2.1 pour les serveurs distants. Options : lecture anonyme + écriture authentifiée (OAuth via GitHub, ou jeton délivré sur le site après Turnstile), ou tout authentifié. Reco : lecture anonyme limitée, écriture authentifiée.
- **Q49. Outils exposés ?** Proposition : `list_projects`, `get_project`, `get_architecture`, `search_portfolio` (retrieval seul : chunks + sources), `get_profile`, `send_message`, `post_comment` ; ressources MCP `portfolio://projects/{slug}` ; prompts prédéfinis (« interroge-moi sur le projet X »). Faut-il aussi un `ask_portfolio` qui génère la réponse avec ton LLM (coûteux, à limiter) ?
- **Q50. Commentaires publics sur les fiches ?** Modération avant affichage (file dans l'admin, préfiltre LLM, limites de taille, pas de liens) ? Reco : oui, publics après approbation, modération avec interruption LangGraph (human-in-the-loop) pour la démonstration.
- **Q51. Canal de notification des messages reçus ?** Email (Resend, Brevo, SMTP), Telegram, Discord, ou simple boîte de réception dans l'admin ? Reco : admin + email.
- **Q52. Clients à supporter et à tester ?** Claude.ai (connecteurs), Claude Desktop, Claude Code, ChatGPT, Cursor, VS Code. Une page « comment se connecter » avec les snippets de configuration ? Reco : oui.
- **Q53. Framework et découpage ?** SDK Python `mcp` (FastMCP) dans un service séparé partageant le package commun. Reco : oui. Et ton chatbot web consomme-t-il ces mêmes outils (dogfooding) ? Reco : oui.

### G. Infrastructure et exploitation

- **Q54. Hébergement ?** VPS (Hetzner, OVH, Scaleway) avec Docker Compose + Caddy ou Traefik, PaaS (Fly.io, Render, Railway), ou Kubernetes (sur-ingénierie assumée, mais coût d'exploitation réel). Reco : un VPS en UE autour de 10 à 15 € par mois, Docker Compose, Cloudflare devant (DNS, WAF, Turnstile, Access).
- **Q55. Nom de domaine ?** Existant ? Sous-domaines prévus : `www`, `api`, `mcp`, `admin` ?
- **Q56. CI/CD ?** Reco : GitHub Actions (lint, types, tests, build, scan, push des images sur GHCR, déploiement par SSH ou Watchtower, migrations automatiques). Environnement de staging, ou seulement la prod ?
- **Q57. Observabilité ?** Reco : logs structurés JSON, Sentry (erreurs, offre gratuite), Uptime Kuma ou BetterStack (disponibilité), Prometheus + Grafana seulement si tu veux le montrer, OpenTelemetry entre services (LangSmith accepte aussi OTel). Jusqu'où ?
- **Q58. Sauvegardes ?** Reco : dump Postgres nocturne + médias vers un stockage objet, chiffrés, test de restauration documenté.
- **Q59. Dégradation gracieuse ?** Le site doit fonctionner si le service IA, LangSmith ou l'API LLM est indisponible (chat masqué ou message clair). Healthchecks, timeouts, circuit breaker, politiques de redémarrage. Accord ?
- **Q60. Emails sortants ?** Nécessaires pour les notifications (Q51) et éventuellement l'auth. Fournisseur ?
- **Q61. Environnements ?** Dev local complet en Docker Compose (Postgres, Redis, MinIO, `langgraph dev`), puis prod. Reco : oui.

### H. Qualité, tests, documentation

- **Q62. Stratégie de tests ?** Reco : unitaires (chunking, parseurs, garde-fous), intégration (API + DB via testcontainers), E2E Playwright (site + chat), évaluations RAG (LangSmith), tests de contrat MCP (client SDK ou MCP Inspector), test de charge léger (k6) sur le rate limiting, scan sécurité (ZAP baseline, bandit). Un objectif de couverture ?
- **Q63. ADR dès le début ?** Voir avis n°1. Format MADR dans `docs/adr/`. OK ?
- **Q64. Documentation générée ?** OpenAPI pour l'API, README par service. Les docs sont aussi une source du RAG (le bot explique le portfolio). OK ?
- **Q65. Licence du code ?** Si dépôt public : MIT, Apache-2, ou aucune licence (tous droits réservés) ?

### I. Périmètre, contexte, contraintes

- **Q66. Délai et rythme ?** « Assez rapidement » : une date cible pour la phase 1 ? Combien d'heures par semaine ?
- **Q67. Budget mensuel global ?** Hébergement + API LLM + embeddings + LangSmith + domaine. Un plafond à respecter dans la conception ?
- **Q68. Dépôt public ?** Le code sera-t-il visible sur GitHub (partie de la vitrine) ? Si oui : aucune donnée personnelle dans le repo, secrets hors repo, historique nettoyé (`backend/venv` a été commité).
- **Q69. Audience et trafic attendus ?** Recruteurs, pairs ? Quelques visites par jour ? On conçoit pour un faible trafic, mais avec des protections robustes.
- **Q70. Repartir de zéro ?** Le working tree est vide et les suppressions ne sont pas commitées. Je propose de commiter la suppression (ou de réinitialiser l'historique) et de démarrer proprement avec un `.gitignore` correct. Garder quelque chose de l'ancien code (modèles Django, widgets Flutter) ?
- **Q71. Contenu disponible au départ ?** Combien de projets, le CV est-il en PDF ou Markdown, y a-t-il des documents d'expériences déjà rédigés ?
- **Q72. Ton « autre idée » pour la saisie des projets ?** Tu l'as mise de côté dans ton message : je préfère la connaître avant de figer Q11.
- **Q73. Ordre des phases figé ?** Livrer la phase 1 en production avant de commencer la 2, ou concevoir dès maintenant le socle (Postgres, workers, événements) pour la 2 ? Reco : socle prévu dès le départ, code de la phase 2 non écrit avant la mise en prod de la 1.

## 8. Réponses et éclaircissements (2026-09-10)

### 8.1 Réponses reçues

| Sujet | Réponse | Effet |
|---|---|---|
| Avis n°1 (ADR) | Oui. Simplicité, pas de sur-ingénierie gratuite, mais plusieurs briques modulaires et génériques, de préférence des services managés, chacune justifiée. | D6, D7, D8 |
| Avis n°3 (périmètre) | Compris après explication (8.2) : livraison incrémentale par issues, première version en production tôt. | D10 |
| Avis n°5 (Flutter web) | Décision frontend reportée en tout dernier. | D15 |
| Avis n°6 (fiche technique) | Validé. | — |
| Avis n°8 (sécurité) | Validé : très haut niveau de sécurité sur les surfaces publiques, comme démonstration. | — |
| Avis n°9 (MCP) | Souhait : le LLM du visiteur lit les données comme s'il était sur le chatbot du site ; lecture seule + envoi d'email. | D13 |
| Q1 / Q2 | Explications demandées (8.2). Décision en attente. | — |
| Q3 | Reportée en tout dernier. | D15 |
| Q11 | Explications demandées (8.2). Décision en attente. | — |
| Q31 | Tout le contenu du portfolio est public par nature. Projets privés : screenshots, langages, outils seulement, pas de liens. | D14 |
| Q34 | Explication de « traces » demandée (8.2). Décision en attente. | — |
| Q54 | Kubernetes écarté. Explications VPS / PaaS demandées (8.2). Trafic attendu : un ou deux visiteurs occasionnels. | — |
| Q66 / Q67 | Pas de délai ; au plus simple et au plus court ; budget ≈ 50 €/mois maximum sans brider. | D9, D10 |
| Q68 | Dépôt privé, par crainte que le code aide à trouver des failles (MCP exposé). | D11 |
| Q70 | Repartir de zéro. D'abord documenter, puis mettre en place skills, personnalisation de Claude Code et pipeline de développement. | D12 |
| Q72 | L'autre idée : créer les projets via un MCP plutôt qu'un back-office. L'auteur n'est pas convaincu. Voir 8.2. | — |

### 8.2 Éclaircissements

**LangGraph fait-il le RAG ?** Non. LangGraph est un moteur d'orchestration : on déclare des nœuds (fonctions Python à soi) et des arêtes (ordre et conditions d'exécution). Chunking, embeddings, requête hybride pgvector, reranking et prompts restent du code à soi. LangGraph apporte : état typé partagé entre étapes, mémoire de conversation (checkpoints), routage conditionnel, parallélisme, streaming des étapes, interruption pour validation humaine, traçage automatique dans LangSmith. Trois produits à ne pas confondre : LangChain (bibliothèque d'intégrations et de chaînes toutes faites), LangGraph (orchestration, utilisable sans LangChain), LangSmith (observabilité et évaluation, SaaS). Position retenue : LangGraph pour orchestrer le chat ; primitives RAG écrites par nous derrière des adaptateurs fins et remplaçables ; aucune chaîne toute faite de LangChain (elles cacheraient le travail) ; `langchain-anthropic` pour les appels LLM dans les nœuds (streaming et traçage intégrés). Le pipeline d'ingestion est linéaire : fonctions simples dans le worker, tracées dans LangSmith, pas de graphe (remplace la reco de Q28).

**Django vs FastAPI (Q1 / Q2).**

| | Django | FastAPI |
|---|---|---|
| Back-office | Admin généré depuis les modèles (formulaires, upload, filtres, recherche, permissions) | À construire, ou outil tiers moins complet (sqladmin, starlette-admin) |
| ORM et migrations | Inclus | SQLAlchemy + Alembic à assembler |
| Auth, sessions, CSRF, stockage S3 | Inclus ou packages matures | À assembler |
| API typée + OpenAPI | Django Ninja ou DRF | Natif |
| Async, streaming SSE, LangGraph | Possible (ASGI) mais moins naturel | Natif |
| Poids | Cadre complet, monolithique | Minimal |

Réponse à la question posée : oui, avec Django le back-office existe sans être écrit ; il reste à l'ajuster (éditeur Markdown, aperçus d'images, bouton « ré-indexer », statut d'indexation). Reco : Django seul en phase 1 (contenu, admin, API) ; FastAPI pour le service IA en phase 2 (LangGraph, streaming, exécuté séparément, peut tomber sans casser le site). Deux briques, une frontière expliquée par un ADR.

**Back-office : les trois familles (Q11).**

| Option | Ce que c'est | Avantages | Inconvénients |
|---|---|---|---|
| Django admin | Interface CRUD générée depuis les modèles | Gratuit, sûr, immédiat | Basique pour du contenu riche ; édition en formulaire |
| CMS headless (Strapi, Directus, Payload ; SaaS : Sanity, Contentful) | Produit séparé qui gère le contenu (types, médias, rôles, historique, traductions) et l'expose via une API ; « headless » = sans partie visible, le front consomme l'API | Excellente interface d'édition ; webhooks (déclenchement de la ré-indexation) ; une brique de plus à expliquer | Un système de plus à héberger ou payer ; modèle de données chez le CMS (dépendance) ; second runtime (Node) ; rend Django redondant pour le contenu |
| Content-as-code | Chaque projet = dossier de fichiers dans le dépôt (`project.yaml`, `fiche.md`, `images/`), écrit dans l'IDE ou par Claude Code, validé par la CI, importé en base au merge (ce qui déclenche l'indexation) | Versionné, relu par diff, aucune surface d'écriture exposée, s'emboîte avec les ADR, coût nul | Réservé à un développeur ; pas d'édition en ligne ; images dans Git (acceptable à cette échelle, ou stockage objet) |

Reco confirmée : content-as-code pour les projets et le profil ; Django admin pour l'opérationnel (messages reçus, statut d'indexation, journaux du chat, feedback). Lien avec Q72 : l'idée « créer les projets via un MCP » vise le même confort (dicter un projet à un LLM) ; content-as-code l'obtient sans ouvrir de surface d'écriture réseau : Claude Code écrit les fichiers en local, relecture du diff, validation CI. Un MCP d'édition, s'il existait, resterait local (stdio, jamais exposé) ; un skill Claude Code « nouveau projet » suffit.

**Hébergement (Q54).**

| Option | Ce que c'est | Avantages | Inconvénients |
|---|---|---|---|
| Kubernetes | Orchestrateur de conteneurs multi-machines (répartition, auto-scaling, auto-réparation) | Standard en entreprise | Coût et complexité sans rapport avec un ou deux visiteurs. Écarté. |
| VPS (Hetzner, OVH, Scaleway) | Machine virtuelle louée, Docker Compose, tout sur une machine | Le moins cher, contrôle total, classique | On est l'administrateur (mises à jour, sauvegardes, restauration, durcissement) ; un seul point de panne ; contraire à « outils plutôt qu'auto-hébergement » |
| PaaS (Fly.io, Render, Railway ; français : Scalingo, Clever Cloud) | On pousse des conteneurs ; la plateforme fournit exécution, TLS, logs, redémarrages, déploiements sans coupure, souvent Postgres et Redis managés | Zéro administration serveur ; chaque service isolé et visible ; régions UE | Facturation par service ; moins de contrôle ; configuration propre au fournisseur |
| Tout managé (composable) | PaaS pour les conteneurs + Postgres managé avec pgvector (Neon, Supabase) + Redis managé (Upstash) + stockage objet (Cloudflare R2) + email (Resend) + Cloudflare devant (DNS, WAF, Turnstile, Access) + LangSmith + Sentry | L'architecture « plusieurs briques, chacune à sa place » ; offres gratuites généreuses à ce trafic | Beaucoup de comptes ; offres gratuites changeantes ; mise en veille des bases gratuites (première requête plus lente) ; données réparties |

Reco : tout managé, conteneurs sur Fly.io ou Render en région UE, worker d'ingestion éteint entre deux ingestions. Estimation mensuelle (à vérifier lors de l'ADR) :

| Brique | Fournisseur | Estimation |
|---|---|---|
| Conteneurs api, ai, mcp, worker | Fly.io, petites machines toujours allumées | 10 à 25 € |
| Postgres + pgvector | Neon (gratuit, puis ~19 $) | 0 à 18 € |
| Redis | Upstash | 0 |
| Stockage objet | Cloudflare R2 (10 Go gratuits) | 0 |
| Email | Resend | 0 |
| DNS, WAF, Turnstile, Access | Cloudflare | 0 |
| LangSmith, Sentry, GitHub Actions | Offres gratuites | 0 |
| API Claude + embeddings | Usage réel, trafic faible | 5 à 15 € |
| Domaine | | ~1 € |
| **Total** | | **15 à 45 €** |
| Alternative : VPS unique tout compris | Hetzner / OVH | 5 à 15 € + administration à charge |

**MCP : recherche ou réponse (avis n°8).** Deux façons de servir un visiteur qui branche son Claude sur le MCP : (1) recherche : le MCP renvoie les informations brutes (fiches, passages pertinents de la base vectorielle) et le Claude du visiteur rédige la réponse, coût quasi nul ; (2) réponse : le MCP fait tourner notre chatbot et renvoie un texte fini que le Claude du visiteur répète, tokens facturés à chaque appel, deux LLM en série. Le souhait exprimé correspond à (1). Outils retenus : `list_projects`, `get_project`, `search_portfolio`, `get_profile`, et une seule action `send_message` (email). Commentaires retirés (remplace Q49 / Q50). La base de connaissances (chunks + vecteurs) est partagée : le chatbot du site et le MCP sont deux portes d'entrée sur la même base.

**« Traces des visiteurs » (Q34).** Une trace LangSmith est l'enregistrement complet d'une exécution du graphe : question tapée, requête réécrite, passages retrouvés, prompts envoyés au LLM, réponse, durées, tokens. Ces enregistrements sont stockés chez LangChain (États-Unis par défaut, région UE possible). Ce que les visiteurs écrivent dans le chatbot est donc envoyé et conservé chez un tiers, en plus d'Anthropic qui reçoit la question pour y répondre. Acceptable pour un portfolio à trois conditions : le dire dans une page de confidentialité, régler une rétention courte, n'ajouter aux traces ni IP ni identifiant nominatif.

**Dépôt privé (Q68).** Techniquement peu d'impact, à une condition : concevoir comme si le code était public (aucun secret dans le code, sécurité par authentification et limitations, jamais par obscurité). Le code fermé ralentit un attaquant sans le bloquer ; les failles réelles se trouvent en testant le service. Perte : un recruteur ne lira pas le code. Compromis possibles plus tard : ouverture après revue de sécurité, accès sur demande, fiche méta-projet montrant architecture et ADR.

**Périmètre (avis n°3).** Le risque n'est pas de ne pas savoir faire, mais que le projet grossisse sans fin parce que chaque phase vise « le maximum ». Remède : blocs livrés un par un via des issues, et une première version déployée en production très tôt (site + un projet + CI) avant le chatbot. « Tranche verticale » = un petit morceau qui traverse toutes les couches (contenu, API, base, déploiement) plutôt qu'une couche entière à la fois.

### 8.3 Deuxième tour (2026-09-10, suite)

| Sujet | Réponse | Effet |
|---|---|---|
| LangChain | On utilise les trois outils ; se passer de LangChain serait artificiel, et l'ensemble reste représentatif d'un vrai RAG. | D18 |
| Phases | Strictement séquentielles : portfolio (back + front), puis RAG, puis MCP, chacune une fois la précédente solide. | §2 |
| Ancien dépôt | Aucune référence à prendre ; suppression de tout sauf `docs/` demandée et faite. | §5 |
| MCP | Option « recherche » retenue. | D22 |
| Django | Question : recommandé par héritage ou vraie bonne solution ? Réponse en 8.4. | D17 |
| Back-office | Content-as-code rejeté (images, icônes, tags méritent une vraie interface). Vrai back-office demandé. | D16 |
| Hébergement | VPS unique jugé suffisant, coût réduit assumé ; pas de besoin ressenti de versionner, découper ou sauvegarder. | D19 |
| Redis | Souhaité pour montrer une gestion de cache optimisée. Question : confort seulement ? Réponse en 8.4. | D20 |
| Cloudflare, email, stockage, conteneurs | Questions : à quoi sert Cloudflare ? pourquoi un service d'email ? stockage via une librairie Django sur le VPS ? Redis, worker et Postgres + pgvector en conteneurs sur le VPS ? Réponses en 8.4. | D19, D21 |

### 8.4 Éclaircissements du deuxième tour

**Django : héritage ou vrai choix ?** Vrai choix, indépendant de l'ancien dépôt. Arguments propres : (1) l'admin, un back-office complet généré depuis les modèles, exactement ce qui est demandé ; (2) ORM, migrations, auth, gestion des fichiers uploadés, formulaires : tout est intégré et cohérent ; (3) sécurité par défaut (CSRF, échappement XSS, en-têtes, hachage des mots de passe, validation des uploads) ; (4) écosystème : `django-ninja` (API typée), `django-storages` (bascule S3), `django-redis` (cache), `pgvector` (support Django officiel des vecteurs), `django-otp` / `django-allauth` (2FA, OAuth), Celery ; (5) un seul développeur, site orienté contenu, Postgres : le cas d'usage idéal de Django. Limites honnêtes : interface admin d'aspect daté (personnalisable), async de second rang (sans importance en phase 1 ; le service IA de phase 2 pourra être FastAPI ou Django ASGI, à trancher par ADR). FastAPI ne gagnerait que pour une API purement asynchrone sans back-office.

**Redis : confort ou nécessité ?** À ce trafic, le cache n'est pas nécessaire aux performances ; c'est une démonstration. Mais Redis a ici trois rôles réels : (1) cache applicatif (réponses d'API, pages projets, statistiques LangSmith de la page LangGraph, embeddings des questions fréquentes) avec **invalidation à la sauvegarde** via les signaux Django : c'est le motif intéressant à montrer, le cache étant facile et l'invalidation difficile ; (2) en phase 2, broker de la file de tâches du worker d'ingestion (Celery ou arq l'exigent) ; (3) compteurs atomiques du rate limiting du chatbot et du MCP. Une brique, trois rôles, un ADR. Règles : TTL courts, invalidation explicite, le cache n'est jamais une source de vérité. Complément « optimisation » côté HTTP : en-têtes `Cache-Control` et `ETag`, images redimensionnées en WebP, cache CDN de Cloudflare pour les fichiers statiques.

**Cloudflare : à quoi ça sert ici ?** Offre gratuite, placée devant le VPS : DNS ; proxy qui masque l'IP du serveur ; TLS au bord ; CDN pour les fichiers statiques et les images ; pare-feu applicatif (WAF) et protection DDoS ; règles de rate limiting ; **Turnstile** (captcha invisible) pour le chatbot ; **Cloudflare Access** pour n'autoriser l'accès à l'admin qu'après authentification par une identité Google ou GitHub, sans exposer le formulaire de connexion Django. Coût nul, et une couche de sécurité crédible pour un service public. Inconvénients : dépendance à un tiers américain qui voit le trafic en clair au bord, et effet « boîte noire » si mal compris. Alternative sans Cloudflare : Caddy pour le TLS, `fail2ban` et pare-feu, rate limiting applicatif, admin derrière Tailscale ou liste d'IP. Reco : Cloudflare free ; l'ADR documentera le compromis.

**Email : pourquoi un fournisseur ?** Besoins : l'action `send_message` du MCP (phase 3), les notifications de l'admin (nouveau message, ingestion en échec), éventuellement la réinitialisation du mot de passe admin. Envoyer depuis le VPS avec son propre serveur SMTP est un piège : réputation de l'IP, SPF / DKIM / DMARC à configurer, courriers en spam. Django envoie via n'importe quel SMTP : un fournisseur transactionnel (Brevo, Resend, Postmark) en offre gratuite suffit largement. Alternative à coût nul sans email : messages stockés en base, visibles dans l'admin, notification par webhook Telegram ou Discord. Décision non bloquante avant la phase 3.

**Stockage des médias : une librairie Django sur le VPS ?** Oui. Le stockage de fichiers par défaut de Django écrit sur le disque (volume Docker) ; Caddy sert les fichiers directement. Largement suffisant pour quelques centaines d'images. On garde l'abstraction `django-storages` dans le code : passer à un stockage S3 devient un changement de configuration, ce qui fait un bon ADR (« pourquoi le disque local aujourd'hui, et à quel signal on bascule »). Prévoir le redimensionnement et la conversion WebP à l'upload (Pillow, `django-imagekit` ou équivalent).

**Redis, worker, Postgres + pgvector en conteneurs sur le VPS ?** Oui, c'est exactement la cible. Précision de vocabulaire : Redis et Postgres sont des **services** (conteneurs qui tournent en permanence) ; le **worker** est un processus séparé qui consomme les tâches de fond (ingestion, vignettes, envois d'email). Composition Docker Compose visée :

| Conteneur | Rôle | Phase |
|---|---|---|
| `caddy` | Reverse proxy, TLS automatique, fichiers statiques et médias ; seul conteneur exposé (80 / 443) | 1 |
| `web` | Frontend (technologie décidée en dernier ; peut être servi en statique par Caddy) | 1 |
| `api` | Django : contenu, admin, API | 1 |
| `postgres` | Image `pgvector/pgvector` : contenu, vecteurs, checkpoints LangGraph | 1 (pgvector activé en 2) |
| `redis` | Cache, puis broker et rate limiting | 1 |
| `worker` | Tâches de fond (Celery ou arq) : vignettes, puis ingestion | 1 ou 2 |
| `ai` | LangGraph + LangSmith, chat en streaming | 2 |
| `mcp` | Serveur MCP (Streamable HTTP) | 3 |

Réseau Docker privé entre conteneurs, aucun port de base de données exposé. Dimensionnement : 2 vCPU / 4 Go suffisent pour l'ensemble ; 8 Go si un modèle d'embeddings ou un parseur PDF lourd tourne en local.

**Sauvegardes : un point de désaccord assumé.** L'auteur juge les sauvegardes non nécessaires. Avis : un dump Postgres nocturne plus une copie du volume médias vers un stockage externe bon marché (Hetzner Storage Box, Cloudflare R2, Backblaze B2) tient en une tâche cron et coûte de 0 à 4 € par mois ; sans cela, une panne de disque ou une erreur de manipulation oblige à ressaisir chaque projet à la main dans l'admin. Reco maintenue, décision laissée à l'auteur.

**Estimation mensuelle révisée (VPS).**

| Brique | Solution | Par mois |
|---|---|---|
| VPS 2 vCPU / 4 Go | Hetzner CX22 ou CAX11, OVH, Scaleway | 4 à 8 € |
| Variante 8 Go (modèles locaux) | Hetzner CX32 ou équivalent | 7 à 12 € |
| Domaine | | ~1 € |
| Cloudflare (DNS, proxy, WAF, Turnstile, Access) | Offre gratuite | 0 |
| Email transactionnel (phase 3) | Brevo, Resend, Postmark | 0 |
| LangSmith, Sentry, GitHub Actions | Offres gratuites | 0 |
| API Claude + embeddings | Usage réel, trafic faible | 5 à 15 € |
| Sauvegardes hors site (optionnel) | Storage Box, R2, B2 | 0 à 4 € |
| **Total** | | **10 à 30 €** |

### 8.5 Troisième tour (2026-09-10, suite)

| Sujet | Réponse | Effet |
|---|---|---|
| Cloudflare | OK. | D23 |
| Email | Mis de côté, tout est conçu sans ; post-MVP, peut-être jamais. | D24 |
| Stockage des médias | Question : la centralisation des données pour le RAG impose-t-elle un stockage ailleurs ? Faut-il un outil de stockage ? Réponse en 8.6. | D25 |
| Sauvegardes | Acceptées. Questions : cron ? stockées où, par qui ? un outil déjà retenu s'en charge-t-il ? Réponse en 8.6. | D26 |
| Q2 | Django confirmé, avec exigence de code minimal : pas de rôles ni de droits (un seul utilisateur), aucune ligne inutile. | D27 |
| Q15 | FR seul, mais contenu « bien orchestré », pas de valeurs en brut. Interprétation à confirmer en 8.6. | D28 |
| Q34 | Question : que veut dire « LangSmith cloud » ? Le RAG serait-il dans LangSmith ? À quoi sert la page de confidentialité ? Réponse en 8.6. Décision en attente. | — |
| Q55 | Pas de nom de domaine. | D29 |

### 8.6 Éclaircissements du troisième tour

**Centraliser les données pour le RAG et stocker les fichiers sont deux choses différentes.** La centralisation du RAG concerne le *texte* : fiches projets (déjà en base via les modèles Django), texte extrait des PDF, profil structuré. Le point de centralisation est Postgres : une table de documents sources, une table de chunks avec leurs embeddings (pgvector). Le RAG ne lit jamais les octets d'une image ; s'il doit « connaître » une image, ce sont sa légende et son texte alternatif, stockés en base, qui sont indexés. Un PDF est stocké comme fichier, mais son texte extrait vit en base après ingestion. L'emplacement physique des fichiers n'influence donc pas la centralisation.

**Où stocker les fichiers : disque du VPS ou Cloudflare R2 ?** Cloudflare étant retenu, R2 devient l'option naturelle : stockage objet compatible S3, 10 Go gratuits, aucun frais de sortie, intégré à Django par `django-storages`, images servies depuis le CDN sur un sous-domaine `media.`, fichiers hors du serveur (le VPS redevient jetable et reconstructible), sauvegardes simplifiées (seul Postgres reste à sauvegarder). Coût : une configuration d'une dizaine de lignes, un bucket privé pour les documents du RAG et un bucket public pour les images ; en développement, le stockage disque par défaut (l'abstraction rend la bascule triviale). Le disque du VPS reste viable mais rend le serveur stateful et double le périmètre des sauvegardes. Reco : R2, sauf objection (D25).

**Sauvegardes : comment ça marche concrètement.** (1) Quoi : Postgres (contenu, profil, messages, fils de conversation, vecteurs) ; les fichiers sont déjà sur R2, durable par construction. (2) Qui : un conteneur `backup` dans le Docker Compose, avec un cron nocturne, qui lance `pg_dump` (format compressé), chiffre l'archive (outil `age`, clé conservée hors du serveur) et l'envoie avec `rclone` dans un bucket R2 privé `backups`. (3) Rétention : 7 sauvegardes quotidiennes + 4 hebdomadaires, purge automatique. (4) Restauration : commande `make restore` documentée et testée une fois par trimestre ; une sauvegarde jamais restaurée n'est pas une sauvegarde. (5) Option fournisseur : Hetzner et OVH proposent des snapshots automatiques de la machine entière (environ 20 % du prix du serveur, soit ~1 €/mois) ; utile pour reconstruire vite après une panne, mais même fournisseur et restauration en bloc : complément, pas remplacement. Aucun outil déjà retenu ne fait cela seul : R2 est le lieu de stockage, le conteneur `backup` l'exécutant, le cron le déclencheur.

**Django et le code minimal.** Distinguer ce que le framework apporte (auth, permissions, groupes : présents dans Django, pas dans notre code, impossibles et inutiles à retirer) de ce que nous écrivons. Règles retenues : un seul superutilisateur créé par commande ; aucun groupe, aucune permission personnalisée ; `Group` retiré de l'admin ; `INSTALLED_APPS`, middlewares et réglages limités à ce qui est utilisé (l'admin impose `auth`, `contenttypes`, `sessions`, `messages`) ; aucun résidu du squelette `startproject` (commentaires, réglages par défaut non lus) ; pas de code mort, pas d'abstraction « au cas où ». « Chaque ligne sert un but » devient une règle de revue inscrite dans la configuration Claude Code du projet.

**FR seul, « pas de valeur en brut » (interprétation à confirmer).** (1) Tout le contenu (projets, profil, textes de présentation) vient de la base via l'API ; rien n'est écrit en dur dans le front. (2) Les libellés d'interface (boutons, titres de sections) sont centralisés dans un seul catalogue de chaînes, avec le mécanisme d'internationalisation du framework et FR comme unique langue : ajouter l'anglais plus tard consiste à ajouter un fichier, pas à toucher au code. (3) Aucune valeur magique dans le code : configuration dans les réglages et variables d'environnement, énumérations pour les types et statuts.

**LangSmith cloud : ce que c'est, ce que ce n'est pas.** Le RAG tourne entièrement sur le VPS : code, données, vecteurs, appels au LLM. LangSmith est un service *séparé* d'observabilité, hébergé par LangChain (« cloud » = sur leurs serveurs ; l'auto-hébergement est réservé aux offres entreprise). Notre code lui envoie des *traces* : une copie de ce qui s'est passé à chaque exécution du graphe (entrées et sorties de chaque nœud, durées, tokens, erreurs), comme une boîte noire d'avion. On consulte ces traces dans l'interface web de LangSmith pour déboguer, mesurer et évaluer. L'envoi est asynchrone : si LangSmith est indisponible, le chatbot fonctionne quand même. Offre gratuite avec quota mensuel de traces et rétention courte ; région UE disponible. **Page de confidentialité :** les questions tapées par les visiteurs peuvent contenir des données personnelles (un nom, une entreprise). Elles sont transmises à Anthropic (pour répondre), à LangSmith (traces) et conservées chez nous (mémoire de conversation). Le RGPD impose d'informer : ce qui est collecté, pourquoi, quels sous-traitants (Anthropic, LangChain, Cloudflare, hébergeur), combien de temps, et les droits du visiteur. Une page statique suffit, et c'est un signe de sérieux. Mesures de réduction : rétention courte, aucune IP ni identifiant nominatif dans les traces, identifiants de session anonymes.

**Nom de domaine.** À acheter avant le déploiement, pas avant le développement. Reco : Cloudflare Registrar (prix coûtant, DNS déjà chez Cloudflare) si l'extension voulue est proposée, sinon OVH ou Gandi avec les serveurs DNS pointés vers Cloudflare. Sous-domaines prévus : `www` (site), `api`, `media` (R2), `mcp` ; l'admin derrière Cloudflare Access. Choix du nom : à l'auteur.

### 8.7 Quatrième tour (2026-09-11)

| Sujet | Réponse | Effet |
|---|---|---|
| Centralisation RAG | Compris. | — |
| R2 | OK. Questions : détecteur de ré-ingestion à l'ajout ou au retrait d'un PDF ? qu'est-ce qu'un CDN ? comment éviter un serveur stateful ? Réponses en 8.8. | D30, D31, D32 |
| Sauvegardes | Schéma validé. Question : d'autres idées ? Réponse en 8.8. | D33 |
| Code minimal | Confirmé. | D27 |
| FR seul | Interprétation confirmée. Question : est-ce conforme aux bonnes pratiques ? Réponse en 8.8. | D34 |
| LangSmith cloud, page de confidentialité | OK. | D35 |
| Domaine | Cloudflare Registrar + sous-domaines. Demande d'idées de nom pour « Pacôme Bernier ». Voir 8.9. | D36 |

### 8.8 Éclaircissements du quatrième tour

**Détecteur de ré-ingestion.** Oui, c'est le cœur de la phase 2. Les documents (CV, récits d'expérience, PDF) sont un modèle Django `Document` avec un champ fichier stocké sur R2 ; on les ajoute et retire dans l'admin. À la sauvegarde d'un document, le signal Django écrit un événement dans une table outbox ; le worker le consomme : téléchargement depuis R2, extraction du texte, découpage, embeddings, écriture des chunks en base. À la suppression, l'événement inverse purge les chunks et embeddings du document. Un hash du contenu évite de ré-embedder ce qui n'a pas changé ; l'admin affiche l'état (« en attente », « indexé le… », « en erreur »). Règle : un fichier déposé directement dans le bucket sans passer par l'admin n'existe pas pour le RAG ; la base est la source de vérité. Les fiches projets suivent le même mécanisme.

**CDN.** Content Delivery Network : un réseau de serveurs répartis dans le monde qui gardent des copies des fichiers statiques (images, CSS, JS) au plus près des visiteurs. Un visiteur reçoit l'image depuis le serveur Cloudflare le plus proche de lui, pas depuis le VPS. Effets : chargement plus rapide, moins de charge sur le VPS, pics de trafic absorbés. Le proxy Cloudflare joue ce rôle pour le site, et R2 sert ses fichiers par ce même réseau.

**Serveur stateful : la solution.** « Stateful » signifie que la machine détient des données qu'on ne peut pas régénérer : si elle disparaît, elles disparaissent. Avec R2, les fichiers sortent du VPS ; il ne reste que Postgres. Deux options : (a) garder Postgres sur le VPS, unique composant stateful, sauvegardé chaque nuit vers R2, et rendre tout le reste reproductible depuis le dépôt (script d'amorçage + Docker Compose + Caddyfile, secrets dans un gestionnaire de mots de passe) : reconstruire le VPS = lancer le script, restaurer le dump ; (b) Postgres managé (Neon en région UE, Scaleway) : VPS entièrement stateless et sauvegardes assurées par le fournisseur, mais soit gratuit avec mise en veille (première requête lente), soit 12 à 19 € par mois, plus quelques millisecondes de latence réseau sur chaque requête. Reco : (a). Un seul volume, un seul job de sauvegarde, et l'ADR « pourquoi Postgres sur le VPS » est simple à écrire.

**Sauvegardes : autres idées.** (1) Infrastructure as code (ci-dessus) : la sauvegarde ne sert à rien si on ne sait pas reconstruire la machine. (2) Un ping vers healthchecks.io (gratuit) à la fin de chaque sauvegarde : si le ping manque, alerte ; c'est le « dead man's switch » qui détecte une sauvegarde silencieusement cassée. (3) Test de restauration automatisé : un job mensuel restaure le dernier dump dans un Postgres temporaire et exécute une requête de contrôle. (4) Écarté : archivage continu des WAL avec pgBackRest ou WAL-G (restauration à la seconde près, surdimensionné ici), réplication vers un second serveur, Postgres managé (voir ci-dessus). (5) Snapshots du fournisseur en complément, ~1 €/mois.

**FR seul : bonnes pratiques ?** Oui, c'est la pratique standard : séparer le contenu (en base, éditable) de l'interface (libellés dans un catalogue de chaînes via le mécanisme d'internationalisation, `gettext` côté Django et l'équivalent côté front), et sortir toute valeur de configuration du code (variables d'environnement, énumérations). Le piège à éviter est l'inverse : construire toute la plomberie multilingue « au cas où » (champs `title_fr` / `title_en`, sélecteur de langue, détection de locale). On garde les chaînes dans un catalogue, rien de plus, tant que l'anglais n'est pas demandé. Cohérent avec D27.

### 8.9 Nom de domaine : candidats

Contraintes : pas d'accent dans un nom de domaine (« pacome »), nom facile à dicter, extension crédible. `.dev` : extension orientée développeurs, HTTPS obligatoire par construction (liste HSTS préchargée), vendue par Cloudflare Registrar, ~12 € par an. `.fr` : crédible pour un public français, ~8 € par an ; d'après la page des extensions de Cloudflare consultée le 2026-09-11, `.fr` n'est pas proposé par Cloudflare Registrar (`.dev` et `.com` le sont) : un `.fr` s'achèterait chez OVH ou Gandi avec les DNS chez Cloudflare. `.com` : universel, ~10 € par an.

Vérification RDAP du 2026-09-11 (404 = non enregistré, donc a priori disponible ; à confirmer au moment de l'achat, les noms courts en `.dev` peuvent être vendus au tarif « premium ») :

| Nom | Statut |
|---|---|
| pacome.dev | disponible |
| pacomebernier.dev | disponible |
| pacomebernier.fr | disponible |
| pacomebernier.com | disponible |
| pacome-bernier.dev | disponible |
| pacome-bernier.fr | disponible |
| pbernier.dev | disponible |
| pacomeb.dev | disponible |
| pacome.fr | pris |
| bernier.dev | pris |

Reco : `pacome.dev` en premier choix si le prix est standard (court, mémorisable, identité de développeur), sinon `pacomebernier.dev`. Éviter le tiret (se dicte mal). Option : prendre aussi `pacomebernier.fr` en redirection pour le public français. Sous-domaines : `www` (site), `api`, `media`, `mcp` ; admin derrière Cloudflare Access.

### 8.10 Cinquième tour (2026-09-11)

- Domaine : `pacome.dev` retenu (D37).
- Question : « si le serveur est stateful, ajouter un document dans R2 ne lance pas le pipeline d'ingestion, et le document n'est pas disponible dans le RAG avant un rebuild de l'application ? » Réponse : non, les deux notions sont indépendantes. « Stateful » décrit seulement l'endroit où vivent les données (Postgres sur le VPS) ; cela n'a aucun lien avec le déclenchement de l'ingestion. Un document s'ajoute via le formulaire d'upload de l'admin : Django envoie le fichier sur R2 **et** crée la ligne en base dans la même opération ; le signal de sauvegarde émet l'événement ; le worker, processus qui tourne en permanence, l'ingère en quelques secondes à quelques minutes. Aucun rebuild, aucun redéploiement : le contenu est de la donnée, pas du code ; seul un changement de code nécessite un déploiement. Le seul cas où rien ne se passe : déposer un fichier directement dans le bucket depuis le tableau de bord Cloudflare, en contournant l'admin. Django ne le voit pas, d'où la règle « la base est la source de vérité ». Un écouteur d'événements R2 pourrait couvrir ce cas, mais c'est de la complexité pour un chemin qu'on n'utilisera pas.

### 8.11 Sixième tour (2026-09-11) : Postgres sur le VPS, et plan de reprise

**Postgres sur le VPS : avis sincère.** Oui, c'est ce que je ferais, pour ce projet précisément. Arguments : trafic minuscule, base de quelques centaines de Mo, requêtes pgvector locales (pas de latence réseau), coût nul, un seul fichier Compose, environnement de développement identique à la production. Le seul vrai argument pour un Postgres managé est la sauvegarde continue ; or le contenu change rarement, et perdre au pire une journée de saisie dans l'admin est acceptable (les fils de conversation et les traces ne sont pas précieux). Je choisirais un Postgres managé si l'une de ces conditions apparaissait : données modifiées en continu avec une perte tolérée inférieure à une journée, plusieurs applications ou serveurs partageant la base, besoin de faire grandir le VPS horizontalement, ou volonté de zéro exploitation. Aucune ne s'applique. Contrepartie assumée : les montées de version majeure de Postgres et le réglage mémoire sont à notre charge (petits ici). L'ADR consignera ces conditions de réexamen.

**Plan de reprise : ce qui est prévu.** Objectifs chiffrés : RPO 24 h (au pire, on perd la journée écoulée), RTO 1 h (site de nouveau en ligne en moins d'une heure). Moyens :

1. `infra/` versionné dans le dépôt : `compose.yml`, `Caddyfile`, `bootstrap.sh` (installe Docker, crée l'utilisateur, configure le pare-feu, récupère les images, écrit le `.env` à partir des secrets), `RUNBOOK.md` (procédures pas à pas).
2. Secrets hors du serveur : gestionnaire de mots de passe (Bitwarden ou 1Password) et secrets GitHub Actions ; la clé de chiffrement des sauvegardes y est conservée, jamais uniquement sur le VPS.
3. Sauvegarde nocturne : `pg_dump` → chiffrement `age` → `rclone` vers le bucket R2 `backups` → ping healthchecks.io (alerte si le ping manque).
4. Restauration en une commande : `make restore BACKUP=<date>` télécharge, déchiffre, restaure dans le conteneur Postgres, vérifie les migrations, lance un test de fumée. Documentée dans le runbook.
5. Test de restauration automatisé et mensuel : un job récupère le dernier dump, le restaure dans un Postgres jetable, exécute une requête de contrôle (comptages), et alerte en cas d'échec. Une sauvegarde jamais restaurée n'est pas une sauvegarde.
6. Scénario « le VPS a disparu » : louer un VPS, pointer le DNS Cloudflare dessus, lancer `bootstrap.sh`, lancer `make restore`, vérifier. Les médias sont déjà sur R2 : rien à faire. Objectif : moins d'une heure.
7. La configuration Cloudflare (DNS, Access, Turnstile) est elle aussi un état : documentée dans le runbook au minimum ; Terraform avec le provider Cloudflare en option (ADR, brique « infrastructure as code » démontrable).
8. Snapshots du fournisseur en complément (~1 €/mois) : reprise rapide de la machine entière, mais même fournisseur ; ne remplace pas les points 3 à 6.

### 8.12 Prochaine étape

Tous les points bloquants sont tranchés. Étape suivante proposée : réécrire ce document en « cadrage v1 » propre (vision, décisions consolidées D1-D36, architecture cible, questions résiduelles en annexe), puis mettre en place la configuration Claude Code du projet (règles, skills, pipeline de développement) avant toute ligne de code.
