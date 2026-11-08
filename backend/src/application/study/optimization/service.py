from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from fsrs.scheduler import DEFAULT_PARAMETERS

from application.study.optimization.contracts import OptimizationResult
from application.study.optimization.quality import (
    MIN_TRAIN_EXAMPLES,
    MIN_VALIDATION_EXAMPLES,
    split_history,
    validate_parameters,
    validation_loss,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.study.optimization.contracts import (
        OptimizationReview,
        OptimizationStatus,
    )
    from application.study.optimization.repository import OptimizationRepository
    from common.config.study import StudyConfig


class Optimizer(Protocol):
    async def optimize(
        self, reviews: Sequence[OptimizationReview], config: StudyConfig
    ) -> Sequence[float]: ...


class FsrsOptimizationService:
    def __init__(
        self,
        repository: OptimizationRepository,
        optimizer: Optimizer,
        config: StudyConfig,
    ) -> None:
        self._repository = repository
        self._optimizer = optimizer
        self._config = config

    async def optimize_user(self, user_id: int) -> OptimizationResult:
        if user_id <= 0 or user_id > 2**63 - 1:
            return OptimizationResult(user_id, "failed", "Invalid user ID.")
        try:
            async with self._repository.user_lock(user_id) as connection:
                if connection is None:
                    return OptimizationResult(user_id, "already_running")
                history = await self._repository.history(
                    connection, user_id, self._config
                )
                if history is None:
                    return OptimizationResult(
                        user_id, "failed", "User not found or disabled."
                    )
                split = split_history(history.reviews)
                if split.train_examples < MIN_TRAIN_EXAMPLES:
                    return OptimizationResult(
                        user_id,
                        "insufficient_data",
                        "Not enough eligible training reviews.",
                        train_reviews=split.train_examples,
                    )
                current = validate_parameters(
                    history.parameters
                    if history.parameters is not None
                    else DEFAULT_PARAMETERS
                )
                current_loss, validation_count = await asyncio.to_thread(
                    validation_loss, split, current, self._config
                )
                if current_loss is None or validation_count < MIN_VALIDATION_EXAMPLES:
                    return OptimizationResult(
                        user_id,
                        "insufficient_data",
                        "Not enough eligible validation reviews.",
                        train_reviews=split.train_examples,
                        validation_reviews=validation_count,
                    )
                candidate = validate_parameters(
                    await self._optimizer.optimize(split.train, self._config)
                )
                candidate_loss, candidate_count = await asyncio.to_thread(
                    validation_loss, split, candidate, self._config
                )
                if candidate_loss is None or candidate_count != validation_count:
                    raise ValueError("Invalid validation result.")

                def result(
                    status: OptimizationStatus, message: str = ""
                ) -> OptimizationResult:
                    return OptimizationResult(
                        user_id,
                        status,
                        message,
                        train_reviews=split.train_examples,
                        validation_reviews=validation_count,
                        current_loss=current_loss,
                        candidate_loss=candidate_loss,
                    )

                if candidate_loss >= current_loss:
                    return result("not_improved")
                published = await self._repository.publish(
                    connection,
                    user_id=user_id,
                    previous=history.parameters,
                    parameters=candidate,
                )
                if not published:
                    return result(
                        "failed", "User or parameters changed during optimization."
                    )
                return result("updated")
        except Exception as exc:
            return OptimizationResult(user_id, "failed", str(exc))
