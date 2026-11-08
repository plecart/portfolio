"""Tests des images d'un projet dans l'écran Projet : le tableau de la galerie, ordonnable, exigé,
dont la première image est la couverture ; ses aperçus et ses états (brief de #9, décisions 2, 3,
4 et 11). Les règles de chaque image sont éprouvées dans `test_images.py` ; ici, ce que l'écran en
montre et en refuse, et la forme de la couverture, qu'il est seul à tenir."""

import re
from pathlib import Path

import pytest
from config import strings
from content.inlines import HANDLE_CLASS
from content.models import COVER_MIN_SIDE, GalleryImage, ProcessingState, Project
from django.contrib.admin.helpers import InlineAdminFormSet
from django.contrib.staticfiles import finders
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import BaseForm
from django.templatetags.static import static
from django.test import Client
from django.urls import reverse
from django.utils.html import escape
from django.utils.text import capfirst
from factories import BLANK, gallery_image, image_upload, project, saved, technology
from pytest_django import DjangoCaptureOnCommitCallbacks
from test_project_admin import (
    GALLERY,
    INLINE_ROWS_SCRIPT,
    INLINE_ROWS_STYLE,
    group,
    image_row,
    inline_group,
    line,
    new_project_data,
    refused_rows,
    rendered_data,
    saved_project,
)

# La feuille de l'aperçu des images (`GalleryInline`).
IMAGE_PREVIEW_STYLE = "content/admin/image_preview.css"

# La classe de l'aperçu, que la feuille lit : écrite ici et non lue sur l'admin, pour qu'un nom
# changé d'un seul côté fasse rougir ce fichier.
PREVIEW_CLASS = "image-preview"

# Les colonnes d'une image, dans l'ordre, et leur libellé du catalogue.
IMAGE_COLUMNS = {
    "preview": strings.IMAGE_PREVIEW,
    "original": strings.IMAGE_ORIGINAL,
    "caption": strings.IMAGE_CAPTION,
    "state": strings.IMAGE_STATE,
}

