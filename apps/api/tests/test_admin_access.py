"""Tests de l'accès à l'admin : le second facteur de `django-otp`, sa page de connexion, les écrans
retirés, et la fumée de ceux qui restent.

L'admin est un `OTPAdminSite` (`access/site.py`, `config/apps.py`) : il ne sert aucune page à un
superutilisateur qu'aucun appareil n'a vérifié — l'application TOTP ou un code de secours,
qu'enrôle `manage.py enroll_second_factor`. Sa page de connexion est celle de la bibliothèque, sans
le bouton de défi ; sans appareil choisi, son formulaire vérifie le jeton contre l'application. La
fixture `admin_client` (`conftest.py`) arrive vérifiée ; les tests de connexion partent d'un client
nu et passent par le formulaire.
"""

import hashlib
from collections.abc import Callable
from importlib.resources import files

import pytest
from config import strings
from content.preview import PREVIEW_ROUTE
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group, User
from django.db import connection
from django.db.models import Model
from django.http.response import HttpResponseBase
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django_otp.oath import TOTP  # pyright: ignore[reportMissingTypeStubs]
from django_otp.plugins.otp_static.models import (  # pyright: ignore[reportMissingTypeStubs]
    StaticDevice,
    StaticToken,
)
from django_otp.plugins.otp_totp.models import TOTPDevice  # pyright: ignore[reportMissingTypeStubs]
from factories import saved
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed
from test_security_headers import INLINE_CODE, header_nonces, tag_nonces

USERNAME = "auteur-du-portfolio"
PASSWORD = "phrase-de-passe-du-superutilisateur"
BACKUP_CODE = "codedesecours"

# Le gabarit de connexion de `django-otp`, que celui du projet étend (`access/site.py`), et son
# empreinte en 1.7.5 : `access/login.html` en recopie le bloc `content`, sans le bouton de défi.
OTP_LOGIN_TEMPLATE = "otp/admin111/login.html"
OTP_LOGIN_TEMPLATE_SHA256 = "b5f782875e85a6ceab418ed13bfe817192c77bf67b5c6d4c903c73c60fe4887d"

# Une page de chaque sorte, par sa méthode et sa route : l'index, la liste d'un écran, et l'aperçu
# Markdown — vue du projet, que `config/urls.py` place sous les règles de l'admin.
ADMIN_PAGES = {
    "index": ("GET", "admin:index"),
    "liste d'un écran": ("GET", "admin:content_technology_changelist"),
    "aperçu Markdown": ("POST", PREVIEW_ROUTE),
}

# Les écrans que l'admin ne montre pas (cadrage §6.2) : l'unique compte vient d'`ensure_superuser`,
# son second facteur d'`enroll_second_factor` — un écran serait une autre voie d'en ajouter un.
REMOVED_SCREENS: list[type[Model]] = [Group, User, TOTPDevice, StaticDevice]

# Les écrans qu'il montre, tirés de son registre : l'index, puis la liste et l'ajout de chaque
# modèle enregistré — un écran enregistré demain y entre de lui-même.
SCREENS = [
    "admin:index",
    *(
        f"admin:{model._meta.app_label}_{model._meta.model_name}_{view}"
        for model in apps.get_models()
        if admin.site.is_registered(model)
        for view in ("changelist", "add")
    ),
]


def superuser(username: str = USERNAME) -> User:
    return User.objects.create_superuser(username, password=PASSWORD)


def totp_token(device: TOTPDevice, steps: int = 0) -> str:
    """Le jeton que l'application TOTP du compte affiche, décalé de `steps` pas de temps : le pas
    de 30 s, les six chiffres et l'origine des temps par défaut de `TOTP` sont ceux d'un
    `TOTPDevice` neuf."""
    return str(TOTP(device.bin_key, drift=steps).token())


def enroll(user: User) -> tuple[TOTPDevice, StaticDevice]:
    """Les deux appareils qu'`enroll_second_factor` pose sur `user`, sous leurs noms :
    l'application TOTP, et les codes de secours — ici le seul `BACKUP_CODE`."""
    app = saved(TOTPDevice(user=user, name=strings.OTP_DEVICE_TOTP))
    backup = saved(StaticDevice(user=user, name=strings.OTP_DEVICE_BACKUP_CODES))
    saved(StaticToken(device=backup, token=BACKUP_CODE))
    return app, backup


