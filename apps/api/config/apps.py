"""Configurations d'applications tierces propres au projet."""

from django.contrib.admin.apps import AdminConfig as DjangoAdminConfig
from django.contrib.staticfiles.apps import StaticFilesConfig as DjangoStaticFilesConfig


class AdminConfig(DjangoAdminConfig):
    """`django.contrib.admin`, dont le site par défaut exige un second facteur (#6).

    `access.site.SecondFactorAdminSite` : l'`OTPAdminSite` de `django-otp`, sans le bouton de défi
    de sa page de connexion (#215). Son formulaire demande, après le mot de passe, l'appareil et son
    jeton, et son `has_permission` exige `is_verified()` — sans second facteur, seule la page de
    connexion est servie. `default_site` est la voie que la doc de Django donne (« Overriding the
    default admin site ») : un chemin pointé, résolu au premier accès à `admin.site` ;
    `admin.site`, les enregistrements et `config/urls.py` restent tels quels.

    Ici et non dans `access/apps.py` : Django prend pour configuration d'une application la seule
    sous-classe d'`AppConfig` de son module `apps` (`AppConfig.create`), et celle-ci hérite de
    `default = True` — `access` deviendrait l'admin.
    """

    default_site = "access.site.SecondFactorAdminSite"


class StaticFilesConfig(DjangoStaticFilesConfig):
    """`django.contrib.staticfiles`, dont la collecte écarte aussi les fichiers de `ninja`.

    `ninja` n'est installé que pour sa commande d'export du schéma (brief de #10, décision 10) :
    ses docs interactives sont désactivées, et leurs scripts — près de 8 Mo de Swagger et de
    ReDoc — n'ont rien à faire dans l'image. Une sous-classe qui étend `ignore_patterns` est la
    voie que la doc de Django donne (« Customizing the ignored pattern list ») : le motif vaut pour
    toute collecte, celle du build de l'image comme celle des tests. Il écarte tout fichier ou
    dossier nommé `ninja` — aucun autre n'en porte le nom.

    La collecte seulement : en `DEBUG`, WhiteNoise lit les fichiers par les *finders*, que ce
    motif ne filtre pas — le poste sert encore `/static/ninja/`, l'image non.
    """

    # Un attribut de classe mutable, comme Django le déclare : `ClassVar` contredirait le type
    # hérité, que pyright tient pour un attribut d'instance.
    ignore_patterns = [*DjangoStaticFilesConfig.ignore_patterns, "ninja"]  # noqa: RUF012
