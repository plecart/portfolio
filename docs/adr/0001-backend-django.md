# 0001 — Backend Django : contenu, admin et API

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D16, D17, D27 (`docs/cadrage-technique.md` §7)

## Contexte

La phase 1 du portfolio a besoin de trois choses : un back-office pour créer et éditer des
projets (titre, description Markdown, tags de technologies, galerie d'images, fiche technique en
sections), une API en lecture pour le frontend, et un modèle de données qui deviendra la source du
RAG en phase 2. Un seul développeur, un seul administrateur, un contenu qui change rarement, un ou
deux visiteurs occasionnels.

Le projet repart de zéro (D12) : l'ancien dépôt Django + Flutter n'a pas valeur de référence. La
question « Django par héritage ou vrai choix ? » a été posée explicitement pendant le cadrage ; la
décision ci-dessous ne s'appuie sur aucun code existant.

Le service IA de la phase 2 (LangGraph, streaming SSE) n'est pas couvert ici : il aura son propre
ADR à sa phase (le cadrage §5.2 retient FastAPI, exécuté séparément pour que le site vive sans lui).

## Facteurs de décision

- P1 simplicité : la brique la plus simple qui remplit le besoin.
- P4 / D27 code minimal : chaque ligne écrite sert un but.
- P5 sécurité par défaut sur l'admin, seule surface d'écriture de la phase 1.
- Un back-office réel, avec upload d'images, sans avoir à le construire.
- Un écosystème qui couvre stockage S3, cache Redis, vecteurs pgvector et 2FA sans code maison.

## Options considérées

**Framework**

1. Django seul : contenu, admin et API (`django-ninja`).
2. FastAPI seul, avec un admin à construire ou un outil tiers (sqladmin, starlette-admin).
3. Django pour le contenu + FastAPI pour l'API dès la phase 1.

**Back-office**

- a. Django admin personnalisé.
- b. CMS headless (Strapi, Directus, Payload ; SaaS : Sanity, Contentful).
- c. Content-as-code : un dossier versionné par projet (`project.yaml`, `fiche.md`, `images/`),
  validé en CI, importé en base au merge.
- d. Admin construit dans le frontend.

## Décision

**Django, seul en phase 1**, avec :

- **Django admin comme back-office (D16)**, personnalisé : éditeur Markdown, aperçus d'images,
  état d'indexation, bouton « ré-indexer », boîte de réception des messages (phase 3). Accessible
  uniquement derrière Cloudflare Access (ADR 0003), mot de passe fort et 2FA.
- **`django-ninja`** pour l'API HTTP typée ; son schéma OpenAPI sert à générer les types du
  frontend (ADR 0008).
- **Code minimal (D27)** : un seul superutilisateur créé par commande ; aucun groupe ni permission
  personnalisée ; écran « Groupes » retiré de l'admin ; `INSTALLED_APPS`, middlewares et réglages
  limités au strict utilisé (l'admin impose `auth`, `contenttypes`, `sessions`, `messages`) ; aucun
  résidu du squelette `startproject` ; « chaque ligne sert un but » est une règle de revue inscrite
  dans la configuration Claude Code du projet.

### Bibliothèques retenues autour de Django

| Rôle | Bibliothèque |
|---|---|
| Serveur WSGI | `gunicorn` |
| Pilote Postgres | `psycopg` (v3) |
| Champ vecteur (phase 2) | `pgvector` (paquet Python, support Django officiel) |
| Stockage objet (ADR 0004) | `django-storages` + `boto3` |
| Cache (ADR 0006) | `django-redis` |
| Images : redimensionnement, WebP, vignettes | `Pillow`, `django-imagekit` |
| Rendu Markdown et assainissement HTML | `markdown-it-py`, `nh3` |
| 2FA de l'admin | `django-otp` |
| CSP et en-têtes de sécurité | `django-csp` |
| Configuration 12-factor | `pydantic-settings` |
| Logs structurés JSON | `structlog` |
| Remontée d'erreurs | `sentry-sdk` |

Python 3.12, dépendances gérées par `uv`.

## Conséquences

**Positives**

- Le back-office existe dès le premier modèle ; il reste à l'ajuster, pas à l'écrire.
- ORM, migrations, auth, gestion des fichiers uploadés, formulaires : intégrés et cohérents.
- Sécurité par défaut : CSRF, échappement XSS, hachage des mots de passe, validation des uploads,
  en-têtes.
- Un seul framework à connaître en phase 1.

**Négatives, assumées**

- Async de second rang : sans importance en phase 1 ; le service IA sera un service séparé.
- Interface admin d'aspect daté : personnalisable, et vue par le seul auteur.
- Django embarque auth, permissions et groupes : présents dans le framework sans être utilisés,
  impossibles et inutiles à retirer. Le code minimal porte sur ce que *nous* écrivons.

## Comparaison des options

**Framework**

| | Django | FastAPI |
|---|---|---|
| Back-office | Admin généré depuis les modèles (formulaires, upload, filtres, recherche) | À construire, ou outil tiers moins complet |
| ORM et migrations | Inclus | SQLAlchemy + Alembic à assembler |
| Auth, sessions, CSRF, stockage S3 | Inclus ou paquets matures | À assembler |
| API typée + OpenAPI | `django-ninja` | Natif |
| Async, streaming SSE, LangGraph | Possible (ASGI), moins naturel | Natif |
| Poids | Cadre complet | Minimal |

FastAPI ne gagnerait que pour une API purement asynchrone sans back-office ; ce n'est pas le
besoin de la phase 1. L'option 3 (deux frameworks dès la phase 1) double le travail pour un
bénéfice qui n'apparaît qu'en phase 2 : la frontière Django / FastAPI sera tracée à ce moment-là.

**Back-office**

| Option | Pour | Contre | Verdict |
|---|---|---|---|
| Django admin | Gratuit, sûr, immédiat | Édition en formulaire, aspect basique | **Retenu** |
| CMS headless | Excellente interface, webhooks | Un système de plus à héberger ou payer ; modèle de données chez le CMS ; second runtime Node ; rend Django redondant | Écarté |
| Content-as-code | Versionné, relu par diff, aucune surface d'écriture, coût nul | Réservé à un développeur ; images, icônes et tags méritent une vraie interface | Écarté après essai de la reco |
| Admin dans le frontend | Vitrine | Beaucoup de travail pour un seul utilisateur ; contraire à D27 | Écarté |

## Conditions de réexamen

- Une API majoritairement asynchrone sans back-office ferait pencher vers FastAPI seul. Aucun
  signe dans les trois phases prévues.
