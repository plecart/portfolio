"""Tests de l'image de galerie, couverture comprise : l'original — le fichier que l'auteur
téléverse —, sa validation, son nom de stockage et ses lectures, la légende, l'état de traitement
et les variantes. La forme de la couverture, première image, est une règle de l'écran
(`test_image_admin.py`)."""

import logging
import re
import shutil
from collections.abc import Callable, Generator

import pytest
from config import strings
from content.images import validate_original
from content.models import GalleryImage, ProcessingState, Project
from counting_storage import CountingStorage
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import FETCH_PEERS
from django.forms import ModelForm, modelform_factory
from django.test import override_settings
from django.utils.datastructures import MultiValueDict
from factories import BLANK, SVG, gallery_image, image_upload, project, saved
from PIL import Image
from pytest_django import DjangoCaptureOnCommitCallbacks
from refusals import refusals
from test_markdown_preview import importers

type ImageFactory = Callable[..., GalleryImage]

# La borne de la légende (spec §7), écrite ici et non lue sur le modèle, pour qu'une borne changée
# fasse rougir ce fichier.
CAPTION_MAX_LENGTH = 50

# Une variante telle que le worker la décrit (décision 5).
VARIANT = {"name": "images/abc/w640.webp", "width": 640, "height": 640}

# Le nom de stockage d'un original (décision 7) : un identifiant aléatoire, puis l'extension du
# format reconnu.
STORED_NAME = re.compile(r"images/[0-9a-f]{32}/original\.(jpg|png|webp)")

# La borne technique du poids (brief de #9, décision 6), écrite ici et non lue dans le code, pour
# qu'une borne changée fasse rougir ce fichier : 10 Mo de 1 024² octets.
MAX_SIZE = 10 * 1024 * 1024

# Ce qu'un original accepte : les trois formats, reconnus à leur contenu, quel que soit le nom
# que l'auteur a donné au fichier (décision 6, « jamais à son extension »).
ACCEPTED = [
    ("JPEG", image_upload("photo.jpg", image_format="JPEG")),
    ("PNG", image_upload("image.png", image_format="PNG")),
    ("WebP", image_upload("image.webp", image_format="WEBP")),
    ("PNG nommé .jpg", image_upload("image.jpg", image_format="PNG")),
    ("JPEG sans extension", image_upload("photo", image_format="JPEG")),
    # Un JPEG à plusieurs images, comme bien des photos de téléphone : Pillow le nomme « MPO ».
    ("JPEG à plusieurs images", image_upload("photo.jpg", image_format="MPO", frames=2)),
]

# Les formes d'un fichier qui n'est pas une image JPEG, PNG ou WebP — c'est le dénombrement qui
# compte : un fichier qui n'est pas une image, des images d'autres formats sous une extension
# admise, et un document SVG, qu'un `<img>` afficherait mais que le worker de #12 ne convertit pas.
# Le BMP et le TIFF, non compressés, sont petits : au côté de la fabrique, leur poids dépasserait
# la borne, jugée avant le format.
NOT_ACCEPTED = [
    ("texte", SimpleUploadedFile("notes.png", b"Pas une image.")),
    ("GIF nommé .png", image_upload("image.png", image_format="GIF")),
    ("BMP nommé .jpg", image_upload("image.jpg", size=(300, 300), image_format="BMP")),
    ("TIFF nommé .webp", image_upload("image.webp", size=(300, 300), image_format="TIFF")),
    ("SVG nommé .png", SimpleUploadedFile("icone.png", SVG)),
]


def test_seuls_les_modules_des_originaux_et_des_variantes_importent_pillow() -> None:
    """Une seule chaîne d'image (brief de #12, décision 1) : Pillow lit l'original téléversé
    (décision 12 de #9) et en produit les variantes ; aucun autre module de l'application, tests
    exclus, ne l'importe."""
    assert importers("PIL") == {"content.images", "content.variants"}


@pytest.mark.parametrize(
    "upload", [upload for _, upload in ACCEPTED], ids=[form for form, _ in ACCEPTED]
)
def test_un_original_jpeg_png_ou_webp_est_accepte(upload: SimpleUploadedFile) -> None:
    validate_original(upload)


@pytest.mark.parametrize(
    "upload", [upload for _, upload in NOT_ACCEPTED], ids=[form for form, _ in NOT_ACCEPTED]
)
def test_un_original_qui_n_est_pas_une_image_jpeg_png_ou_webp_est_refuse(
    upload: SimpleUploadedFile,
) -> None:
    with pytest.raises(ValidationError) as refusal:
        validate_original(upload)

    assert (refusal.value.code, refusal.value.message) == (
        "image_format_unsupported",
        strings.IMAGE_FORMAT_UNSUPPORTED,
    )


def upload_of_size(size: int) -> SimpleUploadedFile:
    """Une image valide de `size` octets exactement."""
    return image_upload(padding=size - len(image_upload()))


