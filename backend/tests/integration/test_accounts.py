import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, func, select

from application.accounts.database.sqla_uow import SQLAUnitOfWorkFactory
from application.accounts.users.contracts.inputs import (
    UserProfileUpdateInput,
    UserSettingsReplaceInput,
    UserSyncInput,
)
from application.accounts.users.database.models import User
from application.accounts.users.service import UserService
from application.activity.database.models import UserDailyActivity
from application.activity.database.repository import SQLAActivityRepository
from application.activity.service import StreakService
from application.flashcards.cards.database.models import Card
from application.flashcards.decks.database.models import Deck
from application.flashcards.library.database.models import UserDeck
from application.shared.enums import Subject
from application.study.database.models import CardReview, LearningCycle
from application.study.database.sqla_uow import SQLAStudyUnitOfWork
from application.study.services.planner import StudyPlanner
from common.config import settings
from common.database import DatabaseHelper
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.unauthorized import UnauthorizedError
from main import main_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration
VK_IDS = tuple(range(90000001, 90000007))


@pytest_asyncio.fixture
async def helper(validated_test_database) -> AsyncIterator[DatabaseHelper]:
    helper = DatabaseHelper(validated_test_database)

    async def cleanup() -> None:
        async with helper.session_factory.begin() as session:
            user_ids = select(User.id).where(User.vk_user_id.in_(VK_IDS))
            await session.execute(delete(Deck).where(Deck.author_id.in_(user_ids)))
            await session.execute(delete(User).where(User.vk_user_id.in_(VK_IDS)))

    try:
        await cleanup()
        yield helper
    finally:
        await cleanup()
        await helper.dispose()


async def test_repeated_sync_preserves_profile_settings_and_progress(helper) -> None:
    factory = SQLAUnitOfWorkFactory(helper.session_factory)
    users = UserService(factory, streak_factory=StreakService)
    profile = await users.sync(
        UserSyncInput(
            vk_user_id=90000001,
            first_name="Иван",
            last_name="Иванов",
            timezone="Europe/Moscow",
            avatar_url="https://example.com/avatar.jpg",
        )
    )
    await users.update(profile.id, UserProfileUpdateInput(first_name="Анна"))
    async with helper.session_factory.begin() as session:
        user = await session.get(User, profile.id)
        user.daily_new_cards_limit = 5
        user.settings["sound_enabled"] = False
        user.streak_days = 3
        user.max_streak_days = 5
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        session.add_all(
            UserDailyActivity(
                user_id=user.id, activity_date=today - timedelta(days=i), completed=True
            )
            for i in range(3)
        )
        deck = Deck(author_id=user.id, title="Повторный вход", subject=Subject.PHYSICS)
        session.add(deck)
        await session.flush()
        card = Card(deck_id=deck.id, front="Вопрос", back="Ответ")
        session.add(card)
        membership = UserDeck(user_id=user.id, deck_id=deck.id)
        session.add(membership)
        await session.flush()
        now = datetime.now(UTC)
        cycle = LearningCycle(
            user_id=user.id,
            card_id=card.id,
            deck_id=deck.id,
            membership_id=membership.id,
            created_at=now,
        )
        session.add(cycle)
        await session.flush()
        planner = StudyPlanner(settings.study)
        state = planner.review(
            planner.new_card(card.id, now), 3, now, planner.config_snapshot()
        )
        review = CardReview(
            user_id=user.id,
            deck_id=deck.id,
            card_id=card.id,
            cycle_id=cycle.id,
            fsrs_state=state.fsrs_state,
            due_date=state.due_date,
            last_reviewed=now,
        )
        session.add(review)
        await session.flush()
        review_id = review.id

    again = await users.sync(UserSyncInput(vk_user_id=90000001))
    assert again.id == profile.id
    assert again.first_name == "Анна"
    assert again.last_name == "Иванов"
    assert again.timezone == "Europe/Moscow"
    assert str(again.avatar_url) == "https://example.com/avatar.jpg"
    assert again.daily_new_cards_limit == 5
    assert again.settings["sound_enabled"] is False
    assert again.streak_days == 3
    async with helper.session_factory() as session:
        assert (await session.get(CardReview, review_id)).fsrs_state == state.fsrs_state

    updated = await users.sync(
        UserSyncInput(vk_user_id=90000001, last_name="Петрова", avatar_url=None)
    )
    assert updated.first_name == "Анна"
    assert updated.last_name == "Петрова"
    assert updated.avatar_url is None
    assert updated.settings["sound_enabled"] is False
    async with helper.session_factory() as session:
        assert (await session.get(CardReview, review_id)).fsrs_state == state.fsrs_state


