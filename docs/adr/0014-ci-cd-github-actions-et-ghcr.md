# 0014 — CI/CD : GitHub Actions et GHCR

- **Statut** : proposé
- **Date** : 2026-09-27
- **Décisions du cadrage** : D56 (`docs/cadrage-technique.md` §7) ; confirme D43 (GHCR) ; tranche la
  ligne « SBOM, Trivy » de l'annexe A ; décisions de l'interrogatoire de #15 (2026-09-26) et image
  de base de `api` décidée au briefing de sa PR (2026-09-27)

## Contexte

Le cadrage fixe le cap : les images sont construites en CI, publiées sur GHCR et tirées par le VPS,
jamais construites sur le serveur (D43, §5.3) ; le déploiement passe par SSH (§6.7, ADR 0002) ; les
images sont scannées par Trivy (§6.6, annexe A). Le §5.2 laissait cet ADR « à écrire ».

La CI (`.github/workflows/ci.yml`) a trois jobs parallèles, un par pile — `api`, `web`, `infra` — et
un jeton en lecture seule. Le job `infra` construit l'image `api` par `make build`, sans la scanner
ni la publier. Le front se compile dans `apps/web/dist`, que rien ne copie ; les fichiers statiques
de l'admin ne sont servis qu'en développement, par `runserver`. L'image `caddy` n'existe pas.

## Facteurs de décision

- Rien à payer dans l'offre du compte, GitHub Pro : 3 000 minutes d'Actions par mois ; pour les
  paquets, 2 Go de stockage et 10 Go de transfert par mois, le registre de conteneurs étant
  « currently free », avec un mois de préavis avant tout changement (docs GitHub « GitHub Actions
  billing » et « GitHub Packages billing », lues le 2026-09-27).
- Dépôt privé (D11) : les images le sont aussi.
- Chaîne d'approvisionnement (§6.6, #5) : tout ce qui s'exécute est épinglé par empreinte, et le
  jeton n'a que les droits de l'étape qui s'en sert.
- Une seule définition par geste, la même sur le poste et en CI : le `Makefile`.
- Aucune image publiée sans avoir été scannée ; aucun build sur le serveur.
- Mêmes images en développement et en production (ADR 0012).

## Options considérées

- **Registre** : GHCR ; Docker Hub ; registre auto-hébergé sur le VPS.
- **Déploiement** : par SSH (`docker compose pull && up`) ; par un agent sur le VPS qui tire toute
  nouvelle image (type Watchtower).
- **Publication** : un job `publish` dans `ci.yml` ; un second workflow déclenché par
  `workflow_run` ; depuis le job `infra`.
- **Front dans les images** : compilé une fois hors Docker, puis copié ; un étage Node par
  Dockerfile ; un Dockerfile unique à deux cibles.
- **Statiques de l'admin** : WhiteNoise dans l'image `api` ; Caddy, depuis un volume rempli au
  démarrage ; R2.
- **Politique de scan** : bloquer HIGH et CRITICAL, corrigeables ou non ; ne les bloquer que quand
  un correctif existe (`--ignore-unfixed`).
- **Exécution de Trivy** : son image officielle, lancée par `make scan` ; les actions
  `aquasecurity/setup-trivy` ou `aquasecurity/trivy-action`.

## Décision

**GitHub Actions construit, scanne et publie ; GHCR stocke ; un déploiement par SSH fait tirer les
images au VPS.**

