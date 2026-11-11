"""Tests du gabarit du site (`content/site.py`, #265) : ses trois paires de marqueurs, chacune une
fois et dans l'ordre ; ce qu'une vue en remplit ; l'identité du site qu'il porte, seule source ; et
tout gabarit qui manque à l'un ou à l'autre est une erreur qui le nomme.

Le gabarit est le fichier de fixture de test, à une exception : le gabarit source du front, que le
poste sert tel quel (`.env.example`), doit se lire.
"""

from pathlib import Path

import pytest
from content.site import SLOTS, Site, SiteTemplateError, read_template
from system_commands import REPOSITORY_ROOT

# Le gabarit de fixture de test, puis ses octets.
FIXTURE = Path(__file__).with_name("gabarit-apercu.html")
TEMPLATE = FIXTURE.read_bytes()

# Les paires du gabarit, dans leur ordre, écrites ici sans les lire dans le module : une paire
# retirée de `SLOTS` y garde ses cas, qui rougissent, au lieu de les emporter.
PAIRS = ("meta", "page", "root")

# L'identité du site que porte le gabarit de fixture : d'autres valeurs que celles du front, pour
# qu'aucune ne puisse venir d'ailleurs.
SITE = Site(
    home="https://site.test/",
    person="https://site.test/#auteur",
    name="Auteur",
    same_as=("https://profil.test/un", "https://profil.test/deux"),
    description="Portfolio de l’auteur.",
)

# Les éléments de l'identité dans le gabarit de fixture, tels qu'il les écrit.
CANONICAL = b'<link rel="canonical" href="https://site.test/" />'
DESCRIPTION = '<meta name="description" content="Portfolio de l’auteur." />'.encode()
JSON_LD_START = b'<script type="application/ld+json">'
JSON_LD = JSON_LD_START + TEMPLATE.partition(JSON_LD_START)[2].partition(b"</script>")[0]
# Le script JSON-LD entier, fermé : celui qui porte le `Person`.
JSON_LD_SCRIPT = JSON_LD + b"</script>"


def markers(name: str) -> tuple[bytes, bytes]:
    """Les deux marqueurs de la paire `name`, écrits ici sans les lire dans le module."""
    return f"<!--{name}:start-->".encode(), f"<!--{name}:end-->".encode()


def pair(name: str) -> bytes:
    """La paire `name` du gabarit de fixture, marqueurs compris."""
    start, end = markers(name)
    return start + TEMPLATE.partition(start)[2].partition(end)[0] + end


def marker_defects(name: str) -> dict[str, tuple[bytes, str]]:
    """Les défauts des marqueurs de la paire `name`, chacun dans un gabarit, et ce que le message
    doit nommer : la paire."""
    start, end = markers(name)
    defects = {
        "sans marqueur": TEMPLATE.replace(start, b"").replace(end, b""),
        "marqueur de début doublé": TEMPLATE.replace(start, start * 2),
        "marqueur de fin doublé": TEMPLATE.replace(end, end * 2),
        "sans marqueur de début": TEMPLATE.replace(start, b""),
        "sans marqueur de fin": TEMPLATE.replace(end, b""),
        "marqueurs inversés": TEMPLATE.replace(start, b"INVERSION")
        .replace(end, start)
        .replace(b"INVERSION", end),
    }
    return {f"{name} {defect}": (content, start.decode()) for defect, content in defects.items()}