@pytest.mark.parametrize("with_profile", [False, True])
async def test_concurrent_first_sync_creates_exactly_one_user(
    helper, with_profile: bool
) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profiles = await asyncio.gather(
        *(
            users.sync(
                UserSyncInput(vk_user_id=90000002, first_name=f"Имя {index}")
                if with_profile
                else UserSyncInput(vk_user_id=90000002)
            )
            for index in range(8)
        )
    )
    assert len({profile.id for profile in profiles}) == 1
    async with helper.session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.vk_user_id == 90000002)
            )
            == 1
        )


async def test_study_uow_shares_transaction_with_user_and_activity(helper) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profile = await users.sync(UserSyncInput(vk_user_id=90000001, first_name="Before"))
    now = datetime.now(UTC)
    with pytest.raises(RuntimeError, match="abort"):
        async with SQLAStudyUnitOfWork(helper.session_factory) as uow:
            user = await uow.users.get_by_id(profile.id, no_key_update=True)
            user.first_name = "After"
            await uow.activity.record_activity(user.id, now.date(), completed=False)
            uow.repo.add(
                LearningCycle(
                    user_id=user.id,
                    card_id=1,
                    deck_id=1,
                    membership_id=None,
                    created_at=now,
                )
            )
            await uow.flush()
            assert (
                await uow.session.scalar(
                    select(User.first_name).where(User.id == profile.id)
                )
                == "After"
            )
            assert (
                await uow.session.scalar(
                    select(func.count())
                    .select_from(UserDailyActivity)
                    .where(UserDailyActivity.user_id == profile.id)
                )
                == 1
            )
            assert (
                await uow.session.scalar(
                    select(func.count())
                    .select_from(LearningCycle)
                    .where(LearningCycle.user_id == profile.id)
                )
                == 1
            )
            raise RuntimeError("abort")
    async with helper.session_factory() as session:
        assert (await session.get(User, profile.id)).first_name == "Before"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(UserDailyActivity)
                .where(UserDailyActivity.user_id == profile.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LearningCycle)
                .where(LearningCycle.user_id == profile.id)
            )
            == 0
        )


@pytest.mark.parametrize("operation", ["profile", "sync", "update", "settings"])
async def test_user_operations_refresh_stale_streak(helper, operation: str) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profile = await users.sync(UserSyncInput(vk_user_id=90000001))
    old_day = datetime.now(UTC).date() - timedelta(days=2)
    async with helper.session_factory.begin() as session:
        user = await session.get(User, profile.id)
        user.streak_days, user.max_streak_days, user.last_streak_date = 1, 5, old_day
        session.add(
            UserDailyActivity(user_id=user.id, activity_date=old_day, completed=True)
        )

    current = await users.get_current(90000001)
    assert current.model_dump() == {"id": profile.id, "is_active": True}
    async with helper.session_factory() as session:
        assert (await session.get(User, profile.id)).streak_days == 1
    if operation == "profile":
        result = await users.get_profile(profile.id)
    elif operation == "sync":
        result = await users.sync(UserSyncInput(vk_user_id=90000001))
    elif operation == "update":
        result = await users.update(
            profile.id, UserProfileUpdateInput(first_name="Анна")
        )
    else:
        result = await users.replace_settings(
            profile.id, UserSettingsReplaceInput(settings={"theme": "dark"})
        )
    assert (result.streak_days, result.max_streak_days, result.last_streak_date) == (
        0,
        5,
        old_day,
    )
    async with helper.session_factory() as session:
        user = await session.get(User, profile.id)
        assert user.streak_days == 0


@pytest.mark.parametrize("operation", ["update", "settings"])
async def test_profile_mutation_rolls_back_if_streak_refresh_fails(
    helper, monkeypatch, operation: str
) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profile = await users.sync(UserSyncInput(vk_user_id=90000001, first_name="Before"))
    async with helper.session_factory.begin() as session:
        user = await session.get(User, profile.id)
        user.streak_days = 1
        user.max_streak_days = 1
        user.last_streak_date = datetime.now(UTC).date() - timedelta(days=2)

    async def fail(*args, **kwargs):
        raise RuntimeError("activity lookup failed")

    monkeypatch.setattr(SQLAActivityRepository, "pending_days", fail)
    with pytest.raises(RuntimeError, match="activity lookup failed"):
        if operation == "update":
            await users.update(profile.id, UserProfileUpdateInput(first_name="After"))
        else:
            await users.replace_settings(
                profile.id, UserSettingsReplaceInput(settings={"theme": "dark"})
            )
    async with helper.session_factory() as session:
        user = await session.get(User, profile.id)
        assert user.first_name == "Before"
        assert user.settings == {}


