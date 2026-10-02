"""Tests des blocs de la fiche technique dans l'écran Projet : onze blocs fixes, dans l'ordre de la
fiche, sous les tableaux en ligne ; un bloc rempli enregistre sa section, un bloc vide n'enregistre
rien, un bloc vidé la supprime."""

import pytest
from config import strings
from content.forms import SectionField
from content.inlines import HANDLE_CLASS
from content.models import Project, Section, SectionKey
from django.db.models.signals import post_save
from django.test import Client
from django.urls import reverse
from factories import BLANK, saved, section, technology
from test_project_admin import LINES, line, new_project_data, rendered_data, saved_project

# Le titre de chaque bloc, dans l'ordre de la fiche (cadrage §6.1, décision 4).
SECTION_TITLES = [
    strings.SECTION_CONTEXT,
    strings.SECTION_STACK,
    strings.SECTION_ARCHITECTURE,
    strings.SECTION_DATA,
    strings.SECTION_SECURITY,
    strings.SECTION_ASYNC,
    strings.SECTION_API,
    strings.SECTION_DEPLOYMENT,
    strings.SECTION_TESTS,
    strings.SECTION_DECISIONS,
    strings.SECTION_RETROSPECTIVE,
]

# Le nom du bloc de chaque section dans le formulaire de l'écran Projet.
BLOCKS = {key: f"section_{key.name.lower()}" for key in SectionKey}


def stored(owner: Project) -> dict[str, str]:
    """Les sections enregistrées de `owner`, clé et corps."""
    return dict(Section.objects.filter(project=owner).values_list("key", "body"))


@pytest.mark.django_db
def test_l_ecran_projet_affiche_les_onze_blocs_dans_l_ordre_de_la_fiche(
    admin_client: Client,
) -> None:
    """Un groupe à part, titré ; un bloc par section, titré du catalogue, dans l'ordre de la fiche,
    jamais un douzième (critère du corps)."""
    response = admin_client.get(reverse("admin:content_project_add"))
    fieldsets = list(response.context["adminform"])

    assert [fieldset.name for fieldset in fieldsets] == [None, strings.SECTIONS_HEADING]
    blocks = [field.field for line in fieldsets[1] for field in line]
    assert [block.name for block in blocks] == list(BLOCKS.values())
    assert [block.label for block in blocks] == SECTION_TITLES
    assert all(isinstance(block.field, SectionField) for block in blocks)


@pytest.mark.django_db
def test_les_blocs_de_la_fiche_suivent_les_champs_et_les_tableaux_en_ligne(
    admin_client: Client,
) -> None:
    """Sous les champs et les technologies du projet (brief, « Comportement souhaité » ; PRD,
    « Back-office »), que le gabarit de l'écran Projet rend avant eux."""
    page = admin_client.get(reverse("admin:content_project_add")).content.decode()

    marks = [
        'name="published"',
        f'id="{LINES}-group"',
        f'name="{BLOCKS[SectionKey.CONTEXT]}"',
        f'name="{BLOCKS[SectionKey.RETROSPECTIVE]}"',
    ]
    assert [page.count(mark) for mark in marks] == [1, 1, 1, 1]
    assert [page.index(mark) for mark in marks] == sorted(page.index(mark) for mark in marks)


@pytest.mark.django_db
def test_le_script_des_lignes_ne_donne_aux_blocs_ni_poignee_ni_bouton_de_suppression(
    admin_client: Client,
) -> None:
    """`inline_rows.js` agit sur tout tableau en ligne de l'écran, par deux sélecteurs : la poignée
    de tri (`.sortable-handle`) et la case « Supprimer ? » qu'il remplace par un bouton
    (décision 6). Le groupe des blocs n'a ni l'une ni l'autre — quand celui des technologies,
    témoin, a la poignée."""
    page = admin_client.get(reverse("admin:content_project_add")).content.decode()
    heading = page.index(f">{strings.SECTIONS_HEADING}</h2>")
    blocks = page[page.rindex("<fieldset", 0, heading) : page.index("</fieldset>", heading)]
    lines = page[page.index(f'id="{LINES}-group"') : heading]

    assert HANDLE_CLASS in lines
    assert all(name in blocks for name in BLOCKS.values())
    assert HANDLE_CLASS not in blocks
    assert 'type="checkbox"' not in blocks


