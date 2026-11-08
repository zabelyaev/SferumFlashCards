import asyncio
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from application.accounts.database.sqla_uow import SQLAUnitOfWorkFactory
from application.accounts.users.contracts.inputs import UserSyncInput
from application.accounts.users.database.models import User
from application.accounts.users.service import UserService
from application.activity.service import StreakService
from application.flashcards.cards.contracts.inputs import CardCreateInput
from application.flashcards.cards.database.models import Card
from application.flashcards.cards.database.repository import SQLACardRepository
from application.flashcards.cards.service import CardService
from application.flashcards.database.sqla_uow import (
    SQLAFlashcardsUnitOfWork,
    SQLAFlashcardsUnitOfWorkFactory,
)
from application.flashcards.decks.contracts.inputs import DeckCreateInput
from application.flashcards.decks.database.models import Deck
from application.flashcards.decks.service import DeckService
from application.flashcards.library.database.models import UserDeck
from application.flashcards.library.database.repository import SQLALibraryRepository
from application.study.database.models import (
    CardReview,
    ReviewLog,
    StudySession,
    StudySessionCard,
)
from common.database import DatabaseHelper
from common.exceptions.not_found import NotFoundError
from main import create_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration
VK_IDS = (91800001, 91800002)


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


async def test_decks_cards_library_concurrency_and_history(helper, app_headers) -> None:
    app = create_app()
    app.state.database_helper = helper
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=app_headers
    ) as client:
        for vk in VK_IDS:
            assert (
                await client.post("/api/v1/users/sync", json={"vk_user_id": vk})
            ).status_code == 200
        owner = {"X-VK-User-ID": str(VK_IDS[0])}
        other = {"X-VK-User-ID": str(VK_IDS[1])}
        create = await client.post(
            "/api/v1/decks", headers=owner, json={"title": "Тест", "subject": "physics"}
        )
        assert create.status_code == 201, create.text
        deck = create.json()
        deck_id = deck["id"]
        assert isinstance(deck_id, int) and isinstance(deck["author_id"], int)
        path = f"/api/v1/decks/{deck_id}"
        library = f"/api/v1/library/decks/{deck_id}"
        assert (await client.get("/api/v1/library/decks", headers=owner)).json()[
            "items"
        ][0]["id"] == deck_id
        assert (await client.get(path, headers=other)).status_code == 403
        assert (await client.put(library, headers=other)).status_code == 403
        assert (await client.delete(path, headers=other)).status_code == 403
        assert (await client.delete(library, headers=owner)).status_code == 204
        assert (await client.delete(library, headers=owner)).status_code == 204
        first = await client.put(library, headers=owner)
        second = await client.put(library, headers=owner)
        assert first.status_code == 200 and first.json() == second.json()
        assert isinstance(first.json()["id"], int)
        assert (
            await client.post(
                path + "/cards", headers=other, json={"front": "x", "back": "y"}
            )
        ).status_code == 403
        cards = await asyncio.gather(
            *(
                client.post(
                    path + "/cards", headers=owner, json={"front": str(i), "back": "y"}
                )
                for i in range(8)
            )
        )
        assert all(r.status_code == 201 for r in cards), [r.text for r in cards]
        assert sorted(r.json()["order_index"] for r in cards) == list(range(8))
        assert (await client.get(path, headers=owner)).json()["cards_count"] == 8
        started = await client.post(
            "/api/v1/study/sessions", headers=owner, json={"deck_id": deck_id}
        )
        state = started.json()
        card_id = state["current_card_id"]
        cards.sort(key=lambda card: card.json()["id"] != card_id)
        assert isinstance(card_id, int)
        assert (
            await client.delete(path + f"/cards/{card_id}", headers=other)
        ).status_code == 403
        reviewed = await client.post(
            f"/api/v1/study/sessions/{state['session']['id']}/reviews",
            headers=owner,
            json={
                "card_id": card_id,
                "rating": 1,
                "answer_token": state["answer_token"],
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        async with helper.session_factory() as session:
            snapshot = await session.scalar(
                select(StudySessionCard).where(
                    StudySessionCard.session_id == state["session"]["id"],
                    StudySessionCard.card_id == card_id,
                )
            )
            log = await session.scalar(
                select(ReviewLog).where(
                    ReviewLog.session_id == state["session"]["id"],
                    ReviewLog.card_id == card_id,
                )
            )
            snapshot_id, session_id, log_id = (
                snapshot.id,
                state["session"]["id"],
                log.id,
            )
        assert (await client.delete(library, headers=owner)).status_code == 204
        async with helper.session_factory() as session:
            assert (await session.get(StudySessionCard, snapshot_id)).card_id == card_id
            assert (await session.get(ReviewLog, log_id)).card_id == card_id
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CardReview)
                    .where(CardReview.deck_id == deck_id)
                )
                == 0
            )
        assert (await client.put(library, headers=owner)).status_code == 200
        assert (
            await client.delete(path + f"/cards/{card_id}", headers=owner)
        ).status_code == 204
        assert (
            await client.delete(path + f"/cards/{card_id}", headers=owner)
        ).status_code == 404
        assert (await client.get(path, headers=owner)).json()["cards_count"] == 7
        new = await client.post(
            path + "/cards", headers=owner, json={"front": "z", "back": "a"}
        )
        assert (
            new.json()["order_index"]
            == max(card.json()["order_index"] for card in cards[1:]) + 1
        )
        assert (await client.get(path + "/cards", headers=owner)).status_code == 200
        deletes = await asyncio.gather(
            *(
                client.delete(path + f"/cards/{card.json()['id']}", headers=owner)
                for card in cards[1:5]
            )
        )
        assert all(response.status_code == 204 for response in deletes)
        assert (await client.get(path, headers=owner)).json()["cards_count"] == 4
        async with helper.session_factory() as session:
            snapshot = await session.get(StudySessionCard, snapshot_id)
            assert snapshot.source_card_id is None and snapshot.card_id == card_id
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CardReview)
                    .where(CardReview.deck_id == deck_id)
                )
                == 0
            )
        public = await client.post(
            "/api/v1/decks",
            headers=owner,
            json={"title": "public", "subject": "physics", "is_public": True},
        )
        public_id = public.json()["id"]
        assert (
            await client.delete(
                f"/api/v1/decks/{public_id}/cards/{cards[1].json()['id']}",
                headers=owner,
            )
        ).status_code == 404
        pub_library = f"/api/v1/library/decks/{public_id}"
        adds = await asyncio.gather(
            *(client.put(pub_library, headers=other) for _ in range(8))
        )
        assert all(r.status_code == 200 for r in adds)
        assert len({r.json()["id"] for r in adds}) == 1
        assert (
            await client.get(f"/api/v1/decks/{public_id}", headers=other)
        ).status_code == 200
        assert (await client.delete(pub_library, headers=other)).status_code == 204
        assert (
            await client.get(f"/api/v1/decks/{public_id}", headers=owner)
        ).status_code == 200
        assert (await client.delete(path, headers=owner)).status_code == 204
        assert (await client.get(path, headers=owner)).status_code == 404
        async with helper.session_factory() as session:
            assert (await session.get(StudySession, session_id)).deck_id is None
            assert (await session.get(StudySessionCard, snapshot_id)).card_id == card_id
            assert (await session.get(ReviewLog, log_id)).card_id == card_id
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Card)
                    .where(Card.deck_id == deck_id)
                )
                == 0
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(UserDeck)
                    .where(UserDeck.deck_id == deck_id)
                )
                == 0
            )


