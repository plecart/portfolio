"""Tests des fichiers statiques de l'admin : collectés, versionnés, servis par WhiteNoise.

En production, `api` sert lui-même les statiques de l'admin (ADR 0014) : `collectstatic` les copie
au build dans `STATIC_ROOT`, chaque nom portant l'empreinte de son contenu, et WhiteNoise les sert
compressés. La suite rend l'admin sur ce même stockage, à partir de la collecte que la fixture
`collected_static_files` (`conftest.py`) fait une fois par session.
"""

import re
from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse
from django.test import Client
from django.urls import reverse

WHITENOISE = "whitenoise.middleware.WhiteNoiseMiddleware"
SECURITY = "django.middleware.security.SecurityMiddleware"
RUNSERVER_NOSTATIC = "whitenoise.runserver_nostatic"
# `django.contrib.staticfiles`, par sa configuration propre au projet (`config/apps.py`).
STATICFILES = "config.apps.StaticFilesConfig"

# Une empreinte de manifeste : douze chiffres hexadécimaux entre le nom et l'extension.
VERSIONED_STYLESHEET = r"admin/css/base\.[0-9a-f]{12}\.css"
# Les deux premiers octets de tout contenu gzip (RFC 1952, « Member format »).
GZIP_MAGIC = b"\x1f\x8b"


def test_whitenoise_ouvre_la_chaine_des_middlewares() -> None:
    """Juste après `SecurityMiddleware` s'il existe, sinon en tête (doc WhiteNoise, « Enable
    WhiteNoise »).

    `SecurityMiddleware` passe d'abord pour que ses en-têtes couvrent aussi les fichiers
    statiques ; WhiteNoise avant tous les autres, pour qu'une requête de fichier s'arrête là, sans
    ouvrir de session ni lire l'utilisateur. `SecurityMiddleware` arrive avec #6 : ce test tient
    l'ordre qu'il devra respecter.
    """
    middleware = list(settings.MIDDLEWARE)

    assert WHITENOISE in middleware
    expected = middleware.index(SECURITY) + 1 if SECURITY in middleware else 0
    assert middleware.index(WHITENOISE) == expected


def test_runserver_nostatic_precede_staticfiles() -> None:
    """Sinon, `runserver` sert lui-même les statiques et WhiteNoise n'agit qu'en production.

    Django retient la commande de l'application listée la première : `runserver_nostatic` doit
    donc précéder `staticfiles`, dont il remplace le `runserver`.
    """
    apps = list(settings.INSTALLED_APPS)

    assert RUNSERVER_NOSTATIC in apps
    assert apps.index(RUNSERVER_NOSTATIC) < apps.index(STATICFILES)


def test_les_statiques_sont_servis_versionnes_et_compresses(client: Client) -> None:
    """Le parcours de production : la page cite un nom versionné, WhiteNoise le sert compressé.

    Un nom versionné change avec son contenu : le navigateur peut le garder indéfiniment
    (`immutable`), et une nouvelle version n'attend aucune expiration de cache.
    """
    page = client.get(reverse("admin:login")).content.decode()
    stylesheet = re.search(
        rf'href="({re.escape(settings.STATIC_URL)}{VERSIONED_STYLESHEET})"', page
    )
    assert stylesheet, "la feuille de style de l'admin n'est pas versionnée — manifeste absent ?"

    response = client.get(stylesheet.group(1), headers={"accept-encoding": "gzip"})
    assert isinstance(response, StreamingHttpResponse), "le fichier n'est pas servi par WhiteNoise"
    # Lire le corps referme le fichier servi, sans le signal de fin de requête qui toucherait la
    # base — ce test n'y a pas droit.
    body = response.getvalue()

    assert response.status_code == 200
    assert response.headers.get("Content-Encoding") == "gzip"
    assert body.startswith(GZIP_MAGIC)
    assert "immutable" in response.headers["Cache-Control"]


def test_la_collecte_laisse_les_docs_interactives_de_django_ninja() -> None:
    """`ninja` n'est installé que pour sa commande d'export du schéma (brief de #10, décision 10) :
    les fichiers de ses docs interactives, désactivées — près de 8 Mo de scripts Swagger et ReDoc
    —, n'entrent pas dans la collecte, donc pas dans l'image. Lu dans la collecte de la session
    (`collected_static_files`), celle de l'admin à côté pour témoin."""
    collected = Path(settings.STATIC_ROOT)

    assert (collected / "admin").is_dir()
    assert not (collected / "ninja").exists()