def test_un_original_de_10_mo_est_accepte() -> None:
    validate_original(upload_of_size(MAX_SIZE))


def test_un_original_de_plus_de_10_mo_est_refuse() -> None:
    with pytest.raises(ValidationError) as refusal:
        validate_original(upload_of_size(MAX_SIZE + 1))

    assert (refusal.value.code, refusal.value.message) == (
        "image_too_large",
        strings.IMAGE_TOO_LARGE,
    )


def test_une_bombe_de_decompression_est_refusee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pillow refuse de décoder une image dont l'en-tête annonce plus de deux fois
    `MAX_IMAGE_PIXELS` pixels, et quelques kilo-octets suffisent à en porter une : un refus du
    catalogue, jamais une exception de `validate_original`. L'affectation au modèle, elle, lit les
    dimensions avec Django (`get_image_dimensions`), qui laisse passer l'exception — un formulaire
    valide l'original avant de l'affecter (`OriginalFormField`). La limite est abaissée le temps du
    test : l'image de la fabrique la dépasse alors."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)

    with pytest.raises(ValidationError) as refusal:
        validate_original(image_upload())

    assert (refusal.value.code, refusal.value.message) == (
        "image_too_many_pixels",
        strings.IMAGE_TOO_MANY_PIXELS,
    )


def test_un_original_valide_reste_pret_a_etre_lu_depuis_le_debut() -> None:
    """`Storage.save` attend un fichier « ready to be read from the beginning »
    (`django/core/files/storage/base.py`) : la validation, qui lit son en-tête, le rend rembobiné.
    Le stockage sur disque rembobine de lui-même ; un autre stockage n'y est pas tenu."""
    upload = image_upload()

    validate_original(upload)

    assert upload.tell() == 0


# Le formulaire d'une image, réduit à ce que l'auteur saisit : l'original et la légende.
ImageForm = modelform_factory(GalleryImage, fields=("original", "caption"))


def image_form(upload: SimpleUploadedFile) -> ModelForm[GalleryImage]:
    """Le formulaire d'une image neuve, `upload` choisi pour original et la légende remplie, tel
    que l'admin le reçoit."""
    return ImageForm({"caption": "La fiche d'un projet."}, MultiValueDict({"original": [upload]}))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "upload", [upload for _, upload in ACCEPTED], ids=[form for form, _ in ACCEPTED]
)
def test_le_formulaire_d_une_image_accepte_un_original_jpeg_png_ou_webp(
    upload: SimpleUploadedFile,
) -> None:
    """Le formulaire juge l'original comme le modèle, à son contenu (décision 6) : un JPEG sans
    extension compris, que le champ de formulaire de Django, `forms.ImageField`, refuse."""
    form = image_form(upload)

    assert form.is_valid(), form.errors


# Ce que le formulaire refuse, avec le seul message du catalogue : chaque forme qu'un original
# refuse.
FORM_REFUSALS = [
    *[(form, upload, strings.IMAGE_FORMAT_UNSUPPORTED) for form, upload in NOT_ACCEPTED],
    ("plus de 10 Mo", upload_of_size(MAX_SIZE + 1), strings.IMAGE_TOO_LARGE),
]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("upload", "message"),
    [(upload, message) for _, upload, message in FORM_REFUSALS],
    ids=[form for form, _, _ in FORM_REFUSALS],
)
def test_le_formulaire_d_une_image_refuse_un_original_avec_le_seul_message_du_catalogue(
    upload: SimpleUploadedFile, message: str
) -> None:
    """Un refus, celui de l'original : jamais en plus celui de Django pour une image invalide."""
    form = image_form(upload)

    assert form.errors == {"original": [message]}


@pytest.mark.django_db
def test_le_formulaire_d_une_image_refuse_une_bombe_de_decompression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le formulaire valide l'original avant de l'affecter au modèle : affecté, il ferait lire ses
    dimensions par Django (`get_image_dimensions`), qui laisse passer l'exception de Pillow."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)

    form = image_form(image_upload())

    assert form.errors == {"original": [strings.IMAGE_TOO_MANY_PIXELS]}


@pytest.mark.django_db
def test_le_formulaire_d_une_image_ignore_la_longueur_du_nom_de_l_auteur() -> None:
    """Le nom de l'auteur n'est pas gardé (décision 7) : sa longueur ne compte pas, là où
    `forms.FileField` la borne à celle de la colonne, 100 caractères."""
    form = image_form(image_upload(f"{'n' * 200}.png"))

    assert form.is_valid(), form.errors


def test_le_selecteur_de_fichiers_de_l_original_propose_les_trois_formats() -> None:
    """Un confort : le sélecteur du navigateur filtre sur ces types ; le contenu reste seul juge."""
    field = image_form(image_upload()).fields["original"]

    assert field.widget.attrs["accept"] == "image/jpeg,image/png,image/webp"


