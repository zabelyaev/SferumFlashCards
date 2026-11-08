import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, select

from application.accounts.users.database.models import User
from application.flashcards.decks.database.models import Deck
from application.study.database.repository import StudyRepository
from application.study.services import study as study_service
from application.study.services.planner import StudyPlanner
from common.database import DatabaseHelper
from main import create_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration
VK_ID = 96273188
OTHER_VK_ID = 96273189
HEADERS = {"X-VK-User-ID": str(VK_ID)}


@pytest_asyncio.fixture
async def client(
    app_headers: dict[str, str], validated_test_database
) -> AsyncIterator[AsyncClient]:
    helper = DatabaseHelper(validated_test_database)

    async def cleanup() -> None:
        async with helper.session_factory.begin() as session:
            ids = select(User.id).where(User.vk_user_id.in_((VK_ID, OTHER_VK_ID)))
            await session.execute(delete(Deck).where(Deck.author_id.in_(ids)))
            await session.execute(
                delete(User).where(User.vk_user_id.in_((VK_ID, OTHER_VK_ID)))
            )

    try:
        await cleanup()
        app = create_app()
        app.state.database_helper = helper
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=app_headers,
        ) as client:
            result = await client.post("/api/v1/users/sync", json={"vk_user_id": VK_ID})
            assert result.status_code == 200, result.text
            yield client
    finally:
        await cleanup()
        await helper.dispose()


async def test_study_review_replay_and_completion(client: AsyncClient) -> None:
    profile = (await client.get("/api/v1/users/me/profile", headers=HEADERS)).json()
    assert profile["daily_total_cards_limit"] == 125
    assert profile["daily_new_cards_limit"] == 12
    deck = await client.post("/api/v1/decks", headers=HEADERS, json={"title": "FSRS"})
    deck_id = deck.json()["id"]
    for title in ("first", "second"):
        card = await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            headers=HEADERS,
            json={"front": title, "back": "answer"},
        )
        assert card.status_code == 201, card.text

    async def open_session():
        return await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )

    responses = await asyncio.gather(open_session(), open_session())
    assert sorted(item.status_code for item in responses) == [200, 201]
    state = responses[0].json()
    assert state["session"]["id"] == responses[1].json()["session"]["id"]
    assert len(state["cards"]) == 2
    session_id = state["session"]["id"]
    path = f"/api/v1/study/sessions/{session_id}/reviews"
    payload = {
        "card_id": state["current_card_id"],
        "answer_token": state["answer_token"],
        "rating": 1,
    }
    first = await client.post(path, headers=HEADERS, json=payload)
    assert first.status_code == 200, first.text
    again = await client.post(path, headers=HEADERS, json=payload)
    assert again.json() == first.json()
    conflict = await client.post(path, headers=HEADERS, json={**payload, "rating": 2})
    assert conflict.status_code == 409
    current = first.json()
    while current["session"]["status"] == "active":
        response = await client.post(
            path,
            headers=HEADERS,
            json={
                "card_id": current["current_card_id"],
                "answer_token": current["answer_token"],
                "rating": 3,
            },
        )
        assert response.status_code == 200, response.text
        current = response.json()
    assert current["session"]["progress"]["completed_cards"] == 2
    assert current["quota"]["new_used"] == 2
    assert current["streak"]["streak_days"] == 1
    active = await client.get("/api/v1/study/sessions/active", headers=HEADERS)
    assert active.json()["total"] == 0


async def test_personal_weights_are_private_and_frozen_per_session(
    client: AsyncClient,
) -> None:
    from fsrs.scheduler import DEFAULT_PARAMETERS

    from application.study.database.models import StudySession

    app = cast(ASGITransport, client._transport).app
    helper = app.state.database_helper
    decks = []
    for title in ("old snapshot", "new snapshot"):
        deck = await client.post(
            "/api/v1/decks", headers=HEADERS, json={"title": title}
        )
        deck_id = deck.json()["id"]
        assert (
            await client.post(
                f"/api/v1/decks/{deck_id}/cards",
                headers=HEADERS,
                json={"front": "question", "back": "answer"},
            )
        ).status_code == 201
        decks.append(deck_id)

    old = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": decks[0]}
    )
    assert old.status_code == 201
    weights = list(DEFAULT_PARAMETERS)
    weights[0] *= 1.1
    async with helper.session_factory.begin() as session:
        user = await session.scalar(select(User).where(User.vk_user_id == VK_ID))
        user.fsrs_parameters = weights

    resumed = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": decks[0]}
    )
    new = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": decks[1]}
    )
    assert resumed.status_code == 200 and resumed.json() == old.json()
    assert new.status_code == 201
    async with helper.session_factory() as session:
        old_row = await session.get(StudySession, old.json()["session"]["id"])
        new_row = await session.get(StudySession, new.json()["session"]["id"])
        assert old_row.scheduler_config["scheduler"]["parameters"] == list(
            DEFAULT_PARAMETERS
        )
        assert new_row.scheduler_config["scheduler"]["parameters"] == weights

    profile = await client.get("/api/v1/users/me/profile", headers=HEADERS)
    assert "fsrs_parameters" not in profile.json()
    assert "fsrs_parameters" not in new.text
    assert "scheduler_config" not in new.text
    rejected = await client.patch(
        "/api/v1/users/me/profile", headers=HEADERS, json={"fsrs_parameters": weights}
    )
    assert rejected.status_code == 422
    rejected_sync = await client.post(
        "/api/v1/users/sync", json={"vk_user_id": VK_ID, "fsrs_parameters": weights}
    )
    assert rejected_sync.status_code == 422
    arbitrary = await client.put(
        "/api/v1/users/me/settings", headers=HEADERS, json={"fsrs_parameters": [123]}
    )
    assert arbitrary.status_code == 200
    async with helper.session_factory() as session:
        user = await session.scalar(select(User).where(User.vk_user_id == VK_ID))
        assert user.fsrs_parameters == weights


