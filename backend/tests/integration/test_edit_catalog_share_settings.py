import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from application.accounts.users.database.models import User
from application.flashcards.cards.database.models import Card
from application.flashcards.cards.database.repository import SQLACardRepository
from application.flashcards.decks.database.models import Deck
from application.flashcards.library.database.models import UserDeck
from application.flashcards.library.database.repository import SQLALibraryRepository
from application.study.database.models import (
    CardReview,
    ReviewLog,
    StudySessionCard,
)
from common.database import DatabaseHelper
from common.middleware.json_body_limit import MAX_JSON_BODY_CHARACTERS
from main import create_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration
VK_IDS = (91900001, 91900002, 91900003)
OWNER = {"X-VK-User-ID": str(VK_IDS[0])}
MEMBER = {"X-VK-User-ID": str(VK_IDS[1])}
VISITOR = {"X-VK-User-ID": str(VK_IDS[2])}


@pytest_asyncio.fixture
async def helper(validated_test_database) -> AsyncIterator[DatabaseHelper]:
    helper = DatabaseHelper(validated_test_database)

    async def cleanup() -> None:
        async with helper.session_factory.begin() as session:
            ids = select(User.id).where(User.vk_user_id.in_(VK_IDS))
            await session.execute(delete(Deck).where(Deck.author_id.in_(ids)))
            await session.execute(delete(User).where(User.vk_user_id.in_(VK_IDS)))

    try:
        await cleanup()
        yield helper
    finally:
        await cleanup()
        await helper.dispose()


@pytest_asyncio.fixture
async def client(helper, app_headers) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.state.database_helper = helper
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=app_headers
    ) as client:
        for vk_user_id in VK_IDS:
            response = await client.post(
                "/api/v1/users/sync", json={"vk_user_id": vk_user_id}
            )
            assert response.status_code == 200, response.text
        yield client