# Les règles que la base porte, communes aux deux modèles — une contrainte nommée chacune, par
# modèle (décision 4) —, avec le refus de la contrainte, code et message du catalogue, et celui
# que `full_clean()` rend, champ et code. Quand le champ refuse lui-même la valeur (vide), Django
# écarte la contrainte : l'admin n'affiche jamais deux messages pour une faute. L'état et les
# variantes, non éditables, ne sont pas validés par leur champ : seule la contrainte les refuse.
# Un original absent n'a pas de dimensions : la ligne les porte, sans quoi la colonne non nulle
# refuserait avant la contrainte.
DATABASE_GUARDS = [
    (
        "original absent",
        {"original": "", "width": 1200, "height": 1200},
        "original_not_empty",
        ("image_original_missing", strings.IMAGE_ORIGINAL_MISSING),
        ("original", "blank"),
    ),
    (
        "légende vide",
        {"caption": ""},
        "caption_not_empty",
        ("image_caption_missing", strings.IMAGE_CAPTION_MISSING),
        ("caption", "blank"),
    ),
    (
        "légende faite d'espaces",
        {"caption": BLANK},
        "caption_not_empty",
        ("image_caption_missing", strings.IMAGE_CAPTION_MISSING),
        (NON_FIELD_ERRORS, "image_caption_missing"),
    ),
    (
        f"légende de {CAPTION_MAX_LENGTH + 1} caractères",
        {"caption": "l" * (CAPTION_MAX_LENGTH + 1)},
        "caption_length",
        ("image_caption_too_long", strings.IMAGE_CAPTION_TOO_LONG),
        (NON_FIELD_ERRORS, "image_caption_too_long"),
    ),
    (
        "état hors de sa liste",
        {"state": "autre"},
        "state_valid",
        ("image_state_unknown", strings.IMAGE_STATE_UNKNOWN),
        (NON_FIELD_ERRORS, "image_state_unknown"),
    ),
    (
        "variantes d'une image en attente",
        {"variants": [VARIANT]},
        "variants_ready",
        ("image_variants_unready", strings.IMAGE_VARIANTS_UNREADY),
        (NON_FIELD_ERRORS, "image_variants_unready"),
    ),
    (
        "variantes d'une image en échec",
        {"state": ProcessingState.FAILED, "variants": [VARIANT]},
        "variants_ready",
        ("image_variants_unready", strings.IMAGE_VARIANTS_UNREADY),
        (NON_FIELD_ERRORS, "image_variants_unready"),
    ),
]
GUARD_IDS = [guard for guard, *_ in DATABASE_GUARDS]

# Ce qu'une image accepte : chaque borne atteinte sans être dépassée, et chaque état.
ACCEPTANCES: list[tuple[str, dict[str, object]]] = [
    ("image de la fabrique", {}),
    # Reconnu à son contenu, jamais à son nom (décision 6).
    ("original sans extension", {"original": image_upload("photo", image_format="JPEG")}),
    (f"légende de {CAPTION_MAX_LENGTH} caractères", {"caption": "l" * CAPTION_MAX_LENGTH}),
    ("image prête avec ses variantes", {"state": ProcessingState.READY, "variants": [VARIANT]}),
    ("image prête sans variante", {"state": ProcessingState.READY}),
    ("image en échec", {"state": ProcessingState.FAILED}),
]


@pytest.fixture
def portfolio() -> Project:
    """Le projet de la fabrique, enregistré."""
    return saved(project())


@pytest.fixture
def image() -> ImageFactory:
    """La fabrique des images de la galerie, couverture comprise : une règle d'image vaut pour
    toutes."""
    return gallery_image


def constraint_name(made: GalleryImage, rule: str) -> str:
    """Le nom que porte la contrainte `rule` dans la table du modèle de `made`."""
    return f"content_{made._meta.model_name}_{rule}"


def test_une_image_porte_son_original_ses_dimensions_sa_legende_son_etat_et_ses_variantes() -> None:
    """Une seule définition des champs (critère du corps) : ceux de l'image, puis sa place dans la
    galerie de son projet."""
    assert [field.name for field in GalleryImage._meta.concrete_fields] == [
        "id",
        "original",
        "width",
        "height",
        "caption",
        "state",
        "variants",
        "project",
        "position",
    ]


def test_les_valeurs_de_l_etat_sont_celles_que_l_api_expose() -> None:
    """Les valeurs stockées sont un contrat : l'API de #10 les expose telles quelles (ADR 0010),
    le worker de #12 les écrit."""
    assert ProcessingState.values == ["pending", "ready", "failed"]


