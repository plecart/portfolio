"""Test de fumée de l'image `caddy` : son Caddyfile de production, servi par l'image que
`make build` a chargée (brief de #16, décision 9), et la version de son binaire compilé (ADR 0018).

Lancé par `make image-test`, jamais par `make test` : il lui faut l'image construite, donc le front
compilé. Le job `infra` de la CI le lance après son build ; sur un poste, `make build` d'abord.

La pile (`caddy.yml`) tourne sous son propre nom de projet Compose, sur un port hôte que Docker
attribue : le moteur est partagé avec d'autres piles. Les requêtes partent de l'hôte avec l'en-tête
`Host` que `cloudflared` transmettrait.
"""

import json
import os
import socket
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPException, HTTPMessage
from ipaddress import ip_network
from pathlib import Path
from typing import Any

import pytest
import yaml
from test_infra import image_output, loaded_image, run_bounded

STACK = Path(__file__).with_name("caddy.yml")
# Le Compose de production, dont la sonde de `caddy` s'exécute ici dans l'image.
COMPOSE_PROD = Path(__file__).parents[1] / "compose.yml"
# Un nom par lancement : deux lancements simultanés sur le même moteur — un poste et une relecture,
# deux sessions — ne se partagent ni conteneurs ni réseau, et l'arrêt de l'un n'emporte pas l'autre.
PROJECT = f"portfolio-test-caddy-{uuid.uuid4().hex[:8]}"

# Les noms d'hôte que le Caddyfile reçoit, sous le domaine réservé aux tests (RFC 2606).
HOSTS = {"SITE_HOST": "site.test", "API_HOST": "api.test", "MEDIA_HOST": "media.test"}
SITE, API, MEDIA = HOSTS["SITE_HOST"], HOSTS["API_HOST"], HOSTS["MEDIA_HOST"]

# Le temps laissé à Caddy pour ouvrir son port, une fois son conteneur démarré.
STARTUP_DEADLINE = 10.0

# La coquille de l'application, `#root` d'`index.html` : le corps de l'accueil. L'ouverture seule,
# que suit la paire marquée `root` du gabarit (`apps/api/content/site.py`).
APP_SHELL = '<div id="root">'

# Le cache d'un fichier haché par la compilation : un nom ne désigne jamais qu'un contenu.
IMMUTABLE = "public, max-age=31536000, immutable"

# Les en-têtes de sécurité de l'amont factice — ceux que pose le site, dont Django pose aussi trois,
# sa CSP native comprise (ADR 0020). Ceux du site doivent les remplacer sur `/projets/*`, ceux de
# l'hôte de l'API les laisser : chacun a une autre valeur que celui du site, sauf `nosniff`, dont
# un doublon se verrait au décompte.
UPSTREAM_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'",
    "X-Frame-Options": "SAMEORIGIN",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}

# Ce que répond l'amont factice de `caddy.yml` : son corps, ses en-têtes de sécurité, et le cache
# qu'il pose sur les statiques de l'admin — celui de WhiteNoise, différent de celui de Caddy :
# intact, il prouve que Caddy n'y a pas touché. Il renvoie aussi, sous l'en-tête
# `UPSTREAM_PROTO_ECHO`, le `X-Forwarded-Proto` qu'il a reçu.
UPSTREAM = {
    "UPSTREAM_BODY": "amont",
    "UPSTREAM_SECURITY_HEADERS": "\n".join(
        f'{name} "{value}"' for name, value in UPSTREAM_SECURITY_HEADERS.items()
    ),
    "UPSTREAM_STATIC_CACHE": "max-age=315360000, public, immutable",
    "UPSTREAM_PROTO_ECHO": "X-Amont-Forwarded-Proto",
}

# Les en-têtes de sécurité de l'hôte du site (brief de #16, décision 3 ; PRD « Sécurité ») : la
# politique n'admet que des fichiers servis par le site, les appels à l'API et les images de
# `media` ; ni `data:`, ni `unsafe-inline`.
SITE_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        f"default-src 'self'; connect-src https://{API}; img-src 'self' https://{MEDIA}; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

