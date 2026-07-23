"""Atomic file persistence primitives.

All Workbench state (facts, episodes, tasks, plans) is persisted via these
helpers to survive crashes and concurrent access:
- atomic_write_text / atomic_write_json: tempfile + os.replace
- safe_read_json: returns default on missing/corrupt, backs up corrupt as *.corrupt
- atomic_append_jsonl: fcntl.flock(LOCK_EX) guarded append
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str) -> None:
    """Write *content* to *path* atomically (tempfile + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    """Serialize *obj* to JSON and write atomically to *path*."""
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    atomic_write_text(path, text)


def safe_read_json(path: Path, default: Any = None) -> Any:
    """Read JSON from *path*. Return *default* if missing or corrupt.

    Corrupt files are renamed to ``<path>.corrupt`` for later inspection.
    """
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        corrupt = path.with_suffix(path.suffix + ".corrupt")
        try:
            os.replace(path, corrupt)
        except OSError:
            pass
        return default


def atomic_append_jsonl(path: Path, obj: Any) -> None:
    """Append *obj* as a JSON line to *path*, guarded by an exclusive flock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        except ImportError:
            # fcntl not available on Windows; best-effort append.
            f.write(line)
            f.flush()
