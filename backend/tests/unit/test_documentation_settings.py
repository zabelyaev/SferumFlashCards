import pytest
from pydantic import SecretStr, ValidationError

from common.config.documentation import DocumentationConfig
from common.config.settings import Settings


def test_documentation_is_disabled_by_default(clean_documentation_env) -> None:
    config = DocumentationConfig()
    assert config.enabled is False
    assert config.prefix == "/internal"
    assert config.password.get_secret_value() == ""
    assert Settings(_env_file=None).documentation == config  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("prefix", "normalized"),
    [
        ("internal", "/internal"),
        (" /private/docs/ ", "/private/docs"),
        ("/ref-v2_0", "/ref-v2_0"),
    ],
)
def test_prefix_is_normalized(prefix, normalized) -> None:
    assert DocumentationConfig(prefix=prefix).prefix == normalized


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "/",
        "   ",
        "/private//docs",
        "/../docs",
        "/docs?key=1",
        "/docs#ref",
        "/docs%2fref",
        "/<script>",
    ],
)
def test_unsafe_or_empty_prefix_is_rejected(prefix) -> None:
    with pytest.raises(ValidationError, match="prefix"):
        DocumentationConfig(prefix=prefix)


@pytest.mark.parametrize(
    "credentials",
    [
        {},
        {"login": "admin"},
        {"password": "password"},
        {"login": "admin", "password": "   "},
        {"login": "   ", "password": "password"},
    ],
)
def test_enabled_documentation_requires_nonempty_credentials(credentials) -> None:
    with pytest.raises(ValidationError, match="requires a login and password"):
        DocumentationConfig.model_validate({"enabled": True, **credentials})


@pytest.mark.parametrize(
    ("login", "password"),
    [
        ("admin:reader", "password"),
        ("админ", "password"),
        ("admin", "пароль"),
        ("admin", "a\nb"),
    ],
)
def test_unusable_basic_credentials_are_rejected_at_startup(login, password) -> None:
    with pytest.raises(ValidationError, match="printable ASCII"):
        DocumentationConfig(enabled=True, login=login, password=SecretStr(password))


def test_password_is_masked_and_config_is_immutable() -> None:
    config = DocumentationConfig(
        enabled=True, login="admin", password=SecretStr("secret-value")
    )
    assert "secret-value" not in repr(config)
    assert "secret-value" not in config.model_dump_json()
    with pytest.raises(ValidationError, match="frozen"):
        config.enabled = False


@pytest.fixture
def clean_documentation_env(monkeypatch):
    for key in ("", "__PREFIX", "__PASSWORD", "__LOGIN", "__ENABLED"):
        monkeypatch.delenv(f"APP_CONFIG__DOCUMENTATION{key}", raising=False)


def test_documentation_settings_load_from_environment(
    monkeypatch, clean_documentation_env
) -> None:
    monkeypatch.setenv("APP_CONFIG__DOCUMENTATION__PREFIX", "/team/reference/")
    monkeypatch.setenv("APP_CONFIG__DOCUMENTATION__PASSWORD", "environment-password")
    monkeypatch.setenv("APP_CONFIG__DOCUMENTATION__LOGIN", "reader")
    monkeypatch.setenv("APP_CONFIG__DOCUMENTATION__ENABLED", "true")
    config = Settings(_env_file=None).documentation  # type: ignore[call-arg]
    assert config.enabled is True
    assert config.prefix == "/team/reference"
    assert config.login == "reader"
    assert config.password.get_secret_value() == "environment-password"


def test_documentation_settings_load_from_dotenv(
    tmp_path, clean_documentation_env
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_CONFIG__DOCUMENTATION__PREFIX=/dotenv-docs\n"
        "APP_CONFIG__DOCUMENTATION__PASSWORD=dotenv-password\n"
        "APP_CONFIG__DOCUMENTATION__LOGIN=dotenv-reader\n"
        "APP_CONFIG__DOCUMENTATION__ENABLED=true\n"
    )
    config = Settings(_env_file=env_file).documentation  # type: ignore[call-arg]
    assert config.enabled is True
    assert config.prefix == "/dotenv-docs"
    assert config.login == "dotenv-reader"
    assert config.password.get_secret_value() == "dotenv-password"


def test_disabled_documentation_can_load_empty_credentials_from_dotenv(
    tmp_path, clean_documentation_env
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_CONFIG__DOCUMENTATION__PASSWORD=\n"
        "APP_CONFIG__DOCUMENTATION__LOGIN=\n"
        "APP_CONFIG__DOCUMENTATION__ENABLED=false\n"
    )
    config = Settings(_env_file=env_file).documentation  # type: ignore[call-arg]
    assert config.enabled is False
    assert config.login == ""
    assert config.password.get_secret_value() == ""