# Les jetons qu'éprouvent les envois sans appareil choisi, par nom : ceux de l'application se
# tirent de sa clé, le code de secours est fixe.
TOKENS: dict[str, Callable[[TOTPDevice], str]] = {
    "jeton TOTP du moment": totp_token,
    "jeton TOTP périmé": lambda app: totp_token(app, steps=-10),
    "code de secours": lambda _app: BACKUP_CODE,
}


def log_in(
    client: Client, device: TOTPDevice | StaticDevice | None, token: str
) -> HttpResponseBase:
    """Le formulaire de connexion de l'admin, rempli : identifiants, appareil choisi — `None` pour
    aucun, comme au premier envoi, qui ne porte pas le sélecteur — et jeton."""
    choice = {} if device is None else {"otp_device": device.persistent_id}
    return client.post(
        reverse("admin:login"),
        {"username": USERNAME, "password": PASSWORD, "otp_token": token} | choice,
    )


def selected_option(device: TOTPDevice | StaticDevice, label: str) -> str:
    """L'option du sélecteur « Appareil OTP » qui présente `device` sous `label`, présélectionnée."""
    return f'<option value="{device.persistent_id}" selected>{label}</option>'


def failures(device: TOTPDevice | StaticDevice) -> int:
    """Les échecs de vérification que `device` a comptés (`ThrottlingMixin`), relus en base."""
    device.refresh_from_db()
    return device.throttling_failure_count  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


def admin_opens(client: Client) -> bool:
    return client.get(reverse("admin:index")).status_code == 200


def logged_in(client: Client) -> bool:
    """Le formulaire a-t-il connecté le compte ? Un refus se lit ici, pas à l'admin :
    `OTPMiddleware` écarte aussi, à la requête suivante, l'appareil d'un autre compte ou non
    confirmé, et l'admin resterait fermé même si le formulaire avait accepté le jeton."""
    return SESSION_KEY in client.session


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "route"), ADMIN_PAGES.values(), ids=ADMIN_PAGES.keys())
def test_un_superutilisateur_sans_second_facteur_n_obtient_aucune_page(
    client: Client, method: str, route: str
) -> None:
    """Connecté par son seul mot de passe, il est renvoyé vers la connexion, comme un anonyme."""
    user = superuser()
    client.force_login(user)

    response = client.generic(method, reverse(route))

    assert client.session[SESSION_KEY] == str(user.pk), "le compte n'est plus connecté"
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("admin:login"))


@pytest.mark.django_db
def test_un_jeton_totp_ouvre_l_admin_et_un_jeton_perime_ne_l_ouvre_pas(client: Client) -> None:
    """Le jeton du moment ouvre l'admin ; celui d'il y a cinq minutes, hors de la tolérance d'un
    pas de 30 s (`TOTPDevice.tolerance`), ne l'ouvre plus."""
    app, _ = enroll(superuser())

    log_in(client, app, totp_token(app))
    opened = admin_opens(client)
    client.logout()
    log_in(client, app, totp_token(app, steps=-10))

    assert (opened, admin_opens(client)) == (True, False)


@pytest.mark.django_db
def test_un_code_de_secours_ouvre_l_admin_une_seule_fois(client: Client) -> None:
    """Perte de l'application : un code de secours, son appareil choisi, ouvre l'admin, puis ne
    vaut plus."""
    _, backup = enroll(superuser())

    log_in(client, backup, BACKUP_CODE)
    opened = admin_opens(client)
    client.logout()
    log_in(client, backup, BACKUP_CODE)

    assert (opened, admin_opens(client)) == (True, False)


@pytest.mark.django_db
def test_nom_mot_de_passe_et_jeton_totp_ouvrent_l_admin_en_un_seul_envoi(client: Client) -> None:
    """Le premier envoi ne porte pas le sélecteur d'appareil : sans choix, le jeton se vérifie
    contre l'application du compte, et l'admin — qui exige `is_verified()` — s'ouvre."""
    app, _ = enroll(superuser())

    response = log_in(client, None, totp_token(app))

    assert (response.status_code, admin_opens(client)) == (302, True)


@pytest.mark.django_db
def test_sans_appareil_choisi_l_application_se_verifie_sous_verrou(client: Client) -> None:
    """Comme l'appareil choisi, que `django-otp` charge par `select_for_update` : deux envois
    concurrents du même jeton ne passent pas tous deux. La concurrence ne se rejoue pas ici ; le
    verrou se lit dans la requête qui charge l'application."""
    app, _ = enroll(superuser())

    with CaptureQueriesContext(connection) as queries:
        log_in(client, None, totp_token(app))

    assert any(
        "otp_totp_totpdevice" in query["sql"] and "FOR UPDATE" in query["sql"]
        for query in queries.captured_queries
    ), "l'application s'est chargée sans verrou"


