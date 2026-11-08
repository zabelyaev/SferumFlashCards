import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fsrs.scheduler import DEFAULT_PARAMETERS
from sqlalchemy import delete, select, update

import application.models  # noqa: F401
from application.accounts.users.database.models import User
from application.study.database.models import (
    LearningCycle,
    ReviewLog,
    StudySession,
    StudySessionCard,
)
from application.study.optimization.repository import OptimizationRepository
from application.study.services.planner import StudyPlanner
from common.config.study import StudyConfig
from common.database import DatabaseHelper

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration
VK_ID = 97413829


@pytest_asyncio.fixture
async def optimization_user(
    validated_test_database,
) -> AsyncIterator[tuple[DatabaseHelper, int]]:
    helper = DatabaseHelper(validated_test_database)
    async with helper.session_factory.begin() as session:
        await session.execute(delete(User).where(User.vk_user_id == VK_ID))
        user = User(vk_user_id=VK_ID)
        session.add(user)
        await session.flush()
        user_id = user.id
    try:
        yield helper, user_id
    finally:
        async with helper.session_factory.begin() as session:
            await session.execute(delete(User).where(User.vk_user_id == VK_ID))
        await helper.dispose()


async def test_optimization_lock_allows_profile_updates(
    optimization_user,
) -> None:
    helper, user_id = optimization_user
    repo = OptimizationRepository(helper.engine)
    async with repo.user_lock(user_id) as lock:
        assert lock is not None
        async with repo.user_lock(user_id) as second:
            assert second is None

        async def update_profile() -> None:
            async with helper.session_factory.begin() as session:
                await session.execute(
                    update(User).where(User.id == user_id).values(first_name="Updated")
                )

        await asyncio.wait_for(update_profile(), timeout=2)

    async with repo.user_lock(user_id) as second:
        assert second is not None


async def test_parameter_publish_is_atomic_and_checks_previous_value(
    optimization_user,
) -> None:
    helper, user_id = optimization_user
    repo = OptimizationRepository(helper.engine)
    first = tuple(DEFAULT_PARAMETERS)
    second = list(first)
    second[0] *= 1.1
    async with repo.user_lock(user_id) as lock:
        assert lock is not None
        assert await repo.publish(
            lock, user_id=user_id, previous=None, parameters=first
        )
        assert not await repo.publish(
            lock, user_id=user_id, previous=None, parameters=tuple(second)
        )
        assert await repo.publish(
            lock, user_id=user_id, previous=first, parameters=tuple(second)
        )
    async with helper.session_factory() as session:
        value = await session.scalar(
            select(User.fsrs_parameters).where(User.id == user_id)
        )
        assert value == second