async def test_creation_rolls_back_when_library_insert_fails(
    helper, monkeypatch
) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))

    async def fail(self, *, user_id, deck_id):
        raise RuntimeError("simulated membership failure")

    monkeypatch.setattr(SQLALibraryRepository, "ensure_membership", fail)
    service = DeckService(SQLAFlashcardsUnitOfWorkFactory(helper.session_factory))
    with pytest.raises(RuntimeError, match="simulated membership failure"):
        await service.create(
            user.id, DeckCreateInput(title="rollback", subject="physics")
        )
    async with helper.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Deck).where(Deck.author_id == user.id)
            )
            == 0
        )


async def test_share_code_collision_is_retried_atomically(helper, monkeypatch) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))
    codes = iter(["samecode", "samecode", "new_code"])
    monkeypatch.setattr(
        "application.flashcards.decks.database.repository.generate_share_code",
        lambda: next(codes),
    )
    service = DeckService(SQLAFlashcardsUnitOfWorkFactory(helper.session_factory))
    first = await service.create(
        user.id, DeckCreateInput(title="first", subject="physics")
    )
    second = await service.create(
        user.id, DeckCreateInput(title="second", subject="physics")
    )
    assert first.share_code == "samecode"
    assert second.share_code == "new_code"
    async with helper.session_factory() as session:
        memberships = await session.scalar(
            select(func.count())
            .select_from(UserDeck)
            .where(UserDeck.user_id == user.id)
        )
        assert memberships == 2


