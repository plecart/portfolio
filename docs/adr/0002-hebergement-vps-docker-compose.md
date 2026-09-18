# 0002 — Hébergement : VPS unique, Docker Compose, Caddy

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D19 (`docs/cadrage-technique.md` §7) ; conteneurs §5.3

## Contexte

Le portfolio est composé de services conteneurisés : reverse proxy, Django, Postgres, Redis,
worker, sauvegarde en phase 1 ; service IA et modèles d'embeddings en phase 2 ; serveur MCP en
phase 3. Il faut décider où ils tournent, avec un budget global d'environ 50 € par mois, un ou deux
visiteurs occasionnels, et le principe P3 « services managés plutôt qu'auto-hébergement quand le
coût le permet ».

## Facteurs de décision

- Coût mensuel.
- Charge d'exploitation (mises à jour, sauvegardes, durcissement) pour un seul développeur.
- Contrôle : mêmes images en développement et en production, environnement identique.
- Lisibilité de l'architecture pour la fiche du méta-projet.

## Options considérées

1. **Kubernetes** : orchestrateur multi-machines (répartition, auto-scaling, auto-réparation).
2. **VPS unique** (Hetzner, OVH, Scaleway) avec Docker Compose, tout sur une machine.
3. **PaaS** (Fly.io, Render, Railway ; français : Scalingo, Clever Cloud) : on pousse des
   conteneurs, la plateforme fournit exécution, TLS, logs, redémarrages.
4. **Tout managé, composable** : PaaS pour les conteneurs + Postgres managé (Neon, Supabase) +
   Redis managé (Upstash) + R2 + Cloudflare + LangSmith + Sentry.

## Décision

**Un VPS unique en UE, Docker Compose, Caddy en reverse proxy.** Exception assumée au principe P3 :
le coût réduit et le contrôle total l'emportent, à ce trafic.

- **Machine** : 2 vCPU, 4 Go en phase 1, 8 Go à partir de la phase 2 (modèles d'embeddings
  locaux) ; Hetzner, OVH ou Scaleway, région UE ; Ubuntu LTS.
- **Durcissement du système** : `ufw` (seul 22 ouvert), `fail2ban`,
  `unattended-upgrades`, OpenSSH par clés uniquement.
- **Conteneurs** : Docker Engine + Docker Compose ; réseau Docker privé ; aucun port de base de
  données exposé ; images construites en CI et publiées sur GHCR (D43), jamais construites sur le
  serveur ; déploiement par SSH (`docker compose pull && docker compose up -d`), migrations
  automatiques.
- **`cloudflared`** : Cloudflare Tunnel, seule entrée du VPS (D45, ADR 0003) ; connexion sortante
  vers Cloudflare, aucun port web publié.
- **Caddy** : aucun port publié, pas de TLS (terminé par Cloudflare) ; sert le frontend compilé
  (ADR 0008) ; route par nom d'hôte vers `api`, puis `ai` et `mcp`.
- **Reproductibilité** : `infra/` versionné (`compose.yml`, `Caddyfile`, `bootstrap.sh`,
  `RUNBOOK.md`) ; le VPS se reconstruit depuis le dépôt et la dernière sauvegarde (ADR 0007).
- **Développement local** : même Compose avec Docker Desktop (Postgres, Redis, stockage disque).

Écartés pour le reverse proxy : **Traefik** (configuration par labels, plus riche et plus verbeuse
que le besoin) et **nginx** (configuration plus longue). Caddy tient en quelques lignes et sert
les statiques.

## Conséquences

**Positives**

- 4 à 8 € par mois en phase 1, 7 à 12 € en phase 2, contre 15 à 45 € en tout managé.
- Un seul fichier Compose, environnement de développement identique à la production.
- Contrôle total, aucune configuration propre à un fournisseur.

**Négatives, assumées**

- Nous sommes l'administrateur : mises à jour, sauvegardes, restauration, durcissement. La charge
  est réduite par `unattended-upgrades`, un conteneur `backup` (ADR 0007) et un VPS reproductible.
- Point de panne unique. Toléré : RTO d'une heure par reconstruction (ADR 0007).
- Contraire à P3 : exception documentée ici, pas une règle.

## Comparaison des options

| Option | Pour | Contre | Coût estimé |
|---|---|---|---|
| Kubernetes | Standard en entreprise | Coût et complexité sans rapport avec deux visiteurs | Écarté sans chiffrage |
| **VPS unique** | Le moins cher, contrôle total, classique | Administration à charge, point de panne unique | 5 à 15 € |
| PaaS | Zéro administration ; services isolés ; régions UE | Facturation par service ; moins de contrôle ; configuration propre au fournisseur | 10 à 25 € pour les seuls conteneurs |
| Tout managé | L'architecture « chaque brique à sa place » ; offres gratuites généreuses | Beaucoup de comptes ; offres gratuites changeantes ; mise en veille des bases gratuites ; données réparties | 15 à 45 € |

## Conditions de réexamen

- Besoin de plusieurs serveurs (charge, disponibilité).
- Volonté de zéro exploitation.
- Un service managé qui rendrait le VPS inutile à coût égal.
