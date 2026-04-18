"""Tests for the JSON logging formatter.

We avoid asserting on the FastAPI request log lines (uvicorn doesn't
log when using starlette's TestClient) and instead test the formatter
directly: same code path, no flakiness.
"""

import io
import json
import logging

from app.logging_config import JsonFormatter, configure_logging, get_logger


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def test_basic_record_renders_as_json_with_required_fields():
    record = logging.LogRecord(
        name="calltone.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    out = _format(record)
    assert out["level"] == "info"
    assert out["logger"] == "calltone.test"
    assert out["msg"] == "hello world"
    assert "ts" in out


def test_extra_fields_are_merged_into_payload():
    record = logging.LogRecord(
        name="calltone.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="upload",
        args=(),
        exc_info=None,
    )
    record.call_id = "abc-123"
    record.bytes = 4096
    out = _format(record)
    assert out["call_id"] == "abc-123"
    assert out["bytes"] == 4096
    assert out["level"] == "warning"


def test_non_serializable_extra_falls_back_to_repr():
    class Weird:
        def __repr__(self):
            return "<Weird>"

    record = logging.LogRecord(
        name="calltone.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="x",
        args=(),
        exc_info=None,
    )
    record.thing = Weird()
    out = _format(record)
    assert out["thing"] == "<Weird>"


def test_configure_logging_is_idempotent():
    """Calling configure_logging twice must not duplicate handlers."""
    configure_logging()
    before = len(logging.getLogger().handlers)
    configure_logging()
    after = len(logging.getLogger().handlers)
    assert before == after


def test_logger_writes_real_json_line(capsys):
    configure_logging("INFO")
    log = get_logger("calltone.test.real")
    log.info("smoke", extra={"shape": "round"})
    captured = capsys.readouterr().out.strip().splitlines()
    # last line should be ours and parse cleanly
    parsed = json.loads(captured[-1])
    assert parsed["msg"] == "smoke"
    assert parsed["shape"] == "round"
    assert parsed["logger"] == "calltone.test.real"
