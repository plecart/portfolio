"""Tests de la liste des projets de l'admin : ses colonnes, et l'ordre des cartes de la table (D77,
spec §1.9). La liste suit toujours les positions — ni ses en-têtes ni l'adresse ne la trient —,
l'auteur la réordonne par glisser-déposer, ou au clavier, puis l'enregistre une fois (ADR 0013).

Le geste lui-même se regarde à l'écran, faute de navigateur dans la suite du back (ADR 0013,
« Conséquences ») : ces tests tiennent ce que le serveur livre au script, et ce qu'il enregistre
de ce que le script envoie.
"""

import re
from typing import Any

import pytest
from config import strings
from content.inlines import HANDLE_CLASS, POSITION, POSITION_CLASS
from content.models import Project
from django.templatetags.static import static
from django.test import Client
from django.urls import reverse
from django.utils.html import escape
from django.utils.text import capfirst
from factories import project, saved, technology
from pytest_django import DjangoCaptureOnCommitCallbacks
from static_code import code
from test_cache import CHANGED_SUMMARY, FACTORY_SLUG, SUMMARY, summary
from test_project_admin import INLINE_ROWS_SCRIPT, INLINE_ROWS_STYLE, saved_project

# Le paramètre d'adresse qui trie une liste de l'admin sur la colonne de son index
# (`django.contrib.admin.views.main.ORDER_VAR`), et l'index de la colonne du titre : la case de
# sélection, la poignée, puis le titre.
ORDER_VAR = "o"
TITLE_COLUMN = 2

# Les tris qu'une adresse demande, sur le titre : la liste les ignore.
ADDRESSED_ORDERS = {
    "sans tri": "",
    "titre croissant": f"?{ORDER_VAR}={TITLE_COLUMN}",
    "titre décroissant": f"?{ORDER_VAR}=-{TITLE_COLUMN}",
}


def changelist() -> str:
    """L'adresse de la liste des projets."""
    return reverse("admin:content_project_changelist")


def stored() -> dict[str, int]:
    """La position de chaque projet, par slug."""
    return dict(Project.objects.values_list("slug", POSITION))


def projects(*slugs: str) -> None:
    """Un projet enregistré par slug, son titre pour slug, aux positions 1, 2, 3… dans l'ordre des
    slugs."""
    for position, slug in enumerate(slugs, start=1):
        saved(project(slug=slug, title=slug, position=position))


def shown(response: Any) -> list[str]:
    """Les slugs que la liste rendue par `response` montre, dans son ordre."""
    return [listed.slug for listed in response.context["cl"].result_list]


def sent(response: Any, order: list[str] | None = None) -> dict[str, object]:
    """Le formulaire de la liste que `response` rend, tel qu'un navigateur l'envoie à
    « Enregistrer » : formulaire de gestion, clé et position cachée de chaque ligne affichée.

    Sans `order`, chaque ligne envoie la position rendue, comme sans le script. Avec `order`, les
    slugs des lignes affichées dans l'ordre où l'auteur les a placées : le script numérote les
    positions de 1 à n dans cet ordre, et chaque ligne garde son index.
    """
    formset = response.context["cl"].formset
    management = formset.management_form
    data: dict[str, object] = {
        management.add_prefix(name): value for name, value in management.initial.items()
    }
    for form in formset.forms:
        data |= {form.add_prefix(name): form[name].value() for name in form.fields}
        if order is not None:
            data[form.add_prefix(POSITION)] = order.index(form.instance.slug) + 1
    return data | {"_save": "Enregistrer"}


@pytest.mark.django_db
def test_la_liste_des_projets_montre_poignee_titre_type_statut_vitrine_et_publication(
    admin_client: Client,
) -> None:
    """La poignée en tête de ligne, puis les colonnes du projet ; la position, cachée, n'en est pas
    une à l'écran (`inline_rows.css`)."""
    saved_project(saved(technology(name="Django")))

    page = admin_client.get(changelist()).content.decode()

    columns = [
        strings.ADMIN_ROW_ORDER,
        strings.PROJECT_TITLE,
        strings.PROJECT_KIND,
        strings.PROJECT_STATUS,
        strings.PROJECT_SHOWCASE,
        strings.PROJECT_PUBLISHED,
    ]
    positions = [page.find(f">{escape(capfirst(column))}</") for column in columns]
    assert -1 not in positions
    assert positions == sorted(positions)