- **Registre : GHCR** (D43). Images `ghcr.io/plecart/portfolio-api` et
  `ghcr.io/plecart/portfolio-caddy`, étiquetées par le SHA complet du commit et par `latest`.
  Privées : un paquet l'est à sa première publication, et celui que publie le jeton du workflow est
  relié au dépôt, dont il hérite les droits d'accès (docs GitHub « Working with the Container
  registry »). Le VPS tirera avec un jeton `read:packages` (#16).
- **Une image par dossier `infra/<service>/`** portant un `Dockerfile`, toutes construites par
  `make build` : ajouter un dossier suffit. Le nom des images se préfixe par une variable, pour que
  la CI publie sous le nom GHCR sans redéfinir la commande.
- **Front compilé une fois**, hors Docker, par `make web-build`. `apps/web/dist` entre dans le
  contexte de build par une exception du `.dockerignore` : `caddy` le sert (ADR 0008), `api` en
  garde `index.html` en `/app/web/index.html`, gabarit des aperçus de lien (ADR 0011, #14).
  `make build` et `make dev` le compilent s'il manque. Écartés : un étage Node par Dockerfile, qui
  compile deux fois ; un Dockerfile à deux cibles, qui casse la règle « un dossier par Dockerfile »
  que suit Dependabot.
- **Statiques de l'admin : WhiteNoise dans l'image `api`**, collectés au build (`collectstatic`, sur
  des valeurs factices : aucun vrai secret n'entre dans le build) et servis compressés, avec un
  manifeste (`CompressedManifestStaticFilesStorage`) ; en développement,
  `whitenoise.runserver_nostatic` les sert à la place de `runserver`. Écartés : Caddy depuis un
  volume, qui n'existerait qu'en production (ADR 0012) ; R2, que l'ADR 0004 réserve aux médias et
  aux documents.
- **Images de base** épinglées étiquette `x.y.z` et empreinte, `FROM` lisible par Dependabot (#5).
  `api` repose sur Debian 13 (`python:3.12.x-slim-trixie`) : Debian 12 est sorti du support de
  sécurité régulier le 2026-06-11 (wiki Debian « LTS »), et au premier scan (2026-09-27) son image
  portait 21 vulnérabilités HIGH ou CRITICAL sans correctif, contre 8 HIGH pour l'image de base
  Debian 13.
- **Scan : Trivy**, sur chaque PR (job `infra`) et avant chaque publication : rouge sur toute
  vulnérabilité HIGH ou CRITICAL, corrigeable ou non, et sur un système d'exploitation en fin de vie
  (`--exit-on-eol 1`).
- **Une vulnérabilité sans correctif** arrête la CI le temps d'une évaluation en trois points : le
  composant a-t-il sa place dans l'image ; le code vulnérable est-il atteint par ce qui tourne ;
  quelles alternatives — autre image de base, retrait du paquet, correctif annoncé. L'évaluation se
  consigne en exception datée de `.trivyignore.yaml` : `id`, `statement` qui résume les trois
  points, `expired_at`. Le fichier est passé par `--ignorefile`, cette forme étant encore
  expérimentale chez Trivy. Passée la date, la vulnérabilité rebloque et l'évaluation se refait. Est
  sans correctif, pour l'image, une vulnérabilité corrigée en amont mais absente de toute version
  publiée de ce qui l'embarque — la bibliothèque standard Go du binaire `caddy`, par exemple.
- **Trivy tourne dans son image officielle**, `ghcr.io/aquasecurity/trivy`, épinglée étiquette et
  empreinte, lancée par `make scan` : même commande sur le poste et en CI, rien à installer.
  Dependabot ne lit pas cette épingle : elle se monte à la main, comme celle de Ryuk
  (`apps/api/tests/process_environment.py`) — nouvelle étiquette, signature vérifiée par cosign,
  empreinte relevée par `docker buildx imagetools inspect`. En mars 2026, les étiquettes des deux
  actions de Trivy ont été déplacées vers un voleur d'identifiants (GHSA-69fq-xp46-6x23) : seul un
  épinglage par empreinte en protégeait.
- **Empreinte d'une image de base** que Trivy bloque sans PR Dependabot (reconstruction d'une même
  étiquette, #5) : le mainteneur la monte à la main, par la même commande. Pas de job planifié.
- **Publication : un job `publish` dans `ci.yml`**, sur push vers `main` seulement, après `api`,
  `web` et `infra` ; seul job à recevoir `packages: write` ; une publication à la fois, la suivante
  attend la fin de la précédente ; il récupère `dist` du job `web` par artefact, reconstruit depuis
  le cache, scanne, pousse.
- **Rétention : trois versions par paquet**, les plus anciennes supprimées par `publish` après le
  push.
- **Ni attestation de provenance ni SBOM** au build : elles créent des versions sans étiquette qui
  fausseraient la rétention, et rien ne les consomme.
- **Déploiement par SSH** (§6.7, ADR 0002), porté par #16.

## Conséquences

**Positives**

- Une image publiée a passé toute la CI, puis un scan juste avant son push.
- Aucun secret à créer pour publier : le jeton du workflow suffit, et son droit d'écriture ne vit
  que dans `publish`.
- Le poste construit et scanne par les mêmes cibles que la CI.
- L'admin ne dépend d'aucun service pour ses statiques ; Caddy et R2 gardent chacun un seul rôle.

**Négatives, assumées**

- La politique de scan rougit toute PR dès qu'une nouvelle vulnérabilité HIGH ou CRITICAL touche une
  image de base, sans lien avec le contenu de la PR, jusqu'à son évaluation. Au premier scan : 8
  pour l'image de base de `api`, 16 pour `caddy` 2.11.4, sa dernière version (bibliothèque standard
  et modules Go corrigés en amont, absents de toute image `caddy` publiée).
- Le front se compile deux fois par run de PR, dans `web` et dans `infra`, pour que `infra`
  n'attende pas `web`.
- L'épingle de Trivy et les empreintes reconstruites se montent à la main.
- `index.html` existe dans deux images (ADR 0008, « Aperçus de lien »).
- Si GitHub facture un jour le registre de conteneurs, les quotas de l'offre Pro s'appliqueront :
  trois versions de deux images, quelques centaines de mégaoctets estimés, y tiennent.

## Comparaison des options

| Registre | GHCR | Docker Hub | Auto-hébergé |
|---|---|---|---|
| Coût | inclus dans l'offre Pro | un compte et une offre de plus | disque et exploitation du VPS |
| Accès depuis la CI | jeton du workflow | secret à créer et à renouveler | secret, registre exposé |
| Exploitation | aucune | aucune | TLS, sauvegarde, mises à jour |

| Déploiement | SSH | Agent sur le VPS |
|---|---|---|
| Moment du déploiement | choisi, migrations comprises | chaque image publiée, sans témoin |
| Sur le VPS | rien de plus | un processus et un jeton de registre |

| Publication | Job `publish` | `workflow_run` | Depuis `infra` |
|---|---|---|---|
| Ne publie qu'un commit vert | oui (`needs`) | oui | non : `infra` ignore les autres jobs |
| Artefact `dist` | du même run | d'un autre run | — |
| Workflow exécuté | celui du commit | celui de la branche par défaut | celui du commit |

| Scan | Sans correctif bloquant | `--ignore-unfixed` |
|---|---|---|
| Vulnérabilité sans correctif | évaluée, datée, réévaluée | ignorée sans trace |
| PR rougie par une image de base | oui, jusqu'à l'évaluation | non |

| Exécution de Trivy | Image officielle | `setup-trivy`, `trivy-action` |
|---|---|---|
| Même commande poste et CI | oui | non : installation locale à part |
| Épingles de version | une | deux, dans le workflow et sur le poste |
| Mise à jour | à la main | l'action par Dependabot, la version de Trivy à la main |

## Conditions de réexamen

- GitHub annonce la facturation du registre de conteneurs, ou le stockage approche le quota.
- Les exceptions de `.trivyignore.yaml` deviennent l'état ordinaire d'une image : changer son image
  de base plutôt que les renouveler.
- `caddy` publie durablement avec une bibliothèque Go en retard : le compiler dans un étage du
  projet.
- Un environnement de préproduction est décidé (annexe A, « Staging ») : un second déploiement.
- Dependabot sait suivre l'épingle de Trivy : la lui confier.
