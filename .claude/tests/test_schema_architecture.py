"""Tests de la validation de la description d'un schéma d'architecture
(`.claude/skills/schema-architecture/scripts/description.py`).

Le validateur reçoit les icônes disponibles en paramètre : les cas d'erreur s'éprouvent sur un jeu
témoin écrit ici, sans disque ; seule la description de pacome.dev se valide contre le dossier
d'icônes réel du skill. Chaque cas d'erreur part de `BASE`, une description valide qui porte
chaque structure de la forme — sections côte à côte, section imbriquée, demi-colonne, secret —,
et n'y change qu'une valeur. Les cas s'écrivent en littéraux, jamais dérivés des constantes du
script (`cycle-pr/references/tests.md`, « Le rouge se constate, il ne se suppose pas »).
"""

import copy
import json
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from conftest import REPOSITORY_ROOT, load_script, run_in_pipe

description = load_script("schema-architecture", "description")

PACOME_DEV = REPOSITORY_ROOT / "docs" / "schema" / "architecture.json"
# Les icônes disponibles des cas : celles de `BASE` et des descriptions valides, rien d'autre.
ICONES_TEMOINS = frozenset({"keepassxc", "lock-keyhole", "vault", "globe", "docker", "django"})

BASE: dict[str, Any] = {
    "intro": "Un projet témoin.",
    "columns": 4,
    "secretManager": {"name": "KeePassXC", "icon": "keepassxc"},
    "zones": [
        [
            {
                "label": "Gauche",
                "color": "gold",
                "icon": "lock-keyhole",
                "span": [0, 1],
                "rows": [
                    [
                        {"id": "a", "name": "A", "icon": "keepassxc", "column": 0},
                        {"id": "b", "name": "B", "icon": "vault", "column": 1},
                    ]
                ],
            },
            {
                "label": "Droite",
                "color": "blue",
                "span": [2, 3],
                "rows": [[{"id": "c", "name": "C", "icon": "globe", "column": 2.5}]],
            },
        ],
        {
            "label": "Serveur",
            "color": "red",
            "icon": "docker",
            "zones": [
                {
                    "label": "Couloir",
                    "color": "lane",
                    "rows": [
                        [
                            {
                                "id": "d",
                                "name": "D",
                                "icon": "django",
                                "column": 1.5,
                                "secret": "le jeton",
                            }
                        ]
                    ],
                }
            ],
        },
    ],
    "links": [],
}

# La valeur d'un cas qui retire la clé au lieu de la remplacer.
RETIREE = object()


def etapes(chemin: str) -> list[str | int]:
    """Les clés et les indices d'un chemin de la forme `zones[0][1].rows`, dans l'ordre."""
    return [
        int(etape[1:-1]) if etape.startswith("[") else etape
        for etape in chemin.replace("[", ".[").split(".")
        if etape
    ]


def modifiee(chemin: str, valeur: object) -> object:
    """`BASE`, la valeur au bout de `chemin` remplacée par `valeur` — retirée sous `RETIREE` ;
    `valeur` elle-même au chemin vide, la racine."""
    if not chemin:
        return valeur
    racine = copy.deepcopy(BASE)
    *parents, derniere = etapes(chemin)
    noeud: Any = racine
    for etape in parents:
        noeud = noeud[etape]
    if valeur is RETIREE:
        del noeud[derniere]
    else:
        noeud[derniere] = valeur
    return racine


class Cas(NamedTuple):
    """Une forme d'erreur : la valeur posée au chemin `pose` de `BASE`, le chemin que porte
    l'erreur rendue — `pose` s'il est omis —, et ce que son message nomme — la valeur fautive
    en JSON —, `None` quand il n'y a pas de valeur à nommer."""

    pose: str
    valeur: object
    fragment: str | None
    chemin: str | None = None


