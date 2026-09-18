# 0005 — Postgres 16 + pgvector sur le VPS

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D32 (`docs/cadrage-technique.md` §7)

## Contexte

Postgres est la base du projet : contenu et profil (phase 1), chunks et embeddings du RAG,
checkpoints LangGraph et table outbox (phase 2), messages reçus (phase 3). Deux questions ont été
tranchées : où tourne Postgres (sur le VPS ou managé), et où vivent les vecteurs (dans Postgres via
pgvector, ou dans une base vectorielle dédiée).

Avec les fichiers sur R2 (ADR 0004), Postgres est l'**unique composant stateful** de l'architecture.

## Facteurs de décision

- Coût et latence des requêtes (pgvector local ou distant).
- Simplicité : un seul fichier Compose, développement identique à la production.
- Perte de données tolérée : RPO 24 h (ADR 0007).
- Recherche hybride (texte + vecteurs) et sauvegardes unifiées.
- Charge d'exploitation d'un seul développeur.

## Options considérées

**Emplacement**

1. **Postgres en conteneur sur le VPS**, sauvegardé chaque nuit.
2. **Postgres managé** en région UE (Neon, Scaleway, Supabase).

**Vecteurs**

- a. **pgvector**, extension de Postgres.
- b. Base vectorielle dédiée (Qdrant, Weaviate).

## Décision

**Postgres 16 en conteneur sur le VPS, image `pgvector/pgvector`, pilote `psycopg` (v3).**
Aucun port exposé hors du réseau Docker privé ; sauvegarde nocturne chiffrée vers R2 et test de
restauration mensuel (ADR 0007). L'extension pgvector est activée en phase 2.

**pgvector pour les vecteurs** : une seule base pour le contenu, les vecteurs, les checkpoints et
l'outbox ; recherche hybride facile (BM25 via `tsvector` + vecteurs, fusion RRF) ; sauvegardes
unifiées.

Pourquoi sur le VPS, pour ce projet précisément : trafic minuscule, base de quelques centaines de
Mo, requêtes pgvector locales sans latence réseau, coût nul, un seul fichier Compose, environnement
de développement identique à la production. Le seul vrai argument pour un Postgres managé est la
sauvegarde continue ; or le contenu change rarement, et perdre au pire une journée de saisie dans
l'admin est acceptable. Les fils de conversation et les traces ne sont pas précieux.

## Conséquences

**Positives**

- Coût nul, latence nulle, un conteneur de plus dans le Compose existant.
- Sauvegardes et restauration sous notre contrôle, testées (ADR 0007).
- Une seule base à comprendre et à sauvegarder ; pas de synchronisation entre un index vectoriel
  et la base de contenu.

**Négatives, assumées**

- Montées de version majeure de Postgres et réglage mémoire à notre charge — petits ici.
- Pas de sauvegarde continue : RPO 24 h.
- Le VPS reste stateful pour ce seul composant ; sa reconstruction passe par une restauration.

## Comparaison des options

**Emplacement**

| | Sur le VPS | Managé |
|---|---|---|
| Coût | 0 | Gratuit avec mise en veille (première requête lente), sinon 12 à 19 € par mois |
| Latence | Locale | Quelques millisecondes réseau par requête |
| Sauvegardes | À nous (ADR 0007) | Fournies, continues |
| Développement | Identique à la production | Différent |
| Exploitation | Versions majeures, mémoire | Zéro |

**Vecteurs**

| | pgvector | Base dédiée |
|---|---|---|
| Services à exploiter | Aucun de plus | Un de plus, avec ses sauvegardes |
| Recherche hybride | `tsvector` + vecteurs dans une requête | Deux systèmes à fusionner |
| Cohérence contenu / index | Une transaction | À synchroniser |
| Vitrine | Suffisante à cette échelle | Plus « spécialisée » |

## Conditions de réexamen

Un Postgres managé redevient le bon choix si l'une de ces conditions apparaît :

- données modifiées en continu avec une perte tolérée inférieure à une journée ;
- plusieurs applications ou serveurs partageant la base ;
- besoin de faire grandir l'infrastructure horizontalement ;
- volonté de zéro exploitation.

Aucune ne s'applique aujourd'hui.
