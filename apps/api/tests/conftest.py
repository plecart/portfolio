"""Fixtures communes aux tests de `apps/api`."""

import pytest

# Un environnement complet et valide. Chaque test en retire ou en corrompt une seule entrée,
# pour que l'échec attendu ne puisse venir que de celle-là.
VALID_ENVIRONMENT = {
    # Sans accent, et au-dessus du seuil de 50 caractères exigé par `Env`.
    "SECRET_KEY": "cle-de-test-sans-valeur-reelle-uniquement-pour-les-tests",
    "DEBUG": "false",
    "ALLOWED_HOSTS": '["portfolio.test"]',
    "DATABASE_URL": "postgresql://portfolio:secret@localhost:5432/portfolio",
    "REDIS_URL": "redis://localhost:6379/0",
    # Relatif à dessein : c'est la forme que `.env.example` propose, donc celle que la plupart
    # des clones porteront, et la seule qui éprouve l'ancrage sur la racine du dépôt.
    "MEDIA_ROOT": "fichiers-de-test",
}


@pytest.fixture
def variables() -> dict[str, str]:
    """L'environnement valide, sous forme de dictionnaire — pour un sous-processus."""
    return dict(VALID_ENVIRONMENT)


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, variables: dict[str, str]) -> pytest.MonkeyPatch:
    """Pose l'environnement valide dans ce processus et rend la main pour le corrompre."""
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    return monkeypatch
