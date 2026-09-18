# Outils et librairies du projet

_Liste brute, sans détail. 2026-09-13. Source : cadrage-technique.md, décisions D1 à D43._

## Domaine et bord
- Cloudflare Registrar
- Cloudflare DNS
- Cloudflare Proxy / CDN
- Cloudflare WAF
- Cloudflare Rate Limiting
- Cloudflare Access
- Cloudflare R2
- Cloudflare Turnstile (optionnel, phase 2)
- Terraform + provider Cloudflare (optionnel)

## Serveur
- VPS (Hetzner, OVH ou Scaleway)
- Ubuntu LTS
- ufw
- fail2ban
- unattended-upgrades
- OpenSSH
- Docker Engine
- Docker Compose
- Caddy
- caddy-dns/cloudflare (ou Cloudflare Origin CA)
- supercronic

## Backend
- Python 3.12
- uv
- Django
- gunicorn
- django-ninja
- psycopg
- pgvector (package Python)
- django-storages
- boto3
- django-redis
- Pillow
- django-imagekit
- markdown-it-py
- nh3
- django-otp
- django-csp
- pydantic
- pydantic-settings
- structlog
- sentry-sdk
- PyJWT
- Celery (ou arq)

## Données
- PostgreSQL 16
- pgvector (extension)
- Redis 7

## Tâches et ingestion
- Celery worker + Celery beat (ou arq)
- Docling (ou Unstructured)
- pypdf
- langchain-text-splitters
- langchain-anthropic
- langchain-huggingface
- langsmith
- httpx

## Embeddings et reranking locaux
- text-embeddings-inference (Hugging Face)
- BAAI/bge-m3
- BAAI/bge-reranker-v2-m3

## Service IA
- FastAPI
- uvicorn
- LangGraph
- langgraph-checkpoint-postgres
- langchain-core
- langchain-anthropic
- anthropic (SDK)
- langchain-postgres
- langchain-huggingface
- langsmith
- sse-starlette
- redis (client Python)
- httpx
- langchain-mcp-adapters
- Claude : claude-opus-5, claude-haiku-4-5 (claude-sonnet-5 en option)
- LangSmith (SaaS, région UE)
- LangGraph Studio (langgraph-cli)

## MCP
- mcp (SDK Python, FastMCP)
- MCP Inspector

## Frontend
_Détail, versions et ordre d'installation : `frontend-outillage.md`._
- Vite
- React
- TypeScript
- Tailwind CSS v4 (+ @tailwindcss/vite)
- shadcn/ui (+ Radix)
- motion
- react-bits
- bklit-ui
- Rive (@rive-app/react-canvas)
- openapi-typescript
- ESLint + eslint-plugin-jsx-a11y
- Playwright + @axe-core/playwright
- Lighthouse CI (@lhci/cli)

## Outillage Claude Code et sécurité
- Skills : taste-skill, minimalist-skill, emil-design-eng, prototype, animate, review-animations, improve-animations, find-animation-opportunities, animation-vocabulary, no-ai-slop, improve-codebase-architecture
- SkillSpector
- strix
- Manus (SaaS)

## Sauvegarde et reprise
- pg_dump / pg_restore
- age
- rclone
- healthchecks.io
- Makefile
- Snapshots du fournisseur VPS (optionnel)

## Observabilité
- Sentry
- healthchecks.io
- LangSmith
- structlog
- Logs JSON Caddy

## Livraison et qualité
- Git
- GitHub (dépôt privé, Issues)
- GitHub Actions
- GHCR
- Renovate (ou Dependabot)
- ruff
- pyright
- pytest
- testcontainers
- Trivy
- pip-audit
- pre-commit
- Conventional Commits

## Secrets
- Bitwarden (ou 1Password)
- GitHub Actions secrets

## Développement local
- Docker Desktop
- MinIO (optionnel)
- Claude Code

## Méthode et documentation
- ADR au format MADR
- Markdown
