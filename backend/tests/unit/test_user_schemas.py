import pytest
from pydantic import ValidationError

from application.accounts.users.contracts.inputs import (
    UserProfileUpdateInput,
    UserSyncInput,
)


def test_profile_update_requires_fields_and_rejects_unknown_or_null_fields() -> None:
    for payload in ({}, {"first_name": None}, {"vk_user_id": 1}, {"role": "admin"}):
        with pytest.raises(ValidationError):
            UserProfileUpdateInput.model_validate(payload)


def test_profile_names_are_normalized_and_limited() -> None:
    profile = UserSyncInput(vk_user_id=1, first_name="  Иван  ")
    assert profile.first_name == "Иван"
    with pytest.raises(ValidationError):
        UserSyncInput(vk_user_id=1, first_name="x" * 101)


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("name", ["A\x00B", "A\ud800B"])
def test_application_profile_names_reject_invalid_database_text(field, name) -> None:
    with pytest.raises(ValidationError):
        UserSyncInput.model_validate({"vk_user_id": 1, field: name})
    with pytest.raises(ValidationError):
        UserProfileUpdateInput.model_validate({field: name})


def test_profile_update_can_clear_avatar() -> None:
    assert UserProfileUpdateInput(avatar_url=None).model_dump(exclude_unset=True) == {
        "avatar_url": None
    }


@pytest.mark.parametrize("limit", [None, 0, 251, True, 5.5, "20"])
def test_profile_update_rejects_invalid_daily_cards_limit(limit) -> None:
    with pytest.raises(ValidationError):
        UserProfileUpdateInput.model_validate({"daily_new_cards_limit": limit})


@pytest.mark.parametrize("limit", [1, 12, 250])
def test_profile_update_accepts_valid_daily_cards_limit(limit: int) -> None:
    update = UserProfileUpdateInput(daily_new_cards_limit=limit)
    assert update.model_dump(exclude_unset=True) == {"daily_new_cards_limit": limit}
