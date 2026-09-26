"""Lire les refus d'une validation de modèle, pour les comparer aux paires du catalogue."""

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError


def refusals(error: ValidationError, field: str = NON_FIELD_ERRORS) -> list[tuple[str | None, str]]:
    """Les refus que `error` porte pour `field`, chacun en paire (code, message).

    Une paire et jamais le code seul : un refus au bon code et au mauvais message afficherait à
    l'auteur un texte hors du catalogue. Par défaut, les refus qui ne visent aucun champ — ceux
    des contraintes du modèle.
    """
    return [(refusal.code, str(refusal.message)) for refusal in error.error_dict[field]]
