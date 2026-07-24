"""Lightweight trace context for linking agent loop steps.

A *trace* groups all episodes produced by a single task run
(Planner → Generator → Evaluator) under a shared ``trace_id`` so the full
chain can be reconstructed for debugging. The tracer is stdlib-only and
stores trace metadata in episode ``details["trace_id"]`` — no separate
store is needed; the existing episodes JSONL is the source of truth.

A span also pushes the ``trace_id`` into the structured-logging context
(see :mod:`hermes.workbench.structured_logging`), so log records emitted
inside the span automatically carry the ``trace_id`` field for grep/filter.

Usage::

    tracer = Tracer(memory)
    with tracer.span("task-run-abc") as trace_id:
        # episodes recorded inside this block get trace_id stamped
        # log records also carry trace_id automatically
        planner.plan(goal, fallback_plan)
        ...

Public surface:
    * :class:`Tracer`        — creates trace_ids and stamps episodes
    * :func:`new_trace_id`   — short unique id generator
    * :func:`stamp_episode`  — attach a trace_id to an Episode's details
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from hermes.workbench.memory import Episode, MemoryService, make_episode

__all__ = ["Tracer", "new_trace_id", "stamp_episode"]


def new_trace_id() -> str:
    """Generate a short, unique trace id (8 hex chars)."""
    return uuid.uuid4().hex[:8]


def stamp_episode(episode: Episode, trace_id: str) -> Episode:
    """Return a copy of *episode* with ``trace_id`` set in its details.

    Does not mutate the original; returns a new Episode so callers that
    hold a reference are not surprised.
    """
    new_details = dict(episode.details or {})
    new_details["trace_id"] = trace_id
    return Episode(
        id=episode.id,
        kind=episode.kind,
        summary=episode.summary,
        details=new_details,
        created_at=episode.created_at,
    )


class Tracer:
    """Stamps recorded episodes with a shared trace_id within a span.

    The tracer wraps a :class:`MemoryService` and exposes a ``span``
    context manager. Episodes recorded via :meth:`record` inside the
    span automatically carry the active trace_id in their details.
    """

    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory
        self._active_trace_id: str | None = None

    @property
    def active_trace_id(self) -> str | None:
        """Return the trace_id of the currently-open span, or None."""
        return self._active_trace_id

    @contextmanager
    def span(self, trace_id: str | None = None) -> Iterator[str]:
        """Open a tracing span; all ``record()`` calls inside get stamped.

        Yields the trace_id. Nested spans are not supported (a new span
        replaces the active one for the duration of the context).

        Also pushes ``trace_id`` into the structured-logging context so
        log records emitted inside the span carry it automatically.
        """
        tid = trace_id or new_trace_id()
        prev = self._active_trace_id
        self._active_trace_id = tid
        # Bind trace_id to the structured-logging context for this span.
        # Use a try/except so the tracer works even if structured_logging
        # is not importable (e.g. circular import during bootstrap).
        log_ctx_token = None
        try:
            from hermes.workbench.structured_logging import _LOG_CONTEXT
            parent_ctx = _LOG_CONTEXT.get()
            merged_ctx = {**parent_ctx, "trace_id": tid}
            log_ctx_token = _LOG_CONTEXT.set(merged_ctx)
        except Exception:  # noqa: BLE001
            pass
        try:
            yield tid
        finally:
            self._active_trace_id = prev
            if log_ctx_token is not None:
                try:
                    _LOG_CONTEXT.reset(log_ctx_token)
                except Exception:  # noqa: BLE001
                    pass

    def record(self, episode: Episode) -> None:
        """Record an episode, stamping it with the active trace_id if any.

        When no span is open, the episode is recorded unchanged (no
        trace_id), preserving backward compatibility.
        """
        if self._active_trace_id is not None:
            episode = stamp_episode(episode, self._active_trace_id)
        self.memory.record_episode(episode)

    def record_event(
        self, kind: str, summary: str, details: dict[str, Any] | None = None
    ) -> Episode:
        """Build, stamp, and record an episode in one call. Returns it.

        The returned Episode is the stamped copy (with ``trace_id`` set
        in its details) when a span is active, otherwise the original.
        """
        ep = make_episode(kind, summary, details)
        self.record(ep)
        # If a span is active, record() stamped a *copy* and persisted that;
        # we want callers to see the stamped version too.
        if self._active_trace_id is not None:
            return stamp_episode(ep, self._active_trace_id)
        return ep

    def get_trace(self, trace_id: str) -> list[Episode]:
        """Return all episodes carrying the given trace_id, oldest first.

        Scans all episodes (up to 10k) and filters by ``details.trace_id``.
        """
        all_eps = self.memory.list_episodes(limit=10000)
        matching = [
            ep for ep in all_eps
            if (ep.details or {}).get("trace_id") == trace_id
        ]
        # list_episodes returns newest-first; reverse for chronological order
        matching.reverse()
        return matching
