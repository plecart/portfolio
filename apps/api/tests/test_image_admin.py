"""Tests des images d'un projet dans l'écran Projet : le bloc de la couverture, exigée, son aperçu
et son état (brief de #9, décisions 2, 3 et 11). Les règles des images elles-mêmes sont éprouvées
dans `test_images.py` et `test_cover.py` ; ici, ce que l'écran en montre et en refuse."""

import re

import pytest
from config import strings
from content.models import Cover, ProcessingState, Project
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import BaseForm
from django.test import Client
from django.urls import reverse
from django.utils.html import escape
from django.utils.text import capfirst
from factories import BLANK, image_upload, project, saved, technology
from test_project_admin import (
    COVER,
    LINES,
    cover_row,
    inline_group,
    line,
    new_project_data,
    refused_rows,
    rendered_data,
    saved_project,
)

# Chaque colonne du bloc de la couverture, dans l'ordre, et son libellé du catalogue.
COVER_COLUMNS = {
    "preview": strings.IMAGE_PREVIEW,
    "original": strings.IMAGE_ORIGINAL,
    "caption": strings.IMAGE_CAPTION,
    "state": strings.IMAGE_STATE,
}

# Ce que le bloc de la couverture refuse, chaque fois avec le seul message du catalogue : sa
# forme, que la base porte sur des colonnes absentes du formulaire, sa légende, son fichier.
COVER_REFUSALS = [
    ("non carrée", {"original": image_upload(size=(1200, 1201))}, strings.COVER_NOT_SQUARE),
    ("trop petite", {"original": image_upload(size=(1199, 1199))}, strings.COVER_TOO_SMALL),
    ("légende vide", {"caption": ""}, strings.IMAGE_CAPTION_MISSING),
    ("légende faite d'espaces", {"caption": BLANK}, strings.IMAGE_CAPTION_MISSING),
    ("légende de 51 caractères", {"caption": "l" * 51}, strings.IMAGE_CAPTION_TOO_LONG),
    (
        "fichier qui n'est pas une image",
        {"original": SimpleUploadedFile("notes.png", b"Pas une image.")},
        strings.IMAGE_FORMAT_UNSUPPORTED,
    ),
    ("légende sans fichier", {"original": ""}, strings.IMAGE_ORIGINAL_MISSING),
]


def messages(form: BaseForm) -> list[str]:
    """Tous les refus qu'une ligne affiche, sous ses champs ou en tête."""
    return [str(message) for errors in form.errors.values() for message in errors]


def cover_group(page: str) -> str:
    """Le bloc de la couverture dans la page de l'écran Projet, jusqu'aux technologies — qui le
    suivent : un bloc rendu ailleurs rend une tranche vide."""
    return page[page.index(f'id="{COVER}-group"') : page.index(f'id="{LINES}-group"')]


@pytest.mark.django_db
def test_l_ecran_projet_montre_la_couverture_avant_les_technologies(admin_client: Client) -> None:
    """Un bloc titré « Couverture », au singulier, d'une seule ligne, sans ajout ni suppression,
    colonnes libellées du catalogue, rendu avant les technologies (décision 11)."""
    response = admin_client.get(reverse("admin:content_project_add"))
    block = inline_group(response, COVER)
    page = response.content.decode()

    assert [(field["name"], capfirst(str(field["label"]))) for field in block.fields()] == [
        (name, capfirst(label)) for name, label in COVER_COLUMNS.items()
    ]
    assert (block.formset.max_num, block.formset.can_delete) == (1, False)
    group = cover_group(page)
    assert escape(capfirst(strings.COVER)) in group
    assert escape(capfirst(strings.COVERS)) not in group