@pytest.mark.django_db
@pytest.mark.parametrize("query", ADDRESSED_ORDERS.values(), ids=ADDRESSED_ORDERS.keys())
def test_la_liste_des_projets_suit_toujours_les_positions(admin_client: Client, query: str) -> None:
    """L'ordre affiché est celui qu'on enregistre : une liste triée par une adresse — un favori,
    l'historique du navigateur, un retour de fiche qui garde le tri d'avant — enregistrerait un
    autre ordre que celui des cartes. Ni les titres ni les clés ne donnent ici celui des
    positions."""
    projects("c", "a", "b")

    response = admin_client.get(changelist() + query)

    assert shown(response) == ["c", "a", "b"]


@pytest.mark.django_db
def test_les_en_tetes_de_la_liste_des_projets_ne_la_trient_pas(admin_client: Client) -> None:
    """Aucun en-tête ne porte le lien de tri de Django (`admin/change_list_results.html`)."""
    projects("a", "b")

    page = admin_client.get(changelist()).content.decode()

    assert f'href="?{ORDER_VAR}=' not in page


@pytest.mark.django_db
def test_enregistrer_la_liste_range_les_projets_dans_l_ordre_affiche(admin_client: Client) -> None:
    """Le geste principal (critère de #288) : D glissé en deuxième, puis « Enregistrer »."""
    projects("a", "b", "c", "d", "e")
    response = admin_client.get(changelist())

    saved_list = admin_client.post(changelist(), sent(response, ["a", "d", "b", "c", "e"]))

    assert saved_list.status_code == 302
    assert stored() == {"a": 1, "d": 2, "b": 3, "c": 4, "e": 5}


@pytest.mark.django_db
def test_enregistrer_ne_reecrit_que_les_positions_des_lignes_affichees(
    admin_client: Client,
) -> None:
    """Les lignes affichées reprennent entre elles leurs positions, dans leur nouvel ordre : une
    liste filtrée — ou paginée — ne heurte jamais un projet qu'elle ne montre pas. Les projets
    publiés sont affichés, les brouillons s'intercalent entre eux. `x` poste la position qu'il
    avait, et en change : la position enregistrée n'est pas celle que la ligne poste."""
    for slug, position, published in [
        ("u", 1, False),
        ("x", 2, True),
        ("v", 3, False),
        ("y", 5, True),
        ("w", 7, False),
        ("z", 9, True),
    ]:
        saved(project(slug=slug, title=slug, position=position, published=published))
    filtered = f"{changelist()}?published__exact=1"
    response = admin_client.get(filtered)
    assert shown(response) == ["x", "y", "z"]

    saved_list = admin_client.post(filtered, sent(response, ["z", "x", "y"]))

    assert saved_list.status_code == 302
    assert stored() == {"u": 1, "z": 2, "v": 3, "x": 5, "w": 7, "y": 9}


@pytest.mark.django_db
@pytest.mark.parametrize("same_position", [False, True], ids=["sans le script", "positions égales"])
def test_une_liste_envoyee_sans_deplacement_ne_change_rien(
    admin_client: Client, same_position: bool
) -> None:
    """Sans le script — désactivé, ou en échec —, chaque ligne envoie la position rendue ; une même
    position partout, l'ordre affiché la départage, comme deux positions stockées égales. Rien ne
    change d'ordre, et aucun projet n'est enregistré : sa date de modification, que lit le plan du
    site, reste la sienne."""
    for slug, position in [("p", 3), ("q", 3), ("r", 7)]:
        saved(project(slug=slug, title=slug, position=position))
    before = list(Project.objects.values_list("slug", POSITION, "updated_at"))
    response = admin_client.get(changelist())
    data = sent(response)
    if same_position:
        data |= {key: 1 for key in data if key.endswith(f"-{POSITION}")}

    saved_list = admin_client.post(changelist(), data)

    assert saved_list.status_code == 302
    assert list(Project.objects.values_list("slug", POSITION, "updated_at")) == before


@pytest.mark.django_db
def test_une_ligne_de_la_liste_arrivee_sans_position_se_range_a_la_sienne(
    admin_client: Client,
) -> None:
    """La position est facultative dans le formulaire : une ligne qui l'envoie vide — ni l'écran ni
    le script n'en produisent — se range à sa position stockée, au lieu de faire échouer
    l'enregistrement. `c` arrive vide, `b` et `a` envoient 1 et 2 : `c` reste après eux, là où une
    position vide comptée pour zéro le mettrait en tête."""
    projects("a", "b", "c")
    response = admin_client.get(changelist())
    [emptied] = [
        form.add_prefix(POSITION)
        for form in response.context["cl"].formset.forms
        if form.instance.slug == "c"
    ]

    saved_list = admin_client.post(changelist(), sent(response, ["b", "a", "c"]) | {emptied: ""})

    assert saved_list.status_code == 302
    assert stored() == {"b": 1, "a": 2, "c": 3}


