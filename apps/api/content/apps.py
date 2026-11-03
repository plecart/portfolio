"""Configuration de l'application de contenu."""

from config import strings
from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save

from content.cache import purge_after_commit


class ContentConfig(AppConfig):
    """Donne à l'application son nom français dans l'admin, et branche la purge du cache du
    contenu sur ses écritures."""

    name = "content"
    verbose_name = strings.CONTENT

    def ready(self) -> None:
        """Chaque enregistrement ou suppression d'une ligne d'un modèle de l'application vide le
        cache du contenu après validation (brief de #11, décision 3) : un modèle ajouté y entre
        sans rien changer ici."""
        for model in self.get_models():
            post_save.connect(purge_after_commit, sender=model)
            post_delete.connect(purge_after_commit, sender=model)
