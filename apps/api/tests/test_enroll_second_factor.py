"""Tests d'`enroll_second_factor`, la commande qui enrôle le second facteur de l'unique
superutilisateur : un appareil TOTP et dix codes de secours, imprimés une seule fois.

Seuls les appareils confirmés comptent : un appareil qui ne l'est pas ne vérifie personne
(`OTPMiddleware`).
"""

from io import StringIO
from typing import cast

import pytest
from access.management.commands.enroll_second_factor import BACKUP_CODES_HEADER, URI_HEADER
from django.core.management import call_command
from django.core.management.base import CommandError
from django_otp.plugins.otp_static.models import (  # pyright: ignore[reportMissingTypeStubs]
    StaticDevice,
    StaticToken,
)
from django_otp.plugins.otp_totp.models import TOTPDevice  # pyright: ignore[reportMissingTypeStubs]
from test_admin_access import USERNAME, superuser

pytestmark = pytest.mark.django_db


def enroll() -> tuple[str, list[str]]:
    """Joue la commande, sans argument.

    Returns:
        L'URI et les codes qu'elle imprime, chacun sous son titre.
    """
    output = StringIO()
    call_command("enroll_second_factor", stdout=output)
    uri_header, uri, codes_header, *codes = output.getvalue().splitlines()
    assert (uri_header, codes_header) == (URI_HEADER, BACKUP_CODES_HEADER)
    return uri, codes


def enrolled_uri() -> str:
    """L'URI de l'unique application TOTP confirmée en base.

    `cast` : le gestionnaire des appareils (`DeviceManager`, `django_otp/models.py`) dérive de
    `Manager` sans le paramétrer, et ce qu'il rend est inconnu de pyright.
    """
    return cast(TOTPDevice, TOTPDevice.objects.get(confirmed=True)).config_url


def stored_codes() -> list[str]:
    """Les codes de secours confirmés en base, triés ; un code consommé n'y est plus."""
    return sorted(
        StaticToken.objects.filter(device__confirmed=True).values_list("token", flat=True)
    )


def test_la_commande_imprime_l_uri_de_l_appareil_et_dix_codes_distincts() -> None:
    superuser()

    uri, codes = enroll()

    assert uri.startswith("otpauth://totp/")
    assert uri == enrolled_uri()
    assert len(set(codes)) == len(codes) == 10
    assert sorted(codes) == stored_codes()


def test_relancee_elle_remplace_les_appareils_et_les_anciens_codes_ne_valent_plus() -> None:
    superuser()

    first_uri, first_codes = enroll()
    second_uri, second_codes = enroll()

    assert (TOTPDevice.objects.count(), StaticDevice.objects.count()) == (1, 1)
    assert enrolled_uri() == second_uri != first_uri
    assert stored_codes() == sorted(second_codes)
    assert not set(first_codes) & set(second_codes)


@pytest.mark.parametrize("usernames", [[], [USERNAME, "ancien"]], ids=["aucun", "deux"])
def test_sans_superutilisateur_unique_la_commande_refuse(usernames: list[str]) -> None:
    """L'admin n'a qu'un compte : la commande ne choisit pas entre deux."""
    for username in usernames:
        superuser(username)

    with pytest.raises(CommandError):
        enroll()

    assert (TOTPDevice.objects.count(), StaticDevice.objects.count()) == (0, 0)