async def test_open_reports_each_no_work_reason(client: AsyncClient) -> None:
    await client.patch(
        "/api/v1/users/me/profile",
        headers=HEADERS,
        json={"daily_new_cards_limit": 1},
    )
    deck_id = (
        await client.post("/api/v1/decks", headers=HEADERS, json={"title": "Empty"})
    ).json()["id"]
    path = "/api/v1/study/sessions"
    empty = await client.post(path, headers=HEADERS, json={"deck_id": deck_id})
    assert empty.status_code == 200
    assert empty.json()["reason"] == "empty_deck"
    assert empty.json()["session"] is None and empty.json()["cards"] == []
    card_ids = []
    for front in ("first", "second"):
        card = await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            headers=HEADERS,
            json={"front": front, "back": "answer"},
        )
        assert card.status_code == 201
        card_ids.append(card.json()["id"])
    opened = await client.post(path, headers=HEADERS, json={"deck_id": deck_id})
    assert opened.status_code == 201
    state = opened.json()
    resumed = await client.post(path, headers=HEADERS, json={"deck_id": deck_id})
    assert resumed.status_code == 200 and resumed.json() == state
    reviewed = await client.post(
        f"{path}/{state['session']['id']}/reviews",
        headers=HEADERS,
        json={
            "card_id": state["current_card_id"],
            "rating": 3,
            "answer_token": state["answer_token"],
        },
    )
    assert reviewed.status_code == 200
    limited = await client.post(path, headers=HEADERS, json={"deck_id": deck_id})
    assert limited.status_code == 200 and limited.json()["reason"] == "limits_reached"
    other_id = next(
        card_id for card_id in card_ids if card_id != state["current_card_id"]
    )
    deleted = await client.delete(
        f"/api/v1/decks/{deck_id}/cards/{other_id}", headers=HEADERS
    )
    assert deleted.status_code == 204
    due = await client.post(path, headers=HEADERS, json={"deck_id": deck_id})
    assert due.status_code == 200 and due.json()["reason"] == "nothing_due"


@pytest.mark.parametrize("with_card", [False, True])
async def test_open_reads_daily_usage_once(
    client: AsyncClient, with_card: bool
) -> None:
    deck = await client.post(
        "/api/v1/decks", headers=HEADERS, json={"title": "Single quota read"}
    )
    deck_id = deck.json()["id"]
    if with_card:
        card = await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            headers=HEADERS,
            json={"front": "question", "back": "answer"},
        )
        assert card.status_code == 201

    app = cast(ASGITransport, client._transport).app
    engine = app.state.database_helper.engine.sync_engine
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert response.status_code == (201 if with_card else 200), response.text
    quota_queries = [
        statement
        for statement in statements
        if statement.lstrip().startswith("select")
        and "from study_daily_cards" in statement
    ]
    assert len(quota_queries) == 1
    if with_card:
        assert len(response.json()["cards"]) == 1
        assert not any(
            statement.lstrip().startswith("select")
            and "from study_session_cards" in statement
            for statement in statements
        )