async def test_exhausted_share_codes_leave_no_partial_deck(helper, monkeypatch) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))
    monkeypatch.setattr(
        "application.flashcards.decks.database.repository.generate_share_code",
        lambda: "samecode",
    )
    service = DeckService(SQLAFlashcardsUnitOfWorkFactory(helper.session_factory))
    await service.create(user.id, DeckCreateInput(title="first", subject="physics"))
    with pytest.raises(RuntimeError, match="unique deck share code"):
        await service.create(
            user.id, DeckCreateInput(title="second", subject="physics")
        )
    async with helper.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Deck).where(Deck.author_id == user.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(UserDeck)
                .where(UserDeck.user_id == user.id)
            )
            == 1
        )


async def test_failed_card_creation_rolls_back_card_and_counter(
    helper, monkeypatch
) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))
    factory = SQLAFlashcardsUnitOfWorkFactory(helper.session_factory)
    deck = await DeckService(factory).create(
        user.id, DeckCreateInput(title="rollback", subject="physics")
    )
    append = SQLACardRepository.append

    async def fail_after_insert(self, *, deck_id, data):
        await append(self, deck_id=deck_id, data=data)
        raise RuntimeError("simulated failure after card insert")

    monkeypatch.setattr(SQLACardRepository, "append", fail_after_insert)
    with pytest.raises(RuntimeError, match="simulated failure"):
        await CardService(factory).create(
            user.id, deck.id, CardCreateInput(front="question", back="answer")
        )

    async with helper.session_factory() as session:
        persisted = await session.get(Deck, deck.id)
        assert persisted.cards_count == 0
        assert (
            await session.scalar(
                select(func.count()).select_from(Card).where(Card.deck_id == deck.id)
            )
            == 0
        )


async def test_failure_after_flushing_card_and_counter_rolls_back_both(
    helper, monkeypatch
) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))
    factory = SQLAFlashcardsUnitOfWorkFactory(helper.session_factory)
    deck = await DeckService(factory).create(
        user.id, DeckCreateInput(title="rollback", subject="physics")
    )
    flush = SQLAFlashcardsUnitOfWork.flush

    async def fail_after_flush(self):
        await flush(self)
        raise RuntimeError("simulated failure after flush")

    monkeypatch.setattr(SQLAFlashcardsUnitOfWork, "flush", fail_after_flush)
    with pytest.raises(RuntimeError, match="after flush"):
        await CardService(factory).create(
            user.id, deck.id, CardCreateInput(front="question", back="answer")
        )

    async with helper.session_factory() as session:
        persisted = await session.get(Deck, deck.id)
        assert persisted.cards_count == 0
        assert (
            await session.scalar(
                select(func.count()).select_from(Card).where(Card.deck_id == deck.id)
            )
            == 0
        )


async def test_failure_before_delete_commit_restores_card_and_counter(
    helper, monkeypatch
) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))
    factory = SQLAFlashcardsUnitOfWorkFactory(helper.session_factory)
    deck = await DeckService(factory).create(
        user.id, DeckCreateInput(title="rollback", subject="physics")
    )
    card = await CardService(factory).create(
        user.id, deck.id, CardCreateInput(front="question", back="answer")
    )

    async def fail_before_commit(self):
        await self.flush()
        raise RuntimeError("simulated failure before commit")

    monkeypatch.setattr(SQLAFlashcardsUnitOfWork, "commit", fail_before_commit)
    with pytest.raises(RuntimeError, match="before commit"):
        await CardService(factory).delete(user.id, deck.id, card.id)

    async with helper.session_factory() as session:
        assert (await session.get(Deck, deck.id)).cards_count == 1
        assert (await session.get(Card, card.id)).deck_id == deck.id


