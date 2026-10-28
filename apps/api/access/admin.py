"""L'admin réduit au contenu (cadrage §6.2) : ni « Groupes », ni « Utilisateurs », ni les appareils
du second facteur.

L'unique compte vient d'`ensure_superuser`, son second facteur d'`enroll_second_factor` : un écran
de compte ou d'appareil serait une autre voie d'en ajouter un. `auth`, `otp_totp` et `otp_static`
enregistrent ces écrans dans leur propre module `admin`, que l'autodécouverte importe avant
celui-ci (ordre d'`INSTALLED_APPS`) ; un écran absent ferait échouer le retrait (`NotRegistered`).
"""

from django.contrib import admin
from django.contrib.auth.models import Group, User
from django_otp.plugins.otp_static.models import StaticDevice  # pyright: ignore[reportMissingTypeStubs]
from django_otp.plugins.otp_totp.models import TOTPDevice  # pyright: ignore[reportMissingTypeStubs]

admin.site.unregister([Group, User, TOTPDevice, StaticDevice])