async def create_deck(client, title: str, **kwargs) -> dict:
    response = await client.post(
        "/api/v1/decks",
        headers=OWNER,
        json={"title": title, "subject": "physics", **kwargs},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_deck_nullable_subject_and_cover_through_api_and_database(
    client, helper
) -> None:
    created = await client.post(
        "/api/v1/decks",
        headers=OWNER,
        json={"title": "nullable-marker", "is_public": True},
    )
    assert created.status_code == 201, created.text
    deck = created.json()
    deck_id = deck["id"]
    path = f"/api/v1/decks/{deck_id}"
    assert deck["subject"] is None and deck["cover_color"] is None

    explicit = await client.post(
        "/api/v1/decks",
        headers=OWNER,
        json={"title": "explicit-null", "subject": None, "cover_color": None},
    )
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["subject"] is None and explicit.json()["cover_color"] is None

    async with helper.session_factory.begin() as session:
        stored = await session.get(Deck, deck_id)
        assert stored is not None
        assert stored.subject is None and stored.cover_color is None
        author_id = await session.scalar(
            select(User.id).where(User.vk_user_id == VK_IDS[0])
        )
        orm_deck = Deck(author_id=author_id, title="ORM-default")
        session.add(orm_deck)
        await session.flush()
        assert orm_deck.subject is None and orm_deck.cover_color is None

    fetched = await client.get(path, headers=OWNER)
    assert fetched.status_code == 200
    assert fetched.json()["subject"] is None and fetched.json()["cover_color"] is None
    catalog = await client.get(
        "/api/v1/decks", headers=OWNER, params={"search": "nullable-marker"}
    )
    assert catalog.status_code == 200
    assert catalog.json()["total"] == 1
    assert catalog.json()["items"][0]["subject"] is None
    assert catalog.json()["items"][0]["cover_color"] is None
    library = await client.get(
        "/api/v1/library/decks", headers=OWNER, params={"search": "nullable-marker"}
    )
    assert library.status_code == 200
    assert library.json()["items"][0]["id"] == deck_id
    assert library.json()["items"][0]["subject"] is None
    assert library.json()["items"][0]["cover_color"] is None
    preview = await client.get(
        f"/api/v1/decks/share/{deck['share_code']}", headers=VISITOR
    )
    assert preview.status_code == 200
    assert preview.json()["deck"]["subject"] is None
    assert preview.json()["deck"]["cover_color"] is None

    filters = {"search": "nullable-marker", "subject": "physics"}
    assert (await client.get("/api/v1/decks", headers=OWNER, params=filters)).json()[
        "total"
    ] == 0
    assert (
        await client.get("/api/v1/library/decks", headers=OWNER, params=filters)
    ).json()["total"] == 0
    assert (
        await client.patch(path, headers=MEMBER, json={"subject": "physics"})
    ).status_code == 403

    updated = await client.patch(
        path, headers=OWNER, json={"subject": "physics", "cover_color": "blue"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["subject"] == "physics"
    assert updated.json()["cover_color"] == "blue"
    assert (await client.get("/api/v1/decks", headers=OWNER, params=filters)).json()[
        "total"
    ] == 1
    assert (
        await client.get("/api/v1/library/decks", headers=OWNER, params=filters)
    ).json()["total"] == 1

    renamed = await client.patch(
        path, headers=OWNER, json={"title": "nullable-marker updated"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["subject"] == "physics"
    assert renamed.json()["cover_color"] == "blue"
    subject_cleared = await client.patch(path, headers=OWNER, json={"subject": None})
    assert subject_cleared.status_code == 200
    assert subject_cleared.json()["subject"] is None
    assert subject_cleared.json()["cover_color"] == "blue"
    color_cleared = await client.patch(path, headers=OWNER, json={"cover_color": None})
    assert color_cleared.status_code == 200
    assert color_cleared.json()["subject"] is None
    assert color_cleared.json()["cover_color"] is None
    assert (await client.get("/api/v1/decks", headers=OWNER, params=filters)).json()[
        "total"
    ] == 0
    assert (
        await client.get("/api/v1/library/decks", headers=OWNER, params=filters)
    ).json()["total"] == 0
    assert (await client.patch(path, headers=OWNER, json={})).status_code == 422
    assert (
        await client.patch(path, headers=OWNER, json={"cover_color": " "})
    ).status_code == 422
    async with helper.session_factory() as session:
        stored = await session.get(Deck, deck_id)
        assert stored is not None
        assert stored.subject is None and stored.cover_color is None


async def test_private_deck_preserves_members_and_shares_by_code(
    client, helper
) -> None:
    deck = await create_deck(client, "Public before update", is_public=True, grade=9)
    deck_id = deck["id"]
    code = deck["share_code"]
    path = f"/api/v1/decks/{deck_id}"
    member_path = f"/api/v1/library/decks/{deck_id}"
    card = await client.post(
        path + "/cards", headers=OWNER, json={"front": "Question", "back": "Answer"}
    )
    assert card.status_code == 201
    card_id = card.json()["id"]
    membership = await client.put(member_path, headers=MEMBER)
    assert membership.status_code == 200

    started = await client.post(
        "/api/v1/study/sessions", headers=MEMBER, json={"deck_id": deck_id}
    )
    state = started.json()
    result = await client.post(
        f"/api/v1/study/sessions/{state['session']['id']}/reviews",
        headers=MEMBER,
        json={"card_id": card_id, "rating": 3, "answer_token": state["answer_token"]},
    )
    assert result.status_code == 200, result.text
    async with helper.session_factory() as session:
        review = await session.scalar(
            select(CardReview).where(CardReview.card_id == card_id)
        )
        review_id, original_state = review.id, review.fsrs_state

    assert (
        await client.patch(path, headers=MEMBER, json={"title": "not authorized"})
    ).status_code == 403
    result = await client.patch(
        path,
        headers=OWNER,
        json={
            "title": "Private after update",
            "description": None,
            "is_public": False,
            "subject": "algebra",
            "exam_type": "ege",
            "cover_color": "gradient-green",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["share_code"] == code
    assert result.json()["grade"] == 9 and result.json()["cards_count"] == 1
    assert result.json()["description"] is None and result.json()["is_public"] is False
    assert result.json()["subject"] == "algebra" and result.json()["exam_type"] == "ege"
    assert result.json()["cover_color"] == "gradient-green"
    assert (
        await client.patch(path, headers=OWNER, json={"description": "bad\x00text"})
    ).status_code == 422
    catalog = await client.get(
        "/api/v1/decks", headers=OWNER, params={"search": "Private after"}
    )
    assert catalog.json()["items"] == []
    assert (await client.get(path, headers=MEMBER)).status_code == 200
    assert (await client.get(path + "/cards", headers=MEMBER)).status_code == 200
    assert (await client.put(member_path, headers=MEMBER)).json() == membership.json()
    assert (await client.get(path, headers=VISITOR)).status_code == 403
    assert (await client.get(path + "/cards", headers=VISITOR)).status_code == 403
    assert (await client.put(member_path, headers=VISITOR)).status_code == 403

    async with helper.session_factory() as session:
        review = await session.get(CardReview, review_id)
        assert review is not None and review.fsrs_state == original_state

    preview_path = f"/api/v1/decks/share/{code}"
    preview = await client.get(preview_path, headers=VISITOR)
    assert preview.status_code == 200, preview.text
    assert set(preview.json()) == {"deck", "cards"}
    assert preview.json()["deck"]["id"] == deck_id
    assert preview.json()["deck"]["cards_count"] == len(preview.json()["cards"]) == 1
    assert [item["id"] for item in preview.json()["cards"]] == [card_id]
    assert (await client.get(path, headers=VISITOR)).status_code == 403
    add_path = f"/api/v1/library/decks/share/{code}"
    adds = await asyncio.gather(
        *(client.put(add_path, headers=VISITOR) for _ in range(8))
    )
    assert all(response.status_code == 200 for response in adds)
    assert len({response.json()["id"] for response in adds}) == 1
    assert (await client.get(path, headers=VISITOR)).status_code == 200
    assert (await client.get(path + "/cards", headers=VISITOR)).status_code == 200
    assert (
        await client.patch(path, headers=VISITOR, json={"title": "x"})
    ).status_code == 403
    assert (await client.put(member_path, headers=VISITOR)).status_code == 200
    async with helper.session_factory() as session:
        visitor_id = await session.scalar(
            select(User.id).where(User.vk_user_id == VK_IDS[2])
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(UserDeck)
                .where(UserDeck.user_id == visitor_id, UserDeck.deck_id == deck_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CardReview)
                .where(CardReview.user_id == visitor_id, CardReview.deck_id == deck_id)
            )
            == 0
        )
    assert (await client.delete(member_path, headers=VISITOR)).status_code == 204
    assert (await client.get(path, headers=VISITOR)).status_code == 403
    assert (await client.get(preview_path, headers=VISITOR)).status_code == 200
    missing_code = ("A" if code[0] != "A" else "B") + code[1:]
    assert (
        await client.get(f"/api/v1/decks/share/{missing_code}", headers=VISITOR)
    ).status_code == 404
    assert (
        await client.put(f"/api/v1/library/decks/share/{missing_code}", headers=VISITOR)
    ).status_code == 404
    assert (
        await client.get("/api/v1/decks/share/no", headers=VISITOR)
    ).status_code == 422


async def test_card_edit_preserves_snapshots_logs_progress_and_order(
    client, helper
) -> None:
    deck = await create_deck(client, "History deck")
    deck_id = deck["id"]
    path = f"/api/v1/decks/{deck_id}"
    created = await client.post(
        path + "/cards",
        headers=OWNER,
        json={"front": "Old front", "back": "Old back", "hint": "Old hint"},
    )
    assert created.status_code == 201
    original = created.json()
    card_id = original["id"]
    started = await client.post(
        "/api/v1/study/sessions", headers=OWNER, json={"deck_id": deck_id}
    )
    state = started.json()
    result = await client.post(
        f"/api/v1/study/sessions/{state['session']['id']}/reviews",
        headers=OWNER,
        json={"card_id": card_id, "rating": 1, "answer_token": state["answer_token"]},
    )
    assert result.status_code == 200, result.text
    async with helper.session_factory() as session:
        snapshot = await session.scalar(
            select(StudySessionCard).where(
                StudySessionCard.session_id == state["session"]["id"]
            )
        )
        review = await session.scalar(
            select(CardReview).where(CardReview.card_id == card_id)
        )
        log = await session.scalar(
            select(ReviewLog).where(ReviewLog.session_id == state["session"]["id"])
        )
        snapshot_id, review_id, log_id = snapshot.id, review.id, log.id
        original_state, original_result = review.fsrs_state, log.result

    edit_path = path + f"/cards/{card_id}"
    assert (
        await client.patch(edit_path, headers=MEMBER, json={"front": "bad"})
    ).status_code == 403
    assert (
        await client.patch(edit_path, headers=OWNER, json={"order_index": 3})
    ).status_code == 422
    response = await client.patch(
        edit_path,
        headers=OWNER,
        json={
            "front": " New front ",
            "hint": None,
            "image_url": "https://example.com/a.png",
        },
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["front"] == "New front"
        and response.json()["back"] == "Old back"
    )
    assert response.json()["hint"] is None and response.json()["order_index"] == 0
    assert (
        await client.patch(edit_path, headers=OWNER, json={"front": "bad\x00text"})
    ).status_code == 422
    assert (await client.get(path, headers=OWNER)).json()["cards_count"] == 1
    other = await create_deck(client, "Wrong deck")
    assert (
        await client.patch(
            f"/api/v1/decks/{other['id']}/cards/{card_id}",
            headers=OWNER,
            json={"back": "x"},
        )
    ).status_code == 404

    async with helper.session_factory() as session:
        snapshot = await session.get(StudySessionCard, snapshot_id)
        review = await session.get(CardReview, review_id)
        log = await session.get(ReviewLog, log_id)
        card = await session.get(Card, card_id)
        assert snapshot is not None and snapshot.snapshot == original
        assert review is not None and review.fsrs_state == original_state
        assert log is not None and log.result == original_result
        assert card is not None and card.front == "New front" and card.hint is None


async def test_catalog_and_library_filters_use_literal_search_and_pagination(
    client,
) -> None:
    prefix = "feature-catalog"
    first = await create_deck(
        client, f"{prefix} Alpha%One", is_public=True, grade=9, exam_type="oge"
    )
    second = await create_deck(
        client, f"{prefix} Alpha_One", is_public=True, grade=9, exam_type="oge"
    )
    await create_deck(client, f"{prefix} AlphaXOne", is_public=True, grade=10)
    await create_deck(
        client, f"{prefix} Chemistry", subject="chemistry", is_public=True
    )
    hidden = await create_deck(client, f"{prefix} hidden", grade=9)
    assert (
        await client.put(f"/api/v1/library/decks/{first['id']}", headers=MEMBER)
    ).status_code == 200
    assert (
        await client.put(f"/api/v1/library/decks/{second['id']}", headers=MEMBER)
    ).status_code == 200
    params = {
        "search": prefix.upper(),
        "subject": "physics",
        "grade": 9,
        "exam_type": "oge",
        "limit": 1,
    }
    page1 = (await client.get("/api/v1/decks", headers=OWNER, params=params)).json()
    page2 = (
        await client.get("/api/v1/decks", headers=OWNER, params={**params, "page": 2})
    ).json()
    page3 = (
        await client.get("/api/v1/decks", headers=OWNER, params={**params, "page": 3})
    ).json()
    assert all(set(result) == {"items", "total"} for result in (page1, page2, page3))
    assert page1["total"] == page2["total"] == page3["total"] == 2
    assert [page1["items"][0]["id"], page2["items"][0]["id"]] == [
        second["id"],
        first["id"],
    ]
    assert page3["items"] == []
    far_page = await client.get(
        "/api/v1/decks",
        headers=OWNER,
        params={**params, "page": 2**31 - 1, "limit": 100},
    )
    assert far_page.status_code == 200
    assert far_page.json() == {"items": [], "total": 2}
    for search, expected in (("%", first["id"]), ("_", second["id"])):
        response = await client.get(
            "/api/v1/decks",
            headers=OWNER,
            params={"search": f"{prefix} Alpha{search}One"},
        )
        assert [item["id"] for item in response.json()["items"]] == [expected]
    hidden_catalog = await client.get(
        "/api/v1/decks", headers=OWNER, params={"search": f"{prefix} hidden"}
    )
    assert hidden_catalog.json()["total"] == 0
    private_library = await client.get(
        "/api/v1/library/decks",
        headers=OWNER,
        params={"search": "HIDDEN", "subject": "physics"},
    )
    assert [item["id"] for item in private_library.json()["items"]] == [hidden["id"]]
    member_library = await client.get(
        "/api/v1/library/decks",
        headers=MEMBER,
        params={"search": "%", "subject": "physics"},
    )
    assert [item["id"] for item in member_library.json()["items"]] == [first["id"]]
    no_leak = await client.get(
        "/api/v1/library/decks", headers=VISITOR, params={"search": prefix}
    )
    assert no_leak.json() == {"items": [], "total": 0}


async def test_library_pagination_filters_and_isolates_users(client, helper) -> None:
    decks = [
        await create_deck(client, f"Page-Marker% {index}", is_public=index != 0)
        for index in range(5)
    ]
    await create_deck(client, "Page-Marker% chemistry", subject="chemistry")
    await create_deck(client, "Page-MarkerX physics")
    other = await client.post(
        "/api/v1/decks",
        headers=MEMBER,
        json={"title": "Page-Marker% other user", "subject": "physics"},
    )
    assert other.status_code == 201

    async with helper.session_factory.begin() as session:
        owner_id = await session.scalar(
            select(User.id).where(User.vk_user_id == VK_IDS[0])
        )
        await session.execute(
            update(UserDeck)
            .where(UserDeck.user_id == owner_id)
            .values(created_at=datetime(2026, 1, 1, tzinfo=UTC))
        )

    default = (await client.get("/api/v1/library/decks", headers=OWNER)).json()
    assert set(default) == {"items", "total"}
    assert default["total"] == 7
    assert len(default["items"]) == 7
    assert default["items"][0]["id"] == decks[0]["id"]
    assert default["items"][0]["is_public"] is False

    params = {"search": "  page-marker%  ", "subject": "physics", "limit": 2}
    pages = []
    for page in range(1, 5):
        response = await client.get(
            "/api/v1/library/decks", headers=OWNER, params={**params, "page": page}
        )
        assert response.status_code == 200
        result = response.json()
        assert set(result) == {"items", "total"}
        assert result["total"] == 5
        pages.append([item["id"] for item in result["items"]])
    assert pages == [
        [decks[0]["id"], decks[1]["id"]],
        [decks[2]["id"], decks[3]["id"]],
        [decks[4]["id"]],
        [],
    ]
    far_page = (
        await client.get(
            "/api/v1/library/decks",
            headers=OWNER,
            params={**params, "page": 2**31 - 1, "limit": 100},
        )
    ).json()
    assert far_page == {"items": [], "total": 5}
    member = (
        await client.get("/api/v1/library/decks", headers=MEMBER, params=params)
    ).json()
    assert member["total"] == 1
    assert [item["id"] for item in member["items"]] == [other.json()["id"]]
    visitor = (await client.get("/api/v1/library/decks", headers=VISITOR)).json()
    assert visitor == {"items": [], "total": 0}


async def test_card_pagination_keeps_access_order_and_full_share_preview(
    client, helper
) -> None:
    deck = await create_deck(client, "Paged private cards")
    other = await create_deck(client, "Other public cards", is_public=True)
    path = f"/api/v1/decks/{deck['id']}/cards"
    other_path = f"/api/v1/decks/{other['id']}/cards"
    empty = (await client.get(other_path, headers=OWNER)).json()
    assert empty == {"items": [], "total": 0}
    assert (
        await client.post(
            other_path, headers=OWNER, json={"front": "other", "back": "other"}
        )
    ).status_code == 201

    cards = []
    for index in range(25):
        response = await client.post(
            path, headers=OWNER, json={"front": f"Question {index}", "back": "Answer"}
        )
        assert response.status_code == 201, response.text
        cards.append(response.json())
    assert (
        await client.delete(f"{path}/{cards[1]['id']}", headers=OWNER)
    ).status_code == 204
    created = await client.post(
        path, headers=OWNER, json={"front": "New", "back": "Answer"}
    )
    assert created.status_code == 201
    assert created.json()["order_index"] == 25
    async with helper.session_factory.begin() as session:
        await session.execute(
            update(Card).where(Card.id == cards[3]["id"]).values(order_index=2)
        )
    expected_ids = [
        cards[0]["id"],
        *[card["id"] for card in cards[2:]],
        created.json()["id"],
    ]

    first = await client.get(path, headers=OWNER)
    assert first.status_code == 200
    result = first.json()
    assert set(result) == {"items", "total"}
    assert result["total"] == 25
    assert [item["id"] for item in result["items"]] == expected_ids[:20]
    assert [item["order_index"] for item in result["items"][:3]] == [0, 2, 2]
    ids = []
    for page in range(1, 6):
        response = await client.get(
            path, headers=OWNER, params={"page": page, "limit": 7}
        )
        assert response.status_code == 200
        result = response.json()
        assert set(result) == {"items", "total"}
        assert result["total"] == 25
        assert len(result["items"]) <= 7
        if page == 5:
            assert result["items"] == []
        ids.extend(item["id"] for item in result["items"])
    assert ids == expected_ids
    assert len(ids) == len(set(ids))
    far_page = (
        await client.get(path, headers=OWNER, params={"page": 2**31 - 1, "limit": 100})
    ).json()
    assert far_page == {"items": [], "total": 25}
    assert (await client.get(other_path, headers=OWNER)).json()["total"] == 1
    assert (
        await client.get(path, headers=VISITOR, params={"page": 999})
    ).status_code == 403
    assert (
        await client.get("/api/v1/decks/9223372036854775807/cards", headers=OWNER)
    ).status_code == 404

    preview = await client.get(
        f"/api/v1/decks/share/{deck['share_code']}", headers=VISITOR
    )
    assert preview.status_code == 200
    assert set(preview.json()) == {"deck", "cards"}
    assert preview.json()["deck"]["cards_count"] == len(preview.json()["cards"]) == 25
    assert [card["id"] for card in preview.json()["cards"]] == expected_ids
    added = await client.put(
        f"/api/v1/library/decks/share/{deck['share_code']}", headers=MEMBER
    )
    assert added.status_code == 200
    member_page = (await client.get(path, headers=MEMBER, params={"page": 2})).json()
    assert member_page["total"] == 25
    assert [card["id"] for card in member_page["items"]] == expected_ids[20:]


@pytest.mark.parametrize("operation", ["cards", "add", "add_by_share_code"])
async def test_flashcards_read_and_library_add_locks_allow_shares_but_block_writes(
    client, helper, monkeypatch, operation
) -> None:
    deck = await create_deck(client, "Shared lock protection", is_public=True)
    deck_id = deck["id"]
    path = f"/api/v1/decks/{deck_id}/cards"
    card = await client.post(path, headers=OWNER, json={"front": "Q", "back": "A"})
    assert card.status_code == 201
    checked = False

    async def check_lock(locked_deck_id):
        nonlocal checked
        assert locked_deck_id == deck_id
        async with (
            helper.session_factory() as reader,
            helper.session_factory() as writer,
        ):
            assert (
                await reader.scalar(
                    select(Deck)
                    .where(Deck.id == deck_id)
                    .with_for_update(read=True, of=Deck, nowait=True)
                )
                is not None
            )
            await reader.rollback()
            with pytest.raises(DBAPIError) as caught:
                async with writer.begin_nested():
                    await writer.scalar(
                        select(Deck)
                        .where(Deck.id == deck_id)
                        .with_for_update(of=Deck, nowait=True)
                    )
            assert caught.value.orig.sqlstate == "55P03"
        checked = True

    if operation == "cards":
        original_page = SQLACardRepository.list_page_for_deck

        async def checked_page(self, selected_deck_id, data, *, total):
            await check_lock(selected_deck_id)
            assert total == 1
            return await original_page(self, selected_deck_id, data, total=total)

        monkeypatch.setattr(SQLACardRepository, "list_page_for_deck", checked_page)
        response = await client.get(path, headers=VISITOR)
        assert response.status_code == 200
        assert response.json()["total"] == len(response.json()["items"]) == 1
    else:
        original_membership = SQLALibraryRepository.ensure_membership

        async def checked_membership(self, *, user_id, deck_id):
            await check_lock(deck_id)
            return await original_membership(self, user_id=user_id, deck_id=deck_id)

        monkeypatch.setattr(
            SQLALibraryRepository, "ensure_membership", checked_membership
        )
        add_path = (
            f"/api/v1/library/decks/{deck_id}"
            if operation == "add"
            else f"/api/v1/library/decks/share/{deck['share_code']}"
        )
        response = await client.put(add_path, headers=MEMBER)
        assert response.status_code == 200
        assert response.json()["deck_id"] == deck_id
    assert checked


@pytest.mark.parametrize("mutation", ["add", "delete"])
async def test_full_share_preview_count_matches_cards_changed_after_metadata_read(
    client, monkeypatch, mutation
) -> None:
    deck = await create_deck(client, "Preview count race")
    path = f"/api/v1/decks/{deck['id']}/cards"
    first = await client.post(
        path,
        headers=OWNER,
        json={
            "front": "Question",
            "back": "Answer",
            "hint": "Hint",
            "explanation": "Explanation",
            "image_url": "https://example.com/card.png",
        },
    )
    assert first.status_code == 201
    original = SQLACardRepository.list_for_deck
    expected = []

    async def mutate_before_read(self, deck_id):
        assert deck_id == deck["id"]
        if mutation == "add":
            added = await client.post(
                path, headers=OWNER, json={"front": "New", "back": "New answer"}
            )
            assert added.status_code == 201
            expected.extend([first.json(), added.json()])
        else:
            deleted = await client.delete(f"{path}/{first.json()['id']}", headers=OWNER)
            assert deleted.status_code == 204
        return await original(self, deck_id)

    monkeypatch.setattr(SQLACardRepository, "list_for_deck", mutate_before_read)
    response = await client.get(
        f"/api/v1/decks/share/{deck['share_code']}", headers=VISITOR
    )
    assert response.status_code == 200
    preview = response.json()
    assert set(preview) == {"deck", "cards"}
    assert preview["cards"] == expected
    assert preview["deck"]["cards_count"] == len(expected)
    stored = await client.get(f"/api/v1/decks/{deck['id']}", headers=OWNER)
    assert stored.status_code == 200
    assert stored.json()["cards_count"] == len(expected)


@pytest.mark.parametrize("kind", ["list", "dict"])
async def test_settings_depth_limit_preserves_readable_stored_profile(
    client, helper, kind
) -> None:
    opening, closing = (b"[", b"]") if kind == "list" else (b'{"x":', b"}")

    def payload(depth: int) -> bytes:
        return b'{"x":' + opening * depth + b"0" + closing * depth + b"}"

    path = "/api/v1/users/me/settings"
    headers = {**OWNER, "Content-Type": "application/json"}
    accepted = payload(253)
    response = await client.put(path, headers=headers, content=accepted)
    assert response.status_code == 200
    assert response.json()["settings"] == json.loads(accepted)
    for depth in (254, 255, 1500, 10_000):
        response = await client.put(path, headers=headers, content=payload(depth))
        assert response.status_code == 422
        assert all(
            set(error) == {"type", "loc", "msg"} for error in response.json()["detail"]
        )
    async with helper.session_factory() as session:
        settings = await session.scalar(
            select(User.settings).where(User.vk_user_id == VK_IDS[0])
        )
        assert settings == json.loads(accepted)
    profile = await client.get("/api/v1/users/me/profile", headers=OWNER)
    assert profile.status_code == 200
    assert profile.json()["settings"] == json.loads(accepted)


@pytest.mark.parametrize("letter", ["a", "я", "😀"])
@pytest.mark.parametrize("chunked", [False, True])
async def test_json_body_size_limit_preserves_stored_settings(
    client, helper, letter, chunked
) -> None:
    prefix, suffix = '{"x":"', '"}'
    text = prefix + letter * (MAX_JSON_BODY_CHARACTERS - len(prefix + suffix)) + suffix
    accepted = text.encode()
    path = "/api/v1/users/me/settings"
    headers = {**OWNER, "Content-Type": "application/json"}
    response = await client.put(path, headers=headers, content=accepted)
    assert response.status_code == 200
    assert response.json()["settings"] == json.loads(accepted)

    rejected = (text + " ").encode()

    async def chunks():

        for start in range(0, len(rejected), 1023):
            yield rejected[start : start + 1023]

    response = await client.put(
        path, headers=headers, content=chunks() if chunked else rejected
    )
    assert response.status_code == 413
    async with helper.session_factory() as session:
        stored = await session.scalar(
            select(User.settings).where(User.vk_user_id == VK_IDS[0])
        )
        assert stored == json.loads(accepted)
    profile = await client.get("/api/v1/users/me/profile", headers=OWNER)
    assert profile.status_code == 200
    assert profile.json()["settings"] == json.loads(accepted)


async def test_oversized_sync_does_not_modify_existing_user(client, helper) -> None:
    payload = json.dumps({"vk_user_id": VK_IDS[0], "first_name": "must-not-save"})
    payload += " " * (MAX_JSON_BODY_CHARACTERS + 1 - len(payload))
    response = await client.post(
        "/api/v1/users/sync",
        content=payload.encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    async with helper.session_factory() as session:
        first_name = await session.scalar(
            select(User.first_name).where(User.vk_user_id == VK_IDS[0])
        )
        assert first_name == ""


async def test_settings_and_profile_columns_are_independent(client, helper) -> None:
    profile_path = "/api/v1/users/me/profile"
    path = "/api/v1/users/me/settings"
    initial = await client.get(profile_path, headers=OWNER)
    assert initial.status_code == 200 and initial.json()["settings"] == {}
    assert initial.json()["timezone"] == "UTC"
    assert initial.json()["daily_new_cards_limit"] == 12
    assert initial.json()["daily_total_cards_limit"] == 125
    settings_data = {
        "timezone": "Mars/Olympus",
        "daily_new_cards_limit": {"custom": 500},
        "role": "admin",
        "theme": "anything-the-client-wants",
        "settings": {"nested": [1, None, False, {"a": "b"}]},
        "__pydantic_extra__": "arbitrary key",
    }
    response = await client.put(path, headers=OWNER, json=settings_data)
    assert response.status_code == 200, response.text
    assert response.json()["settings"] == settings_data
    assert response.json()["timezone"] == "UTC"
    assert response.json()["daily_new_cards_limit"] == 12
    assert response.json()["role"] == "student"
    async with helper.session_factory() as session:
        user = await session.scalar(select(User).where(User.vk_user_id == VK_IDS[0]))
        assert user is not None
        assert user.settings == settings_data and user.timezone == "UTC"
        assert user.daily_new_cards_limit == 12 and user.role.value == "student"
    for invalid in (
        {"custom": {"bad\x00key": 1}},
        {"custom": ["bad\x00value"]},
    ):
        assert (await client.put(path, headers=OWNER, json=invalid)).status_code == 422
        assert (await client.get(profile_path, headers=OWNER)).json()[
            "settings"
        ] == settings_data
    assert (await client.put(path, headers=OWNER, json=[])).status_code == 422
    for invalid in (
        {"timezone": "Mars/Olympus"},
        {"timezone": None},
        {"daily_new_cards_limit": None},
        {"daily_new_cards_limit": 0},
        {"daily_new_cards_limit": 251},
        {"daily_new_cards_limit": True},
        {"daily_new_cards_limit": "20"},
    ):
        response = await client.patch(
            profile_path, headers=OWNER, json={"first_name": "Not saved", **invalid}
        )
        assert response.status_code == 422
        unchanged = (await client.get(profile_path, headers=OWNER)).json()
        assert unchanged["first_name"] == ""
        assert unchanged["settings"] == settings_data
        assert (
            unchanged["timezone"] == "UTC" and unchanged["daily_new_cards_limit"] == 12
        )

    response = await client.patch(
        profile_path,
        headers=OWNER,
        json={"timezone": "Europe/Moscow", "daily_new_cards_limit": 30},
    )
    assert response.status_code == 200, response.text
    assert response.json()["settings"] == settings_data
    assert response.json()["timezone"] == "Europe/Moscow"
    assert response.json()["daily_new_cards_limit"] == 30
    async with helper.session_factory() as session:
        user = await session.scalar(select(User).where(User.vk_user_id == VK_IDS[0]))
        assert user is not None
        assert user.settings == settings_data and user.timezone == "Europe/Moscow"
        assert user.daily_new_cards_limit == 30

    replacement = {"timezone": None, "daily_new_cards_limit": False, "another": None}
    response = await client.put(path, headers=OWNER, json=replacement)
    assert response.json()["settings"] == replacement
    assert response.json()["timezone"] == "Europe/Moscow"
    assert response.json()["daily_new_cards_limit"] == 30
    response = await client.put(path, headers=OWNER, json={})
    assert response.json()["settings"] == {}
    assert response.json()["timezone"] == "Europe/Moscow"
    assert response.json()["daily_new_cards_limit"] == 30

    final_settings = {"after_sync": [1, 2], "timezone": "frontend-only"}
    assert (
        await client.put(path, headers=OWNER, json=final_settings)
    ).status_code == 200
    synced = await client.post(
        "/api/v1/users/sync", json={"vk_user_id": VK_IDS[0], "timezone": "Asia/Tokyo"}
    )
    assert synced.status_code == 200
    assert synced.json()["settings"] == final_settings
    assert synced.json()["timezone"] == "Asia/Tokyo"
    assert synced.json()["daily_new_cards_limit"] == 30
    synced_again = await client.post(
        "/api/v1/users/sync", json={"vk_user_id": VK_IDS[0]}
    )
    assert synced_again.json()["settings"] == final_settings
    assert synced_again.json()["timezone"] == "Asia/Tokyo"


async def test_concurrent_settings_replacements_do_not_mix_json_objects(client) -> None:
    path = "/api/v1/users/me/settings"
    left, right = await asyncio.gather(
        client.put(path, headers=OWNER, json={"timezone": "Europe/Moscow", "left": 1}),
        client.put(path, headers=OWNER, json={"daily_new_cards_limit": 9, "right": 2}),
    )
    assert left.status_code == right.status_code == 200
    profile = (await client.get("/api/v1/users/me/profile", headers=OWNER)).json()
    assert profile["timezone"] == "UTC"
    assert profile["daily_new_cards_limit"] == 12
    assert profile["settings"] in (
        {"timezone": "Europe/Moscow", "left": 1},
        {"daily_new_cards_limit": 9, "right": 2},
    )


async def test_concurrent_settings_and_profile_updates_do_not_overwrite_each_other(
    client,
) -> None:
    settings = {
        "timezone": "client-only",
        "daily_new_cards_limit": 100,
        "feature": True,
    }
    updated_settings, updated_profile = await asyncio.gather(
        client.put("/api/v1/users/me/settings", headers=OWNER, json=settings),
        client.patch(
            "/api/v1/users/me/profile",
            headers=OWNER,
            json={"timezone": "Europe/Moscow", "daily_new_cards_limit": 9},
        ),
    )
    assert updated_settings.status_code == updated_profile.status_code == 200
    profile = (await client.get("/api/v1/users/me/profile", headers=OWNER)).json()
    assert profile["timezone"] == "Europe/Moscow"
    assert profile["daily_new_cards_limit"] == 9
    assert profile["settings"] == settings


async def test_concurrent_deck_patches_preserve_independent_fields(client) -> None:
    deck = await create_deck(client, "Original title")
    path = f"/api/v1/decks/{deck['id']}"
    left, right = await asyncio.gather(
        client.patch(path, headers=OWNER, json={"title": "New title"}),
        client.patch(path, headers=OWNER, json={"description": "New description"}),
    )
    assert left.status_code == right.status_code == 200
    current = (await client.get(path, headers=OWNER)).json()
    assert (
        current["title"] == "New title" and current["description"] == "New description"
    )


async def test_share_codes_are_case_sensitive(client, helper) -> None:
    deck = await create_deck(client, "Case sensitive")
    code = "A" + deck["share_code"][1:]
    async with helper.session_factory.begin() as session:
        stored = await session.get(Deck, deck["id"])
        assert stored is not None
        stored.share_code = code
    assert (
        await client.get(f"/api/v1/decks/share/{code}", headers=VISITOR)
    ).status_code == 200
    wrong_case = "a" + code[1:]
    assert (
        await client.get(f"/api/v1/decks/share/{wrong_case}", headers=VISITOR)
    ).status_code == 404