# Des adresses qu'aucun fichier du front ne porte ni aucune route ne relaie, dont celles qu'un robot
# demande à un site (#265) : `404`, avec le corps d'`index.html` (ADR 0030).
UNSERVED_PATHS = ["/nimporte", "/llms-full.txt", "/index.md", "/.well-known/ai-catalog.json"]

# Ce que l'hôte du site relaie vers `api` (ADR 0030) : les fiches, le plan du site, `llms.txt`.
RELAYED_PATHS = ["/projets/x", "/sitemap.xml", "/llms.txt"]


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
    """La pile démarrée : l'environnement qui la désigne à Compose, le port où Caddy écoute."""

    environment: Mapping[str, str]
    port: int

    def get(self, host: str, path: str, headers: Mapping[str, str] | None = None) -> Reply:
        """Une requête `GET` sur `path`, sous le nom d'hôte `host`.

        Args:
            host: la valeur de l'en-tête `Host`, celle que `cloudflared` transmettrait.
            path: le chemin demandé.
            headers: des en-têtes de plus, comme `cloudflared` en ajoute.

        Returns:
            La réponse, corps lu et décodé — les octets d'une image, qui ne sont pas de l'UTF-8,
            remplacés.
        """
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", path, headers={"Host": host, **(headers or {})})
            response = connection.getresponse()
            return Reply(
                response.status, response.headers, response.read().decode(errors="replace")
            )
        finally:
            connection.close()


def site_security_headers(reply: Reply) -> dict[str, list[str]]:
    """Les en-têtes de sécurité de l'hôte du site dans `reply`, chacun avec toutes ses valeurs —
    un doublon s'y voit —, à comparer à `SECURED`."""
    return {name: reply.headers.get_all(name) or [] for name in SITE_SECURITY_HEADERS}


# Chaque en-tête de sécurité de l'hôte du site, posé une fois.
SECURED = {name: [value] for name, value in SITE_SECURITY_HEADERS.items()}


def compose_command(*arguments: str) -> list[str]:
    """La commande `docker compose` sur la pile du test, sous son nom de projet."""
    return ["docker", "compose", "--project-name", PROJECT, "--file", str(STACK), *arguments]


def compose(*arguments: str, environment: Mapping[str, str]) -> str:
    """Lance `docker compose` sur la pile du test, sous son nom de projet.

    Returns:
        La sortie standard. Une erreur de Compose fait échouer le test, sa sortie d'erreur pour
        message — « No such image » si `make build` n'a pas tourné.
    """
    return run_bounded(compose_command(*arguments), environment=environment).stdout.decode()


def wait_until_serving(stack: Stack, path: str = "/") -> None:
    """Attend que l'hôte du site serve `path` en `200` : le conteneur de Caddy démarre avant son
    serveur, et un `api` redémarré rend `502` tant qu'il n'écoute pas.

    Une connexion TCP ne suffit pas : le port publié est tenu par le proxy de Docker, qui
    l'accepte avant que Caddy n'écoute, puis la coupe.
    """
    deadline = time.monotonic() + STARTUP_DEADLINE
    while True:
        try:
            outcome: object = stack.get(SITE, path).status
        except (OSError, HTTPException) as error:
            outcome = error
        if outcome == 200:
            return
        assert time.monotonic() < deadline, f"{path} n'est pas servi en 200 : {outcome!r}"
        time.sleep(0.2)


def hashed_script(stack: Stack) -> str:
    """Le chemin du script compilé qu'`index.html` charge — un fichier haché par la compilation,
    sous `/assets/`. La page charge aussi `/theme.js` (#18), servi sous son nom, sans empreinte :
    l'ordre des balises ne désigne donc pas le script haché."""
    page = ScriptSources()
    page.feed(stack.get(SITE, "/").body)
    hashed = [source for source in page.sources if source.startswith("/assets/")]
    assert hashed, "aucun `<script src>` sous `/assets/` dans `index.html` — sa forme a changé ?"
    return hashed[0]


@pytest.fixture(scope="module")
def stack() -> Iterator[Stack]:
    """La pile démarrée pour le module, arrêtée et supprimée à la fin, même en cas d'échec."""
    environment = {**os.environ, "CADDY_IMAGE": loaded_image("caddy"), **HOSTS, **UPSTREAM}
    try:
        # Dans le `try` : un démarrage raté laisse un réseau et des conteneurs créés.
        compose("up", "--detach", "--wait", environment=environment)
        published = compose("port", "caddy", "80", environment=environment)
        started = Stack(environment, int(published.strip().rsplit(":", 1)[1]))
        wait_until_serving(started)
        yield started
    finally:
        compose("down", environment=environment)


