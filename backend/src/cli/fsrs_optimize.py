"""Manually optimize private per-user FSRS parameters."""

import argparse
import asyncio
import importlib.util
import json
import sys
from dataclasses import asdict


def positive_user_id(value: str) -> int:
    try:
        user_id = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("user ID must be a positive BIGINT") from exc
    if not 0 < user_id <= 2**63 - 1:
        raise argparse.ArgumentTypeError("user ID must be a positive BIGINT")
    return user_id


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--user-id", type=positive_user_id, help="internal user ID")
    mode.add_argument(
        "--eligible-users",
        action="store_true",
        help="process eligible users sequentially",
    )
    return result


async def run(user_id: int | None) -> int:
    from application.study.optimization.engine import FsrsOptimizer
    from application.study.optimization.repository import OptimizationRepository
    from application.study.optimization.service import FsrsOptimizationService
    from common.config import settings
    from common.database import DatabaseHelper

    helper = DatabaseHelper(settings.db)
    repository = OptimizationRepository(helper.engine)
    service = FsrsOptimizationService(repository, FsrsOptimizer(), settings.study)
    counts: dict[str, int] = {}
    failed = False

    async def process(current_id: int) -> None:
        nonlocal failed
        result = await service.optimize_user(current_id)
        print(
            json.dumps(asdict(result), ensure_ascii=False, allow_nan=False), flush=True
        )
        counts[result.status] = counts.get(result.status, 0) + 1
        failed |= result.status in ("failed", "already_running")

    try:
        if user_id is not None:
            await process(user_id)
        else:
            after_id = 0
            while ids := await repository.eligible_users(after_id=after_id, limit=100):
                for current_id in ids:
                    await process(current_id)
                after_id = ids[-1]
            print(json.dumps({"summary": counts}, ensure_ascii=False), flush=True)
    finally:
        await helper.dispose()
    return int(failed)


def missing_optimizer_dependencies() -> list[str]:
    return [
        name
        for name in ("torch", "numpy", "pandas", "tqdm")
        if importlib.util.find_spec(name) is None
    ]


def main() -> int:
    args = parser().parse_args()
    if missing_optimizer_dependencies():
        print(
            "FSRS optimizer dependencies are missing. Run: "
            "uv sync --extra fsrs-optimizer",
            file=sys.stderr,
        )
        return 2
    try:
        return asyncio.run(run(args.user_id))
    except Exception as exc:
        print(f"FSRS optimization failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
