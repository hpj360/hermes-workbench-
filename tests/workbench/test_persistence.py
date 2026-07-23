"""Tests for hermes.workbench.persistence atomic primitives."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from hermes.workbench.persistence import (
    atomic_append_jsonl,
    atomic_write_json,
    atomic_write_text,
    safe_read_json,
)


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    atomic_write_text(p, "hello world")
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "hello world"


def test_atomic_write_text_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "deep" / "nested" / "out.txt"
    atomic_write_text(p, "data")
    assert p.exists()
    assert p.parent.exists()


def test_atomic_write_text_overwrites_existing(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    atomic_write_text(p, "first")
    atomic_write_text(p, "second")
    assert p.read_text(encoding="utf-8") == "second"


def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    payload = {"k": "v", "n": 42, "nested": {"a": [1, 2, 3]}}
    atomic_write_json(p, payload)
    assert json.loads(p.read_text(encoding="utf-8")) == payload


def test_safe_read_json_missing_returns_default(tmp_path: Path) -> None:
    p = tmp_path / "nope.json"
    assert safe_read_json(p, default={"fallback": True}) == {"fallback": True}


def test_safe_read_json_corrupt_returns_default_and_backs_up(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    out = safe_read_json(p, default=None)
    assert out is None
    assert (tmp_path / "broken.json.corrupt").exists()
    assert not p.exists()


def test_safe_read_json_valid_returns_parsed(tmp_path: Path) -> None:
    p = tmp_path / "ok.json"
    atomic_write_json(p, {"hello": "world"})
    assert safe_read_json(p) == {"hello": "world"}


def test_safe_read_json_default_none_when_unspecified(tmp_path: Path) -> None:
    p = tmp_path / "missing.json"
    assert safe_read_json(p) is None


def test_atomic_append_jsonl_appends_one_line(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    atomic_append_jsonl(p, {"i": 1})
    assert p.exists()
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"i": 1}


def test_atomic_append_jsonl_multiple_appends(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    for i in range(5):
        atomic_append_jsonl(p, {"i": i})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    assert json.loads(lines[0]) == {"i": 0}
    assert json.loads(lines[4]) == {"i": 4}


def test_atomic_append_jsonl_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "deep" / "nested" / "log.jsonl"
    atomic_append_jsonl(p, {"x": 1})
    assert p.exists()
    assert p.parent.is_dir()


def test_atomic_append_jsonl_file_content_correct(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    atomic_append_jsonl(p, {"a": "1"})
    atomic_append_jsonl(p, {"b": "2"})
    text = p.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text.count("\n") == 2


def test_atomic_append_jsonl_concurrent_writes(tmp_path: Path) -> None:
    p = tmp_path / "concurrent.jsonl"
    n_threads = 10
    per_thread = 50

    def worker(tid: int) -> None:
        for i in range(per_thread):
            atomic_append_jsonl(p, {"tid": tid, "i": i})

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == n_threads * per_thread
    # Each line is valid JSON
    for line in lines:
        json.loads(line)