async def test_candidate_batches_match_unbounded_reference_selection(
    client: AsyncClient,
) -> None:
    from application.activity.service import StreakService
    from application.flashcards.cards.database.models import Card
    from application.flashcards.library.database.models import UserDeck
    from application.study.contracts.outputs import StudyLimitsOutput
    from application.study.contracts.types import DailyUsage
    from application.study.database.models import CardReview, LearningCycle
    from application.study.database.sqla_uow import SQLAStudyUnitOfWorkFactory
    from application.study.services.study import StudyService
    from common.config import settings

    response = await client.post(
        "/api/v1/decks", headers=HEADERS, json={"title": "Large batch"}
    )
    deck_id = response.json()["id"]
    app = cast(ASGITransport, client._transport).app
    helper = app.state.database_helper
    now = datetime.now(UTC)
    async with helper.session_factory.begin() as session:
        user_id = await session.scalar(select(User.id).where(User.vk_user_id == VK_ID))
        membership_id = await session.scalar(
            select(UserDeck.id).where(
                UserDeck.user_id == user_id, UserDeck.deck_id == deck_id
            )
        )
        cards = [
            Card(deck_id=deck_id, front=f"front {i}", back="answer", order_index=i // 2)
            for i in range(360)
        ]
        session.add_all(cards)
        await session.flush()
        cycles = [
            LearningCycle(
                user_id=user_id,
                card_id=card.id,
                deck_id=deck_id,
                membership_id=membership_id,
                created_at=now,
            )
            for card in cards[:200]
        ]
        session.add_all(cycles)
        await session.flush()
        session.add_all(
            CardReview(
                user_id=user_id,
                card_id=card.id,
                deck_id=deck_id,
                cycle_id=cycle.id,
                fsrs_state={},
                due_date=now + timedelta(days=1 if i % 17 == 0 else -1),
                last_reviewed=now,
            )
            for i, (card, cycle) in enumerate(zip(cards, cycles))
        )
        ids = [card.id for card in cards]

    planner = StudyPlanner(settings.study)
    factory = SQLAStudyUnitOfWorkFactory(helper.session_factory)
    service = StudyService(factory, streak_factory=StreakService, planner=planner)
    scenarios = [
        (
            DailyUsage(frozenset(), frozenset()),
            StudyLimitsOutput(daily_total_cards_limit=20, daily_new_cards_limit=1),
        ),
        (
            DailyUsage(frozenset(), frozenset()),
            StudyLimitsOutput(daily_total_cards_limit=250, daily_new_cards_limit=125),
        ),
        (
            DailyUsage(frozenset(ids[:25] + ids[200:210]), frozenset(ids[200:210])),
            StudyLimitsOutput(daily_total_cards_limit=20, daily_new_cards_limit=1),
        ),
        (
            DailyUsage(frozenset(ids[:10] + ids[200:201]), frozenset(ids[200:201])),
            StudyLimitsOutput(daily_total_cards_limit=20, daily_new_cards_limit=1),
        ),
    ]
    async with factory() as uow:
        query = (
            select(Card, CardReview)
            .outerjoin(
                CardReview,
                (CardReview.card_id == Card.id) & (CardReview.user_id == user_id),
            )
            .where(
                Card.deck_id == deck_id,
                (CardReview.id.is_(None)) | (CardReview.due_date <= now),
            )
            .order_by(
                CardReview.id.is_(None), CardReview.due_date, Card.order_index, Card.id
            )
        )
        reference = list((await uow.repo.db.execute(query)).all())
        for usage, limits in scenarios:
            expected = []
            total, new = len(usage.card_ids), len(usage.new_card_ids)
            for card, progress in reference:
                total_cost = int(card.id not in usage.card_ids)
                new_cost = int(progress is None and card.id not in usage.new_card_ids)
                if (total_cost and total >= limits.daily_total_cards_limit) or (
                    new_cost and new >= limits.daily_new_cards_limit
                ):
                    continue
                expected.append(card.id)
                total += total_cost
                new += new_cost
            actual = await service._select_candidates(
                uow,
                user_id=user_id,
                deck_id=deck_id,
                now=now,
                usage=usage,
                limits=limits,
            )
            assert [card.id for card, _ in actual] == expected


async def test_large_new_deck_hydrates_only_selected_card(client: AsyncClient) -> None:
    from application.flashcards.cards.database.models import Card

    assert (
        await client.patch(
            "/api/v1/users/me/profile",
            headers=HEADERS,
            json={"daily_new_cards_limit": 1},
        )
    ).status_code == 200
    deck = await client.post(
        "/api/v1/decks", headers=HEADERS, json={"title": "Large new deck"}
    )
    deck_id = deck.json()["id"]
    app = cast(ASGITransport, client._transport).app
    helper = app.state.database_helper
    async with helper.session_factory.begin() as session:
        session.add_all(
            Card(
                deck_id=deck_id,
                front=f"question {i}",
                back="answer" * 100,
                order_index=i,
            )
            for i in range(1000)
        )
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.lower().split()))

    engine = helper.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        opened = await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert opened.status_code == 201, opened.text
    assert len(opened.json()["cards"]) == 1
    candidate_queries = [
        sql for sql in statements if sql.startswith("select") and "from cards" in sql
    ]
    assert any(
        "cards.front" not in sql and "not (exists" in sql and " limit " in sql
        for sql in candidate_queries
    )
    hydration = [sql for sql in candidate_queries if "cards.front" in sql]
    assert len(hydration) == 1
    assert "cards.id in (" in hydration[0]