async def test_access_membership_and_scoped_card_deletion(helper, app_headers) -> None:
    app = create_app()
    app.state.database_helper = helper
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=app_headers
    ) as client:
        for vk in VK_IDS:
            assert (
                await client.post("/api/v1/users/sync", json={"vk_user_id": vk})
            ).status_code == 200
        owner = {"X-VK-User-ID": str(VK_IDS[0])}
        other = {"X-VK-User-ID": str(VK_IDS[1])}
        response = await client.post(
            "/api/v1/decks",
            headers=owner,
            json={"title": "shared", "subject": "physics", "is_public": True},
        )
        assert response.status_code == 201
        deck_id = response.json()["id"]
        path = f"/api/v1/decks/{deck_id}"
        library = f"/api/v1/library/decks/{deck_id}"
        added = await client.put(library, headers=other)
        assert added.status_code == 200
        membership_id = added.json()["id"]
        created_at = added.json()["created_at"]
        async with helper.session_factory.begin() as session:
            membership = await session.get(UserDeck, membership_id)
            membership.is_favorite = True

        repeated = await client.put(library, headers=other)
        assert repeated.status_code == 200
        assert repeated.json()["id"] == membership_id
        assert repeated.json()["created_at"] == created_at
        assert repeated.json()["is_favorite"] is True
        assert (
            await client.post(
                path + "/cards", headers=other, json={"front": "q", "back": "a"}
            )
        ).status_code == 403

        async with helper.session_factory.begin() as session:
            deck = await session.get(Deck, deck_id)
            deck.is_public = False

        assert (await client.get(path, headers=other)).status_code == 200
        assert (await client.get(path + "/cards", headers=other)).status_code == 200
        assert (await client.put(library, headers=other)).json()["id"] == membership_id
        assert (await client.delete(library, headers=other)).status_code == 204
        assert (await client.delete(library, headers=other)).status_code == 204
        assert (await client.get(path, headers=other)).status_code == 403
        assert (await client.get(path + "/cards", headers=other)).status_code == 403
        assert (await client.put(library, headers=other)).status_code == 403

        assert (await client.delete(library, headers=owner)).status_code == 204
        assert (await client.get(path, headers=owner)).status_code == 200
        card = await client.post(
            path + "/cards", headers=owner, json={"front": "q", "back": "a"}
        )
        assert card.status_code == 201
        assert (await client.put(library, headers=owner)).status_code == 200

        other_deck = await client.post(
            "/api/v1/decks",
            headers=owner,
            json={"title": "other", "subject": "physics"},
        )
        assert other_deck.status_code == 201
        other_path = f"/api/v1/decks/{other_deck.json()['id']}"
        wrong_delete = await client.delete(
            other_path + f"/cards/{card.json()['id']}", headers=owner
        )
        assert wrong_delete.status_code == 404
        assert (await client.get(path, headers=owner)).json()["cards_count"] == 1
        assert (await client.get(other_path, headers=owner)).json()["cards_count"] == 0
        assert (await client.get(path + "/cards", headers=owner)).json()["items"][0][
            "id"
        ] == card.json()["id"]
        assert (
            await client.delete(
                "/api/v1/library/decks/9223372036854775807", headers=owner
            )
        ).status_code == 404


async def test_uow_shares_session_and_rolls_back_on_exception(helper) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))
    uow = SQLAFlashcardsUnitOfWorkFactory(helper.session_factory)()
    with pytest.raises(RuntimeError, match="rollback test"):
        async with uow:
            assert uow.decks._session is uow.cards._session is uow.library._session
            await uow.decks.create(
                author_id=user.id,
                data=DeckCreateInput(title="rollback", subject="physics"),
            )
            await uow.flush()
            raise RuntimeError("rollback test")
    with pytest.raises(RuntimeError, match="has not been entered"):
        await uow.flush()
    with pytest.raises(RuntimeError, match="has not been entered"):
        await uow.commit()
    async with helper.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(Deck).where(Deck.author_id == user.id)
            )
            == 0
        )


async def test_required_repository_gets_and_generated_defaults(helper) -> None:
    user = await UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), StreakService
    ).sync(UserSyncInput(vk_user_id=VK_IDS[0]))
    factory = SQLAFlashcardsUnitOfWorkFactory(helper.session_factory)
    async with factory() as uow:
        with pytest.raises(NotFoundError, match="Deck not found"):
            await uow.decks.get_by_id(2**63 - 1)
        with pytest.raises(NotFoundError, match="Card not found"):
            await uow.cards.get_by_id(2**63 - 1, deck_id=2**63 - 1)
        assert await uow.library.find_membership(user.id, 2**63 - 1) is None
        deck = await uow.decks.create(
            author_id=user.id, data=DeckCreateInput(title="defaults", subject="physics")
        )
        assert deck.id > 0
        assert deck.created_at is not None and deck.updated_at is not None
        assert deck.cards_count == 0
        membership = await uow.library.ensure_membership(
            user_id=user.id, deck_id=deck.id
        )
        assert membership.id > 0 and membership.created_at is not None
        await uow.decks.get_by_id(deck.id, for_update=True)
        card = await uow.cards.append(
            deck_id=deck.id, data=CardCreateInput(front="q", back="a")
        )
        assert (
            card.id > 0 and card.created_at is not None and card.updated_at is not None
        )
        assert (await uow.cards.get_by_id(card.id, deck_id=deck.id)).id == card.id
        deck_id = deck.id

    async with helper.session_factory() as session:
        assert await session.get(Deck, deck_id) is None
