"""Test de fumée de l'image `caddy` : son Caddyfile de production, servi par l'image que
`make build` a chargée (brief de #16, décision 9).

Lancé par `make image-test`, jamais par `make test` : il lui faut l'image construite, donc le front
compilé. Le job `infra` de la CI le lance après son build ; sur un poste, `make build` d'abord.

La pile (`caddy.yml`) tourne sous son propre nom de projet Compose, sur un port hôte que Docker
attribue : le moteur est partagé avec d'autres piles. Les requêtes partent de l'hôte avec l'en-tête
`Host` que `cloudflared` transmettrait.
"""

import os
import subprocess
import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPException, HTTPMessage
from pathlib import Path

import pytest
from test_infra import built_images, make_dry_run

STACK = Path(__file__).with_name("caddy.yml")
# Un nom par lancement : deux lancements simultanés sur le même moteur — un poste et une relecture,
# deux sessions — ne se partagent ni conteneurs ni réseau, et l'arrêt de l'un n'emporte pas l'autre.
PROJECT = f"portfolio-test-caddy-{uuid.uuid4().hex[:8]}"

# Les noms d'hôte que le Caddyfile reçoit, sous le domaine réservé aux tests (RFC 2606).
HOSTS = {"SITE_HOST": "site.test"}
SITE = HOSTS["SITE_HOST"]

# Le temps laissé à Caddy pour ouvrir son port, une fois son conteneur démarré.
STARTUP_DEADLINE = 10.0

# La coquille de l'application, que toute route du front doit rendre.
APP_SHELL = '<div id="root"></div>'

# Le cache d'un fichier haché par la compilation : un nom ne désigne jamais qu'un contenu.
IMMUTABLE = "public, max-age=31536000, immutable"


class ScriptSources(HTMLParser):
    """Les `src` des balises `<script>` d'une page, dans l'ordre."""

    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        source = dict(attrs).get("src")
        if tag == "script" and source:
            self.sources.append(source)


@dataclass(frozen=True)
class Reply:
    """Une réponse lue en entier : son statut, ses en-têtes, son corps."""

    status: int
    headers: HTTPMessage
    body: str


@dataclass(frozen=True)
class Stack:
    """La pile démarrée : le port hôte où Caddy écoute."""

    port: int

    def get(self, host: str, path: str) -> Reply:
        """Une requête `GET` sur `path`, sous le nom d'hôte `host`.

        Args:
            host: la valeur de l'en-tête `Host`, celle que `cloudflared` transmettrait.
            path: le chemin demandé.

        Returns:
            La réponse, corps lu et décodé.
        """
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", path, headers={"Host": host})
            response = connection.getresponse()
            return Reply(response.status, response.headers, response.read().decode())
        finally:
            connection.close()


def caddy_image() -> str:
    """Le nom que `make build` donne à l'image `caddy` — celle que le test doit trouver chargée.

    Sous le préfixe de cet appel, s'il en pose un : le `Makefile` exporte `IMAGE_PREFIX`, donc
    `make image-test IMAGE_PREFIX=…` teste l'image que `make build IMAGE_PREFIX=…` a construite.
    """
    prefix = {"IMAGE_PREFIX": os.environ["IMAGE_PREFIX"]} if "IMAGE_PREFIX" in os.environ else {}
    return built_images(make_dry_run("build", environment=prefix))["infra/caddy/Dockerfile"]


def compose(*arguments: str, environment: Mapping[str, str]) -> str:
    """Lance `docker compose` sur la pile du test, sous son nom de projet.

    Returns:
        La sortie standard. Une erreur de Compose fait échouer le test ; sa sortie d'erreur, non
        capturée ici, s'affiche avec l'échec — « No such image » si `make build` n'a pas tourné.
    """
    command = ["docker", "compose", "--project-name", PROJECT, "--file", str(STACK), *arguments]
    return subprocess.run(
        command, env=environment, stdout=subprocess.PIPE, text=True, check=True
    ).stdout


def wait_until_serving(stack: Stack) -> None:
    """Attend la première réponse HTTP de Caddy : son conteneur démarre avant son serveur.

    Une connexion TCP ne suffit pas : le port publié est tenu par le proxy de Docker, qui
    l'accepte avant que Caddy n'écoute, puis la coupe.
    """
    deadline = time.monotonic() + STARTUP_DEADLINE
    while True:
        try:
            stack.get(SITE, "/")
            return
        except (OSError, HTTPException):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


@pytest.fixture(scope="module")
def stack() -> Iterator[Stack]:
    """La pile démarrée pour le module, arrêtée et supprimée à la fin, même en cas d'échec."""
    environment = {**os.environ, "CADDY_IMAGE": caddy_image(), **HOSTS}
    try:
        # Dans le `try` : un démarrage raté laisse un réseau et des conteneurs créés.
        compose("up", "--detach", "--wait", environment=environment)
        published = compose("port", "caddy", "80", environment=environment)
        started = Stack(int(published.strip().rsplit(":", 1)[1]))
        wait_until_serving(started)
        yield started
    finally:
        compose("down", "--volumes", environment=environment)


def test_l_accueil_est_servi_sans_cache(stack: Stack) -> None:
    """`index.html` change à chaque compilation et cite les fichiers hachés du moment : servi en
    `no-cache`, il est revalidé à chaque visite, jamais servi périmé."""
    reply = stack.get(SITE, "/")

    assert reply.status == 200
    assert APP_SHELL in reply.body
    assert reply.headers.get_all("Cache-Control") == ["no-cache"]


def test_une_route_du_front_rend_l_accueil(stack: Stack) -> None:
    """Le front route lui-même (`/projets/<slug>` mis à part, que `api` sert) : un chemin qu'aucun
    fichier ne porte rend `index.html`, sans cache comme lui."""
    reply = stack.get(SITE, "/une/route/du/front")

    assert reply.status == 200
    assert APP_SHELL in reply.body
    assert reply.headers.get_all("Cache-Control") == ["no-cache"]


def hashed_script(stack: Stack) -> str:
    """Le chemin du script compilé qu'`index.html` charge — un fichier haché par la compilation."""
    page = ScriptSources()
    page.feed(stack.get(SITE, "/").body)
    assert page.sources, "aucun `<script src>` dans `index.html` — sa forme a-t-elle changé ?"
    return page.sources[0]


def test_un_fichier_hache_est_servi_immuable(stack: Stack) -> None:
    """Son nom porte une empreinte de son contenu : sous ce nom, il ne change jamais. Mis en cache
    un an sans revalidation, il n'est téléchargé qu'une fois par visiteur et par compilation."""
    reply = stack.get(SITE, hashed_script(stack))

    assert reply.status == 200
    assert reply.headers.get_all("Cache-Control") == [IMMUTABLE]


def test_un_fichier_hache_absent_rend_404_sans_cache_long(stack: Stack) -> None:
    """Un nom d'une compilation précédente — un visiteur qui garde une page ouverte pendant un
    déploiement — ne rend pas `index.html` : servie sous un nom de script et marquée immuable, la
    page resterait un an dans les caches, du navigateur comme de Cloudflare, à la place du script."""
    reply = stack.get(SITE, "/assets/index-absent00.js")

    assert reply.status == 404
    assert APP_SHELL not in reply.body
    assert IMMUTABLE not in (reply.headers.get_all("Cache-Control") or [])