async def test_two_users_can_open_same_deck_concurrently(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = {"X-VK-User-ID": str(OTHER_VK_ID)}
    assert (
        await client.post("/api/v1/users/sync", json={"vk_user_id": OTHER_VK_ID})
    ).status_code == 200
    deck = await client.post(
        "/api/v1/decks",
        headers=HEADERS,
        json={"title": "Concurrent learners", "is_public": True},
    )
    deck_id = deck.json()["id"]
    assert (
        await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            headers=HEADERS,
            json={"front": "q", "back": "a"},
        )
    ).status_code == 201
    assert (
        await client.put(f"/api/v1/library/decks/{deck_id}", headers=other)
    ).status_code == 200
    original = StudyRepository.candidate_batch
    both_reached = asyncio.Event()
    reached: set[int] = set()

    async def rendezvous(self, user_id, *args, **kwargs):
        result = await original(self, user_id, *args, **kwargs)
        reached.add(user_id)
        if len(reached) == 2:
            both_reached.set()
        await asyncio.wait_for(both_reached.wait(), timeout=5)
        return result

    monkeypatch.setattr(StudyRepository, "candidate_batch", rendezvous)
    responses = await asyncio.gather(
        client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        ),
        client.post("/api/v1/study/sessions", headers=other, json={"deck_id": deck_id}),
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["session"]["id"] != responses[1].json()["session"]["id"]
    monkeypatch.setattr(StudyRepository, "candidate_batch", original)
    original_cards = StudyRepository.review_cards
    both_reviewing = asyncio.Event()
    reviewing: set[int] = set()

    async def review_rendezvous(self, session_id):
        result = await original_cards(self, session_id)
        reviewing.add(session_id)
        if len(reviewing) == 2:
            both_reviewing.set()
        await asyncio.wait_for(both_reviewing.wait(), timeout=5)
        return result

    monkeypatch.setattr(StudyRepository, "review_cards", review_rendezvous)
    reviews = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/study/sessions/{view['session']['id']}/reviews",
                headers=headers,
                json={
                    "card_id": view["current_card_id"],
                    "answer_token": view["answer_token"],
                    "rating": 3,
                },
            )
            for view, headers in (
                (responses[0].json(), HEADERS),
                (responses[1].json(), other),
            )
        )
    )
    assert [review.status_code for review in reviews] == [200, 200]
    assert all(review.json()["session"]["status"] == "completed" for review in reviews)
    assert reviewing == {response.json()["session"]["id"] for response in responses}
    assert both_reviewing.is_set()


async def test_study_deck_lock_blocks_exclusive_content_writes(
    client: AsyncClient,
) -> None:
    from sqlalchemy.exc import DBAPIError

    deck = await client.post(
        "/api/v1/decks", headers=HEADERS, json={"title": "Lock protection"}
    )
    deck_id = deck.json()["id"]
    app = cast(ASGITransport, client._transport).app
    helper = app.state.database_helper
    async with helper.session_factory() as reader, helper.session_factory() as writer:
        assert await StudyRepository(reader).lock_deck(deck_id) is not None
        with pytest.raises(DBAPIError) as caught:
            async with writer.begin_nested():
                await writer.scalar(
                    select(Deck).where(Deck.id == deck_id).with_for_update(nowait=True)
                )
        assert caught.value.orig.sqlstate == "55P03"
        await reader.rollback()
        assert (
            await writer.scalar(
                select(Deck).where(Deck.id == deck_id).with_for_update(nowait=True)
            )
            is not None
        )
        await writer.rollback()


async def test_open_session_serializes_with_card_deletion(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    deck = await client.post(
        "/api/v1/decks", headers=HEADERS, json={"title": "Delete during open"}
    )
    deck_id = deck.json()["id"]
    card = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        headers=HEADERS,
        json={"front": "original", "back": "answer"},
    )
    card_id = card.json()["id"]
    ready = asyncio.Event()
    release = asyncio.Event()
    original = StudyRepository.candidate_batch

    async def pause_while_locked(self, *args, **kwargs):
        batch = await original(self, *args, **kwargs)
        ready.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        return batch

    monkeypatch.setattr(StudyRepository, "candidate_batch", pause_while_locked)
    open_task = asyncio.create_task(
        client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )
    )
    delete_task = None
    try:
        await asyncio.wait_for(ready.wait(), timeout=5)
        delete_task = asyncio.create_task(
            client.delete(f"/api/v1/decks/{deck_id}/cards/{card_id}", headers=HEADERS)
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(delete_task), timeout=0.3)
        release.set()
        opened = await asyncio.wait_for(open_task, timeout=5)
        deleted = await asyncio.wait_for(delete_task, timeout=5)
    finally:
        release.set()
        await asyncio.gather(
            open_task,
            *(task for task in (delete_task,) if task is not None),
            return_exceptions=True,
        )
    assert opened.status_code == 201
    assert deleted.status_code == 204
    view = opened.json()
    assert view["cards"][0]["front"] == "original"
    review = await client.post(
        f"/api/v1/study/sessions/{view['session']['id']}/reviews",
        headers=HEADERS,
        json={"card_id": card_id, "answer_token": view["answer_token"], "rating": 3},
    )
    assert review.status_code == 200
    assert review.json()["session"]["status"] == "completed"


