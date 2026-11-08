from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from common.config.run import RunConfig


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workers", 0),
        ("workers", 65),
        ("backlog", 127),
        ("backlog", 65536),
        ("timeout_keep_alive", 0),
        ("timeout_keep_alive", 301),
        ("timeout_graceful_shutdown", 0),
        ("timeout_graceful_shutdown", 301),
    ],
)
def test_invalid_server_capacity_settings_are_rejected(field, value) -> None:
    with pytest.raises(ValidationError):
        RunConfig(**{field: value})


def test_uvicorn_uses_import_string_and_configured_worker_settings(monkeypatch) -> None:
    import main

    config = RunConfig(
        host="0.0.0.0",
        port=8123,
        workers=4,
        backlog=8192,
        timeout_keep_alive=20,
        timeout_graceful_shutdown=40,
    )
    monkeypatch.setattr(main.settings, "run", config)
    serve = MagicMock()
    monkeypatch.setattr(main.uvicorn, "run", serve)
    main.run()
    serve.assert_called_once_with(
        "main:main_app",
        host="0.0.0.0",
        port=8123,
        workers=4,
        backlog=8192,
        timeout_keep_alive=20,
        timeout_graceful_shutdown=40,
    )
