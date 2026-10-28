"""`manage.py ensure_superuser` : pose l'unique superutilisateur de l'admin (cadrage §6.2).

Le point d'entrée du conteneur la joue après les migrations (`STARTUP_STEPS`,
`infra/api/entrypoint.sh`), sans argument : le nom et le mot de passe viennent des réglages
`ADMIN_USERNAME` et `ADMIN_PASSWORD` (`config/env.py`). Rejouée à chaque démarrage, elle crée le
compte une fois, puis n'écrit que ce qui a changé.

Elle refuse — sortie non nulle, donc conteneur arrêté — un nom ou un mot de passe vide, un mot de
passe que `AUTH_PASSWORD_VALIDATORS` rejette, et tout autre superutilisateur : l'admin n'en a qu'un.
Ni sa sortie ni ses refus ne citent le mot de passe : ils partent dans le journal du conteneur.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

CREATED = "superutilisateur créé"
UNCHANGED = "superutilisateur inchangé"
RIGHTS_RESTORED = "droits de superutilisateur rétablis"
PASSWORD_UPDATED = "mot de passe du superutilisateur mis à jour"

MISSING = "ADMIN_USERNAME et ADMIN_PASSWORD sont exigés, non vides"
ANOTHER_SUPERUSER = (
    "un autre superutilisateur existe : l'admin n'en a qu'un, ADMIN_USERNAME le nomme"
)
WEAK_PASSWORD = "ADMIN_PASSWORD refusé par les validateurs de Django : "


def _update(user: User, password: str) -> str:
    """Rend ses droits et son mot de passe à un compte existant, sans rien écrire s'il les a.

    Returns:
        Ce qui a été écrit, `UNCHANGED` si rien ne l'a été.
    """
    written: list[str] = []
    if not (user.is_superuser and user.is_staff and user.is_active):
        user.is_superuser = user.is_staff = user.is_active = True
        written.append(RIGHTS_RESTORED)
    if not user.check_password(password):
        user.set_password(password)
        written.append(PASSWORD_UPDATED)
    if written:
        user.save()
    return ", ".join(written) or UNCHANGED


class Command(BaseCommand):
    help = "Crée ou met à jour l'unique superutilisateur, d'après ADMIN_USERNAME et ADMIN_PASSWORD."

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        username = User.normalize_username(settings.ADMIN_USERNAME)
        password: str = settings.ADMIN_PASSWORD.get_secret_value()
        if not username or not password:
            raise CommandError(MISSING)
        if User.objects.filter(is_superuser=True).exclude(username=username).exists():
            raise CommandError(ANOTHER_SUPERUSER)

        user = User.objects.filter(username=username).first()
        try:
            # L'utilisateur, même neuf, pour que la similarité au nom soit éprouvée.
            validate_password(password, user or User(username=username))
        except ValidationError as error:
            raise CommandError(WEAK_PASSWORD + " ".join(error.messages)) from error

        if user is None:
            User.objects.create_superuser(username, password=password)
            self.stdout.write(CREATED)
        else:
            self.stdout.write(_update(user, password))