# La carte `d` de `BASE` — dans une section imbriquée sans span, à secret, visée par aucun lien —,
# où un champ fautif ne fait naître aucune autre erreur.
CARTE_D = "zones[1].zones[0].rows[0][0]"
FORMES: dict[str, dict[str, Cas]] = {
    "champ requis manquant": {
        "intro-manquant": Cas("intro", RETIREE, None),
        "columns-manquant": Cas("columns", RETIREE, None),
        "zones-manquant": Cas("zones", RETIREE, None),
        "secretmanager-name-manquant": Cas("secretManager.name", RETIREE, None),
        "secretmanager-icon-manquant": Cas("secretManager.icon", RETIREE, None),
        "zone-label-manquant": Cas("zones[1].label", RETIREE, None),
        "zone-color-manquant": Cas("zones[1].color", RETIREE, None),
        "carte-id-manquant": Cas(f"{CARTE_D}.id", RETIREE, None),
        "carte-name-manquant": Cas(f"{CARTE_D}.name", RETIREE, None),
        "carte-icon-manquant": Cas(f"{CARTE_D}.icon", RETIREE, None),
        "carte-column-manquant": Cas(f"{CARTE_D}.column", RETIREE, None),
        "lien-from-manquant": Cas("links", [{"to": "a"}], None, "links[0].from"),
        "lien-to-manquant": Cas("links", [{"from": "a"}], None, "links[0].to"),
    },
    "champ d'un autre type": {
        "intro-nombre": Cas("intro", 42, "42"),
        "columns-chaine": Cas("columns", "4", '"4"'),
        "columns-booleen": Cas("columns", True, "true"),
        "secretmanager-chaine": Cas("secretManager", "KeePassXC", '"KeePassXC"'),
        "zones-objet": Cas("zones", {}, "{}"),
        "links-objet": Cas("links", {}, "{}"),
        "secretmanager-name-nombre": Cas("secretManager.name", 7, "7"),
        "secretmanager-icon-nombre": Cas("secretManager.icon", 7, "7"),
        "zone-label-nombre": Cas("zones[1].label", 7, "7"),
        "zone-color-nombre": Cas("zones[1].color", 7, "7"),
        "zone-icon-nombre": Cas("zones[1].icon", 7, "7"),
        "zone-span-chaine": Cas("zones[0][0].span", "0-1", '"0-1"'),
        "zone-span-un-seul-entier": Cas("zones[0][0].span", [0], "[0]"),
        "zone-span-booleen": Cas("zones[0][0].span", [0, True], "[0, true]"),
        "zone-rows-chaine": Cas("zones[0][1].rows", "x", '"x"'),
        "zone-zones-chaine": Cas("zones[1].zones", "x", '"x"'),
        "carte-id-nombre": Cas(f"{CARTE_D}.id", 7, "7"),
        "carte-name-nombre": Cas(f"{CARTE_D}.name", 7, "7"),
        "carte-icon-nombre": Cas(f"{CARTE_D}.icon", 7, "7"),
        "carte-column-chaine": Cas(f"{CARTE_D}.column", "1", '"1"'),
        "carte-column-booleen": Cas(f"{CARTE_D}.column", True, "true"),
        "carte-secret-nombre": Cas(f"{CARTE_D}.secret", 7, "7"),
        "lien-from-nombre": Cas("links", [{"from": 7, "to": "a"}], "7", "links[0].from"),
        "lien-to-nombre": Cas("links", [{"from": "a", "to": 7}], "7", "links[0].to"),
        "lien-route-nombre": Cas(
            "links", [{"from": "a", "to": "b", "route": 7}], "7", "links[0].route"
        ),
        "racine-liste": Cas("", [], "[]"),
        "entree-nombre": Cas("zones[1]", 42, "42"),
        "zone-cote-a-cote-liste": Cas("zones[0][1]", [], "[]"),
        "rangee-nombre": Cas("zones[1].zones[0].rows[0]", 42, "42"),
        "carte-nombre": Cas(CARTE_D, 42, "42"),
        "lien-nombre": Cas("links", [42], "42", "links[0]"),
    },
    "valeur vide ou hors des bornes de son type": {
        "intro-vide": Cas("intro", "", '""'),
        "secretmanager-name-vide": Cas("secretManager.name", "", '""'),
        "zone-label-vide": Cas("zones[1].label", "", '""'),
        "carte-id-vide": Cas(f"{CARTE_D}.id", "", '""'),
        "carte-name-vide": Cas(f"{CARTE_D}.name", "", '""'),
        "carte-secret-vide": Cas(f"{CARTE_D}.secret", "", '""'),
        "lien-from-vide": Cas("links", [{"from": "", "to": "a"}], '""', "links[0].from"),
        "lien-to-vide": Cas("links", [{"from": "a", "to": ""}], '""', "links[0].to"),
        "zones-vide": Cas("zones", [], "[]"),
        "cote-a-cote-vide": Cas("zones[0]", [], "[]"),
        "rangee-vide": Cas("zones[0][1].rows[0]", [], "[]"),
        "columns-zero": Cas("columns", 0, "0"),
    },
    "clé inconnue": {
        "racine-cle-inconnue": Cas("titre", "x", '"titre"'),
        "secretmanager-cle-inconnue": Cas("secretManager.url", "x", '"url"'),
        "zone-cle-inconnue": Cas("zones[1].couleur", "x", '"couleur"'),
        "carte-cle-inconnue": Cas(f"{CARTE_D}.c", 1, '"c"'),
        "lien-cle-inconnue": Cas(
            "links", [{"from": "a", "to": "b", "label": "x"}], '"label"', "links[0].label"
        ),
    },
    "icône absente du dossier": {
        "carte-icone-absente": Cas("zones[0][0].rows[0][0].icon", "absente", '"absente"'),
        "zone-icone-absente": Cas("zones[0][0].icon", "absente", '"absente"'),
        "secretmanager-icone-absente": Cas("secretManager.icon", "absente", '"absente"'),
    },
    "valeur hors de son ensemble": {
        "couleur-inconnue": Cas("zones[1].color", "pink", '"pink"'),
        "route-inconnue": Cas(
            "links", [{"from": "a", "to": "b", "route": "up"}], '"up"', "links[0].route"
        ),
    },
    "colonne": {
        "colonne-apres-la-grille": Cas(f"{CARTE_D}.column", 4, "4"),
        "colonne-avant-la-grille": Cas(f"{CARTE_D}.column", -0.5, "-0.5"),
        "colonne-hors-du-span": Cas("zones[0][0].rows[0][1].column", 2, "2"),
        "colonne-quart": Cas(f"{CARTE_D}.column", 0.25, "0.25"),
        "colonne-nan": Cas(f"{CARTE_D}.column", float("nan"), "NaN"),
    },
    "span": {
        "span-apres-la-grille": Cas("zones[0][1].span", [2, 4], "[2, 4]"),
        "span-avant-la-grille": Cas("zones[0][0].span", [-1, 1], "[-1, 1]"),
        "span-inverse": Cas("zones[0][1].span", [3, 2], "[3, 2]"),
    },
    "zones côte à côte": {
        "cote-a-cote-chevauchement": Cas("zones[0][1].span", [1, 3], "zones[0][0]"),
        "cote-a-cote-sans-span": Cas("zones[0][1].span", RETIREE, None),
    },
    "zone sans contenu": {
        "zone-sans-rows": Cas("zones[1].zones[0].rows", RETIREE, None, "zones[1].zones[0]"),
        "zone-rows-vide": Cas("zones[1].zones[0].rows", [], None, "zones[1].zones[0]"),
        "zone-zones-vide": Cas("zones[1].zones", [], None, "zones[1]"),
    },
    "références": {
        "id-en-double": Cas("zones[0][1].rows[0][0].id", "a", '"a"'),
        "lien-vers-une-carte-inconnue": Cas(
            "links", [{"from": "a", "to": "fantome"}], '"fantome"', "links[0].to"
        ),
        "lien-depuis-une-carte-inconnue": Cas(
            "links", [{"from": "fantome", "to": "a"}], '"fantome"', "links[0].from"
        ),
        "lien-vers-elle-meme": Cas("links", [{"from": "a", "to": "a"}], '"a"', "links[0].to"),
    },
    "secret sans gestionnaire": {
        "secret-sans-secretmanager": Cas("secretManager", RETIREE, None, f"{CARTE_D}.secret"),
    },
}
CAS = {nom: cas for groupe in FORMES.values() for nom, cas in groupe.items()}


