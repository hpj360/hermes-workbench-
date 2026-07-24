"""Tests for workbench.audit module.

Covers AuditEntry dataclass, AuditLog record/query/stats/clear, and
the global audit-log singleton helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes.workbench.audit import (
    AuditEntry,
    AuditLog,
    get_audit_log,
    init_audit_log,
    reset_audit_log,
)


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------


def test_audit_entry_defaults():
    e = AuditEntry()
    assert e.id  # auto-generated
    assert e.timestamp > 0
    assert e.method == ""
    assert e.path == ""
    assert e.status == 0
    assert e.error is None


def test_audit_entry_to_dict_roundtrip():
    e = AuditEntry(
        method="GET",
        path="/skills",
        status=200,
        duration_ms=12.5,
        client_ip="127.0.0.1",
        user_agent="curl/8",
    )
    d = e.to_dict()
    assert d["method"] == "GET"
    assert d["path"] == "/skills"
    assert d["status"] == 200
    assert d["duration_ms"] == 12.5
    assert d["client_ip"] == "127.0.0.1"
    assert d["user_agent"] == "curl/8"
    assert d["error"] is None


def test_audit_entry_with_error():
    e = AuditEntry(method="POST", path="/tasks", status=500, error="boom")
    d = e.to_dict()
    assert d["error"] == "boom"


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_log(tmp_path: Path) -> AuditLog:
    return AuditLog(state_dir=tmp_path)


def test_audit_log_records_entry(audit_log: AuditLog):
    e = AuditEntry(method="GET", path="/health", status=200, duration_ms=1.0)
    audit_log.record(e)
    entries = audit_log.query(limit=10)
    assert len(entries) == 1
    assert entries[0]["method"] == "GET"


def test_audit_log_query_returns_newest_first(audit_log: AuditLog):
    """Query returns entries sorted newest-first by timestamp."""
    audit_log.record(AuditEntry(method="GET", path="/a", timestamp=100.0))
    audit_log.record(AuditEntry(method="GET", path="/b", timestamp=200.0))
    audit_log.record(AuditEntry(method="GET", path="/c", timestamp=150.0))

    entries = audit_log.query(limit=10)
    assert [e["path"] for e in entries] == ["/b", "/c", "/a"]


def test_audit_log_query_filter_by_method(audit_log: AuditLog):
    audit_log.record(AuditEntry(method="GET", path="/a"))
    audit_log.record(AuditEntry(method="POST", path="/b"))
    audit_log.record(AuditEntry(method="GET", path="/c"))

    only_get = audit_log.query(method="GET")
    assert len(only_get) == 2
    assert all(e["method"] == "GET" for e in only_get)


def test_audit_log_query_filter_by_path_prefix(audit_log: AuditLog):
    audit_log.record(AuditEntry(path="/skills"))
    audit_log.record(AuditEntry(path="/memory/facts"))
    audit_log.record(AuditEntry(path="/memory/episodes"))

    only_memory = audit_log.query(path_prefix="/memory")
    assert len(only_memory) == 2


def test_audit_log_query_filter_by_status(audit_log: AuditLog):
    audit_log.record(AuditEntry(path="/ok", status=200))
    audit_log.record(AuditEntry(path="/bad", status=404))
    audit_log.record(AuditEntry(path="/boom", status=500))

    only_errors = audit_log.query(min_status=400)
    assert len(only_errors) == 2

    only_404 = audit_log.query(min_status=400, max_status=499)
    assert len(only_404) == 1
    assert only_404[0]["status"] == 404


def test_audit_log_query_limit(audit_log: AuditLog):
    for i in range(10):
        audit_log.record(AuditEntry(path=f"/p{i}"))
    assert len(audit_log.query(limit=3)) == 3


def test_audit_log_query_empty(audit_log: AuditLog):
    assert audit_log.query() == []


def test_audit_log_stats_empty(audit_log: AuditLog):
    stats = audit_log.stats()
    assert stats["total"] == 0
    assert stats["errors"] == 0
    assert stats["avg_duration_ms"] == 0


def test_audit_log_stats_with_entries(audit_log: AuditLog):
    audit_log.record(AuditEntry(status=200, duration_ms=10.0))
    audit_log.record(AuditEntry(status=200, duration_ms=20.0))
    audit_log.record(AuditEntry(status=500, duration_ms=30.0))

    stats = audit_log.stats()
    assert stats["total"] == 3
    assert stats["errors"] == 1
    assert stats["error_rate"] == round(1 / 3, 3)
    assert stats["avg_duration_ms"] == 20.0  # (10+20+30)/3


def test_audit_log_clear(audit_log: AuditLog):
    audit_log.record(AuditEntry(path="/a"))
    audit_log.record(AuditEntry(path="/b"))
    count = audit_log.clear()
    assert count == 2
    assert audit_log.query() == []
    assert audit_log.stats()["total"] == 0


def test_audit_log_clear_empty(audit_log: AuditLog):
    count = audit_log.clear()
    assert count == 0


def test_audit_log_buffer_cap(tmp_path: Path):
    """Buffer is capped at buffer_size; older entries evicted."""
    log = AuditLog(state_dir=tmp_path, buffer_size=3)
    for i in range(5):
        log.record(AuditEntry(path=f"/p{i}"))
    # Only the last 3 should be in memory
    entries = log.query(limit=100)
    assert len(entries) == 3
    paths = {e["path"] for e in entries}
    assert paths == {"/p2", "/p3", "/p4"}


def test_audit_log_persists_to_disk(audit_log: AuditLog, tmp_path: Path):
    audit_log.record(AuditEntry(path="/a", method="GET"))
    audit_path = tmp_path / "audit.jsonl"
    assert audit_path.exists()
    content = audit_path.read_text(encoding="utf-8").strip()
    assert "/a" in content


def test_audit_log_loads_existing_entries(tmp_path: Path):
    """A new AuditLog instance loads entries from the existing audit.jsonl."""
    log1 = AuditLog(state_dir=tmp_path)
    log1.record(AuditEntry(path="/first"))
    log1.record(AuditEntry(path="/second"))

    log2 = AuditLog(state_dir=tmp_path)
    entries = log2.query(limit=10)
    assert len(entries) == 2
    paths = {e["path"] for e in entries}
    assert paths == {"/first", "/second"}


def test_audit_log_loads_corrupt_file_gracefully(tmp_path: Path):
    """A corrupt audit.jsonl is silently ignored."""
    (tmp_path / "audit.jsonl").write_text("not valid json\n", encoding="utf-8")
    log = AuditLog(state_dir=tmp_path)
    assert log.query() == []


def test_audit_log_loads_empty_file(tmp_path: Path):
    (tmp_path / "audit.jsonl").write_text("", encoding="utf-8")
    log = AuditLog(state_dir=tmp_path)
    assert log.query() == []


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


def test_get_audit_log_returns_none_before_init():
    reset_audit_log()
    assert get_audit_log() is None


def test_init_audit_log_creates_singleton(tmp_path: Path):
    reset_audit_log()
    log = init_audit_log(tmp_path)
    assert get_audit_log() is log


def test_init_audit_log_idempotent(tmp_path: Path):
    """Second init returns the same singleton (does not replace)."""
    reset_audit_log()
    log1 = init_audit_log(tmp_path)
    log2 = init_audit_log(tmp_path)
    assert log1 is log2


def test_reset_audit_log_clears_singleton(tmp_path: Path):
    reset_audit_log()
    init_audit_log(tmp_path)
    reset_audit_log()
    assert get_audit_log() is None
