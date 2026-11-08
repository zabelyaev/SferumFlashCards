import os

import pytest
from sqlalchemy.engine import make_url

from common.config import settings


def require_test_database(database: str | None) -> None:
    if not database or not database.endswith("_test"):
        pytest.fail("Integration tests require a database whose name ends in '_test'.")


@pytest.fixture
def validated_test_database():
    require_test_database(make_url(settings.db.async_url).database)
    return settings.db


@pytest.fixture
def validated_migration_database_url():
    database_url = os.getenv("TEST_MIGRATION_DATABASE_URL")
    if database_url is None:
        pytest.skip("Set TEST_MIGRATION_DATABASE_URL to run migration regressions.")
    url = make_url(database_url)
    require_test_database(url.database)
    return url