def test_le_binaire_compile_est_de_la_version_de_l_image_de_base() -> None:
    """Deux épingles d'une même version (ADR 0018) : l'étiquette de l'image de base, que Dependabot
    monte, et l'exigence de l'étage qui compile `caddy`. `CADDY_VERSION`, que l'image de base pose,
    est celle de son étiquette ; le premier mot de `caddy version`, celle que le binaire compilé
    annonce — `unknown` s'il n'est pas compilé sous la forme de sa release, comme dépendance d'un
    module principal (mesuré)."""
    image = loaded_image("caddy")

    compiled = image_output(image, "caddy", "version").split()[0]

    assert compiled == image_output(image, "printenv", "CADDY_VERSION").strip()


def test_l_image_ne_porte_pas_curl() -> None:
    """Le Dockerfile retire `curl` de l'image de base, et `libcurl` avec lui — son commentaire dit
    pourquoi : leurs avis ne concernent plus l'image (CVE-2026-92392). `busybox`, dont la sonde de
    production appelle `wget`, est le témoin que la liste des paquets a bien été lue."""
    installed = image_output(loaded_image("caddy"), "apk", "info").split()

    assert "busybox" in installed
    assert {"curl", "libcurl"}.isdisjoint(installed)


def test_l_accueil_est_servi_sans_cache(stack: Stack) -> None:
    """`index.html` change à chaque compilation et cite les fichiers hachés du moment : servi en
    `no-cache`, il est revalidé à chaque visite, jamais servi périmé."""
    reply = stack.get(SITE, "/")

    assert reply.status == 200
    assert APP_SHELL in reply.body
    assert reply.headers.get_all("Cache-Control") == ["no-cache"]


@pytest.mark.parametrize("path", UNSERVED_PATHS)
def test_une_adresse_sans_fichier_rend_404_avec_le_corps_de_l_accueil(
    stack: Stack, path: str
) -> None:
    """Un robot lit `404`, un humain voit l'accueil, que le front montre à toute adresse (ADR 0030,
    ADR 0009) : le corps d'`index.html`, sans cache comme lui et sous les en-têtes de sécurité du
    site, que la route d'erreur repose."""
    reply = stack.get(SITE, path)

    assert reply.status == 404
    assert APP_SHELL in reply.body
    assert reply.headers.get_all("Cache-Control") == ["no-cache"]
    assert site_security_headers(reply) == SECURED


def test_le_fichier_des_robots_est_servi(stack: Stack) -> None:
    """Un fichier du front à la racine, servi tel quel : `try_files` le trouve."""
    reply = stack.get(SITE, "/robots.txt")

    assert reply.status == 200
    assert reply.body.startswith("User-agent: *")


def test_un_hote_inconnu_ne_recoit_pas_le_site(stack: Stack) -> None:
    """Le site ne répond que sous son nom. Un `SITE_HOST` vide, ou un nom de variable qui aurait
    dérivé entre le Caddyfile et ce qui le démarre, en ferait un site sans nom, servi sous tout
    hôte — mesuré à la relecture de la PR #67, sans qu'aucun autre test ne rougisse."""
    reply = stack.get("inconnu.test", "/")

    assert APP_SHELL not in reply.body


def test_un_fichier_hache_est_servi_immuable(stack: Stack) -> None:
    """Son nom porte une empreinte de son contenu : sous ce nom, il ne change jamais. Mis en cache
    un an sans revalidation, il n'est téléchargé qu'une fois par visiteur et par compilation."""
    reply = stack.get(SITE, hashed_script(stack))

    assert reply.status == 200
    assert reply.headers.get_all("Cache-Control") == [IMMUTABLE]


