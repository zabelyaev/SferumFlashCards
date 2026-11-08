from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from api.v1.flashcards.decks.contracts.mappers import (
    to_deck_input,
    to_deck_response,
    to_deck_update_input,
)
from api.v1.flashcards.decks.contracts.requests import (
    DeckCreateRequest,
    DeckUpdateRequest,
)
from application.flashcards.decks.contracts.inputs import (
    DeckCreateInput,
    DeckUpdateInput,
)
from application.flashcards.decks.contracts.outputs import DeckOutput
from application.shared.enums import Subject
from main import create_app


@pytest.mark.parametrize(
    "optional_fields",
    [
        {},
        {"subject": None},
        {"cover_color": None},
        {"subject": None, "cover_color": None},
    ],
)
def test_deck_creation_defaults_optional_fields_to_null(optional_fields) -> None:
    request = DeckCreateRequest.model_validate({"title": "Тема", **optional_fields})
    model = to_deck_input(request)
    assert request.subject is None and request.cover_color is None
    assert model.subject is None and model.cover_color is None
    assert DeckCreateInput(title="Тема").subject is None
    assert DeckCreateInput(title="Тема").cover_color is None


def test_deck_creation_preserves_explicit_subject_and_cover_color() -> None:
    request = DeckCreateRequest(
        title="Тема", subject="physics", cover_color="  gradient-blue  "
    )
    model = to_deck_input(request)
    assert model.subject is Subject.PHYSICS
    assert model.cover_color == "gradient-blue"


@pytest.mark.parametrize(
    "fields",
    [{"subject": None}, {"cover_color": None}, {"subject": None, "cover_color": None}],
)
def test_patch_explicit_null_clears_optional_fields(fields) -> None:
    request = DeckUpdateRequest.model_validate(fields)
    model = to_deck_update_input(request)
    assert request.model_dump(exclude_unset=True) == fields
    assert model.model_dump(exclude_unset=True) == fields
    assert (
        DeckUpdateInput.model_validate(fields).model_dump(exclude_unset=True) == fields
    )


def test_patch_omitted_optional_fields_are_not_updated() -> None:
    request = DeckUpdateRequest(title="Другое название")
    model = to_deck_update_input(request)
    assert request.model_fields_set == model.model_fields_set == {"title"}
    assert model.model_dump(exclude_unset=True) == {"title": "Другое название"}


@pytest.mark.parametrize(
    ("schema", "fields"),
    [
        (DeckCreateRequest, {"subject": "not-a-subject"}),
        (DeckCreateRequest, {"cover_color": "  "}),
        (DeckCreateRequest, {"cover_color": "x" * 33}),
        (DeckCreateInput, {"subject": "not-a-subject"}),
        (DeckCreateInput, {"cover_color": "  "}),
        (DeckUpdateRequest, {"subject": "not-a-subject"}),
        (DeckUpdateRequest, {"cover_color": "  "}),
        (DeckUpdateRequest, {"title": None}),
        (DeckUpdateRequest, {"is_public": None}),
        (DeckUpdateInput, {"subject": "not-a-subject"}),
        (DeckUpdateInput, {"cover_color": "  "}),
        (DeckUpdateInput, {"title": None}),
    ],
)
def test_optional_fields_still_validate_non_null_values(schema, fields) -> None:
    payload = {"title": "Тема", **fields} if "Create" in schema.__name__ else fields
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_deck_response_mapper_handles_missing_subject_and_cover_color() -> None:
    timestamp = datetime(2026, 10, 23, tzinfo=UTC)
    model = DeckOutput(
        id=1,
        author_id=2,
        title="Тема",
        description=None,
        subject=None,
        grade=None,
        exam_type=None,
        cover_color=None,
        is_public=True,
        is_official=False,
        share_code="Abcd1234",
        cards_count=0,
        created_at=timestamp,
        updated_at=timestamp,
    )
    response = to_deck_response(model)
    assert response.model_dump(mode="json")["subject"] is None
    assert response.model_dump(mode="json")["cover_color"] is None


def test_openapi_describes_optional_and_nullable_deck_fields() -> None:
    schemas = create_app().openapi()["components"]["schemas"]
    create = schemas["DeckCreateRequest"]
    assert "subject" not in create.get("required", [])
    assert "cover_color" not in create.get("required", [])
    for name in ("DeckCreateRequest", "DeckUpdateRequest", "DeckResponse"):
        properties = schemas[name]["properties"]
        for field in ("subject", "cover_color"):
            assert any(
                choice.get("type") == "null" for choice in properties[field]["anyOf"]
            )
