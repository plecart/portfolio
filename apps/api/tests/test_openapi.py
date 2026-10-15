"""Tests du schéma OpenAPI de l'API publique : le fichier versionné que `make openapi` écrit, dont
le front dérive ses types (#19) — frais, typé strictement, et conforme au corps réel de la réponse
(brief de #10, décisions 10 et 11)."""

import json
from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client
from jsonschema import Draft202012Validator
from test_api import PROJECTS, listed, project_with_variant

# Le fichier versionné, que `make openapi` écrit.
OPENAPI = Path(__file__).resolve().parents[1] / "openapi.json"

# Des formes lâches, une par règle de `loose_nodes`, construites ici : chacune doit être relevée.
# Ce que la génération de types TypeScript ne saurait traduire qu'en `unknown` ou en
# `Record<string, unknown>`.
LOOSE_FORMS: dict[str, dict[str, Any]] = {
    "propriété sans type": {"title": "Extra"},
    "objet sans propriétés": {"type": "object"},
    "objet ouvert": {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "additionalProperties": True,
    },
    "tableau sans éléments": {"type": "array"},
    "tableau d'éléments sans type": {"type": "array", "items": {}},
    "alternative sans type": {"anyOf": [{"type": "string"}, {}]},
}


def versioned() -> dict[str, Any]:
    """Le schéma versionné, décodé."""
    return json.loads(OPENAPI.read_text(encoding="utf-8"))


def generated() -> dict[str, Any]:
    """Le schéma que le code produit, rendu par la commande même que `make openapi` lance, avec
    son `--api` : décodé, il se compare au fichier valeur pour valeur. Passer par la commande, et
    non par l'instance, tient aussi ce dont elle dépend — `ninja` installé, sans quoi Django ne la
    trouve pas."""
    output = StringIO()
    call_command("export_openapi_schema", "--api", "content.api.api", stdout=output)
    return json.loads(output.getvalue())


def loose_nodes(node: dict[str, Any], path: str) -> Iterator[str]:
    """Le chemin de chaque nœud de `node` qui n'est pas typé strictement (décision 11).

    Un nœud est typé par `$ref`, par `type` ou par `anyOf` dont chaque branche est typée. Un
    objet nomme ses propriétés et n'en déclare pas d'autres (`additionalProperties` absent ou
    `false`) ; un tableau type ses éléments.
    """
    if "$ref" in node:
        return
    if "anyOf" in node:
        for index, branch in enumerate(node["anyOf"]):
            yield from loose_nodes(branch, f"{path}.anyOf[{index}]")
        return
    kind = node.get("type")
    if kind is None:
        yield path
    elif kind == "object":
        if "properties" not in node or node.get("additionalProperties", False) is not False:
            yield path
        for name, nested in node.get("properties", {}).items():
            yield from loose_nodes(nested, f"{path}.{name}")
    elif kind == "array":
        if "items" not in node:
            yield path
        else:
            yield from loose_nodes(node["items"], f"{path}[]")


def test_le_schema_versionne_est_celui_du_code() -> None:
    """Un contrat changé sans `make openapi` rougit ici, donc dans `make test` et en CI : le front
    ne dérive jamais ses types d'un schéma périmé."""
    assert versioned() == generated()


@pytest.mark.parametrize("form", LOOSE_FORMS.values(), ids=LOOSE_FORMS.keys())
def test_chaque_forme_lache_est_relevee(form: dict[str, Any]) -> None:
    """Les témoins de `loose_nodes` : chaque règle relève sa forme."""
    assert list(loose_nodes(form, "témoin")) != []


def test_chaque_champ_du_contrat_est_type_strictement() -> None:
    """Aucun nœud lâche dans les schémas du contrat, condition de types TypeScript utiles (critère 6
    du corps de l'issue). Lu dans le schéma du code : le test de fraîcheur l'égale au fichier."""
    schemas = generated()["components"]["schemas"]

    assert {"ProjectOut", "TechnologyOut", "GalleryImageOut", "VariantOut", "SectionOut"} <= set(
        schemas
    )
    assert [path for name, node in schemas.items() for path in loose_nodes(node, name)] == []


@pytest.mark.django_db
def test_le_corps_reel_valide_contre_le_schema_versionne(client: Client) -> None:
    """Le corps HTTP réel valide contre le schéma de la réponse `200`, lu dans le fichier versionné
    par `jsonschema` (Draft 2020-12, celui d'OpenAPI 3.1) — indépendant de la sérialisation de
    django-ninja, qui ne prouverait que sa propre cohérence. Un corps complet : chaque liste et
    chaque type de valeur y figure, une variante comprise."""
    document = versioned()
    response = document["paths"][PROJECTS]["get"]["responses"]["200"]
    schema = {
        **response["content"]["application/json"]["schema"],
        "components": document["components"],
    }
    Draft202012Validator.check_schema(schema)
    project_with_variant("complet")

    body = listed(client)

    assert body[0]["gallery"][1]["variants"]
    # Les formats (`date`) ne sont qu'annotations sans vérificateur (Draft 2020-12, « format »).
    # jsonschema ne publie pas `py.typed` : pyright ne voit pas la signature de `validate`.
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    validator.validate(body)  # pyright: ignore[reportUnknownMemberType]
