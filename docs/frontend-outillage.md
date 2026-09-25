# Frontend — outillage et plan d'installation

_2026-09-18, amendé le 2026-09-23 au scaffold de `apps/web` (#3), puis le 2026-09-25 (versions retirées de l'inventaire, refus de mises à jour majeures). Détaille D44 (cadrage §7), qui remplace D15. Le pourquoi, les options écartées et les points tranchés sont dans l'ADR 0008 (`docs/adr/`) ; ce document garde l'inventaire installé et le plan d'installation._

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
2026-09-23, amendée le 2026-09-25 (§2.4). C'est cette section qui fait foi sur ce qui est installé
et pourquoi ; les versions de `apps/web` se lisent dans son manifeste et son verrou (§2.4). Le §3
reste le plan, avec l'état de chaque item.

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

### 2.4 Application `apps/web` — 2026-09-23, amendée le 2026-09-25

Node **24.21.0**, LTS active du jour, épinglée par `.nvmrc` et par `engines` (valeurs égales,
vérifiées par un test). Paquets directs installés par `npm create vite@latest -- --template react-ts`,
puis émondés de ce que le gabarit ajoute pour sa page de démonstration. Leurs plages sont dans
`package.json`, leurs versions installées dans le verrou `package-lock.json` : le tableau n'en
recopie aucune, une copie datée devenant fausse à la première mise à jour de Dependabot. Seules les
contraintes de version délibérées sont écrites ici, chacune avec sa raison : Node ci-dessus ;
ESLint, TypeScript et les `overrides` du manifeste ci-dessous.

| Paquet | Rôle |
|---|---|
| `react`, `react-dom` | Interface en composants |
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

**Bloc d'aperçu de l'`index.html`.** Entre `<!--meta:start-->` et `<!--meta:end-->`, dans le
`<head>`. La CI copie l'`index.html` compilé dans l'image `api` ; sur `/projets/<slug>`, une vue
Django remplace **tout le bloc** par les balises du projet (#14, ADR 0008 « Aperçus de lien »). Les
deux marqueurs sont le contrat : ils doivent rester uniques dans le fichier **compilé**, ce qu'un
scénario de bout en bout vérifie sur la version servie et non sur la source. Trois points à savoir
avant de toucher au bloc :

- Les valeurs par défaut sont celles du site. Servies telles quelles à un robot d'aperçu, elles
  restent correctes — c'est le comportement attendu hors `/projets/<slug>` et pour un slug inconnu
  (ADR 0008 : « gabarit sans balises projet »).
- **`og:image` n'a pas de valeur par défaut.** Partout où la documentation le nomme, c'est la
  **couverture du projet** (spec §1.11 et §7, ADR 0008), et aucune image de site n'existe. #14
  l'injecte avec les autres ; une image d'ouverture propre au site relèverait de #18.
- Le bloc porte **quatre** balises, pas trois : `<meta name="description">` accompagne
  `og:description` et porte le même texte — un test verrouille leur égalité. Sans elle, le score
  SEO plafonne à 91, sous le seuil bloquant de la spec §1.16. #14 doit donc en produire quatre.

L'explication vit ici et non dans l'`index.html` : ce fichier est servi à chaque visite et recopié
dans l'image `api`, chaque ligne de commentaire y voyage sur le réseau.

**Lighthouse CI.** `lighthouserc.json` sert la version compilée depuis `staticDistDir` et assied les
quatre seuils de la spec §1.16. Trois points mesurés, non évidents :

- La porte est **`lhci autorun`, jamais `lhci assert` seul** : sans rapport collecté, `assert`
  annonce « 0 URL(s), 0 run(s), All results processed » et sort **0**. Une collecte cassée rendrait
  donc la porte verte sans avoir rien vérifié. `autorun` sort 1 dans le même cas.
- **La collecte ne tourne pas sous Windows** : `chrome-launcher` échoue sur `EPERM` en supprimant
  son dossier temporaire, que Chrome tient encore (reproduit trois fois, y compris avec `%TEMP%`
  déplacé). C'est donc une porte **de CI seulement** ; en local, `npx lighthouse <url>` écrit bien
  son rapport JSON avant le plantage de nettoyage, ce qui suffit à mesurer.
- Les scores de la page minimale, mesurés le 2026-09-23 (Lighthouse 12.6.1, profil mobile) :
  performance 100, accessibilité 100, bonnes pratiques 100, SEO 100. Deux correctifs ont été
  nécessaires pour y arriver : `public/robots.txt` (sans lui SEO plafonne à 91) et une icône
  déclarée `data:,` dans l'`index.html` (sans elle, le 404 sur `/favicon.ico` fait tomber l'audit
  « erreurs dans la console » et les bonnes pratiques à 96).

**`overrides` du manifeste — trois avis de sécurité écartés à la racine.** `@lhci/cli` 0.15.1
traînait 10 avis (`npm audit`, arbre complet), dont 7 `high`. Trois racines, trois issues
différentes :

| Racine | Résolution | Pourquoi |
|---|---|---|
| `tmp` (2 × high) | `^0.2.7` | Les versions tirées (0.0.33 via `external-editor`, 0.1.0 en direct) sont vulnérables ; 0.2.7 est corrigée et expose les deux seules API appelées, `tmpNameSync` et `fileSync` (vérifié) |
| `uuid` (moderate) | `^11.1.1` | `lhci` n'appelle que `uuid.v4()`, présent en CJS en v11 (vérifié) |
| `extract-zip` (2 × high, CVSS 8.1) | `@puppeteer/browsers` → `^3.2.3` | **Aucune version d'`extract-zip` n'est corrigée** : les avis portent sur `<= 2.0.1`, et 2.0.1 est la dernière publiée (2023-03-04, paquet abandonné). La sortie n'est pas de le corriger mais de cesser d'en dépendre : `@puppeteer/browsers` 3.x l'a remplacé par `modern-tar`. C'est la correction que portent aussi Puppeteer 25.7 et les projets qui ont rencontré le même mur |

Résultat mesuré : `npm audit` sur l'arbre **complet** rend `found 0 vulnerabilities`, et
`npm ls extract-zip` rend vide. La porte `make web-audit` porte donc sur tout l'arbre, sans
`--omit=dev` : une chaîne de build compromise sait écrire dans `dist/`, et l'exclure la rendrait
aveugle à ce risque-là.

Le saut de majeure `@puppeteer/browsers` 2 → 3 sous un `puppeteer-core` 24 est le vrai risque de
cette manœuvre. Il a donc été éprouvé en exécutant réellement l'outil, pas seulement l'audit :
Lighthouse 12.6.1 rend 100/100/100/100 sur la page, `lhci healthcheck` trouve Chrome, `lhci assert`
sort 0, et les six portes front sont vertes après un `npm ci` depuis un verrou régénéré de zéro.

**ESLint est épinglé sur la ligne 9** alors que la 10 est publiée : `eslint-plugin-jsx-a11y` 6.10.2,
sa dernière version, déclare `eslint@^3 || … || ^9`. Tourner sur la 10 demanderait de forcer un pair
non déclaré, sur le plugin même dont dépend l'accessibilité. Le script de lint porte
`--max-warnings 0` : sur les 114 règles actives, 3 sont en simple avertissement
(`react-hooks/exhaustive-deps`, `incompatible-library`, `unsupported-syntax`) et passeraient la
porte en silence sans lui — mesuré, `eslint .` sort 0 là où `--max-warnings 0` sort 1.

**TypeScript reste sur la 6.0** (`~6.0.2`) alors que la 7 est publiée : `typescript-eslint` 8.70.1,
sa dernière version, déclare `typescript >=4.8.4 <6.1.0`, et aucune 6.1 n'existe. Sur la 7, `npm ci`
échoue en `ERESOLVE` — mesuré sur la PR Dependabot #43.

**Ces deux épingles sont des refus datés, pas des oublis.** Dependabot ne propose plus les majeures
d'ESLint, d'`@eslint/js` — qui va par paire avec lui — et de TypeScript (`ignore` de
`.github/dependabot.yml`, 2026-09-25), jusqu'à ce que le plugin concerné publie son support.

La famille Manrope est déclarée **comme jeton de thème Tailwind** (`@theme { --font-sans }`) plutôt
que sur `:root` : la feuille de base de Tailwind pose déjà la police du document depuis ce jeton, et
deux déclarations se disputeraient la même propriété. Les jetons de couleur, d'espacement et de
rayon de la spec §2 viendront avec #18, au même endroit.

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
Les huit autres restent à faire, chacun avec l'issue qui le portera. Trois items se sont révélés
partiellement faux à l'exécution ; l'écart est consigné sous chacun d'eux et détaillé au §2.4.

1. **Projet** ✅ *fait (#3)* : `npm create vite@latest apps/web -- --template react-ts`, puis suppression de la page de démonstration du gabarit. TypeScript strict **posé explicitement** — contrairement à ce que cet item affirmait, `create-vite` 9.2.1 ne l'active plus (§2.4).
2. **Tailwind CSS v4** ✅ *fait (#3)* : `npm i -D tailwindcss @tailwindcss/vite`, plugin dans `vite.config.ts`, `@import "tailwindcss";` dans le CSS d'entrée. **Jamais** le script CDN `cdn.tailwindcss.com` (c'est lui qui affiche « ne pas utiliser en production »).
3. **Alias `@/`** — à faire avec #21 (requis par shadcn) : `paths` dans `tsconfig.json` et `tsconfig.app.json`, `resolve.alias` dans `vite.config.ts`, `npm i -D @types/node`.
4. **shadcn/ui** — à faire avec #21 : `npx shadcn@latest init`, puis `npx shadcn@latest add <composant>` au besoin (`dialog` pour la fiche projet en modal). Radix arrive comme dépendance de chaque composant ; rien à installer à part.
5. **motion** — hors phase 1 (PRD #1) : `npm i motion` ; import depuis `motion/react`.
6. **react-bits** — hors phase 1 (PRD #1) : composant par composant, `npx shadcn@latest add @react-bits/<Nom>-TS-TW`. **Licence MIT + Commons Clause** : usage libre, revente d'un produit fondé sur ces composants interdite — citée dans l'ADR 0008.
7. **bklit-ui** (graphiques) — hors phase 1 (PRD #1) : composant par composant, `npx shadcn@latest add @bklit/<graphique>` ; vérifier si le registre `@bklit` doit être déclaré dans `components.json`. Composants MIT ; Bklit Studio (outil hébergé) propriétaire.
8. **Rive** (animation 2D interactive) — hors phase 1 (PRD #1) : `npm i @rive-app/react-canvas`. Fichiers `.riv` servis en statique ; le runtime charge un WASM : mesurer son poids avec Lighthouse avant d'en généraliser l'usage. Éditeur Rive : compte gratuit à créer soi-même.
9. **Types de l'API** — à faire avec #19 : `npm i -D openapi-typescript`, génération depuis le schéma OpenAPI de django-ninja ; script npm + vérification en CI (types à jour).
10. **Accessibilité statique** ✅ *fait (#3)* : `npm i -D eslint-plugin-jsx-a11y`. La configuration ESLint a dû être **écrite**, non héritée : contrairement à ce que cet item affirmait, le gabarit Vite ne fournit plus ESLint mais `oxlint` (§2.4).
11. **E2E** ✅ *fait (#3)*, par `npm i -D @playwright/test` plutôt que par l'assistant `npm init playwright@latest`, qui écrit des exemples à supprimer derrière lui (§2.4) ; `npm i -D @axe-core/playwright` pour un contrôle d'accessibilité par page. Couvre le site en phase 1, le chat en phase 2 (§8.4).
12. **Lighthouse CI** ✅ *fait (#3)* : `@lhci/cli` dans GitHub Actions ; seuils sur performance, accessibilité, bonnes pratiques, SEO ; la PR échoue sous le seuil. Lighthouse = audit Google intégré à Chrome, notes sur 100 et indicateurs de vitesse ressentie.
13. **Tests unitaires** ✅ *fait (#3)* : `npm i -D vitest` ; logique pure du front (format des dates, ordre des cartes, technologies de carte) ; script npm + CI (ADR 0010).
14. **Markdown** — à faire avec la fiche projet : `npm i markdown-to-jsx` ; description et sections rendues en éléments React, HTML brut échappé, jamais d'insertion d'HTML (ADR 0010).

### Build et déploiement

- Build dans GitHub Actions ; `apps/web/dist` copié dans l'image Caddy publiée sur GHCR (D43) ; pas de conteneur `web` (cadrage §5.3).
- Caddy : `try_files {path} /index.html` pour les routes côté client ; en-têtes `Cache-Control: immutable` sur les fichiers hachés, `no-cache` sur `index.html`.

## 4. Comptes à créer (par l'auteur)

- **Rive** : éditeur, offre gratuite.
- **Manus** : agent IA autonome en ligne, à crédits. Sert aux maquettes jetables, moodboards et recherches ; son code ne part pas en production (D27).

## 5. Points ouverts

Tous tranchés le 2026-09-18 : l'ADR 0008 fixe les aperçus de lien (vue Django sur `/projets/<slug>`, `index.html` copié dans l'image `api`, Caddy route `/projets/*`), l'origine de l'API (`api.pacome.dev` + CORS restreint) et les tests unitaires du front (condition de réexamen atteinte : Vitest en phase 1, ADR 0010) ; `.claude/skills/design-system` (hérité d'un autre projet) recoupait `taste-skill` et a été retiré.
