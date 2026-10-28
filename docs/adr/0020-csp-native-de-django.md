# 0020 — CSP et en-têtes de sécurité par la brique native de Django

- **Statut** : accepté
- **Date** : 2026-10-28
- **Décisions du cadrage** : D65 (`docs/cadrage-technique.md` §7) ; remplace le point « CSP et
  en-têtes de sécurité | `django-csp` » de l'ADR 0001 (§ Bibliothèques retenues autour de Django),
  qui reste accepté pour tout le reste

## Contexte

L'ADR 0001 confiait la CSP de l'admin et ses en-têtes de sécurité à `django-csp`, choisi le
2026-09-18 (cadrage §6.6, « CSP stricte »). Django 6 a depuis sa propre CSP : le réglage
`SECURE_CSP`, `ContentSecurityPolicyMiddleware` et le processeur de contexte `csp`. Le projet est
en Django 6.1.2.

Les gabarits de l'admin de 6.1.2 posent leurs nonces par `{% csp_nonce_attr %}`, qui lit celui du
processeur de contexte natif — le nonce que `ContentSecurityPolicyMiddleware` pose sur chaque
requête (`django/middleware/csp.py`, `django/template/context_processors.py`). Avec `django-csp`,
le `<style>` en ligne de `change_list.html` et les scripts que les écrans déclarent — ceux du
projet compris, comme celui de l'aperçu Markdown (#8) — resteraient sans nonce : refusés, ou admis
par `unsafe-inline`, que la politique exclut (constat du briefing de #6, 2026-10-28).

## Facteurs de décision

- P5 sécurité par défaut sur l'admin, seule surface d'écriture de la phase 1 : une CSP sans
  `unsafe-inline`, que l'admin respecte sans retouche de ses gabarits.
- P4 / D27 code minimal : une dépendance de moins, pour ce que le framework fournit.
- Les en-têtes que `django-csp` ne posait pas restent à `SecurityMiddleware`, natif aussi.

## Options considérées

1. **`django-csp`**, comme l'ADR 0001 le prévoyait.
2. **La CSP native de Django** : `SECURE_CSP`, `ContentSecurityPolicyMiddleware`, processeur de
   contexte `csp`.

## Décision

**Option 2.** La politique (`apps/api/config/settings.py`) : `default-src 'self'` ; scripts et
styles de l'origine ou sous le nonce de la requête ; `img-src` sur l'origine, plus l'hôte des
médias sous R2 (ADR 0004), où pointent les aperçus d'images de l'admin — seule source tierce ;
`object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`. Aucun
`unsafe-inline`. La requête de l'aperçu Markdown vers l'admin, sur la même origine, retombe sur
`default-src`.

`SecurityMiddleware` pose `X-Content-Type-Options`, `Referrer-Policy` et
`Cross-Origin-Opener-Policy`, aux défauts de Django. Ni redirection vers HTTPS ni HSTS : `.dev` est
en HSTS préchargé (ADR 0003), et Caddy ne pose pas non plus ce dernier.

## Conséquences

**Positives**

- Les gabarits de l'admin et les écrans du projet sont servis sous la politique stricte sans
  aucune retouche : chaque balise `<script>` et `<style>` porte le nonce de l'en-tête (test de
  fumée par écran, `apps/api/tests/test_admin_access.py`).
- Une dépendance de moins.
- Les pages d'erreur de développement de Django s'exemptent elles-mêmes de la politique
  (`csp_override({})`, `django/views/debug.py`).

**Négatives, assumées**

- Un script ou un style en ligne écrit à la main sans `{% csp_nonce_attr %}` est refusé : chaque
  écran neuf passe par les gabarits de l'admin, ou pose ce nonce.

## Comparaison des options

| | `django-csp` | CSP native |
|---|---|---|
| Nonce lu par les gabarits de l'admin 6.1 | non | oui |
| `<style>` en ligne de `change_list.html` | refusé, ou `unsafe-inline` | admis par nonce |
| Dépendance | une de plus | aucune |
| Verdict | Écartée | **Retenue** |
