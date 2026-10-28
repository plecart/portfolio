"""`manage.py ensure_superuser` : pose l'unique superutilisateur de l'admin (cadrage §6.2).

Le point d'entrée du conteneur la joue après les migrations (`STARTUP_STEPS`,
`infra/api/entrypoint.sh`), sans argument : le nom et le mot de passe viennent des réglages
`ADMIN_USERNAME` et `ADMIN_PASSWORD` (`config/env.py`). Rejouée à chaque démarrage, elle crée le
compte une fois, puis n'écrit que ce qui a changé.

Elle refuse — sortie non nulle, donc conteneur arrêté — un nom ou un mot de passe vide, tout autre
compte d'admin, superutilisateur ou staff : l'admin n'en a qu'un ; et un mot de passe neuf, à la
création ou quand il change, que `AUTH_PASSWORD_VALIDATORS` rejette. Un mot de passe inchangé
n'est pas rejugé : une montée de Django qui durcit un validateur n'arrête pas `api`.
Ni sa sortie ni ses refus ne citent le mot de passe : ils partent dans le journal du conteneur.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

CREATED = "superutilisateur créé"
UNCHANGED = "superutilisateur inchangé"
RIGHTS_RESTORED = "droits de superutilisateur rétablis"
PASSWORD_UPDATED = "mot de passe du superutilisateur mis à jour"

MISSING = "ADMIN_USERNAME et ADMIN_PASSWORD sont exigés, non vides"
ANOTHER_ADMIN = (
    "un autre compte d'admin existe, superutilisateur ou staff : l'admin n'en a qu'un, "
    "ADMIN_USERNAME le nomme"
)
WEAK_PASSWORD = "ADMIN_PASSWORD refusé par les validateurs de Django : "


def _validate(password: str, user: User) -> None:
    """Soumet un mot de passe neuf aux validateurs de Django, `user` pour la similarité au nom.

    Raises:
        CommandError: leurs motifs, jamais le mot de passe.
    """
    try:
        validate_password(password, user)
    except ValidationError as error:
        raise CommandError(WEAK_PASSWORD + " ".join(error.messages)) from error


def _create(username: str, password: str) -> str:
    """Crée le compte, son mot de passe passé d'abord aux validateurs.

    Returns:
        `CREATED`.
    """
    _validate(password, User(username=username))
    User.objects.create_superuser(username, password=password)
    return CREATED


def _update(user: User, password: str) -> str:
    """Rend ses droits et son mot de passe à un compte existant, sans rien écrire s'il les a.

    Seul un mot de passe qui change passe les validateurs : celui en place n'est pas rejugé.

    Returns:
        Ce qui a été écrit, `UNCHANGED` si rien ne l'a été.
    """
    written: list[str] = []
    if not (user.is_superuser and user.is_staff and user.is_active):
        user.is_superuser = user.is_staff = user.is_active = True
        written.append(RIGHTS_RESTORED)
    if not user.check_password(password):
        _validate(password, user)
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
        admins = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True))
        if admins.exclude(username=username).exists():
            raise CommandError(ANOTHER_ADMIN)

        user = User.objects.filter(username=username).first()
        self.stdout.write(_create(username, password) if user is None else _update(user, password))
