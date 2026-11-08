from typing import TYPE_CHECKING

from sqlalchemy import Date, func, literal, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import load_only

from application.flashcards.cards.database.models import Card
from application.flashcards.decks.database.models import Deck
from application.flashcards.library.database.models import UserDeck
from application.study.contracts.types import DailyUsage, DailyUsageCounts
from application.study.database.models import (
    CardReview,
    ReviewLog,
    StudyDailyCard,
    StudyDailyUsage,
    StudySession,
    StudySessionCard,
)
from application.study.database.types import CandidateMetadata

if TYPE_CHECKING:
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

    from application.study.contracts.outputs import StudyLimitsOutput
    from application.study.database.models import LearningCycle
    from application.study.database.types import StudyCandidate


class StudyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def membership(self, user_id: int, deck_id: int) -> UserDeck | None:
        return await self.db.scalar(
            select(UserDeck).where(
                UserDeck.user_id == user_id, UserDeck.deck_id == deck_id
            )
        )

    async def lock_deck(self, deck_id: int) -> Deck | None:
        return await self.db.scalar(
            select(Deck).where(Deck.id == deck_id).with_for_update(read=True, of=Deck)
        )

    async def peek_session(self, user_id: int, session_id: int) -> StudySession | None:
        return await self.db.scalar(
            select(StudySession).where(
                StudySession.id == session_id, StudySession.user_id == user_id
            )
        )

    def add(
        self,
        record: StudySession
        | StudySessionCard
        | CardReview
        | LearningCycle
        | ReviewLog,
    ) -> None:
        self.db.add(record)

    async def session(self, user_id: int, session_id: int) -> StudySession | None:
        return await self.db.scalar(
            select(StudySession)
            .where(StudySession.id == session_id, StudySession.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def active_for_deck(self, user_id: int, deck_id: int) -> StudySession | None:
        return await self.db.scalar(
            select(StudySession)
            .where(
                StudySession.user_id == user_id,
                StudySession.historical_deck_id == deck_id,
                StudySession.status == "active",
            )
            .with_for_update()
        )

    async def active(self, user_id: int, now: datetime) -> list[StudySession]:
        query = (
            select(StudySession)
            .where(
                StudySession.user_id == user_id,
                StudySession.status == "active",
                StudySession.expires_at > now,
            )
            .order_by(StudySession.last_activity_at.desc(), StudySession.id.desc())
        )
        return list((await self.db.scalars(query)).all())

    async def cards(self, session_id: int) -> list[StudySessionCard]:
        return list(
            (
                await self.db.scalars(
                    select(StudySessionCard)
                    .where(StudySessionCard.session_id == session_id)
                    .order_by(StudySessionCard.order_index, StudySessionCard.id)
                )
            ).all()
        )

    async def review_cards(self, session_id: int) -> list[StudySessionCard]:

        stmt = (
            select(StudySessionCard)
            .where(
                StudySessionCard.session_id == session_id,
                StudySessionCard.completed_at.is_(None),
            )
            .options(
                load_only(
                    StudySessionCard.session_id,
                    StudySessionCard.card_id,
                    StudySessionCard.source_card_id,
                    StudySessionCard.order_index,
                    StudySessionCard.fsrs_state,
                    StudySessionCard.cycle_id,
                    StudySessionCard.was_new,
                    StudySessionCard.attempts_count,
                    StudySessionCard.completed_at,
                    raiseload=True,
                )
            )
            .order_by(StudySessionCard.order_index, StudySessionCard.id)
        )
        return list((await self.db.scalars(stmt)).all())

    async def candidate_batch(
        self,
        user_id: int,
        deck_id: int,
        now: datetime,
        *,
        usage: DailyUsage,
        limits: StudyLimitsOutput,
        after: CandidateMetadata | None,
        limit: int,
    ) -> list[CandidateMetadata]:
        total_full = len(usage.card_ids) >= limits.daily_total_cards_limit
        new_full = len(usage.new_card_ids) >= limits.daily_new_cards_limit
        result: list[CandidateMetadata] = []

        if after is None or after.due_date is not None:
            due = (
                select(Card.id, Card.order_index, CardReview.due_date)
                .join(CardReview, CardReview.card_id == Card.id)
                .where(
                    Card.deck_id == deck_id,
                    CardReview.user_id == user_id,
                    CardReview.due_date <= now,
                )
                .order_by(CardReview.due_date, Card.order_index, Card.id)
            )
            if total_full:
                due = due.where(Card.id.in_(usage.card_ids))
            if after is not None:
                due = due.where(
                    tuple_(CardReview.due_date, Card.order_index, Card.id)
                    > (after.due_date, after.order_index, after.card_id)
                )
            rows = (await self.db.execute(due.limit(limit))).all()
            result.extend(
                CandidateMetadata(row.id, row.order_index, row.due_date) for row in rows
            )

        if len(result) == limit or (new_full and not usage.new_card_ids):
            return result

        progress_exists = (
            select(CardReview.id)
            .where(CardReview.card_id == Card.id, CardReview.user_id == user_id)
            .exists()
        )
        new = (
            select(Card.id, Card.order_index)
            .where(Card.deck_id == deck_id, ~progress_exists)
            .order_by(Card.order_index, Card.id)
        )
        if total_full:
            new = new.where(Card.id.in_(usage.card_ids))
        if new_full:
            new = new.where(Card.id.in_(usage.new_card_ids))
        if after is not None and after.due_date is None:
            new = new.where(
                tuple_(Card.order_index, Card.id) > (after.order_index, after.card_id)
            )
        rows = (await self.db.execute(new.limit(limit - len(result)))).all()
        result.extend(CandidateMetadata(row.id, row.order_index, None) for row in rows)
        return result

    async def candidates_by_ids(
        self, user_id: int, deck_id: int, card_ids: list[int]
    ) -> list[StudyCandidate]:
        if not card_ids:
            return []
        query = (
            select(Card, CardReview)
            .outerjoin(
                CardReview,
                (CardReview.card_id == Card.id) & (CardReview.user_id == user_id),
            )
            .where(Card.deck_id == deck_id, Card.id.in_(card_ids))
        )
        found = {
            card.id: (card, progress)
            for card, progress in (await self.db.execute(query)).all()
        }
        return [found[card_id] for card_id in card_ids]

    async def has_candidates(self, user_id: int, deck_id: int, now: datetime) -> bool:
        query = (
            select(Card.id)
            .outerjoin(
                CardReview,
                (CardReview.card_id == Card.id) & (CardReview.user_id == user_id),
            )
            .where(
                Card.deck_id == deck_id,
                or_(CardReview.id.is_(None), CardReview.due_date <= now),
            )
        )
        return bool(await self.db.scalar(select(query.exists())))

    async def deck_has_cards(self, deck_id: int) -> bool:
        return bool(
            await self.db.scalar(
                select(select(Card.id).where(Card.deck_id == deck_id).exists())
            )
        )

    async def used(self, user_id: int, deck_id: int, day: date) -> DailyUsage:
        query = select(StudyDailyCard.card_id, StudyDailyCard.was_new).where(
            StudyDailyCard.user_id == user_id,
            StudyDailyCard.deck_id == deck_id,
            StudyDailyCard.study_date == day,
        )
        rows = (await self.db.execute(query)).all()
        return DailyUsage(
            card_ids=frozenset(row.card_id for row in rows),
            new_card_ids=frozenset(row.card_id for row in rows if row.was_new),
        )

    async def usage_counts(
        self, user_id: int, deck_id: int, day: date
    ) -> DailyUsageCounts:
        row = (
            await self.db.execute(
                select(StudyDailyUsage.total_used, StudyDailyUsage.new_used).where(
                    StudyDailyUsage.user_id == user_id,
                    StudyDailyUsage.deck_id == deck_id,
                    StudyDailyUsage.study_date == day,
                )
            )
        ).first()
        return DailyUsageCounts(*row) if row else DailyUsageCounts(0, 0)

    async def record_usage(
        self, user_id: int, deck_id: int, day: date, card_id: int, *, was_new: bool
    ) -> None:

        inserted = (
            insert(StudyDailyCard)
            .values(
                user_id=user_id,
                deck_id=deck_id,
                study_date=day,
                card_id=card_id,
                was_new=was_new,
            )
            .on_conflict_do_nothing()
            .returning(StudyDailyCard.was_new)
            .cte("inserted_usage")
        )
        total_delta = select(func.count()).select_from(inserted).scalar_subquery()
        new_delta: ColumnElement[int] = (
            select(func.count())
            .select_from(inserted)
            .where(inserted.c.was_new.is_(True))
            .scalar_subquery()
        )
        if was_new:
            promoted = (
                update(StudyDailyCard)
                .where(
                    StudyDailyCard.user_id == user_id,
                    StudyDailyCard.deck_id == deck_id,
                    StudyDailyCard.study_date == day,
                    StudyDailyCard.card_id == card_id,
                    StudyDailyCard.was_new.is_(False),
                    ~select(inserted.c.was_new).exists(),
                )
                .values(was_new=True)
                .returning(StudyDailyCard.card_id)
                .cte("promoted_usage")
            )
            new_delta += select(func.count()).select_from(promoted).scalar_subquery()
        previous = select(StudyDailyUsage.total_used, StudyDailyUsage.new_used).where(
            StudyDailyUsage.user_id == user_id,
            StudyDailyUsage.deck_id == deck_id,
            StudyDailyUsage.study_date == day,
        )

        total_used = (
            func.coalesce(
                previous.with_only_columns(
                    StudyDailyUsage.total_used
                ).scalar_subquery(),
                0,
            )
            + total_delta
        )
        new_used = (
            func.coalesce(
                previous.with_only_columns(StudyDailyUsage.new_used).scalar_subquery(),
                0,
            )
            + new_delta
        )
        counters = insert(StudyDailyUsage).from_select(
            ["user_id", "deck_id", "study_date", "total_used", "new_used"],
            select(
                literal(user_id),
                literal(deck_id),
                literal(day, type_=Date),
                total_used,
                new_used,
            ),
        )
        await self.db.execute(
            counters.on_conflict_do_update(
                index_elements=[
                    StudyDailyUsage.user_id,
                    StudyDailyUsage.deck_id,
                    StudyDailyUsage.study_date,
                ],
                set_={
                    "total_used": counters.excluded.total_used,
                    "new_used": counters.excluded.new_used,
                },
                where=or_(
                    StudyDailyUsage.total_used != counters.excluded.total_used,
                    StudyDailyUsage.new_used != counters.excluded.new_used,
                ),
            )
        )

    async def log(self, user_id: int, token: str) -> ReviewLog | None:
        return await self.db.scalar(
            select(ReviewLog).where(
                ReviewLog.user_id == user_id, ReviewLog.answer_token == token
            )
        )

    async def progress(self, user_id: int, card_id: int) -> CardReview | None:
        return await self.db.scalar(
            select(CardReview)
            .where(CardReview.user_id == user_id, CardReview.card_id == card_id)
            .with_for_update()
        )
