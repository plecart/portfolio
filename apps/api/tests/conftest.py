"""Fixtures communes aux tests de `apps/api`."""

import shutil
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from config.celery import app as celery_app
from config.database import database_settings
from containers import postgres, running
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, override_settings
from process_environment import VALID_ENVIRONMENT
from pydantic import PostgresDsn, TypeAdapter

# Ce module se charge aussi sans réglages (`test_sans_reglages_chaque_test_echoue`), et un modèle
# ne s'importe qu'avec eux : les fixtures qui en demandent un l'importent elles-mêmes.
if TYPE_CHECKING:
    from django.contrib.auth.models import User

UNCONFIGURED = (
    "Django n'est pas configuré pour les tests : le greffon `process_environment`, chargé par "
    "l'`addopts` de `pyproject.toml`, pose `DJANGO_SETTINGS_MODULE`."
)


def require_settings() -> None:
    """Fait échouer le test d'emblée, en disant pourquoi, si Django n'est pas configuré.

    Passer par la fixture `settings` de pytest-django **sauterait** le test — et avec lui toute
    la suite, puisque les fixtures automatiques d'ici s'y appuieraient : verte sans rien avoir
    vérifié. `override_settings` seul le laisserait tourner sur des réglages vides, et
    n'échouerait qu'au démontage, sans dire pourquoi (mesuré).
    """
    if not settings.configured:
        pytest.fail(UNCONFIGURED, pytrace=False)


@pytest.fixture(scope="module")
def bash_de_ce_systeme() -> str:
    """Le `bash` du `PATH`, par `shutil.which` (doc `subprocess`, avertissement de `Popen`), s'il lit
    les chemins de ce système ; sinon, le test qui le prend est sauté.

    Sous Windows, le test ne prend qu'un `bash` MSYS, dont `uname -s` commence par `MINGW` ou
    `MSYS` (les deux mesurés sous Git Bash, selon `MSYSTEM`). Celui de WSL — le lanceur de
    `System32` comme l'alias de `WindowsApps`, tous deux sur le poste — rend `Linux`, et la commande
    y échoue : mesuré le 2026-10-26, 37 cas sur 37 sur « unexpected EOF while looking for
    matching » avec un `PATH` de shell Windows où `shutil.which` le trouve d'abord. Un `"bash"` nu,
    résolu par `CreateProcess`, le trouve même sous Git Bash. Ailleurs — en CI Linux, le test
    tourne — le `bash` du `PATH` sert tel quel.
    """
    bash = shutil.which("bash")
    if bash is not None and sys.platform == "win32":
        uname = subprocess.run(
            [bash, "-c", "uname -s"], capture_output=True, text=True, check=False
        )
        if not uname.stdout.startswith(("MINGW", "MSYS")):
            bash = None
    if bash is None:
        pytest.skip("pas de `bash` POSIX (absent, ou celui de WSL) : le test ne se joue pas ici")
    return bash


@pytest.fixture
def variables() -> dict[str, str]:
    """L'environnement valide, sous forme de dictionnaire — pour un sous-processus."""
    return dict(VALID_ENVIRONMENT)


@pytest.fixture(autouse=True)
def media_root(tmp_path: Path) -> Generator[None]:
    """Les fichiers qu'un test enregistre vont dans son dossier temporaire, jamais dans le dépôt.

    Le `MEDIA_ROOT` du processus de test est relatif à la racine du dépôt (`process_environment`) :
    sans ce dossier, une icône enregistrée par un test y atterrirait. Automatique, pour qu'aucun
    test ne puisse l'oublier.
    """
    require_settings()
    with override_settings(MEDIA_ROOT=tmp_path):
        yield