def test_le_script_de_restauration_du_mode_est_servi_sans_cache(stack: Stack) -> None:
    """`/theme.js` garde son nom d'une compilation à l'autre : marqué immuable, une version
    corrigée n'atteindrait jamais un visiteur déjà passé. Servi en `no-cache`, il est revalidé
    comme `index.html` — le prix accepté par le brief de #18, décision 4."""
    reply = stack.get(SITE, "/theme.js")

    assert reply.status == 200
    assert "localStorage" in reply.body
    assert reply.headers.get_all("Cache-Control") == ["no-cache"]
    # Sous `nosniff`, un autre type ferait refuser le script par le navigateur.
    assert "javascript" in (reply.headers.get("Content-Type") or "")


# Les icônes du site (#237) et les types admis pour chacune.
SITE_ICONS = {
    "/icon.svg": ("image/svg+xml",),
    "/favicon.ico": ("image/vnd.microsoft.icon", "image/x-icon"),
    "/apple-touch-icon.png": ("image/png",),
}


@pytest.mark.parametrize(("path", "types"), SITE_ICONS.items(), ids=SITE_ICONS.keys())
def test_les_icones_du_site_sont_servies_sans_cache(
    stack: Stack, path: str, types: tuple[str, ...]
) -> None:
    """Une icône absente de l'image rendrait 404, le corps d'`index.html` sous son nom. Leurs noms
    sont stables, comme `/theme.js` : revalidées à chaque visite, jamais immuables."""
    reply = stack.get(SITE, path)

    assert reply.status == 200
    assert reply.headers.get("Content-Type") in types
    assert APP_SHELL not in reply.body
    assert reply.headers.get_all("Cache-Control") == ["no-cache"]


def test_un_fichier_hache_absent_rend_404_sans_cache_long(stack: Stack) -> None:
    """Un nom d'une compilation précédente — un visiteur qui garde une page ouverte pendant un
    déploiement — ne rend pas `index.html` : servie sous un nom de script et marquée immuable, la
    page resterait un an dans les caches, du navigateur comme de Cloudflare, à la place du
    script."""
    reply = stack.get(SITE, "/assets/index-absent00.js")

    assert reply.status == 404
    assert APP_SHELL not in reply.body
    assert IMMUTABLE not in (reply.headers.get_all("Cache-Control") or [])


@pytest.mark.parametrize("path", RELAYED_PATHS)
def test_les_fiches_et_les_fichiers_de_decouverte_sont_relayes_vers_api(
    stack: Stack, path: str
) -> None:
    """`/projets/<slug>` est la seule sortie HTML du back : la vue des aperçus de lien (#14, ADR
    0011) y injecte les balises du projet, ou redirige. Le plan du site et `llms.txt` suivent la
    base (ADR 0030). Caddy les relaie au lieu de servir le front."""
    reply = stack.get(SITE, path)

    assert reply.status == 200
    assert reply.body == UPSTREAM["UPSTREAM_BODY"]


def test_une_autre_erreur_que_404_ne_recoit_pas_l_accueil(stack: Stack) -> None:
    """La route d'erreur est bornée au 404 : `api` tombé, une fiche rend le `502` de Caddy, jamais
    `index.html`, qui le masquerait. `api` repart ensuite, pour les tests qui suivent."""
    compose("stop", "api", environment=stack.environment)
    try:
        reply = stack.get(SITE, "/projets/x")
    finally:
        compose("start", "api", environment=stack.environment)
        wait_until_serving(stack, "/projets/x")

    assert reply.status == 502
    assert APP_SHELL not in reply.body


def test_l_hote_de_l_api_est_relaye_vers_api(stack: Stack) -> None:
    """L'API publique et l'admin vivent sur leur propre hôte : tout y part vers `api`."""
    reply = stack.get(API, "/admin/")

    assert reply.status == 200
    assert reply.body == UPSTREAM["UPSTREAM_BODY"]


@pytest.mark.parametrize(
    "path",
    ["/admin%2Flogin/", "/admin%2flogin/", "/admin%2F", "/admin%2f", "/%2Fadmin/", "/x/%2F/admin/"],
)
def test_une_barre_oblique_encodee_n_atteint_pas_api(stack: Stack, path: str) -> None:
    """Access ne couvre pas ces formes, que `gunicorn` décode en chemins de l'admin (#25)."""
    assert stack.get(API, path).status == 400


