import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.types import UserRole
from api.v1.users.contracts.mappers import (
    ROLE_TO_RESPONSE,
    to_user_profile_response,
    to_user_profile_update_input,
)
from api.v1.users.contracts.requests import (
    UserProfileUpdateRequest,
    UserSettingsReplaceRequest,
    UserSyncRequest,
)
from api.v1.users.contracts.responses import UserProfileResponse
from application.accounts.users.contracts.inputs import (
    UserProfileUpdateInput,
    UserSettingsReplaceInput,
    UserSyncInput,
)
from application.accounts.users.contracts.outputs import UserProfileOutput
from application.shared.enums import UserRole as ApplicationUserRole


def test_transport_update_rejects_empty_and_nonnullable_null_patches() -> None:
    with pytest.raises(ValidationError, match="At least one field"):
        UserProfileUpdateRequest()
    with pytest.raises(ValidationError, match="cannot be null"):
        UserProfileUpdateRequest(first_name=None)


def test_profile_patch_can_clear_avatar_without_changing_omitted_fields() -> None:
    model = UserProfileUpdateRequest(avatar_url=None)
    assert model.model_dump(exclude_unset=True) == {"avatar_url": None}


def test_response_preserves_profile_and_serializes_bigint_ids(profile) -> None:
    profile = profile.model_copy(update={"id": 9007199254740993})
    response = to_user_profile_response(profile)
    assert response.id == 9007199254740993
    assert response.model_dump(mode="json")["id"] == 9007199254740993
    assert response.model_dump(mode="json")["vk_user_id"] == 12345678
    assert "password" not in response.model_dump()


def test_api_schemas_do_not_inherit_application_inputs_or_outputs() -> None:
    assert not issubclass(UserProfileResponse, UserProfileOutput)
    assert not issubclass(UserProfileUpdateRequest, UserProfileUpdateInput)
    assert not issubclass(UserSyncRequest, UserSyncInput)
    assert not issubclass(UserSettingsReplaceRequest, UserSettingsReplaceInput)
    assert UserRole is not ApplicationUserRole


def test_api_schema_modules_do_not_import_application() -> None:
    api_path = Path(__file__).resolve().parents[2] / "src" / "api"
    paths = [
        *api_path.rglob("types.py"),
        *api_path.rglob("contracts/requests.py"),
        *api_path.rglob("contracts/responses.py"),
    ]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("application"), path
            elif isinstance(node, ast.Import):
                assert not any(
                    alias.name.startswith("application") for alias in node.names
                ), path


@pytest.mark.parametrize(
    "payload",
    [
        {"first_name": "  Анна  "},
        {"last_name": "  Иванова  "},
        {"avatar_url": None},
        {"avatar_url": "https://example.com/avatar.jpg"},
        {"timezone": "Europe/Moscow"},
        {"daily_new_cards_limit": 1},
        {"daily_total_cards_limit": 1000},
        {"daily_new_cards_limit": 30, "timezone": "Europe/Moscow"},
        {"first_name": "Анна", "avatar_url": None},
    ],
)
def test_update_mapper_preserves_only_explicit_fields(payload) -> None:
    request = UserProfileUpdateRequest.model_validate(payload)
    application_input = to_user_profile_update_input(request)
    assert type(application_input) is UserProfileUpdateInput
    assert application_input.model_fields_set == request.model_fields_set
    assert application_input.model_dump(exclude_unset=True) == request.model_dump(
        exclude_unset=True
    )


@pytest.mark.parametrize("role", ["student", "teacher", "admin"])
@pytest.mark.parametrize("settings", [{}, {"theme": "custom", "nested": [1, None]}])
def test_response_mapper_preserves_entire_public_profile(
    profile, role, settings
) -> None:
    source = profile.model_copy(
        update={
            "role": ApplicationUserRole(role),
            "settings": settings,
            "daily_new_cards_limit": 5,
            "streak_days": 3,
            "max_streak_days": 8,
        }
    )
    response = to_user_profile_response(source)
    assert type(response) is UserProfileResponse
    assert type(response.settings) is dict
    assert type(response.role) is UserRole
    assert response.model_dump(mode="json") == source.model_dump(mode="json")


def test_role_mapping_covers_every_application_role() -> None:
    assert set(ROLE_TO_RESPONSE) == set(ApplicationUserRole)
    assert ROLE_TO_RESPONSE[ApplicationUserRole.STUDENT] is UserRole.STUDENT
    assert ROLE_TO_RESPONSE[ApplicationUserRole.TEACHER] is UserRole.TEACHER
    assert ROLE_TO_RESPONSE[ApplicationUserRole.ADMIN] is UserRole.ADMIN


def test_response_uses_role_mapping_not_internal_string_value(
    profile, monkeypatch
) -> None:
    monkeypatch.setitem(ROLE_TO_RESPONSE, ApplicationUserRole.TEACHER, UserRole.STUDENT)
    source = profile.model_copy(update={"role": ApplicationUserRole.TEACHER})
    response = to_user_profile_response(source)
    assert response.role is UserRole.STUDENT


def test_new_application_fields_do_not_leak_into_response(profile) -> None:
    class InternalProfile(UserProfileOutput):
        internal_note: str = "private-note"

    payload = profile.model_dump()
    payload["settings"] = {"internal_preference": "frontend-value"}
    source = InternalProfile.model_validate(payload)
    response = to_user_profile_response(source).model_dump(mode="json")
    assert "internal_note" not in response
    assert response["settings"] == {"internal_preference": "frontend-value"}
    assert "private-note" not in str(response)


@pytest.mark.parametrize(
    "payload",
    [
        {"first_name": "x" * 101},
        {"last_name": "x" * 101},
        {"timezone": "Unknown/Zone"},
        {"avatar_url": "not-a-url"},
        {"first_name": None},
        {"last_name": None},
        {"timezone": None},
        {"daily_new_cards_limit": None},
        {"daily_total_cards_limit": 19},
        {"daily_new_cards_limit": 251},
        {"daily_new_cards_limit": True},
        {"daily_new_cards_limit": "20"},
    ],
)
def test_api_update_validation_is_enforced_independently(payload) -> None:
    with pytest.raises(ValidationError):
        UserProfileUpdateRequest.model_validate(payload)
