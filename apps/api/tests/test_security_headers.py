"""Tests des en-têtes de sécurité de Django : la CSP native (ADR 0020) et ceux de
`SecurityMiddleware`, lus sur les réponses réelles de l'admin.

La page de connexion suffit à les lire : anonyme, elle ne touche pas la base. Que chaque écran de
l'admin s'ouvre sous cette CSP, nonces des balises compris, `test_admin_access.py` le vérifie ; que
l'hôte des médias n'y entre que sous R2, `test_django_project.py`, dans un processus neuf.
"""

import re

import pytest
from django.http.response import HttpResponseBase
from django.test import Client, RequestFactory
from django.utils.csp import CSP

LOGIN = "/admin/login/"

# Le nonce d'une source de la CSP, et celui d'une balise de la page.
NONCE_SOURCE = re.compile(r"'nonce-([^']+)'")
NONCE_ATTRIBUTE = re.compile(r'nonce="([^"]+)"')
# Une balise ouvrante `<script>` ou `<style>`, sur plusieurs lignes au besoin.
SCRIPT_OR_STYLE = re.compile(r"<(?:script|style)\b[^>]*>")
# Ce que la même CSP refuse sans nonce possible : un attribut `style=`, un gestionnaire `on…=`, une
# adresse `javascript:`.
INLINE_CODE = re.compile(
    r"""[\s"'/](?:style|on[a-z]+)\s*=|=\s*["']?\s*javascript:""", re.IGNORECASE
)

# La politique de l'admin, directive par directive, le nonce de la requête masqué : scripts et
# styles du projet ou de la page, par nonce ; aucun `unsafe-inline`, aucune source tierce — sous le
# disque de la suite, `img-src` n'a pas l'hôte des médias. Sans `connect-src`, la requête de
# l'aperçu Markdown vers l'admin retombe sur `default-src`.
MASKED_NONCE = "'nonce-…'"
POLICY = {
    "default-src": {"'self'"},
    "script-src": {"'self'", MASKED_NONCE},
    "style-src": {"'self'", MASKED_NONCE},
    "img-src": {"'self'"},
    "object-src": {"'none'"},
    "base-uri": {"'self'"},
    "form-action": {"'self'"},
    "frame-ancestors": {"'none'"},
}

# Ceux que `SecurityMiddleware` pose de lui-même, aux défauts de Django.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def directives(response: HttpResponseBase) -> dict[str, set[str]]:
    """La CSP de `response`, directive par directive, son nonce masqué."""
    policy = NONCE_SOURCE.sub(MASKED_NONCE, response[CSP.HEADER_ENFORCE])
    return {name: set(sources) for name, *sources in (part.split() for part in policy.split(";"))}


def header_nonces(response: HttpResponseBase) -> set[str]:
    """Les nonces qu'autorise la CSP de `response` : un seul, en `script-src` comme en
    `style-src`."""
    return set(NONCE_SOURCE.findall(response[CSP.HEADER_ENFORCE]))


def tag_nonces(page: str) -> set[str | None]:
    """Le nonce de chaque balise `<script>` et `<style>` de `page` ; `None` pour une balise qui
    n'en porte pas."""
    return {
        found.group(1) if (found := NONCE_ATTRIBUTE.search(tag)) else None
        for tag in SCRIPT_OR_STYLE.findall(page)
    }


def test_l_admin_pose_une_csp_stricte(client: Client) -> None:
    assert directives(client.get(LOGIN)) == POLICY


def test_le_nonce_change_a_chaque_requete(client: Client) -> None:
    """Deviné ou rejoué, un nonce n'ouvrirait plus rien : chaque réponse a le sien."""
    assert header_nonces(client.get(LOGIN)) != header_nonces(client.get(LOGIN))


def test_security_middleware_pose_ses_en_tetes(client: Client) -> None:
    response = client.get(LOGIN)

    assert {name: response.get(name) for name in SECURITY_HEADERS} == SECURITY_HEADERS


@pytest.mark.parametrize(
    ("headers", "secure"),
    [({"x-forwarded-proto": "https"}, True), ({}, False)],
    ids=["relayée en https", "sans en-tête"],
)
def test_django_lit_le_schema_que_caddy_transmet(headers: dict[str, str], secure: bool) -> None:
    """Derrière `cloudflared` et Caddy, qui ne transmet `X-Forwarded-Proto` que depuis le réseau
    privé (`infra/caddy/Caddyfile`) : sans cette lecture, Django voit `http`, et sa vérification
    d'origine du CSRF refuse tout envoi de formulaire de l'admin servi en `https`."""
    assert RequestFactory().get("/", headers=headers).is_secure() is secure
