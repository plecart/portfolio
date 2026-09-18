# 0003 — Cloudflare en bordure et domaine `pacome.dev`

- **Statut** : accepté
- **Date** : 2026-09-18
- **Décisions du cadrage** : D23, D36, D37, D41 (`docs/cadrage-technique.md` §7)

## Contexte

Le site est public dès la phase 1 ; un chatbot (phase 2) et un serveur MCP (phase 3) s'y ajoutent,
exposés au public avec l'exigence P5 « sécurité maximale sur les surfaces publiques ». L'admin
Django ne doit pas être atteignable sans authentification préalable. Le VPS (ADR 0002) est une
machine unique dont l'adresse IP ne devrait pas être connue. Le projet n'avait aucun nom de
domaine.

## Facteurs de décision

- Coût nul ou presque.
- Couche de sécurité crédible devant un VPS unique : WAF, DDoS, rate limiting, accès à l'admin.
- Masquage de l'IP d'origine.
- Un seul fournisseur pour le domaine, le DNS et le bord, pour limiter les comptes.
- Compromis de confidentialité à expliquer dans la page de confidentialité.

## Options considérées

1. **Cloudflare, offre gratuite, devant le VPS.**
2. **Sans Cloudflare** : Caddy pour le TLS, `fail2ban` et pare-feu, rate limiting applicatif
   seul, admin derrière Tailscale ou une liste d'adresses IP.

## Décision

**Cloudflare (offre gratuite) en bordure**, avec les fonctions suivantes :

| Fonction | Usage |
|---|---|
| Registrar | Achat de `pacome.dev` à prix coûtant |
| DNS | Zone du domaine |
| Proxy | Masque l'IP du VPS ; TLS au bord |
| CDN | Cache des fichiers statiques et des images |
| WAF et protection DDoS | Fournis par l'offre, sans implémentation |
| Rate limiting | Règles au bord, en complément des compteurs applicatifs (ADR 0006) |
| Access | Authentification par identité Google ou GitHub avant d'atteindre l'admin ; le formulaire de connexion Django n'est jamais exposé |
| Turnstile | Captcha invisible, **optionnel** (D41) : hors phase 1 ; en phase 2 seulement si des abus sont constatés |
| R2 | Stockage objet (ADR 0004) |

**Domaine** : `pacome.dev` (D36, D37), acheté chez Cloudflare Registrar avant le premier
déploiement, tarif à vérifier (un nom court en `.dev` peut être vendu au tarif premium). L'extension
`.dev` est sur la liste HSTS préchargée : HTTPS obligatoire par construction. Sous-domaines : `www`
(ou apex) pour le site, `api` pour l'API et l'admin, `media` pour R2, `mcp` pour le serveur MCP.

**La configuration Cloudflare est un état** (DNS, Access, règles) : documentée dans le runbook au
minimum ; Terraform avec le provider Cloudflare en option, comme brique « infrastructure as code »
démontrable (ADR 0007, point 7).

## Conséquences

**Positives**

- Coût nul. WAF, DDoS, CDN et Access sans rien exploiter.
- L'admin n'est atteignable qu'après une authentification externe, avant même le mot de passe
  Django et la 2FA.
- L'IP du VPS n'apparaît nulle part.

**Négatives, assumées**

- Dépendance à un tiers américain qui voit le trafic en clair au bord (TLS terminé chez lui). Dit
  dans la page de confidentialité, avec les autres sous-traitants.
- Effet « boîte noire » si l'on ne comprend pas ce que chaque fonction fait : chaque règle activée
  est documentée dans le runbook.
- Le masquage de l'IP n'a de valeur que si le VPS n'accepte le trafic HTTP que depuis les plages
  d'adresses Cloudflare : à appliquer dans le pare-feu (`infra/`).

## Comparaison des options

| | Cloudflare | Sans Cloudflare |
|---|---|---|
| WAF, DDoS | Fournis | Absents |
| Protection de l'admin | Access (identité externe) | Tailscale ou liste d'IP |
| CDN | Oui | Non |
| IP d'origine | Masquée | Visible |
| Confidentialité | Trafic vu par un tiers au bord | Rien ne sort |
| Coût | 0 | 0 |
| Exploitation | Une console de plus | Tout sur le VPS |

**Nom de domaine** : candidats vérifiés le 2026-09-11 (RDAP) : `pacome.dev`, `pacomebernier.dev`,
`pacomebernier.fr`, `pacomebernier.com`, `pacome-bernier.dev`, `pbernier.dev` disponibles ;
`pacome.fr` et `bernier.dev` pris. `.fr` n'est pas vendu par Cloudflare Registrar (il faudrait OVH
ou Gandi avec les DNS chez Cloudflare). Retenu `pacome.dev` : court, se dicte sans tiret, identité
de développeur ; repli `pacomebernier.dev` si le tarif est premium.

## Conditions de réexamen

- Des abus constatés sur le chat ou le MCP activent Turnstile (D41), sans nouvel ADR.
- Une exigence de confidentialité incompatible avec un TLS terminé chez un tiers ferait basculer
  vers l'option 2.
