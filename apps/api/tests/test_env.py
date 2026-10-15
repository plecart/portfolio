"""Tests de `Env`, la seule lecture de l'environnement du back."""

import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from config.env import ConfigurationError, Env, env_file_path
from pydantic import ValidationError

# Les variables dont le type impose une forme d'URL. Toute nouvelle adresse de service s'ajoute
# ici : c'est cette liste qui fait du test suivant une garantie de classe, pas d'occurrence.
SERVICE_URLS = ["DATABASE_URL", "REDIS_URL"]

# Les variables dont la valeur est un chemin. Même rôle que la liste ci-dessus : c'est elle qui
# fait des deux tests d'ancrage une garantie de classe. Tout champ `Path` ajouté à `Env` s'y
# inscrit, sans quoi son ancrage n'est garanti par rien.
PATH_VARIABLES = ["MEDIA_ROOT"]

# `test_env.py` → `tests` → `api` → `apps` → racine du dépôt. Calculé ici pour vérifier, depuis
# un autre point de départ, l'arithmétique de chemin que fait `config/env.py`.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Les deux fichiers d'environnement du projet, et la frontière entre eux (interrogatoire du
# 2026-09-24). `.env.example` est le modèle de `.env`, que lit `Env` ; `infra/dev.env` porte ce
# que Compose seul connaît. `Env` refuse une clé inconnue *dans son fichier*, mais pas dans
# l'environnement du processus — donc pas dans le conteneur, où Compose injecte `.env` variable
# par variable. Ces deux tests sont la seule chose qui tienne la frontière sur les deux chemins.
ENV_EXAMPLE = REPOSITORY_ROOT / ".env.example"
COMPOSE_ENV = REPOSITORY_ROOT / "infra" / "dev.env"

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

# Les façons de rendre la configuration invalide — **cinq mécanismes de refus distincts**,
# et c'est le dénombrement qui compte : borne de longueur, URL mal formée (deux fois, car deux
# champs la portent), validateur de modèle qui reçoit l'environnement **entier**, validateur de
# champ qui reçoit la liste entière des origines, et échec de lecture d'une *source* avant même
# la validation (deux fois, car deux champs sont des listes). Le dernier ne lève pas le même type
# d'exception que les autres : c'est précisément pourquoi il doit figurer ici.
INVALID_CONFIGURATIONS = [
    ("clé trop courte", "SECRET_KEY", "TROP-COURTE-ET-SECRETE"),
    ("base mal formée", "DATABASE_URL", "postgres://admin:MOT-DE-PASSE-BASE@"),
    ("redis mal formé", "REDIS_URL", "redis://admin:MOT-DE-PASSE-REDIS@"),
    ("aucun hôte autorisé", "ALLOWED_HOSTS", "[]"),
    ("liste mal formée", "ALLOWED_HOSTS", "[oups"),
    ("origine avec chemin", "CORS_ALLOWED_ORIGINS", '["http://SITE-SECRET.test/chemin"]'),
    ("origine sans schéma", "CORS_ALLOWED_ORIGINS", '["//SITE-SECRET.test"]'),
    ("hôte nu", "CORS_ALLOWED_ORIGINS", '["SITE-SECRET.test"]'),
    ("aucune origine", "CORS_ALLOWED_ORIGINS", "[]"),
    ("liste d'origines mal formée", "CORS_ALLOWED_ORIGINS", "[oups"),
]

