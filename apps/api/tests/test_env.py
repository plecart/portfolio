"""Tests de `Env`, la seule lecture de l'environnement du back."""

from collections.abc import Callable
from pathlib import Path

import pytest
from config.env import Env
from pydantic import ValidationError

# Les variables dont le type impose une forme d'URL. Toute nouvelle adresse de service s'ajoute
# ici : c'est cette liste qui fait du test suivant une garantie de classe, pas d'occurrence.
SERVICE_URLS = ["DATABASE_URL", "REDIS_URL"]

# `test_env.py` → `tests` → `api` → `apps` → racine du dépôt. Calculé ici pour vérifier, depuis
# un autre point de départ, l'arithmétique de chemin que fait `config/env.py`.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Toutes les façons dont `Env` peut rendre son contenu lisible : une trace, un journal, une
# sérialisation. Le secret ne doit apparaître dans aucune. `get_secret_value()` est
# volontairement absent — c'est l'accesseur, son travail est précisément de rendre la valeur.
SECRET_TRAVEL_FORMS: list[tuple[str, Callable[[Env], str]]] = [
    ("repr du modèle", repr),
    ("str du modèle", str),
    ("interpolation", lambda env: f"{env}"),
    ("repr du champ", lambda env: repr(env.SECRET_KEY)),
    ("str du champ", lambda env: str(env.SECRET_KEY)),
    ("model_dump", lambda env: str(env.model_dump())),
    ("model_dump_json", lambda env: env.model_dump_json()),
    ("model_dump en mode json", lambda env: str(env.model_dump(mode="json"))),
]


def build_env(env_file: Path | None = None) -> Env:
    """Construit `Env` en ignorant le `.env` du poste, pour que les tests soient hermétiques.

    Le commentaire `pyright: ignore` est le contournement documenté par `pydantic-settings` :
    les champs sans défaut sont résolus depuis l'environnement, pas depuis l'appel.
    """
    return Env(_env_file=env_file)  # pyright: ignore[reportCallIssue]


def test_le_demarrage_echoue_sans_cle_secrete(environment: pytest.MonkeyPatch) -> None:
    environment.delenv("SECRET_KEY")

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        build_env()


@pytest.mark.parametrize("variable", SERVICE_URLS)
def test_une_adresse_de_service_mal_formee_est_refusee(
    environment: pytest.MonkeyPatch, variable: str
) -> None:
    """Toute adresse de service est refusée mal formée — la liste couvre la classe entière."""
    environment.setenv(variable, "pas-une-url")

    with pytest.raises(ValidationError, match=variable):
        build_env()


def test_le_demarrage_echoue_sans_hote_autorise_hors_debug(
    environment: pytest.MonkeyPatch,
) -> None:
    """Django exige ALLOWED_HOSTS hors debug ; échouer au démarrage vaut mieux qu'à la requête."""
    environment.setenv("ALLOWED_HOSTS", "[]")

    with pytest.raises(ValidationError, match="ALLOWED_HOSTS"):
        build_env()


def test_debug_est_faux_par_defaut(environment: pytest.MonkeyPatch) -> None:
    """Un oubli doit laisser l'application en posture de production, jamais l'inverse."""
    environment.delenv("DEBUG")

    assert build_env().DEBUG is False


def test_un_hote_absent_est_tolere_en_debug(environment: pytest.MonkeyPatch) -> None:
    """Le garde ne doit pas gêner le développement, où Django autorise déjà les hôtes locaux."""
    environment.setenv("DEBUG", "true")
    environment.setenv("ALLOWED_HOSTS", "[]")

    assert build_env().ALLOWED_HOSTS == []


@pytest.mark.parametrize(
    "rendu",
    [rendu for _, rendu in SECRET_TRAVEL_FORMS],
    ids=[nom for nom, _ in SECRET_TRAVEL_FORMS],
)
def test_la_cle_secrete_n_apparait_dans_aucune_forme(
    environment: pytest.MonkeyPatch,
    variables: dict[str, str],
    rendu: Callable[[Env], str],
) -> None:
    """Le masquage se solde sur la classe : 8 formes recensées, 8 éprouvées ici."""
    env = build_env()

    assert variables["SECRET_KEY"] not in rendu(env)


def test_une_cle_secrete_trop_courte_est_refusee(environment: pytest.MonkeyPatch) -> None:
    """Django n'avertit qu'en `check --deploy`, que la CI ne lance pas : on refuse au démarrage."""
    environment.setenv("SECRET_KEY", "trop-courte")

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        build_env()


def test_une_cle_inconnue_dans_le_fichier_env_est_refusee(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Une clé absente de `Env` est une faute de frappe, pas une option : elle doit bloquer."""
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY_TYPO=oups\n", encoding="utf-8")

    # La casse est normalisée par `pydantic-settings` (`case_sensitive=False` par défaut).
    with pytest.raises(ValidationError, match="(?i)SECRET_KEY_TYPO"):
        build_env(env_file)


def test_le_fichier_env_est_cherche_a_la_racine_du_depot() -> None:
    """`manage.py` se lance depuis `apps/api`, pytest depuis la racine : un seul `.env` pour les deux."""
    assert (REPOSITORY_ROOT / "pyproject.toml").exists(), "l'ancre du dépôt a bougé"
    assert Env.model_config.get("env_file") == REPOSITORY_ROOT / ".env"