# Les gabarits défectueux, chacun avec ce que le message doit nommer en plus du fichier : la paire
# en défaut pour chaque défaut de ses marqueurs, l'élément en défaut pour l'identité du site.
BROKEN_TEMPLATES: dict[str, tuple[bytes, str]] = {
    **{key: value for name in PAIRS for key, value in marker_defects(name).items()},
    "paires meta et page inversées": (
        TEMPLATE.replace(pair("meta"), b"PAIRE")
        .replace(pair("page"), pair("meta"))
        .replace(b"PAIRE", pair("page")),
        "<!--page:start-->",
    ),
    "pas en UTF-8": (TEMPLATE + bytes([0xFF]), "UTF-8"),
    "sans canonical": (TEMPLATE.replace(CANONICAL, b""), "canonical"),
    "canonical hors de la paire page": (
        TEMPLATE.replace(CANONICAL, b"").replace(b"</head>", CANONICAL + b"</head>"),
        "canonical",
    ),
    "deux canonical": (TEMPLATE.replace(CANONICAL, CANONICAL * 2), "canonical"),
    "canonical sans adresse": (
        TEMPLATE.replace(CANONICAL, b'<link rel="canonical" />'),
        "canonical",
    ),
    "sans description": (TEMPLATE.replace(DESCRIPTION, b""), "description"),
    "description hors de la paire meta": (
        TEMPLATE.replace(DESCRIPTION, b"").replace(b"</head>", DESCRIPTION + b"</head>"),
        "description",
    ),
    "description sans contenu": (
        TEMPLATE.replace(DESCRIPTION, b'<meta name="description" />'),
        "description",
    ),
    "sans JSON-LD": (TEMPLATE.replace(JSON_LD_SCRIPT, b""), "Person"),
    # L'identité ne se lit que hors des paires : une vue en remplace le contenu, et une fiche qui
    # remplit `page` ôterait à son `author` le `Person` qu'il cite.
    **{
        f"JSON-LD dans la paire {name}": (
            TEMPLATE.replace(JSON_LD_SCRIPT, b"").replace(
                markers(name)[1], JSON_LD_SCRIPT + markers(name)[1]
            ),
            "Person",
        )
        for name in PAIRS
    },
    "JSON-LD illisible": (TEMPLATE.replace(b'"@context"', b"@context"), "JSON-LD"),
    "JSON-LD qui n'est pas un objet": (
        TEMPLATE.replace(JSON_LD, JSON_LD_START + b"[]"),
        "@graph",
    ),
    "JSON-LD sans graphe": (TEMPLATE.replace(b'"@graph"', b'"@liste"'), "@graph"),
    "graphe qui n'est pas une liste": (
        TEMPLATE.replace(b'"@graph": [', b'"@graph": {}, "noeuds": ['),
        "@graph",
    ),
    "sans Person": (TEMPLATE.replace(b'"Person"', b'"Organization"'), "Person"),
    "deux Person": (TEMPLATE.replace(b'"WebSite"', b'"Person"'), "Person"),
    "Person sans @id": (TEMPLATE.replace(b'"@id"', b'"@ident"'), "@id"),
    "nom qui n'est pas un texte": (
        TEMPLATE.replace(b'"name": "Auteur",', b'"name": 1,'),
        "name",
    ),
    "profils qui ne sont pas une liste": (
        TEMPLATE.replace(b'"sameAs": [', b'"sameAs": "https://profil.test/un", "autres": ['),
        "sameAs",
    ),
    "profil qui n'est pas un texte": (
        TEMPLATE.replace(b'"https://profil.test/deux"', b"2"),
        "sameAs",
    ),
}


def test_le_gabarit_a_trois_paires_dans_leur_ordre() -> None:
    """L'autre sens des cas écrits pour chaque paire (`PAIRS`) : une paire ajoutée au module en
    réclame les siens."""
    assert SLOTS == PAIRS


def test_le_gabarit_porte_l_identite_du_site() -> None:
    """L'adresse de l'accueil, l'auteur et la description se lisent dans le gabarit, seule source."""
    assert read_template(FIXTURE).site == SITE


def test_le_gabarit_source_du_front_se_lit() -> None:
    """Ses trois paires et l'identité du site : sans elles, le poste rendrait chaque fiche en
    `500` — la version compilée, que sert la production, en garde la forme (`e2e/page.spec.ts`)."""
    site = read_template(REPOSITORY_ROOT / "apps" / "web" / "index.html").site

    assert all(site)


def test_sans_bloc_le_gabarit_est_rendu_octet_pour_octet() -> None:
    """Une paire que la vue ne remplit pas garde son contenu."""
    assert read_template(FIXTURE).fill({}) == TEMPLATE


def test_remplir_une_paire_remplace_son_contenu_et_garde_ses_marqueurs() -> None:
    """Le contenu de la paire, et lui seul : marqueurs et reste du gabarit gardent leurs octets."""
    start, end = markers("page")
    before, _, rest = TEMPLATE.partition(start)

    filled = read_template(FIXTURE).fill({"page": b"<p>X</p>"})

    assert filled == before + start + b"<p>X</p>" + end + rest.partition(end)[2]


@pytest.mark.parametrize(
    ("content", "named"), BROKEN_TEMPLATES.values(), ids=BROKEN_TEMPLATES.keys()
)
def test_un_gabarit_defectueux_est_une_erreur_qui_nomme_le_fichier_et_le_defaut(
    tmp_path: Path, content: bytes, named: str
) -> None:
    """Une paire absente, doublée ou hors de son ordre, ou une identité du site absente, en double
    ou d'un autre type : jamais une page sans ses balises, ni une identité devinée."""
    path = tmp_path / "index.html"
    path.write_bytes(content)

    with pytest.raises(SiteTemplateError) as raised:
        read_template(path)

    assert str(path) in str(raised.value)
    assert named in str(raised.value)
