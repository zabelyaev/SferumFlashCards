from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.flashcards.cards.contracts.mappers import to_card_output
from application.study.contracts.mappers import (
    review_result_from_json,
    to_active_sessions_output,
    to_no_work_output,
    to_review_result_output,
    to_session_view_output,
    to_study_limits_output,
)
from application.study.contracts.outputs import StudySessionOpenedOutput
from application.study.contracts.types import DailyUsage
from application.study.database.models import (
    CardReview,
    LearningCycle,
    ReviewLog,
    StudySession,
    StudySessionCard,
)
from common.exceptions.conflict import ConflictError
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.not_found import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.accounts.users.database.models import User
    from application.activity.database.uow import StreakServiceFactory
    from application.flashcards.library.database.models import UserDeck
    from application.study.contracts.inputs import (
        ReviewCreateInput,
        StudySessionCreateInput,
    )
    from application.study.contracts.outputs import (
        ActiveStudySessionsOutput,
        DailyQuotaOutput,
        ReviewResultOutput,
        StudyLimitsOutput,
        StudyOpenResult,
        StudySessionViewOutput,
    )
    from application.study.contracts.types import (
        ReviewCalculation,
        SchedulerSnapshot,
        StudyDay,
    )
    from application.study.database.types import CandidateMetadata, StudyCandidate
    from application.study.database.uow import StudyUnitOfWork, StudyUnitOfWorkFactory
    from application.study.services.planner import StudyPlanner


def now_utc() -> datetime:
    return datetime.now(UTC)