@pytest.mark.django_db
def test_une_image_nait_en_attente_sans_variante(portfolio: Project, image: ImageFactory) -> None:
    """Sans transaction validée, rien ne la traite : le worker la fait passer à « prêt » ou à
    « échec » (`test_tasks.py`)."""
    made = saved(image(portfolio))

    made.refresh_from_db()
    assert (made.state, made.variants) == (ProcessingState.PENDING, [])


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [fields for _, fields in ACCEPTANCES],
    ids=[acceptance for acceptance, _ in ACCEPTANCES],
)
def test_une_image_accepte_des_valeurs_dans_ses_regles(
    portfolio: Project, image: ImageFactory, fields: dict[str, object]
) -> None:
    """`django_db` : `full_clean()` fait évaluer les contraintes par la base."""
    image(portfolio, **fields).full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "cleaned"),
    [(fields, cleaned) for _, fields, _, _, cleaned in DATABASE_GUARDS],
    ids=GUARD_IDS,
)
def test_full_clean_refuse_une_image_hors_de_ses_regles(
    portfolio: Project, image: ImageFactory, fields: dict[str, object], cleaned: tuple[str, str]
) -> None:
    """Un seul refus, sur un seul champ."""
    field, code = cleaned
    with pytest.raises(ValidationError) as error:
        image(portfolio, **fields).full_clean()

    assert error.value.error_dict.keys() == {field}
    assert [refused for refused, _ in refusals(error.value, field)] == [code]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "refusal"),
    [(fields, refusal) for _, fields, _, refusal, _ in DATABASE_GUARDS],
    ids=GUARD_IDS,
)
def test_une_garde_de_la_base_refuse_avec_le_code_et_le_message_du_catalogue(
    portfolio: Project, image: ImageFactory, fields: dict[str, object], refusal: tuple[str, str]
) -> None:
    """`validate_constraints()` seul rend le refus de la contrainte, que `full_clean()` écarte
    quand le champ est déjà en erreur."""
    with pytest.raises(ValidationError) as error:
        image(portfolio, **fields).validate_constraints()

    assert refusals(error.value) == [refusal]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fields", "rule"),
    [(fields, rule) for _, fields, rule, _, _ in DATABASE_GUARDS],
    ids=GUARD_IDS,
)
def test_la_base_refuse_une_image_qui_enfreint_ses_regles(
    portfolio: Project, image: ImageFactory, fields: dict[str, object], rule: str
) -> None:
    """Pour une ligne écrite hors de l'admin — celle du worker de #12 comprise —, chaque table
    sous le nom de contrainte de son modèle."""
    made = image(portfolio, **fields)

    with pytest.raises(IntegrityError, match=constraint_name(made, rule)), transaction.atomic():
        made.save()


@pytest.mark.django_db
def test_un_fichier_qui_n_est_pas_une_image_n_a_qu_un_refus(
    portfolio: Project, image: ImageFactory
) -> None:
    """Sans dimensions lisibles, `width` et `height` restent vides sans se plaindre : seul
    l'original dit pourquoi."""
    with pytest.raises(ValidationError) as error:
        image(portfolio, original=SimpleUploadedFile("notes.png", b"Pas une image.")).full_clean()

    assert error.value.error_dict.keys() == {"original"}
    assert [code for code, _ in refusals(error.value, "original")] == ["image_format_unsupported"]


@pytest.mark.django_db
def test_les_dimensions_sont_lues_dans_l_original(portfolio: Project) -> None:
    made = saved(gallery_image(portfolio, original=image_upload(size=(1300, 800))))

    made.refresh_from_db()
    assert (made.width, made.height) == (1300, 800)


@pytest.mark.django_db
def test_le_nom_stocke_ne_reprend_rien_du_nom_de_l_auteur(
    portfolio: Project, image: ImageFactory
) -> None:
    made = saved(image(portfolio, original=image_upload("vacances-2026.png")))

    assert STORED_NAME.fullmatch(made.original.name or "")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("upload", "extension"),
    [
        (image_upload("photo.png", image_format="JPEG"), "jpg"),
        (image_upload("photo.png", image_format="MPO", frames=2), "jpg"),
        (image_upload("image.jpg", image_format="PNG"), "png"),
        (image_upload("image.jpg", image_format="WEBP"), "webp"),
    ],
    ids=["JPEG nommé .png", "MPO nommé .png", "PNG nommé .jpg", "WebP nommé .jpg"],
)
def test_l_original_est_enregistre_sous_l_extension_de_son_format(
    portfolio: Project, upload: SimpleUploadedFile, extension: str
) -> None:
    """L'extension est celle du format reconnu, d'où le serveur de fichiers tire le type servi."""
    made = saved(gallery_image(portfolio, original=upload))

    assert (made.original.name or "").endswith(f"/original.{extension}")