@pytest.mark.parametrize("cas", CAS.values(), ids=CAS.keys())
def test_une_forme_d_erreur_rend_une_erreur_au_chemin_du_champ_fautif(cas: Cas) -> None:
    """**Dénombrement des formes, écrit avant le premier correctif** (#217, bloc A, 2026-11-05).

    Population : la forme verrouillée de la description — 5 objets (racine, `secretManager`,
    zone, carte, lien), 21 champs dont 13 requis, 2 contenants positionnels (entrée, rangée) —
    et les contraintes qui lient ses champs. **84 formes**, une par cas de `FORMES` :

    - champ requis manquant : 13, un par champ requis ;
    - champ d'un autre type : 31 — un par champ (21), le booléen là où un entier est attendu
      (`columns`, `column`, borne de `span`), le `span` d'un seul entier, et chaque contenant
      qui n'est pas de son type (racine, entrée, zone côte à côte, rangée, carte, lien) ;
    - valeur vide ou hors des bornes de son type : 12 — chaque chaîne non vide (8), chaque liste
      non vide (racine `zones`, zones côte à côte, rangée), `columns` à 0 ;
    - clé inconnue : 5, une par objet ;
    - icône absente du dossier : 3 (carte, zone, `secretManager`) ;
    - valeur hors de son ensemble : 2 (`color`, `route`) ;
    - colonne hors de la grille (2, une par bord), hors du span de sa zone (1), pas un multiple
      de 0,5 (2, dont NaN, que `json.loads` accepte) : 5 ;
    - span hors de la grille (2, une par bord) ou inversé (1) : 3 ;
    - zones côte à côte qui se chevauchent, ou sans span : 2 ;
    - zone sans `rows` ni `zones` non vides : 3 ;
    - `id` en double, lien vers ou depuis une carte inconnue, lien d'une carte vers elle-même : 4 ;
    - `secret` sans `secretManager` : 1.

    Chaque cas rend **une** erreur, au chemin exact, dont le message nomme la valeur fautive.
    """
    erreurs = description.valider(modifiee(cas.pose, cas.valeur), ICONES_TEMOINS)

    assert [erreur.chemin for erreur in erreurs] == [cas.chemin or cas.pose]
    assert cas.fragment is None or cas.fragment in erreurs[0].message