async def seed_reviews(session, *, user_id, cycle_id, snapshot, now, count=1) -> None:
    study = StudySession(
        user_id=user_id,
        deck_id=None,
        historical_deck_id=1,
        timezone="UTC",
        study_date=now.date(),
        status="completed",
        total_cards=1,
        completed_cards=1,
        daily_total_cards_limit=125,
        daily_new_cards_limit=12,
        scheduler_config=snapshot,
        started_at=now,
        last_activity_at=now,
        day_end_at=now,
        expires_at=now,
        finished_at=now,
    )
    session.add(study)
    await session.flush()
    session.add(
        StudySessionCard(
            session_id=study.id,
            card_id=1,
            source_card_id=None,
            snapshot={"id": 1},
            order_index=0,
            fsrs_state={},
            cycle_id=cycle_id,
            was_new=True,
        )
    )
    await session.flush()
    session.add_all(
        ReviewLog(
            user_id=user_id,
            card_id=1,
            deck_id=1,
            session_id=study.id,
            cycle_id=cycle_id,
            study_date=now.date(),
            answer_token=f"optimization-{study.id}-{index}",
            rating=3,
            was_new=index == 0,
            result={},
            reviewed_at=now + timedelta(seconds=index),
        )
        for index in range(count)
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("library_version",), "0.0.0"),
        (("library_version",), None),
        (("scheduler", "learning_steps"), [60, 600]),
        (("scheduler", "relearning_steps"), [60]),
        ((), None),
        ((), {}),
        ((), []),
        ((), "invalid snapshot"),
        ((), 42),
        (("scheduler",), {}),
        (("scheduler",), None),
        (("scheduler",), []),
        (("scheduler",), "invalid scheduler"),
        (("scheduler", "learning_steps"), None),
        (("scheduler", "learning_steps"), 60),
        (("scheduler", "learning_steps"), ["60"]),
        (("scheduler", "relearning_steps"), None),
        (("scheduler", "relearning_steps"), {"0": 600}),
    ],
)
async def test_history_excludes_entire_cycle_with_incompatible_scheduler(
    optimization_user, path, value
) -> None:
    helper, user_id = optimization_user
    config = StudyConfig()
    planner = StudyPlanner(config)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with helper.session_factory.begin() as session:
        cycles = [
            LearningCycle(user_id=user_id, card_id=1, deck_id=1, created_at=now)
            for _ in range(2)
        ]
        session.add_all(cycles)
        await session.flush()
        invalid = planner.config_snapshot()
        if not path:
            invalid = value
        elif len(path) == 1:
            invalid[path[0]] = value
        else:
            invalid[path[0]][path[1]] = value

        for index, (cycle, snapshot) in enumerate(
            [
                (cycles[0], planner.config_snapshot()),
                (cycles[1], planner.config_snapshot()),
                (cycles[1], invalid),
                (cycles[1], planner.config_snapshot()),
            ]
        ):
            await seed_reviews(
                session,
                user_id=user_id,
                cycle_id=cycle.id,
                snapshot=snapshot,
                now=now + timedelta(days=index),
            )
        ids = [cycle.id for cycle in cycles]
    repo = OptimizationRepository(helper.engine)
    async with repo.user_lock(user_id) as lock:
        assert lock is not None
        history = await repo.history(lock, user_id, config)
        assert not lock.connection.in_transaction()
    assert history is not None
    assert history.incompatible_cycles == 1
    assert [review.cycle_id for review in history.reviews] == [ids[0]]


async def test_eligible_users_threshold_filters_keyset_and_limit(
    optimization_user,
) -> None:
    helper, user_id = optimization_user
    repo = OptimizationRepository(helper.engine)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    snapshot = StudyPlanner(StudyConfig()).config_snapshot()
    additional_ids = []
    try:
        async with helper.session_factory.begin() as session:
            others = [
                User(vk_user_id=VK_ID + offset, is_active=offset != 2)
                for offset in range(1, 4)
            ]
            session.add_all(others)
            await session.flush()
            additional_ids = [user.id for user in others]
            ids = [user_id, *additional_ids]
            cycles = [
                LearningCycle(user_id=owner, card_id=1, deck_id=1, created_at=now)
                for owner in ids
            ]
            session.add_all(cycles)
            await session.flush()
            cycle_ids = [cycle.id for cycle in cycles]
            for owner, cycle_id, count in zip(ids, cycle_ids, [513, 514, 600, 1000]):
                await seed_reviews(
                    session,
                    user_id=owner,
                    cycle_id=cycle_id,
                    snapshot=snapshot,
                    now=now,
                    count=count,
                )

            await seed_reviews(
                session,
                user_id=user_id,
                cycle_id=None,
                snapshot=snapshot,
                now=now,
                count=20,
            )
        first, disabled, last = additional_ids
        assert await repo.eligible_users(after_id=user_id - 1, limit=1) == [first]
        assert await repo.eligible_users(after_id=user_id - 1, limit=10) == [
            first,
            last,
        ]
        assert await repo.eligible_users(after_id=first, limit=1) == [last]
        assert await repo.eligible_users(after_id=disabled, limit=10) == [last]
        assert await repo.eligible_users(after_id=last, limit=10) == []
        assert await repo.eligible_users(after_id=user_id - 1, limit=0) == []
        async with helper.session_factory.begin() as session:
            await seed_reviews(
                session,
                user_id=user_id,
                cycle_id=cycle_ids[0],
                snapshot=snapshot,
                now=now,
            )
        assert await repo.eligible_users(after_id=user_id - 1, limit=10) == [
            user_id,
            first,
            last,
        ]
    finally:
        async with helper.session_factory.begin() as session:
            await session.execute(delete(User).where(User.id.in_(additional_ids)))
