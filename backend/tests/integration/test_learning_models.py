from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, func, inspect, select, update
from sqlalchemy.exc import IntegrityError

import application.models  # noqa: F401
from application.accounts.users.contracts.outputs import UserProfileOutput
from application.accounts.users.database.models import User
from application.activity.contracts.outputs import UserDailyActivityOutput
from application.activity.database.models import UserDailyActivity
from application.flashcards.cards.contracts.outputs import CardOutput
from application.flashcards.cards.database.models import Card
from application.flashcards.decks.contracts.outputs import DeckOutput
from application.flashcards.decks.database.models import Deck
from application.flashcards.library.contracts.outputs import UserDeckOutput
from application.flashcards.library.database.models import UserDeck
from application.shared.enums import StudySessionStatus, Subject
from application.study.contracts.mappers import to_study_session_output
from application.study.contracts.outputs import (
    ReviewLogOutput,
    ReviewResultOutput,
    StudySessionCardOutput,
)
from application.study.database.models import (
    CardReview,
    LearningCycle,
    ReviewLog,
    StudySession,
    StudySessionCard,
)
from application.study.services.planner import StudyPlanner
from common.config import settings
from common.database import Base, DatabaseHelper

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def db_session(validated_test_database) -> AsyncIterator[AsyncSession]:
    helper = DatabaseHelper(validated_test_database)
    try:
        async with helper.session_factory() as session:
            await session.begin()
            try:
                yield session
            finally:
                await session.rollback()
    finally:
        await helper.dispose()


async def create_learning_graph(
    session: AsyncSession, vk_user_id: int = 3_000_000_000
) -> tuple[User, Deck, Card, CardReview, StudySession]:
    user = User(vk_user_id=vk_user_id, first_name="Иван", timezone="Europe/Moscow")
    deck = Deck(author=user, title="Кинематика", subject=Subject.PHYSICS, grade=9)
    card = Card(deck=deck, front="Скорость", back=r"$v = \frac{s}{t}$")
    session.add_all([user, deck, card])
    await session.flush()
    membership = UserDeck(user_id=user.id, deck_id=deck.id)
    session.add(membership)
    await session.flush()
    now = datetime.now(UTC)
    planner = StudyPlanner(settings.study)
    state = planner.review(
        planner.new_card(card.id, now), 3, now, planner.config_snapshot()
    )
    cycle = LearningCycle(
        user_id=user.id,
        card_id=card.id,
        deck_id=deck.id,
        membership_id=membership.id,
        created_at=now,
    )
    session.add(cycle)
    await session.flush()
    review = CardReview(
        user_id=user.id,
        card_id=card.id,
        deck_id=deck.id,
        cycle_id=cycle.id,
        fsrs_state=state.fsrs_state,
        due_date=state.due_date,
        last_reviewed=now,
    )
    study = StudySession(
        user_id=user.id,
        deck_id=deck.id,
        historical_deck_id=deck.id,
        membership_id=membership.id,
        timezone=user.timezone,
        study_date=now.date(),
        status="active",
        total_cards=1,
        completed_cards=0,
        daily_total_cards_limit=125,
        daily_new_cards_limit=12,
        scheduler_config=planner.config_snapshot(),
        started_at=now,
        last_activity_at=now,
        day_end_at=now + timedelta(days=1),
        expires_at=now + timedelta(days=1),
    )
    session.add_all([review, study])
    await session.flush()
    session.add(
        StudySessionCard(
            session_id=study.id,
            card_id=card.id,
            source_card_id=card.id,
            snapshot=CardOutput.model_validate(card).model_dump(mode="json"),
            order_index=0,
            fsrs_state=state.fsrs_state,
            cycle_id=cycle.id,
            was_new=True,
        )
    )
    await session.flush()
    return user, deck, card, review, study


def make_log(
    user: User, card: Card, review: CardReview, study: StudySession
) -> ReviewLog:
    result = ReviewResultOutput.model_validate(
        {
            "session": to_study_session_output(study),
            "current_card_id": card.id,
            "answer_token": "next",
            "quota": {
                "total_used": 1,
                "new_used": 1,
                "total_remaining": 124,
                "new_remaining": 11,
            },
            "streak": {
                "streak_days": 0,
                "max_streak_days": 0,
                "last_streak_date": None,
            },
        }
    )
    return ReviewLog(
        user_id=user.id,
        card_id=card.id,
        session_id=study.id,
        answer_token="review-123",
        deck_id=study.historical_deck_id,
        study_date=study.study_date,
        cycle_id=review.cycle_id,
        reviewed_at=datetime.now(UTC),
        rating=3,
        was_new=True,
        result=result.model_dump(mode="json"),
    )


