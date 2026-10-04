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

# Technologie : modèle, champs et valeurs du type
TECHNOLOGY = "technologie"
TECHNOLOGIES = "technologies"
TECHNOLOGY_NAME = "nom"
TECHNOLOGY_KIND = "type"
TECHNOLOGY_ICON = "icône"
TECHNOLOGY_WEBSITE = "site"
TECHNOLOGY_KIND_LANGUAGE = "Langage"
TECHNOLOGY_KIND_FRAMEWORK = "Framework"
TECHNOLOGY_KIND_INFRASTRUCTURE = "Infra"
TECHNOLOGY_KIND_TOOL = "Outil"

# Technologie : libellés accessibles du symbole de lien, dans la liste de l'admin
TECHNOLOGY_WEBSITE_OPEN = "{name} : ouvrir le site"
TECHNOLOGY_WEBSITE_NONE = "Aucun site"

# Technologie : refus
TECHNOLOGY_NAME_TAKEN = "Une technologie porte déjà ce nom, majuscules et minuscules confondues."
TECHNOLOGY_NAME_MISSING = "Une technologie porte un nom."
TECHNOLOGY_KIND_UNKNOWN = "Le type d’une technologie est langage, framework, infra ou outil."
TECHNOLOGY_ICON_MISSING = "Une technologie porte une icône."
ICON_NOT_SVG = "L’icône doit être un fichier SVG."

# Projet : modèle, champs, valeurs du type et du statut
PROJECT = "projet"
PROJECTS = "projets"
PROJECT_TITLE = "titre"
PROJECT_SLUG = "slug"
PROJECT_SUMMARY = "résumé"
PROJECT_DESCRIPTION = "description"
PROJECT_KIND = "type"
PROJECT_STATUS = "statut"
PROJECT_STARTED_ON = "date de début"
PROJECT_FINISHED_ON = "date de fin"
PROJECT_CLIENT = "client"
PROJECT_REPOSITORY_URL = "lien du dépôt"
PROJECT_DEMO_URL = "lien de la démo"
PROJECT_SHOWCASE = "vitrine"
PROJECT_PUBLISHED = "publié"
PROJECT_CREATED_AT = "créé le"
PROJECT_UPDATED_AT = "modifié le"
PROJECT_KIND_PERSONAL = "Perso"
PROJECT_KIND_PROFESSIONAL = "Pro"
PROJECT_KIND_SCHOOL = "École"
PROJECT_STATUS_ONGOING = "En cours"
PROJECT_STATUS_FINISHED = "Terminé"
PROJECT_STATUS_ARCHIVED = "Archivé"

# Projet : refus
PROJECT_SLUG_TAKEN = "Un projet porte déjà ce slug."
PROJECT_SLUG_INVALID = (
    "Le slug d’un projet est fait de lettres sans accent, de chiffres, de traits d’union et de "
    "soulignés."
)
PROJECT_TITLE_MISSING = "Un projet porte un titre."
PROJECT_TITLE_TOO_LONG = "Le titre d’un projet tient en 30 caractères au plus."
PROJECT_SUMMARY_MISSING = "Un projet porte un résumé."
PROJECT_SUMMARY_TOO_LONG = "Le résumé d’un projet tient en 120 caractères au plus."
PROJECT_SUMMARY_WORD_TOO_LONG = (
    "Aucun mot du résumé ne dépasse 20 caractères ; espaces et traits d’union séparent les mots, "
    "pas les espaces insécables."
)
PROJECT_DESCRIPTION_MISSING = "Un projet porte une description, et pas seulement des espaces."
PROJECT_KIND_UNKNOWN = "Le type d’un projet est perso, pro ou école."
PROJECT_STATUS_UNKNOWN = "Le statut d’un projet est en cours, terminé ou archivé."
PROJECT_FINISHED_ON_MISSING = "Un projet terminé ou archivé porte une date de fin."
PROJECT_ONGOING_FINISHED = "Un projet en cours n’a pas de date de fin."
PROJECT_DATES_REVERSED = "La date de fin d’un projet ne précède pas sa date de début."
PROJECT_SHOWCASE_TAKEN = "Un autre projet est déjà la vitrine : un seul l’est à la fois."

# Technologie de projet : modèle et champ ; le projet et la technologie qu'elle lie portent leurs
# propres noms
PROJECT_TECHNOLOGY = "technologie de projet"
PROJECT_TECHNOLOGIES = "technologies de projet"
PROJECT_TECHNOLOGY_POSITION = "position"

# Technologie de projet : refus
PROJECT_TECHNOLOGY_TAKEN = "Cette technologie figure déjà dans le projet."
PROJECT_TECHNOLOGIES_MISSING = "Un projet emploie au moins une technologie."

# Section de fiche technique : modèle et champs
SECTION = "section"
SECTIONS = "sections"
SECTION_TITLE = "titre"
SECTION_ANCHOR = "ancre"
SECTION_BODY = "corps"
SECTION_POSITION = "position"

# Section de fiche technique : le titre de leur tableau dans l'écran Projet
SECTIONS_HEADING = "Fiche technique"

# Section de fiche technique : refus
SECTION_TITLE_MISSING = "Une section porte un titre."
SECTION_TITLE_TOO_LONG = "Le titre d’une section tient en 40 caractères au plus."
SECTION_ANCHOR_INVALID = (
    "L’ancre d’une section est faite de lettres sans accent, de chiffres et de traits d’union."
)
SECTION_ANCHOR_TAKEN = "Une autre section de ce projet porte déjà cette ancre."
SECTION_BODY_MISSING = "Une section porte un texte, et pas seulement des espaces."

# Image d'un projet, couverture ou image de galerie : refus de l'original
IMAGE_FORMAT_UNSUPPORTED = "L’image doit être un fichier JPEG, PNG ou WebP."
IMAGE_TOO_LARGE = "L’image pèse 10 Mo au plus."

# Aperçu Markdown de l'admin, sous la description d'un projet et le corps d'une section : sa
# légende, et ce qu'il montre quand il ne peut pas se rafraîchir
MARKDOWN_PREVIEW = "Aperçu"
MARKDOWN_PREVIEW_FAILED = "Aperçu indisponible."

# Lignes en ligne de l'admin : la colonne et la poignée qui les ordonnent par glisser-déposer
ADMIN_ROW_ORDER = "ordre"
ADMIN_ROW_MOVE = "Déplacer la ligne : la faire glisser, ou flèches haut et bas"