class StudyService:
    def __init__(
        self,
        uow_factory: StudyUnitOfWorkFactory,
        streak_factory: StreakServiceFactory,
        planner: StudyPlanner,
    ) -> None:
        self.uow_factory = uow_factory
        self._streak_factory = streak_factory
        self._planner = planner

    async def open_session(
        self, user_id: int, model: StudySessionCreateInput
    ) -> StudyOpenResult:
        deck_id = model.deck_id
        async with self.uow_factory() as uow:
            user = await self._user(uow, user_id)
            deck = await uow.repo.lock_deck(deck_id)
            if deck is None:
                raise NotFoundError("Deck not found.")

            session = await uow.repo.active_for_deck(user_id, deck_id)
            now = now_utc()

            if session is not None:
                self._expire_session(session, now)
                if session.status == "active":
                    streaks = self._streak_factory(uow.activity)
                    await streaks.ensure_current(user, now)
                    quota = await self._load_quota(uow, session)
                    cards = await uow.repo.cards(session.id)
                    data = to_session_view_output(
                        session, user=user, quota=quota, cards=cards
                    )
                    await uow.commit()
                    return StudySessionOpenedOutput(view=data, created=False)
                await uow.flush()
            membership = await uow.repo.membership(user_id, deck_id)
            if membership is None:
                raise ForbiddenError("Deck is not in your library.")

            day = self._planner.study_day(now, user.timezone)
            limits = to_study_limits_output(user)
            usage = await uow.repo.used(user_id, deck_id, day.study_date)
            quota = self._planner.quota(usage, limits)
            chosen = await self._select_candidates(
                uow,
                user_id=user_id,
                deck_id=deck_id,
                now=now,
                usage=usage,
                limits=limits,
            )
            streaks = self._streak_factory(uow.activity)

            await streaks.ensure_current(user, now)

            if not chosen:
                has_cards = await uow.repo.deck_has_cards(deck_id)
                reason = self._planner.no_work_reason(
                    has_cards=has_cards,
                    has_candidates=has_cards
                    and await uow.repo.has_candidates(user_id, deck_id, now),
                )
                result = to_no_work_output(
                    deck_id=deck_id,
                    study_date=day.study_date,
                    user=user,
                    limits=limits,
                    quota=quota,
                    reason=reason,
                )
                await uow.commit()
                return result

            session, cards = await self._create_session(
                uow,
                user=user,
                membership=membership,
                day=day,
                limits=limits,
                chosen=chosen,
                now=now,
            )
            data = to_session_view_output(session, user=user, quota=quota, cards=cards)
            await uow.commit()
            return StudySessionOpenedOutput(view=data, created=True)

    async def list_active_sessions(self, user_id: int) -> ActiveStudySessionsOutput:
        now = now_utc()
        async with self.uow_factory() as uow:
            await self._user(uow, user_id)
            sessions = await uow.repo.active(user_id, now)
            return to_active_sessions_output(sessions)

    async def get_session(
        self, user_id: int, session_id: int
    ) -> StudySessionViewOutput:
        async with self.uow_factory() as uow:
            user = await self._user(uow, user_id)
            session = await uow.repo.session(user_id, session_id)
            if session is None:
                raise NotFoundError("Session not found.")
            now = now_utc()
            self._expire_session(session, now)
            await uow.flush()
            streaks = self._streak_factory(uow.activity)
            await streaks.ensure_current(user, now)
            quota = await self._load_quota(uow, session)
            cards = await uow.repo.cards(session.id)
            data = to_session_view_output(session, user=user, quota=quota, cards=cards)
            await uow.commit()
            return data

    async def submit_review(
        self, user_id: int, session_id: int, model: ReviewCreateInput
    ) -> ReviewResultOutput:
        async with self.uow_factory() as uow:
            user = await self._user(uow, user_id)
            replay = await self._replay_review(
                uow, user_id=user_id, session_id=session_id, model=model
            )
            if replay is not None:
                return replay
            session = await self._lock_session_for_review(
                uow, user_id=user_id, session_id=session_id
            )
            now = now_utc()
            self._expire_session(session, now)
            if session.status != "active":
                await uow.flush()
                streaks = self._streak_factory(uow.activity)
                await streaks.ensure_current(user, now)
                await uow.commit()
                raise ConflictError("Session is not active.")
            if (
                session.current_card_id != model.card_id
                or session.answer_token != model.answer_token
            ):
                raise ConflictError("Answer token or current card is invalid.")
            cards = await uow.repo.review_cards(session_id)
            item = next(card for card in cards if card.card_id == model.card_id)
            was_new = item.was_new and item.attempts_count == 0
            calculation = self._planner.review(
                item.fsrs_state, model.rating, now, session.scheduler_config
            )
            await self._apply_review(
                uow, session=session, item=item, calculation=calculation, now=now
            )
            self._advance_session(
                session, cards, config=session.scheduler_config, now=now
            )
            await uow.activity.record_activity(
                user_id, session.study_date, session.status == "completed"
            )
            await uow.repo.record_usage(
                user_id,
                session.historical_deck_id,
                session.study_date,
                item.card_id,
                was_new=was_new,
            )

            await uow.flush()
            streaks = self._streak_factory(uow.activity)
            if (
                session.status == "completed"
                and session.study_date != user.last_streak_date
            ):
                await streaks.recalculate(user, now)
            else:
                await streaks.ensure_current(user, now)
            quota = await self._load_quota(uow, session)
            result = to_review_result_output(session, user=user, quota=quota)
            self._record_review(
                uow,
                session=session,
                item=item,
                model=model,
                was_new=was_new,
                now=now,
                result=result,
            )
            await uow.commit()
            return result

    @staticmethod
    def _expire_session(session: StudySession, now: datetime) -> None:
        if session.status == "active" and session.expires_at <= now:
            session.status = "abandoned"
            session.finished_at = session.expires_at
            session.finish_reason = "timeout"
            session.current_card_id = None
            session.answer_token = None

    async def _user(self, uow: StudyUnitOfWork, user_id: int) -> User:
        try:
            user = await uow.users.get_by_id(user_id, no_key_update=True)
        except NotFoundError as exc:
            raise NotFoundError("User not found.") from exc
        if not user.is_active:
            raise ForbiddenError("User is disabled.")
        return user

    async def _replay_review(
        self,
        uow: StudyUnitOfWork,
        *,
        user_id: int,
        session_id: int,
        model: ReviewCreateInput,
    ) -> ReviewResultOutput | None:
        existing = await uow.repo.log(user_id, model.answer_token)
        if existing is None:
            return None
        if (
            existing.session_id != session_id
            or existing.card_id != model.card_id
            or existing.rating != model.rating
        ):
            raise ConflictError(
                "Answer token was already used with a different answer."
            )
        return review_result_from_json(existing.result)

    async def _lock_session_for_review(
        self, uow: StudyUnitOfWork, *, user_id: int, session_id: int
    ) -> StudySession:

        peek = await uow.repo.peek_session(user_id, session_id)
        if peek is None:
            raise NotFoundError("Session not found.")
        if peek.deck_id is not None:
            await uow.repo.lock_deck(peek.deck_id)
        session = await uow.repo.session(user_id, session_id)
        assert session is not None
        return session

    async def _load_quota(
        self, uow: StudyUnitOfWork, session: StudySession
    ) -> DailyQuotaOutput:
        usage = await uow.repo.usage_counts(
            session.user_id, session.historical_deck_id, session.study_date
        )
        return self._planner.quota(usage, to_study_limits_output(session))

    async def _select_candidates(
        self,
        uow: StudyUnitOfWork,
        *,
        user_id: int,
        deck_id: int,
        now: datetime,
        usage: DailyUsage,
        limits: StudyLimitsOutput,
    ) -> list[StudyCandidate]:
        batch_size = 128
        after: CandidateMetadata | None = None
        reserved = usage
        selected: list[int] = []
        while True:
            batch = await uow.repo.candidate_batch(
                user_id,
                deck_id,
                now,
                usage=reserved,
                limits=limits,
                after=after,
                limit=batch_size,
            )
            if not batch:
                break
            chosen = self._planner.select_cards(batch, usage=reserved, limits=limits)
            selected.extend(item.card_id for item in chosen)
            reserved = DailyUsage(
                card_ids=reserved.card_ids.union(item.card_id for item in chosen),
                new_card_ids=reserved.new_card_ids.union(
                    item.card_id for item in chosen if item.is_new
                ),
            )
            after = batch[-1]
            if len(batch) < batch_size:
                break
        return await uow.repo.candidates_by_ids(user_id, deck_id, selected)

    async def _create_session(
        self,
        uow: StudyUnitOfWork,
        *,
        user: User,
        membership: UserDeck,
        day: StudyDay,
        limits: StudyLimitsOutput,
        chosen: Sequence[StudyCandidate],
        now: datetime,
    ) -> tuple[StudySession, list[StudySessionCard]]:
        session = StudySession(
            user_id=user.id,
            deck_id=membership.deck_id,
            historical_deck_id=membership.deck_id,
            membership_id=membership.id,
            study_date=day.study_date,
            timezone=user.timezone,
            status="active",
            total_cards=len(chosen),
            completed_cards=0,
            daily_total_cards_limit=limits.daily_total_cards_limit,
            daily_new_cards_limit=limits.daily_new_cards_limit,
            scheduler_config=self._planner.config_snapshot(user.fsrs_parameters),
            started_at=now,
            last_activity_at=now,
            day_end_at=day.ends_at,
            expires_at=self._planner.expiration(day.ends_at, now),
        )
        uow.repo.add(session)
        await uow.flush()
        items: list[StudySessionCard] = []
        for index, (card, progress) in enumerate(chosen):
            state = (
                progress.fsrs_state
                if progress is not None
                else self._planner.new_card(card.id, now)
            )
            item = StudySessionCard(
                session_id=session.id,
                card_id=card.id,
                source_card_id=card.id,
                snapshot=to_card_output(card).model_dump(mode="json"),
                order_index=index,
                fsrs_state=state,
                cycle_id=progress.cycle_id if progress is not None else None,
                was_new=progress is None,
                attempts_count=0,
            )
            uow.repo.add(item)
            items.append(item)
        self._advance_session(session, items, config=session.scheduler_config, now=now)
        assert session.current_card_id is not None
        await uow.flush()
        return session, items

    async def _apply_review(
        self,
        uow: StudyUnitOfWork,
        *,
        session: StudySession,
        item: StudySessionCard,
        calculation: ReviewCalculation,
        now: datetime,
    ) -> None:
        item.fsrs_state = calculation.fsrs_state
        item.attempts_count += 1
        membership = (
            await uow.repo.membership(session.user_id, session.historical_deck_id)
            if session.deck_id is not None
            else None
        )
        can_update = (
            item.source_card_id is not None
            and membership is not None
            and membership.id == session.membership_id
        )
        if item.cycle_id is None:
            cycle = LearningCycle(
                user_id=session.user_id,
                card_id=item.card_id,
                deck_id=session.historical_deck_id,
                membership_id=membership.id if can_update and membership else None,
                created_at=now,
            )
            uow.repo.add(cycle)
            await uow.flush()
            item.cycle_id = cycle.id
        if can_update:
            progress = await uow.repo.progress(session.user_id, item.card_id)
            if progress is None and item.was_new:
                uow.repo.add(
                    CardReview(
                        user_id=session.user_id,
                        card_id=item.card_id,
                        deck_id=session.historical_deck_id,
                        cycle_id=item.cycle_id,
                        fsrs_state=item.fsrs_state,
                        due_date=calculation.due_date,
                        last_reviewed=now,
                    )
                )
            elif progress is not None and progress.cycle_id == item.cycle_id:
                progress.fsrs_state = item.fsrs_state
                progress.due_date = calculation.due_date
                progress.last_reviewed = now
        if calculation.completed:
            item.completed_at = now
            session.completed_cards += 1

    def _advance_session(
        self,
        session: StudySession,
        cards: Sequence[StudySessionCard],
        *,
        config: SchedulerSnapshot,
        now: datetime,
    ) -> None:
        session.last_activity_at = now
        session.expires_at = self._planner.expiration(session.day_end_at, now)
        following = self._planner.next_card(cards, now, config)
        if following is None:
            session.status = "completed"
            session.finished_at = now
            session.current_card_id = None
            session.answer_token = None
        else:
            session.current_card_id = following.card_id
            session.answer_token = secrets.token_urlsafe(24)

    def _record_review(
        self,
        uow: StudyUnitOfWork,
        *,
        session: StudySession,
        item: StudySessionCard,
        model: ReviewCreateInput,
        was_new: bool,
        now: datetime,
        result: ReviewResultOutput,
    ) -> None:
        log = ReviewLog(
            user_id=session.user_id,
            card_id=item.card_id,
            deck_id=session.historical_deck_id,
            session_id=session.id,
            cycle_id=item.cycle_id,
            study_date=session.study_date,
            answer_token=model.answer_token,
            rating=model.rating,
            was_new=was_new,
            result=result.model_dump(mode="json"),
            reviewed_at=now,
        )
        uow.repo.add(log)
