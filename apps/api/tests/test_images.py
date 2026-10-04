"""Tests de ce que la couverture et l'image de galerie ont en commun, éprouvé sur l'une et l'autre :
l'original — le fichier que l'auteur téléverse —, sa validation, son nom de stockage et ses
lectures, la légende, l'état de traitement et les variantes."""

import re
from collections.abc import Callable, Generator

import pytest
from config import strings
from content.images import validate_original
from content.models import Cover, GalleryImage, ProcessingState, Project, ProjectImage
from counting_storage import CountingStorage
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.files.storage import default_storage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from factories import BLANK, SVG, cover, gallery_image, image_upload, project, saved
from refusals import refusals

type ImageFactory = Callable[..., ProjectImage]

# La borne de la légende (spec §7), écrite ici et non lue sur le modèle, pour qu'une borne changée
# fasse rougir ce fichier.
CAPTION_MAX_LENGTH = 50

# Une variante telle que le worker de #12 la décrira (décision 5).
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
]

# Les formes d'un fichier qui n'est pas une image JPEG, PNG ou WebP — c'est le dénombrement qui
# compte : un fichier qui n'est pas une image, des images d'autres formats sous une extension
# admise, et un document SVG, qu'un `<img>` afficherait mais que le worker de #12 ne convertit pas.
NOT_ACCEPTED = [
    ("texte", SimpleUploadedFile("notes.png", b"Pas une image.")),
    ("GIF nommé .png", image_upload("image.png", image_format="GIF")),
    ("BMP nommé .jpg", image_upload("image.jpg", image_format="BMP")),
    ("TIFF nommé .webp", image_upload("image.webp", image_format="TIFF")),
    ("SVG nommé .png", SimpleUploadedFile("icone.png", SVG)),
]


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


def test_un_original_valide_reste_pret_a_etre_lu_depuis_le_debut() -> None:
    """`Storage.save` attend un fichier « ready to be read from the beginning »
    (`django/core/files/storage/base.py`) : la validation, qui lit son en-tête, le rend rembobiné.
    Le stockage sur disque rembobine de lui-même ; un autre stockage n'y est pas tenu."""
    upload = image_upload()

    validate_original(upload)

    assert upload.tell() == 0


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


@pytest.fixture(params=[cover, gallery_image], ids=["couverture", "image de galerie"])
def image(request: pytest.FixtureRequest) -> ImageFactory:
    """La fabrique de chacun des deux modèles : une règle commune vaut pour l'un et l'autre."""
    return request.param


def constraint_name(made: ProjectImage, rule: str) -> str:
    """Le nom que porte la contrainte `rule` dans la table du modèle de `made`."""
    return f"content_{made._meta.model_name}_{rule}"


@pytest.mark.parametrize(
    ("model", "own_fields"),
    [(Cover, ["project"]), (GalleryImage, ["project", "position"])],
    ids=["couverture", "image de galerie"],
)
def test_une_image_porte_son_original_ses_dimensions_sa_legende_son_etat_et_ses_variantes(
    model: type[ProjectImage], own_fields: list[str]
) -> None:
    """Une seule définition des champs communs (critère du corps) : ceux de la base d'abord."""
    assert [field.name for field in model._meta.concrete_fields] == [
        "id",
        "original",
        "width",
        "height",
        "caption",
        "state",
        "variants",
        *own_fields,
    ]


def test_les_valeurs_de_l_etat_sont_celles_que_l_api_expose() -> None:
    """Les valeurs stockées sont un contrat : l'API de #10 les expose telles quelles (ADR 0010),
    le worker de #12 les écrit."""
    assert ProcessingState.values == ["pending", "ready", "failed"]


@pytest.mark.django_db
def test_une_image_nait_en_attente_sans_variante(portfolio: Project, image: ImageFactory) -> None:
    """Rien ici ne la traite : le worker de #12 la fera passer à « prêt » ou à « échec »."""
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
def test_un_png_nomme_jpg_est_enregistre_sous_png(portfolio: Project) -> None:
    """L'extension est celle du format reconnu, d'où le serveur de fichiers tire le type servi."""
    made = saved(gallery_image(portfolio, original=image_upload("image.jpg", image_format="PNG")))

    assert (made.original.name or "").endswith("/original.png")


@pytest.mark.django_db
def test_deux_televersements_du_meme_fichier_ont_deux_noms(portfolio: Project) -> None:
    first = saved(gallery_image(portfolio, original=image_upload("image.png")))
    second = saved(gallery_image(portfolio, original=image_upload("image.png"), position=2))

    assert first.original.name != second.original.name


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
    stored = saved(image(portfolio))
    loaded = type(stored).objects.get(pk=stored.pk)
    loaded.caption = "Une autre légende."

    loaded.full_clean()
    loaded.original = loaded.original
    loaded.save()

    assert witness.opened == []
    loaded.refresh_from_db()
    assert (loaded.width, loaded.height) == (stored.width, stored.height)
