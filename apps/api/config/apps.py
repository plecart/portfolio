"""Configurations d'applications tierces propres au projet."""

from django.contrib.staticfiles.apps import StaticFilesConfig as DjangoStaticFilesConfig


class StaticFilesConfig(DjangoStaticFilesConfig):
    """`django.contrib.staticfiles`, dont la collecte écarte aussi les fichiers de `ninja`.

    `ninja` n'est installé que pour sa commande d'export du schéma (brief de #10, décision 10) :
    ses docs interactives sont désactivées, et leurs scripts — près de 8 Mo de Swagger et de
    ReDoc — n'ont rien à faire dans l'image ni sous `/static/`. Une sous-classe qui étend
    `ignore_patterns` est la voie que la doc de Django donne (« Customizing the ignored pattern
    list ») : le motif vaut pour toute collecte, celle du build de l'image comme celle des tests.
    Il écarte tout fichier ou dossier nommé `ninja` — aucun autre n'en porte le nom.
    """

    # Un attribut de classe mutable, comme Django le déclare : `ClassVar` contredirait le type
    # hérité, que pyright tient pour un attribut d'instance.
    ignore_patterns = [*DjangoStaticFilesConfig.ignore_patterns, "ninja"]  # noqa: RUF012