@pytest.mark.parametrize("operation", ["profile", "update", "settings", "timezone"])
async def test_streak_and_profile_flush_in_one_update_before_mapping(
    helper, operation: str
) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profile = await users.sync(UserSyncInput(vk_user_id=90000001))
    old_day = datetime.now(UTC).date() - timedelta(days=3)
    previous_timestamp = datetime.now(UTC) - timedelta(days=1)
    async with helper.session_factory.begin() as session:
        user = await session.get(User, profile.id)
        user.streak_days, user.max_streak_days, user.last_streak_date = 1, 5, old_day
        user.updated_at = previous_timestamp
        session.add(
            UserDailyActivity(user_id=user.id, activity_date=old_day, completed=True)
        )
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(helper.engine.sync_engine, "before_cursor_execute", capture)
    try:
        if operation == "profile":
            result = await users.get_profile(profile.id)
        elif operation == "update":
            result = await users.update(
                profile.id, UserProfileUpdateInput(first_name="After")
            )
        elif operation == "settings":
            result = await users.replace_settings(
                profile.id, UserSettingsReplaceInput(settings={"theme": "dark"})
            )
        else:
            result = await users.update(
                profile.id, UserProfileUpdateInput(timezone="Europe/Moscow")
            )
    finally:
        event.remove(helper.engine.sync_engine, "before_cursor_execute", capture)
    updates = [sql for sql in statements if sql.startswith("UPDATE users SET")]
    assert len(updates) == 1
    assert "streak_days=" in updates[0]
    assert "FOR NO KEY UPDATE OF users" in statements[0]
    assert (result.streak_days, result.max_streak_days, result.last_streak_date) == (
        0,
        5,
        old_day,
    )
    assert result.updated_at > previous_timestamp
    async with helper.session_factory() as session:
        user = await session.get(User, profile.id)
        assert user.streak_days == 0
        assert result.updated_at == user.updated_at
        assert result.first_name == user.first_name
        assert result.settings == user.settings
        assert result.timezone == user.timezone


async def test_repeated_empty_sync_uses_locked_read_without_user_writes(helper) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profile = await users.sync(UserSyncInput(vk_user_id=90000001))
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(helper.engine.sync_engine, "before_cursor_execute", capture)
    try:
        for _ in range(2):
            again = await users.sync(UserSyncInput(vk_user_id=90000001))
            assert again == profile
    finally:
        event.remove(helper.engine.sync_engine, "before_cursor_execute", capture)
    assert len(statements) == 2
    assert all(sql.startswith("SELECT ") for sql in statements)
    assert all("FOR NO KEY UPDATE OF users" in sql for sql in statements)


@pytest.mark.parametrize("operation", ["update", "settings"])
async def test_profile_mutation_rolls_back_after_flush_if_mapping_fails(
    helper, monkeypatch, operation: str
) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profile = await users.sync(UserSyncInput(vk_user_id=90000001, first_name="Before"))

    def fail(user):
        raise RuntimeError("mapping failed")

    monkeypatch.setattr(
        "application.accounts.users.service.to_user_profile_output", fail
    )
    with pytest.raises(RuntimeError, match="mapping failed"):
        if operation == "update":
            await users.update(profile.id, UserProfileUpdateInput(first_name="After"))
        else:
            await users.replace_settings(
                profile.id, UserSettingsReplaceInput(settings={"theme": "dark"})
            )
    async with helper.session_factory() as session:
        user = await session.get(User, profile.id)
        assert user.first_name == "Before"
        assert user.settings == {}
        assert user.updated_at == profile.updated_at


async def test_reset_is_persisted_and_following_profile_skips_activity(
    helper, monkeypatch
) -> None:
    users = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    profile = await users.sync(UserSyncInput(vk_user_id=90000001))
    old_day = datetime.now(UTC).date() - timedelta(days=2)
    async with helper.session_factory.begin() as session:
        user = await session.get(User, profile.id)
        user.streak_days, user.max_streak_days, user.last_streak_date = 1, 5, old_day
        session.add(
            UserDailyActivity(user_id=user.id, activity_date=old_day, completed=True)
        )
    assert (await users.get_profile(profile.id)).streak_days == 0

    async def fail(*args, **kwargs):
        raise AssertionError("activity must not be queried after reset")

    monkeypatch.setattr(SQLAActivityRepository, "completed_days", fail)
    monkeypatch.setattr(SQLAActivityRepository, "pending_days", fail)
    result = await users.get_profile(profile.id)
    assert (result.streak_days, result.max_streak_days, result.last_streak_date) == (
        0,
        5,
        old_day,
    )