@pytest.fixture(scope="session", autouse=True)
def collected_static_files(tmp_path_factory: pytest.TempPathFactory) -> Generator[None]:
    """Collecte les fichiers statiques une fois pour la session, comme le build de l'image.

    Le stockage à manifeste refuse de rendre une page qui cite un fichier absent de sa collecte
    (ADR 0014) : la suite rend l'admin sur ce même stockage, et un fichier statique manquant y
    échoue comme il échouerait en production. La collecte va dans un dossier temporaire, jamais
    dans le dépôt.
    """
    require_settings()
    with override_settings(STATIC_ROOT=tmp_path_factory.mktemp("static")):
        call_command("collectstatic", interactive=False, verbosity=0)
        yield


@pytest.fixture(scope="session", autouse=True)
def synchronous_tasks() -> None:
    """Les tâches Celery s'exécutent dans le processus de test, à l'enfilement, et leur exception
    en sort : la suite n'a besoin d'aucun Redis (ADR 0015, « Tests »).

    Posé ici sur l'application, jamais par une branche des réglages : la configuration de
    production vient d'`Env`, sans « si test » (brief de #12, décision 12). Le mode synchrone est
    une émulation — la doc Celery le dit « by definition not suitable for unit tests » : il ne
    prouve rien du worker, que la fumée sur la pile complète éprouve (#26).
    """
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)


@pytest.fixture(scope="session", autouse=True)
def memory_cache() -> Generator[None]:
    """Le cache du processus de test est en mémoire, à la durée de vie de celui de la production
    (`TIMEOUT`) : la suite n'a besoin d'aucun Redis (ADR 0015, « Tests » ; brief de #11,
    décision 1).

    Posé ici, jamais par une branche des réglages, comme le mode synchrone de Celery : la
    production reste sur Redis, et `test_cache.py` éprouve le vrai client sur une adresse
    injoignable.
    """
    require_settings()
    timeout = settings.CACHES["default"]["TIMEOUT"]
    memory = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "TIMEOUT": timeout}
    with override_settings(CACHES={"default": memory}):
        yield


@pytest.fixture(autouse=True)
def empty_cache() -> None:
    """Chaque test part d'un cache vide : le cache en mémoire survit d'un test à l'autre."""
    cache.clear()


@pytest.fixture
def admin_client(admin_user: "User") -> Client:
    """Le client de pytest-django, connecté en superutilisateur et vérifié par un second facteur.

    Remplace la fixture du même nom de pytest-django : l'admin (`OTPAdminSite`, `config/apps.py`)
    ne sert aucune page à un compte qu'aucun appareil n'a vérifié. Un seul point pour tous les
    tests de l'admin. La vérification est celle que `django_otp.login` pose dans la session à la
    connexion — l'identifiant d'un appareil confirmé du compte —, sans passer par le formulaire,
    que `test_admin_access.py` éprouve.
    """
    from django_otp import DEVICE_ID_SESSION_KEY  # pyright: ignore[reportMissingTypeStubs]
    from django_otp.plugins.otp_totp.models import (  # pyright: ignore[reportMissingTypeStubs]
        TOTPDevice,
    )

    client = Client()
    client.force_login(admin_user)
    device = TOTPDevice(user=admin_user, name="test")
    device.save()
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
    return client


@pytest.fixture(scope="session")
def django_db_modify_db_settings() -> Generator[None]:
    """Pointe la base de test sur un Postgres démarré pour la session.

    Point d'extension que pytest-django documente pour déplacer la base de test : son
    `django_db_setup` en dépend, puis crée la base de test et joue les migrations. Le conteneur ne
    démarre donc que si un test touche la base, et s'arrête après la suppression de la base de
    test.

    L'adresse du conteneur passe par `database_settings`, la traduction qu'emprunte
    `DATABASE_URL` en production. Le dictionnaire est mis à jour en place : les connexions de
    Django en gardent une référence.
    """
    with running(postgres) as server:
        url = TypeAdapter(PostgresDsn).validate_python(server.get_connection_url())
        settings.DATABASES["default"].update(database_settings(url))
        yield
