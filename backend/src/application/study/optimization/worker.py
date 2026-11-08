"""Private subprocess entry point for the optional, CPU-bound FSRS optimizer."""

import json
import sys
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.metadata import version


def main() -> int:
    if version("fsrs") != "6.3.2":
        raise RuntimeError("FSRS optimizer requires fsrs==6.3.2.")
    try:
        import fsrs.optimizer as optimizer_module
        from fsrs import Rating, ReviewLog, Scheduler
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional dependency: uv sync --extra fsrs-optimizer"
        ) from exc

    payload = json.load(sys.stdin)
    logs = [
        ReviewLog(
            card_id=item["cycle_id"],
            rating=Rating(item["rating"]),
            review_datetime=datetime.fromisoformat(item["reviewed_at"]).astimezone(UTC),
            review_duration=None,
        )
        for item in payload["reviews"]
    ]

    setattr(
        optimizer_module,
        "Scheduler",
        partial(
            Scheduler,
            learning_steps=(timedelta(seconds=payload["learning_step_seconds"]),),
            relearning_steps=(timedelta(seconds=payload["relearning_step_seconds"]),),
            enable_fuzzing=False,
        ),
    )
    parameters = getattr(
        optimizer_module.Optimizer(logs), "compute_optimal_parameters"
    )()
    print(json.dumps(parameters, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