@pytest.mark.django_db
def test_deux_televersements_du_meme_fichier_ont_chacun_leur_dossier(portfolio: Project) -> None:
    """Le dossier aléatoire distingue deux téléversements : sur R2, `django-storages` écraserait
    un objet de même nom (décision 7) — le stockage sur disque, lui, renomme le second, ce qui
    masquerait la faute si l'on ne comparait que les noms."""
    first = saved(gallery_image(portfolio, original=image_upload("image.png")))
    second = saved(gallery_image(portfolio, original=image_upload("image.png"), position=2))

    names = [made.original.name or "" for made in (first, second)]
    assert all(STORED_NAME.fullmatch(name) for name in names), names
    assert names[0].rsplit("/", 1)[0] != names[1].rsplit("/", 1)[0]


@pytest.mark.django_db
def test_l_original_stocke_est_identique_a_l_octet_au_fichier_televerse(
    portfolio: Project, image: ImageFactory
) -> None:
    """Jamais recadré ni réencodé (spec §1.11)."""
    upload = image_upload(image_format="JPEG")
    content = upload.read()
    upload.seek(0)

    made = saved(image(portfolio, original=upload))

    with made.original.open() as stored:
        assert stored.read() == content


@pytest.mark.django_db
def test_la_sauvegarde_brute_d_un_fichier_qui_n_est_pas_une_image_ne_stocke_rien(
    portfolio: Project,
) -> None:
    """Sans validation, le nommage refuse encore : sans format reconnu, pas d'extension."""
    made = gallery_image(
        portfolio, original=SimpleUploadedFile("notes.png", b"Pas une image."), width=1, height=1
    )

    with pytest.raises(ValidationError) as refusal:
        made.save()

    assert refusal.value.code == "image_format_unsupported"
    assert not default_storage.exists("images")


@pytest.fixture
def witness() -> Generator[CountingStorage]:
    """Le stockage par défaut, le temps du test : un stockage sur disque qui compte ses
    ouvertures."""
    witness_storages = {
        **settings.STORAGES,
        "default": {"BACKEND": "counting_storage.CountingStorage"},
    }
    with override_settings(STORAGES=witness_storages):
        storage = storages["default"]
        assert isinstance(storage, CountingStorage)
        yield storage


@pytest.mark.django_db
def test_enregistrer_une_image_sans_changer_son_fichier_n_ouvre_pas_l_original(
    portfolio: Project, image: ImageFactory, witness: CountingStorage
) -> None:
    """Sur R2, chaque ouverture serait un téléchargement (décision 9). Le chemin de l'admin, pas à
    pas : la ligne relue, validée, son fichier réaffecté tel quel — ce que fait le formulaire
    (`construct_instance`) —, puis enregistrée."""
    made = saved(image(portfolio))
    loaded = type(made).objects.get(pk=made.pk)

    loaded.refresh_from_db()
    loaded.caption = "Une autre légende."
    loaded.full_clean()
    loaded.original = loaded.original
    loaded.save()
    loaded.refresh_from_db()

    assert witness.opened == []
    assert (loaded.width, loaded.height) == (made.width, made.height)


@pytest.mark.django_db
def test_le_formulaire_d_une_image_dont_le_fichier_ne_change_pas_n_ouvre_pas_l_original(
    portfolio: Project, witness: CountingStorage
) -> None:
    """Le même chemin, par le formulaire lui-même : sans nouveau fichier, son champ rend l'original
    stocké sans le valider (décision 9)."""
    made = saved(gallery_image(portfolio))
    form = ImageForm(
        {"caption": "Une autre légende."}, instance=GalleryImage.objects.get(pk=made.pk)
    )

    form.save()

    assert witness.opened == []


class Rollback(Exception):
    """Annule la transaction d'un test, comme une erreur après l'écriture."""


def ready(made: GalleryImage) -> list[str]:
    """Enregistre `made` prête, avec une variante stockée à côté de son original, comme le worker
    le fait ; rend les noms que le stockage tient pour elle."""
    saved(made)
    folder = (made.original.name or "").rsplit("/", 1)[0]
    variant = default_storage.save(f"{folder}/w640.webp", ContentFile(b"variante"))
    made.state = ProcessingState.READY
    made.variants = [{"name": variant, "width": 640, "height": 640}]
    made.save()
    return [made.original.name or "", variant]


def stored(names: list[str]) -> list[bool]:
    """Pour chacun de `names`, si le stockage le tient encore."""
    return [default_storage.exists(name) for name in names]


def pending(made: GalleryImage) -> bool:
    """Si la ligne de `made` est en attente, sans variante — ce qu'un remplacement écrit, lu avant
    la validation de sa transaction : après, le worker l'a traitée."""
    row = type(made).objects.get(pk=made.pk)
    return (row.state, row.variants) == (ProcessingState.PENDING, [])


def processed(made: GalleryImage) -> bool:
    """Si la ligne de `made` est prête, ses variantes rangées dans le dossier de l'original
    qu'elle référence — le worker est passé sur le nouveau fichier."""
    row = type(made).objects.get(pk=made.pk)
    folder = (row.original.name or "").rsplit("/", 1)[0]
    return (
        ProcessingState(row.state) is ProcessingState.READY
        and bool(row.variants)
        and all(variant["name"].startswith(f"{folder}/") for variant in row.variants)
    )