# Ce qu'une ligne d'image refuse, chaque fois avec le seul message du catalogue : sa légende, son
# fichier.
IMAGE_REFUSALS = [
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

# Le côté minimal de la couverture (spec §1.11 et §7), lu sur le modèle par son nom (brief de #242,
# décision 6) : les bornes s'éprouvent de part et d'autre, et le message les nomme.
MIN_SIDE = COVER_MIN_SIDE

# Les formes que la couverture refuse, bornes éprouvées des deux côtés, chacune avec ses refus.
SHAPE_REFUSALS = [
    (
        f"{MIN_SIDE - 1} × {MIN_SIDE - 1}",
        (MIN_SIDE - 1, MIN_SIDE - 1),
        [strings.GALLERY_COVER_TOO_SMALL],
    ),
    (f"{MIN_SIDE} × {MIN_SIDE + 1}", (MIN_SIDE, MIN_SIDE + 1), [strings.GALLERY_COVER_NOT_SQUARE]),
    (f"{MIN_SIDE + 1} × {MIN_SIDE}", (MIN_SIDE + 1, MIN_SIDE), [strings.GALLERY_COVER_NOT_SQUARE]),
    # Le petit côté compte : plus large que la borne, mais trop basse.
    (
        f"{MIN_SIDE + 100} × {MIN_SIDE - 100}",
        (MIN_SIDE + 100, MIN_SIDE - 100),
        [strings.GALLERY_COVER_NOT_SQUARE, strings.GALLERY_COVER_TOO_SMALL],
    ),
]

# Une image libre, qui ne peut pas être la couverture : en paysage, assez haute pour ne recevoir
# qu'un refus en tête.
LANDSCAPE = (MIN_SIDE + 400, MIN_SIDE)


def with_rows(count: int) -> dict[str, object]:
    """Le formulaire de gestion d'une galerie de `count` lignes : l'écran d'ajout n'en montre
    qu'une, le bouton « Ajouter » de l'admin en ajoute d'autres."""
    return {f"{GALLERY}-TOTAL_FORMS": count}


def messages(form: BaseForm) -> list[str]:
    """Tous les refus qu'une ligne affiche, sous ses champs ou en tête."""
    return [str(message) for errors in form.errors.values() for message in errors]


def columns(block: InlineAdminFormSet) -> list[tuple[str, str]]:
    """Les colonnes d'un tableau en ligne, dans l'ordre : nom du champ et libellé affiché."""
    return [(str(field["name"]), capfirst(str(field["label"]))) for field in block.fields()]


def with_landscape_second() -> tuple[Project, str]:
    """Un projet enregistré dont la galerie porte la couverture, carrée, puis une image en
    paysage ; et l'adresse de son écran."""
    portfolio = saved_project(saved(technology(name="Django")))
    saved(gallery_image(portfolio, original=image_upload(size=LANDSCAPE), position=2))
    return portfolio, reverse("admin:content_project_change", args=[portfolio.pk])


@pytest.mark.django_db
def test_l_ecran_projet_montre_la_galerie_en_tableau_ordonnable(admin_client: Client) -> None:
    """Un tableau titré « Galerie », colonnes libellées du catalogue, des poignées de tri : l'auteur
    ajoute, retire et ordonne ses images par glisser-déposer (décision 11, ADR 0013). Il charge la
    feuille de ses aperçus, et le script et la feuille des lignes ordonnables."""
    response = admin_client.get(reverse("admin:content_project_add"))
    gallery = inline_group(response, GALLERY)

    assert gallery.opts.verbose_name_plural == strings.GALLERY_HEADING
    assert columns(gallery) == [
        ("move", capfirst(strings.ADMIN_ROW_ORDER)),
        *((name, capfirst(label)) for name, label in IMAGE_COLUMNS.items()),
        ("position", capfirst(strings.GALLERY_IMAGE_POSITION)),
    ]
    assert HANDLE_CLASS in group(response.content.decode(), GALLERY)
    for asset in (IMAGE_PREVIEW_STYLE, INLINE_ROWS_SCRIPT, INLINE_ROWS_STYLE):
        assert static(asset) in str(gallery.media)


@pytest.mark.django_db
def test_l_ecran_d_ajout_ne_montre_qu_une_ligne_de_galerie(admin_client: Client) -> None:
    """À l'ajout, la ligne obligatoire est la seule, vide (arrêt visuel du 2026-10-14) ; un projet
    enregistré montre ses images et une ligne neuve en plus."""
    portfolio = saved_project(saved(technology(name="Django")))
    change = reverse("admin:content_project_change", args=[portfolio.pk])

    added = inline_group(admin_client.get(reverse("admin:content_project_add")), GALLERY)
    changed = inline_group(admin_client.get(change), GALLERY)

    assert len(added.formset.forms) == 1
    assert len(changed.formset.forms) == 2


@pytest.mark.django_db
def test_l_admin_enregistre_un_projet_avec_sa_couverture_en_attente(admin_client: Client) -> None:
    """La couverture naît avec le projet, première image de sa galerie, « en attente », sans
    variante : rien ici ne la traite."""
    data = new_project_data(admin_client, **line(0, saved(technology(name="Django")), 1))

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    made = Project.objects.get().gallery.get()
    assert (made.caption, made.state, made.variants) == (
        "La table des projets.",
        ProcessingState.PENDING,
        [],
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        {f"{GALLERY}-0-original": "", f"{GALLERY}-0-caption": ""},
        {f"{GALLERY}-TOTAL_FORMS": 0},
    ],
    ids=["lignes laissées vides", "aucune ligne envoyée"],
)
def test_l_admin_refuse_un_projet_sans_image(
    admin_client: Client, fields: dict[str, object]
) -> None:
    """Une image au moins, toujours, brouillon compris (décision 2) : un seul message, celui du
    catalogue, au-dessus du tableau."""
    data = new_project_data(admin_client, **line(0, saved(technology(name="Django")), 1), **fields)

    response = admin_client.post(reverse("admin:content_project_add"), data)

    gallery = inline_group(response, GALLERY).formset
    assert list(gallery.non_form_errors()) == [strings.PROJECT_IMAGES_MISSING]
    assert [messages(form) for form in gallery.forms if form.errors] == []
    assert not Project.objects.exists()