@pytest.mark.django_db
def test_une_liste_envoyee_apres_la_disparition_d_un_projet_affiche_est_reaffichee_en_erreur(
    admin_client: Client,
) -> None:
    """Un projet affiché est supprimé — par un autre onglet — avant l'envoi de la liste : sa ligne
    arrive sans objet et le formulaire la refuse. `SortableListFormSet.clean` rend alors la main
    avant de lire les positions de cette ligne, qu'elle n'a pas : la liste se réaffiche avec son
    erreur, au lieu d'une 500, et les projets restants gardent leur position."""
    projects("a", "b", "c")
    data = sent(admin_client.get(changelist()))
    Project.objects.filter(slug="b").delete()

    reshown = admin_client.post(changelist(), data)

    assert reshown.status_code == 200
    assert any(reshown.context["cl"].formset.errors)
    assert stored() == {"a": 1, "c": 3}


@pytest.mark.django_db
def test_enregistrer_la_liste_vide_le_cache_de_l_api(
    admin_client: Client,
    client: Client,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Chaque projet repositionné s'enregistre par `save`, dont le signal vide le cache
    (`purge_after_commit`) : jamais par une écriture groupée, qui n'en émet aucun. Témoin, comme
    dans `test_cache.py` : un résumé changé sans signal, que la liste en cache ne montre pas."""
    saved(project(published=True))
    saved(project(slug="autre", published=True))
    summary(client)
    Project.objects.filter(slug=FACTORY_SLUG).update(summary=CHANGED_SUMMARY)
    from_cache = summary(client)
    response = admin_client.get(changelist())

    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(changelist(), sent(response, ["autre", FACTORY_SLUG]))

    assert (from_cache, summary(client)) == (SUMMARY, CHANGED_SUMMARY)


@pytest.mark.django_db
def test_la_liste_des_projets_livre_au_script_les_prises_qu_il_lit(admin_client: Client) -> None:
    """`inline_rows.js` n'a pas de test de navigateur (ADR 0013) : ce test en tient la part serveur
    sur la liste, comme `test_project_admin.py` sur les tableaux en ligne. Une poignée par ligne,
    hors de tout lien — la colonne du lien est le titre —, la position cachée à la classe que le
    script remplit, le script et sa feuille, et ce que rend le gabarit de Django
    (`admin/change_list.html`, `admin/change_list_results.html`), qu'une montée de version peut
    déplacer : le formulaire, le tableau et ses lignes, les classes de la colonne de la position que
    la feuille cache, et le bouton « Enregistrer ». Le script émet aussi un `change` sur la position
    d'une ligne déplacée : seul cet événement arme l'avertissement de Django avant une action
    (`admin/js/actions.js`, `list_editable_changed`), que le glisser et les flèches ne produisent
    pas."""
    projects("a", "b", "c")
    script, style = code(INLINE_ROWS_SCRIPT), code(INLINE_ROWS_STYLE)

    page = admin_client.get(changelist()).content.decode()

    for hook in (f".{HANDLE_CLASS}", f"input.{POSITION_CLASS}", "#result_list > tbody > tr"):
        assert hook in script
    assert re.search(
        rf'input\.{POSITION_CLASS}"\)\?\.dispatchEvent\(\s*new Event\("change", \{{ bubbles: true \}}\)',
        script,
    )
    for hook in ("#result_list", f".column-{POSITION}", f".field-{POSITION}"):
        assert hook in style
    for asset in (INLINE_ROWS_SCRIPT, INLINE_ROWS_STYLE):
        assert static(asset) in page
    handle = f'<td class="field-move"><button type="button" class="{HANDLE_CLASS}"'
    assert page.count(handle) == 3
    hidden = re.findall(rf'<td class="field-{POSITION}"><input type="hidden"[^>]*>', page)
    assert len(hidden) == 3
    assert all(f'class="{POSITION_CLASS}"' in field for field in hidden)
    assert f'<th scope="col" class="column-{POSITION}">' in page
    assert re.search(
        r'<form id="changelist-form".*<table id="result_list">.*<tbody>\s*<tr>', page, re.DOTALL
    )
    assert 'name="_save"' in page