@pytest.mark.parametrize("path", ["/admin/?next=%2Fadmin%2F", "/admin%252Flogin/"])
def test_seule_une_barre_oblique_encodee_dans_le_chemin_est_refusee(
    stack: Stack, path: str
) -> None:
    """La chaîne de requête passe ; un encodage double se décode une fois, sans route d'admin."""
    assert stack.get(API, path).body == UPSTREAM["UPSTREAM_BODY"]


def test_les_statiques_de_l_admin_gardent_leur_cache(stack: Stack) -> None:
    """`api` sert lui-même les statiques de l'admin, sous `/static/`, avec ses en-têtes de cache
    (WhiteNoise, ADR 0014) : Caddy les relaie sans y toucher."""
    reply = stack.get(API, "/static/admin/css/base.css")

    assert reply.status == 200
    assert reply.headers.get_all("Cache-Control") == [UPSTREAM["UPSTREAM_STATIC_CACHE"]]


def production_probe() -> str:
    """La commande de la sonde de `caddy` dans `infra/compose.yml`, telle que Compose la passe au
    conteneur : `$$`, qui y échappe le `$` destiné au shell du conteneur, rendu à `$`."""
    services = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))["services"]
    kind, command = services["caddy"]["healthcheck"]["test"]
    assert kind == "CMD-SHELL", kind
    return command.replace("$$", "$")


@pytest.mark.parametrize(("site_host", "healthy"), [(SITE, True), ("inconnu.test", False)])
def test_la_sonde_de_production_ne_dit_sain_que_le_site_servi(
    stack: Stack, site_host: str, healthy: bool
) -> None:
    """Le déploiement attend `caddy` sain (`up --wait`) : sa sonde doit lire la page du site sous
    son nom. Le code ne suffit pas — à un hôte qu'aucun bloc ne sert, Caddy rend un 200 vide
    (mesuré à la relecture de la PR #71). Sous un `SITE_HOST` que le Caddyfile ne sert pas, la
    même sonde doit échouer."""
    probed = run_bounded(
        compose_command(
            "exec", "-T", "-e", f"SITE_HOST={site_host}", "caddy", "sh", "-c", production_probe()
        ),
        environment=stack.environment,
        check=False,
    )

    assert (probed.returncode == 0) is healthy, probed.stderr.decode()


# Ce que sert l'hôte du site, sous chacune de ses formes : la page, un fichier haché, une fiche
# relayée vers `api` — dont les en-têtes de Django doivent être remplacés, jamais doublés.
SITE_RESPONSES: dict[str, Callable[[Stack], str]] = {
    "accueil": lambda stack: "/",
    "fichier haché": hashed_script,
    "fiche projet": lambda stack: "/projets/x",
}


@pytest.mark.parametrize("path", SITE_RESPONSES.values(), ids=SITE_RESPONSES.keys())
def test_l_hote_du_site_pose_ses_en_tetes_de_securite(
    stack: Stack, path: Callable[[Stack], str]
) -> None:
    """Une politique par réponse : deux politiques de sécurité s'additionnent, la plus stricte
    l'emporte directive par directive (MDN « Content Security Policy »). Sur `/projets/*`, celle de
    Caddy remplace donc celle de Django au lieu de s'y ajouter (préfixe `>` de `header`)."""
    reply = stack.get(SITE, path(stack))

    assert reply.status == 200
    assert site_security_headers(reply) == SECURED


def test_l_hote_de_l_api_garde_les_en_tetes_de_django(stack: Stack) -> None:
    """L'admin et l'API ont leur propre politique, la CSP native de Django (ADR 0020) : celle du
    site, qui n'admet ni leurs formulaires ni leurs scripts, n'y entre pas."""
    reply = stack.get(API, "/admin/")

    assert {name: reply.headers.get_all(name) for name in UPSTREAM_SECURITY_HEADERS} == {
        name: [value] for name, value in UPSTREAM_SECURITY_HEADERS.items()
    }


