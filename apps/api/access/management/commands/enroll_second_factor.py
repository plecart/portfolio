"""`manage.py enroll_second_factor` : enrôle le second facteur de l'unique superutilisateur (#6).

Sans argument, lancée à la main dans le conteneur `api` (`CONTRIBUTING.md`, `infra/RUNBOOK.md`).
Elle remplace les appareils du compte par une application TOTP et dix codes de secours à usage
unique, puis imprime une seule fois l'URI `otpauth://` que l'application lit, et les codes : rien
ne les réaffiche. Relancée, elle ré-enrôle — l'ancienne application et les anciens codes ne valent
plus.

Elle refuse — sortie non nulle — sans superutilisateur, ou avec plusieurs : l'admin n'en a qu'un.
"""

from config import strings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_static.models import (  # pyright: ignore[reportMissingTypeStubs]
    StaticDevice,
    StaticToken,
)
from django_otp.plugins.otp_totp.models import TOTPDevice  # pyright: ignore[reportMissingTypeStubs]

BACKUP_CODE_COUNT = 10

URI_HEADER = "URI à ouvrir dans l'application d'authentification :"
BACKUP_CODES_HEADER = "Codes de secours, chacun à usage unique :"

NOT_ONE_SUPERUSER = (
    "l'admin a un seul superutilisateur, que pose ensure_superuser ; la base en compte {count}"
)


def _enroll(user: User) -> tuple[str, list[str]]:
    """Remplace les appareils de `user` par une application TOTP et des codes de secours neufs.

    Returns:
        L'URI de l'application et les codes.
    """
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()
    app = TOTPDevice(user=user, name=strings.OTP_DEVICE_TOTP)
    app.save()
    backup = StaticDevice(user=user, name=strings.OTP_DEVICE_BACKUP_CODES)
    backup.save()
    codes = [StaticToken.random_token() for _ in range(BACKUP_CODE_COUNT)]
    StaticToken.objects.bulk_create(StaticToken(device=backup, token=code) for code in codes)
    return app.config_url, codes


class Command(BaseCommand):
    help = "Enrôle le second facteur de l'unique superutilisateur : application TOTP et codes."

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        superusers = list(User.objects.filter(is_superuser=True))
        if len(superusers) != 1:
            raise CommandError(NOT_ONE_SUPERUSER.format(count=len(superusers)))

        uri, codes = _enroll(superusers[0])
        self.stdout.write("\n".join([URI_HEADER, uri, BACKUP_CODES_HEADER, *codes]))