async def test_concurrent_profile_update_and_completion_keep_streak(
    client: AsyncClient,
) -> None:
    deck = await client.post("/api/v1/decks", headers=HEADERS, json={"title": "Race"})
    deck_id = deck.json()["id"]
    card = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        headers=HEADERS,
        json={"front": "question", "back": "answer"},
    )
    assert card.status_code == 201
    opened = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
    )
    state = opened.json()
    review, update = await asyncio.gather(
        client.post(
            f"/api/v1/study/sessions/{state['session']['id']}/reviews",
            headers=HEADERS,
            json={
                "card_id": state["current_card_id"],
                "rating": 3,
                "answer_token": state["answer_token"],
            },
        ),
        client.patch(
            "/api/v1/users/me/profile", headers=HEADERS, json={"first_name": "Updated"}
        ),
    )
    assert review.status_code == update.status_code == 200
    profile = await client.get("/api/v1/users/me/profile", headers=HEADERS)
    assert profile.json()["first_name"] == "Updated"
    assert profile.json()["streak_days"] == 1


async def test_limits_are_independent_and_frozen_per_session(
    client: AsyncClient,
) -> None:
    changed = await client.patch(
        "/api/v1/users/me/profile",
        headers=HEADERS,
        json={"daily_total_cards_limit": 20, "daily_new_cards_limit": 1},
    )
    assert changed.status_code == 200, changed.text
    deck_ids = []
    for title in ("first deck", "second deck"):
        deck_id = (
            await client.post("/api/v1/decks", headers=HEADERS, json={"title": title})
        ).json()["id"]
        deck_ids.append(deck_id)
        for number in range(2):
            assert (
                await client.post(
                    f"/api/v1/decks/{deck_id}/cards",
                    headers=HEADERS,
                    json={"front": str(number), "back": "answer"},
                )
            ).status_code == 201
    first = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_ids[0]}
    )
    second = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_ids[1]}
    )
    assert first.status_code == second.status_code == 201
    assert len(first.json()["cards"]) == len(second.json()["cards"]) == 1
    assert (
        await client.patch(
            "/api/v1/users/me/profile",
            headers=HEADERS,
            json={"daily_new_cards_limit": 2},
        )
    ).status_code == 200
    resumed = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_ids[0]}
    )
    assert resumed.json()["session"]["limits"]["daily_new_cards_limit"] == 1
    current = resumed.json()
    path = f"/api/v1/study/sessions/{current['session']['id']}/reviews"
    response = await client.post(
        path,
        headers=HEADERS,
        json={
            "card_id": current["current_card_id"],
            "rating": 3,
            "answer_token": current["answer_token"],
        },
    )
    assert response.status_code == 200, response.text
    new = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_ids[0]}
    )
    assert new.status_code == 201, new.text
    assert new.json()["session"]["limits"]["daily_new_cards_limit"] == 2
    assert new.json()["quota"]["new_used"] == 1
    assert len(new.json()["cards"]) == 1


