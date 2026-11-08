import pytest
from pydantic import ValidationError

from api.v1.users.contracts.mappers import to_user_sync_input
from api.v1.users.contracts.requests import UserSyncRequest
from application.accounts.users.contracts.inputs import UserSyncInput


def test_sync_requires_only_vk_id_and_keeps_optional_fields_omitted() -> None:
    model = UserSyncRequest.model_validate({"vk_user_id": 12345678})
    assert model.vk_user_id == 12345678
    assert model.model_dump(exclude_unset=True) == {"vk_user_id": 12345678}


@pytest.mark.parametrize("field", ["password", "login", "role", "is_active", "id"])
def test_sync_rejects_credentials_and_server_owned_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        UserSyncRequest.model_validate({"vk_user_id": 12345678, field: "value"})


@pytest.mark.parametrize(
    "profile",
    [
        {},
        {"first_name": "  Иван  "},
        {"last_name": "Иванов", "timezone": "Europe/Moscow"},
        {"avatar_url": None},
        {"avatar_url": "https://example.com/avatar.jpg"},
    ],
)
def test_sync_mapper_preserves_omitted_profile_fields(profile) -> None:
    request = UserSyncRequest.model_validate({"vk_user_id": 12345678, **profile})
    application_input = to_user_sync_input(request)
    assert type(application_input) is UserSyncInput
    assert application_input.model_fields_set == request.model_fields_set
    assert application_input.model_dump(exclude_unset=True) == request.model_dump(
        exclude_unset=True
    )


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        False,
        1.5,
        2**63,
        "0",
        "1.5",
        "abc",
        "9223372036854775808",
    ],
)
def test_sync_api_validates_ids_without_application_schema(value) -> None:
    with pytest.raises(ValidationError):
        UserSyncRequest.model_validate({"vk_user_id": value})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", 1),
        ("12345678", 12345678),
        ("9223372036854775807", 2**63 - 1),
        (1.0, 1),
        (True, 1),
    ],
)
def test_sync_api_uses_default_integer_coercion(value, expected) -> None:
    request = UserSyncRequest.model_validate({"vk_user_id": value})
    result = to_user_sync_input(request)
    assert type(request.vk_user_id) is int and request.vk_user_id == expected
    assert type(result.vk_user_id) is int and result.vk_user_id == expected


def test_sync_api_and_mapper_preserve_bigint_precision() -> None:
    request = UserSyncRequest.model_validate_json('{"vk_user_id": 9223372036854775807}')
    application_input = to_user_sync_input(request)
    assert application_input.vk_user_id == 2**63 - 1
    assert request.model_dump(mode="json")["vk_user_id"] == 9223372036854775807


@pytest.mark.parametrize(
    "profile",
    [
        {"first_name": "x" * 101},
        {"last_name": "x" * 101},
        {"timezone": "Unknown/Zone"},
        {"avatar_url": "not-a-url"},
        {"first_name": None},
    ],
)
def test_sync_api_validates_profile_without_application_schema(profile) -> None:
    with pytest.raises(ValidationError):
        UserSyncRequest.model_validate({"vk_user_id": 12345678, **profile})
