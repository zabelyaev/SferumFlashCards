from datetime import UTC, datetime

import pytest

from application.accounts.users.contracts.mappers import to_user_profile_output
from application.accounts.users.database.models import User
from application.flashcards.cards.contracts.mappers import (
    to_card_list_output,
    to_card_output,
)
from application.flashcards.cards.database.models import Card
from application.flashcards.decks.contracts.mappers import (
    to_deck_catalog_output,
    to_deck_output,
    to_deck_share_preview_output,
)
from application.flashcards.decks.database.models import Deck
from application.flashcards.library.contracts.mappers import (
    to_library_list_output,
    to_user_deck_output,
)
from application.flashcards.library.database.models import UserDeck
from application.shared.enums import ExamType, Subject

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def make_card(card_id: int) -> Card:
    return Card(
        id=card_id,
        deck_id=17,
        front="Лицевая сторона",
        back="Оборотная сторона",
        hint=None,
        explanation="Пояснение",
        image_url=None,
        order_index=4,
        created_at=NOW,
        updated_at=NOW,
    )


def make_deck(deck_id: int) -> Deck:
    return Deck(
        id=deck_id,
        author_id=None,
        title="Физика",
        description=None,
        subject=Subject.PHYSICS,
        grade=9,
        exam_type=ExamType.OGE,
        cover_color=None,
        is_public=True,
        is_official=False,
        share_code="testcode",
        cards_count=23,
        created_at=NOW,
        updated_at=NOW,
    )


def test_user_mapper_preserves_profile_and_copies_json_settings(profile) -> None:
    values = profile.model_dump()
    values.update(
        id=9007199254740993,
        settings={"theme": "dark", "nested": [1, None, {"enabled": True}]},
    )
    user = User(**values)
    result = to_user_profile_output(user)
    assert result.model_dump() == values
    user.settings["nested"].append("changed")
    assert result.settings["nested"] == [1, None, {"enabled": True}]


def test_card_mapper_preserves_fields_without_loading_relationships() -> None:
    result = to_card_output(make_card(9007199254740993))
    assert result.model_dump() == {
        "id": 9007199254740993,
        "deck_id": 17,
        "front": "Лицевая сторона",
        "back": "Оборотная сторона",
        "hint": None,
        "explanation": "Пояснение",
        "image_url": None,
        "order_index": 4,
        "created_at": NOW,
        "updated_at": NOW,
    }


@pytest.mark.parametrize("ids", [(), (19, 3)])
def test_card_list_mapper_preserves_page_order_and_total(ids) -> None:
    result = to_card_list_output(tuple(make_card(card_id) for card_id in ids), 42)
    assert [card.id for card in result.items] == list(ids)
    assert result.total == 42


def test_deck_mapper_preserves_nullable_author_enums_and_stored_count() -> None:
    result = to_deck_output(make_deck(9007199254740993))
    assert result.model_dump() == {
        "id": 9007199254740993,
        "author_id": None,
        "title": "Физика",
        "description": None,
        "subject": Subject.PHYSICS,
        "grade": 9,
        "exam_type": ExamType.OGE,
        "cover_color": None,
        "is_public": True,
        "is_official": False,
        "share_code": "testcode",
        "cards_count": 23,
        "created_at": NOW,
        "updated_at": NOW,
    }


@pytest.mark.parametrize("mapper", [to_deck_catalog_output, to_library_list_output])
@pytest.mark.parametrize("ids", [(), (19, 3)])
def test_deck_page_mappers_preserve_page_order_and_total(mapper, ids) -> None:
    result = mapper(tuple(make_deck(deck_id) for deck_id in ids), 42)
    assert [deck.id for deck in result.items] == list(ids)
    assert result.total == 42


@pytest.mark.parametrize("ids", [(), (19, 3)])
def test_share_preview_maps_cards_without_recalculating_deck_count(ids) -> None:
    deck = make_deck(17)
    cards = tuple(make_card(card_id) for card_id in ids)
    result = to_deck_share_preview_output(deck, cards)
    assert result.deck == to_deck_output(deck)
    assert result.cards == [to_card_output(card) for card in cards]
    assert result.deck.cards_count == 23


def test_membership_mapper_preserves_fields_without_loading_relationships() -> None:
    values = {
        "id": 9007199254740993,
        "user_id": 7,
        "deck_id": 17,
        "is_favorite": True,
        "created_at": NOW,
    }
    result = to_user_deck_output(UserDeck(**values))
    assert result.model_dump() == values
