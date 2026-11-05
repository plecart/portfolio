"""Le site de l'admin : celui de `django-otp`, servi par le gabarit de connexion du projet, et dont
le formulaire prend l'application TOTP du compte quand aucun appareil n'est choisi (#215).

Le gabarit de la bibliothèque, `otp/admin111/login.html`, offre après le mot de passe un bouton de
défi : il demande à l'appareil choisi d'émettre un défi (`Device.generate_challenge`), ce qu'aucun
des deux appareils du compte — l'application TOTP, les codes de secours — ne sait faire. Le bouton
ne rendait qu'une erreur : « The selected OTP device is not interactive », message
`not_interactive` d'`OTPAuthenticationFormMixin`.

Dans un module à part et non dans `config/apps.py` : `django_otp.admin` ne s'importe pas avant que
le registre des applications soit prêt (`AppRegistryNotReady`), et `AdminConfig.default_site`
n'en est que le chemin, résolu au premier accès à `admin.site`.
"""

from typing import cast

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.http import QueryDict
from django_otp.admin import (  # pyright: ignore[reportMissingTypeStubs]
    OTPAdminAuthenticationForm,
    OTPAdminSite,
)
from django_otp.models import Device  # pyright: ignore[reportMissingTypeStubs]
from django_otp.plugins.otp_totp.models import TOTPDevice  # pyright: ignore[reportMissingTypeStubs]

DEVICE_FIELD = "otp_device"


def authenticator_app(user: User) -> QuerySet[TOTPDevice]:
    """L'application TOTP de `user`, confirmée — prête à vérifier (`Device.confirmed`).

    Le filtre de `DeviceManager.devices_for_user`, écrit ici pour typer le résultat : le
    gestionnaire de `django-otp`, non paramétré, rend pour pyright un `QuerySet[Unknown]`.
    """
    return cast("QuerySet[TOTPDevice]", TOTPDevice.objects.filter(user=user, confirmed=True))


class SecondFactorAuthenticationForm(OTPAdminAuthenticationForm):
    """Le formulaire d'`OTPAdminSite`, dont l'appareil, faute de choix, est l'application TOTP.

    Le premier envoi ne porte pas le sélecteur, qui dépend du compte : sans appareil choisi, le
    jeton se vérifie contre l'application du compte, et elle seule — nom, mot de passe et code
    TOTP ouvrent l'admin en un envoi. `django-otp` 1.7 refuse ce cas (`device_required`) plutôt
    que d'essayer chaque appareil, ce qui comptait un échec contre les autres, codes de secours
    compris : un code de secours passe donc par le choix de son appareil. Un appareil choisi
    l'emporte, sous la garde de la bibliothèque, qui écarte celui d'un autre compte ; sans
    application confirmée, le formulaire reste celui de la bibliothèque. L'application se charge
    verrouillée (`select_for_update`), comme l'appareil choisi, que la bibliothèque charge par
    `Device.from_persistent_id(..., for_verify=True)`.

    Quand la page redemande le jeton, le sélecteur se présente sur l'application, faute d'autre
    choix : un formulaire lié rend la valeur envoyée (`BoundField.value`), et non `initial`.
    """

    def _chosen_device(self, user: User) -> Device | None:
        if self.cleaned_data.get(DEVICE_FIELD):
            return super()._chosen_device(user)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return authenticator_app(user).select_for_update().first()

    def _update_form(self, user: User) -> None:
        super()._update_form(user)  # pyright: ignore[reportUnknownMemberType]
        if not self.cleaned_data.get(DEVICE_FIELD) and (app := authenticator_app(user).first()):
            # Une copie : `request.POST` est immuable, et la décompression d'un `QueryDict`
            # en dictionnaire rend des listes de valeurs.
            data = QueryDict(mutable=True)
            data.update(self.data)
            data[DEVICE_FIELD] = app.persistent_id
            self.data = data


class SecondFactorAdminSite(OTPAdminSite):
    """`OTPAdminSite`, dont la page de connexion ne porte plus le bouton de défi, et dont le
    formulaire prend l'application TOTP quand aucun appareil n'est choisi.

    `access/login.html` étend le gabarit de la bibliothèque et n'en redéfinit que le bloc
    `content`, recopié sans ce bouton : le choix de l'appareil, les champs, les styles et
    `form.media` restent les siens. Un nom propre au projet plutôt qu'un homonyme du gabarit de la
    bibliothèque, qui ne l'emporterait que par l'ordre d'`INSTALLED_APPS`. `test_admin_access.py`
    épingle l'empreinte de ce gabarit : une montée de `django-otp` qui le change rougit, et le bloc
    recopié se relit.

    `has_permission`, qui exige `is_verified()`, reste celui d'`OTPAdminSite`.
    """

    login_form = SecondFactorAuthenticationForm
    login_template = "access/login.html"