async def test_lookup_does_not_create_unknown_users(helper) -> None:
    service = UserService(
        SQLAUnitOfWorkFactory(helper.session_factory), streak_factory=StreakService
    )
    with pytest.raises(UnauthorizedError):
        await service.get_current(90000003)
    async with helper.session_factory() as session:
        assert (
            await session.scalar(select(User.id).where(User.vk_user_id == 90000003))
            is None
        )


async def test_disabled_sync_does_not_update_profile(helper) -> None:
    factory = SQLAUnitOfWorkFactory(helper.session_factory)
    users = UserService(factory, streak_factory=StreakService)
    profile = await users.sync(UserSyncInput(vk_user_id=90000004, first_name="Иван"))
    async with helper.session_factory.begin() as session:
        user = await session.get(User, profile.id)
        user.is_active = False
    with pytest.raises(ForbiddenError):
        await users.sync(UserSyncInput(vk_user_id=90000004, first_name="Другое имя"))
    with pytest.raises(ForbiddenError):
        await users.sync(UserSyncInput(vk_user_id=90000004))
    with pytest.raises(ForbiddenError):
        await UserService(factory, streak_factory=StreakService).get_current(90000004)
    async with helper.session_factory() as session:
        assert (await session.get(User, profile.id)).first_name == "Иван"


async def test_update_clear_avatar_and_delete_profile(helper) -> None:
    factory = SQLAUnitOfWorkFactory(helper.session_factory)
    users = UserService(factory, streak_factory=StreakService)
    profile = await users.sync(
        UserSyncInput(vk_user_id=90000005, avatar_url="https://example.com/avatar.jpg")
    )
    updated = await users.update(
        profile.id, UserProfileUpdateInput(first_name="  Анна  ", avatar_url=None)
    )
    assert updated.first_name == "Анна"
    assert updated.avatar_url is None
    persisted = await users.get_profile(profile.id)
    assert persisted.avatar_url is None
    await users.delete(profile.id)
    with pytest.raises(UnauthorizedError):
        await users.get_current(90000005)


async def test_http_sync_profile_without_tokens_or_rsa(helper, app_headers) -> None:
    async with main_app.router.lifespan_context(main_app):
        assert not hasattr(main_app.state, "jwt_service")
        async with AsyncClient(
            transport=ASGITransport(app=main_app), base_url="http://test"
        ) as client:
            path = "/api/v1/users/me/profile"
            profile_headers = {**app_headers, "X-VK-User-ID": "90000006"}
            assert (await client.get(path, headers=profile_headers)).status_code == 401
            string_id = await client.post(
                "/api/v1/users/sync",
                headers=app_headers,
                json={"vk_user_id": "90000006"},
            )
            assert string_id.status_code == 200
            assert string_id.json()["vk_user_id"] == 90000006
            assert type(string_id.json()["vk_user_id"]) is int
            assert (await client.get(path, headers=profile_headers)).status_code == 200
            response = await client.post(
                "/api/v1/users/sync",
                headers=app_headers,
                json={
                    "vk_user_id": 90000006,
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "avatar_url": "https://example.com/avatar.jpg",
                },
            )
            assert response.status_code == 200
            assert response.json()["vk_user_id"] == 90000006
            assert "access_token" not in response.json()
            response = await client.post(
                "/api/v1/users/sync",
                headers=app_headers,
                json={
                    "vk_user_id": 90000006,
                    "first_name": "Анна",
                    "avatar_url": None,
                },
            )
            assert response.status_code == 200
            assert response.json()["first_name"] == "Анна"
            assert response.json()["last_name"] == "Иванов"
            assert response.json()["avatar_url"] is None
            assert (
                await client.post(
                    "/api/v1/auth/login",
                    headers=app_headers,
                    json={"vk_user_id": 90000006},
                )
            ).status_code == 404
            assert (await client.get(path, headers=profile_headers)).status_code == 200
            patched = await client.patch(
                path, headers=profile_headers, json={"first_name": "Анна"}
            )
            assert patched.status_code == 200
            assert patched.json()["first_name"] == "Анна"
            assert (
                await client.delete(path, headers=profile_headers)
            ).status_code == 405
