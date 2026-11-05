"""Le site de l'admin : celui de `django-otp`, servi par le gabarit de connexion du projet (#215).

Le gabarit de la bibliothèque, `otp/admin111/login.html`, offre après le mot de passe un bouton de
défi : il demande à l'appareil choisi d'émettre un défi (`Device.generate_challenge`), ce qu'aucun
des deux appareils du compte — l'application TOTP, les codes de secours — ne sait faire. Le bouton
ne rendait qu'une erreur : « The selected OTP device is not interactive », message
`not_interactive` d'`OTPAuthenticationFormMixin`.

Dans un module à part et non dans `config/apps.py` : `django_otp.admin` ne s'importe pas avant que
le registre des applications soit prêt (`AppRegistryNotReady`), et `AdminConfig.default_site`
n'en est que le chemin, résolu au premier accès à `admin.site`.
"""

from django_otp.admin import OTPAdminSite  # pyright: ignore[reportMissingTypeStubs]


class SecondFactorAdminSite(OTPAdminSite):
    """`OTPAdminSite`, dont la page de connexion ne porte plus le bouton de défi.

    `access/login.html` étend le gabarit de la bibliothèque et n'en redéfinit que le bloc
    `content`, recopié sans ce bouton : le choix de l'appareil, les champs, les styles et
    `form.media` restent les siens. Un nom propre au projet plutôt qu'un homonyme du gabarit de la
    bibliothèque, qui ne l'emporterait que par l'ordre d'`INSTALLED_APPS`. `test_admin_access.py`
    épingle l'empreinte de ce gabarit : une montée de `django-otp` qui le change rougit, et le bloc
    recopié se relit.

    Le reste — le formulaire, et `has_permission`, qui exige `is_verified()` — est celui
    d'`OTPAdminSite`.
    """

    login_template = "access/login.html"
