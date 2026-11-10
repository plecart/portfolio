# Portfolio — Spécification d'interface

_Document normatif de rang 2 (`.claude/pipeline.config.md`, « Sources de vérité »). État courant seulement : §1 porte les décisions, §2 à §7 les valeurs, mesurées sur les prototypes retenus. Amendement : le § concerné._

## 1. Direction

### 1.1 Public et impression

- **Public primaire** : recruteur technique, lead ou CTO qui décide en dix secondes s'il ouvre une fiche. **Public secondaire** : pairs développeurs, notamment via le MCP (phase 3).
- **Impression à laisser** : « ce développeur livre des projets complets, avec rigueur, sans bruit ». Découle de la finalité du cadrage (§1 : prouver la capacité à monter un projet de bout en bout).
- Aucun public « client » : pas de canal de contact (cadrage §3 « Email », D24). Ancres vérifiées : cadrage §1 conforme, §3 conforme.

### 1.2 Personnalité et mouvement

- **Sobre au repos, vivant au geste.** L'état immobile est éditorial : typographie, blanc, peu de décor. Le mouvement n'existe qu'en réaction à une action du visiteur.
- **Rien ne bouge sans cause.** Aucune animation autonome ni décorative. Le mouvement est réservé à : l'ouverture et la fermeture de la fiche projet, l'apparition des éléments au défilement, le retour visuel d'un survol ou d'un focus, et la pulsation lente des cadres vides pendant un chargement.
- **Système de mouvement unique** (§2) : quelques durées, deux courbes, un ressort ; toute animation les réutilise (P4, code minimal). Transitions d'état sous 300 ms ; un geste suit le pointeur sans durée propre.
- **Propriétés animées** : position, échelle, opacité pour tout mouvement ; la couleur seule (texte, icône, fond, filet) peut aussi transiter, brièvement, pour un retour de survol, de focus ou d'état (performance Lighthouse).
- **`prefers-reduced-motion`** : toute transition devient un fondu quasi instantané ; tout geste a un équivalent clavier.
- **Rive** hors phase 1 (runtime WASM sans besoin avéré, ADR 0008 « mesurer son poids »). Ancres vérifiées : cadrage annexe B « le plus sobre possible » conforme ; ADR 0008 « Compléments » conforme.

### 1.3 Accueil : la table de polaroids

- **Une carte par projet, de style polaroid** : image en haut, titre, et en bas deux ou trois icônes de technologies plus un indicateur « en ligne » (choix des technologies et sens de « en ligne » : §1.4). Le projet marqué « vitrine » dans l'admin (un seul à la fois, §1.9) occupe deux colonnes en tête de table ; sans projet vitrine, toutes les cartes ont la même taille.
- **Disposition** : grille fluide sur le fond de page, sans table dessinée ni 3D. Chaque carte porte une rotation légère (−3° à +3°) et un décalage de quelques pixels, déterminés par le projet, identiques à chaque visite. Le relief vient des ombres des cartes seulement.
- **Survol / focus** : la carte se redresse à 0°, se soulève, l'ombre s'élargit ; son contenu reste immobile.
- **Défilement** : vertical, continu, sans pagination ni limite ; toutes les fiches publiées sont chargées d'un coup, images en `loading="lazy"`. Chaque carte apparaît à l'entrée dans l'écran (montée de quelques pixels + fondu, décalage entre voisines).
- **Sélection** : la carte sélectionnée grandit pour devenir la fiche (sa photo, son post-it et ses rubans voyagent jusqu'à leur place dans la fiche) ; toutes les autres reculent légèrement dans la direction opposée à la carte sélectionnée et s'effacent, toutes en même temps. À la fermeture, mouvement inverse : les cartes reviennent à leur place en réapparaissant, la fiche redevient sa carte. Arrivée directe par `/projets/<slug>` : la fiche apparaît centrée en fondu ; sa fermeture fait apparaître les cartes à leur place, avec leur animation d'entrée.
- **Repli `prefers-reduced-motion`** : fondu croisé entre la table et la fiche, sans déplacement.
- **Clavier** : Entrée ouvre la carte focalisée ; à la fermeture, le focus revient sur la carte d'origine. Ancres vérifiées : cadrage §4 conforme (D46) ; ADR 0008 « Aperçus de lien » conforme (`/projets/<slug>`) ; ADR 0009 conforme (adresse inconnue : redirection vers l'accueil) ; frontend-outillage §1 « Spline écarté » conforme (pas de 3D).

### 1.4 Contenu d'une carte

- **Titre seul**, pas de phrase de résumé imprimée sur la carte. Le résumé est révélé par intention (survol, focus, premier toucher : §1.7).
- **Technologies** : ordonnées dans l'admin par projet ; la carte montre **les trois premières de type langage / framework / infra** (icône seule, nom au survol et pour les lecteurs d'écran). Les technologies de type « outil » (cadrage §6.1) ne figurent pas sur la carte ; la fiche les présente en second groupe « Outils » (§1.8). Ancres vérifiées : cadrage §6.1 « Technologie : … type (langage / framework / infra / outil) » conforme, aucun champ ajouté ; §3 « captures d'écran, langages et outils » conforme.

### 1.5 Modes clair et sombre

- Les deux modes, **suivant le réglage du système** (`prefers-color-scheme`), avec un bouton qui force l'autre ; le choix forcé est mémorisé côté navigateur. Le clic qui ramène au mode du système efface le choix et sa mémoire : le site suit de nouveau le système. Un choix mémorisé devenu égal au mode du système (le système a changé entre-temps) reste jusqu'au prochain clic (brief de #18, décision 2). Deux palettes en §2. Le point d'arrêt visuel de chaque PR se fait dans les deux modes (`contraintes.md`). Ancres vérifiées : cadrage muet ; `contraintes.md` « Points d'arrêt humains » conforme.

### 1.6 Responsive

- **Un seul site, desktop et mobile au même niveau**, mêmes animations ; chaque prototype est regardé aux deux largeurs.
- **Téléphone** : deux colonnes de cartes (largeur exacte : prototype §4), défilement continu ; la fiche occupe tout l'écran ; le bouton « retour » du navigateur ferme la fiche (une entrée d'historique par ouverture, adresse `/projets/<slug>`).
- **Desktop** : fiche en panneau centré à largeur bornée.
- **Seules les cartes visibles à l'écran sont animées** à l'ouverture et à la fermeture, sur tous les appareils.
- **Tactile** : pas de parallaxe ; état « pressé » (léger enfoncement) avant l'ouverture. Ancres vérifiées : cadrage muet ; ADR 0008 « Aperçus de lien » conforme.
- **Deux étiquettes d'état, indépendantes** : « en cours » (statut « en cours » du modèle §6.1 ; l'image de la carte reste en couleur, une sangle de chantier ceinture le polaroid et l'étiquette porte un point ambre fixe ; l'étiquette dit toujours l'état en texte, #255) et « en ligne » (un lien démo existe ; ne dit rien de l'achèvement). Un projet sans lien ne porte aucune étiquette de plus : pas de notion « privé » affichée. Ancres vérifiées : cadrage §6.1 « statut (en cours / terminé / archivé) », « liens (dépôt, démo : absents pour les projets privés) » conformes.

### 1.7 Révéler le résumé, ouvrir la fiche

- **Desktop** : le survol ou le focus clavier affiche le résumé par-dessus l'image ; un clic (ou Entrée) ouvre la fiche.
- **Mobile** : premier toucher, le résumé apparaît avec un bouton « Ouvrir » ; second toucher sur la carte, ouverture ; toucher ailleurs referme. Une seule carte révélée à la fois.
- Le résumé fait en permanence partie de la description accessible de la carte.

### 1.8 Vocabulaire graphique « fait main »

- **Quatre objets, pas plus**, dessinés à plat, deux tons chacun, valides dans les deux modes : le cadre polaroid ; le post-it du titre tenu par un trombone (trombone décoratif, `aria-hidden` ; le titre reste du texte) ; l'étiquette en ruban adhésif, un seul style pour les technologies et pour « en cours » / « en ligne » (le ruban-bouton de la stack, qui n'est ni l'un ni l'autre, en reprend la forme en contour, §4.3) ; la sangle de chantier d'un projet « en cours », rayée jaune et encre, sans texte, décorative (`aria-hidden`, §4.1, #255). Ni dégradé, ni ombre lourde, ni texture : les rayures de la sangle sont des aplats à arêtes nettes, lissées sur 1 px contre le crénelage. Verdict visuel au prototype (§4).

### 1.9 Ordre des cartes