@pytest.mark.parametrize("host", [SITE, API])
def test_le_schema_transmis_par_le_reseau_prive_atteint_api(stack: Stack, host: str) -> None:
    """`cloudflared` joint Caddy en HTTP et transmet `X-Forwarded-Proto: https`. Caddy, qui
    réécrit par défaut ces en-têtes d'après sa propre connexion, le garde quand il vient du réseau
    privé : Django y lit que la requête du visiteur était en HTTPS (`SECURE_PROXY_SSL_HEADER`, #6),
    sans quoi sa vérification d'origine du CSRF refuse les envois de l'admin. Les requêtes du test
    arrivent par la passerelle du réseau de Docker, une adresse privée."""
    reply = stack.get(host, "/projets/x", headers={"X-Forwarded-Proto": "https"})

    assert reply.headers.get_all(UPSTREAM["UPSTREAM_PROTO_ECHO"]) == ["https"]


# La préface d'un client HTTP/2 en clair « en connaissance préalable » (RFC 9113 §3.3), et le type
# de la trame SETTINGS (RFC 9113 §6.5), que tout serveur HTTP/2 envoie en premier — au quatrième
# octet de son en-tête de trame.
H2C_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
SETTINGS_FRAME_TYPE = 0x04


# Ce que `file_server` sert sur l'hôte du site, et sous quel statut : un fichier, puis l'`index.html`
# de la route d'erreur.
FILE_SERVER_RESPONSES: dict[str, tuple[Callable[[Stack], str], int]] = {
    "fichier haché": (hashed_script, 200),
    "adresse sans fichier": (lambda stack: "/nimporte", 404),
}


@pytest.mark.parametrize(
    ("path", "status"), FILE_SERVER_RESPONSES.values(), ids=FILE_SERVER_RESPONSES.keys()
)
def test_caddy_ne_sert_aucun_telechargement_partiel(
    stack: Stack, path: Callable[[Stack], str], status: int
) -> None:
    """`Range` est retiré des requêtes de l'hôte du site, et c'est la configuration que visait
    CVE-2026-78667, corrigée depuis dans le Go qui compile `caddy` (ADR 0018) : l'absence de borne
    sur la taille d'un `Range` analysé par un serveur. Le seul analyseur de l'image est
    `file_server`, dans la route d'erreur aussi ; sans cette garde il rendrait une tranche, en 206
    sur un fichier, sous le 404 dans la route d'erreur (mesuré, Caddy 2.11.9). Rien ici n'a besoin
    de téléchargement partiel — le front compilé est servi entier, les médias vivent sur R2."""
    chemin = path(stack)
    entier = stack.get(SITE, chemin)

    tranche = stack.get(SITE, chemin, {"Range": "bytes=0-10"})

    assert entier.status == status, "le montage ne prouve rien si le fichier n'est pas servi"
    assert tranche.status == status, f"206 attendu nulle part : {tranche.status}"
    assert tranche.body == entier.body, "le corps doit être entier, pas une tranche"
    assert "Content-Range" not in tranche.headers


def test_caddy_ne_parle_pas_http2_en_clair(stack: Stack) -> None:
    """`cloudflared` joint Caddy en HTTP/1.1 : HTTP/2 en clair (`h2c`) n'a rien à servir, et c'est
    le serveur HTTP/2 que visait CVE-2026-78669, corrigée par Caddy 2.11.9. Caddy 2.11.4 l'accepte
    pourtant sans qu'on le lui demande — mesuré à la relecture de la PR #67 : sa réponse à la
    préface commence par une trame SETTINGS. Une réponse HTTP/1.1 ou une connexion fermée conviennent."""
    with socket.create_connection(("127.0.0.1", stack.port), timeout=5) as connection:
        connection.sendall(H2C_PREFACE)
        answer = connection.recv(9)

    assert not (len(answer) > 3 and answer[3] == SETTINGS_FRAME_TYPE), answer


# --- La confiance dans les en-têtes transmis : une garde sur la configuration de Caddy -----------

# Le réseau privé, au sens de `private_ranges` de Caddy (doc Caddy, options globales) — où Docker
# place ses réseaux. Pas `ipaddress.is_private`, plus large : il compte les plages de documentation.
PRIVATE_NETWORKS = [
    ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fd00::/8")
] + [ip_network("::1/128")]


def is_private(network: str) -> bool:
    """`network` tient-il tout entier dans le réseau privé ?"""
    candidate = ip_network(network, strict=False)
    return any(
        candidate.network_address in private and candidate.broadcast_address in private
        for private in PRIVATE_NETWORKS
    )


