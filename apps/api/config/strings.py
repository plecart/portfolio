"""Catalogue des chaînes du back : tout texte du projet que l'admin affiche vient d'ici.

Un seul module de constantes françaises aux noms anglais (cadrage §3, « libellés dans un
catalogue de chaînes unique »), lu par les modèles, les validateurs et l'admin. Ni gettext ni
fichier `.po` : le contenu est en français seulement. Les écrans et messages propres à Django,
eux, sont traduits par `LANGUAGE_CODE` (`config/settings.py`).

Noms de modèle et de champ en minuscules : Django met la majuscule où il la faut. Les libellés
des modèles, des champs — choix compris — et des contraintes sont recopiés dans les migrations :
en changer un demande une migration, que `test_migrations.py` réclame.
"""

# Application de contenu
CONTENT = "Contenu"

# Technologie
TECHNOLOGY = "technologie"
TECHNOLOGIES = "technologies"
TECHNOLOGY_NAME = "nom"
TECHNOLOGY_KIND = "type"
TECHNOLOGY_ICON = "icône"
TECHNOLOGY_WEBSITE = "site"
TECHNOLOGY_WEBSITE_OPEN = "{name} : ouvrir le site"
TECHNOLOGY_WEBSITE_NONE = "Aucun site"
TECHNOLOGY_KIND_LANGUAGE = "Langage"
TECHNOLOGY_KIND_FRAMEWORK = "Framework"
TECHNOLOGY_KIND_INFRASTRUCTURE = "Infra"
TECHNOLOGY_KIND_TOOL = "Outil"
TECHNOLOGY_NAME_TAKEN = "Une technologie porte déjà ce nom, majuscules et minuscules confondues."
TECHNOLOGY_NAME_MISSING = "Une technologie porte un nom."
TECHNOLOGY_KIND_UNKNOWN = "Le type d’une technologie est langage, framework, infra ou outil."
TECHNOLOGY_ICON_MISSING = "Une technologie porte une icône."
ICON_NOT_SVG = "L’icône doit être un fichier SVG."
