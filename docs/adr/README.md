# Architecture Decision Records

Un fichier MADR par décision structurante (cadrage §8.3, D8). Chaque ADR se lit seul : il est
indexé dans le RAG de la phase 2 et cité par la fiche du méta-projet.

## Conventions

- **Nommage** : `NNNN-sujet.md`, numéro séquentiel, jamais réutilisé.
- **Statut** : `proposé` · `accepté` · `remplacé par NNNN` · `abandonné`.
- **Un ADR accepté ne s'édite pas.** Pour revenir sur une décision : nouvel ADR, ancien passé en
  « remplacé par NNNN », ligne au registre §7 de `docs/cadrage-technique.md` (la décision
  remplacée y reste, marquée « remplacée par »).
- Chaque ADR cite les décisions du registre §7 qu'il documente (`D<n>`).
- Sections : Contexte · Facteurs de décision · Options considérées · Décision · Conséquences ·
  Comparaison des options · Conditions de réexamen (quand la décision en a).
- Toute référence croisée cite un § ou un titre de section, jamais un numéro de ligne.

## Index

| ADR | Sujet | Décisions | Statut |
|---|---|---|---|
| [0001](0001-backend-django.md) | Backend Django : contenu, admin et API | D16, D17, D27 | accepté ; point « Rendu Markdown » remplacé par 0010 |
| [0002](0002-hebergement-vps-docker-compose.md) | Hébergement : VPS unique, Docker Compose, Caddy | D19 | accepté ; point « un seul fichier Compose » remplacé par 0012 |
| [0003](0003-cloudflare-en-bordure.md) | Cloudflare en bordure et domaine `pacome.dev` | D23, D36, D37, D41 | accepté |
| [0004](0004-fichiers-sur-cloudflare-r2.md) | Fichiers sur Cloudflare R2 | D25, D30 (remplace D21) | accepté |
| [0005](0005-postgres-sur-le-vps.md) | Postgres 16 + pgvector sur le VPS | D32 | accepté ; argument « un seul fichier Compose » remplacé par 0012 |
| [0006](0006-redis-des-la-phase-1.md) | Redis dès la phase 1 | D20 | accepté |
| [0007](0007-sauvegardes-et-plan-de-reprise.md) | Sauvegardes et plan de reprise | D26, D33, D38, D42 | accepté |
| [0008](0008-frontend-statique-vite-react.md) | Frontend statique Vite + React + TypeScript + Tailwind CSS + shadcn/ui | D44 (remplace D15) | accepté ; point « slug inconnu » remplacé par 0009 ; condition « Vitest » levée par 0010 ; point « balises injectées » remplacé par 0011 |
| [0009](0009-adresse-de-fiche-inconnue.md) | Adresse de fiche inconnue : redirection vers l'accueil | D50 (remplace le point « slug inconnu » de 0008) | accepté |
| [0010](0010-rendu-markdown-dans-le-front.md) | Rendu du Markdown dans le front ; Vitest en phase 1 | D51 (remplace le point « Rendu Markdown » de 0001) | accepté ; décompte « quatre balises » corrigé par 0011 |
| [0011](0011-balises-d-apercu-du-gabarit.md) | Balises d'aperçu du gabarit : cinq, dont la description SEO | D53 (remplace le point « balises injectées » de 0008) | accepté |
| [0012](0012-deux-fichiers-compose.md) | Deux fichiers Compose, mêmes images | D54 (remplace le point « un seul fichier Compose » de 0002 et l'argument de 0005) | accepté |
| [0013](0013-ordre-des-lignes-par-glisser-deposer.md) | Ordre des lignes de l'admin par glisser-déposer | D55 | accepté |

## À écrire à leur phase

Le cadrage (annexe A) reporte ces décisions au moment où leur phase commence : moteur du worker
(Celery ou arq), service IA (FastAPI + LangGraph), LangSmith, embeddings et reranking locaux,
serveur MCP, authentification de `send_message`.
