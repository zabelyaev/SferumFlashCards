"""Run the FSRS batch only at the configured daily UTC hour."""

import asyncio
import json
import os
import signal
import sys
from datetime import UTC, datetime, timedelta

from cli.fsrs_optimize import missing_optimizer_dependencies, run

MAX_START_DELAY = timedelta(seconds=60)


def configured_hour() -> int:
    value = os.environ.get("FSRS_OPTIMIZER_HOUR_UTC", "21")
    try:
        hour = int(value)
    except ValueError as exc:
        raise ValueError(
            "FSRS_OPTIMIZER_HOUR_UTC must be an integer from 0 to 23"
        ) from exc
    if not 0 <= hour <= 23:
        raise ValueError("FSRS_OPTIMIZER_HOUR_UTC must be an integer from 0 to 23")
    return hour


def next_run(now: datetime, hour: int) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Current time must be timezone-aware")
    now = now.astimezone(UTC)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def log(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


async def wait_until(target: datetime) -> None:

    while (remaining := (target - datetime.now(UTC)).total_seconds()) > 0:
        await asyncio.sleep(min(remaining, 60))


async def schedule(hour: int) -> None:
    log("scheduler_started", hour_utc=hour)
    while True:
        target = next_run(datetime.now(UTC), hour)
        log("next_batch", at=target.isoformat())
        await wait_until(target)
        now = datetime.now(UTC)
        if now < target:
            continue
        if now - target > MAX_START_DELAY:
            log("batch_skipped", at=target.isoformat(), reason="missed_slot")
            continue
        log("batch_started")
        try:
            status = await run(None)
        except Exception as exc:
            log("batch_failed", error=str(exc))
        else:
            log("batch_finished", exit_code=status)


async def serve(hour: int) -> None:
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(schedule(hour))
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        log("scheduler_stopped")
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def main() -> int:
    try:
        hour = configured_hour()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if missing_optimizer_dependencies():
        print("FSRS optimizer dependencies are missing.", file=sys.stderr)
        return 2
    asyncio.run(serve(hour))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