async def test_database_uses_bigint_identity_for_all_models(
    db_session: AsyncSession,
) -> None:
    connection = await db_session.connection()

    def check_columns(sync_connection: Connection) -> None:
        inspector = inspect(sync_connection)
        for table_name in Base.metadata.tables:
            columns = inspector.get_columns(table_name)
            for column in columns:
                if column["name"] == "id" or column["name"].endswith("_id"):
                    assert isinstance(column["type"], BigInteger), (table_name, column)
                if column["name"] == "id":
                    assert column.get("identity") is not None, table_name

    await connection.run_sync(check_columns)
    user = User(id=2**31 + 1, vk_user_id=3_000_000_001, first_name="Анна")
    db_session.add(user)
    await db_session.flush()
    assert user.id > 2**31


async def test_models_round_trip_to_pydantic_without_lazy_queries(
    db_session: AsyncSession,
) -> None:
    user, deck, card, review, study = await create_learning_graph(db_session)
    activity = UserDailyActivity(
        user_id=user.id, activity_date=date(2026, 10, 22), cards_reviewed=1
    )
    log = make_log(user, card, review, study)
    db_session.add_all([activity, log])
    await db_session.flush()
    membership = await db_session.scalar(
        select(UserDeck).where(UserDeck.user_id == user.id)
    )
    item = await db_session.scalar(
        select(StudySessionCard).where(StudySessionCard.session_id == study.id)
    )

    assert UserProfileOutput.model_validate(user).settings == {}
    assert DeckOutput.model_validate(deck).subject == Subject.PHYSICS
    assert CardOutput.model_validate(card).back == r"$v = \frac{s}{t}$"
    assert UserDeckOutput.model_validate(membership).deck_id == deck.id
    assert UserDailyActivityOutput.model_validate(activity).cards_reviewed == 1
    assert StudySessionCardOutput.model_validate(item).was_new is True
    assert ReviewLogOutput.model_validate(log).result.session.id == study.id
    assert user.vk_user_id == 3_000_000_000

    deck.title = "Обновлённая колода"
    user.settings["sound_enabled"] = False
    await db_session.flush()
    assert DeckOutput.model_validate(deck).title == "Обновлённая колода"
    assert UserProfileOutput.model_validate(user).settings["sound_enabled"] is False
    await db_session.refresh(deck)
    await db_session.refresh(user, attribute_names=["settings"])
    assert deck.title == "Обновлённая колода"
    assert user.settings["sound_enabled"] is False


@pytest.mark.parametrize("legacy", [False, True])
async def test_database_accepts_numeric_and_legacy_string_snapshot_ids(
    db_session: AsyncSession, legacy: bool
) -> None:
    _, _, card, _, study = await create_learning_graph(db_session)
    item = await db_session.scalar(
        select(StudySessionCard).where(StudySessionCard.session_id == study.id)
    )
    assert item is not None
    snapshot = dict(item.snapshot)
    snapshot["id"] = str(card.id) if legacy else card.id
    snapshot["deck_id"] = str(card.deck_id) if legacy else card.deck_id
    item.snapshot = snapshot
    await db_session.flush()
    await db_session.refresh(item)
    output = StudySessionCardOutput.model_validate(item).model_dump(mode="json")
    assert output["snapshot"]["id"] == card.id
    assert output["snapshot"]["deck_id"] == card.deck_id
    assert isinstance(item.snapshot["id"], str if legacy else int)