@pytest.mark.django_db
def test_supprimer_une_image_supprime_ses_fichiers_apres_la_transaction(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """L'original et ses variantes : le bucket des images est public (ADR 0004), une image
    retirée resterait servie (décision 10)."""
    made = image(portfolio)
    names = ready(made)

    with django_capture_on_commit_callbacks(execute=True):
        made.delete()
        assert stored(names) == [True, True]

    assert stored(names) == [False, False]


@pytest.mark.django_db
def test_supprimer_un_projet_supprime_les_fichiers_de_ses_images(
    portfolio: Project, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    names = [*ready(gallery_image(portfolio)), *ready(gallery_image(portfolio, position=2))]

    with django_capture_on_commit_callbacks(execute=True):
        portfolio.delete()

    assert stored(names) == [False] * 4


@pytest.mark.django_db
def test_une_suppression_annulee_ne_supprime_aucun_fichier(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    made = image(portfolio)
    names = ready(made)

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(Rollback),
        transaction.atomic(),
    ):
        made.delete()
        raise Rollback

    assert stored(names) == [True, True]


@pytest.mark.django_db
def test_remplacer_le_fichier_d_une_image_prete_la_remet_en_attente_et_supprime_l_ancien(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Les variantes de l'ancien original ne valent plus rien : vidées, et supprimées avec lui une
    fois la transaction validée. Le worker repart de l'état « en attente » : la transaction
    validée, il a traité le nouvel original (`test_tasks.py`)."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    loaded.original = image_upload("nouvelle.png")

    with django_capture_on_commit_callbacks(execute=True):
        loaded.save()
        assert stored(names) == [True, True]
        assert pending(loaded)

    assert stored(names) == [False, False]
    assert stored([loaded.original.name or ""]) == [True]
    assert processed(loaded)


@pytest.mark.django_db
def test_un_remplacement_annule_ne_supprime_aucun_fichier(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    loaded.original = image_upload("nouvelle.png")

    with (
        django_capture_on_commit_callbacks(execute=True),
        pytest.raises(Rollback),
        transaction.atomic(),
    ):
        loaded.save()
        raise Rollback

    assert stored(names) == [True, True]


@pytest.mark.django_db
def test_remplacer_l_original_par_son_enregistrement_direct_lit_le_nouveau_contenu(
    portfolio: Project,
    image: ImageFactory,
    witness: CountingStorage,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """`image.original.save(nom, contenu)` — une commande, un script de reprise : le format et le
    nom se lisent dans le contenu qui s'enregistre, jamais dans l'original stocké, et l'image
    repart en attente comme après un téléversement."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    jpeg = image_upload(image_format="JPEG").read()

    with django_capture_on_commit_callbacks(execute=True):
        loaded.original.save("photo.png", ContentFile(jpeg))
        assert pending(loaded)
        assert witness.opened == []

    loaded.refresh_from_db()
    assert (loaded.original.name or "").endswith("/original.jpg")
    assert stored(names) == [False, False]
    # La transaction validée, le worker lit le nouvel original, et lui seul.
    assert witness.opened == [loaded.original.name]
    assert processed(loaded)


@pytest.mark.django_db
def test_l_enregistrement_direct_d_un_fichier_qui_n_est_pas_une_image_est_refuse(
    portfolio: Project,
) -> None:
    """Sans validation, le nommage refuse encore : rien n'est stocké, la ligne ne change pas."""
    made = saved(gallery_image(portfolio))
    name = made.original.name

    with pytest.raises(ValidationError) as refusal:
        made.original.save("notes.png", ContentFile(b"Pas une image."))

    assert refusal.value.code == "image_format_unsupported"
    assert GalleryImage.objects.get(pk=made.pk).original.name == name
    folders, _ = default_storage.listdir("images")
    assert len(folders) == 1


@pytest.mark.django_db
def test_enregistrer_une_image_sans_changer_son_fichier_garde_ses_fichiers_et_son_etat(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Seul un téléversement remplace : une légende retouchée ne touche ni l'état ni les
    fichiers."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    loaded.caption = "Une autre légende."

    with django_capture_on_commit_callbacks(execute=True):
        loaded.save()

    loaded.refresh_from_db()
    assert loaded.state == ProcessingState.READY
    assert stored(names) == [True, True]


def replaced_elsewhere(made: GalleryImage, name: str) -> GalleryImage:
    """Remplace l'original de la ligne de `made` par un autre enregistrement que `made` ; rend
    cet enregistrement."""
    other = type(made).objects.get(pk=made.pk)
    other.original = image_upload(name)
    other.save()
    return other


def stale_instance(image: ImageFactory, made: GalleryImage, how: str) -> GalleryImage:
    """Une instance de la ligne de `made`, de la façon `how`, que la suite rendra périmée ;
    `image` fabrique une ligne du même modèle."""
    if how == "créée puis enregistrée":
        return made
    if how == "différée":
        stale = type(made).objects.only("id", "caption").get(pk=made.pk)
        assert stale.original.name  # le chargement à la demande passe par `refresh_from_db`
        return stale
    if how == "différée par lot":
        # Une seule ligne se recharge seule (`refresh_from_db`) : un pair, sur un autre projet,
        # fait charger l'original du lot d'une requête, sans elle (`DeferredAttribute.fetch_many`).
        saved(image(saved(project(slug="pair"))))
        lot = list(type(made).objects.all().fetch_mode(FETCH_PEERS).only("id", "caption"))
        stale = next(row for row in lot if row.pk == made.pk)
        assert stale.original.name
        return stale
    stale = type(made).objects.get(pk=made.pk)
    if how == "rafraîchie":
        replaced_elsewhere(made, "intermediaire.png")
        stale.refresh_from_db()
    return stale


@pytest.mark.django_db
@pytest.mark.parametrize(
    "how", ["lue en base", "créée puis enregistrée", "rafraîchie", "différée", "différée par lot"]
)
def test_une_instance_perimee_ne_supprime_pas_l_original_qu_un_autre_enregistrement_a_pose(
    portfolio: Project,
    image: ImageFactory,
    how: str,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Deux écrivains sur la même image — deux onglets de l'admin, l'admin et le worker de #12 :
    celui qui n'a pas touché à l'original ne le supprime pas, même quand la ligne en porte un
    autre que celui qu'il a lu. Seul ce que l'instance a remplacé sort du stockage.

    Les voies par lesquelles un nom d'original stocké arrive sur une instance, recensées dans
    Django 6.1 : quatre, toutes ici — lecture (`from_db`), écriture (`save`), relecture
    (`refresh_from_db`, rafraîchie ou champ différé chargé seul) et chargement d'un champ différé
    avec ses pairs (`FETCH_PEERS`, `DeferredAttribute.fetch_many`), qui ne passe par aucune
    méthode du modèle : l'instance y ignore le nom, et ne supprime donc rien. L'affectation
    directe d'un fichier, cinquième voie, est un remplacement."""
    made = image(portfolio)
    ready(made)
    stale = stale_instance(image, made, how)

    with django_capture_on_commit_callbacks(execute=True):
        fresh = replaced_elsewhere(made, "nouvelle.png")
        stale.caption = "Une autre légende."
        stale.save()

    assert stored([fresh.original.name or ""]) == [True]


@pytest.mark.django_db
def test_un_televersement_remplace_meme_sur_une_instance_qui_n_a_pas_lu_son_original(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Un téléversement remplace ce que la ligne référence au moment de l'écriture, quoi que
    l'instance ait lu : une ligne chargée sans son original (`only`) le remplace pour de bon."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.only("id").get(pk=made.pk)
    loaded.original = image_upload("nouvelle.png")

    with django_capture_on_commit_callbacks(execute=True):
        loaded.save()
        assert pending(loaded)

    assert stored(names) == [False, False]
    assert processed(loaded)


@pytest.mark.django_db
def test_une_instance_qui_reprend_l_original_de_la_ligne_ne_le_supprime_pas(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Ce que la ligne référencera après l'écriture ne sort jamais du stockage : une instance
    périmée à qui l'on rend le nom que la ligne porte déjà n'a rien remplacé."""
    made = image(portfolio)
    ready(made)
    stale = type(made).objects.get(pk=made.pk)

    with django_capture_on_commit_callbacks(execute=True):
        fresh = replaced_elsewhere(made, "nouvelle.png")
        stale.original = fresh.original.name
        stale.save()

    assert stored([fresh.original.name or ""]) == [True]


@pytest.mark.django_db
def test_un_enregistrement_partiel_de_l_original_ecrit_ses_dimensions(
    portfolio: Project, image: ImageFactory
) -> None:
    """Les dimensions décrivent l'original — la forme de la couverture se juge sur elles : il ne
    s'écrit jamais sans elles."""
    made = saved(image(portfolio))
    loaded = type(made).objects.get(pk=made.pk)
    loaded.original = image_upload(size=(1300, 1300))

    loaded.save(update_fields=["original"])

    row = type(made).objects.get(pk=made.pk)
    assert (row.width, row.height) == (1300, 1300)


@pytest.mark.django_db
def test_un_enregistrement_partiel_accepte_des_champs_donnes_par_un_generateur(
    portfolio: Project,
) -> None:
    """Django accepte tout itérable : le lire avant lui ne doit pas le vider."""
    made = saved(gallery_image(portfolio))
    made.caption = "Une autre légende."

    made.save(update_fields=(field for field in ["caption"]))

    assert GalleryImage.objects.get(pk=made.pk).caption == "Une autre légende."


@pytest.mark.django_db
def test_un_original_ecarte_d_un_enregistrement_partiel_reste_a_remplacer(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """L'enregistrement partiel qui n'écrit pas l'original ne fait pas croire à l'instance que la
    ligne porte celui qu'elle tient : l'enregistrement complet qui suit le remplace pour de bon."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    loaded.original = image_upload("nouvelle.png")

    with django_capture_on_commit_callbacks(execute=True):
        loaded.save(update_fields=["caption"])
        loaded.save()
        assert pending(loaded)

    assert stored(names) == [False, False]
    assert processed(loaded)


@pytest.mark.django_db
def test_supprimer_une_image_deja_supprimee_ne_supprime_rien_de_plus(
    portfolio: Project, django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks
) -> None:
    """Deux instances de la même ligne, supprimées l'une après l'autre : la seconde ne trouve plus
    de ligne, et rien ne casse."""
    made = gallery_image(portfolio)
    names = ready(made)
    first, second = (GalleryImage.objects.get(pk=made.pk) for _ in range(2))

    with django_capture_on_commit_callbacks(execute=True):
        first.delete()
        second.delete()

    assert stored(names) == [False, False]


@pytest.mark.django_db
def test_un_enregistrement_partiel_sans_l_original_ne_remplace_rien(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """`save(update_fields=…)` sans l'original n'écrit pas le fichier affecté au champ : la ligne
    garde le sien, ses variantes et son état — rien à supprimer."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    loaded.original = image_upload("nouvelle.png")
    loaded.caption = "Une autre légende."

    with django_capture_on_commit_callbacks(execute=True):
        loaded.save(update_fields=["caption"])

    row = type(made).objects.get(pk=made.pk)
    assert (row.original.name, row.state) == (names[0], ProcessingState.READY)
    assert stored(names) == [True, True]


@pytest.mark.django_db
def test_un_enregistrement_partiel_qui_remplace_l_original_remet_l_image_en_attente(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """L'état et les variantes rejoignent les champs écrits : sans eux, la ligne garderait
    l'état « prêt » et des variantes déjà supprimées."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    loaded.original = image_upload("nouvelle.png")

    with django_capture_on_commit_callbacks(execute=True):
        loaded.save(update_fields=["original", "width", "height"])
        assert pending(loaded)

    assert stored(names) == [False, False]
    assert processed(loaded)


@pytest.mark.django_db
def test_supprimer_une_image_dont_l_original_vient_d_etre_remplace_supprime_l_original_stocke(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Ce que la ligne référence sort du stockage, pas ce que l'instance tient en mémoire : c'est
    le cas d'une ligne de galerie cochée pour suppression avec un nouveau fichier choisi."""
    made = image(portfolio)
    names = ready(made)
    loaded = type(made).objects.get(pk=made.pk)
    loaded.original = image_upload("nouvelle.png")

    with django_capture_on_commit_callbacks(execute=True):
        loaded.delete()

    assert stored(names) == [False, False]


@pytest.mark.django_db
def test_supprimer_une_image_chargee_sans_ses_fichiers_supprime_ses_fichiers(
    portfolio: Project,
    image: ImageFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Une instance différée (`only`) : ses noms se lisent dans la ligne avant sa suppression."""
    made = image(portfolio)
    names = ready(made)

    with django_capture_on_commit_callbacks(execute=True):
        type(made).objects.only("id").get(pk=made.pk).delete()

    assert stored(names) == [False, False]


@pytest.mark.django_db
def test_supprimer_une_image_dont_le_dossier_a_disparu_ne_journalise_aucune_erreur(
    portfolio: Project,
    caplog: pytest.LogCaptureFixture,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Un dossier déjà absent n'a rien à supprimer : pas d'erreur journalisée, qui deviendrait un
    événement Sentry (ADR 0027)."""
    made = saved(gallery_image(portfolio))
    shutil.rmtree(default_storage.path((made.original.name or "").rsplit("/", 1)[0]))

    with django_capture_on_commit_callbacks(execute=True):
        made.delete()

    assert [record.message for record in caplog.records if record.levelno >= logging.ERROR] == []


@pytest.mark.django_db
def test_une_panne_du_stockage_n_empeche_pas_les_autres_suppressions(
    portfolio: Project,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La ligne est déjà supprimée quand les fichiers sortent du stockage : un fichier qui résiste
    est journalisé, les suivants sortent quand même, et rien ne remonte à la requête."""
    made = gallery_image(portfolio)
    original, variant = ready(made)
    delete = FileSystemStorage.delete

    def failing_delete(storage: FileSystemStorage, name: str) -> None:
        if name == original:
            raise OSError("panne du stockage")
        delete(storage, name)

    monkeypatch.setattr(FileSystemStorage, "delete", failing_delete)

    with django_capture_on_commit_callbacks(execute=True):
        made.delete()

    assert stored([original, variant]) == [True, False]