@pytest.mark.django_db
def test_un_bloc_rempli_enregistre_sa_section_et_un_bloc_vide_ou_d_espaces_rien(
    admin_client: Client,
) -> None:
    django = saved(technology(name="Django"))
    data = new_project_data(
        admin_client,
        **line(0, django, 1),
        **{
            BLOCKS[SectionKey.CONTEXT]: "Pourquoi ce projet.",
            BLOCKS[SectionKey.STACK]: "",
            BLOCKS[SectionKey.DATA]: BLANK,
        },
    )

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert stored(Project.objects.get()) == {SectionKey.CONTEXT: "Pourquoi ce projet."}


@pytest.mark.django_db
def test_un_bloc_garde_son_texte_tel_que_saisi(admin_client: Client) -> None:
    """En Markdown, une ligne de tête indentée de quatre espaces est un bloc de code : le texte
    s'enregistre sans être retaillé."""
    django = saved(technology(name="Django"))
    code = "    make dev\n"
    data = new_project_data(admin_client, **line(0, django, 1), **{BLOCKS[SectionKey.TESTS]: code})

    response = admin_client.post(reverse("admin:content_project_add"), data)

    assert response.status_code == 302
    assert stored(Project.objects.get()) == {SectionKey.TESTS: code}


@pytest.mark.django_db
def test_l_ecran_reaffiche_chaque_section_dans_son_bloc(admin_client: Client) -> None:
    portfolio = saved_project(saved(technology(name="Django")))
    saved(section(portfolio, key=SectionKey.CONTEXT, body="Pourquoi."))
    saved(section(portfolio, key=SectionKey.RETROSPECTIVE, body="Ce que j'en retiens."))

    response = admin_client.get(reverse("admin:content_project_change", args=[portfolio.pk]))
    form = response.context["adminform"].form

    assert {name: form[name].value() for name in BLOCKS.values() if form[name].value()} == {
        BLOCKS[SectionKey.CONTEXT]: "Pourquoi.",
        BLOCKS[SectionKey.RETROSPECTIVE]: "Ce que j'en retiens.",
    }


@pytest.mark.django_db
@pytest.mark.parametrize("emptied", ["", BLANK], ids=["bloc vidé", "bloc réduit à des espaces"])
def test_un_bloc_vide_supprime_sa_section_et_un_bloc_change_la_remplace(
    admin_client: Client, emptied: str
) -> None:
    """Le bloc de chaque section enregistrée est rempli à l'ouverture de l'écran : l'auteur le vide,
    le change ou n'y touche pas, et l'enregistrement suit — les autres sections restent."""
    portfolio = saved_project(saved(technology(name="Django")))
    for key in (SectionKey.CONTEXT, SectionKey.STACK, SectionKey.RETROSPECTIVE):
        saved(section(portfolio, key=key, body=f"Avant : {key.label}."))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {
        BLOCKS[SectionKey.CONTEXT]: emptied,
        BLOCKS[SectionKey.STACK]: "Après.",
    }

    response = admin_client.post(url, data)

    assert response.status_code == 302
    assert stored(portfolio) == {
        SectionKey.STACK: "Après.",
        SectionKey.RETROSPECTIVE: f"Avant : {SectionKey.RETROSPECTIVE.label}.",
    }


@pytest.mark.django_db
def test_seul_le_bloc_change_ecrit_sa_section_et_emet_son_signal(admin_client: Client) -> None:
    """Une écriture par bloc changé, signal compris — la purge du cache de #11 s'y branchera ;
    une section dont le bloc n'a pas changé n'est pas réécrite."""
    portfolio = saved_project(saved(technology(name="Django")))
    for key in (SectionKey.CONTEXT, SectionKey.STACK):
        saved(section(portfolio, key=key))
    url = reverse("admin:content_project_change", args=[portfolio.pk])
    data = rendered_data(admin_client, url) | {BLOCKS[SectionKey.STACK]: "Après."}
    written: list[str] = []

    def record(sender: type[Section], instance: Section, **kwargs: object) -> None:
        written.append(instance.key)

    post_save.connect(record, sender=Section)
    try:
        response = admin_client.post(url, data)
    finally:
        post_save.disconnect(record, sender=Section)

    assert response.status_code == 302
    assert written == [SectionKey.STACK]
