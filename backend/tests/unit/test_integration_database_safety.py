import os
import subprocess
import sys


def test_study_fixture_rejects_non_test_database_before_connecting() -> None:
    env = os.environ.copy()
    env.update(
        RUN_DB_TESTS="1",
        APP_CONFIG__DB__NAME="production",
        APP_CONFIG__DB__HOST="127.0.0.1",
        APP_CONFIG__DB__PORT="1",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/test_study_flow.py::test_study_review_replay_and_completion",
            "-q",
            "--tb=short",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "database whose name ends in '_test'" in result.stdout
    assert "ConnectionRefusedError" not in result.stdout


def test_migration_fixture_rejects_non_test_database_before_connecting() -> None:
    env = os.environ.copy()
    env.update(
        RUN_DB_TESTS="1",
        TEST_MIGRATION_DATABASE_URL="postgresql+asyncpg://app:app@127.0.0.1:1/production",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/test_learning_migrations.py::test_initial_schema_round_trip",
            "-q",
            "--tb=short",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "database whose name ends in '_test'" in result.stdout
    assert "ConnectionRefusedError" not in result.stdout
