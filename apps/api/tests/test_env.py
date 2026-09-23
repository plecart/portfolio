"""Tests de `Env`, la seule lecture de l'environnement du back."""

from pathlib import Path

import pytest
from config.env import Env
from pydantic import ValidationError

# Un environnement complet et valide. Chaque test en retire ou en corrompt une seule entrée,
# pour que l'échec attendu ne puisse venir que de celle-là.
ENVIRONNEMENT_VALIDE = {
    "SECRET_KEY": "clé-de-test",
    "DEBUG": "false",
    "ALLOWED_HOSTS": '["portfolio.test"]',
    "DATABASE_URL": "postgresql://portfolio:secret@localhost:5432/portfolio",
    "REDIS_URL": "redis://localhost:6379/0",
}

# Les variables dont le type impose une forme d'URL. Toute nouvelle adresse de service s'ajoute
# ici : c'est cette liste qui fait du test suivant une garantie de classe, pas d'occurrence.
ADRESSES_DE_SERVICE = ["DATABASE_URL", "REDIS_URL"]


def construire(fichier_env: Path | None = None) -> Env:
    """Construit `Env` en ignorant le `.env` du poste, pour que les tests soient hermétiques.

    Le commentaire `pyright: ignore` est le contournement documenté par `pydantic-settings` :
    les champs sans défaut sont résolus depuis l'environnement, pas depuis l'appel.
    """
    return Env(_env_file=fichier_env)  # pyright: ignore[reportCallIssue]


@pytest.fixture
def environnement(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Pose un environnement valide et rend la main pour le corrompre."""
    for nom, valeur in ENVIRONNEMENT_VALIDE.items():
        monkeypatch.setenv(nom, valeur)
    return monkeypatch


def test_le_demarrage_echoue_sans_cle_secrete(
    environnement: pytest.MonkeyPatch,
) -> None:
    environnement.delenv("SECRET_KEY")

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        construire()


@pytest.mark.parametrize("variable", ADRESSES_DE_SERVICE)
def test_une_adresse_de_service_mal_formee_est_refusee(
    environnement: pytest.MonkeyPatch, variable: str
) -> None:
    """Toute adresse de service est refusée mal formée — la liste couvre la classe entière."""
    environnement.setenv(variable, "pas-une-url")

    with pytest.raises(ValidationError, match=variable):
        construire()


def test_le_demarrage_echoue_sans_hote_autorise_hors_debug(
    environnement: pytest.MonkeyPatch,
) -> None:
    """Django rejetterait chaque requête en 400 ; on préfère un démarrage qui échoue franchement."""
    environnement.setenv("ALLOWED_HOSTS", "[]")

    with pytest.raises(ValidationError, match="ALLOWED_HOSTS"):
        construire()


def test_debug_est_faux_par_defaut(environnement: pytest.MonkeyPatch) -> None:
    """Un oubli doit laisser l'application en posture de production, jamais l'inverse."""
    environnement.delenv("DEBUG")

    assert construire().DEBUG is False


def test_un_hote_absent_est_tolere_en_debug(environnement: pytest.MonkeyPatch) -> None:
    """Le garde ne doit pas gêner le développement, où Django autorise déjà les hôtes locaux."""
    environnement.setenv("DEBUG", "true")
    environnement.setenv("ALLOWED_HOSTS", "[]")

    assert construire().ALLOWED_HOSTS == []


def test_la_cle_secrete_n_apparait_pas_dans_une_trace(
    environnement: pytest.MonkeyPatch,
) -> None:
    """Une trace d'exception ou un journal ne doit jamais révéler la clé de signature."""
    env = construire()

    assert ENVIRONNEMENT_VALIDE["SECRET_KEY"] not in repr(env)


def test_une_cle_inconnue_dans_le_fichier_env_est_refusee(
    environnement: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Une clé absente de `Env` est une faute de frappe, pas une option : elle doit bloquer."""
    fichier_env = tmp_path / ".env"
    fichier_env.write_text("SECRET_KEY_TYPO=oups\n", encoding="utf-8")

    # La casse est normalisée par `pydantic-settings` (`case_sensitive=False` par défaut).
    with pytest.raises(ValidationError, match="(?i)SECRET_KEY_TYPO"):
        construire(fichier_env)
