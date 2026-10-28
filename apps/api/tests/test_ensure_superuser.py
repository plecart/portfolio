"""Tests d'`ensure_superuser`, la commande qui pose l'unique superutilisateur de l'admin.

Le point d'entrée du conteneur la joue sans argument (`STARTUP_STEPS`) : elle lit
`settings.ADMIN_USERNAME` et `settings.ADMIN_PASSWORD`, que chaque test pose ici.
"""

from collections.abc import Callable
from io import StringIO

import pytest
from access.management.commands.ensure_superuser import (
    CREATED,
    PASSWORD_UPDATED,
    RIGHTS_RESTORED,
    UNCHANGED,
)
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.models import BooleanField
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from pydantic import SecretStr
from test_compose import PROD_ENV_EXAMPLE
from test_env import declared_variables

pytestmark = pytest.mark.django_db

USERNAME = "auteur-du-portfolio"
PASSWORD = "phrase-de-passe-du-superutilisateur"
NEW_PASSWORD = "nouvelle-phrase-de-passe-du-superutilisateur"

# Les drapeaux de droits du compte : ceux que l'admin exige (`AdminSite.has_permission` lit
# `is_active` et `is_staff`), et celui qui lui ouvre toutes les permissions (`has_perm`).
RIGHTS = ("is_superuser", "is_staff", "is_active")
GRANTED = dict.fromkeys(RIGHTS, True)

# Ce par quoi une requête écrit en base. Les autres sont des lectures, ou les points de sauvegarde
# de la transaction de la commande, imbriquée dans celle du test.
WRITES = ("INSERT", "UPDATE", "DELETE")

# Un mot de passe par validateur de `AUTH_PASSWORD_VALIDATORS`, que celui-là seul refuse (mesuré
# validateur par validateur le 2026-10-28, Django 6.1.2) : un validateur retiré du réglage, ou une
# longueur minimale ramenée aux 8 de son défaut, laisse passer le sien.
WEAK_PASSWORDS = {
    "trop court": "c0urt-Xq",
    "courant": "123456qwerty",
    "entièrement numérique": "731904268513",
    "proche du nom": f"{USERNAME}!",
}

# Chaque issue de la commande — compte créé ; compte existant inchangé, droits rétablis, mot de passe
# mis à jour, ou les deux ; trois refus, un par `CommandError` —, avec ce qui la précède en base et
# les réglages qui la déclenchent : aucune ne doit citer un mot de passe.
EXITS: dict[str, tuple[Callable[[], object], str, str]] = {
    "créé": (lambda: None, USERNAME, PASSWORD),
    "inchangé": (lambda: run(), USERNAME, PASSWORD),
    "mot de passe mis à jour": (lambda: run(), USERNAME, NEW_PASSWORD),
    "droits rétablis": (
        lambda: User.objects.create_user(USERNAME, password=PASSWORD),
        USERNAME,
        PASSWORD,
    ),
    "droits rétablis et mot de passe mis à jour": (
        lambda: User.objects.create_user(USERNAME, password=PASSWORD),
        USERNAME,
        NEW_PASSWORD,
    ),
    "nom vide": (lambda: None, "", PASSWORD),
    "mot de passe faible": (lambda: None, USERNAME, WEAK_PASSWORDS["trop court"]),
    "autre compte d'admin": (
        lambda: User.objects.create_superuser("ancien", password=NEW_PASSWORD),
        USERNAME,
        PASSWORD,
    ),
}


def run(username: str = USERNAME, password: str = PASSWORD, output: StringIO | None = None) -> str:
    """Joue la commande sous ces réglages, comme le point d'entrée : sans argument.

    Returns:
        Ce qu'elle écrit, sortie standard et sortie d'erreur confondues — dans `output` s'il est
        donné, ce qui le garde lisible quand la commande refuse.
    """
    output = output or StringIO()
    with override_settings(ADMIN_USERNAME=username, ADMIN_PASSWORD=SecretStr(password)):
        call_command("ensure_superuser", stdout=output, stderr=output)
    return output.getvalue()


def rights_of(user: User) -> dict[str, bool]:
    """Les drapeaux de droits du compte, par nom."""
    return {flag: getattr(user, flag) for flag in RIGHTS}


def assert_unchanged(password: str = PASSWORD) -> None:
    """Joue la commande, qui doit dire le superutilisateur inchangé sans rien écrire en base."""
    with CaptureQueriesContext(connection) as queries:
        assert run(password=password) == f"{UNCHANGED}\n"

    assert queries, "aucune requête capturée — la capture a-t-elle cessé de mordre ?"
    assert [query["sql"] for query in queries if query["sql"].startswith(WRITES)] == []


def test_la_commande_cree_le_superutilisateur_sans_e_mail() -> None:
    assert run() == f"{CREATED}\n"

    user = User.objects.get()
    assert (user.username, user.email) == (USERNAME, "")
    assert rights_of(user) == GRANTED
    assert user.check_password(PASSWORD)


def test_deux_lancements_ne_creent_qu_un_compte_et_le_second_n_ecrit_rien() -> None:
    """Le point d'entrée la rejoue à chaque démarrage du conteneur."""
    run()

    assert_unchanged()
    assert User.objects.count() == 1


def test_un_mot_de_passe_change_est_mis_a_jour() -> None:
    run()

    assert run(password=NEW_PASSWORD) == f"{PASSWORD_UPDATED}\n"
    assert User.objects.get().check_password(NEW_PASSWORD)