async def test_library_removal_cascades_only_the_users_progress(
    db_session: AsyncSession,
) -> None:
    user, deck, card, review, _ = await create_learning_graph(db_session)
    other = User(vk_user_id=3_000_000_002, first_name="Анна")
    db_session.add(other)
    await db_session.flush()
    db_session.add(UserDeck(user_id=other.id, deck_id=deck.id))
    await db_session.flush()
    other_review = CardReview(
        user_id=other.id,
        card_id=card.id,
        deck_id=deck.id,
        cycle_id=review.cycle_id,
        fsrs_state=review.fsrs_state,
        due_date=review.due_date,
        last_reviewed=review.last_reviewed,
    )
    db_session.add(other_review)
    await db_session.flush()

    membership = await db_session.scalar(
        select(UserDeck).where(UserDeck.user_id == user.id)
    )
    assert membership is not None
    await db_session.delete(membership)
    await db_session.flush()

    assert (
        await db_session.scalar(select(CardReview.id).where(CardReview.id == review.id))
        is None
    )
    assert (
        await db_session.scalar(
            select(CardReview.id).where(CardReview.id == other_review.id)
        )
        == other_review.id
    )
    assert await db_session.scalar(select(Card.id).where(Card.id == card.id)) == card.id


async def test_author_deletion_preserves_deck_and_cards(
    db_session: AsyncSession,
) -> None:
    user, deck, card, _, _ = await create_learning_graph(db_session)
    await db_session.delete(user)
    await db_session.flush()
    await db_session.refresh(deck)
    assert deck.author_id is None
    assert await db_session.scalar(select(Card.id).where(Card.id == card.id)) == card.id


async def test_review_idempotency_key_is_unique_per_user(
    db_session: AsyncSession,
) -> None:
    user, _, card, review, study = await create_learning_graph(db_session)
    db_session.add(make_log(user, card, review, study))
    await db_session.flush()
    with pytest.raises(IntegrityError, match="uq_review_logs_user_id_answer_token"):
        async with db_session.begin_nested():
            db_session.add(make_log(user, card, review, study))
            await db_session.flush()

    other, _, other_card, other_review, other_study = await create_learning_graph(
        db_session, vk_user_id=3_000_000_003
    )
    db_session.add(make_log(other, other_card, other_review, other_study))
    await db_session.flush()


@pytest.mark.parametrize("target", ["card", "deck"])
@pytest.mark.parametrize("completed", [False, True])
async def test_content_deletion_preserves_sessions_and_review_ledger(
    db_session: AsyncSession, target: str, completed: bool
) -> None:
    user, deck, card, review, study = await create_learning_graph(db_session)
    extra_cards = [
        Card(deck_id=deck.id, front=f"Вопрос {index}", back=f"Ответ {index}")
        for index in range(1, 5)
    ]
    db_session.add_all(extra_cards)
    await db_session.flush()
    for index, extra_card in enumerate(extra_cards, start=1):
        db_session.add(
            StudySessionCard(
                session_id=study.id,
                card_id=extra_card.id,
                source_card_id=extra_card.id,
                snapshot=CardOutput.model_validate(extra_card).model_dump(mode="json"),
                order_index=index,
                fsrs_state=StudyPlanner(settings.study).new_card(
                    extra_card.id, datetime.now(UTC)
                ),
                was_new=True,
            )
        )
    study.total_cards = 5
    study.completed_cards = 5 if completed else 0
    if completed:
        study.status = StudySessionStatus.COMPLETED
        study.finished_at = datetime.now(UTC)
    await db_session.flush()
    if completed:
        items = (
            await db_session.scalars(
                select(StudySessionCard).where(StudySessionCard.session_id == study.id)
            )
        ).all()
        for item in items:
            item.completed_at = study.finished_at
            item.attempts_count = 1

    log = make_log(user, card, review, study)
    if not completed:
        log.rating = 1
    db_session.add(log)
    await db_session.flush()
    user_id, session_id, card_id, log_id = user.id, study.id, card.id, log.id
    deck_id, study_date = deck.id, study.study_date
    original_result = log.result.copy()
    original_snapshot = CardOutput.model_validate(card).model_dump(mode="json")
    original_ids = {card.id, *(extra_card.id for extra_card in extra_cards)}

    card.front = "Изменённый вопрос"
    await db_session.flush()
    await db_session.delete(card if target == "card" else deck)
    await db_session.flush()
    db_session.expire_all()

    persisted = await db_session.get(StudySession, session_id)
    assert persisted is not None
    assert persisted.total_cards == 5
    assert persisted.completed_cards == (5 if completed else 0)
    assert persisted.status == (
        StudySessionStatus.COMPLETED if completed else StudySessionStatus.ACTIVE
    )
    items = (
        await db_session.scalars(
            select(StudySessionCard).where(StudySessionCard.session_id == session_id)
        )
    ).all()
    assert {item.card_id for item in items} == original_ids
    deleted_item = next(item for item in items if item.card_id == card_id)
    assert deleted_item.source_card_id is None
    assert deleted_item.snapshot == original_snapshot
    assert (
        StudySessionCardOutput.model_validate(deleted_item).snapshot.front == "Скорость"
    )
    if target == "deck":
        assert persisted.deck_id is None
        assert all(item.source_card_id is None for item in items)

    stored_log = await db_session.get(ReviewLog, log_id)
    assert stored_log is not None
    assert stored_log.result == original_result
    assert ReviewLogOutput.model_validate(stored_log).result.session.id == session_id
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ReviewLog)
            .where(ReviewLog.user_id == user_id, ReviewLog.was_new.is_(True))
        )
        == 1
    )
    with pytest.raises(IntegrityError, match="uq_review_logs_user_id_answer_token"):
        async with db_session.begin_nested():
            db_session.add(
                ReviewLog(
                    user_id=user_id,
                    session_id=session_id,
                    card_id=card_id,
                    answer_token="review-123",
                    deck_id=deck_id,
                    study_date=study_date,
                    reviewed_at=datetime.now(UTC),
                    was_new=False,
                    rating=4,
                    result=original_result,
                )
            )
            await db_session.flush()

    if not completed:
        for item in items:
            item.completed_at = datetime.now(UTC)
            item.attempts_count += 1
        persisted.completed_cards = 5
        persisted.status = StudySessionStatus.COMPLETED
        persisted.finished_at = datetime.now(UTC)
        completion_result = original_result
        completion_log = ReviewLog(
            user_id=user_id,
            session_id=session_id,
            card_id=card_id,
            answer_token="after-deletion",
            deck_id=deck_id,
            study_date=persisted.study_date,
            reviewed_at=datetime.now(UTC),
            was_new=False,
            rating=3,
            result=completion_result,
        )
        db_session.add(completion_log)
        await db_session.flush()
        await db_session.refresh(persisted)
        assert persisted.status == StudySessionStatus.COMPLETED
        assert ReviewLogOutput.model_validate(completion_log).card_id == card_id


