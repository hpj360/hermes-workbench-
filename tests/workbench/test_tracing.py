"""Tests for hermes.workbench.tracing."""

from __future__ import annotations

from pathlib import Path

from hermes.workbench.memory import MemoryService, make_episode
from hermes.workbench.tracing import Tracer, new_trace_id, stamp_episode


def _make_memory(tmp_path: Path) -> MemoryService:
    return MemoryService(state_dir=tmp_path / "state")


# ---------------------------------------------------------------------------
# new_trace_id
# ---------------------------------------------------------------------------


def test_new_trace_id_is_8_hex_chars() -> None:
    tid = new_trace_id()
    assert isinstance(tid, str)
    assert len(tid) == 8
    int(tid, 16)  # parses as hex


def test_new_trace_ids_are_unique() -> None:
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# stamp_episode
# ---------------------------------------------------------------------------


def test_stamp_episode_adds_trace_id() -> None:
    ep = make_episode("k", "summary", {"foo": "bar"})
    stamped = stamp_episode(ep, "abc123")
    assert stamped.details["trace_id"] == "abc123"
    # Original details preserved
    assert stamped.details["foo"] == "bar"
    # Original episode NOT mutated
    assert "trace_id" not in (ep.details or {})


def test_stamp_episode_does_not_mutate_original() -> None:
    ep = make_episode("k", "s")
    original_details = dict(ep.details)
    _ = stamp_episode(ep, "tid")
    assert ep.details == original_details


def test_stamp_episode_preserves_other_fields() -> None:
    ep = make_episode("loop", "did thing", {"a": 1, "b": 2})
    stamped = stamp_episode(ep, "t1")
    assert stamped.id == ep.id
    assert stamped.kind == ep.kind
    assert stamped.summary == ep.summary
    assert stamped.created_at == ep.created_at


# ---------------------------------------------------------------------------
# Tracer.span
# ---------------------------------------------------------------------------


def test_span_yields_trace_id(tmp_path: Path) -> None:
    tracer = Tracer(_make_memory(tmp_path))
    with tracer.span() as tid:
        assert isinstance(tid, str)
        assert len(tid) == 8


def test_span_accepts_explicit_trace_id(tmp_path: Path) -> None:
    tracer = Tracer(_make_memory(tmp_path))
    with tracer.span("custom-id") as tid:
        assert tid == "custom-id"


def test_span_resets_active_id_after(tmp_path: Path) -> None:
    tracer = Tracer(_make_memory(tmp_path))
    assert tracer.active_trace_id is None
    with tracer.span():
        assert tracer.active_trace_id is not None
    assert tracer.active_trace_id is None


def test_span_nested_restores_parent(tmp_path: Path) -> None:
    """Nested spans: inner replaces outer; outer restored after inner exits."""
    tracer = Tracer(_make_memory(tmp_path))
    with tracer.span("outer") as outer_tid:
        assert tracer.active_trace_id == "outer"
        with tracer.span("inner") as inner_tid:
            assert inner_tid == "inner"
            assert tracer.active_trace_id == "inner"
        # Inner exited; outer restored
        assert tracer.active_trace_id == "outer"
    assert tracer.active_trace_id is None


# ---------------------------------------------------------------------------
# Tracer.record
# ---------------------------------------------------------------------------


def test_record_outside_span_stamps_nothing(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    tracer = Tracer(mem)
    ep = make_episode("k", "s")
    tracer.record(ep)
    episodes = mem.list_episodes()
    assert len(episodes) == 1
    assert "trace_id" not in (episodes[0].details or {})


def test_record_inside_span_stamps_trace_id(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    tracer = Tracer(mem)
    with tracer.span("tid-1"):
        tracer.record(make_episode("k", "s"))
    episodes = mem.list_episodes()
    assert len(episodes) == 1
    assert episodes[0].details["trace_id"] == "tid-1"


def test_record_event_builds_and_stamps(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    tracer = Tracer(mem)
    with tracer.span("t-event") as tid:
        ep = tracer.record_event("note", "thing happened", {"k": "v"})
    assert ep.details["trace_id"] == "t-event"
    assert ep.details["k"] == "v"
    # And it's persisted
    episodes = mem.list_episodes()
    assert len(episodes) == 1
    assert episodes[0].details["trace_id"] == tid


# ---------------------------------------------------------------------------
# Tracer.get_trace
# ---------------------------------------------------------------------------


def test_get_trace_returns_chronological(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    tracer = Tracer(mem)
    with tracer.span("trace-A"):
        tracer.record_event("planner", "first")
        tracer.record_event("generator", "second")
        tracer.record_event("evaluator", "third")
    # Some other trace to ensure filtering works
    with tracer.span("trace-B"):
        tracer.record_event("planner", "other")

    eps = tracer.get_trace("trace-A")
    assert len(eps) == 3
    # Chronological: first, second, third
    assert [e.summary for e in eps] == ["first", "second", "third"]
    assert all(e.details["trace_id"] == "trace-A" for e in eps)


def test_get_trace_returns_empty_when_no_match(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    tracer = Tracer(mem)
    with tracer.span("real"):
        tracer.record_event("k", "s")
    eps = tracer.get_trace("nonexistent")
    assert eps == []


def test_get_trace_ignores_episodes_without_trace_id(tmp_path: Path) -> None:
    """Episodes recorded outside any span should not appear in any trace."""
    mem = _make_memory(tmp_path)
    tracer = Tracer(mem)
    # Record without span
    mem.record_episode(make_episode("k", "no-trace"))
    with tracer.span("t1"):
        tracer.record_event("k", "with-trace")

    eps = tracer.get_trace("t1")
    assert len(eps) == 1
    assert eps[0].summary == "with-trace"
