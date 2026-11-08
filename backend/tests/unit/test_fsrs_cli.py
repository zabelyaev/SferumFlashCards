import os
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock

from application.study.optimization.contracts import OptimizationResult
from cli.fsrs_optimize import run


def test_cli_help_and_invalid_id_do_not_require_optimizer_dependencies() -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    help_result = subprocess.run(
        [sys.executable, "-m", "cli.fsrs_optimize", "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert help_result.returncode == 0
    assert (
        "--user-id" in help_result.stdout and "--eligible-users" in help_result.stdout
    )
    invalid = subprocess.run(
        [sys.executable, "-m", "cli.fsrs_optimize", "--user-id", "0"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert invalid.returncode == 2
    assert "positive BIGINT" in invalid.stderr


async def test_batch_continues_after_user_error_and_reports_failure(
    monkeypatch, capsys
) -> None:
    import common.database
    from application.study.optimization import repository, service

    helper = MagicMock()
    helper.dispose = AsyncMock()
    monkeypatch.setattr(common.database, "DatabaseHelper", lambda config: helper)
    repo = MagicMock()
    repo.eligible_users = AsyncMock(side_effect=[[1, 2], []])
    monkeypatch.setattr(repository, "OptimizationRepository", lambda engine: repo)
    worker = MagicMock()
    worker.optimize_user = AsyncMock(
        side_effect=[
            OptimizationResult(1, "failed", "error"),
            OptimizationResult(2, "insufficient_data"),
        ]
    )
    monkeypatch.setattr(service, "FsrsOptimizationService", lambda *args: worker)
    assert await run(None) == 1
    assert worker.optimize_user.await_count == 2
    assert repo.eligible_users.await_args_list[1].kwargs["after_id"] == 2
    assert '"summary"' in capsys.readouterr().out
    helper.dispose.assert_awaited_once()