@pytest.mark.django_db
def test_l_admin_enregistre_un_projet_avec_sa_couverture_en_attente(admin_client: Client) -> None:
    """La couverture naît avec le projet, « en attente », sans variante : rien ici ne la traite."""
    data = new_project_data(admin_client, **line(0, saved(technology(name="Django")), 1))

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    made = Project.objects.get().cover
    assert (made.caption, made.state, made.variants) == (
        "La table des projets.",
        ProcessingState.PENDING,
        [],
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        {f"{COVER}-0-original": "", f"{COVER}-0-caption": ""},
        {f"{COVER}-TOTAL_FORMS": 0},
    ],
    ids=["bloc laissé vide", "aucun bloc envoyé"],
)
def test_l_admin_refuse_un_projet_sans_couverture(
    admin_client: Client, fields: dict[str, object]
) -> None:
    """Une couverture, toujours, brouillon compris (décision 2) : seconde règle hors base, après
    « au moins une technologie » ; un seul message, celui du catalogue, au-dessus du bloc."""
    data = new_project_data(admin_client, **line(0, saved(technology(name="Django")), 1), **fields)

    response = admin_client.post(reverse("admin:content_project_add"), data)

    block = inline_group(response, COVER).formset
    assert list(block.non_form_errors()) == [strings.PROJECT_COVER_MISSING]
    assert [messages(form) for form in block.forms if form.errors] == []
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_un_projet_ne_sans_couverture_la_recoit_a_son_prochain_enregistrement(
    admin_client: Client,
) -> None:
    """Aucune reprise de données (décision 2) : un projet du poste né avant l'écran n'a pas de
    couverture ; l'écran la lui demande au prochain enregistrement."""
    portfolio = saved(project())
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | line(0, saved(technology(name="Django")), 1)

    refusals = refused_rows(admin_client, url, data, COVER)
    response = admin_client.post(url, data | cover_row())

    assert refusals == [strings.PROJECT_COVER_MISSING]
    assert response.status_code == 302
    assert Cover.objects.filter(project=portfolio).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "message"),
    [(fields, message) for _, fields, message in COVER_REFUSALS],
    ids=[refusal for refusal, _, _ in COVER_REFUSALS],
)
def test_l_admin_refuse_une_couverture_hors_de_ses_regles(
    admin_client: Client, fields: dict[str, object], message: str
) -> None:
    """Chaque refus avec son seul message, sans rien enregistrer — la forme comprise, que Django
    n'éprouverait qu'en base : un formulaire écarte d'ordinaire les contraintes qui lisent un champ
    qu'il n'a pas, et la largeur et la hauteur n'y sont pas."""
    data = new_project_data(
        admin_client, **line(0, saved(technology(name="Django")), 1), **cover_row(**fields)
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 200
    assert messages(inline_group(response, COVER).formset.forms[0]) == [message]
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_l_ecran_accepte_une_couverture_sans_extension(admin_client: Client) -> None:
    """L'original est reconnu à son contenu, jamais à son nom (décision 6) : le bloc emploie le champ
    de formulaire de l'original, pas celui de Django."""
    data = new_project_data(
        admin_client,
        **line(0, saved(technology(name="Django")), 1),
        **cover_row(original=image_upload("photo", image_format="JPEG")),
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert (Project.objects.get().cover.original.name or "").endswith("/original.jpg")


@pytest.mark.django_db
def test_l_admin_refuse_une_seconde_couverture(admin_client: Client) -> None:
    """L'écran n'offre qu'une ligne ; un envoi qui en porte deux est refusé, et la couverture
    enregistrée reste seule."""
    portfolio = saved_project(saved(technology(name="Django")))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    second = {
        f"{COVER}-TOTAL_FORMS": 2,
        f"{COVER}-1-original": image_upload(),
        f"{COVER}-1-caption": "Une autre couverture.",
    }

    response = admin_client.post(url, rendered_data(admin_client, url) | second)

    assert response.status_code == 200
    assert Cover.objects.filter(project=portfolio).count() == 1


@pytest.mark.django_db
def test_l_auteur_remplace_le_fichier_de_la_couverture(admin_client: Client) -> None:
    """Le geste du bloc enregistré : choisir un autre fichier. La couverture le prend, et revient
    « en attente » (décision 5)."""
    portfolio = saved_project(saved(technology(name="Django")))
    before = portfolio.cover.original.name
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        f"{COVER}-0-original": image_upload(size=(1300, 1300))
    }

    response = admin_client.post(url, data)

    assert response.status_code == 302
    replaced = Cover.objects.get(project=portfolio)
    assert replaced.original.name != before
    assert (replaced.width, replaced.state) == (1300, ProcessingState.PENDING)


@pytest.mark.django_db
def test_l_apercu_montre_l_original_enregistre_et_son_etat_en_texte(admin_client: Client) -> None:
    """L'original dans un `<img>` : dimensions en attributs, sans `style` en ligne (CSP de #6),
    légende en texte alternatif (décision 11). L'état, en texte, ne se modifie pas."""
    portfolio = saved_project(saved(technology(name="Django")))
    made = portfolio.cover
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    page = admin_client.get(url).content.decode()

    group = cover_group(page)
    images = re.findall(r"<img [^>]*>", group)
    assert len(images) == 1
    assert f'src="{made.original.url}"' in images[0]
    assert f'alt="{escape(made.caption)}"' in images[0]
    assert re.search(r'width="\d+" height="\d+"', images[0])
    assert "style" not in images[0]
    assert escape(strings.PROCESSING_STATE_PENDING) in group
    assert f'name="{COVER}-0-state"' not in page


@pytest.mark.django_db
def test_une_couverture_choisie_mais_pas_enregistree_n_a_pas_d_apercu(admin_client: Client) -> None:
    """L'aperçu apparaît après l'enregistrement (décision 3) : sur un écran revenu en erreur, le
    fichier choisi n'est pas stocké, et rien ne le montre."""
    data = new_project_data(admin_client)

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 200
    assert "<img " not in cover_group(response.content.decode())


@pytest.mark.django_db
def test_la_page_de_suppression_d_un_projet_nomme_sa_couverture(admin_client: Client) -> None:
    """Django y nomme chaque objet que la suppression emporte : la couverture, par son projet et
    sa légende, comme une technologie de projet."""
    portfolio = saved_project(saved(technology(name="Django")))

    page = admin_client.get(
        reverse("admin:content_project_delete", args=[portfolio.pk])
    ).content.decode()

    assert escape(f"{portfolio.title} · {portfolio.cover.caption}") in page