async def test_session_crosses_midnight_and_attributes_old_day(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [datetime(2026, 11, 2, 23, 59, tzinfo=UTC)]
    monkeypatch.setattr(study_service, "now_utc", lambda: clock[0])
    deck_id = (
        await client.post("/api/v1/decks", headers=HEADERS, json={"title": "late"})
    ).json()["id"]
    for number in range(2):
        assert (
            await client.post(
                f"/api/v1/decks/{deck_id}/cards",
                headers=HEADERS,
                json={"front": str(number), "back": "answer"},
            )
        ).status_code == 201
    opened = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
    )
    state = opened.json()
    assert state["session"]["study_date"] == "2026-11-02"
    assert state["session"]["expires_at"].startswith("2026-11-03T00:29:00")
    path = f"/api/v1/study/sessions/{state['session']['id']}/reviews"
    clock[0] = datetime(2026, 11, 3, 0, 15, tzinfo=UTC)
    result = await client.post(
        path,
        headers=HEADERS,
        json={
            "card_id": state["current_card_id"],
            "rating": 3,
            "answer_token": state["answer_token"],
        },
    )
    assert result.status_code == 200, result.text
    state = result.json()
    assert state["session"]["expires_at"].startswith("2026-11-03T00:45:00")
    assert state["session"]["study_date"] == "2026-11-02"
    clock[0] = datetime(2026, 11, 3, 0, 40, tzinfo=UTC)
    result = await client.post(
        path,
        headers=HEADERS,
        json={
            "card_id": state["current_card_id"],
            "rating": 3,
            "answer_token": state["answer_token"],
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["session"]["status"] == "completed"
    assert result.json()["streak"]["last_streak_date"] == "2026-11-02"


async def test_late_completion_connects_streak_after_new_day_completion(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [datetime(2026, 11, 1, 12, tzinfo=UTC)]
    monkeypatch.setattr(study_service, "now_utc", lambda: clock[0])
    deck_ids = []
    for title in ("first", "late", "today"):
        deck = await client.post(
            "/api/v1/decks", headers=HEADERS, json={"title": title}
        )
        deck_id = deck.json()["id"]
        card = await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            headers=HEADERS,
            json={"front": title, "back": "answer"},
        )
        assert card.status_code == 201
        deck_ids.append(deck_id)

    async def open_deck(deck_id: int) -> dict:
        response = await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )
        assert response.status_code == 201
        return response.json()

    async def complete(state: dict) -> dict:
        response = await client.post(
            f"/api/v1/study/sessions/{state['session']['id']}/reviews",
            headers=HEADERS,
            json={
                "card_id": state["current_card_id"],
                "rating": 3,
                "answer_token": state["answer_token"],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert (await complete(await open_deck(deck_ids[0])))["streak"]["streak_days"] == 1
    clock[0] = datetime(2026, 11, 2, 23, 59, tzinfo=UTC)
    late = await open_deck(deck_ids[1])
    clock[0] = datetime(2026, 11, 3, 0, 5, tzinfo=UTC)
    today = await complete(await open_deck(deck_ids[2]))
    assert today["streak"]["streak_days"] == 1
    joined = await complete(late)
    assert joined["streak"]["streak_days"] == 3
    assert joined["streak"]["max_streak_days"] == 3
    assert joined["streak"]["last_streak_date"] == "2026-11-03"


async def test_streak_waits_for_late_session_until_timeout(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [datetime(2026, 11, 1, 12, tzinfo=UTC)]
    monkeypatch.setattr(study_service, "now_utc", lambda: clock[0])
    decks = []
    for title in ("completed", "pending"):
        deck = await client.post(
            "/api/v1/decks", headers=HEADERS, json={"title": title}
        )
        deck_id = deck.json()["id"]
        await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            headers=HEADERS,
            json={"front": title, "back": "answer"},
        )
        decks.append(deck_id)
    first = (
        await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": decks[0]}
        )
    ).json()
    completed = await client.post(
        f"/api/v1/study/sessions/{first['session']['id']}/reviews",
        headers=HEADERS,
        json={
            "card_id": first["current_card_id"],
            "rating": 3,
            "answer_token": first["answer_token"],
        },
    )
    assert completed.json()["streak"]["streak_days"] == 1
    clock[0] = datetime(2026, 11, 2, 23, 59, tzinfo=UTC)
    late = (
        await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": decks[1]}
        )
    ).json()
    path = f"/api/v1/study/sessions/{late['session']['id']}"
    clock[0] = datetime(2026, 11, 3, 0, 5, tzinfo=UTC)
    assert (await client.get(path, headers=HEADERS)).json()["streak"][
        "streak_days"
    ] == 1
    clock[0] = datetime(2026, 11, 3, 0, 30, tzinfo=UTC)
    expired = await client.get(path, headers=HEADERS)
    assert expired.json()["session"]["status"] == "abandoned"
    assert expired.json()["streak"]["streak_days"] == 0
    assert expired.json()["streak"]["max_streak_days"] == 1


async def test_deleted_live_card_still_completes_from_snapshot(
    client: AsyncClient,
) -> None:
    deck_id = (
        await client.post("/api/v1/decks", headers=HEADERS, json={"title": "snapshots"})
    ).json()["id"]
    card = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        headers=HEADERS,
        json={"front": "original", "back": "answer"},
    )
    card_id = card.json()["id"]
    opened = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
    )
    state = opened.json()
    assert (
        await client.delete(f"/api/v1/decks/{deck_id}/cards/{card_id}", headers=HEADERS)
    ).status_code == 204
    response = await client.post(
        f"/api/v1/study/sessions/{state['session']['id']}/reviews",
        headers=HEADERS,
        json={"card_id": card_id, "rating": 3, "answer_token": state["answer_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["session"]["status"] == "completed"
    view = await client.get(
        f"/api/v1/study/sessions/{state['session']['id']}", headers=HEADERS
    )
    assert view.json()["cards"][0]["front"] == "original"


async def test_lost_membership_does_not_restore_old_progress(
    client: AsyncClient,
) -> None:
    deck_id = (
        await client.post("/api/v1/decks", headers=HEADERS, json={"title": "old cycle"})
    ).json()["id"]
    card = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        headers=HEADERS,
        json={"front": "question", "back": "answer"},
    )
    card_id = card.json()["id"]
    opened = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
    )
    state = opened.json()
    library = f"/api/v1/library/decks/{deck_id}"
    assert (await client.delete(library, headers=HEADERS)).status_code == 204
    assert (await client.put(library, headers=HEADERS)).status_code == 200
    result = await client.post(
        f"/api/v1/study/sessions/{state['session']['id']}/reviews",
        headers=HEADERS,
        json={"card_id": card_id, "rating": 3, "answer_token": state["answer_token"]},
    )
    assert result.status_code == 200, result.text
    assert result.json()["session"]["status"] == "completed"

    reopened = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
    )
    assert reopened.status_code == 201, reopened.text
    assert reopened.json()["current_card_id"] == card_id


