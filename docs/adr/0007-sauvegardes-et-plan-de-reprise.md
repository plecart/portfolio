# 0007 — Sauvegardes et plan de reprise

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D26, D33, D38, D42 (`docs/cadrage-technique.md` §7) ; plan détaillé §6.7

## Contexte

L'auteur jugeait d'abord les sauvegardes non nécessaires. Point de désaccord assumé pendant le
cadrage : sans elles, une panne de disque ou une erreur de manipulation oblige à ressaisir chaque
projet à la main dans l'admin ; un dump nocturne vers un stockage externe tient en une tâche cron
et coûte de 0 à 4 € par mois. Les sauvegardes ont été acceptées (D26), puis complétées par des
garde-fous (D33) et un plan de reprise chiffré (D38).

Ce qu'il y a à sauvegarder : Postgres seulement (ADR 0005) — contenu, profil, messages, fils de
conversation, vecteurs. Les fichiers sont sur R2 (ADR 0004), durables par construction. Le reste du
VPS est reproductible depuis le dépôt (ADR 0002).

## Facteurs de décision

- Objectifs chiffrés : **RPO 24 h** (au pire, la journée écoulée est perdue) et **RTO 1 h** (site de
  nouveau en ligne en moins d'une heure).
- Une sauvegarde jamais restaurée n'est pas une sauvegarde.
- Une sauvegarde silencieusement cassée doit se voir.
- La clé de chiffrement ne doit jamais exister uniquement sur le VPS.
- Coût nul ou presque.

## Options considérées

1. **Aucune sauvegarde** (position initiale).
2. **Snapshots du fournisseur seuls** (Hetzner, OVH : image de la machine entière).
3. **Dump nocturne chiffré vers un stockage objet**, avec restauration testée.
4. **Archivage continu des WAL** (pgBackRest, WAL-G) : restauration à la seconde près.
5. **Réplication** vers un second serveur.
6. **Postgres managé** avec sauvegardes fournies.

## Décision

**Option 3, en huit points**, exécutée par un conteneur `backup` dédié (D42).

1. **`infra/` versionné** : `compose.yml`, `Caddyfile`, `bootstrap.sh` (installe Docker, crée
   l'utilisateur, configure le pare-feu, tire les images, écrit le `.env` à partir des secrets),
   `RUNBOOK.md` (procédures pas à pas). La sauvegarde ne sert à rien si l'on ne sait pas reconstruire
   la machine.
2. **Secrets hors du serveur** : gestionnaire de mots de passe (Bitwarden ou 1Password) et secrets
   GitHub Actions ; la clé de chiffrement des sauvegardes y est conservée, jamais uniquement sur le
   VPS.
3. **Sauvegarde nocturne** : `pg_dump` (format compressé) → chiffrement `age` → `rclone` vers le
   bucket R2 privé `backups` → ping healthchecks.io. Rétention 7 quotidiennes + 4 hebdomadaires,
   purge automatique.
4. **Restauration en une commande** : `make restore BACKUP=<date>` télécharge, déchiffre,
   `pg_restore` dans le conteneur Postgres, vérifie les migrations, lance un test de fumée.
   Documentée dans le runbook.
5. **Test de restauration automatisé et mensuel** : un job récupère le dernier dump, le restaure
   dans un Postgres jetable, exécute une requête de contrôle (comptages) et alerte en cas d'échec.
6. **Scénario « le VPS a disparu »** : louer un VPS, pointer le DNS Cloudflare dessus, lancer
   `bootstrap.sh`, lancer `make restore`, vérifier. Les médias sont déjà sur R2. Objectif : moins
   d'une heure.
7. **La configuration Cloudflare est un état** (DNS, Access, Turnstile) : documentée dans le runbook
   au minimum ; Terraform avec le provider Cloudflare en option.
8. **Snapshots du fournisseur** en complément (~1 € par mois) : reprise rapide de la machine
   entière, mais même fournisseur et restauration en bloc ; ne remplace pas les points 3 à 6.

**Le conteneur `backup` (D42)** : Postgres fournit `pg_dump` mais rien ne l'ordonnance. Un
conteneur cron isolé (`supercronic`, cron conçu pour les conteneurs, journaux sur la sortie
standard), versionné dans le Compose, avec ses propres droits — un rôle Postgres en lecture seule
et la clé publique `age` uniquement. Aucun outil déjà retenu ne fait cela seul : R2 est le lieu de
stockage, le conteneur `backup` l'exécutant, le cron le déclencheur.

**healthchecks.io** joue le rôle de « dead man's switch » (D33) : si le ping attendu ne vient pas,
alerte. C'est ce qui détecte une sauvegarde silencieusement cassée. Le service est conservé pour
cet usage même si la surveillance de disponibilité externe a été écartée (D40).

## Conséquences

**Positives**

- RPO 24 h et RTO 1 h tenables avec un dump, un script et un runbook.
- Coût : 0 (R2 dans l'offre gratuite, healthchecks.io gratuit), ~1 € avec les snapshots.
- Un test mensuel automatique prouve que la restauration marche.

**Négatives, assumées**

- Perdre la clé `age` rend toutes les sauvegardes inutilisables : d'où le point 2.
- Un runbook et un job de test à maintenir.
- Pas de restauration à la seconde près : hors besoin, le contenu change rarement.

## Comparaison des options

| Option | Pour | Contre | Verdict |
|---|---|---|---|
| Aucune | Rien à faire | Ressaisie manuelle après tout incident | Écartée |
| Snapshots seuls | Une case à cocher | Même fournisseur ; restauration en bloc ; pas de test | Complément (point 8) |
| **Dump nocturne chiffré** | Simple, testable, gratuit | RPO 24 h | **Retenue** |
| WAL continu | Restauration fine | Surdimensionné pour un contenu qui change rarement | Écartée |
| Réplication | Bascule rapide | Second serveur à payer et exploiter | Écartée |
| Postgres managé | Sauvegardes fournies | ADR 0005 : coût, latence, mise en veille | Écartée |

## Conditions de réexamen

- Un RPO inférieur à 24 h ferait passer à l'archivage continu des WAL ou à un Postgres managé.
- Un échec du test mensuel est un incident, pas une condition de réexamen : il se corrige.
