"""Tests de l'accès à l'admin : le second facteur de `django-otp`, sa page de connexion, les écrans
retirés, et la fumée de ceux qui restent.

L'admin est un `OTPAdminSite` (`access/site.py`, `config/apps.py`) : il ne sert aucune page à un
superutilisateur qu'aucun appareil n'a vérifié — l'application TOTP ou un code de secours,
qu'enrôle `manage.py enroll_second_factor`. Sa page de connexion est celle de la bibliothèque, sans
le bouton de défi. La fixture `admin_client` (`conftest.py`) arrive vérifiée ; les tests de
connexion partent d'un client nu et passent par le formulaire.
"""

import hashlib
from importlib.resources import files

import pytest
from content.preview import PREVIEW_ROUTE
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group, User
from django.db.models import Model
from django.http.response import HttpResponseBase
from django.test import Client
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


def log_in(client: Client, device: TOTPDevice | StaticDevice, token: str) -> HttpResponseBase:
    """Le formulaire de connexion de l'admin, rempli : identifiants, appareil choisi et jeton."""
    return client.post(
        reverse("admin:login"),
        {
            "username": USERNAME,
            "password": PASSWORD,
            "otp_device": device.persistent_id,
            "otp_token": token,
        },
    )


def admin_opens(client: Client) -> bool:
    return client.get(reverse("admin:index")).status_code == 200


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
    device = saved(TOTPDevice(user=superuser(), name="totp"))

    log_in(client, device, totp_token(device))
    opened = admin_opens(client)
    client.logout()
    log_in(client, device, totp_token(device, steps=-10))

    assert (opened, admin_opens(client)) == (True, False)


@pytest.mark.django_db
def test_un_code_de_secours_ouvre_l_admin_une_seule_fois(client: Client) -> None:
    """Perte de l'application : un code de secours ouvre l'admin, puis ne vaut plus."""
    device = saved(StaticDevice(user=superuser(), name="secours"))
    saved(StaticToken(device=device, token=BACKUP_CODE))

    log_in(client, device, BACKUP_CODE)
    opened = admin_opens(client)
    client.logout()
    log_in(client, device, BACKUP_CODE)

    assert (opened, admin_opens(client)) == (True, False)


@pytest.fixture
def password_accepted(db: None, client: Client) -> HttpResponseBase:
    """La page que rend le premier envoi du formulaire — nom et mot de passe justes, jeton vide —
    pour un compte enrôlé : elle redemande le jeton, et l'appareil qui l'a produit."""
    saved(TOTPDevice(user=superuser(), name="totp"))

    return client.post(
        reverse("admin:login"), {"username": USERNAME, "password": PASSWORD, "otp_token": ""}
    )


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
    device = saved(TOTPDevice(user=superuser(), name="totp"))
    cookies = (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME)

    response = log_in(client, device, totp_token(device))

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