async def test_concurrent_retries_change_progress_once(client: AsyncClient) -> None:
    deck_id = (
        await client.post("/api/v1/decks", headers=HEADERS, json={"title": "retry"})
    ).json()["id"]
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        headers=HEADERS,
        json={"front": "question", "back": "answer"},
    )
    state = (
        await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )
    ).json()
    path = f"/api/v1/study/sessions/{state['session']['id']}/reviews"
    payload = {
        "card_id": state["current_card_id"],
        "rating": 3,
        "answer_token": state["answer_token"],
    }
    responses = await asyncio.gather(
        *(client.post(path, headers=HEADERS, json=payload) for _ in range(5))
    )
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    assert responses[0].json()["quota"]["total_used"] == 1
    assert responses[0].json()["streak"]["streak_days"] == 1


@pytest.mark.parametrize("failure_stage", ["planner", "after_usage"])
async def test_review_failure_rolls_back_state_and_allows_retry(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    deck = await client.post(
        "/api/v1/decks", headers=HEADERS, json={"title": "Rollback review"}
    )
    deck_id = deck.json()["id"]
    card = await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        headers=HEADERS,
        json={"front": "question", "back": "answer"},
    )
    assert card.status_code == 201
    opened = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
    )
    assert opened.status_code == 201
    view = opened.json()
    session_path = f"/api/v1/study/sessions/{view['session']['id']}"
    payload = {
        "card_id": view["current_card_id"],
        "answer_token": view["answer_token"],
        "rating": 3,
    }

    def fail_next_card(*args, **kwargs):
        raise ValueError("simulated planner failure")

    original_usage = StudyRepository.record_usage

    async def fail_after_usage(self, user_id, deck_id, day, card_id, **kwargs):
        await original_usage(self, user_id, deck_id, day, card_id, **kwargs)
        counts = await self.usage_counts(user_id, deck_id, day)
        assert (counts.total_used, counts.new_used) == (1, 1)
        raise ValueError("simulated quota failure")

    with monkeypatch.context() as patch:
        if failure_stage == "planner":
            patch.setattr(StudyPlanner, "next_card", fail_next_card)
        else:
            patch.setattr(StudyRepository, "record_usage", fail_after_usage)
        with pytest.raises(ValueError, match="simulated .* failure"):
            await client.post(f"{session_path}/reviews", headers=HEADERS, json=payload)

    from sqlalchemy import func

    from application.activity.database.models import UserDailyActivity
    from application.study.database.models import (
        CardReview,
        LearningCycle,
        ReviewLog,
        StudyDailyCard,
        StudyDailyUsage,
    )

    helper = cast(ASGITransport, client._transport).app.state.database_helper
    async with helper.session_factory() as session:
        user_id = await session.scalar(select(User.id).where(User.vk_user_id == VK_ID))
        for model in (
            CardReview,
            LearningCycle,
            ReviewLog,
            UserDailyActivity,
            StudyDailyCard,
            StudyDailyUsage,
        ):
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.user_id == user_id)
                )
                == 0
            ), model.__name__

    restored = await client.get(session_path, headers=HEADERS)
    assert restored.status_code == 200
    assert restored.json() == view
    retry = await client.post(f"{session_path}/reviews", headers=HEADERS, json=payload)
    assert retry.status_code == 200
    assert retry.json()["session"]["status"] == "completed"
    assert retry.json()["quota"]["total_used"] == 1


