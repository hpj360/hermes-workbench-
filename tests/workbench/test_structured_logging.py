"""Tests for hermes.workbench.structured_logging."""

from __future__ import annotations

import io
import json
import logging

from hermes.workbench.structured_logging import (
    StructuredFormatter,
    configure_logging,
    get_log_context,
    log_context,
)


# ---------------------------------------------------------------------------
# log_context
# ---------------------------------------------------------------------------


def test_log_context_binds_fields() -> None:
    assert get_log_context() == {}
    with log_context(trace_id="abc", task_id="t1"):
        ctx = get_log_context()
        assert ctx["trace_id"] == "abc"
        assert ctx["task_id"] == "t1"
    # Restored after exit
    assert get_log_context() == {}


def test_log_context_merges_nested() -> None:
    with log_context(a="1", b="2"):
        with log_context(b="3", c="4"):
            ctx = get_log_context()
            assert ctx == {"a": "1", "b": "3", "c": "4"}
        # Inner exited; outer restored
        assert get_log_context() == {"a": "1", "b": "2"}


def test_log_context_isolation_across_concurrent_tasks() -> None:
    """contextvars isolate bindings across concurrent tasks (asyncio-safe)."""
    import asyncio

    async def worker(name: str) -> dict[str, str]:
        with log_context(worker=name):
            await asyncio.sleep(0)
            return get_log_context()

    async def main() -> list[dict[str, str]]:
        return await asyncio.gather(
            worker("a"), worker("b"), worker("c"),
        )

    results = asyncio.run(main())
    assert {r["worker"] for r in results} == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# StructuredFormatter
# ---------------------------------------------------------------------------


def _make_record(msg: str, **extras) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extras.items():
        setattr(record, k, v)
    return record


def test_formatter_emits_json() -> None:
    formatter = StructuredFormatter()
    out = formatter.format(_make_record("hello"))
    data = json.loads(out)
    assert data["msg"] == "hello"
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert "ts" in data
    assert data["ts"].endswith("Z")


def test_formatter_includes_extras() -> None:
    formatter = StructuredFormatter()
    out = formatter.format(_make_record("p", event="plan", steps=3))
    data = json.loads(out)
    assert data["event"] == "plan"
    assert data["steps"] == 3


def test_formatter_includes_log_context_bindings() -> None:
    formatter = StructuredFormatter()
    with log_context(trace_id="t-1", task_id="task-x"):
        out = formatter.format(_make_record("hi"))
    data = json.loads(out)
    assert data["trace_id"] == "t-1"
    assert data["task_id"] == "task-x"


def test_formatter_record_extras_override_context() -> None:
    """Record-level extras should override context bindings of the same name."""
    formatter = StructuredFormatter()
    with log_context(trace_id="from-context"):
        out = formatter.format(_make_record("m", trace_id="from-record"))
    data = json.loads(out)
    assert data["trace_id"] == "from-record"


def test_formatter_includes_exception_info() -> None:
    formatter = StructuredFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    out = formatter.format(record)
    data = json.loads(out)
    assert "exc" in data
    assert "ValueError" in data["exc"]
    assert "boom" in data["exc"]


def test_formatter_ts_format_iso8601() -> None:
    formatter = StructuredFormatter()
    # Use a fixed time for deterministic test
    record = _make_record("m")
    record.created = 1721900000.123  # 2024-07-25T...
    out = formatter.format(record)
    data = json.loads(out)
    ts = data["ts"]
    # ISO-8601 format: YYYY-MM-DDTHH:MM:SS.mmmZ (24 chars)
    assert ts.endswith("Z")
    assert "T" in ts
    # The ".mmmZ" suffix has 3 millisecond digits before the trailing Z
    assert ts[-5] == "."
    assert len(ts) == 24  # "YYYY-MM-DDTHH:MM:SS.mmmZ" = 24 chars


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


def test_configure_logging_json_writes_to_stream() -> None:
    stream = io.StringIO()
    configure_logging(level="INFO", json=True, stream=stream)
    log = logging.getLogger("test.config.json")
    log.info("hello world", extra={"event": "test"})
    out = stream.getvalue().strip()
    data = json.loads(out)
    assert data["msg"] == "hello world"
    assert data["event"] == "test"


def test_configure_logging_text_mode() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", json=False, stream=stream)
    log = logging.getLogger("test.config.text")
    log.warning("warn msg")
    out = stream.getvalue()
    assert "warn msg" in out
    assert "WARNING" in out
    # Should NOT be JSON
    assert not out.strip().startswith("{")


def test_configure_logging_is_idempotent() -> None:
    """Calling configure_logging multiple times should not stack handlers."""
    stream1 = io.StringIO()
    configure_logging(level="INFO", json=True, stream=stream1)
    root = logging.getLogger()
    n1 = len(root.handlers)

    stream2 = io.StringIO()
    configure_logging(level="INFO", json=True, stream=stream2)
    n2 = len(root.handlers)

    assert n2 == n1  # same count, not stacked


def test_configure_logging_respects_level() -> None:
    stream = io.StringIO()
    configure_logging(level="WARNING", json=True, stream=stream)
    log = logging.getLogger("test.config.level")
    log.debug("debug-msg")  # below threshold; should not appear
    log.warning("warn-msg")  # at threshold; should appear
    out = stream.getvalue().strip()
    assert "debug-msg" not in out
    assert "warn-msg" in out
