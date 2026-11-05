# Frontend — outillage et plan d'installation

_2026-09-18, amendé le 2026-09-23 au scaffold de `apps/web` (#3), puis le 2026-09-25 (versions retirées de l'inventaire, refus de mises à jour majeures) et le 2026-09-26 (majeure de `@types/node` alignée sur Node). Détaille D44 (cadrage §7), qui remplace D15. Le pourquoi, les options écartées et les points tranchés sont dans l'ADR 0008 (`docs/adr/`) ; ce document garde l'inventaire installé et le plan d'installation._

## 1. Décision D44

**Vite + React + TypeScript + Tailwind CSS + shadcn/ui, compilé en CI, servi en statique par Caddy.**

| Brique | Rôle | Pourquoi ici |
|---|---|---|
| React | Librairie JavaScript d'interface en composants | Tout l'outillage retenu (shadcn, react-bits, bklit, motion, Rive) cible React |
| TypeScript | JavaScript typé, vérifié à la compilation | Pendant front de Python + pyright strict ; types générés depuis l'OpenAPI de django-ninja : l'API change → le front ne compile plus |
| Vite | Serveur de dev + compilation | Standard, rapide, sans configuration |
| Tailwind CSS | Style par classes utilitaires, compilé au build | Exigé par shadcn et bklit ; zéro code exécuté côté navigateur ou serveur |
| shadcn/ui | Composants accessibles (sur Radix) copiés dans le dépôt | On possède le code, on n'ajoute que ce qu'on utilise (D27) ; format de registre utilisé par react-bits et bklit |

**Rôle de Django** : API (django-ninja) et admin uniquement. L'admin garde son propre style ; Tailwind n'existe que dans `apps/web/`.

**Servi en statique** : `npm run build` produit `index.html` + JS + CSS ; Caddy les sert, le navigateur récupère le contenu via l'API.

- Pour : aucun Node en production, rien à patcher côté front sur le VPS, RAM quasi nulle, cache Cloudflare, modifier le contenu dans l'admin ne demande pas de rebuild.
- Contre : le HTML initial est vide. Les aperçus de lien (LinkedIn, Slack, Discord) n'exécutent pas le JS → titre et image génériques sur `/projets/<slug>`.
- Parade : une vue Django qui renvoie `index.html` avec les **cinq** balises du bloc marqué — `<title>`, `<meta name="description">`, `og:title`, `og:description`, `og:image` du projet. Mécanisme dans l'ADR 0008, liste des balises dans l'ADR 0011, forme du bloc au §2.4.
- Next.js écarté : serveur Node permanent (conteneur, RAM, surface d'attaque, second runtime à maintenir) contraire à P1 pour un site à deux visiteurs.

**Écarté à l'audit** : anime.js (doublon de motion), design-motion-principles (reconditionne Emil Kowalski), UX Engine / designmotionhq (payant, doublon), boneyard (sur-ingénierie), Spline (3D lourde — à rouvrir si un besoin 3D réel apparaît, avec three.js en alternative), watermelon-platform et motion-primitives (doublons de react-bits), dépôt 21st (inactif depuis mai 2025), ui-ux-pro-max-skill (taste-skill préféré).

## 2. Inventaire installé

Skills et outils en ligne de commande : 2026-09-18 (§2.1 à §2.3). Application `apps/web` :
2026-09-23, amendée les 2026-09-25, 26 et 2026-10-02 (§2.4). C'est cette section qui fait foi
sur ce qui est installé et pourquoi ; les versions de `apps/web` se lisent dans son manifeste et
son verrou (§2.4). Le §3 reste le plan, avec l'état de chaque item.

### 2.1 Skills Claude Code (`.claude/skills/`)

Copiées depuis GitHub, licence MIT jointe dans chaque dossier. Mise à jour : re-cloner le dépôt, recopier, rescanner (§2.3).

| Skill | Dépôt @ commit | Usage |
|---|---|---|
| `taste-skill` (`design-taste-frontend`) | Leonxlnx/taste-skill @ e79ca9e | Direction visuelle anti-générique ; molettes variance / mouvement / densité |
| `minimalist-skill` (`minimalist-ui`) | Leonxlnx/taste-skill @ e79ca9e | Variante sobre, éditoriale (Annexe B : « le plus sobre possible ») |
| `emil-design-eng` | emilkowalski/skills @ 85e8e23 | Principes design engineering d'Emil Kowalski |
| `prototype` | emilkowalski/skills @ 85e8e23 | Idée → plusieurs variantes d'UI comparables dans un sélecteur |
| `animate` | emilkowalski/skills @ 85e8e23 | Écrire une animation (courbes, durées, propriétés) |
| `review-animations` | emilkowalski/skills @ 85e8e23 | Relecture stricte d'animations |
| `improve-animations` | emilkowalski/skills @ 85e8e23 | Audit + plans d'amélioration, lecture seule |
| `find-animation-opportunities` | emilkowalski/skills @ 85e8e23 | Repérer où le mouvement apporte quelque chose |
| `animation-vocabulary` | emilkowalski/skills @ 85e8e23 | Vocabulaire précis pour décrire une animation |
| `no-ai-slop` | petergyang/no-ai-slop @ 000650b | Rédaction des fiches ; motifs écrits pour l'anglais, transfert partiel au français |
| `improve-codebase-architecture` | mattpocock/skills @ c55ee46 | Audit d'architecture (modules profonds), s'appuie sur les ADR |

Non retenues dans emilkowalski/skills : `animate-expo`, `write-swift`, `mobile-native` (natif), `ask-sonner` (librairie non choisie), `pick-ui-library` (choix fait), `apple-design`.
Non retenues dans taste-skill : variantes `soft`, `brutalist`, `redesign`, `output`, `gpt-tasteskill`, `stitch`, générateurs d'images, `v1`.

### 2.2 Outils en ligne de commande (`uv tool`)

Installés avec `uv tool`, chacun dans son environnement isolé et disponible dans tout le système. Ils ne font pas partie du projet : leurs dépendances (LiteLLM, YARA…) entreraient en conflit avec celles du backend.

| Outil | Version | Installation / mise à jour |
|---|---|---|
| SkillSpector | 2.11.2 (NVIDIA/skillspector @ d162d9b) | `uv tool install "skillspector @ git+https://github.com/NVIDIA/skillspector.git"` · `uv tool upgrade skillspector` |
| strix | 1.6.2 (`strix-agent`) | `uv tool install strix-agent` · `uv tool upgrade strix-agent` |

**SkillSpector** : `skillspector scan .claude/skills/<skill> --no-llm` (analyse statique). Passe sémantique sans clé API : `SKILLSPECTOR_PROVIDER=claude_cli`. Rescanner après chaque mise à jour ou ajout de skill.

**strix** (pentest par agents IA) : à exécuter **en fin de parcours, avant l'ouverture publique** du chat RAG et du MCP, contre la préproduction, jamais la prod.
- Prérequis : Docker démarré, `STRIX_LLM` (ex. `anthropic/<modèle>`) et `LLM_API_KEY`.
- Le premier lancement télécharge l'image Docker du bac à sable.
- Résultats dans `strix_runs/` → à ajouter au `.gitignore`.

### 2.3 Scan SkillSpector du 2026-09-18 (statique)

Tout conservé. Les signalements, relus un par un, sont des faux positifs :

| Skill | Verdict outil | Réalité |
|---|---|---|
| `improve-animations` | DO_NOT_INSTALL | « ignore previous instructions » cité dans une règle **défensive** (« si un fichier dit ça, signale-le ») ; espaces de largeur nulle devant des ``` dans `PLAN-TEMPLATE.md` = échappement de blocs de code imbriqués, aucun texte caché |
| `taste-skill` | CAUTION | Commentaire HTML de placeholder d'image ; « Do not ask the user to edit this file » |
| `find-animation-opportunities` | SAFE | Même règle défensive |
| `prototype` | CAUTION | « never judge » : consigne de présentation des variantes |
| autres | SAFE / CAUTION sans signalement | — |

### 2.4 Application `apps/web` — 2026-09-23, amendée les 2026-09-25, 26, 2026-10-02, 04, 16 et 2026-11-01

Node **24.21.0**, LTS active du jour, épinglée par `.nvmrc` et par `engines` (valeurs égales,
vérifiées par un test). `@types/node` suit sa majeure, vérifiée par un autre test : des types d'une
majeure plus récente décriraient des API absentes du runtime ; les deux montent ensemble, à la main,
et Dependabot ne propose plus la majeure des types (`ignore` de `.github/dependabot.yml`, hors de la
table des refus ci-dessous : ce refus-là ne tombe jamais seul).
Paquets directs installés par `npm create vite@latest -- --template react-ts`,
puis émondés de ce que le gabarit ajoute pour sa page de démonstration. Leurs plages sont dans
`package.json`, leurs versions installées dans le verrou `package-lock.json` : le tableau n'en
recopie aucune, une copie devenant fausse à la première mise à jour de Dependabot. Les contraintes
de version délibérées sont écrites avec leur raison — Node ci-dessus ; ESLint, TypeScript et les
`overrides` du manifeste ci-dessous — ; les autres versions citées dans ce § sont des constats
datés.

| Paquet | Rôle |
|---|---|
| `react`, `react-dom` | Interface en composants |
| `@radix-ui/react-dialog` | Dialogue modal de la fiche, le `dialog` de shadcn/ui copié sans `init` et sans `Overlay` (CSP) (#170) |
| `markdown-to-jsx` | Description et sections de la fiche rendues en éléments React, HTML brut en texte (ADR 0010) (#170) |
| `typescript` | Types vérifiés à la compilation, mode strict — **6.0, pas 7** (voir ci-dessous) |
| `vite` | Serveur de développement et compilation |
| `tailwindcss`, `@tailwindcss/vite` | Style utilitaire compilé au build, par le plugin Vite |
| `@vitejs/plugin-react` | Prise en charge de React par Vite |
| `vitest` | Tests unitaires (ADR 0010) |
| `eslint`, `@eslint/js` | Analyse statique — **ligne 9, pas 10** (voir ci-dessous) |
| `typescript-eslint` | Règles TypeScript pour ESLint |
| `eslint-plugin-jsx-a11y` | Accessibilité statique du JSX (ADR 0008) |
| `eslint-plugin-react-hooks` | Règles des hooks React |
| `@lhci/cli` | Lighthouse CI, seuils bloquants de la spec §1.16 |
| `@playwright/test` | Scénarios de bout en bout, Chromium seul |
| `@axe-core/playwright` | Contrôle d'accessibilité par page |
| `@types/node`, `@types/react`, `@types/react-dom` | Types ambiants |
| `semver`, `@types/semver` | Lecture des plages npm, qui fait expirer les refus (voir ci-dessous) |
| `openapi-typescript` | Types de l'API générés depuis `apps/api/openapi.json` (ADR 0008) — **pair `typescript` forcé** (voir ci-dessous) |

**Bloc d'aperçu de l'`index.html`.** Entre `<!--meta:start-->` et `<!--meta:end-->`, dans le
`<head>`. La CI copie l'`index.html` compilé dans l'image `api` ; sur `/projets/<slug>`, une vue
Django remplace **tout le bloc** par les balises du projet (#14, ADR 0008 « Aperçus de lien »). Les
deux marqueurs sont le contrat : ils doivent rester uniques dans le fichier **compilé**, ce qu'un
scénario de bout en bout vérifie sur la version servie et non sur la source. Trois points à savoir
avant de toucher au bloc :

- Les valeurs par défaut sont celles du site. Servies telles quelles à un robot d'aperçu, elles
  restent correctes — c'est le comportement attendu hors `/projets/<slug>`. Une adresse de
  `/projets/*` sans projet publié ne sert pas le gabarit : elle redirige en `302` vers `/`
  (ADR 0009, D50).
- **`og:image` n'a pas de valeur par défaut.** Partout où la documentation le nomme, c'est la
  **couverture du projet** (spec §1.11 et §7, ADR 0008), et aucune image de site n'existe. #14
  l'injecte avec les autres ; une image d'ouverture propre au site n'existe pas en phase 1 (PRD #1,
  « Hors périmètre »).
- Le bloc porte **quatre** balises, pas trois : `<meta name="description">` accompagne
  `og:description` et porte le même texte — un test verrouille leur égalité. Sans elle, le score
  SEO plafonne à 91, sous le seuil bloquant de la spec §1.16. #14 doit donc en produire quatre.

L'explication vit ici et non dans l'`index.html` : ce fichier est servi à chaque visite et recopié
dans l'image `api`, chaque ligne de commentaire y voyage sur le réseau.

**Lighthouse CI.** `lighthouserc.json` mesure la table à douze cartes et assied les quatre seuils de
la spec §1.16. Sa collecte démarre `e2e/lighthouse-server.ts` (`collect.startServerCommand`) et lit
son adresse (`collect.url`) : un serveur rangé avec les tests, lancé par Node sans outil de plus, qui
sert le `dist` réel, repli SPA compris, la liste de `PROJECT_SETS.twelveWithShowcase` et de vrais
WebP, le tout sur son origine. `dist` portant `VITE_API_URL` en dur, il remplace cette origine par
la sienne dans le JS servi, sans second build : l'artefact mesuré reste celui de la production.
Quatre points mesurés, non évidents :

- La porte est **`lhci autorun`, jamais `lhci assert` seul** : sans rapport collecté, `assert`
  annonce « 0 URL(s), 0 run(s), All results processed » et sort **0**. Une collecte cassée rendrait
  donc la porte verte sans avoir rien vérifié. `autorun` sort 1 dans le même cas.
- **Les seuils ne prouvent pas que la table a été mesurée** : l'écran d'erreur rend 99, 100, 100,
  100, et `lhci` n'a aucune assertion de minimum — il ne lit que `minScore`, `maxLength` et
  `maxNumericValue`, et ignore `minNumericValue` en silence (`@lhci/utils`, `assertions.js`). C'est
  `e2e/lighthouse-server.spec.ts`, joué par `make web-e2e`, qui prouve que ce serveur rend les douze
  cartes et toutes leurs images, couvertures et icônes ; ses quatre routes (`dist`, API, images,
  icônes), mutées une à une, y rougissent.
- **La collecte ne tourne pas sous Windows** : `chrome-launcher` échoue sur `EPERM` en supprimant
  son dossier temporaire, que Chrome tient encore (reproduit trois fois, y compris avec `%TEMP%`
  déplacé). C'est donc une porte **de CI seulement** ; en local, `node e2e/lighthouse-server.ts`,
  puis `npx lighthouse <url>` écrit bien son rapport JSON avant le plantage de nettoyage, ce qui
  suffit à mesurer. `lhci collect` y démarre le serveur et lance Lighthouse jusqu'à ce même plantage.
- Les scores, profil mobile, Lighthouse 12.6.1. La page minimale, mesurée le 2026-09-23 :
  performance 100, accessibilité 100, bonnes pratiques 100, SEO 100. Deux correctifs ont été
  nécessaires pour y arriver : `public/robots.txt` (sans lui SEO plafonne à 91) et une icône
  déclarée `data:,` dans l'`index.html` (sans elle, le 404 sur `/favicon.ico` fait tomber l'audit
  « erreurs dans la console » et les bonnes pratiques à 96). La table à douze cartes, mesurée le
  2026-11-01 sur quinze runs avec les images d'essai de 3 et 7 Ko : performance 98, accessibilité
  100, bonnes pratiques 100, SEO 100, LCP de 1,8 à 2 s. L'audit `font-size` passe : les résumés
  masqués comptent comme texte lisible et les rubans de 11 px (spec §2.2) n'en sont plus que
  7,38 % ; sans résumés, ils remontent à 48 % et les bonnes pratiques retombent à 96. Le LCP porte
  sur le `<h1>` de l'entête, 13 runs sur 15, et sur une couverture pour les 2 autres : `.card-entry`,
  à opacité 0, écarte les couvertures, et celle de la vitrine le reprend 8 runs sur 8 une fois cette
  opacité retirée de `dist`. Le chiffre reste sensible à leur poids : la simulation coupe son
  graphe à l'instant observé du LCP, pas à son élément, et les images reçues avant lui y pèsent
  (Lantern, `LargestContentfulPaint.js`). Avec des WebP de bruit de 92 et 351 Ko, le `<h1>` tient
  12 runs sur 12, mais performance 95 et LCP de 2,6 s sur les 11 où les images arrivent avant lui,
  98 et 2,1 s sur l'autre. Avant l'entrée des cartes, le 2026-10-31, le LCP portait sur la
  couverture de la vitrine en `loading="lazy"` : performance 98 à 99 et LCP de l'ordre de 2 s avec
  les images d'essai, 95 à 96 et de l'ordre de 2,6 s avec des WebP de bruit de 90 et 357 Ko.

**`overrides` du manifeste — cinq avis de sécurité écartés à la racine.** `@lhci/cli` 0.15.1
traînait 10 avis (`npm audit`, arbre complet), dont 7 `high`, sur trois racines (2026-09-25). Un
avis publié le 2026-10-01 en a ajouté une quatrième, `basic-ftp`, que l'audit compte 9 fois en
`high` — le paquet et les huit qui le tirent (#64). L'audit du 2026-10-25 en a ajouté une
cinquième, `zod`, comptée 6 fois en `high` — le paquet et les cinq qui le tirent jusqu'à
`@lhci/cli` (#156). Cinq racines, cinq issues différentes :

| Racine | Résolution | Pourquoi |
|---|---|---|
| `tmp` (2 × high) | `^0.2.7` | Les versions tirées (0.0.33 via `external-editor`, 0.1.0 en direct) sont vulnérables ; 0.2.7 est corrigée et expose les deux seules API appelées, `tmpNameSync` et `fileSync` (vérifié) |
| `uuid` (moderate) | `^11.1.1` | `lhci` n'appelle que `uuid.v4()`, présent en CJS en v11 (vérifié) |
| `extract-zip` (2 × high, CVSS 8.1) | `@puppeteer/browsers` → `^3.2.3` | **Aucune version d'`extract-zip` n'est corrigée** : les avis portent sur `<= 2.0.1`, et 2.0.1 est la dernière publiée (2023-03-04, paquet abandonné). La sortie n'est pas de le corriger mais de cesser d'en dépendre : `@puppeteer/browsers` 3.x l'a remplacé par `modern-tar`. C'est la correction que portent aussi Puppeteer 25.7 et les projets qui ont rencontré le même mur |
| `zod` (high, GHSA-mrhx-c7xc-m3w5) | `chromium-bidi` → `zod` `^4.6.6` | Seule la 4.6.6 est corrigée, et `chromium-bidi` 14, que fige `puppeteer-core` 24.43.1 sous Lighthouse 12.6.1, demande `zod ^3.24.1` ; ses versions suivantes passent à `zod ^4` (158.0.8124-0 demande `^4.6.5`). Saut de majeure sans risque à l'exécution : `chromium-bidi` ne sert qu'au protocole WebDriver BiDi, que `puppeteer-core` charge paresseusement (`BrowserLauncher.js`, `BrowserConnector.js`), et Lighthouse se connecte en CDP (`puppeteer.connect({browserURL})`) — importer `lighthouse` puis `puppeteer-core` ne résout aucun module de `chromium-bidi` ni de `zod`, et le témoin qui importe `bidi.js` en résout 73 (mesuré le 2026-10-25, hook `registerHooks` de Node). La résolution se retire quand la chaîne de Lighthouse atteint un `chromium-bidi` qui demande la 4 — un test rougit ce jour-là (`tests/dependency-refusals.test.ts`) |
| `basic-ftp` (high, GHSA-c475-qrg2-pj4r) | `^6.2.1` | Seule la 6.2.1 est corrigée, et aucun parent n'a cessé d'en dépendre : `get-uri` demande `basic-ftp ^5.3.1` jusqu'à sa dernière version (8.0.1 au 2026-10-02), et `@lhci/cli` fige sa chaîne sur `get-uri` 6 (`proxy-agent` 6 → `pac-proxy-agent` 7). La correction amont prend la même voie (TooTallNate/proxy-agents#500, ouverte au 2026-10-02) ; la résolution se retire quand la chaîne de `@lhci/cli` atteint un `get-uri` qui demande la 6.2.1 |

Résultat mesuré : `npm audit` sur l'arbre **complet** rend `found 0 vulnerabilities`,
`npm ls extract-zip` rend vide et `npm ls basic-ftp` ne rend que la 6.2.1. La porte
`make web-audit` porte donc sur tout l'arbre, sans `--omit=dev` : une chaîne de build compromise
sait écrire dans `dist/`, et l'exclure la rendrait aveugle à ce risque-là.

Le saut de majeure `@puppeteer/browsers` 2 → 3 sous un `puppeteer-core` 24 est le vrai risque de
cette manœuvre. Il a donc été éprouvé en exécutant réellement l'outil, pas seulement l'audit :
Lighthouse 12.6.1 rend 100/100/100/100 sur la page, `lhci healthcheck` trouve Chrome, `lhci assert`
sort 0, et les six portes front sont vertes après un `npm ci` depuis un verrou régénéré de zéro.

Même exigence pour `basic-ftp` 5 → 6 sous `get-uri` 6.0.5 (2026-10-02). La 6.0.0 déclare une
seule rupture : un serveur sans `EPSV` dont la réponse `PASV` désigne un autre hôte que celui de la
connexion de contrôle est refusé — derrière un NAT compris, que la 5.x contournait —, et `get-uri`
ne permet pas de le réautoriser. Le module `ftp` de `get-uri` a été exécuté contre un serveur FTP
factice local, sur la 5.3.1 puis sur la 6.2.1, avec les mêmes résultats sur ses quatre chemins : la
date lue par `MDTM` ou, à défaut, par `MLSD` donne le fichier ; le repli sur `LIST`, qui passe par
le parseur Unix que vise l'avis, ne donne pas de date et rend « introuvable », comme un fichier
absent (550). Le verrou n'a changé que sur l'entrée `basic-ftp`, et les portes front sont vertes
après `npm ci` ; Lighthouse CI, qui ne tourne pas sous Windows, se prouve par le job `web` de la
PR #65.

**ESLint est épinglé sur la ligne 9** alors que la 10 est publiée : `eslint-plugin-jsx-a11y` déclare
`eslint@^3 || … || ^9` (6.10.2, sa dernière version au 2026-09-25). Tourner sur la 10 demanderait de
forcer un pair non déclaré, sur le plugin même dont dépend l'accessibilité. `@eslint/js` va par
paire avec ESLint et reste sur la 9 avec lui : seule, sa 10 passe `npm ci` (PR Dependabot #42), mais
elle déclare `eslint ^10` en pair optionnel, et `npm install` échoue alors en `ERESOLVE`. Le script
de lint porte `--max-warnings 0` : sur les 114 règles actives, 3 sont en simple avertissement
(`react-hooks/exhaustive-deps`, `incompatible-library`, `unsupported-syntax`) et passeraient la
porte en silence sans lui — mesuré, `eslint .` sort 0 là où `--max-warnings 0` sort 1.

**TypeScript reste sur la 6.0** (plage en tilde du manifeste) alors que la 7 est publiée :
`typescript-eslint` déclare `typescript >=4.8.4 <6.1.0` (8.70.1, sa dernière version au 2026-09-25,
quand aucune 6.1 n'était publiée). Sur la 7, `npm ci` échoue en `ERESOLVE` — mesuré sur la PR
Dependabot #43.

**Ces épingles sont des refus datés, pas des oublis.** Dependabot ne propose plus ces majeures
(`ignore` de `.github/dependabot.yml`, 2026-09-25) tant que le plugin concerné ne les déclare pas —
pour les mises à jour de version seulement : une mise à jour de sécurité passe outre un
`update-types`. Le refus expire sans qu'on y pense. `dependency-refusals.json` en tient la liste —
plugin, pair, majeure, paquets refusés —, que `test_supply_chain.py` exige identique aux `ignore`
qu'elle fonde (celui de `@types/node`, hors table, vient après eux) ;
et `tests/dependency-refusals.test.ts` lit dans le verrou la plage de pairs de chaque plugin, avec
`semver` — la bibliothèque par laquelle npm lui-même résout les plages —, et rougit le jour où elle
accepte la majeure refusée. Le verrou ne bougeant que par une PR, le rouge apparaît dans celle qui
apporte la nouvelle version du plugin — le plus souvent la PR groupée de Dependabot, qu'il bloque.
On lève alors le refus en entier, table et règles ensemble, dans une PR à part, puis
`@dependabot rebase` sur la PR bloquée. Avant de lever, vérifier que la dernière majeure publiée
est acceptée elle aussi : sinon, monter à la main sur la majeure acceptée et reporter le refus sur
la suivante, table comprise.

**`openapi-typescript` tourne sous TypeScript 6 par un pair forcé** (#19, 2026-10-16) : sa dernière
version, la 7.13.0 (publiée le 2026-06-15), déclare `typescript ^5.x`, et `npm install` échoue en
`ERESOLVE` sans rien d'autre — l'ajout de la 6 est demandé en amont depuis le 2026-03-27
(openapi-ts/openapi-typescript#2723). L'`overrides` du manifeste,
`"openapi-typescript": { "typescript": "$typescript" }`, lui donne la version installée à la racine.
C'est l'inverse des refus ci-dessus, et il ne se paie pas de la même façon : ESLint et TypeScript
sont refusés pour ne pas forcer un pair non déclaré sous un plugin dont dépend une porte, alors
qu'ici l'outil n'écrit qu'un fichier, relu par `tsc` et par le test de fraîcheur des types — une
rupture serait bruyante, jamais silencieuse. Mesuré avant l'installation, Node 24.3.0 : `npm ci`
depuis le verrou dans un dossier neuf, génération des neuf schémas, sonde `tsc --strict` sur
`ProjectOut`. Rien dans la table des refus ni dans `.github/dependabot.yml` : rien n'est refusé, la
majeure suivante du générateur arrive en PR comme les autres ; si une version du générateur, ou de
`typescript` dont il emprunte l'imprimeur, imprime le module autrement, le test de fraîcheur des types rougit dans sa PR, et `make web-openapi` s'y lance comme
après un changement du contrat. L'override expire comme un refus —
`tests/dependency-refusals.test.ts` lit dans le verrou la plage de pair d'`openapi-typescript` et
rougit le jour où elle accepte la majeure installée : on retire alors l'override.

**L'origine de l'API vient des fichiers de mode de Vite** (#19, décision 4) : `VITE_API_URL` vaut
`http://127.0.0.1:8000` dans `.env.development` — le back de `make dev`, qui admet le serveur de
développement en CORS — et `https://api.pacome.dev` dans `.env.production`, l'origine que fixe
l'ADR 0008. Les deux sont committés : ils ne portent aucun secret, et le `.gitignore` n'exclut que
`.env`. Pas de valeur par défaut dans le code : `vite.config.ts` refuse de compiler sans la
variable. **Invariant de déploiement** : la CSP de Caddy n'admet que `https://{$API_HOST}` en
`connect-src` (`infra/caddy/Caddyfile`), donc `API_HOST` du VPS vaut l'hôte de
`.env.production` — sinon le navigateur bloque l'appel, et le site montre l'état erreur.

La famille Manrope est déclarée **comme jeton de thème Tailwind** (`@theme { --font-sans }`) plutôt
que sur `:root` : la feuille de base de Tailwind pose déjà la police du document depuis ce jeton, et
deux déclarations se disputeraient la même propriété.

**Les jetons de la spec §2** vivent dans `src/tokens.css` : les 38, sur `:root`, sous leur nom de
spec et hors de toute couche — pas dans `@theme`, qui n'émet que les variables utilisées. Six sont
les durées fixes de §2.7, nommées par #19 et #22 pour que la règle des valeurs n'admette aucun
littéral de durée hors de ce fichier. Cinq autres tombent dans un espace de noms de Tailwind (`--shadow-*` :
`--shadow-rest`, `--shadow-lift` ; `--ease-*` : les trois courbes) ; déclarés hors de `@theme`, ils
ne produisent aucun utilitaire nommé. Les composants les lisent par la syntaxe `(--jeton)` de Tailwind 4 :
`bg-(--paper)`, `ease-(--ease-out)`.

Tailwind, lui, perd ses couleurs, ses ombres, ses animations et ses courbes : `--color-*`,
`--shadow-*`, `--inset-shadow-*`, `--drop-shadow-*`, `--text-shadow-*`, `--animate-*` et
`--ease-*` valent `initial` dans le `@theme` d'`index.css` — les seuls espaces de noms de son
thème qui portent une couleur, une durée ou une courbe. Sans cela, il émettait son propre
`--ease-out`, `cubic-bezier(0, 0, .2, 1)`, dès qu'une classe `ease-out` apparaissait dans les
sources, et `bg-red-500`, `shadow-lg` ou `animate-spin` apportaient des valeurs étrangères à la
spec — mesuré, Tailwind 4.3.3, 2026-10-04. Sa transition par défaut (`transition-colors` sans
durée ni courbe) lit `--dur-fast` et `--ease-out`. Reste une couleur que porte un utilitaire et non
le thème : le `#fff` par défaut de `ring-offset-*`, seule couleur visible parmi les 8 568 classes
de Tailwind une fois ces remises à zéro faites (mesuré) — un décalage d'anneau prend donc toujours
sa couleur. C'est l'une des trois portes de la règle des valeurs (CONTRIBUTING.md, « Valeurs du
front ») ; les deux autres, ESLint et le balayage des feuilles CSS, lisent les motifs de
`forbidden-values.json`.

Ses points de rupture aussi : `--breakpoint-*` vaut `initial`, et `--breakpoint-sm` 600 px — le
seul point de rupture de la spec (§6.1), au lieu des 640 px de Tailwind. `md:` ou `lg:` ne
produisent plus rien ; le scénario de l'entête à 599 et 600 px de large prouve la valeur.

La palette sombre ne vit dans aucun sélecteur : chaque couleur porte ses deux valeurs dans
`light-dark()`, et `color-scheme` choisit — `light dark` par défaut, le mode de `data-theme` quand
il est forcé. La minification de Vite 8.3 (Lightning CSS, cible « baseline widely available »)
réécrit `light-dark()` en une bascule de variables `--lightningcss-light` / `--lightningcss-dark`,
posée sur `:root` par `prefers-color-scheme` et par les deux règles `data-theme`. Même comportement
tant que seul `:root` porte `color-scheme` : un `color-scheme` local ne rebascule pas les jetons
dans le build, alors qu'il le fait en développement, où `light-dark()` reste natif (mesuré à la
première relecture de #18) ; aucun composant ne branche sur le mode, les jetons portent la palette.
La valeur brute d'un jeton lue depuis le JavaScript diffère aussi — `light-dark(…)` en
développement, la couleur résolue dans le build : l'appliquer à une propriété et lire sa valeur
calculée, comme le fait `e2e/tokens.spec.ts`.

**Restauration du mode forcé** : `public/theme.js`, copié tel quel par Vite, chargé dans le
`<head>` par `<script src="/theme.js">`, hors du bloc d'aperçu. Script classique — sans
`type="module"`, `async` ni `defer` : un module est différé après l'analyse du document, donc le
premier rendu pourrait le précéder ; un script classique retient l'analyse et le rendu jusqu'à ce
que `data-theme` soit posé. Il ne retient que `light` ou `dark` sous la clé `theme`, et se tait
quand le stockage est refusé. Chemin absolu : la même page est servie sous `/projets/<slug>`. Le
prix, accepté par le brief de #18 (décision 4) : une requête bloquante de plus par visite, et un
nom sans empreinte, que Caddy sert `no-cache` comme `index.html`. `tsc` ne le lit pas ; le lint le
lit en script classique — un test le vérifie — et `e2e/tokens.spec.ts` l'exécute, application
bloquée.

**Police** : `src/assets/fonts/manrope-latin.woff2` — Manrope variable 200–800, sous-ensemble latin,
Google Fonts v20, 24,3 Ko, sous SIL Open Font License 1.1. L'OFL veut que la notice **et** le texte
de la licence accompagnent la police partout où elle est distribuée : la notice voyage en
commentaire légal dans le CSS compilé, et le texte intégral est servi depuis `public/OFL.txt`, donc
présent dans `dist/`. Un scénario de bout en bout le vérifie sur ce qui est réellement servi —
le premier jet renvoyait au chemin du dépôt, que personne recevant la distribution ne possède. C'est le
fichier exact sur lequel la spec §2.2 a mesuré ses 25 Ko : repris des prototypes plutôt que
réinstallé, pour que la valeur épinglée par la spec reste vraie. Aucune dépendance npm de police.

Deux projets Playwright : `desktop` (descripteur « Desktop Chrome », 1280 px) et `mobile`
(descripteur « Pixel 5 », largeur ramenée à 400 px, émulation tactile conservée). Ils s'exécutent
contre la **version compilée servie en statique**, celle que Caddy publie.

**Trois errata au plan du §3**, relevés en installant — le gabarit a changé depuis le 2026-09-18 :

- item 1, « TypeScript strict (déjà actif dans le modèle) » : **faux depuis `create-vite` 9.2.1**,
  qui ne pose plus `strict`. L'option est désormais posée explicitement dans
  `apps/web/tsconfig.base.json`, et un test la mesure sur **toutes** les configurations du projet —
  liste dérivée des `references` de `tsconfig.json`, pour qu'une configuration ajoutée demain ne
  puisse pas s'y soustraire.
- item 11, « `npm init playwright@latest` » : l'assistant écrit des scénarios d'exemple, un
  `.gitignore` et une configuration à moitié commentée, tous à supprimer derrière lui. Remplacé
  par `npm i -D @playwright/test @axe-core/playwright` puis `npx playwright install chromium`, et
  une configuration écrite à la main — même résultat, sans le ménage.
- item 10, « la config ESLint fournie par le modèle Vite » : **le gabarit ne fournit plus ESLint**,
  il fournit `oxlint`. La décision de l'ADR 0008 (ESLint + `eslint-plugin-jsx-a11y`) est inchangée
  et tient toujours ; c'est la provenance de la configuration qui change — elle sera écrite, pas
  héritée. `oxlint` a été retiré du projet : deux linters pour une seule règle d'accessibilité
  seraient un doublon.

## 3. À installer à l'initialisation de `apps/web/`

Ordre à suivre. Vérifier les commandes contre la doc officielle du jour (les CLI évoluent).

**État au 2026-09-23 (#3)** : les items **1, 2, 10, 11, 12 et 13 sont faits** — inventaire au
§2.4, qui fait foi sur ce qui est installé ; versions dans le verrou `apps/web/package-lock.json`.
L'item **9** l'est depuis le 2026-10-16 (#19), les items **3**, **4** et **14** sont tranchés depuis
le 2026-11-01 (#170). Les quatre autres restent à faire, chacun avec l'issue qui le portera. Trois
items se sont révélés partiellement faux à l'exécution ; l'écart est consigné sous chacun d'eux et détaillé au §2.4.

1. **Projet** ✅ *fait (#3)* : `npm create vite@latest apps/web -- --template react-ts`, puis suppression de la page de démonstration du gabarit. TypeScript strict **posé explicitement** — contrairement à ce que cet item affirmait, `create-vite` 9.2.1 ne l'active plus (§2.4).
2. **Tailwind CSS v4** ✅ *fait (#3)* : `npm i -D tailwindcss @tailwindcss/vite`, plugin dans `vite.config.ts`, `@import "tailwindcss";` dans le CSS d'entrée. **Jamais** le script CDN `cdn.tailwindcss.com` (c'est lui qui affiche « ne pas utiliser en production »).
3. **Alias `@/`** — sans objet (#170, décision du 2026-10-27) : le `dialog` copié n'en a pas besoin.
4. **shadcn/ui** ✅ *fait autrement (#170)* : `dialog` copié sans `init`, décision du 2026-10-27 — aucune palette, aucun `tw-animate-css`, seule dépendance `@radix-ui/react-dialog` ; classes passées aux jetons, sans `Overlay` (CSP).
5. **motion** — hors phase 1 (PRD #1) : `npm i motion` ; import depuis `motion/react`.
6. **react-bits** — hors phase 1 (PRD #1) : composant par composant, `npx shadcn@latest add @react-bits/<Nom>-TS-TW`. **Licence MIT + Commons Clause** : usage libre, revente d'un produit fondé sur ces composants interdite — citée dans l'ADR 0008.
7. **bklit-ui** (graphiques) — hors phase 1 (PRD #1) : composant par composant, `npx shadcn@latest add @bklit/<graphique>` ; vérifier si le registre `@bklit` doit être déclaré dans `components.json`. Composants MIT ; Bklit Studio (outil hébergé) propriétaire.
8. **Rive** (animation 2D interactive) — hors phase 1 (PRD #1) : `npm i @rive-app/react-canvas`. Fichiers `.riv` servis en statique ; le runtime charge un WASM : mesurer son poids avec Lighthouse avant d'en généraliser l'usage. Éditeur Rive : compte gratuit à créer soi-même.
9. **Types de l'API** ✅ *fait (#19)* : `npm i -D openapi-typescript`, sous TypeScript 6 par un pair forcé (§2.4) ; `scripts/api-types.ts` génère `src/api/schema.ts` depuis le schéma OpenAPI de django-ninja, par `make web-openapi` ; la vérification en CI est un test de la suite (`tests/api-types.test.ts`), que `make web-test` lance.
10. **Accessibilité statique** ✅ *fait (#3)* : `npm i -D eslint-plugin-jsx-a11y`. La configuration ESLint a dû être **écrite**, non héritée : contrairement à ce que cet item affirmait, le gabarit Vite ne fournit plus ESLint mais `oxlint` (§2.4).
11. **E2E** ✅ *fait (#3)*, par `npm i -D @playwright/test` plutôt que par l'assistant `npm init playwright@latest`, qui écrit des exemples à supprimer derrière lui (§2.4) ; `npm i -D @axe-core/playwright` pour un contrôle d'accessibilité par page. Couvre le site en phase 1, le chat en phase 2 (§8.4).
12. **Lighthouse CI** ✅ *fait (#3)* : `@lhci/cli` dans GitHub Actions ; seuils sur performance, accessibilité, bonnes pratiques, SEO ; la PR échoue sous le seuil. Lighthouse = audit Google intégré à Chrome, notes sur 100 et indicateurs de vitesse ressentie.
13. **Tests unitaires** ✅ *fait (#3)* : `npm i -D vitest` ; logique pure du front (format des dates, ordre des cartes, technologies de carte) ; script npm + CI (ADR 0010).
14. **Markdown** ✅ *fait (#170)* : `npm i markdown-to-jsx`, importé depuis `markdown-to-jsx/react` avec `disableParsingRawHTML` ; description et sections rendues en éléments React, HTML brut en texte, jamais d'insertion d'HTML (ADR 0010).

### Build et déploiement

- Build dans GitHub Actions ; `apps/web/dist` copié dans l'image Caddy publiée sur GHCR (D43) ; pas de conteneur `web` (cadrage §5.3).
- Caddy : `try_files {path} /index.html` pour les routes côté client ; en-têtes `Cache-Control: immutable` sur les fichiers hachés, `no-cache` sur `index.html`.

## 4. Comptes à créer (par l'auteur)

- **Rive** : éditeur, offre gratuite.
- **Manus** : agent IA autonome en ligne, à crédits. Sert aux maquettes jetables, moodboards et recherches ; son code ne part pas en production (D27).

## 5. Points ouverts

Tous tranchés le 2026-09-18 : l'ADR 0008 fixe les aperçus de lien (vue Django sur `/projets/<slug>`, `index.html` copié dans l'image `api`, Caddy route `/projets/*`), l'origine de l'API (`api.pacome.dev` + CORS restreint) et les tests unitaires du front (condition de réexamen atteinte : Vitest en phase 1, ADR 0010) ; `.claude/skills/design-system` (hérité d'un autre projet) recoupait `taste-skill` et a été retiré.
