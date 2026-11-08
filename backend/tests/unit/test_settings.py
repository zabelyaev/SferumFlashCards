from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from common.config.auth import AuthConfig
from common.config.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


def test_settings_expose_selected_configuration() -> None:
    settings = Settings()  # type: ignore[call-arg]

    assert settings.run.host
    assert settings.api.prefix
    assert settings.api.v1.users
    assert settings.api.v1.sync
    assert not hasattr(settings.api.v1, "auth")
    assert not hasattr(settings.api.v1, "login")
    assert not hasattr(settings.api.v1, "refresh_access_token")
    assert not hasattr(settings.api.v1, "signup")
    assert settings.db.password.get_secret_value()
    assert settings.auth.app_key
    assert not hasattr(settings.auth, "client_key")
    assert not hasattr(settings.auth, "access_key")
    assert not hasattr(settings.auth, "jwt")


def test_dotenv_can_contain_compose_and_application_variables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_CONFIG__DB__PASSWORD")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "APP_CONFIG__DB__PASSWORD=app-password",
                "POSTGRES_DB=app",
                "POSTGRES_SUPERUSER_PASSWORD=postgres-password",
            )
        )
    )

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.db.password.get_secret_value() == "app-password"


def test_app_key_is_frozen_and_configurable(monkeypatch) -> None:
    assert AuthConfig() == AuthConfig()
    with pytest.raises(ValidationError, match="frozen"):
        AuthConfig().app_key = "replacement"
    monkeypatch.setenv("APP_CONFIG__AUTH__APP_KEY", "configured-app")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.auth.app_key == "configured-app"
    assert "configured-app" not in repr(settings.auth)


def test_app_key_can_be_loaded_from_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("APP_CONFIG__AUTH__APP_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_CONFIG__AUTH__APP_KEY=dotenv-app\n")
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert settings.auth == AuthConfig(app_key="dotenv-app")


@pytest.mark.parametrize("value", ["", None])
def test_app_key_has_no_builtin_default(value) -> None:
    assert AuthConfig(app_key=value).app_key is None


def test_settings_can_load_without_key_for_database_migrations(monkeypatch) -> None:
    monkeypatch.delenv("APP_CONFIG__AUTH__APP_KEY", raising=False)
    monkeypatch.delenv("APP_CONFIG__AUTH", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.auth.app_key is None


@pytest.mark.parametrize("value", [" ", "bad key", "x" * 257, "ключ"])
def test_app_key_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        AuthConfig(app_key=value)