def test_les_cas_d_erreur_comptent_les_formes_de_leur_docstring() -> None:
    """Le dénombrement de la docstring ci-dessus, recompté à chaque exécution
    (`.claude/rules/cleanup-verbatim.md`, passe « affirmations ») : un nom de cas répété d'un
    groupe à l'autre en ôterait un de `CAS`."""
    assert {groupe: len(cas) for groupe, cas in FORMES.items()} == {
        "champ requis manquant": 13,
        "champ d'un autre type": 31,
        "valeur vide ou hors des bornes de son type": 12,
        "clé inconnue": 5,
        "icône absente du dossier": 3,
        "valeur hors de son ensemble": 2,
        "colonne": 5,
        "span": 3,
        "zones côte à côte": 2,
        "zone sans contenu": 3,
        "références": 4,
        "secret sans gestionnaire": 1,
    }
    assert len(CAS) == 84


def test_une_passe_rend_toutes_les_erreurs_et_verifie_les_freres_d_un_noeud_fautif() -> None:
    """Une zone d'un autre type n'arrête pas la lecture de sa voisine côte à côte, ni des
    liens."""
    fautive = copy.deepcopy(BASE)
    fautive["zones"][0][0] = 42
    fautive["zones"][0][1]["rows"][0][0]["column"] = 9
    fautive["links"] = [{"from": "c", "to": "fantome"}]

    erreurs = description.valider(fautive, ICONES_TEMOINS)

    assert sorted(erreur.chemin for erreur in erreurs) == [
        "links[0].to",
        "zones[0][0]",
        "zones[0][1].rows[0][0].column",
    ]


def carte(identifiant: str, colonne: float, **autres: str) -> dict[str, Any]:
    """Une carte valide pour le jeu d'icônes témoin."""
    return {
        "id": identifiant,
        "name": identifiant.upper(),
        "icon": "globe",
        "column": colonne,
        **autres,
    }


