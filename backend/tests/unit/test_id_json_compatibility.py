import json

import pytest
from pydantic import ValidationError

from application.study.contracts.outputs import ReviewLogOutput, StudySessionCardOutput


@pytest.mark.parametrize("legacy", [True, False])
def test_session_snapshot_reads_old_and_new_json_ids(legacy: bool) -> None:
    card_id = 9007199254740993
    deck_id = 9223372036854775807
    payload = {
        "id": 10,
        "session_id": 11,
        "card_id": card_id,
        "source_card_id": None,
        "snapshot": {
            "id": str(card_id) if legacy else card_id,
            "deck_id": str(deck_id) if legacy else deck_id,
            "front": "123",
            "back": "456",
            "hint": None,
            "explanation": None,
            "image_url": None,
            "order_index": 0,
            "created_at": "2026-10-23T00:00:00Z",
            "updated_at": "2026-10-23T00:00:00Z",
        },
        "order_index": 0,
        "fsrs_state": {"state": 1},
        "cycle_id": None,
        "was_new": True,
        "attempts_count": 0,
        "completed_at": None,
    }
    serialized = json.loads(
        StudySessionCardOutput.model_validate(payload).model_dump_json()
    )
    assert serialized["snapshot"]["id"] == card_id
    assert serialized["snapshot"]["deck_id"] == deck_id
    assert serialized["snapshot"]["front"] == "123"
    assert serialized["source_card_id"] is None
    assert payload["snapshot"]["id"] == (str(card_id) if legacy else card_id)
    assert payload["snapshot"]["deck_id"] == (str(deck_id) if legacy else deck_id)


@pytest.mark.parametrize("legacy", [True, False])
def test_review_history_reads_old_and_new_json_ids(legacy: bool) -> None:
    def stored_id(value: int) -> int | str:
        return str(value) if legacy else value

    result = {
        "session": {
            "id": stored_id(9007199254740993),
            "deck_id": stored_id(4),
            "study_date": "2026-10-23",
            "status": "active",
            "limits": {"daily_total_cards_limit": 125, "daily_new_cards_limit": 12},
            "progress": {"total_cards": 1, "completed_cards": 0, "remaining_cards": 1},
            "started_at": "2026-10-23T00:00:00Z",
            "last_activity_at": "2026-10-23T00:00:00Z",
            "expires_at": "2026-10-24T00:00:00Z",
            "finished_at": None,
            "finish_reason": None,
        },
        "current_card_id": stored_id(3),
        "answer_token": "next",
        "quota": {
            "total_used": 1,
            "new_used": 1,
            "total_remaining": 124,
            "new_remaining": 11,
        },
        "streak": {"streak_days": 0, "max_streak_days": 0, "last_streak_date": None},
    }
    payload = {
        "id": 6,
        "user_id": 2,
        "card_id": 3,
        "deck_id": 4,
        "session_id": 5,
        "cycle_id": 7,
        "study_date": "2026-10-23",
        "answer_token": "123",
        "rating": 3,
        "was_new": True,
        "result": result,
        "reviewed_at": "2026-10-23T00:00:00Z",
    }
    serialized = json.loads(ReviewLogOutput.model_validate(payload).model_dump_json())
    for part in (serialized["result"]["session"],):
        for name, value in part.items():
            if name == "id" or name.endswith("_id"):
                assert type(value) is int
    assert serialized["result"]["session"]["id"] == 9007199254740993
    assert serialized["answer_token"] == "123"
    assert payload["result"]["session"]["id"] == stored_id(9007199254740993)


@pytest.mark.parametrize(
    "value", ["0", "-1", "1.5", "abc", "9223372036854775808", 0, False, 1.5]
)
def test_snapshot_rejects_invalid_legacy_ids(value: object) -> None:
    payload = {
        "id": 10,
        "session_id": 11,
        "card_id": 12,
        "source_card_id": None,
        "snapshot": {
            "id": value,
            "deck_id": 13,
            "front": "question",
            "back": "answer",
            "hint": None,
            "explanation": None,
            "image_url": None,
            "order_index": 0,
            "created_at": "2026-10-23T00:00:00Z",
            "updated_at": "2026-10-23T00:00:00Z",
        },
        "order_index": 0,
        "fsrs_state": {"state": 1},
        "cycle_id": None,
        "was_new": True,
        "attempts_count": 0,
        "completed_at": None,
    }
    with pytest.raises(ValidationError) as error:
        StudySessionCardOutput.model_validate(payload)
    assert any(item["loc"] == ("snapshot", "id") for item in error.value.errors())