- Le projet **« vitrine » d'abord** (booléen de l'admin, un seul projet à la fois, carte double : §1.3) ; puis les projets **« en cours »** ; puis les autres **du plus récent au plus ancien** (date de fin, sinon date de début). Aucun champ de position : le seul choix manuel est le booléen « vitrine ». Contrainte induite : toute fiche a une date de début. Ancres vérifiées : cadrage §6.1 « dates », « statut », « mise en avant » (D48) conformes ; D3 conforme (le méta-projet ouvre la table s'il porte le booléen).

### 1.10 Fiche projet

- **Desktop** : deux colonnes dans un panneau centré, dimensionné depuis la photo. Gauche : la galerie, fixe, légende et compteur sous l'image. Droite : en haut, fixes, le titre sur son post-it, les liens démo et dépôt sur des post-its **seulement s'ils existent** (rien à leur place sinon, cadrage §3), puis les rubans d'état « en cours » et « en ligne » s'il y en a (rien sinon) ; dessous, une colonne qui défile : ligne de faits (type, dates, client), résumé, stack « Technologies » puis « Outils » (ordre de l'admin, rubans avec icône, deux rangées au plus par groupe derrière un ruban-bouton « +N », §4.3 ; les trois technologies de la carte ouvrent le groupe « Technologies »), description Markdown, puis les sections de la fiche technique (cadrage §6.1), dans l'ordre de l'admin, repliées, chacune avec une ancre qui l'ouvre (liens profonds du RAG, cadrage §6.3) ; une section vide n'apparaît pas. Valeurs en §4.
- **Mobile** : galerie en haut, texte dessous, le tout défile ; galerie non fixe.
- **Fermeture** : bouton fixe en haut à droite, `Échap`, bouton « retour » du navigateur, clic hors du panneau (desktop).
- **Galerie** : balayage tactile, flèches gauche/droite à l'écran, flèches du clavier, compteur « n / N », légende sous l'image, texte alternatif = légende. Une seule image : ni flèches ni compteur.
- **Plein écran** : le bouton « Agrandir l'image » ou un clic sur l'image l'ouvre en plein écran, sur fond sombre, où l'on zoome (double clic ou double tape, molette, pincement) et où l'on se déplace (glisser, flèches) ; Échap, « Fermer l'image » ou un clic sur le fond referment, la fiche restant ouverte (§4.4).
- **Continuité** : la photo du polaroid devient la première image de la galerie ; le post-it devient le titre ; chaque ruban de la carte devient son homologue de même nom dans la fiche : une technologie, son ruban de la stack « Technologies » ; un état, son ruban de l'en-tête (§4.6). Ancres vérifiées : cadrage §4 « Fiche projet (modal) » conforme ; §6.1 « galerie d'images avec légendes » conforme.

### 1.11 Format des images

- **Cadre carré 1:1** pour la photo de la carte et pour la galerie. Chaque projet fournit une **couverture carrée** (carte, première image de la galerie, `og:image` de l'ADR 0011), d'au moins 2400 px de côté, pour le plein écran et les écrans denses ; l'`og:image` en sert la variante de 1200 px (ADR 0028). Les autres images sont libres et s'affichent entières dans le cadre carré sur fond neutre, jamais recadrées. Ancres vérifiées : cadrage §6.7 « images WebP redimensionnées » conforme ; ADR 0011 « og:image » conforme ; cadrage §7 D72.

### 1.12 Entête et navigation

- **Une ligne, fixe, fine** : à gauche le nom (texte, lien vers la table) ; à droite le bouton clair / sombre (icône, libellé accessible). Aucun logo, aucun menu replié, aucun autre lien en phase 1.
- Se fait discrète en défilant vers le bas, réapparaît dès qu'on remonte.
- **Place réservée** : phase 2, entrée « Chat » à gauche du bouton de mode (absente si le service IA est indisponible, cadrage §6.7) ; phase 3, entrée « MCP ». Trois liens au plus, jamais de menu. Ancres vérifiées : cadrage §4 phases 2 et 3 conformes ; cadrage §6.7 « Dégradation gracieuse » conforme.
- **Icône du site** (onglet, favoris, écran d'accueil d'un téléphone) : le cadre polaroid penché de 8°, sa photo couleur post-it portant un « P » de Manrope 800 ; elle suit le thème du système ou du navigateur (`prefers-color-scheme`), pas le bouton de mode, avec un cadre clair dans les deux modes pour rester visible sur un onglet sombre. Absente de l'entête, qui reste sans logo. Source et jetons : #237. Ancres vérifiées : §1.8 conforme (deux des objets « fait main », aucun nouveau) ; §1.5 conforme (le bouton règle la page, pas le navigateur).

### 1.13 Pas de page « à propos » ; liens de l'auteur

- **Aucune page ni fiche « à propos » en phase 1.** Le profil (cadrage §6.1) n'alimente que le RAG (phase 2) ; le CV public est servi par le chat, amorcé par la phrase « Demande-moi le CV de Pacôme Bernier » (place réservée, cadrage §3 « CV … version publique » conforme).
- **Liens de l'auteur** : deux icônes au trait, GitHub et LinkedIn, avec libellé accessible ; rien d'autre. Quand la marge à côté de la table le permet, elles forment une **colonne fixe en bas à droite de la fenêtre** ; sinon elles font un **pied de page** d'une ligne (seuil et valeurs : §3). Place réservée, au même endroit : « Confidentialité » et « LangGraph » en phase 2, « Se connecter au MCP » en phase 3 (cadrage §4, §6.5 et §6.6). Ancres vérifiées : cadrage §6.1 et D49 conformes.
- **Ce qui n'existe pas** : blog, formulaire de contact ou adresse email (D24), compteur de visites, bandeau cookies (aucun cookie tiers, cadrage §6.6), sélecteur de langue (D28), recherche ou filtre sur la table.

### 1.14 Couleur et typographie (direction)

- **Monochrome chaud, un seul accent.** Fond crème côté clair, gris chaud très sombre côté sombre ; jamais de blanc ni de noir purs ; texte en encre foncée. Le cadre, le post-it et le ruban « fait main » restent dans la gamme (post-it et ruban en teintes pâles) ; la sangle de chantier, seul objet vif, ne dit que « en cours ». L'accent sert à deux choses seulement : l'anneau de focus et les liens. Autres couleurs, chacune à un seul usage : le vert `--live` au point « en ligne » ; l'ambre `--ongoing` au point « en cours » ; le jaune et l'encre du chantier (`--strap`, `--strap-ink`) à la sangle d'un projet « en cours » (#255). Valeurs : §2, mesurées au prototype.
- **Une seule famille sans-serif, police variable, hébergée sur le site** (aucune requête vers un service de polices : Lighthouse, cadrage §6.6, CSP). Contraste par tailles et graisses ; pas de police manuscrite. Ancres vérifiées : cadrage §6.6 « CSP stricte », « pas de cookie tiers » conformes ; annexe B « le plus sobre possible » conforme.

### 1.15 États

- **Chargement** : des cadres de polaroid vides, dans la gamme du fond, à la place des cartes — autant que de projets publiés, nombre tenu à la main (§5.1) ; remplacés par les cartes avec l'animation d'apparition.
- **Erreur** (API injoignable) : un texte centré, « Les projets ne se chargent pas. », suivi d'un lien « Réessayer » qui relance le chargement ; aucun polaroid.
- **Vide** (aucun projet publié) : rien — entête et liens seuls, table vide, aucun message.
- **Adresse inconnue** (`/projets/<slug>` sans projet, ADR 0009) : le serveur redirige vers l'accueil ; aucune page 404.
- **1, 3, 12 cartes** : une carte seule, plus grande et centrée ; trois cartes en rangée centrée ; à partir de quatre, grille pleine largeur. Tailles : §4, mesurées au prototype.

### 1.16 Seuils Lighthouse (bloquants en CI, version de production)

| Catégorie | Seuil |
|---|---|
| Performance | ≥ 90 |
| Accessibilité | = 100 |
| Bonnes pratiques | ≥ 95 |
| SEO | ≥ 95 |

Ancres vérifiées : frontend-outillage §3 item 12 (seuils annoncés sans valeur : vide comblé) ; ADR 0008 « Lighthouse CI » conforme. P6 conforme.

### 1.17 Contraintes de contenu induites (récapitulatif, détaillé en §7)

- Titre : **30 caractères** au plus, sur deux lignes au plus du post-it (à 14 px, une ligne de 30 caractères, environ 204 px de texte, exige une carte d'environ 255 px, que la carte simple n'atteint pas à 400 px).
- Résumé : **120 caractères** au plus (sept lignes au plus sur la carte simple mobile, moins sous 400 px, §7) ; sert aussi d'`og:description`.
- Couverture : **carrée, ≥ 2400 px de côté**, une par projet ; autres images libres, chacune avec une légende (texte alternatif).
- Technologies : au moins une, ordonnées ; les trois premières de type langage / framework / infra vont sur la carte.
- Dates : date de début obligatoire ; date de fin pour les projets terminés (ordre §1.9).
- Liens : dépôt et démo facultatifs ; « en ligne » découle de la démo.
- Vitrine : un projet au plus porte le booléen ; l'admin refuse un second.
- Sections : autant que l'auteur en crée, titre de **40 caractères** au plus, ancre unique dans le projet.

## 2. Jetons

Les jetons sont des propriétés CSS déclarées sur `:root` (la palette l'est aussi sur la couche plein écran, qui la prend sombre, §4.4). La palette suit `prefers-color-scheme` ; `data-theme="light"` ou `data-theme="dark"` sur `<html>` force l'autre mode et se mémorise dans `localStorage` (clé `theme`), et le retour au mode du système retire l'un et l'autre (§1.5) ; `color-scheme: light dark`, ou le seul mode forcé quand `data-theme` est posé — les éléments natifs du navigateur suivent alors le mode affiché. Les sections 3 à 7 citent les couleurs, ombres et courbes par leur jeton ; elles citent tailles, rayons, durées et espacements par leur valeur, qui appartient toujours aux échelles de cette section, hors les dimensions propres à un objet listées en §2.3.

### 2.1 Couleurs

| Jeton | Clair | Sombre | Sert à |
|---|---|---|---|
| `--bg` | `#F3EDE4` | `#1C1A17` | fond de page |
| `--paper` | `#FBF8F2` | `#2B2724` | papier : cadres polaroid, panneau de fiche, feuille en vol, entête décollée, disques des boutons et des liens |
| `--ink` | `#2A2622` | `#EDE6DA` | texte principal, nom, icônes au survol, message d'erreur |
| `--ink-2` | `#6B635A` | `#A69C8F` | texte secondaire (faits, légendes, compteur, intertitres), icônes au repos, trombone, marqueurs + / − |
| `--line` | `#DCD3C6` | `#3B3631` | filets, cadres vides, zone image avant chargement, curseur de la barre de défilement |
| `--accent` | `#B4471F` | `#E88A5E` | anneau de focus, liens (dont « Réessayer »), nom au survol |
| `--live` | `#4A7C59` | `#8FB996` | point « en ligne », seul usage (§1.14) |
| `--postit` | `#F4E3A1` | `#B59F55` | post-it du titre |
| `--postit-ink` | `#2A2622` | `#1C1A17` | texte des post-its |
| `--postit-link` | `color-mix(in srgb, var(--accent) 22%, var(--postit))`, soit `#E6C184` | même formule, soit `#C09A57` | post-its de lien de la fiche |
| `--tape` | `#E8DFCF` | `#3D372F` | rubans |
| `--tape-ink` | `#2A2622` | `#D8CFC0` | texte des rubans |
| `--ongoing` | `#9A6A0E` | `#C98A12` | point « en cours », seul usage (§1.14) |
| `--strap` | `#F0C23A` | `#CCA531` | rayures jaunes de la sangle de chantier |
| `--strap-ink` | `#2A2622` | `#1C1A17` | rayures encre de la sangle |
| `--strap-edge` | `color-mix(in srgb, var(--strap) 50%, var(--strap-ink))`, soit ≈ `#8D742E` | même formule, soit ≈ `#746024` | tranche de 3 px de la sangle, hors du cadre |

Teintes dérivées, toujours par `color-mix` sur ces jetons : bandeau de résumé et entête décollée = `--paper` à 94 % ; flèches de galerie et bouton « Agrandir l'image » = `--paper` à 88 %. La couche plein écran de la galerie (§4.4) prend les valeurs sombres de cette table dans les deux modes. Jamais de blanc ni de noir purs (§1.14). Contrastes : §6.2.

### 2.2 Typographie

- **Famille** : Manrope, police variable 200–800, sous-ensemble latin (woff2, 25 Ko), incorporée dans le CSS du site, `font-display: swap` ; repli `'Segoe UI Variable', system-ui, sans-serif`. Corps 16 px, interligne 1,5, `-webkit-font-smoothing: antialiased`.
- **Échelle** : `--fs-body` 16 px · `--fs-small` 13 px · `--fs-tiny` 11 px. Tailles propres à un objet, hors échelle : 15 px (nom, post-it lien, titre de section), 22 px (titre de fiche), 16 / 20 / 14 / 18 px (post-it de carte, §4.1), 14 px (résumé sur carte), 18 px (résumé de la fiche, marqueur + / −).

| Texte | Taille / graisse | Interligne | Interlettrage | Couleur |
|---|---|---|---|---|
| Nom (entête) | 15 / 600 | — | .01em | `--ink` |
| Lien « Chat » (place réservée) | 13 / 600 | — | — | `--ink-2` |
| Post-it de carte | 16 / 600 ; vitrine 20 ; mobile 14, vitrine 18 | 1,25 | .005em | `--postit-ink` |
| Post-it de fiche (titre) | 22 / 600 | 1,25 | .005em | `--postit-ink` |
| Post-it lien | 15 / 600 | 1,25 | — | `--postit-ink` |
| Ruban | 13 / 700, toutes cartes et fiche | 1 | .02em | `--tape-ink` |
| Résumé sur carte | 14 / 400 ; mobile 13 | 1,4 | — | `--ink` |
| Ligne de faits, légende, compteur | 13 / 400 | 1,5 | — | `--ink-2` |
| Résumé de la fiche | 18 / 500 | 1,4 | — | `--ink` |
| Description et sections de la fiche | 16 / 400 | 1,5 | — | `--ink` |
| Titre de section | 15 / 700 | 1,5 | — | `--ink` |
| Intertitre « Technologies » / « Outils » | 11 / 700, capitales | 1,5 | .08em | `--ink-2` |
| Message d'erreur | 16 / 400 | 1,5 | — | `--ink` |
| Lien « Réessayer » | 16 / 400, souligné | 1,5 | — | `--accent` |
| Bouton « Ouvrir » | 13 / 600 | — | — | `--ink` |

### 2.3 Espacement

Échelle `--s-1` à `--s-7` : 4, 8, 12, 16, 24, 32, 48 px. Valeurs hors échelle, propres à un objet et citées telles quelles en §3 et §4 : 28 px (gouttière de la table), 6 px (montée d'une carte, décalage du bandeau, point « en ligne », marge haute des post-its de lien), 9 px (marge des rubans de carte), 10 et 14 px (cadre du polaroid, marge des post-its), 18 px (retrait des listes).

### 2.4 Rayons

`--r-card` 2 px (cadre polaroid, panneau, feuille) · `--r-tape` 2 px (rubans) · `--r-button` 6 px (« Ouvrir ») · post-it 1 px · disques 999 px (boutons icône, liens de l'auteur, flèches de galerie, curseur de barre de défilement).

### 2.5 Ombres

| Jeton | Clair | Sombre | Sert à |
|---|---|---|---|
| `--shadow-rest` | `0 1px 2px rgba(42,38,34,.08), 0 4px 12px rgba(42,38,34,.10)` | `0 1px 2px rgba(0,0,0,.30), 0 4px 12px rgba(0,0,0,.35)` | carte au repos, disques des liens |
| `--shadow-lift` | `0 4px 8px rgba(42,38,34,.10), 0 20px 40px rgba(42,38,34,.20)` | `0 4px 8px rgba(0,0,0,.35), 0 20px 40px rgba(0,0,0,.55)` | carte survolée ou révélée, feuille en vol, panneau de fiche |

Filet de l'entête décollée : `0 1px 0 var(--line)`. Aucune autre ombre.

### 2.6 Barre de défilement

Page, colonne de lecture de la fiche et, sur téléphone, son panneau : `scrollbar-width: thin ; scrollbar-color: var(--line) transparent`. Moteurs WebKit : 6 px de large, curseur `--line` arrondi (999 px), piste transparente.

### 2.7 Mouvement

- **Propriétés** : `transform` (position, échelle) et `opacity` pour tout mouvement ; `color`, `background-color` et `box-shadow` seulement pour un retour de survol, de focus ou d'état (§1.2) ; la largeur et la marge intérieure seulement pour le ruban qui se roule en vol (§4.6).
- **Durées** : `--dur-fast` 150 ms · `--dur` 240 ms · `--dur-open` 280 ms. Durées fixes, nommées (#19) : `--dur-content` 200 ms (entrée du contenu de fiche, retrait du trombone, arrivée directe) · `--dur-press` 80 ms (pression) · `--delay-column` 40 ms (retard d'entrée par colonne) · `--delay-ribbon` 20 ms (retard entre rubans en vol) · `--dur-strap` 500 ms (glissement de la sangle au coin, #255) · `--dur-pulse` 1,8 s (pulsation des cadres vides) · `--dur-reduced` 160 ms (activation et fermeture de la fiche en mouvement réduit, §6.3).
- **Courbes** : `--ease-out` `cubic-bezier(.22, 1, .36, 1)` pour toute transition · `--ease-spring` `linear(0, .28 6%, .62 13%, .88 20%, 1.03 28%, 1.01 40%, 1)` pour le seul soulèvement d'une carte · `--ease-in-out` `cubic-bezier(.65, 0, .35, 1)` pour la seule pulsation.

| Mouvement | Durée | Courbe |
|---|---|---|
| Entrée d'une carte (montée de 8 px + fondu) | 240 ms, + 40 ms par colonne | `--ease-out` |
| Redressement, recul et retour d'une carte | 240 ms | `--ease-out` |
| Soulèvement d'une carte (−6 px, ×1,02) | 240 ms | `--ease-spring` |
| Ombre soulevée (opacité) | 240 ms | `--ease-out` |
| Bandeau de résumé | opacité 150 ms, translation 240 ms | `--ease-out` |
| Pression sur une carte | 80 ms | `--ease-spring` |
| Couleur au survol (nom, icônes, liens) ; fond et filet de l'entête | 150 ms | `--ease-out` |
| Entête qui sort et revient | 240 ms | `--ease-out` |
| Colonne des liens de l'auteur qui s'efface et revient | 150 ms | `--ease-out` |
| Glissement de la sangle au coin et retour ; son entrée sur la carte réapparue (§4.6) | 500 ms | `--ease-out` |
| Vol de la photo, du post-it et des rubans ; sortie de la sangle ; feuille ; recul des cartes | 280 ms | `--ease-out` |
| Trombone | opacité 150 ms, translation 200 ms | `--ease-out` |
| Contenu de la fiche : entrée / sortie | 200 ms (+ 8 px) / 150 ms | `--ease-out` |
| Galerie (glissement) | 240 ms | `--ease-out` |
| Plein écran : fondu d'ouverture et de fermeture | 240 ms | `--ease-out` |
| Plein écran : zoom au double clic et aux touches, déplacement aux touches (aucune transition au glisser, à la molette, au pincement ; changer d'image est instantané) | 240 ms | `--ease-out` |
| Post-it lien (survol, −2 px) / liens de l'auteur (survol, −2 px) | 150 ms / 240 ms | `--ease-out` |
| Arrivée directe : entrée / sortie | 200 ms / 150 ms | `--ease-out` |
| Pulsation des cadres vides | 1,8 s, infinie | `--ease-in-out` |

Mouvement réduit : §6.3.

## 3. Architecture des écrans

### 3.1 Accueil (`/`)

De haut en bas : l'entête (§3.3), la table (`<main>`), les liens de l'auteur (§3.4), en pied de page ou en colonne fixe.

- **Table** : conteneur à marge intérieure 24 px 16 px 32 px ; grille `repeat(auto-fit, 240px)` centrée, gouttière 28 px, largeur maximale 1200 px, remplissage dense. Quatre colonnes au plus (1044 px) dès 1076 px de large ; trois (776 px) de 808 à 1075 px ; deux (508 px) de 600 à 807 px. En dessous de 600 px : deux colonnes `1fr`, gouttière 16 px (cartes de 176 px à 400 px de large). La carte vitrine occupe deux colonnes et deux rangées ; sur mobile, la première rangée entière. Repère à 1280 px : table de 1044 px, marge de 118 px de chaque côté.
- **Entrée des cartes** : une carte apparaît quand 15 % de sa surface entre dans l'écran (`IntersectionObserver`, seuil 0,15) : montée de 8 px et fondu de 240 ms, retardés de 40 ms par indice de colonne. Défilement continu, sans pagination (§1.3) ; images en `loading="lazy"`.
- **Adresses** : `/` pour la table ; `/projets/<slug>` pour une fiche ouverte, avec une entrée d'historique par ouverture (le retour du navigateur ferme la fiche) ; adresse sans projet : §5.4.
- **Ordre des cartes** : §1.9.

### 3.2 Fiche projet (`/projets/<slug>`)

- **Panneau** : `role="dialog"` `aria-modal="true"`, nommé par le titre ; fixé au centre de la fenêtre, z-index 30, au-dessus de la table dont le défilement est verrouillé ; papier, rayon 2 px, `--shadow-lift`, marge intérieure 10 px ; deux colonnes « photo | lecture », gouttière 24 px.
- **Dimension depuis la photo** : `--photo = min(100vh − 96px, 660px, (100vw − 92px) / 2)` ; largeur du panneau `2 × photo + 44 px` ; hauteur `photo + 48 px`. Constantes : 44 = 10 + 24 + 10 (marges intérieures et gouttière) ; 48 = 10 + 20 + 8 + 10 (marges, barre de galerie, écart sous la photo) ; 96 = 48 + 2 × 24 et 92 = 44 + 2 × 24 (le panneau garde 24 px de chaque bord de la fenêtre). Repères : 1280 × 800 → photo 594 px, panneau 1232 × 642 px (marges 24 px et 79 px) ; 1440 × 900 → photo 660 px (plafond), panneau 1364 × 708 px ; 1024 × 768 → photo 466 px, panneau 976 × 514 px.
- **Colonne de lecture** : marge intérieure 12 px 16 px 0 0 ; en haut, fixes, le post-it du titre, les post-its de lien et les rubans d'état ; dessous, la colonne défilante (§4.3). À 1280 × 800 (mesuré le 2026-11-09, #255) : avec un état, en-tête de 101 px, colonne défilante de 509 px, marge basse de 16 px comprise ; sans état, en-tête de 53 px avec des liens (colonne de 557 px) et de 52 px sans lien (558 px).
- **Mobile** (≤ 599 px) : le panneau est la fenêtre (100 vw × 100 vh, rayon 0, marge intérieure 8 px), une colonne, gouttière 12 px ; la photo prend la largeur disponible (384 px à 400 px) ; l'en-tête n'est plus fixe : tout défile avec le panneau ; colonne de lecture à marge 12 px 0 32 px.
- **Fermeture** : bouton de 36 px en haut à droite du panneau, à 8 px des bords, papier, icône 20 px, libellé « Fermer la fiche » ; Échap ; retour du navigateur ; dès 600 px, un clic hors du panneau. Focus : sur ce bouton à l'ouverture, retenu dans le panneau, rendu à la carte d'origine à la fermeture. Chorégraphie : §4.6.

### 3.3 Entête

- **Boîte** : fixe en haut, z-index 40, 56 px de haut, marge intérieure 0 24 px (0 16 px sous 600 px) ; le corps de page commence 56 px plus bas.
- **Gauche** : le nom, 15 px / 600, lien vers `/`, `--accent` au survol.
- **Droite**, groupe à 8 px d'écart : la place « Chat » (phase 2 ; « MCP », phase 3, à sa gauche, même composant) puis le bouton de mode : 36 px rond, icône au trait 20 px (soleil en mode clair, lune en mode sombre ; l'icône inactive est retirée du rendu), libellé « Passer en mode sombre » ou « Passer en mode clair », `--ink-2` → `--ink` au survol.
- **Défilement** : en haut de page, l'entête est transparente. Dès 1 px de défilement, elle prend `--paper` à 94 % et un filet bas de 1 px `--line`. Au-delà de 56 px de défilement, 8 px cumulés vers le bas la font sortir par le haut (translation de −100 %, 240 ms) ; 8 px cumulés vers le haut la ramènent. Elle reste visible tant qu'elle contient le focus clavier.
- **Fiche ouverte** : l'entête prend son état de sortie par le haut, quel que soit le défilement, et revient à la fermeture ; en mouvement réduit, fondu de 150 ms (§6.3).
- **Place « Chat »** : lien texte 13 px / 600, 36 px de haut, marge intérieure 0 12 px, rayon 999 px, `--ink-2` → `--ink` ; absent du DOM en phase 1. À 400 px, le nom (114 px), « Chat » (54 px) et le bouton laissent environ 155 px libres. Trois liens au plus (§1.12).

### 3.4 Liens de l'auteur (D49)

Deux liens, GitHub puis LinkedIn, icônes au trait 22 px, libellés « GitHub de Pacôme Bernier » et « LinkedIn de Pacôme Bernier » ; même élément `<footer>` sous les deux formes, dernier dans l'ordre de tabulation.

- **Colonne fixe** : dès que la marge entre le bord de la fenêtre et la cellule de carte la plus proche atteint 76 px (36 px de disque + 24 px du bord + 16 px de garde), le pied devient une colonne fixe en bas à droite : à 24 px des bords, z-index 40, 36 px de large ; un disque de 36 px par lien, écart 8 px (80 px de haut pour deux), papier, `--shadow-rest`, icône `--ink-2` ; survol : `--ink` et montée de 2 px (240 ms). La marge se mesure sur les cellules affichées dans la table — cartes et cadres de chargement, chacun sur sa boîte de grille, hors pose et hors animation —, et hors barre de défilement : la grille, centrée dans la largeur visible, recule de la moitié de la barre, que la mesure lui rend ; les repères ci-dessous valent donc avec ou sans barre (choix du mainteneur, 2026-10-14) ; une table sans cellule (écrans vide et erreur) a sa colonne fixe dès 600 px de large et son pied de page en dessous (brief de #18, décision 1). Recalculée au redimensionnement et quand les cellules changent. Repères : colonne à 1280 px (marge 118), 1200 px (78) et 1000 px (112, trois colonnes de cartes) ; pied de page à 1100 px (28, quatre colonnes), 600 px (46) et sur mobile (16).
- **Pied de page** : après la table, une rangée centrée, marge 48 px 0 32 px, écart 24 px, un filet de 48 × 1 px `--line` centré au-dessus ; chaque icône dans une zone de 38 px (marge intérieure 8 px), sans disque, `--ink-2` → `--ink` et montée de 2 px au survol.
- **Fiche ouverte** : la colonne fixe s'efface en 150 ms et revient à la fermeture ; le pied de page reste sous le plein écran.
- **Place réservée** (§1.13) : un disque de plus en haut de la colonne, ou un lien de plus dans la rangée.

## 4. Composants

### 4.1 Carte polaroid

- **Structure** : `<a href="/projets/<slug>">`, nom accessible « Titre. En cours. En ligne. » (les états présents seulement ; sans état, le titre seul), description accessible : le résumé puis les technologies. Couches, de l'extérieur vers l'intérieur : entrée et recul ; pose (rotation, décalage) ; face (papier, ombre, cadre) ; puis la photo (image, bandeau de résumé), le trombone, le post-it et la bande basse (rubans, bouton « Ouvrir ») ; et par-dessus tout, la sangle d'un projet « en cours », qui ne croise pas la bande basse.

| Carte | Largeur | Cadre | Photo | Bande (min.) | Hauteur (min.) |
|---|---|---|---|---|---|
| simple, desktop | 240 px | 10 px | 220 px | 52 px | 282 px |
| vitrine, desktop | 508 px (2 colonnes + 28) | 14 px | 480 px | 64 px | 558 px |
| seule, desktop (1 projet) | 360 px | 10 px | 340 px | 52 px | 402 px |
| simple, mobile | (100 vw − 48 px) / 2 = 176 px à 400 px | 8 px | 160 px | 48 px | 216 px |
| vitrine, mobile | 100 vw − 32 px = 368 px à 400 px | 12 px | 344 px | 56 px | 412 px |
| seule, mobile | 80 % de la table = 294 px à 400 px | 8 px | 278 px | 48 px | 334 px |

Hauteur = cadre + photo + bande ; la bande grandit si les rubans passent sur deux lignes : 84 px mesurés (deux rangées de 32 px, écart 4 px, marges 8 px) sur une carte simple portant cinq rubans, et sur la carte simple mobile dès trois technologies et « en ligne ».

- **Pose** : rotation dans ±3° et décalage dans ±6 px sur chaque axe, tirés d'une empreinte du slug (FNV-1a) : identiques à chaque visite (§1.3).
- **Face** : `--paper`, rayon 2 px, `--shadow-rest`, marge intérieure cadre / cadre / 0.
- **Post-it** (`<h2>`) : absolu, 8 px au-dessus du cadre et 14 px de son bord gauche, largeur maximale = carte − 28 px, marge intérieure 6 10 6 12, rayon 1 px, rotation −2° (pivot haut gauche), texte §2.2, deux lignes au plus (troncature `line-clamp`).
- **Trombone** : absolu, 14 px au-dessus du cadre et 6 px de son bord gauche, 14 × 30 px, trait 1,6 px `--ink-2`, rotation −12°, décoratif.
- **Photo** : carré ; l'image de couverture (§1.11) remplit le cadre ; fond `--line` avant chargement ; débordement masqué. En couleur, quel que soit l'état du projet.
- **Sangle** (projet « en cours » seulement, carte simple et vitrine ; décorative, `aria-hidden`, sans texte) : une bande rayée tendue en diagonale du bas gauche au haut droit de la photo : son bord bas rencontre le bord gauche de la face à la hauteur du bas de la photo, son bord haut le bord droit à la hauteur du haut de la photo, toute son épaisseur dans la hauteur de la photo — elle ne croise jamais la bande basse ; centrée sur la photo, son angle suit les proportions de chaque carte, atan2(photo, face) − asin(épaisseur / diagonale) (−38,2° sur la carte simple desktop, −39,2° vitrine, −39,1° seule ; −37,9° / −38,8° / −39,1° sur mobile) ; épaisse de 10 % de la largeur de sa boîte, la face et ses deux tranches de 3 px (24,6 px sur la carte simple desktop, 51,4 px vitrine, 36,6 px seule ; 18,2 / 37,4 / 30,0 px sur mobile) ; rayures à 45° de son axe, `--strap` et `--strap-ink`, chacune large d'une demi-épaisseur, chacune passant à la suivante en 1 px. Coupée au bord de la face ; elle enroule la carte : une tranche `--strap-edge` de 3 px dépasse des bords gauche et droit, dans le prolongement de la bande, rien au-delà : aucune carte voisine n'est recouverte. Au-dessus de la photo, du post-it et du trombone ; elle ne croise pas la bande basse ; elle suit la pose, le soulèvement et la pression de la face. Révélation (survol, focus, premier toucher : les déclencheurs du bandeau) : elle glisse perpendiculairement à son axe jusqu'à ceinturer le coin haut gauche, à moitié de son épaisseur (12,3 px sur la carte simple desktop, 9,1 px sur mobile), son axe à 8 % de la largeur de sa boîte (19,7 px sur la carte simple desktop) du coin haut gauche de cette boîte, le bandeau entièrement dégagé (`transform` seul, 500 ms, `--ease-out`) ; trajet inverse au retour. Mouvement réduit : §6.3. Ouverture et fermeture : §4.6.
- **Bandeau de résumé** : absolu en bas de la photo, marge intérieure 12 px, `--paper` à 94 %, 14 px (mobile 13 px), `--ink` ; caché (opacité 0, 6 px plus bas) ; révélé au survol ou au focus (opacité 150 ms, translation 240 ms) et au premier toucher ; `aria-hidden` (le résumé est dans la description accessible). Capacité : §7.
- **Bande basse** : hauteur minimale selon la carte, marge 8 px 0, deux listes — rubans de technologies à gauche, rubans d'état à droite — écart 4 px, retour à la ligne si besoin. Sur un appareil sans survol, pendant la révélation, les deux listes laissent la place au bouton « Ouvrir » (30 px de haut, marge intérieure 0 12 px, bordure 1 px `--ink`, `--paper`, rayon 6 px, 13 / 600) : la hauteur de la carte ne change pas.
- **Ruban** : 32 px de haut sur toutes les cartes et à toutes les largeurs, marge intérieure 0 9 px, `--tape` / `--tape-ink`, rayon 2 px, 13 / 700, sans retour à la ligne, rotation −1,5° (impairs) ou +1° (pairs) ; icône de 24 px, à 4 px du texte. Technologie : icône visible, nom complet en texte masqué et en infobulle. « en cours » : point de 6 px `--ongoing`, fixe (ni animation ni clignotement), puis le texte. « en ligne » : point de 6 px `--live` puis le texte. Chaque ruban porte son identité (`data-ribbon` : le nom de la technologie, ou `ongoing` / `live`), qui l'apparie à son homologue de la fiche (§4.6). Sur la carte simple desktop, trois technologies et « en ligne » tiennent sur une rangée (218 px pour 220 ; 226 px avec une marge de 10 px).
- **Survol et focus** (appareils à survol) : la pose revient à 0° et 0 px (240 ms) ; la face monte de 6 px et grandit de 2 % (240 ms, `--ease-spring`) ; l'ombre soulevée apparaît (240 ms) ; le bandeau se révèle. Focus clavier : anneau de 2 px `--accent` à 4 px de la face. Pression : ×0,985 en 80 ms.
- **Toucher** : premier toucher = révélation (redressement, ombre soulevée, bandeau, bouton « Ouvrir ») ; second toucher, sur la carte ou le bouton = ouverture ; toucher hors des cartes = fin de la révélation ; une carte révélée à la fois.

### 4.2 Carte vitrine

La carte du projet « vitrine » (§1.9) est une carte polaroid aux dimensions de la ligne « vitrine » du tableau de §4.1 : deux colonnes et deux rangées de la table (une rangée sur mobile), cadre 14 px, bande 64 px, post-it 20 px (mobile : 12 px, 56 px, 18 px) ; ses rubans sont ceux de toutes les cartes (§4.1). Elle n'existe pas quand la table n'a qu'une carte.

### 4.3 Fiche

- **Galerie** à gauche (§4.4), calée en haut.
- **En-tête fixe** (retour à la ligne, écart horizontal 16 px ; marge droite de 26 px dès 600 px, qui l'arrête à 8 px du bouton de fermeture) : le post-it du titre (`<h2>`, 22 / 600, marge intérieure 8 14 8 16, marge basse 8 px, rotation −2°, `--postit`) ; les post-its de lien (`<a>`) « Voir le site » (démo) puis « Voir le dépôt » (dépôt) : 15 / 600, marge intérieure 8 14, marge 6 px 0 12 px, rotation −4° gardée dans tous les états, `--postit-link`, icône de lien externe 14 px à 4 px du texte, survol : montée de 2 px (150 ms) ; absents sans lien. Puis, sur toute la largeur, les rubans d'état « en cours » et « en ligne » (rubans de §4.1), écart 4 px 8 px, marge basse 16 px ; sans état, ni cette rangée ni sa marge. Les technologies de la carte n'y sont pas : elles ouvrent la stack (item 3), où leurs rubans volent (§4.6, #255).
- **Colonne défilante** (`overflow-y: auto` une fois la fiche posée ; marge 0 8 px 16 px 0 ; barre §2.6), dans l'ordre :
  1. ligne de faits « Type · Dates · Client », 13 px `--ink-2`, marge basse 16 px ; un fait absent disparaît avec son séparateur ;
  2. résumé, 18 / 500, interligne 1,4, marge basse 16 px ;
  3. stack : intertitre « Technologies » (marge 12 px 0 8 px) puis les technologies dans l'ordre de l'admin (rubans de 32 px en 13 px, icône de 24 px, marge intérieure 0 8 px, 6 px entre icône et texte, liste à retours à la ligne, écart 4 px 8 px) ; ses trois premières sont celles de la carte ; intertitre « Outils » et ses rubans, seulement s'il y a des outils. **Deux rangées au plus par groupe**, mesurées sur la mise en page réelle et recalculées quand la largeur de la colonne change (repliées seulement) : les rubans qui n'y tiennent pas sont retirés du rendu, et le dernier emplacement de la deuxième rangée devient un **ruban-bouton** « +N » (il peut repousser un ruban dans le repli) ; si tout tient, aucun bouton. Le ruban-bouton reprend la forme, la hauteur (32 px, bord compris) et l'inclinaison des rubans, en contour : fond transparent, bord pointillé 1 px `--tape`, texte `--ink`, marge intérieure 0 8 px ; survol : montée de 2 px (150 ms), sans montée en mouvement réduit. Il déplie le groupe sur place et devient « Réduire », en fin de liste, focus gardé ; chaque ouverture de la fiche montre les groupes repliés. Sémantique : §6.2. À 1280 × 800, la colonne fait 570 px de large ; un groupe de 12 technologies y montre 11 rubans et « +1 » ;
  4. description (Markdown rendu : paragraphes à marge basse 12 px, listes à retrait 18 px), marge haute 16 px ;
  5. sections : bloc à marge haute 16 px et filet haut 1 px `--line` ; un `<details id="s-<ancre>">` fermé par section, filet bas 1 px chacun ; `<summary>` de 47 px (marge 12 px 0), titre 15 / 700 à gauche, « + » (« − » ouvert) 18 px `--ink-2` à droite, marqueur natif masqué ; corps à marge basse 12 px, paragraphes 16 px à marge basse 8 px. Une section vide n'est pas rendue. Ordre et ancres : ceux de l'admin, l'ancre de chaque section unique dans le projet (§7). Un lien vers `#s-<ancre>` ouvre la section et la fait défiler en vue (`scroll-margin-top` 8 px ; défilement animé, instantané en mouvement réduit).
- **Mobile** : galerie, en-tête, colonne, dans cet ordre ; tout défile avec le panneau (§3.2).

### 4.4 Galerie

- **Cadre** : carré de `--photo` (§3.2), fond `--line` ; piste de diapositives translatée de `−i × 100 %` en 240 ms ; une image non carrée s'affiche entière sur fond neutre (§1.11).
- **Flèches** « Image précédente » et « Image suivante » : 36 px rondes, `--paper` à 88 %, `--ink`, icône 18 px, centrées verticalement, à 8 px des bords.
- **Barre** sous l'image : 20 px, 13 px `--ink-2`, légende à gauche, compteur « n / N » à droite (chiffres tabulaires, `aria-live="polite"`).
- **Commandes** : les flèches ; ← et → au clavier quand la fiche est ouverte, sans autre effet ; balayage horizontal de plus de 40 px ; boucle après la dernière image.
- **Une seule image** : ni flèches ni compteur ; la barre reste, avec la légende.
- Texte alternatif = légende. Projet « en cours » : la galerie est en couleur, la première image comprise, pendant le vol comme posée ; la fiche ne porte pas de sangle (§4.6).
- **Plein écran** (#243) :
  - **Ouverture** : le bouton « Agrandir l'image » (36 px, rond, `--paper` à 88 %, `--ink`, icône 18 px, en bas à droite du cadre à 8 px, présent à une seule image) ou un clic sur l'image (curseur loupe) ouvre la couche sur l'image courante ; un balayage ne l'ouvre pas.
  - **La couche** : un second dialogue modal, « Image en plein écran », sur toute la fenêtre, fond `--bg` et valeurs sombres des jetons dans les deux modes (§2.1). Une zone d'image (la fenêtre moins la barre) où l'image entière se centre, servie par `srcset` avec `sizes="100vw"` ; « Fermer l'image » en haut à droite à 8 px (36 px, `--paper`, `--ink-2`) ; les flèches de la galerie, à 8 px des bords, centrées dans la zone, absentes à une seule image, qui changent toujours d'image, en boucle ; une barre dessous, 13 px `--ink-2`, à 8 px des bords : légende à gauche, compteur « n / N » à droite (`aria-live="polite"`), absent à une seule image. Aucun bouton de zoom. Une seule image montée : changer d'image est une bascule instantanée et remet le zoom à ×1.
  - **Zoom** de ×1 à ×4, bornes fixes : double clic, ou double tape au doigt (deux touchers consécutifs, à 500 ms et 20 px au plus l'un de l'autre ; un autre geste, une molette, une touche ou un changement d'image entre eux le rompt), de ×1 à ×2 au point visé, et de tout zoom supérieur à ×1 ; molette au point du curseur (+15 % par cran de 100 px ; le pincement du pavé tactile, molette avec Ctrl, zoome l'image et non la page) ; pincement à deux doigts, au point milieu ; touches + et −, au palier entier suivant ou précédent, au centre de la zone. Le point visé reste sous le pointeur, sauf quand la borne de déplacement l'en écarte près d'un bord. Un pincement ou une molette qui s'achève (150 ms sans cran) sous ×1,05 revient à ×1, sans transition.
  - **Déplacement**, une fois zoomé : glisser à la souris ou au doigt, depuis l'image ou le fond (curseur main) ; ← → ↑ ↓ de 100 px, dans le sens du défilement d'une page. Toujours borné : aucun bord de l'image zoomée ne s'écarte du bord de la zone qu'il dépasse, et l'image reste centrée sur un axe où elle tient. À ×1, ← et → et le balayage horizontal au doigt ou au stylet (plus de 40 px ; jamais à la souris) changent d'image. Au redimensionnement, la vue revient dans ses bornes, sans transition.
  - **Tactile** : la couche prend tous les gestes du doigt (`touch-action: none`) ; le cadre de la galerie garde les siens au navigateur.
  - **Fermeture** : Échap, « Fermer l'image », ou un toucher du fond (un appui et un relâché sur le fond, sans glisser au-delà de 10 px, commencé plus de 500 ms après l'ouverture : plus tôt, c'est le second temps du double clic qui a ouvert la couche) ferment la couche seule ; un second Échap ferme la fiche. La couche n'a pas d'entrée d'historique : le retour du navigateur ferme la fiche entière (§3.1). À l'ouverture, le focus va sur « Fermer l'image » et reste dans la couche ; à la fermeture, il revient sur « Agrandir l'image », et la galerie montre l'image vue en dernier.
  - **Mouvement** : fondu d'ouverture et de fermeture de 240 ms ; zoom au double clic et aux touches en 240 ms ; aucune transition pendant un glisser, une molette ou un pincement (§2.7, §6.3).

### 4.5 Message d'erreur

Un paragraphe (`role="status"`) centré, horizontalement et verticalement, dans l'espace entre l'entête et les liens de l'auteur, à la place de la table : 16 px `--ink`, « Les projets ne se chargent pas. » puis, à la ligne, le lien « Réessayer » — un bouton au style de lien, `--accent`, souligné à 3 px sous la ligne, sans bordure ni fond, `--ink` au survol, anneau de focus §6.2 ; clic ou Entrée relance le chargement (§5.1). Aucun cadre, aucune icône.

### 4.6 Chorégraphie d'ouverture et de fermeture

**Ouverture** (clic, Entrée, second toucher).

| Instant | Ce qui se passe |
|---|---|
| t = 0 | La fiche est rendue, invisible. Une feuille (`--paper`, rayon 2 px, `--shadow-lift`) est posée exactement sur le cadre de la carte. La photo et le post-it reçoivent leur trajet vers leur homologue dans la fiche (translation et échelle, pivot haut gauche), et chaque ruban de la carte le sien, roulé : translation et échelle uniforme (rapport des hauteurs), centré sur son homologue de la carte, sa largeur et sa marge intérieure ramenées aux siennes, ce qui les dépasse coupé, le nom d'une technologie effacé côté carte et entier côté fiche ; un ruban s'apparie par son identité (`data-ribbon`, §4.1), jamais par sa place : une technologie vole vers son ruban de la stack « Technologies », un état vers son ruban de l'en-tête. Un ruban dont l'homologue est replié (§4.3) n'a pas de trajet et disparaît avec la carte. Chaque ruban visé vole par une copie fixe (`[data-flyer]`, `aria-hidden`, même inclinaison), posée sur sa place du moment — hors de vue comprise — que la colonne défilante ne coupe pas ; le ruban lui-même reste caché pendant le vol. Entrée d'historique `/projets/<slug>`. |
| image suivante | La carte se cache d'un coup : photo, post-it, bande, papier et ombre à 0, sans transition ; sa sangle sort d'un coup de la carte et passe à sa copie (fixe, `aria-hidden`, posée sur elle, au-dessus de la feuille et de la photo), qui glisse perpendiculairement à son axe vers le coin haut-gauche jusqu'à quitter la carte (280 ms) ; sa pose revient à 0° (280 ms). Le trombone monte de 14 px (200 ms) en s'effaçant (150 ms). Les autres cartes visibles reculent de 48 px dans la direction opposée à la carte ouverte et s'effacent (280 ms, toutes en même temps) ; les cartes hors de l'écran ne bougent pas (§1.6). |
| image suivante | La photo vole du cadre de la carte au cadre de la galerie (280 ms). La feuille s'étire de la carte au panneau (280 ms, échelle non uniforme). Le post-it vole vers le titre (280 ms). Les rubans volent vers leur homologue, le i-ème de la bande de la carte avec 20 × i ms de retard, à 35 % d'opacité entre 30 % et 70 % du trajet ; les rubans visés de la stack sont seuls visibles dans la colonne, dont la barre de défilement reste transparente pendant le vol. |
| t = 280 ms | La fiche est posée : papier et ombre du panneau, interactions actives. Le reste — bouton fermer, flèches, barre de galerie, post-its de lien, et dans la colonne défilante chaque élément qui ne contient aucun ruban visé — apparaît en 200 ms avec une montée de 8 px, autour des rubans posés. Focus sur « Fermer la fiche ». |

**Fermeture** (bouton, Échap, retour du navigateur, clic hors du panneau).

| Instant | Ce qui se passe |
|---|---|
| t = 0 | Le contenu apparu à la pose s'efface (150 ms) ; les rubans visés restent. |
| t = 150 ms | Le panneau redevient transparent ; la feuille est dessous. La photo, le post-it et les rubans repartent vers la carte (280 ms), chaque ruban visé par sa copie reposée sur sa place du moment, défilée hors de vue comprise ; la copie de la sangle est retirée, la sangle de la carte reste hors d'elle ; la feuille se replie sur le cadre de la carte (280 ms) ; les autres cartes reviennent à leur place en réapparaissant (280 ms). |
| t = 430 ms (+ retard du dernier ruban) | La carte réapparaît d'un coup sous la photo posée, puis sa sangle y glisse perpendiculairement à son axe, depuis le haut au-delà du coin haut-gauche, jusqu'à sa pose (500 ms) ; panneau et feuille sont retirés ; défilement rendu ; focus sur la carte. |

Règles : jamais de fondu croisé entre deux images, la bascule est instantanée ; la photo de la carte et la première image de la galerie sont la même image ; les bascules du thème sont instantanées.

**Arrivée directe** : sans carte d'origine, la fiche apparaît centrée par un fondu de 200 ms et se ferme par un fondu de 150 ms ; à la fermeture, les cartes font leur animation d'entrée (§3.1).

Mouvement réduit : §6.3.

## 5. États

### 5.1 Chargement

Autant de cadres vides que de projets publiés, à la place des cartes et dans la disposition de la table qu'ils annoncent (§5.5) : un cadre seul prend la taille et la piste de la carte seule, centré ; à partir de deux, un cadre double aux dimensions de la carte vitrine puis des simples (§4.1). Le nombre est tenu à la main dans le front et sa mise à jour est facultative : un écart ne casse rien, la table prend sa forme à l'arrivée des cartes. Les cadres sont `aria-hidden` et inertes (aucune réaction au survol, au focus ni au clic), sans post-it ni ruban ; papier, zone image `--line`, une barre `--line` de 40 % × 10 px (rayon 999 px) dans la bande ; pulsation de 1,8 s (opacité jusqu'à 55 %, `--ease-in-out`, infinie). À l'arrivée des données, les cartes les remplacent avec leur animation d'entrée ; sans projet vitrine, le cadre double laisse place à deux cartes simples.

### 5.2 Erreur

Le message d'erreur (§4.5) à la place de la table : « Les projets ne se chargent pas. » et le lien « Réessayer », qui relance le chargement (§5.1) puis affiche la table.

### 5.3 Vide

Rien : l'entête et les liens de l'auteur seuls, table vide, aucun message. Le méta-projet est toujours publié (D3) : ce cas ne se présente pas en production et ne reçoit aucune logique.

### 5.4 Adresse sans projet (`/projets/<slug>`)

Le serveur répond par une redirection `302` vers `/` (ADR 0009) : le visiteur voit l'accueil. Aucune page 404, aucun état dans le front.

### 5.5 Table à 1, 3 et 12 cartes

- **1 carte** : la carte seule (§4.1), centrée ; la carte vitrine n'existe pas à cette taille.
- **3 cartes** : avec un projet vitrine, la double occupe les colonnes 1 et 2 sur deux rangées ; à partir de 1076 px, les deux simples occupent les colonnes 3 et 4 de la première rangée (bloc de 1044 px) ; de 808 à 1075 px, elles s'empilent dans la colonne 3 (776 px) ; de 600 à 807 px, la double prend les deux colonnes et les simples la rangée suivante (508 px). Sans projet vitrine, trois simples en rangée dès 808 px. Mobile : la vitrine sur la première rangée, les deux simples dessous.
- **12 cartes** : quatre colonnes ; avec la vitrine, quinze cellules sur quatre rangées, la dernière de trois cartes ; le remplissage dense ne laisse aucun trou avant la dernière rangée. Mobile : deux colonnes, la vitrine en tête, puis six rangées.

## 6. Responsive, accessibilité, performance

### 6.1 Responsive

Un seul point de rupture, 600 px ; la colonne fixe des liens dépend de la marge à côté de la table, pas de la seule largeur (§3.4).

| | ≥ 600 px | ≤ 599 px |
|---|---|---|
| Entête | marge intérieure 0 24 px | 0 16 px |
| Table | `auto-fit` 240 px, gouttière 28 px, deux à quatre colonnes | deux colonnes `1fr`, gouttière 16 px |
| Carte simple | 240 px | (100 vw − 48 px) / 2 |
| Carte vitrine | 508 px, deux colonnes × deux rangées | 100 vw − 32 px, une rangée |
| Post-it de carte | 16 px (vitrine 20) | 14 px (vitrine 18) |
| Cadre / bande | 10 / 52 px (vitrine 14 / 64) | 8 / 48 px (vitrine 12 / 56) |
| Fiche | panneau centré dimensionné depuis la photo, deux colonnes, en-tête fixe | plein écran, une colonne, tout défile |
| Liens de l'auteur | colonne fixe si la marge ≥ 76 px ou si la table n'a aucune cellule, sinon pied de page | pied de page (marge de 16 px) |
| Survol | sur les appareils à survol | non ; révélation au toucher |

Repères mesurés : 1280 × 800 → table 1044 px, carte 240 / 508 px, fiche 1232 × 642 px, colonne de liens ; 400 × 800 → carte 176 / 368 px, fiche 400 × 800 px, pied de page.

### 6.2 Accessibilité

- **Contrastes** (WCAG, calculés sur les jetons, clair / sombre) : `--ink` sur `--paper` 14,16 / 11,94 ; `--ink` sur `--bg` 12,90 / 14,00 ; `--ink-2` sur `--bg` 5,07 / 6,43 ; `--ink-2` sur `--paper` 5,57 / 5,48 ; `--tape-ink` sur `--tape` 11,36 / 7,62 ; `--postit-ink` sur `--postit` 11,69 / 6,66 ; `--postit-ink` sur `--postit-link` 8,81 / 6,62 ; `--accent` sur `--bg` 4,67 / 6,80 ; `--accent` sur `--paper` 5,13 / 5,80 ; point « en ligne » (`--live`) sur `--tape` 3,68 / 5,35 ; point « en cours » (`--ongoing`) sur `--tape` 3,58 / 3,99 (mesuré le 2026-11-09, #255 ; la teinte de maquette `#C98A12` en clair tomberait à 2,23) (rapport (L1 + 0,05) / (L2 + 0,05) des luminances relatives de WCAG 2.x, calculé le 2026-11-08 sur `#4A7C59` / `#E8DFCF` et `#8FB996` / `#3D372F`, les paires ci-dessus rejouées en témoins). Surfaces translucides, composées sur leur fond réel : bandeau de résumé (`--paper` 94 %) sous `--ink`, sur une image noire 12,39 / 12,29, sur une image blanche 14,17 / 9,94 ; flèches de galerie (`--paper` 88 %) sous `--ink`, sur image noire 10,77 / 12,71, sur image blanche 14,27 / 8,17 ; entête décollée (`--paper` 94 % sur `--bg`) sous `--ink` 14,07 / 12,09 et sous `--ink-2` 5,53 / 5,55. Couche plein écran (§4.4), valeurs sombres dans les deux modes : `--ink` sur `--bg` 14,00, `--ink-2` sur `--bg` 6,43 (en clair, `--ink-2` sur ce fond tomberait à 2,94). Tout texte ≥ 4,5 ; anneau de focus et points « en ligne » et « en cours » ≥ 3 ; `--line` (1,27 / 1,45 sur `--bg`) ne porte que des filets décoratifs.
- **Clavier** : Tab parcourt le nom, la place « Chat » quand elle existe, le bouton de mode, les cartes dans l'ordre de la table, puis les liens de l'auteur ; Entrée ouvre la carte focalisée ; dans la fiche, Tab boucle entre le bouton fermer, les flèches, « Agrandir l'image », les post-its de lien, la colonne de lecture, les rubans-boutons « +N » de la stack quand un groupe replie, et ses sections, ← / → changent d'image, Échap ferme ; le focus revient sur la carte. Dans la couche plein écran (§4.4), Tab boucle entre « Fermer l'image » et les flèches ; à ×1, ← / → changent d'image ; zoomée, ← → ↑ ↓ déplacent l'image ; + / − zooment ; Échap ferme la couche et rend le focus à « Agrandir l'image ». Anneau de focus : 2 px `--accent` à 3 px de l'élément (4 px de la face d'une carte), visible au clavier seulement (`:focus-visible`).
- **Sémantique** : une carte est un lien nommé par son titre et ses états, décrit par son résumé et ses technologies ; un ruban de technologie porte son nom en texte masqué ; « en cours » et « en ligne » sont du texte ; la fiche est un dialogue modal nommé par le titre ; la couche plein écran, un dialogue modal « Image en plein écran » ; la galerie est un groupe « Images du projet » au compteur `aria-live` ; le message d'erreur est un `status` ; les icônes décoratives, la sangle de chantier et les copies volantes des rubans sont `aria-hidden` ; le ruban-bouton de la stack est un `<button>` à `aria-expanded`, `aria-controls` vers sa liste, de nom constant qui contient les deux verbes et le nombre — « Afficher ou réduire les N autres technologies » (ou « outils »), au singulier « Afficher ou réduire 1 autre technologie » (ou « outil ») — pour que ses deux libellés visibles, « +N » et « Réduire », figurent dans son nom (WCAG 2.5.3, #255) ; les rubans repliés sont retirés de l'arbre d'accessibilité ; chaque bouton icône a un libellé ; l'icône de thème inactive est retirée du rendu.
- **Cibles** : boutons et liens icône 36 px (pied de page 38 px), flèches 36 px, « Agrandir l'image » et « Fermer l'image » 36 px, « Ouvrir » 30 px de haut, lien « Réessayer » 24 px (sa ligne de texte) ; 8 px au moins entre deux cibles.
- **Langue** : `lang="fr"` ; libellés et messages en français, dans le catalogue de chaînes (D28, D34), avec l'apostrophe typographique « ’ » dans les textes rendus.
- Mouvement réduit : §6.3.

### 6.3 Mouvement réduit (`prefers-reduced-motion: reduce`)

- Cartes : entrée par fondu de 150 ms sans montée ; ni redressement, ni soulèvement ; bandeau de résumé par fondu seul ; sangle d'un projet « en cours » : fondu croisé de 150 ms (`--ease-out`) entre la pose et le coin, sans glissement ; pas de pulsation des cadres vides.
- Fiche : le ruban-bouton de la stack ne monte pas au survol.
- Ouverture : la face de la carte s'efface (150 ms) pendant que la fiche apparaît (150 ms), sans feuille ni vol ; les autres cartes s'effacent (150 ms) sans reculer ; la fiche est active à 160 ms. Fermeture : contenu en 160 ms, puis fiche en 160 ms, les cartes réapparaissent (150 ms).
- Entête : sortie et retour par fondu de 150 ms, sans translation.
- Galerie : bascule instantanée ; ancre de section : défilement instantané.
- Plein écran : ouverture et fermeture par fondu de 150 ms ; zoom et déplacement sans transition.
- Post-its de lien et liens de l'auteur : pas de montée au survol ; les couleurs transitent encore (150 ms).

### 6.4 Performance

Seuils bloquants : §1.16. Moyens : police unique de 25 Ko incorporée, sans requête vers un service tiers ; images WebP redimensionnées (cadrage §6.7) en `loading="lazy"` ; couverture carrée d'au moins 2400 px (§1.11) ; animations sur `transform` et `opacity` (§2.7) ; entrée des cartes par `IntersectionObserver` ; aucune bibliothèque d'animation chargée pour ce qui précède ; aucune requête externe (§1.14).

## 7. Contraintes de contenu

Base : §1.17. Les capacités ci-dessous sont mesurées sur la carte simple mobile à 400 px de large (176 px) ; ce qui y tient tient partout à partir de cette largeur. Sous 400 px la photo rétrécit : le bandeau de résumé passe à six lignes, puis cinq et quatre, avec une ellipse, le texte complet restant dans la description accessible.

- **Titre** : 30 caractères au plus ; sur le post-it de la carte simple mobile (14 px, 126 px de texte, environ 18 caractères par ligne) il tient sur deux lignes ; sur la fiche (22 px) il tient sur une ligne et laisse la place d'un post-it de lien à sa droite (le second passe à la ligne).
- **Résumé** : 120 caractères au plus, aucun mot de plus de 20 caractères ; sur la carte simple mobile (13 px, 136 px de texte, environ 22 caractères par ligne) il occupe sept lignes au plus, soit 151 px dans une photo de 160 px ; cinq lignes sur la carte simple desktop (14 px, 98 px de haut, remesurés au prototype le 2026-11-08), trois sur la carte seule, deux sur la vitrine. Sert d'`og:description`.
- **Couverture** : carrée, WebP, 2400 px de côté au moins, une par projet ; c'est la photo de la carte, la première image de la galerie et l'`og:image`, servie en variante de 1200 px.
- **Autres images** : format libre, affichées entières dans le carré ; chacune avec une légende de 50 caractères au plus, qui sert de texte alternatif et tient sur la ligne de la barre de galerie à côté du compteur (336 px disponibles à 400 px).
- **Technologies** : au moins une, ordonnées dans l'admin, chacune avec une icône ; les trois premières de type langage / framework / infra vont sur la carte ; toutes vont dans la fiche, les outils dans le groupe « Outils ».
- **Faits** : type parmi Perso, Pro, École ; dates « Depuis <mois année> » pour un projet en cours, « <Mois année> – <mois année> » sinon ; client facultatif ; affichés « Type · Dates · Client ».
- **Statuts** : « en cours » découle du statut du modèle ; « en ligne » découle de la présence d'un lien démo ; un projet sans lien ne porte rien de plus (§1.6).
- **Liens** : démo → « Voir le site », dépôt → « Voir le dépôt », facultatifs, jamais de lien vide.
- **Sections** : autant que l'auteur en crée (cadrage §6.1), dans l'ordre de l'admin ; chacune un titre de 40 caractères au plus, une ancre (lettres sans accent, chiffres, traits d'union ; préremplie depuis le titre, unique dans le projet) et un corps en Markdown (paragraphes et listes) ; une section vide est omise. Sur la fiche mobile de 360 px (`<summary>` de 326 px, titre 15 / 700), un titre courant de 40 caractères tient sur une ligne.
- **Vitrine** : un projet au plus ; l'admin refuse un second.
- **Nombre de projets** : aucune limite ; la table à douze cartes est le cas de référence (§5.5).