async def test_review_sql_budget_skips_content_and_log_rewrite(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    deck_id = (
        await client.post(
            "/api/v1/decks", headers=HEADERS, json={"title": "SQL budget"}
        )
    ).json()["id"]
    for index in range(3):
        created = await client.post(
            f"/api/v1/decks/{deck_id}/cards",
            headers=HEADERS,
            json={
                "front": f"Question {index}",
                "back": "answer",
                "explanation": "x" * 4096,
            },
        )
        assert created.status_code == 201
    view = (
        await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )
    ).json()
    path = f"/api/v1/study/sessions/{view['session']['id']}/reviews"
    first = await client.post(
        path,
        headers=HEADERS,
        json={
            "card_id": view["current_card_id"],
            "answer_token": view["answer_token"],
            "rating": 4,
        },
    )
    assert first.status_code == 200
    state = first.json()
    original_cards = StudyRepository.review_cards
    queue_sizes: list[int] = []

    async def track_queue(self, session_id):
        from sqlalchemy import inspect

        cards = await original_cards(self, session_id)
        queue_sizes.append(len(cards))
        assert all("snapshot" in inspect(card).unloaded for card in cards)
        assert all(card.card_id != view["current_card_id"] for card in cards)
        return cards

    monkeypatch.setattr(StudyRepository, "review_cards", track_queue)
    engine = cast(
        ASGITransport, client._transport
    ).app.state.database_helper.engine.sync_engine
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = await client.post(
            path,
            headers=HEADERS,
            json={
                "card_id": state["current_card_id"],
                "answer_token": state["answer_token"],
                "rating": 1,
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    assert queue_sizes == [2]
    assert response.json()["quota"]["total_used"] == 2
    card_selects = [
        sql
        for sql in statements
        if sql.startswith("select") and "from study_session_cards" in sql
    ]
    assert len(card_selects) == 1
    assert "snapshot" not in card_selects[0]
    assert "completed_at is null" in card_selects[0]
    session_selects = [
        sql
        for sql in statements
        if sql.startswith("select") and "from study_sessions" in sql
    ]
    assert len(session_selects) == 2
    assert sum("for update" in sql for sql in session_selects) == 1
    assert sum(sql.startswith("insert into review_logs") for sql in statements) == 1
    assert not any(sql.startswith("update review_logs") for sql in statements)
    quota_selects = [
        sql
        for sql in statements
        if sql.startswith("select") and "from study_daily_usage" in sql
    ]
    assert len(quota_selects) == 1
    assert not any("distinct" in sql for sql in statements)


async def test_second_completion_of_day_skips_streak_history(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    from application.activity.database.repository import SQLAActivityRepository

    clock = datetime(2026, 11, 3, 12, tzinfo=UTC)
    monkeypatch.setattr(study_service, "now_utc", lambda: clock)
    results = []
    history = AsyncMock(side_effect=AssertionError("unchanged day reread history"))
    for index in range(2):
        deck_id = (
            await client.post(
                "/api/v1/decks",
                headers=HEADERS,
                json={"title": f"Same completed day {index}"},
            )
        ).json()["id"]
        assert (
            await client.post(
                f"/api/v1/decks/{deck_id}/cards",
                headers=HEADERS,
                json={"front": "question", "back": "answer"},
            )
        ).status_code == 201
        view = (
            await client.post(
                "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
            )
        ).json()
        if index == 1:
            monkeypatch.setattr(SQLAActivityRepository, "completed_days", history)
        result = await client.post(
            f"/api/v1/study/sessions/{view['session']['id']}/reviews",
            headers=HEADERS,
            json={
                "card_id": view["current_card_id"],
                "answer_token": view["answer_token"],
                "rating": 4,
            },
        )
        assert result.status_code == 200, result.text
        assert result.json()["session"]["status"] == "completed"
        results.append(result.json())
    history.assert_not_awaited()
    assert results[0]["streak"] == results[1]["streak"]
    assert results[1]["streak"]["streak_days"] == 1


async def test_expired_session_is_not_revived(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [datetime(2026, 11, 2, 23, 59, tzinfo=UTC)]
    monkeypatch.setattr(study_service, "now_utc", lambda: clock[0])
    deck_id = (
        await client.post("/api/v1/decks", headers=HEADERS, json={"title": "expiry"})
    ).json()["id"]
    await client.post(
        f"/api/v1/decks/{deck_id}/cards",
        headers=HEADERS,
        json={"front": "question", "back": "answer"},
    )
    state = (
        await client.post(
            "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
        )
    ).json()
    old_id = state["session"]["id"]
    clock[0] = datetime(2026, 11, 3, 0, 30, tzinfo=UTC)
    response = await client.post(
        f"/api/v1/study/sessions/{old_id}/reviews",
        headers=HEADERS,
        json={
            "card_id": state["current_card_id"],
            "rating": 3,
            "answer_token": state["answer_token"],
        },
    )
    assert response.status_code == 409
    expired = await client.get(f"/api/v1/study/sessions/{old_id}", headers=HEADERS)
    assert expired.json()["session"]["status"] == "abandoned"
    new = await client.post(
        "/api/v1/study/sessions", headers=HEADERS, json={"deck_id": deck_id}
    )
    assert new.status_code == 201
    assert new.json()["session"]["id"] != old_id
