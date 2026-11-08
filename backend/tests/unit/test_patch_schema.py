from typing import ClassVar

import pytest
from pydantic import ValidationError

from api.v1.flashcards.cards.contracts.requests import CardUpdateRequest
from api.v1.flashcards.decks.contracts.requests import DeckUpdateRequest
from api.v1.users.contracts.requests import (
    UserProfileUpdateRequest,
    UserSettingsReplaceRequest,
)
from application.accounts.users.contracts.inputs import UserProfileUpdateInput
from application.flashcards.cards.contracts.inputs import CardUpdateInput
from application.flashcards.decks.contracts.inputs import DeckUpdateInput
from application.flashcards.library.contracts.inputs import UserDeckUpdateInput
from common.schemas.patch import PatchSchema


class ExamplePatch(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"note"})

    title: str | None = None
    note: str | None = None
    count: int | None = None
    enabled: bool | None = None


def test_patch_distinguishes_omitted_fields_from_explicit_null() -> None:
    patch = ExamplePatch(note=None, enabled=False, count=0)
    assert patch.model_fields_set == {"note", "enabled", "count"}
    assert patch.model_dump(exclude_unset=True) == {
        "note": None,
        "enabled": False,
        "count": 0,
    }
    assert "nullable_fields" not in ExamplePatch.model_fields
    assert "nullable_fields" not in ExamplePatch.model_json_schema()["properties"]


def test_patch_rejects_empty_unknown_and_nonnullable_fields() -> None:
    with pytest.raises(ValidationError, match="At least one field"):
        ExamplePatch.model_validate({})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExamplePatch.model_validate({"other": 1})
    with pytest.raises(ValidationError, match="Fields cannot be null: count, title"):
        ExamplePatch.model_validate({"title": None, "note": None, "count": None})


@pytest.mark.parametrize(
    ("schema", "allowed", "forbidden"),
    [
        (UserProfileUpdateRequest, {"avatar_url": None}, {"timezone": None}),
        (UserProfileUpdateInput, {"avatar_url": None}, {"timezone": None}),
        (DeckUpdateRequest, {"description": None, "grade": None}, {"title": None}),
        (DeckUpdateInput, {"description": None, "grade": None}, {"title": None}),
        (CardUpdateRequest, {"hint": None, "image_url": None}, {"front": None}),
        (CardUpdateInput, {"hint": None, "image_url": None}, {"front": None}),
        (UserDeckUpdateInput, {"is_favorite": False}, {"is_favorite": None}),
    ],
)
def test_application_and_api_updates_share_patch_rules(
    schema, allowed, forbidden
) -> None:
    assert issubclass(schema, PatchSchema)
    assert schema.model_validate(allowed).model_dump(exclude_unset=True) == allowed
    with pytest.raises(ValidationError, match="cannot be null"):
        schema.model_validate(forbidden)
    with pytest.raises(ValidationError, match="At least one field"):
        schema.model_validate({})


def test_settings_replacement_remains_independent_of_patch_rules() -> None:
    assert not issubclass(UserSettingsReplaceRequest, PatchSchema)
    assert UserSettingsReplaceRequest.model_validate({}).root == {}
    assert UserSettingsReplaceRequest.model_validate({"timezone": None}).root == {
        "timezone": None
    }
