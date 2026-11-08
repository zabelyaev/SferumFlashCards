import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("APP_CONFIG__DB__PASSWORD", "app")
os.environ.setdefault("APP_CONFIG__AUTH", "{}")
os.environ.setdefault("APP_CONFIG__AUTH__APP_KEY", "test-app-key")
os.environ.setdefault("APP_CONFIG__CORS", "{}")


@pytest.fixture
def profile():
    from application.accounts.users.contracts.outputs import UserProfileOutput

    return UserProfileOutput(
        id=7,
        vk_user_id=12345678,
        first_name="Иван",
        last_name="Иванов",
        avatar_url=None,
        role="student",
        is_active=True,
        timezone="UTC",
        streak_days=0,
        max_streak_days=0,
        last_streak_date=None,
        daily_total_cards_limit=125,
        daily_new_cards_limit=12,
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
        updated_at=datetime(2026, 10, 23, tzinfo=UTC),
    )


@pytest.fixture
def app_headers() -> dict[str, str]:
    from common.config import settings

    assert settings.auth.app_key is not None
    return {"X-App-Key": settings.auth.app_key}


@pytest.fixture
def user_headers(app_headers, profile) -> dict[str, str]:
    return {**app_headers, "X-VK-User-ID": str(profile.vk_user_id)}


@pytest.fixture
def resolve_openapi_schema():
    def resolve(document: dict, schema: dict) -> dict:
        while "$ref" in schema:
            ref = schema["$ref"]
            assert ref.startswith("#/"), ref
            target = document
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            schema = {
                **target,
                **{key: value for key, value in schema.items() if key != "$ref"},
            }
        return schema

    return resolve


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.getenv("RUN_DB_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="Set RUN_DB_TESTS=1 to run PostgreSQL tests.")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
