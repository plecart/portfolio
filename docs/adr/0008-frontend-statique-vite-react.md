# 0008 — Frontend statique : Vite + React + TypeScript + Tailwind CSS + shadcn/ui

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D44 (`docs/cadrage-technique.md` §7) ; remplace D15

## Contexte

Le choix du frontend avait été reporté en tout dernier (D15), après le choix des skills et outils
de design. Cet audit a eu lieu le 2026-09-18 : tout l'outillage retenu (shadcn/ui, react-bits,
bklit-ui, motion, Rive) cible React. Il restait à fixer le framework, le mode de service et trois
points que le cadrage laissait ouverts : les aperçus de lien, l'origine de l'API, les tests
unitaires du front.

Contraintes : P1 simplicité, D27 code minimal, un ou deux visiteurs, contenu entièrement servi par
l'API Django (ADR 0001), et « aucun runtime Node en production » (cadrage §3).

## Facteurs de décision

- Aucun processus Node à exploiter sur le VPS : RAM, surface d'attaque, second runtime.
- Le contenu vit en base : le modifier dans l'admin ne doit pas déclencher de rebuild.
- Types du front dérivés de l'API : un changement d'API doit casser la compilation du front.
- Accessibilité et performance vérifiables en CI.
- Aperçus de lien corrects (LinkedIn, Slack, Discord) sur les fiches projets.

## Options considérées

1. **Vite + React + TypeScript + Tailwind CSS + shadcn/ui**, compilé en CI, servi en statique.
2. **Next.js** : React avec rendu côté serveur, serveur Node permanent.
3. **Flutter web** : technologie de la tentative précédente.
4. Astro ou SvelteKit, évoqués au cadrage v0, écartés dès que l'outillage retenu a fixé React.

## Décision

**Option 1.** Application dans `apps/web/`, version de Node fixée à l'initialisation.

| Brique | Rôle | Pourquoi ici |
|---|---|---|
| React | Librairie d'interface en composants | Tout l'outillage retenu cible React |
| TypeScript | JavaScript typé, vérifié à la compilation, mode strict | Pendant front de Python + pyright strict ; types générés depuis l'OpenAPI de `django-ninja` : l'API change → le front ne compile plus |
| Vite | Serveur de développement et compilation | Standard, rapide, sans configuration |
| Tailwind CSS v4 | Style par classes utilitaires, compilé au build | Exigé par shadcn/ui et bklit-ui ; zéro code exécuté côté navigateur ou serveur ; jamais le script CDN |
| shadcn/ui | Composants accessibles (Radix) copiés dans le dépôt | On possède le code, on n'ajoute que ce qu'on utilise (D27) ; format de registre partagé par react-bits et bklit-ui |

**Servi en statique** : `npm run build` produit `index.html` + JS + CSS dans `apps/web/dist`,
copié dans l'image Caddy publiée sur GHCR (D43) ; pas de conteneur `web`. Caddy sert les fichiers
(`try_files {path} /index.html` pour les routes côté client ; `Cache-Control: immutable` sur les
fichiers hachés, `no-cache` sur `index.html`) et le navigateur récupère le contenu via l'API.

**Rôle de Django** : API et admin uniquement. L'admin garde son propre style ; Tailwind n'existe
que dans `apps/web/`.

**Compléments** :

| Outil | Usage | Note |
|---|---|---|
| motion | Animations | Import depuis `motion/react` |
| react-bits | Composants animés, ajoutés un par un via le registre shadcn | **Licence MIT + Commons Clause** : usage libre, revente d'un produit fondé sur ces composants interdite. Compatible : le portfolio n'est pas vendu |
| bklit-ui | Graphiques, ajoutés un par un | Composants MIT ; Bklit Studio (outil hébergé) est propriétaire et n'est pas utilisé |
| Rive | Animation 2D interactive | Runtime WASM : mesurer son poids avec Lighthouse avant d'en généraliser l'usage |
| openapi-typescript | Types générés depuis le schéma OpenAPI de `django-ninja` | Vérification en CI que les types sont à jour |
| ESLint + `eslint-plugin-jsx-a11y` | Accessibilité statique | Config ESLint du modèle Vite |
| Playwright + `@axe-core/playwright` | E2E et contrôle d'accessibilité par page | Site en phase 1, chat en phase 2 |
| Lighthouse CI | Performance, accessibilité, bonnes pratiques, SEO | Seuils bloquants en CI |
| `npm audit` | Dépendances vulnérables | En CI, à côté de `pip-audit` |

