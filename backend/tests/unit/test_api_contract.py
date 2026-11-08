import os
import subprocess
import sys
from pathlib import Path

from main import main_app


def test_profile_uses_required_vk_id_header_and_sync_uses_body() -> None:
    schema = main_app.openapi()
    paths = schema["paths"]
    profile = paths["/api/v1/users/me/profile"]
    assert "/api/v1/users/{vk_user_id}/profile" not in paths
    assert set(profile) == {"get", "patch"}
    for operation in profile.values():
        parameters = operation["parameters"]
        vk_parameter = next(p for p in parameters if p["name"] == "X-VK-User-ID")
        assert vk_parameter["in"] == "header"
        assert vk_parameter["required"] is True
        assert not any(p["name"] == "vk_user_id" for p in parameters)
        assert not any(p["in"] == "path" for p in parameters)
    assert "requestBody" not in profile["get"]
    assert profile["patch"]["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/UserProfileUpdateRequest")
    assert profile["get"]["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/UserProfileResponse")
    assert "/api/v1/users/me" not in paths
    sync = paths["/api/v1/users/sync"]["post"]
    assert sync["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/UserSyncRequest")
    assert not any(
        p["name"] in {"vk_user_id", "X-VK-User-ID"} for p in sync.get("parameters", [])
    )
    assert sync["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/UserProfileResponse")
    assert "/api/v1/auth/login" not in paths
    assert "/api/v1/auth/refresh_access_token" not in paths
    assert (
        "vk_user_id" in schema["components"]["schemas"]["UserSyncRequest"]["required"]
    )


def test_openapi_id_types_preserve_input_and_describe_numeric_output(
    resolve_openapi_schema,
) -> None:
    schema = main_app.openapi()
    response_properties = schema["components"]["schemas"]["UserProfileResponse"][
        "properties"
    ]
    response_id = resolve_openapi_schema(schema, response_properties["id"])
    response_vk_id = resolve_openapi_schema(schema, response_properties["vk_user_id"])
    assert response_id["type"] == "integer"
    assert response_vk_id["type"] == "integer"
    sync_id = schema["components"]["schemas"]["UserSyncRequest"]["properties"][
        "vk_user_id"
    ]
    sync_id = resolve_openapi_schema(schema, sync_id)
    assert sync_id["type"] == "integer"
    profile_id = next(
        p
        for p in schema["paths"]["/api/v1/users/me/profile"]["get"]["parameters"]
        if p["name"] == "X-VK-User-ID"
    )
    assert profile_id["in"] == "header"
    profile_id_schema = resolve_openapi_schema(schema, profile_id["schema"])
    assert profile_id_schema["type"] == "integer"
    deck_parameters = schema["paths"]["/api/v1/decks/{deck_id}"]["get"]["parameters"]
    deck_id = next(
        parameter for parameter in deck_parameters if parameter["name"] == "deck_id"
    )
    deck_id_schema = resolve_openapi_schema(schema, deck_id["schema"])
    assert deck_id_schema["type"] == "integer"
    for definition in (
        response_id,
        response_vk_id,
        sync_id,
        profile_id_schema,
        deck_id_schema,
    ):
        assert float(definition["maximum"]) == float(2**63 - 1)
        assert definition["exclusiveMinimum"] == 0
    assert profile_id_schema["maximum"] == 2**63 - 1


