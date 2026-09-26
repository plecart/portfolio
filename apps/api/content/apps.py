"""Configuration de l'application de contenu."""

from config import strings
from django.apps import AppConfig


class ContentConfig(AppConfig):
    """Donne à l'application son nom français dans l'admin."""

    name = "content"
    verbose_name = strings.CONTENT