VALIDES: dict[str, dict[str, Any]] = {
    "base-des-cas-d-erreur": BASE,
    "une-seule-section": {
        "intro": "Un service seul.",
        "columns": 1,
        "secretManager": {"name": "Bitwarden", "icon": "vault"},
        "zones": [
            {
                "label": "Serveur",
                "color": "grey",
                "rows": [[carte("app", 0, secret="la clé d'API")], [carte("base", 0)]],
            }
        ],
        "links": [{"from": "app", "to": "base"}],
    },
    "sans-lien": {
        "intro": "Deux sections sans flèche.",
        "columns": 2,
        "zones": [
            {"label": "Haut", "color": "blue", "rows": [[carte("a", 0.5)]]},
            {"label": "Bas", "color": "green", "rows": [[carte("b", 0), carte("c", 1)]]},
        ],
    },
    "sans-sections-cote-a-cote": {
        "intro": "Des sections empilées.",
        "columns": 3,
        "zones": [
            {"label": "Internet", "color": "blue", "icon": "globe", "rows": [[carte("v", 1)]]},
            {
                "label": "Hôte",
                "color": "red",
                "zones": [{"label": "Conteneurs", "color": "lane", "rows": [[carte("w", 2)]]}],
            },
        ],
        "links": [{"from": "v", "to": "w", "route": "right"}],
    },
    "sans-gestionnaire-de-secrets": {
        "intro": "Aucun secret marqué.",
        "columns": 2,
        "zones": [
            [
                {"label": "Gauche", "color": "gold", "span": [0, 0], "rows": [[carte("g", 0)]]},
                {"label": "Droite", "color": "orange", "span": [1, 1], "rows": [[carte("d", 1)]]},
            ]
        ],
        "links": [{"from": "g", "to": "d", "route": "under"}],
    },
}


@pytest.mark.parametrize("valide", VALIDES.values(), ids=VALIDES.keys())
def test_une_description_d_une_autre_forme_est_valide(valide: dict[str, Any]) -> None:
    """Le skill ne suppose aucune architecture (#217, « Décisions », 2026-11-05)."""
    assert description.valider(valide, ICONES_TEMOINS) == []


def test_la_description_de_pacome_dev_est_valide_avec_les_icones_du_dossier() -> None:
    """La description committée, contre les icônes réellement copiées dans le skill."""
    pacome_dev = json.loads(PACOME_DEV.read_text(encoding="utf-8"))

    assert description.valider(pacome_dev, description.icones_disponibles()) == []


def test_la_cli_valide_la_description_de_pacome_dev() -> None:
    """Sortie 0 et la seule ligne « valide »."""
    done = run_in_pipe("schema-architecture", "description", str(PACOME_DEV))

    assert (done.returncode, done.stdout.decode("utf-8").splitlines()) == (0, ["valide"])


def test_la_cli_rend_une_ligne_par_erreur_en_utf_8_dans_un_tube(tmp_path: Path) -> None:
    """Sortie 1, une ligne `<chemin> : <message>` par erreur, lisible en UTF-8 dans le tube que
    `run_in_pipe` met en cp1252 (`pipeline.config.md`, « Qualité »)."""
    fautive = copy.deepcopy(BASE)
    fautive["intro"] = 42
    fautive["links"] = [{"from": "a", "to": "fantôme"}]
    chemin = tmp_path / "architecture.json"
    chemin.write_text(json.dumps(fautive, ensure_ascii=False), encoding="utf-8")

    done = run_in_pipe("schema-architecture", "description", str(chemin))

    lignes = done.stdout.decode("utf-8").splitlines()
    assert done.returncode == 1
    assert [ligne.split(" : ")[0] for ligne in lignes] == ["intro", "links[0].to"]
    assert '"fantôme"' in lignes[1]


ILLISIBLES = {
    "fichier-absent": None,
    "pas-en-utf-8": '{"intro": "é"}'.encode("cp1252"),
    "json-mal-forme": b'{"intro": ',
}


@pytest.mark.parametrize("contenu", ILLISIBLES.values(), ids=ILLISIBLES.keys())
def test_la_cli_sort_en_2_avec_un_motif_d_une_ligne_sur_un_fichier_illisible(
    contenu: bytes | None, tmp_path: Path
) -> None:
    """Fichier absent, pas en UTF-8 ou JSON mal formé : sortie 2, une ligne sur la sortie
    d'erreur, rien sur la sortie standard."""
    chemin = tmp_path / "architecture.json"
    if contenu is not None:
        chemin.write_bytes(contenu)

    done = run_in_pipe("schema-architecture", "description", str(chemin))

    assert (done.returncode, done.stdout) == (2, b"")
    assert len(done.stderr.decode("utf-8").splitlines()) == 1