@pytest.mark.django_db
@pytest.mark.parametrize("token", ["jeton TOTP périmé", "code de secours"])
def test_sans_appareil_choisi_le_jeton_ne_se_verifie_que_contre_l_application(
    client: Client, token: str
) -> None:
    """L'application compte l'échec ; les codes de secours n'enregistrent aucune tentative, et le
    code envoyé reste valable : il ne vaut que par le choix de son appareil. Essayer chaque
    appareil tour à tour compterait un échec contre chacun — ce que `django-otp` 1.7 a retiré."""
    app, backup = enroll(superuser())

    log_in(client, None, TOKENS[token](app))

    assert not logged_in(client)
    assert failures(app) == 1, "l'échec ne s'est pas compté contre l'application"
    assert (failures(backup), StaticToken.objects.count()) == (0, 1), (
        "les codes de secours ont été éprouvés"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("token", ["jeton TOTP du moment", "code de secours"])
def test_sans_application_confirmee_un_jeton_sans_appareil_est_refuse(
    client: Client, token: str
) -> None:
    """Le formulaire de la bibliothèque demande alors l'appareil (`device_required`) : une
    application non confirmée n'est pas prête (`Device.confirmed`), et les codes de secours ne
    deviennent pas l'appareil par défaut."""
    app, _ = enroll(superuser())
    app.confirmed = False
    app.save()

    log_in(client, None, TOKENS[token](app))

    assert not logged_in(client)


@pytest.mark.django_db
@pytest.mark.parametrize("chosen", [True, False], ids=["choisie", "non choisie"])
def test_le_jeton_de_l_application_d_un_autre_compte_est_refuse(
    client: Client, chosen: bool
) -> None:
    """Choisie, elle ne vaut rien : la garde de `django-otp`, qui écarte l'appareil d'un autre
    compte. Non choisie, l'application qui vérifie le jeton est celle du compte, jamais une autre —
    l'autre est enregistrée la première, pour être prise si le compte cessait de filtrer."""
    stranger_app = saved(TOTPDevice(user=superuser("un-autre-compte"), name="autre"))
    enroll(superuser())

    log_in(client, stranger_app if chosen else None, totp_token(stranger_app))

    assert not logged_in(client)


@pytest.mark.django_db
def test_avant_le_mot_de_passe_la_connexion_ne_porte_pas_le_selecteur(client: Client) -> None:
    """La liste des appareils dépend du compte : ni la page servie à un anonyme, ni celle qui suit
    un mot de passe faux ne la montrent."""
    enroll(superuser())

    anonymous = client.get(reverse("admin:login"))
    wrong_password = client.post(
        reverse("admin:login"), {"username": USERNAME, "password": "faux", "otp_token": ""}
    )

    assertNotContains(anonymous, 'name="otp_device"')
    assertNotContains(wrong_password, 'name="otp_device"')


@pytest.mark.django_db
def test_apres_le_mot_de_passe_le_selecteur_presente_l_application(client: Client) -> None:
    """Nom et mot de passe justes, jeton vide : la page qui redemande le jeton porte le sélecteur,
    présélectionné sur l'application parmi les appareils du compte — renvoyer le jeton suffit."""
    app, _ = enroll(superuser())

    response = log_in(client, None, "")

    assertContains(response, selected_option(app, strings.OTP_DEVICE_TOTP), html=True)


@pytest.mark.django_db
def test_le_selecteur_garde_l_appareil_choisi(client: Client) -> None:
    """Les codes de secours choisis, jeton vide : la page qui redemande le jeton présente
    l'appareil choisi, pas l'application."""
    _, backup = enroll(superuser())

    response = log_in(client, backup, "")

    assertContains(response, selected_option(backup, strings.OTP_DEVICE_BACKUP_CODES), html=True)


@pytest.fixture
def password_accepted(db: None, client: Client) -> HttpResponseBase:
    """La page que rend le premier envoi du formulaire — nom et mot de passe justes, jeton vide —
    pour un compte enrôlé : elle redemande le jeton, et l'appareil qui l'a produit."""
    enroll(superuser())

    return log_in(client, None, "")


def test_apres_le_mot_de_passe_la_connexion_n_offre_pas_de_defi(
    password_accepted: HttpResponseBase,
) -> None:
    """Le bouton de défi de `django-otp` demande à l'appareil choisi d'émettre un défi : ni
    l'application TOTP ni les codes de secours ne le savent, et il ne rendait qu'une erreur. Le
    choix de l'appareil et son jeton restent."""
    assertNotContains(password_accepted, 'name="otp_challenge"')
    assertContains(password_accepted, 'name="otp_device"')
    assertContains(password_accepted, 'name="otp_token"')


def test_la_connexion_est_rendue_par_le_gabarit_du_projet_qui_etend_celui_de_django_otp(
    password_accepted: HttpResponseBase,
) -> None:
    """Le projet n'en redéfinit que le bloc `content` : le reste de la page — styles et
    `form.media` compris — reste celui de la bibliothèque, qu'il étend."""
    assertTemplateUsed(password_accepted, "access/login.html")
    assertTemplateUsed(password_accepted, OTP_LOGIN_TEMPLATE)


def test_le_gabarit_de_connexion_de_django_otp_est_celui_que_le_projet_recopie() -> None:
    """Lu dans le paquet installé : une montée de `django-otp` qui change le gabarit rougit, et le
    bloc recopié se relit avant d'en reporter l'empreinte."""
    template = files("django_otp").joinpath("templates", OTP_LOGIN_TEMPLATE)

    assert hashlib.sha256(template.read_bytes()).hexdigest() == OTP_LOGIN_TEMPLATE_SHA256, (
        f"le gabarit {OTP_LOGIN_TEMPLATE} de django-otp a changé : relis son bloc `content`, "
        "recopié sans le bouton de défi dans `access/templates/access/login.html`, puis reporte "
        "ici sa nouvelle empreinte"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("model", REMOVED_SCREENS, ids=lambda model: model.__name__)
def test_l_admin_ne_propose_pas_l_ecran(admin_client: Client, model: type[Model]) -> None:
    """Absent de l'index, et son adresse ne mène nulle part."""
    index = admin_client.get(reverse("admin:index"))
    listed = [entry["model"] for app in index.context["app_list"] for entry in app["models"]]
    changelist = f"/admin/{model._meta.app_label}/{model._meta.model_name}/"

    assert listed, "aucun écran listé — l'index a-t-il changé de contexte ?"
    assert model not in listed
    assert admin_client.get(changelist).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("route", SCREENS)
def test_chaque_ecran_s_ouvre_sous_la_csp(admin_client: Client, route: str) -> None:
    """Il s'ouvre, chacune de ses balises `<script>` et `<style>` porte le nonce que sa CSP
    autorise, et aucun attribut n'y porte de code en ligne : rien n'est refusé au navigateur
    (ADR 0020)."""
    response = admin_client.get(reverse(route))
    page = response.content.decode()

    assert (response.status_code, tag_nonces(page)) == (200, header_nonces(response))
    assert INLINE_CODE.findall(page) == []


@pytest.mark.parametrize("route", SCREENS)
def test_un_anonyme_est_renvoye_vers_la_connexion(client: Client, route: str) -> None:
    response = client.get(reverse(route))

    assert response.status_code == 302
    assert response["Location"].startswith(reverse("admin:login"))


@pytest.mark.django_db
def test_la_connexion_pose_ses_cookies_en_secure(client: Client) -> None:
    """Hors `DEBUG`, comme la suite tourne : la session et le jeton CSRF, que la connexion
    renouvelle, ne repartent que sur HTTPS."""
    app, _ = enroll(superuser())
    cookies = (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME)

    response = log_in(client, app, totp_token(app))

    assert {name: response.cookies[name]["secure"] for name in cookies} == dict.fromkeys(
        cookies, True
    )


def test_la_page_de_connexion_repond_a_la_sonde_d_api(client: Client) -> None:
    """La sonde d'`api` (`infra/compose.yml`) : `GET /admin/login/`, anonyme, sous le premier nom
    d'`ALLOWED_HOSTS`, saine sous 400 — derrière toute la chaîne des middlewares, en-têtes de
    sécurité compris. Sans `django_db` : la page ne touche pas la base."""
    response = client.get("/admin/login/", headers={"host": settings.ALLOWED_HOSTS[0]})

    assert response.status_code < 400


def test_l_icone_que_demande_le_navigateur_ne_rend_pas_d_erreur(client: Client) -> None:
    """Toute page de l'admin fait demander `/favicon.ico` au navigateur : un 404 s'inscrirait en
    erreur dans sa console. L'hôte de l'API n'a pas d'icône, et le dit sans erreur."""
    assert client.get("/favicon.ico").status_code == 204
