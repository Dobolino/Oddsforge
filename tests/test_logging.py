"""Tests for logging setup: logger creation, formatting, and level handling."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from rich.logging import RichHandler

from quantbot import logging as qlog
from quantbot.config import Settings
from quantbot.logging import JsonFormatter, configure_logging, get_logger


@pytest.fixture(autouse=True)
def _restore_logging_state() -> Iterator[None]:
    """Snapshot and restore the root logger and the module's configured flag."""

    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_flag = qlog._CONFIGURED
    try:
        yield
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        qlog._CONFIGURED = saved_flag


def _record(msg: str = "hello %s", args: tuple = ("world",)) -> logging.LogRecord:
    return logging.LogRecord(
        name="quantbot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg=msg,
        args=args,
        exc_info=None,
    )


# --- JsonFormatter ---


def test_json_formatter_basic_fields() -> None:
    payload = json.loads(JsonFormatter().format(_record()))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "quantbot.test"
    assert payload["message"] == "hello world"
    assert "ts" in payload


def test_json_formatter_includes_extras() -> None:
    record = _record()
    record.match_id = "m1"  # structured extra
    payload = json.loads(JsonFormatter().format(record))
    assert payload["match_id"] == "m1"


def test_json_formatter_includes_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="quantbot.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=20,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "exc_info" in payload
    assert "ValueError" in payload["exc_info"]


def test_json_formatter_output_is_valid_json() -> None:
    # default=str keeps non-serializable extras from breaking output.
    record = _record()
    record.obj = object()
    payload = json.loads(JsonFormatter().format(record))
    assert "obj" in payload


# --- configure_logging ---


def test_configure_logging_json_handler() -> None:
    configure_logging(Settings(log_json=True, log_level="DEBUG"), force=True)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_configure_logging_rich_handler() -> None:
    configure_logging(Settings(log_json=False, log_level="WARNING"), force=True)
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert isinstance(root.handlers[0], RichHandler)


def test_configure_logging_is_idempotent() -> None:
    configure_logging(Settings(log_json=True, log_level="INFO"), force=True)
    handler_before = logging.getLogger().handlers[0]
    # Second call without force must not replace the handler.
    configure_logging(Settings(log_json=False, log_level="ERROR"))
    assert logging.getLogger().handlers[0] is handler_before


def test_configure_logging_force_reapplies() -> None:
    configure_logging(Settings(log_json=True, log_level="INFO"), force=True)
    configure_logging(Settings(log_json=False, log_level="ERROR"), force=True)
    root = logging.getLogger()
    assert isinstance(root.handlers[0], RichHandler)
    assert root.level == logging.ERROR


# --- get_logger ---


def test_get_logger_returns_named_logger() -> None:
    qlog._CONFIGURED = False
    logger = get_logger("quantbot.unit")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "quantbot.unit"
    # Accessing it configured the root logger.
    assert logging.getLogger().handlers


def test_get_logger_emits_without_error(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(log_json=True, log_level="INFO"), force=True)
    logger = get_logger("quantbot.emit")
    logger.info("structured message", extra={"stake": 0.05})
    # No exception raised; JSON line written to stderr.
    captured = capsys.readouterr()
    assert "structured message" in captured.err or "structured message" in captured.out


@pytest.mark.parametrize("json_mode", [False, True])
def test_httpx_query_keys_are_redacted(json_mode, capsys):
    import httpx

    configure_logging(Settings(log_json=json_mode), force=True)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        client.get("https://example.test/odds", params={"apiKey": "fake-sensitive-key"})
    captured = capsys.readouterr()
    output = captured.err + captured.out
    assert "fake-sensitive-key" not in output
    assert "apiKey=" in output


def test_expired_cache_does_not_log_key(tmp_path, caplog):
    from quantbot.data.providers.base_http import FileCache

    cache = FileCache(tmp_path, ttl_seconds=1, time_fn=lambda: 0)
    cache.set("/odds?[('apiKey', 'fake-sensitive-key')]", [])
    cache._time_fn = lambda: 2
    with caplog.at_level(logging.DEBUG):
        assert cache.get("/odds?[('apiKey', 'fake-sensitive-key')]") is None
    assert "Cache expired" in caplog.text
    assert "fake-sensitive-key" not in caplog.text