Ordre d'installation et commandes : `docs/frontend-outillage.md` §3.

### Points ouverts tranchés

**Aperçus de lien.** Le HTML initial d'une application statique est vide ; les robots d'aperçu
(LinkedIn, Slack, Discord) n'exécutent pas le JavaScript et afficheraient titre et image
génériques sur `/projets/<slug>`. Parade : la CI copie `dist/index.html` dans l'image `api` comme
gabarit ; une vue Django sur `/projets/<slug>` injecte `<title>`, `og:title`, `og:description` et
`og:image` du projet à un emplacement marqué du gabarit et renvoie la page (slug inconnu : gabarit
sans balises projet, statut 404, et le front affiche sa page 404 personnalisée) ; Caddy route
`/projets/*` vers `api` et sert tout le reste en statique.
Un seul mécanisme pour tous les clients, robots comme humains. Coût : le build web précède le
build de l'image `api`, et `index.html` existe dans deux images. Écarté : détecter les robots par
`User-Agent` dans Caddy (liste à maintenir, rendu différent selon le client) ; rendre `index.html`
comme gabarit Caddy avec inclusion d'un fragment servi par Django (aucune duplication, mais une
fonctionnalité Caddy peu connue dans le chemin critique).

**Origine de l'API.** `api.pacome.dev`, conformément au cadrage §6.7 « Domaine » : Caddy route par
nom d'hôte ; l'admin vit sur le même hôte derrière Cloudflare Access (ADR 0003). CORS restreint à
l'origine du site (`django-cors-headers`) ; l'API publique est en lecture et sans cookie ; la CSP du
site n'autorise que cette origine en `connect-src`. La même origine via un préfixe `/api` aurait
évité CORS mais contredit les sous-domaines fixés par D36 et D37.

**Tests unitaires du front (Vitest).** Non en phase 1. Le front est un client mince (appel d'API et
rendu), couvert par Playwright + axe et par les types générés ; ajouter Vitest sans logique pure à
tester serait contraire à D27. Condition de réexamen : Vitest entre le jour où une logique pure
(formatage, filtrage, gestion d'état) mérite un test sans navigateur.

## Conséquences

**Positives**

- Aucun Node en production, rien à patcher côté front sur le VPS, RAM quasi nulle.
- Cache Cloudflare sur tous les fichiers ; modifier le contenu dans l'admin ne demande pas de
  rebuild.
- Composants possédés dans le dépôt, ajoutés un par un.
- Types du front couplés à l'API par la compilation.

**Négatives, assumées**

- HTML initial vide : traité par la vue d'aperçus ci-dessus pour les fiches projets ; l'accueil et
  la page « à propos » gardent des balises statiques.
- `index.html` présent dans deux images, et un ordre de build à respecter en CI.
- Un second écosystème de dépendances (`npm`) à auditer.

## Comparaison des options

| | Statique (Vite + React) | Next.js | Flutter web |
|---|---|---|---|
| Runtime en production | Aucun | Serveur Node permanent : conteneur, RAM, surface d'attaque, second runtime à maintenir | Aucun |
| Aperçus de lien et SEO | Vue Django pour les fiches | Natifs (SSR) | Pauvres : pas de rendu côté serveur |
| Poids initial | Léger | Moyen | Bundle lourd |
| Accessibilité, sélection de texte | Natives | Natives | Médiocres |
| Markdown, streaming du chat | Naturels | Naturels | Moins naturels |
| Outillage de design retenu | Compatible | Compatible | Incompatible |
| Verdict | **Retenu** | Contraire à P1 pour un site à deux visiteurs | Écarté ; à garder pour une application mobile compagnon si Flutter doit être montré |

## Conditions de réexamen

- Un besoin de rendu côté serveur généralisé (pages nombreuses à référencer) rouvrirait Next.js ou
  Astro.
- L'apparition de logique pure côté front déclenche l'ajout de Vitest.