def test_les_drapeaux_de_droits_sont_tous_les_booleens_du_compte() -> None:
    """`RIGHTS` couvre le modèle sans résidu : un booléen qu'une montée de Django ajouterait à
    `User` rougit ici, jusqu'à ce qu'on dise s'il donne un droit."""
    booleans = {field.name for field in User._meta.get_fields() if isinstance(field, BooleanField)}

    assert booleans == set(RIGHTS)


@pytest.mark.parametrize("right", RIGHTS)
@pytest.mark.parametrize(
    ("password", "written"),
    [(PASSWORD, [RIGHTS_RESTORED]), (NEW_PASSWORD, [RIGHTS_RESTORED, PASSWORD_UPDATED])],
    ids=["même mot de passe", "mot de passe changé"],
)
def test_un_compte_existant_retrouve_chacun_de_ses_droits(
    right: str, password: str, written: list[str]
) -> None:
    """Chaque drapeau de droits que la commande rétablit manque seul : aucun ne se cache derrière
    un autre dans la condition qui décide de les rétablir.

    Dénombrés avant le correctif (relecture de la PR #181) : 3 — `is_superuser`, `is_staff`,
    `is_active` (`RIGHTS`), les trois `BooleanField` de `User` sous Django 6.1.2, ce que tient
    `test_les_drapeaux_de_droits_sont_tous_les_booleens_du_compte`.
    """
    User.objects.create_user(USERNAME, password=PASSWORD)
    User.objects.update(**GRANTED | {right: False})

    assert run(password=password) == f"{', '.join(written)}\n"
    user = User.objects.get()
    assert rights_of(user) == GRANTED
    assert user.check_password(password)


@pytest.mark.parametrize("existing", [False, True], ids=["à la création", "au changement"])
@pytest.mark.parametrize("password", WEAK_PASSWORDS.values(), ids=WEAK_PASSWORDS.keys())
def test_un_mot_de_passe_neuf_et_faible_est_refuse_avec_les_motifs_des_validateurs(
    password: str, existing: bool
) -> None:
    """Un mot de passe neuf entre par deux chemins, la création du compte et son changement :
    les validateurs gardent l'un et l'autre."""
    if existing:
        run()
    with pytest.raises(ValidationError) as rejection:
        validate_password(password, User(username=USERNAME))

    with pytest.raises(CommandError) as refusal:
        run(password=password)

    assert all(reason in str(refusal.value) for reason in rejection.value.messages)
    kept = [user.check_password(PASSWORD) for user in User.objects.all()]
    assert kept == ([True] if existing else []), "le mot de passe refusé a été écrit"


@pytest.mark.parametrize("password", WEAK_PASSWORDS.values(), ids=WEAK_PASSWORDS.keys())
def test_un_mot_de_passe_inchange_n_est_pas_rejuge(password: str) -> None:
    """Les validateurs ne jugent qu'un mot de passe neuf : une montée de Django qui en durcit un
    n'arrête pas `api` sur le compte déjà posé. `create_superuser` pose celui-ci sans les jouer."""
    User.objects.create_superuser(USERNAME, password=password)

    assert_unchanged(password)


@pytest.mark.parametrize("flag", ["is_superuser", "is_staff"])
def test_un_autre_compte_d_admin_fait_refuser_la_commande(flag: str) -> None:
    """L'admin n'a qu'un compte (cadrage §6.2) : la commande n'en crée jamais un second. L'un ou
    l'autre drapeau, seul, fait d'un compte un compte d'admin (`RIGHTS`) — un staff seul, reste
    d'une restauration ou d'un ancien poste, compris."""
    User.objects.create(username="ancien", **{flag: True})

    with pytest.raises(CommandError):
        run()

    assert list(User.objects.values_list("username", flat=True)) == ["ancien"]


@pytest.mark.parametrize(
    ("username", "password"),
    [("", PASSWORD), (USERNAME, "")],
    ids=["nom vide", "mot de passe vide"],
)
def test_une_variable_vide_fait_refuser_la_commande(username: str, password: str) -> None:
    """Vides par défaut dans `Env` : c'est la commande qui arrête `api` sans eux."""
    with pytest.raises(CommandError, match="ADMIN_USERNAME et ADMIN_PASSWORD"):
        run(username, password)

    assert not User.objects.exists()


@pytest.mark.parametrize(("prepare", "username", "password"), EXITS.values(), ids=EXITS.keys())
def test_aucune_issue_ne_cite_le_mot_de_passe(
    prepare: Callable[[], object], username: str, password: str
) -> None:
    """Sa sortie part dans le journal du conteneur, son refus aussi (`CommandError: …`)."""
    prepare()
    output = StringIO()
    try:
        run(username, password, output)
    except CommandError as refusal:
        output.write(str(refusal))

    emitted = output.getvalue()
    assert emitted, "aucune sortie lue — la commande a-t-elle cessé d'écrire ?"
    assert [secret for secret in (password, PASSWORD, NEW_PASSWORD) if secret in emitted] == []


def test_le_modele_de_production_cree_son_superutilisateur() -> None:
    """`infra/tests/backup.yml` démarre `api` sur `infra/prod.env.example`, et `api` joue la
    commande à son démarrage : un mot de passe factice que les validateurs refusent arrêterait la
    pile des tests d'images, que `make test` ne lance pas."""
    model = declared_variables(PROD_ENV_EXAMPLE)

    assert run(model["ADMIN_USERNAME"], model["ADMIN_PASSWORD"]) == f"{CREATED}\n"
