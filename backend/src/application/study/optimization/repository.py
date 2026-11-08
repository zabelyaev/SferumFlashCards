from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import version
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB

from application.accounts.users.database.models import User
from application.study.database.models import ReviewLog, StudySession
from application.study.optimization.contracts import (
    OptimizationHistory,
    OptimizationReview,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

    from common.config.study import StudyConfig


@dataclass(frozen=True)
class OptimizationLock:
    connection: AsyncConnection
    backend_pid: int


class OptimizationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def user_lock(self, user_id: int) -> AsyncGenerator[OptimizationLock | None]:

        async with self._engine.connect() as connection:
            lock_key = f"apiforhack:fsrs-optimization:{user_id}"
            try:
                locked, backend_pid = (
                    await connection.execute(
                        text(
                            "SELECT pg_try_advisory_lock(hashtextextended(:key, 0)), "
                            "pg_backend_pid()"
                        ),
                        {"key": lock_key},
                    )
                ).one()
                await connection.commit()
            except BaseException:
                await connection.invalidate()
                raise
            if not locked:
                yield None
                return
            try:
                yield OptimizationLock(connection, backend_pid)
            finally:
                try:
                    await connection.rollback()
                    unlocked = await connection.scalar(
                        text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                        {"key": lock_key},
                    )
                    await connection.commit()
                    if not unlocked:
                        await connection.invalidate()
                except BaseException:
                    await connection.invalidate()
                    raise

    async def history(
        self, lock: OptimizationLock, user_id: int, config: StudyConfig
    ) -> OptimizationHistory | None:
        connection = lock.connection
        await connection.execution_options(isolation_level="REPEATABLE READ")
        async with connection.begin():
            user = (
                await connection.execute(
                    select(User.fsrs_parameters).where(
                        User.id == user_id, User.is_active.is_(True)
                    )
                )
            ).first()
            if user is None:
                return None
            snapshot = StudySession.scheduler_config

            scheduler = func.jsonb_extract_path(snapshot, "scheduler")
            compatible = func.coalesce(
                and_(
                    func.jsonb_typeof(snapshot) == "object",
                    func.jsonb_typeof(scheduler) == "object",
                    snapshot["library_version"].astext == version("fsrs"),
                    func.jsonb_extract_path(
                        snapshot, "scheduler", "learning_steps", type_=JSONB
                    )
                    == [config.learning_step_seconds],
                    func.jsonb_extract_path(
                        snapshot, "scheduler", "relearning_steps", type_=JSONB
                    )
                    == [config.relearning_step_seconds],
                ),
                False,
            ).label("compatible")
            rows = (
                await connection.execute(
                    select(
                        ReviewLog.id,
                        ReviewLog.cycle_id,
                        ReviewLog.rating,
                        ReviewLog.reviewed_at,
                        compatible,
                    )
                    .join(StudySession, StudySession.id == ReviewLog.session_id)
                    .where(
                        ReviewLog.user_id == user_id,
                        ReviewLog.cycle_id.is_not(None),
                    )
                    .order_by(ReviewLog.reviewed_at, ReviewLog.id)
                )
            ).all()
        invalid_cycles: set[int] = set()
        reviews: list[OptimizationReview] = []
        for row in rows:
            assert row.cycle_id is not None
            if not row.compatible:
                invalid_cycles.add(row.cycle_id)
            reviews.append(
                OptimizationReview(
                    cycle_id=row.cycle_id,
                    rating=row.rating,
                    reviewed_at=row.reviewed_at,
                    review_id=row.id,
                )
            )
        return OptimizationHistory(
            parameters=tuple(user.fsrs_parameters)
            if user.fsrs_parameters is not None
            else None,
            reviews=tuple(
                review for review in reviews if review.cycle_id not in invalid_cycles
            ),
            incompatible_cycles=len(invalid_cycles),
        )

    async def publish(
        self,
        lock: OptimizationLock,
        *,
        user_id: int,
        previous: tuple[float, ...] | None,
        parameters: tuple[float, ...],
    ) -> bool:
        connection = lock.connection
        if await connection.scalar(text("SELECT pg_backend_pid()")) != lock.backend_pid:
            raise RuntimeError(
                "Optimization lock connection changed before publication."
            )
        expected = (
            User.fsrs_parameters.is_(None)
            if previous is None
            else User.fsrs_parameters == list(previous)
        )
        result = await connection.scalar(
            update(User)
            .where(User.id == user_id, User.is_active.is_(True), expected)
            .values(fsrs_parameters=list(parameters))
            .returning(User.id)
        )
        await connection.commit()
        return result is not None

    async def eligible_users(self, *, after_id: int, limit: int) -> list[int]:
        async with self._engine.connect() as connection:
            enough_logs = (
                select(ReviewLog.id)
                .where(ReviewLog.user_id == User.id, ReviewLog.cycle_id.is_not(None))
                .correlate(User)
                .offset(513)
                .limit(1)
                .exists()
            )
            stmt = (
                select(User.id)
                .where(
                    User.id > after_id,
                    User.is_active.is_(True),
                    enough_logs,
                )
                .order_by(User.id)
                .limit(limit)
            )
            return list((await connection.scalars(stmt)).all())