@pytest.mark.django_db
def test_un_projet_ne_sans_image_recoit_sa_couverture_a_son_prochain_enregistrement(
    admin_client: Client,
) -> None:
    """Aucune reprise de données (décision 2) : un projet du poste né sans image n'a pas de
    couverture ; l'écran la lui demande au prochain enregistrement."""
    portfolio = saved(project())
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | line(0, saved(technology(name="Django")), 1)

    refusals = refused_rows(admin_client, url, data, GALLERY)
    response = admin_client.post(url, data | image_row(GALLERY))

    assert refusals == [strings.PROJECT_IMAGES_MISSING]
    assert response.status_code == 302
    assert GalleryImage.objects.filter(project=portfolio).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "message"),
    [(fields, message) for _, fields, message in IMAGE_REFUSALS],
    ids=[refusal for refusal, _, _ in IMAGE_REFUSALS],
)
def test_l_admin_refuse_une_image_hors_de_ses_regles(
    admin_client: Client, fields: dict[str, object], message: str
) -> None:
    """Chaque refus avec son seul message, sans rien enregistrer — une ligne légendée sans fichier
    comprise (décision 11). La ligne refusée est la première : la forme de la couverture ne s'y
    juge pas, ses dimensions ne décrivent rien d'admis."""
    data = new_project_data(
        admin_client, **line(0, saved(technology(name="Django")), 1), **image_row(GALLERY, **fields)
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 200
    assert messages(inline_group(response, GALLERY).formset.forms[0]) == [message]
    assert not Project.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "size", [(MIN_SIDE, MIN_SIDE), (MIN_SIDE + 1, MIN_SIDE + 1)], ids=["à la borne", "au-delà"]
)
def test_une_couverture_carree_d_au_moins_le_cote_minimal_est_acceptee(
    admin_client: Client, size: tuple[int, int]
) -> None:
    data = new_project_data(
        admin_client,
        **line(0, saved(technology(name="Django")), 1),
        **image_row(GALLERY, original=image_upload(size=size)),
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("size", "expected"),
    [(size, expected) for _, size, expected in SHAPE_REFUSALS],
    ids=[shape for shape, _, _ in SHAPE_REFUSALS],
)
def test_l_admin_refuse_une_couverture_hors_de_sa_forme(
    admin_client: Client, size: tuple[int, int], expected: list[str]
) -> None:
    """La première image est la couverture : carrée, `MIN_SIDE` px de côté au moins (décision 8).
    Ses refus s'affichent sous sa ligne, avec les messages du catalogue, et rien ne s'enregistre."""
    data = new_project_data(
        admin_client,
        **line(0, saved(technology(name="Django")), 1),
        **image_row(GALLERY, original=image_upload(size=size)),
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 200
    assert messages(inline_group(response, GALLERY).formset.forms[0]) == expected
    assert not Project.objects.exists()


def test_le_refus_d_une_couverture_trop_petite_nomme_le_cote_minimal() -> None:
    """Le catalogue ne peut pas lire la constante du modèle, qui l'importe : le message l'écrit, et
    ce test les tient d'accord (brief de #242, décision 6)."""
    assert f"au moins {MIN_SIDE} px de côté" in strings.GALLERY_COVER_TOO_SMALL


@pytest.mark.django_db
def test_une_couverture_enregistree_sous_le_cote_minimal_est_refusee_au_prochain_enregistrement(
    admin_client: Client,
) -> None:
    """Refus strict (brief de #242, décision 2) : une couverture enregistrée plus petite — sous une
    borne plus basse — est jugée à chaque enregistrement du projet, son fichier inchangé ; le projet
    ne s'enregistre plus tant qu'une image conforme ne la remplace pas."""
    portfolio = saved_project(saved(technology(name="Django")))
    cover = portfolio.gallery.get()
    cover.original = image_upload(size=(MIN_SIDE - 1, MIN_SIDE - 1))
    cover.save()
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    response = admin_client.post(url, rendered_data(admin_client, url))

    assert response.status_code == 200
    forms = inline_group(response, GALLERY).formset.forms
    assert messages(forms[0]) == [strings.GALLERY_COVER_TOO_SMALL]


@pytest.mark.django_db
def test_une_image_libre_a_la_seconde_place_est_acceptee(admin_client: Client) -> None:
    """Seule la première image est la couverture : les autres sont libres (spec §1.11)."""
    data = new_project_data(
        admin_client,
        **line(0, saved(technology(name="Django")), 1),
        **image_row(GALLERY, 0, position=1),
        **image_row(GALLERY, 1, original=image_upload(size=LANDSCAPE), position=2),
        **with_rows(2),
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert [image.width for image in Project.objects.get().gallery.all()] == [
        MIN_SIDE,
        LANDSCAPE[0],
    ]


@pytest.mark.django_db
def test_une_image_libre_glissee_en_tete_est_refusee(admin_client: Client) -> None:
    """Glisser une image en tête en fait la couverture, et lui en applique les règles : l'image en
    paysage est refusée sous sa ligne, et la galerie garde son ordre."""
    portfolio, url = with_landscape_second()
    swapped = {f"{GALLERY}-0-position": 2, f"{GALLERY}-1-position": 1}

    response = admin_client.post(url, rendered_data(admin_client, url) | swapped)

    assert response.status_code == 200
    forms = inline_group(response, GALLERY).formset.forms
    assert [messages(form) for form in forms[:2]] == [[], [strings.GALLERY_COVER_NOT_SQUARE]]
    assert [image.width for image in portfolio.gallery.all()] == [MIN_SIDE, LANDSCAPE[0]]


@pytest.mark.django_db
def test_retirer_la_couverture_fait_de_l_image_suivante_la_couverture(admin_client: Client) -> None:
    """Une ligne retirée ne compte plus : l'image suivante devient la couverture, et en reçoit les
    règles — l'image en paysage est refusée, et la couverture retirée reste."""
    portfolio, url = with_landscape_second()

    response = admin_client.post(
        url, rendered_data(admin_client, url) | {f"{GALLERY}-0-DELETE": "on"}
    )

    assert response.status_code == 200
    forms = inline_group(response, GALLERY).formset.forms
    assert messages(forms[1]) == [strings.GALLERY_COVER_NOT_SQUARE]
    assert portfolio.gallery.count() == 2


@pytest.mark.django_db
def test_une_couverture_enregistree_arrivee_sans_position_reste_la_couverture(
    admin_client: Client,
) -> None:
    """Une ligne enregistrée arrivée sans position — ni l'écran ni le script n'en produisent —
    garde la sienne à l'enregistrement (`SortableFormSet`) : elle garde aussi sa place de
    couverture, et l'image en paysage qui la suit n'est pas jugée comme telle."""
    portfolio, url = with_landscape_second()

    response = admin_client.post(
        url, rendered_data(admin_client, url) | {f"{GALLERY}-0-position": ""}
    )

    assert response.status_code == 302
    assert [image.width for image in portfolio.gallery.all()] == [MIN_SIDE, LANDSCAPE[0]]


@pytest.mark.django_db
def test_sans_le_script_la_premiere_ligne_du_formulaire_est_la_couverture(
    admin_client: Client,
) -> None:
    """Sans le script — désactivé, ou en échec —, les lignes neuves arrivent sans position et se
    rangent dans l'ordre du formulaire : la première est la couverture."""
    data = new_project_data(
        admin_client,
        **line(0, saved(technology(name="Django")), 1),
        **image_row(GALLERY, 0, original=image_upload(size=LANDSCAPE), position=""),
        **image_row(GALLERY, 1, position=""),
        **with_rows(2),
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 200
    forms = inline_group(response, GALLERY).formset.forms
    assert [messages(form) for form in forms[:2]] == [[strings.GALLERY_COVER_NOT_SQUARE], []]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "placed_ahead",
    [{}, {f"{GALLERY}-0-DELETE": "on", **with_rows(3)}],
    ids=["après les lignes enregistrées", "après une ligne neuve placée"],
)
def test_une_ligne_neuve_sans_position_n_est_pas_jugee_couverture(
    admin_client: Client, placed_ahead: dict[str, object]
) -> None:
    """La couverture jugée est la première image enregistrée : une ligne neuve arrivée sans
    position se range après toutes les autres, et n'est pas jugée comme telle.

    Les voies par lesquelles une ligne reçoit sa place — 6 recensées : la position que le script
    remplit (`test_une_image_libre_glissee_en_tete_est_refusee`) ; une ligne enregistrée arrivée
    sans position, qui garde la sienne
    (`test_une_couverture_enregistree_arrivee_sans_position_reste_la_couverture`) ; des lignes
    neuves toutes sans position, dans l'ordre du formulaire
    (`test_sans_le_script_la_premiere_ligne_du_formulaire_est_la_couverture`) ; une ligne neuve
    sans position après une image enregistrée ailleurs
    (`test_une_ligne_neuve_sans_position_se_range_apres_une_image_enregistree_ailleurs`), après
    les lignes enregistrées, puis après une ligne neuve placée (ici). La dernière fuyait tant que
    `save_new` ne comptait que les lignes déjà en base : jugée après la ligne placée, la ligne en
    paysage s'enregistrait devant elle."""
    portfolio = saved_project(saved(technology(name="Django")))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | image_row(
        GALLERY, 1, original=image_upload(size=LANDSCAPE), position=""
    )
    if placed_ahead:
        data |= placed_ahead | image_row(GALLERY, 2, position=5)

    response = admin_client.post(url, data)

    assert response.status_code == 302
    assert [image.width for image in portfolio.gallery.all()] == [MIN_SIDE, LANDSCAPE[0]]


@pytest.mark.django_db
def test_une_ligne_neuve_sans_position_se_range_apres_une_image_enregistree_ailleurs(
    admin_client: Client,
) -> None:
    """Une image enregistrée depuis l'ouverture de l'écran — un second onglet — n'est dans aucune
    ligne de l'envoi : la ligne neuve arrivée sans position se range après elle aussi."""
    portfolio = saved_project(saved(technology(name="Django")))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | image_row(
        GALLERY, 1, original=image_upload(size=LANDSCAPE), position=""
    )
    saved(gallery_image(portfolio, original=image_upload(size=(1300, 1300)), position=7))

    response = admin_client.post(url, data)

    assert response.status_code == 302
    assert [image.width for image in portfolio.gallery.all()] == [MIN_SIDE, 1300, LANDSCAPE[0]]


@pytest.mark.django_db
def test_l_ecran_accepte_une_image_sans_extension(admin_client: Client) -> None:
    """L'original est reconnu à son contenu, jamais à son nom (décision 6) : le tableau emploie le
    champ de formulaire de l'original, pas celui de Django."""
    data = new_project_data(
        admin_client,
        **line(0, saved(technology(name="Django")), 1),
        **image_row(GALLERY, original=image_upload("photo", image_format="JPEG")),
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert (Project.objects.get().gallery.get().original.name or "").endswith("/original.jpg")


@pytest.mark.django_db
def test_l_auteur_remplace_le_fichier_d_une_image(admin_client: Client) -> None:
    """Le geste d'une ligne enregistrée : choisir un autre fichier. L'image le prend, et revient
    « en attente » (décision 5)."""
    portfolio = saved_project(saved(technology(name="Django")))
    before = portfolio.gallery.get().original.name
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        f"{GALLERY}-0-original": image_upload(size=(MIN_SIDE + 100, MIN_SIDE + 100))
    }

    response = admin_client.post(url, data)

    assert response.status_code == 302
    replaced = portfolio.gallery.get()
    assert replaced.original.name != before
    assert (replaced.width, replaced.state) == (MIN_SIDE + 100, ProcessingState.PENDING)


@pytest.mark.django_db
def test_l_apercu_montre_l_original_enregistre_et_son_etat_en_texte(admin_client: Client) -> None:
    """L'original dans un `<img>` : dimensions en attributs, sans `style` en ligne (CSP de #6),
    légende en texte alternatif (décision 11). L'état, en texte, ne se modifie pas."""
    portfolio = saved_project(saved(technology(name="Django")))
    made = portfolio.gallery.get()
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    page = admin_client.get(url).content.decode()

    gallery = group(page, GALLERY)
    images = re.findall(r"<img [^>]*>", gallery)
    assert len(images) == 1
    assert f'src="{made.original.url}"' in images[0]
    assert f'alt="{escape(made.caption)}"' in images[0]
    assert re.search(r'width="\d+" height="\d+"', images[0])
    assert f'class="{PREVIEW_CLASS}"' in images[0]
    assert "style" not in images[0]
    assert escape(strings.PROCESSING_STATE_PENDING) in gallery
    assert f'name="{GALLERY}-0-state"' not in page


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "label"),
    [
        (ProcessingState.PENDING, "En attente"),
        (ProcessingState.READY, "Prêt"),
        (ProcessingState.FAILED, "Échec"),
    ],
    ids=["en attente", "prête", "en échec"],
)
def test_l_ecran_projet_montre_l_etat_que_le_worker_a_ecrit(
    admin_client: Client, state: str, label: str
) -> None:
    """L'état tel que le worker l'écrit — par une requête, hors de l'admin —, sans motif (brief de
    #12, décision 2) : « Échec » se lit à l'écran comme « Prêt »."""
    portfolio = saved_project(saved(technology(name="Django")))
    GalleryImage.objects.filter(project=portfolio).update(state=state)
    url = reverse("admin:content_project_change", args=[portfolio.pk])

    gallery = group(admin_client.get(url).content.decode(), GALLERY)

    assert escape(label) in gallery


