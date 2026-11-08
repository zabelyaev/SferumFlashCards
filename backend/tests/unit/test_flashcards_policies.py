from unittest.mock import AsyncMock

import pytest

from application.flashcards.database.uow import LibraryRepository
from application.flashcards.decks.database.models import Deck
from application.flashcards.shared.access import require_readable_deck
from application.flashcards.shared.policies import (
    can_read_deck,
    require_author,
    require_can_add_to_library,
)
from common.exceptions.forbidden import ForbiddenError


@pytest.mark.parametrize(
    ("author_id", "is_public", "is_member", "readable", "addable", "author"),
    [
        (1, False, False, True, True, True),
        (1, True, False, True, True, True),
        (2, True, False, True, True, False),
        (2, False, True, True, True, False),
        (2, False, False, False, False, False),
        (None, False, False, False, False, False),
        (None, True, False, True, True, False),
    ],
)
def test_policies_distinguish_read_add_and_author(
    author_id, is_public, is_member, readable, addable, author
) -> None:
    deck = Deck(author_id=author_id, is_public=is_public)
    assert can_read_deck(deck, 1, is_member=is_member) is readable
    if addable:
        require_can_add_to_library(deck, 1, is_member=is_member)
    else:
        with pytest.raises(ForbiddenError):
            require_can_add_to_library(deck, 1, is_member=is_member)
    if author:
        require_author(deck, 1)
    else:
        with pytest.raises(ForbiddenError):
            require_author(deck, 1)


@pytest.mark.parametrize(
    ("author_id", "is_public", "membership", "expected_queries", "readable"),
    [
        (1, False, None, 0, True),
        (2, True, None, 0, True),
        (2, False, object(), 1, True),
        (2, False, None, 1, False),
    ],
)
async def test_readable_deck_only_queries_membership_when_needed(
    author_id, is_public, membership, expected_queries, readable
) -> None:
    deck = Deck(id=7, author_id=author_id, is_public=is_public)
    library = AsyncMock(spec=LibraryRepository)
    library.find_membership.return_value = membership
    if readable:
        await require_readable_deck(deck, 1, library)
    else:
        with pytest.raises(ForbiddenError):
            await require_readable_deck(deck, 1, library)
    assert library.find_membership.await_count == expected_queries
    if expected_queries:
        library.find_membership.assert_awaited_once_with(1, deck.id)
