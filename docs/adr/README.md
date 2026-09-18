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
| [0001](0001-backend-django.md) | Backend Django : contenu, admin et API | D16, D17, D27 | accepté |
| [0002](0002-hebergement-vps-docker-compose.md) | Hébergement : VPS unique, Docker Compose, Caddy | D19 | accepté |
| [0003](0003-cloudflare-en-bordure.md) | Cloudflare en bordure et domaine `pacome.dev` | D23, D36, D37, D41 | accepté |
| [0004](0004-fichiers-sur-cloudflare-r2.md) | Fichiers sur Cloudflare R2 | D25, D30 (remplace D21) | accepté |
| [0005](0005-postgres-sur-le-vps.md) | Postgres 16 + pgvector sur le VPS | D32 | accepté |
| [0006](0006-redis-des-la-phase-1.md) | Redis dès la phase 1 | D20 | accepté |
| [0007](0007-sauvegardes-et-plan-de-reprise.md) | Sauvegardes et plan de reprise | D26, D33, D38, D42 | accepté |
| [0008](0008-frontend-statique-vite-react.md) | Frontend statique Vite + React + TypeScript + Tailwind CSS + shadcn/ui | D44 (remplace D15) | accepté |

## À écrire à leur phase

Le cadrage (annexe A) reporte ces décisions au moment où leur phase commence : moteur du worker
(Celery ou arq), service IA (FastAPI + LangGraph), LangSmith, embeddings et reranking locaux,
serveur MCP, authentification de `send_message`.