def test_la_feuille_de_l_apercu_fait_tenir_l_original_entier_dans_son_cadre() -> None:
    """Le cadre de l'aperçu est un carré, nommé en attributs : sans `object-fit: contain` sur la
    classe de l'`<img>`, une image en paysage y serait écrasée (décision 11)."""
    path = finders.find(IMAGE_PREVIEW_STYLE)
    assert isinstance(path, str)

    rule = re.search(rf"\.{PREVIEW_CLASS}\s*\{{([^}}]*)\}}", Path(path).read_text(encoding="utf-8"))

    assert rule is not None
    assert re.search(r"object-fit:\s*contain\s*;", rule.group(1))


@pytest.mark.django_db
def test_une_image_choisie_mais_pas_enregistree_n_a_pas_d_apercu(admin_client: Client) -> None:
    """L'aperçu apparaît après l'enregistrement (décision 3) : sur un écran revenu en erreur, le
    fichier choisi n'est pas stocké, et rien ne le montre."""
    data = new_project_data(admin_client)

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 200
    assert "<img " not in group(response.content.decode(), GALLERY)


@pytest.mark.django_db
def test_l_auteur_retire_ajoute_et_reordonne_les_images_de_la_galerie_en_un_enregistrement(
    admin_client: Client, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """On manipule les lignes — retirer une image, en glisser une neuve en tête —, puis on enregistre
    une fois (décision 11). L'image retirée sort du stockage, une fois la transaction validée
    (décision 10)."""
    portfolio = saved_project(saved(technology(name="Django")))
    removed = portfolio.gallery.get().original.name or ""
    saved(gallery_image(portfolio, caption="La fiche.", position=2))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        f"{GALLERY}-0-DELETE": "on",
        **image_row(GALLERY, 2, caption="La recherche.", position=1),
    }
    assert default_storage.exists(removed)

    with django_capture_on_commit_callbacks(execute=True):
        response = admin_client.post(url, data)

    assert response.status_code == 302
    assert [image.caption for image in portfolio.gallery.all()] == ["La recherche.", "La fiche."]
    assert not default_storage.exists(removed)


@pytest.mark.django_db
def test_une_ligne_de_galerie_neuve_laissee_vide_n_enregistre_rien(admin_client: Client) -> None:
    """Le script numérote toute ligne affichée : une ligne neuve dont seule la position est
    remplie est ignorée (`InlineRowForm.has_changed`, décision 11)."""
    data = new_project_data(
        admin_client,
        **line(0, saved(technology(name="Django")), 1),
        **{f"{GALLERY}-1-position": 2},
        **with_rows(2),
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert Project.objects.get().gallery.count() == 1


@pytest.mark.django_db
def test_la_page_de_suppression_d_un_projet_nomme_ses_images(admin_client: Client) -> None:
    """Django y nomme chaque objet que la suppression emporte : chaque image de la galerie, par
    son projet et sa légende, comme une technologie de projet."""
    portfolio = saved_project(saved(technology(name="Django")))
    saved(gallery_image(portfolio, caption="La fiche.", position=2))

    page = admin_client.get(
        reverse("admin:content_project_delete", args=[portfolio.pk])
    ).content.decode()

    for image in portfolio.gallery.all():
        assert escape(f"{portfolio.title} · {image.caption}") in page