# Ce qu'une origine CORS n'est pas. Une origine est ce qu'un navigateur envoie dans `Origin` :
# `schéma://hôte[:port]`, hôte en minuscules, port absent s'il est celui du schéma — et
# `django-cors-headers` la compare telle quelle (`_url_in_whitelist`). Tout écart laisse le site
# sans API sans qu'aucune erreur ne le dise ; c'est au démarrage qu'on le refuse. Onze formes :
# une par composant d'URL qui ne doit pas y être (chemin, requête, fragment, identifiant, port
# par défaut, port vide) ou qui y manque (schéma, hôte) ; le schéma hors HTTP ; l'hôte nu — que
# `urlsplit` lit comme un chemin, pas comme un schéma absent, si bien que la forme protocolaire
# `//hôte` éprouve la garde du schéma et l'hôte nu non (mesuré) ; l'hôte en majuscules.
REFUSED_ORIGINS = [
    ("chemin", "https://site.test/chemin"),
    ("requête", "https://site.test?x=1"),
    ("fragment", "https://site.test#ancre"),
    ("identifiant", "https://user@site.test"),
    ("port par défaut", "https://site.test:443"),
    ("port vide", "https://site.test:"),
    ("sans schéma", "//site.test"),
    ("sans hôte", "https://"),
    ("schéma hors HTTP", "ftp://site.test"),
    ("hôte nu", "site.test"),
    ("majuscules", "https://Site.test"),
]


def declared_variables(dotenv: Path) -> dict[str, str]:
    """Les variables qu'un fichier d'environnement déclare — commentaires et lignes vides exclus.

    Args:
        dotenv: le fichier à lire, au format `CLÉ=valeur`.

    Returns:
        Chaque nom et sa valeur telle qu'écrite, sans guillemets ni interpolation : les tests n'y
        lisent que la frontière entre les deux fichiers et les adresses de service.
    """
    lines = (raw.strip() for raw in dotenv.read_text(encoding="utf-8").splitlines())
    pairs = (line.partition("=") for line in lines if line and not line.startswith("#"))
    return {name.strip(): value.strip() for name, separator, value in pairs if separator}


def value_fragments(value: str) -> list[str]:
    """Ce qu'un message pourrait citer d'une valeur, en minuscules comme le message est lu.

    Trois formes, chacune mesurée à la relecture sur une mutation qui citait la valeur et
    laissait le test vert : la valeur entière ; chaque élément d'une liste JSON, crochets et
    guillemets retirés — un validateur qui nomme l'origine fautive ; l'hôte de chaque élément
    qui est une URL — un validateur qui suggère la forme canonique, hôte en minuscules et
    chemin retiré.
    """
    pieces = [piece.strip() for piece in re.split(r'[\[\]",]', value) if piece.strip()]
    hosts = [urlsplit(piece).hostname for piece in pieces]
    return [fragment.lower() for fragment in [*pieces, *hosts] if fragment]


def build_env(env_file: Path | None = None) -> Env:
    """Construit `Env` en ignorant le `.env` du poste, pour que les tests soient hermétiques.

    Le commentaire `pyright: ignore` est le contournement documenté par `pydantic-settings` :
    les champs sans défaut sont résolus depuis l'environnement, pas depuis l'appel.
    """
    return Env(_env_file=env_file)  # pyright: ignore[reportCallIssue]


def test_le_demarrage_echoue_sans_cle_secrete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY")

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        build_env()


