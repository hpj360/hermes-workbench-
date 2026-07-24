"""Structured JSON logging for the Hermes workbench.

Provides a ``StructuredFormatter`` for the stdlib :mod:`logging` module
that emits one JSON object per log record. Designed for production
observability: easy to ship to Loki/ELK/CloudWatch and to grep by
fields like ``trace_id``, ``event``, ``task_id``.

Usage::

    import logging
    from hermes.workbench.structured_logging import (
        StructuredFormatter, configure_logging,
    )

    # One-time setup at process start
    configure_logging(level="INFO", json=True)

    # In application code (trace_id propagates via contextvars)
    from hermes.workbench.structured_logging import log_context
    with log_context(trace_id="abc123", task_id="task-1"):
        logging.getLogger(__name__).info("planning finished",
                                         extra={"event": "plan", "steps": 3})

Public surface:
    * :class:`StructuredFormatter` — JSON log formatter
    * :func:`configure_logging` — one-time root logger setup
    * :func:`log_context` — context manager binding fields to the
      current log scope (uses :mod:`contextvars`)
    * :func:`get_log_context` — snapshot of current bindings
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator

__all__ = [
    "StructuredFormatter",
    "configure_logging",
    "log_context",
    "get_log_context",
]


# Contextvar holds a dict of extra fields to inject into every log record
# produced within the scope. Nested bindings merge with parent bindings.
_LOG_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "hermes_log_context", default={}
)


def get_log_context() -> dict[str, Any]:
    """Return a snapshot of the current log context bindings."""
    return dict(_LOG_CONTEXT.get())


@contextmanager
def log_context(**bindings: Any) -> Iterator[dict[str, Any]]:
    """Bind fields to the current log scope for the duration of the block.

    Example::

        with log_context(trace_id="abc", task_id="t1"):
            log.info("started")  # records include trace_id and task_id

    Nested calls merge with the parent scope. Re-binding an existing key
    overrides it for the inner scope only.
    """
    parent = _LOG_CONTEXT.get()
    merged = {**parent, **bindings}
    token = _LOG_CONTEXT.set(merged)
    try:
        yield merged
    finally:
        _LOG_CONTEXT.reset(token)


class StructuredFormatter(logging.Formatter):
    """Emit each log record as a single JSON line.

    Fields:
        ts        — ISO-8601 timestamp with millisecond precision
        level     — log level name (INFO, WARNING, ...)
        logger    — logger name
        msg       — the log message
        — plus any ``record`` extras and the current log_context bindings.
    """

    # Standard LogRecord attributes that should NOT be treated as extras.
    _RESERVED = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        # Merge: log_context bindings (lowest priority) < record extras < explicit fields
        payload: dict[str, Any] = {
            "ts": self._format_time(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Inject context bindings
        for k, v in _LOG_CONTEXT.get().items():
            payload.setdefault(k, v)
        # Inject record extras (only user-supplied ones)
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and not k.startswith("_"):
                payload[k] = v
        # Exception info, if any
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _format_time(created: float) -> str:
        # ISO-8601 with millisecond precision, e.g. 2026-07-25T08:30:00.123Z
        # Splitting manually avoids platform-specific strftime quirks.
        secs = int(created)
        ms = int((created - secs) * 1000)
        t = time.gmtime(secs)
        return (
            f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
            f"T{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
            f".{ms:03d}Z"
        )


def configure_logging(
    level: str | int = "INFO",
    json: bool = True,
    stream: Any = None,
) -> None:
    """Configure the root logger.

    :param level: log level name (``"INFO"``) or numeric value
    :param json: when True, emit JSON lines; when False, plain text
    :param stream: output stream (default: ``sys.stderr``)
    """
    if isinstance(level, str):
        level_num = getattr(logging, level.upper(), logging.INFO)
    else:
        level_num = int(level)

    handler = logging.StreamHandler(stream or sys.stderr)
    if json:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
            )
        )

    root = logging.getLogger()
    # Replace existing handlers to make configure idempotent
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level_num)