def test_openapi_describes_paginated_lists_without_page_metadata() -> None:
    schema = main_app.openapi()
    for path, response_name, item_name in (
        ("/api/v1/decks", "DeckCatalogResponse", "DeckResponse"),
        ("/api/v1/library/decks", "LibraryListResponse", "DeckResponse"),
        ("/api/v1/decks/{deck_id}/cards", "CardListResponse", "CardResponse"),
    ):
        operation = schema["paths"][path]["get"]
        parameters = {p["name"]: p for p in operation["parameters"]}
        for name, default, maximum in (("page", 1, 2**31 - 1), ("limit", 20, 100)):
            parameter = parameters[name]
            assert parameter["in"] == "query"
            assert parameter["required"] is False
            assert parameter["schema"]["type"] == "integer"
            assert parameter["schema"]["minimum"] == 1
            assert parameter["schema"]["maximum"] == maximum
            assert parameter["schema"]["default"] == default
        response = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert response["$ref"] == f"#/components/schemas/{response_name}"
        model = schema["components"]["schemas"][response_name]
        assert set(model["required"]) == {"items", "total"}
        assert set(model["properties"]) == {"items", "total"}
        assert model["properties"]["items"]["items"]["$ref"] == (
            f"#/components/schemas/{item_name}"
        )
    preview = schema["paths"]["/api/v1/decks/share/{share_code}"]["get"]
    assert (
        preview["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/DeckSharePreviewResponse"
    )


def test_openapi_requires_one_vk_header_on_all_routes_except_sync() -> None:
    paths = main_app.openapi()["paths"]
    for path, operations in paths.items():
        for operation in operations.values():
            parameters = operation.get("parameters", [])
            assert not any(p["name"] == "vk_user_id" for p in parameters)
            vk_headers = [p for p in parameters if p["name"] == "X-VK-User-ID"]
            if path == "/api/v1/users/sync":
                assert vk_headers == []
            else:
                assert len(vk_headers) == 1
                assert vk_headers[0]["in"] == "header"
                assert vk_headers[0]["required"] is True


def test_openapi_describes_only_the_app_key() -> None:
    schema = main_app.openapi()
    for path in schema["paths"].values():
        for operation in path.values():
            assert operation["security"] == [{"AppKey": []}]
    schemes = schema["components"]["securitySchemes"]
    assert set(schemes) == {"AppKey"}
    assert {value["name"] for value in schemes.values()} == {"X-App-Key"}
    assert all(value["in"] == "header" for value in schemes.values())
    assert all(value["type"] == "apiKey" for value in schemes.values())


def test_configured_path_segments_are_used_by_all_related_routes() -> None:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
            "APP_CONFIG__API__PREFIX": "/custom-api",
            "APP_CONFIG__API__V1__PREFIX": "/v2",
            "APP_CONFIG__API__V1__USERS": "/people",
            "APP_CONFIG__API__V1__SYNC": "/synchronize",
            "APP_CONFIG__API__V1__ME": "/current",
            "APP_CONFIG__API__V1__PROFILE": "/details",
            "APP_CONFIG__API__V1__SETTINGS": "/preferences",
            "APP_CONFIG__API__V1__LIBRARY": "/shelf",
            "APP_CONFIG__API__V1__DECKS": "/collections",
            "APP_CONFIG__API__V1__CARDS": "/items",
            "APP_CONFIG__API__V1__SHARE": "/shared",
        }
    )
    script = """
from main import main_app

paths = main_app.openapi()["paths"]
prefix = "/custom-api/v2"
assert set(paths[prefix + "/people/current/details"]) == {"get", "patch"}
assert set(paths[prefix + "/people/current/preferences"]) == {"put"}
assert set(paths[prefix + "/people/synchronize"]) == {"post"}
assert set(paths[prefix + "/shelf/collections"]) == {"get"}
assert set(paths[prefix + "/shelf/collections/{deck_id}"]) == {"put", "delete"}
assert set(paths[prefix + "/shelf/collections/shared/{share_code}"]) == {"put"}
assert set(paths[prefix + "/collections/shared/{share_code}"]) == {"get"}
assert set(paths[prefix + "/collections"]) == {"get", "post"}
assert set(paths[prefix + "/collections/{deck_id}"]) == {"get", "patch", "delete"}
assert set(paths[prefix + "/collections/{deck_id}/items"]) == {"get", "post"}
card_path = prefix + "/collections/{deck_id}/items/{card_id}"
assert set(paths[card_path]) == {"patch", "delete"}
assert "/api/v1/users/me/profile" not in paths
assert "/api/v1/users/me/decks" not in paths
assert "/api/v1/library/decks" not in paths
assert prefix + "/people/current/collections" not in paths
assert "/api/v1/decks/{deck_id}/cards" not in paths
"""
    subprocess.run([sys.executable, "-c", script], env=env, check=True)
