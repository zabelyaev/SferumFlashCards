import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter, ValidationError

from application.accounts.users.contracts.inputs import (
    UserProfileUpdateInput,
    UserSettingsReplaceInput,
    UserSyncInput,
)
from application.flashcards.cards.contracts.inputs import (
    CardCreateInput,
    CardUpdateInput,
)
from application.flashcards.decks.contracts.inputs import (
    DeckCreateInput,
    DeckUpdateInput,
)
from application.flashcards.library.contracts.inputs import UserDeckCreateInput
from application.shared.contracts.types import BIGINT_MAX, BigIntId
from application.study.contracts.inputs import (
    ReviewCreateInput,
    StudySessionCreateInput,
)
from application.study.contracts.outputs import CardReviewOutput

if TYPE_CHECKING:
    from pydantic import BaseModel


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        BIGINT_MAX + 1,
        False,
        1.5,
        "0",
        "-1",
        "1e3",
        "１２３",
        str(BIGINT_MAX + 1),
        "9" * 100,
    ],
)
def test_ids_reject_values_outside_signed_bigint(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(BigIntId).validate_python(value)


def test_ids_accept_the_full_positive_bigint_range() -> None:
    assert TypeAdapter(BigIntId).validate_python(BIGINT_MAX) == BIGINT_MAX


def test_bigint_ids_round_trip_as_numbers_in_json() -> None:
    adapter = TypeAdapter(BigIntId)
    assert adapter.validate_python(str(BIGINT_MAX)) == BIGINT_MAX
    encoded = adapter.dump_json(BIGINT_MAX)
    assert json.loads(encoded) == BIGINT_MAX
    assert adapter.validate_json(encoded) == BIGINT_MAX
    assert adapter.json_schema(mode="serialization")["type"] == "integer"


def test_review_requests_accept_numeric_ids_and_keep_python_integers() -> None:
    request = ReviewCreateInput.model_validate_json(
        json.dumps(
            {
                "card_id": 9007199254740993,
                "answer_token": "review-123",
                "rating": 3,
            }
        )
    )
    assert request.card_id == 9007199254740993
    assert request.model_dump()["card_id"] == 9007199254740993
    assert request.model_dump(mode="json")["card_id"] == 9007199254740993


@pytest.mark.parametrize("field", ["card_id"])
def test_review_requests_coerce_string_ids(field: str) -> None:
    payload = {
        "card_id": 2,
        "answer_token": "review-123",
        "rating": 3,
    }
    payload[field] = "1"
    request = ReviewCreateInput.model_validate(payload)
    assert type(getattr(request, field)) is int
    assert getattr(request, field) == 1


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (UserSyncInput, {"vk_user_id": "12345678"}),
        (UserDeckCreateInput, {"deck_id": "1"}),
        (StudySessionCreateInput, {"deck_id": "1"}),
    ],
)
def test_application_inputs_coerce_string_ids(schema, payload) -> None:
    request = schema.model_validate(payload)
    field, original = next(iter(payload.items()))
    assert type(getattr(request, field)) is int
    assert getattr(request, field) == int(original)


def test_profile_accepts_vk_identity_without_legacy_credentials() -> None:
    profile = UserSyncInput(
        vk_user_id=3_000_000_000,
        first_name="  Иван  ",
        timezone="Europe/Moscow",
    )
    assert profile.first_name == "Иван"
    assert profile.timezone == "Europe/Moscow"
    assert "password" not in profile.model_dump()


@pytest.mark.parametrize("timezone", ["Mars/Olympus", "../UTC", "/etc/passwd"])
def test_profile_rejects_unknown_or_invalid_timezones(timezone: str) -> None:
    with pytest.raises(ValidationError, match="Unknown IANA timezone"):
        UserSyncInput(vk_user_id=1, first_name="Иван", timezone=timezone)


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (DeckCreateInput, {"title": "x" * 101, "subject": "physics"}),
        (DeckCreateInput, {"title": "Тема", "subject": "physics", "grade": 12}),
        (DeckCreateInput, {"title": "Тема", "subject": "physics", "is_official": True}),
        (CardCreateInput, {"front": "  ", "back": "Ответ"}),
        (UserProfileUpdateInput, {"daily_new_cards_limit": 251}),
        (UserProfileUpdateInput, {"daily_new_cards_limit": None}),
        (UserProfileUpdateInput, {"timezone": "Unknown/Zone"}),
    ],
)
def test_create_and_profile_schemas_validate_domain_limits(
    schema: type[BaseModel], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


@pytest.mark.parametrize("schema", [DeckUpdateInput, CardUpdateInput])
def test_updates_require_an_explicit_change(schema: type[BaseModel]) -> None:
    with pytest.raises(ValidationError, match="At least one field"):
        schema()


def test_empty_settings_replacement_is_allowed() -> None:
    assert UserSettingsReplaceInput().settings == {}


def test_updates_distinguish_clearing_optional_fields_from_omitting_them() -> None:
    update = CardUpdateInput(hint=None)
    assert update.model_dump(exclude_unset=True) == {"hint": None}
    assert DeckUpdateInput(grade=None).model_dump(exclude_unset=True) == {"grade": None}
    with pytest.raises(ValidationError, match="cannot be null"):
        CardUpdateInput(front=None)


def test_card_content_keeps_mixed_text_and_latex_including_invalid_formulas() -> None:
    content = r"Сила: $F=ma$. $$\frac{a}{b}$$ Ошибка: $\frac{$"
    card = CardCreateInput(front=content, back="Ответ")
    assert card.front == content


def test_exam_type_is_independent_of_school_grade() -> None:
    deck = DeckCreateInput(title="Подготовка к ЕГЭ", subject="physics", exam_type="ege")
    assert deck.grade is None
    assert deck.exam_type == "ege"


@pytest.mark.parametrize(
    "changes",
    [
        {"rating": 0},
        {"rating": 5},
        {"rating": True},
        {"duration_ms": -1},
        {"answer_token": ""},
        {"answer_token": "a\nb"},
        {"user_id": 99},
        {"due_date": "2026-10-23T00:00:00Z"},
    ],
)
def test_review_input_rejects_invalid_or_server_owned_fields(
    changes: dict[str, object],
) -> None:
    payload = {
        "card_id": 2,
        "rating": 3,
        "answer_token": "review-123",
    }
    with pytest.raises(ValidationError):
        ReviewCreateInput.model_validate(payload | changes)


def test_review_output_includes_fsrs_state() -> None:
    payload = {
        "id": 1,
        "user_id": 1,
        "card_id": 1,
        "deck_id": 1,
        "cycle_id": 1,
        "fsrs_state": {"state": 2, "stability": 2.36},
        "due_date": datetime(2026, 10, 23, tzinfo=UTC),
        "last_reviewed": datetime(2026, 10, 22, tzinfo=UTC),
    }
    assert CardReviewOutput.model_validate(payload).fsrs_state["stability"] == 2.36