@pytest.mark.parametrize("wrong_deck", [False, True])
async def test_progress_requires_membership_and_matching_card_deck(
    db_session: AsyncSession, wrong_deck: bool
) -> None:
    _, deck, card, original_review, _ = await create_learning_graph(db_session)
    other = User(vk_user_id=3_000_000_004, first_name="Анна")
    db_session.add(other)
    if wrong_deck:
        deck = Deck(title="Другая колода", subject=Subject.ALGEBRA)
        db_session.add(deck)
    await db_session.flush()
    if wrong_deck:
        db_session.add(UserDeck(user_id=other.id, deck_id=deck.id))
        await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                CardReview(
                    user_id=other.id,
                    card_id=card.id,
                    deck_id=deck.id,
                    cycle_id=original_review.cycle_id,
                    fsrs_state=original_review.fsrs_state,
                    due_date=original_review.due_date,
                    last_reviewed=original_review.last_reviewed,
                )
            )
            await db_session.flush()


async def test_review_log_cannot_target_another_users_session(
    db_session: AsyncSession,
) -> None:
    user, _, card, review, study = await create_learning_graph(db_session)
    other = User(vk_user_id=3_000_000_005, first_name="Анна")
    db_session.add(other)
    await db_session.flush()
    log = make_log(user, card, review, study)
    log.user_id = other.id
    with pytest.raises(
        IntegrityError, match="fk_review_logs_session_id_study_sessions"
    ):
        async with db_session.begin_nested():
            db_session.add(log)
            await db_session.flush()


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"completed_cards": -1}, "ck_study_sessions_completed_cards_range"),
        (
            {"status": "bad", "finished_at": datetime(2026, 11, 1, tzinfo=UTC)},
            "ck_study_sessions_valid_status",
        ),
    ],
)
async def test_database_rejects_invalid_session_state(
    db_session: AsyncSession, values: dict[str, object], constraint: str
) -> None:
    _, _, _, _, study = await create_learning_graph(db_session)
    with pytest.raises(IntegrityError, match=constraint):
        async with db_session.begin_nested():
            await db_session.execute(
                update(StudySession).where(StudySession.id == study.id).values(**values)
            )