@pytest.mark.parametrize("variable", SERVICE_URLS)
def test_une_adresse_de_service_mal_formee_est_refusee(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    """Toute adresse de service est refusée mal formée — la liste couvre la classe entière."""
    monkeypatch.setenv(variable, "pas-une-url")

    with pytest.raises(ValidationError, match=variable):
        build_env()


def test_le_demarrage_echoue_sans_hote_autorise_hors_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Django exige ALLOWED_HOSTS hors debug ; échouer au démarrage vaut mieux qu'à la requête."""
    monkeypatch.setenv("ALLOWED_HOSTS", "[]")

    with pytest.raises(ValidationError, match="ALLOWED_HOSTS"):
        build_env()


def test_debug_est_faux_par_defaut(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un oubli doit laisser l'application en posture de production, jamais l'inverse."""
    monkeypatch.delenv("DEBUG")

    assert build_env().DEBUG is False


def test_un_hote_absent_est_tolere_en_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le garde ne doit pas gêner le développement, où Django autorise déjà les hôtes locaux."""
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("ALLOWED_HOSTS", "[]")

    assert build_env().ALLOWED_HOSTS == []


def test_les_origines_cors_sont_lues_telles_quelles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une liste JSON d'origines, comme `ALLOWED_HOSTS` (brief de #10, décision 8), lue telle
    quelle — le `/` final qu'un type d'URL de pydantic ajouterait ferait rougir ce test."""
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        '["https://site.test","http://localhost:5173","http://site.test:443"]',
    )

    assert build_env().CORS_ALLOWED_ORIGINS == [
        "https://site.test",
        "http://localhost:5173",
        "http://site.test:443",
    ]


@pytest.mark.parametrize(
    "origin",
    [origin for _, origin in REFUSED_ORIGINS],
    ids=[name for name, _ in REFUSED_ORIGINS],
)
def test_une_origine_cors_mal_formee_est_refusee(
    monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    """Chaque composant d'URL qui n'a rien à faire dans une origine, ou qui y manque : refusé au
    démarrage, la liste entière couvrant la classe."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", f'["https://site.test","{origin}"]')

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        build_env()


def test_le_demarrage_echoue_sans_origine_cors_meme_en_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans origine admise, le site ne peut pas appeler l'API, en développement aussi : le serveur
    Vite parle au back depuis une autre origine."""
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "[]")

    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        build_env()


@pytest.mark.parametrize(
    "render",
    [render for _, render in SECRET_TRAVEL_FORMS],
    ids=[name for name, _ in SECRET_TRAVEL_FORMS],
)
def test_la_cle_secrete_n_apparait_dans_aucune_forme(
    variables: dict[str, str], render: Callable[[Env], str]
) -> None:
    """Le masquage se solde sur la classe : 8 formes recensées, 8 éprouvées ici."""
    env = build_env()

    assert variables["SECRET_KEY"] not in render(env)


def test_une_cle_secrete_trop_courte_est_refusee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Django n'avertit qu'en `check --deploy`, que la CI ne lance pas : on refuse au démarrage."""
    monkeypatch.setenv("SECRET_KEY", "trop-courte")

    with pytest.raises(ValidationError, match="SECRET_KEY"):
        build_env()


@pytest.mark.parametrize(
    ("variable", "invalid_value"),
    [(variable, value) for _, variable, value in INVALID_CONFIGURATIONS],
    ids=[name for name, _, _ in INVALID_CONFIGURATIONS],
)
def test_aucune_valeur_ne_fuit_dans_l_erreur_de_demarrage(
    monkeypatch: pytest.MonkeyPatch,
    variables: dict[str, str],
    variable: str,
    invalid_value: str,
) -> None:
    """Une erreur de démarrage part sur stderr : journaux, CI, collecteur d'erreurs.

    `pydantic` joint l'entrée fautive à chacun de ses messages — et le validateur de modèle
    reçoit l'environnement entier, donc *toutes* les valeurs. Le refus doit nommer les champs
    et taire les valeurs, quel que soit le mécanisme qui l'a déclenché.
    """
    monkeypatch.setenv(variable, invalid_value)

    with pytest.raises(ConfigurationError) as refusal:
        Env.load()

    message = str(refusal.value)
    assert variable in message, "le refus doit dire quel champ est en cause"
    for value in [invalid_value, *variables.values()]:
        for fragment in value_fragments(value):
            assert fragment not in message.lower()


def test_une_cle_inconnue_dans_le_fichier_env_est_refusee(tmp_path: Path) -> None:
    """Une clé absente de `Env` est une faute de frappe, pas une option : elle doit bloquer."""
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY_TYPO=oups\n", encoding="utf-8")

    # La casse est normalisée par `pydantic-settings` (`case_sensitive=False` par défaut).
    with pytest.raises(ValidationError, match="(?i)SECRET_KEY_TYPO"):
        build_env(env_file)


def test_le_fichier_env_est_cherche_a_la_racine_du_depot() -> None:
    """`manage.py` se lance depuis `apps/api`, pytest depuis la racine : un seul `.env` pour les deux.

    Résolu sur un environnement vide, et non sur celui du processus : sinon un développeur qui
    exporte `ENV_FILE` verrait rougir un test qui n'a rien à voir avec son changement.
    """
    assert (REPOSITORY_ROOT / "pyproject.toml").exists(), "l'ancre du dépôt a bougé"
    assert env_file_path({}) == REPOSITORY_ROOT / ".env"


def test_un_chemin_env_relatif_est_ancre_sur_la_racine() -> None:
    """Laisser le dossier courant trancher ferait lire deux fichiers selon l'appelant."""
    assert env_file_path({"ENV_FILE": "ailleurs/.env"}) == REPOSITORY_ROOT / "ailleurs" / ".env"


def test_un_chemin_env_absolu_est_respecte() -> None:
    absolute = Path(REPOSITORY_ROOT.anchor) / "tmp" / "ailleurs.env"

    assert env_file_path({"ENV_FILE": str(absolute)}) == absolute


def test_l_exemple_declare_exactement_les_champs_d_env() -> None:
    """« Ajouter une variable, c'est ajouter un champ typé **et** une ligne » — `config/env.py`.

    Cette règle est écrite en tête du module depuis #2 et n'était gardée par rien. Un champ sans
    sa ligne laisse un clone neuf échouer au démarrage sans savoir quoi renseigner ; une ligne
    sans son champ fait échouer le démarrage à la lecture du fichier, pour une variable morte.
    """
    assert set(declared_variables(ENV_EXAMPLE)) == set(Env.model_fields)


def test_les_variables_de_compose_sont_disjointes_de_celles_du_back() -> None:
    """La scission en deux fichiers ne vaut que tant que personne ne les remélange.

    Une variable de `Env` recopiée dans `infra/dev.env` créerait deux sources pour un même
    réglage ; une variable de Compose glissée dans `.env.example` ferait refuser le démarrage
    sur la copie que `CONTRIBUTING.md` demande d'en faire.
    """
    compose_only = set(declared_variables(COMPOSE_ENV))

    assert compose_only, "aucune variable lue dans `infra/dev.env` — le format a-t-il changé ?"
    assert compose_only & set(Env.model_fields) == set()


def test_les_adresses_de_service_de_l_exemple_visent_127_0_0_1() -> None:
    """Le Compose de développement publie ses ports pour `127.0.0.1` seulement, et sous Windows
    `localhost` se résout d'abord en `::1` : une commande lancée depuis le poste attendrait son
    délai à chaque connexion avant de se replier (mesuré : 20 s, contre 0,01 s en `127.0.0.1`)."""
    example = declared_variables(ENV_EXAMPLE)

    hosts = {variable: urlsplit(example[variable]).hostname for variable in SERVICE_URLS}
    assert hosts == dict.fromkeys(SERVICE_URLS, "127.0.0.1")


def test_un_env_file_vide_retombe_sur_la_racine() -> None:
    """Une variable posée mais vide est une variable non renseignée, pas un chemin."""
    assert env_file_path({"ENV_FILE": ""}) == REPOSITORY_ROOT / ".env"


@pytest.mark.parametrize("variable", PATH_VARIABLES)
def test_un_chemin_relatif_est_ancre_sur_la_racine(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    """Même règle que pour `ENV_FILE`, et pour la même raison.

    `manage.py` se lance depuis `apps/api`, `pytest` depuis la racine : laisser le dossier
    courant trancher ferait viser deux endroits différents selon l'appelant.
    """
    monkeypatch.setenv(variable, "ailleurs")

    assert getattr(build_env(), variable) == REPOSITORY_ROOT / "ailleurs"


@pytest.mark.parametrize("variable", PATH_VARIABLES)
def test_un_chemin_absolu_est_respecte(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    """C'est la forme que le conteneur reçoit : un chemin de volume, hors du dépôt."""
    absolute = Path(REPOSITORY_ROOT.anchor) / "srv" / "ailleurs"
    monkeypatch.setenv(variable, str(absolute))

    assert getattr(build_env(), variable) == absolute


def test_le_media_root_par_defaut_est_dans_le_depot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un clone qui n'a pas renseigné la variable sait déjà où écrire (ADR 0004, disque)."""
    monkeypatch.delenv("MEDIA_ROOT")

    assert build_env().MEDIA_ROOT == REPOSITORY_ROOT / "media"
