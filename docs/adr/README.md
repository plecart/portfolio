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
| [0001](0001-backend-django.md) | Backend Django : contenu, admin et API | D16, D17, D27 | accepté ; point « Rendu Markdown » remplacé par 0010 ; point « `django-imagekit` » remplacé par 0015 ; point « `django-csp` » remplacé par 0020 |
| [0002](0002-hebergement-vps-docker-compose.md) | Hébergement : VPS unique, Docker Compose, Caddy | D19 | accepté ; point « un seul fichier Compose » remplacé par 0012 ; point « Machine » de la phase 1 et estimation remplacés par 0023 |
| [0003](0003-cloudflare-en-bordure.md) | Cloudflare en bordure et domaine `pacome.dev` | D23, D36, D37, D41 | accepté |
| [0004](0004-fichiers-sur-cloudflare-r2.md) | Fichiers sur Cloudflare R2 | D25, D30 (remplace D21) | accepté ; point « `django-imagekit` » remplacé par 0015 ; nom `backups` remplacé par 0021 |
| [0005](0005-postgres-sur-le-vps.md) | Postgres 16 + pgvector sur le VPS | D32 | accepté ; argument « un seul fichier Compose » remplacé par 0012 |
| [0006](0006-redis-des-la-phase-1.md) | Redis dès la phase 1 | D20 | accepté ; règle « outbox » remplacée par 0015 pour le worker d'images ; rôle 2 « broker » avancé en phase 1 par 0015 |
| [0007](0007-sauvegardes-et-plan-de-reprise.md) | Sauvegardes et plan de reprise | D26, D33, D38, D42 | accepté ; geste « pointer le DNS » du point 6 remplacé par le Tunnel de 0003 (D45, D58) ; nom `backups` remplacé par 0021 ; mention « Bitwarden ou 1Password » remplacée par 0022 |
| [0008](0008-frontend-statique-vite-react.md) | Frontend statique Vite + React + TypeScript + Tailwind CSS + shadcn/ui | D44 (remplace D15) | accepté ; point « slug inconnu » remplacé par 0009 ; condition « Vitest » levée par 0010 ; point « balises injectées » remplacé par 0011 ; repli `try_files` et point « routage » remplacés par 0030 |
| [0009](0009-adresse-de-fiche-inconnue.md) | Adresse de fiche inconnue : redirection vers l'accueil | D50 (remplace le point « slug inconnu » de 0008) | accepté |
| [0010](0010-rendu-markdown-dans-le-front.md) | Rendu du Markdown dans le front ; Vitest en phase 1 | D51 (remplace le point « Rendu Markdown » de 0001) | accepté ; décompte « quatre balises » corrigé par 0011 ; poids et HTML brut par défaut corrigés par 0024 |
| [0011](0011-balises-d-apercu-du-gabarit.md) | Balises d'aperçu du gabarit : cinq, dont la description SEO | D53 (remplace le point « balises injectées » de 0008) | accepté |
| [0012](0012-deux-fichiers-compose.md) | Deux fichiers Compose, mêmes images | D54 (remplace le point « un seul fichier Compose » de 0002 et l'argument de 0005) | accepté ; `worker` parmi ce que la production porte en propre remplacé par 0016 |
| [0013](0013-ordre-des-lignes-par-glisser-deposer.md) | Ordre des lignes de l'admin par glisser-déposer | D55 | accepté |
| [0014](0014-ci-cd-github-actions-et-ghcr.md) | CI/CD : GitHub Actions et GHCR | D56 (confirme D43) | accepté ; point « Scan sur chaque PR » remplacé par 0017 ; points « après `api`, `web` et `infra` », « il récupère `dist` du job `web` par artefact » et « Une image publiée a passé toute la CI » remplacés par 0031 |
| [0015](0015-moteur-du-worker-celery.md) | Moteur du worker : Celery ; variantes par Pillow seul | D59 (remplace le point « `django-imagekit` » de 0001 et 0004, et la règle « outbox » de 0006 pour le worker d'images ; rôle 2 « broker » de 0006 avancé en phase 1) | accepté ; contexte « VPS de 4 Go » remplacé par 0023 ; point « échelle … dont les 1200 px plafonnent l'échelle » remplacé par 0028 |
| [0016](0016-le-worker-dans-les-deux-fichiers-compose.md) | Le worker dans les deux fichiers Compose | D60 (remplace « le worker » parmi ce que la production porte en propre dans 0012 et D54) | accepté |
| [0017](0017-jobs-de-la-ci-selon-le-delta.md) | Les jobs de la CI selon le delta d'une PR | D61 (remplace le point « Scan : Trivy, sur chaque PR » de 0014) | accepté ; points « Le passage en ready ne déclenche plus de run », « seule l'ouverture d'une draft le saute », « partent après `api`, même rouge » et « le scan Trivy tourne sur chaque PR qui touche un fichier hors du harnais » remplacés par 0019 ; point « la suite du back porte aussi les tests de la pipeline » remplacé par 0025 ; points « tout y tourne », « et `publish` attend toujours les trois jobs », « Dans le doute, le job tourne », « Aucune porte retirée ni allégée », « liste d'exclusion », « Sur un push vers `main`, tout tourne » et « ou au push vers `main` suivant » remplacés par 0031 ; points « Option b », « La première étape du job `api` passe […] », « `web` et `infra` partent après la fin d'`api` » et les verdicts des options (a) et (b) remplacés par 0032 |
| [0018](0018-binaires-go-compiles-par-le-projet.md) | Binaires Go compilés par le projet | D62 (exerce une condition de réexamen de 0014, sans le remplacer) | accepté |
| [0019](0019-runs-de-ci-au-ready-et-avis-planifies.md) | Runs de CI au passage en ready, portes d'avis planifiées | D63 (remplace quatre points de 0017, dont deux repris dans D61 ; renverse la décision « sans horloge » de #77) | accepté ; points « Il tourne, comme tout run de PR, sur la référence de fusion que GitHub calcule… » (§ Décision, point 1) et « la porte de fraîcheur de l'Étape 7 reste la seule preuve de l'état combiné… » (§ Conséquences) remplacés par 0029 ; points « Aucune porte retirée du chemin vers la production », « Un avis neuf doit être vu sous un jour », « chaque jour sur `main` », « Sur un push vers `main`, tout tourne », « sur une PR comme sur `main` », « Un avis neuf est vu par le run planifié du lendemain » et « Sur `main`, un `api` rouge cache `web` et `infra` jusqu'au push correctif » remplacés par 0031 ; point « `web` et `infra` attendent un `api` vert » remplacé par 0032 |
| [0020](0020-csp-native-de-django.md) | CSP et en-têtes de sécurité par la brique native de Django | D65 (remplace le point « `django-csp` » de 0001) | accepté |
| [0021](0021-buckets-r2-prefixes-par-le-projet.md) | Noms des buckets R2 préfixés par le projet | D66 (remplace le nom `backups` de 0004 et 0007) | accepté |
| [0022](0022-keepassxc-comme-gestionnaire.md) | KeePassXC comme gestionnaire de mots de passe | D67 (remplace la mention « Bitwarden ou 1Password » de 0007) | accepté |
| [0023](0023-vps-de-phase-1-a-2-go.md) | VPS de phase 1 : 1 vCPU et 2 Go au minimum | D68 (remplace le point « Machine » de 0002 pour la phase 1, son estimation, et le contexte « VPS de 4 Go » de 0015) | accepté |
| [0024](0024-markdown-to-jsx-poids-et-html-brut.md) | `markdown-to-jsx` : poids mesuré et HTML brut désactivé | D51 (corrige deux énoncés de 0010) | accepté |
| [0025](0025-tests-de-la-pipeline-avec-elle-sur-son-delta.md) | Les tests de la pipeline vivent avec elle et tournent sur son delta | D69 (remplace le point « la suite du back porte aussi les tests de la pipeline » de 0017) | accepté ; points « sur un push vers `main`, toujours » et « et sur chaque push vers `main` » remplacés par 0031 |
| [0026](0026-schema-d-architecture-hors-ligne-et-playwright-python.md) | Le schéma d'architecture : rendu hors ligne, export par Playwright Python | D70 | accepté ; points « 1200 × 1200 px » et « facteur d'échelle 1 » remplacés par 0028 |
| [0027](0027-remontee-d-erreurs-sentry-et-logs-structures.md) | Remontée d'erreurs Sentry et logs structurés | D71 | accepté |
| [0028](0028-couverture-et-schema-a-2400-px.md) | La couverture et le schéma d'architecture à 2400 px de côté | D72 (remplace le point « échelle … 1200 px plafonnent » de 0015, les points « 1200 × 1200 px » et « facteur d'échelle 1 » de 0026, et le point du côté de D70) | accepté |
| [0029](0029-fusion-explicite-du-trunk-dans-les-runs-de-pr.md) | Les runs de PR fusionnent eux-mêmes la tête au trunk courant | D73 (remplace le point 1 de § Décision et un point de § Conséquences de 0019) | accepté |
| [0030](0030-routes-de-l-hote-du-site-et-statut-404.md) | Routes de l'hôte du site : fichiers de découverte servis par Django, statut 404 | D74 (remplace le repli `try_files` et le point « routage » de 0008) | accepté |
| [0031](0031-chaque-verification-de-la-ci-a-un-seul-endroit.md) | Chaque vérification de la CI tourne à un seul endroit | D75 (remplace des points de 0014, 0017, 0019 et 0025) | accepté ; points « Une vérification tourne à un seul endroit », « Le push sur `main` livre », 1, 3 et 4 de § Décision, deux risques de § Conséquences et la re-mesure de § Conditions de réexamen remplacés par 0032 |
| [0032](0032-ci-parallele-et-rejouee-sur-main.md) | La CI d'un dépôt public : vérifications en parallèle, rejouées sur `main` | D78 (remplace des points de 0017, 0019 et 0031) | accepté |

## À écrire à leur phase

Le cadrage (annexe A) reporte ces décisions au moment où leur phase commence : service IA
(FastAPI + LangGraph), LangSmith, embeddings et reranking locaux, serveur MCP, authentification de
`send_message`.
