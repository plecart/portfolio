# 0004 — Fichiers sur Cloudflare R2

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D25, D30 (`docs/cadrage-technique.md` §7) ; remplace D21

## Contexte

Le site stocke des fichiers : images et icônes des projets (phase 1), documents du RAG comme le CV
public et les récits d'expérience (phase 2), archives de sauvegarde (ADR 0007). Il faut décider où
ils vivent.

Une confusion a été levée pendant le cadrage : centraliser les données pour le RAG et stocker les
fichiers sont deux choses différentes. Le RAG travaille sur du *texte* — fiches projets, texte
extrait des PDF, profil structuré — dont le point de centralisation est Postgres (ADR 0005). Une
image n'est jamais lue par le RAG ; sa légende, stockée en base, l'est. L'emplacement physique des
fichiers n'influence donc pas la centralisation.

## Facteurs de décision

- Rendre le VPS jetable : aucun fichier non régénérable sur le serveur (ADR 0007).
- Périmètre des sauvegardes : ne sauvegarder que Postgres.
- Coût à quelques centaines d'images.
- Bascule triviale par configuration grâce à l'abstraction de stockage de Django.

## Options considérées

1. **Disque du VPS** : stockage par défaut de Django sur un volume Docker, fichiers servis par
   Caddy. C'était la décision initiale (D21).
2. **Cloudflare R2** : stockage objet compatible S3.
3. Autre stockage objet (Scaleway Object Storage, Backblaze B2, Hetzner Storage Box).

## Décision

**Cloudflare R2**, via `django-storages` et `boto3`.

- **Trois buckets** : un **public** pour les images, servi par le CDN Cloudflare sur
  `media.pacome.dev` ; un **privé** pour les documents du RAG (jamais servis en entier sauf ceux
  dont la visibilité est `public`, que Django sert lui-même) ; un **privé** `backups` (ADR 0007).
- **Traitement des images à l'upload** : redimensionnement, conversion WebP, vignettes (`Pillow`,
  `django-imagekit`), exécuté par le worker.
- **Développement** : stockage disque par défaut de Django ; MinIO seulement si un comportement
  propre à S3 doit être reproduit en local — optionnel, pas installé par défaut.
- **La base est la source de vérité (D31)** : un fichier déposé directement dans le bucket, sans
  passer par l'admin, n'existe pas pour le site ni pour le RAG. Django envoie le fichier sur R2 et
  crée la ligne en base dans la même opération ; le signal de sauvegarde déclenche la suite. Un
  écouteur d'événements R2 couvrirait ce cas mais ajouterait de la complexité pour un chemin qu'on
  n'utilisera pas.

## Conséquences

**Positives**

- Le VPS ne détient plus que Postgres : reconstructible depuis le dépôt et une sauvegarde.
- Un seul job de sauvegarde (Postgres) ; les fichiers sont durables par construction.
- 10 Go gratuits, aucun frais de sortie, images servies depuis le CDN.
- Configuration d'une dizaine de lignes ; la bascule vers un autre S3 reste un changement de
  configuration.

**Négatives, assumées**

- Dépendance à Cloudflare approfondie (ADR 0003).
- Deux comportements de stockage (disque en développement, R2 en production) : l'abstraction les
  rend identiques pour le code ; MinIO existe si un écart apparaît.

## Comparaison des options

| | Disque du VPS | R2 | Autre S3 |
|---|---|---|---|
| Serveur | Stateful : fichiers à sauvegarder | Jetable | Jetable |
| Sauvegardes | Postgres + volume | Postgres seul | Postgres seul |
| Diffusion | Caddy, depuis le VPS | CDN Cloudflare | CDN à configurer |
| Coût | 0 | 0 (10 Go) | 0 à quelques € |
| Comptes | Aucun | Déjà chez Cloudflare | Un fournisseur de plus |

Le disque du VPS reste viable à cette échelle, mais il rend le serveur stateful et double le
périmètre des sauvegardes. Un autre S3 n'apporte rien de plus que R2 et ajoute un compte.

## Conditions de réexamen

- Une volumétrie ou un coût de R2 qui dépasserait le budget.
- Un besoin de quitter Cloudflare : la bascule est une configuration `django-storages`, pas une
  réécriture.
