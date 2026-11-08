from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING

from application.study.optimization.quality import optimizer_training_reviews

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.study.optimization.contracts import OptimizationReview
    from common.config.study import StudyConfig


class FsrsOptimizer:
    async def optimize(
        self, reviews: Sequence[OptimizationReview], config: StudyConfig
    ) -> list[float]:
        payload = json.dumps(
            {
                "learning_step_seconds": config.learning_step_seconds,
                "relearning_step_seconds": config.relearning_step_seconds,
                "reviews": [
                    {
                        "cycle_id": review.cycle_id,
                        "rating": review.rating,
                        "reviewed_at": review.reviewed_at.isoformat(),
                    }
                    for review in optimizer_training_reviews(reviews)
                ],
            }
        ).encode()
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "application.study.optimization.worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await process.communicate(payload)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode != 0:
            raise RuntimeError(
                f"FSRS optimizer failed: {stderr.decode(errors='replace').strip()}"
            )
        result = json.loads(stdout)
        if not isinstance(result, list):
            raise ValueError("Optimizer did not return a parameter list.")
        return result