def trust_findings(servers: Mapping[str, Any]) -> list[str]:
    """Ce qui, dans les serveurs d'une configuration JSON de Caddy, croit des `X-Forwarded-*` venus
    d'ailleurs que du réseau privé.

    Returns:
        Un constat si aucun serveur n'est lu, un par serveur sans plage de confiance, un par plage
        qui n'est pas privée. Liste vide : seuls les proxys du réseau privé sont crus.
    """
    if not servers:
        return ["aucun serveur — la forme de la configuration a-t-elle changé ?"]
    findings: list[str] = []
    for name, server in servers.items():
        proxies: dict[str, Any] = server.get("trusted_proxies") or {}
        ranges: list[str] = proxies.get("ranges") or []
        findings += [f"`{name}` ne croit aucun proxy"] if not ranges else []
        findings += [f"`{name}` croit {network}" for network in ranges if not is_private(network)]
    return findings


def trusting(*ranges: str) -> dict[str, Any]:
    """Un serveur de configuration JSON qui croit les proxys de `ranges`."""
    return {"trusted_proxies": {"source": "static", "ranges": list(ranges)}}


# Forme → (serveurs, constat attendu). Le premier cas est ce que `private_ranges` devient.
TRUST_FORMS: dict[str, tuple[dict[str, Any], bool]] = {
    "réseau privé": (
        {
            "srv0": trusting(
                "192.168.0.0/16", "172.16.0.0/12", "10.0.0.0/8", "127.0.0.1/8", "fd00::/8", "::1"
            )
        },
        False,
    ),
    "toute adresse": ({"srv0": trusting("0.0.0.0/0")}, True),
    "une adresse publique de plus": ({"srv0": trusting("10.0.0.0/8", "1.1.1.1/32")}, True),
    "une plage de documentation": ({"srv0": trusting("203.0.113.0/24")}, True),
    "toute adresse IPv6": ({"srv0": trusting("::/0")}, True),
    "aucun proxy cru": ({"srv0": {}}, True),
    "un second serveur sans plage": ({"srv0": trusting("10.0.0.0/8"), "srv1": {}}, True),
    "aucun serveur": ({}, True),
}


@pytest.mark.parametrize(("servers", "expected"), TRUST_FORMS.values(), ids=TRUST_FORMS.keys())
def test_la_garde_de_confiance_rend_son_verdict_sur_chaque_forme(
    servers: dict[str, Any], expected: bool
) -> None:
    """Chaque forme recensée : signalée si, et seulement si, elle croit un proxy hors du réseau
    privé ou n'en croit aucun. La garde se prouve ici, sans affaiblir le Caddyfile du dépôt."""
    assert bool(trust_findings(servers)) is expected, trust_findings(servers)


def adapted_config(stack: Stack) -> dict[str, Any]:
    """La configuration JSON que Caddy tire lui-même du Caddyfile (`caddy adapt`)."""
    return json.loads(
        compose(
            "exec",
            "-T",
            "caddy",
            "caddy",
            "adapt",
            "--config",
            "/etc/caddy/Caddyfile",
            environment=stack.environment,
        )
    )


def test_caddy_ne_fait_confiance_qu_au_reseau_prive(stack: Stack) -> None:
    """Un `X-Forwarded-*` venu d'ailleurs est forgé : seul le réseau privé, où vit `cloudflared`,
    est cru. Lu dans la configuration adaptée."""
    assert trust_findings(adapted_config(stack)["apps"]["http"]["servers"]) == []


def test_caddy_ne_sert_pas_d_autorite_acme(stack: Stack) -> None:
    """Caddy n'analyse une clé JWK venue du réseau que dans son serveur ACME — l'autorité de
    smallstep, que monte le handler `acme_server` —, le code que vise CVE-2026-116587
    (`.trivyignore.yaml`). Aucun dans la configuration adaptée ; `reverse_proxy`, présent sous la
    même forme, est le témoin. Vu rouge le 2026-10-28, `acme_server` ajouté au site."""
    adapted = json.dumps(adapted_config(stack))

    assert '"reverse_proxy"' in adapted
    assert '"acme_server"' not in adapted
