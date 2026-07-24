"""Three-layer memory for the Workbench agent runtime.

L1 — Facts: small key/value JSON store for durable preferences and observations.
L2 — Episodes: append-only JSONL log of agent actions (each entry an Episode).
L3 — Profile: the user profile (delegated to hermes.profile).
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hermes.workbench.persistence import (
    atomic_append_jsonl,
    atomic_write_json,
    safe_read_json,
)


@dataclass
class Episode:
    """A single recorded agent event."""

    id: str
    kind: str
    summary: str
    details: dict[str, Any]
    created_at: float


def make_episode(kind: str, summary: str, details: dict[str, Any] | None = None) -> Episode:
    """Build a new Episode with a generated id and current timestamp."""
    return Episode(
        id=uuid.uuid4().hex,
        kind=kind,
        summary=summary,
        details=details if details is not None else {},
        created_at=time.time(),
    )


class MemoryService:
    """In-process memory service backed by atomic file persistence."""

    def __init__(
        self,
        state_dir: Path,
        profile_loader: Callable[[], dict[str, Any]] | None = None,
        profile_saver: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._facts_path = state_dir / "facts.json"
        self._episodes_path = state_dir / "episodes.jsonl"
        self._profile_loader = profile_loader
        self._profile_saver = profile_saver

    # ------------------------------------------------------------------
    # L1 — Facts
    # ------------------------------------------------------------------
    def remember_fact(self, key: str, value: Any) -> None:
        """Set (or overwrite) the value of fact *key*."""
        facts = self._read_facts()
        facts[key] = value
        atomic_write_json(self._facts_path, facts)

    def get_fact(self, key: str) -> dict[str, Any] | None:
        """Return ``{"key": key, "value": value}`` for *key*, or None if absent."""
        facts = self._read_facts()
        if key not in facts:
            return None
        return {"key": key, "value": facts[key]}

    def list_facts(self) -> list[dict[str, Any]]:
        """Return all facts as a list of ``{"key", "value"}`` dicts."""
        facts = self._read_facts()
        return [{"key": k, "value": v} for k, v in facts.items()]

    def forget_fact(self, key: str) -> bool:
        """Delete fact *key*. Returns True if it existed."""
        facts = self._read_facts()
        if key not in facts:
            return False
        del facts[key]
        atomic_write_json(self._facts_path, facts)
        return True

    def _read_facts(self) -> dict[str, Any]:
        data = safe_read_json(self._facts_path, default={})
        if isinstance(data, dict):
            return data
        return {}

    # ------------------------------------------------------------------
    # L2 — Episodes
    # ------------------------------------------------------------------
    def record_episode(self, episode: Episode) -> None:
        """Append *episode* to the JSONL episode log."""
        payload = {
            "id": episode.id,
            "kind": episode.kind,
            "summary": episode.summary,
            "details": episode.details,
            "created_at": episode.created_at,
        }
        atomic_append_jsonl(self._episodes_path, payload)

    def list_episodes(self, kind: str | None = None, limit: int = 1000) -> list[Episode]:
        """Return recorded episodes, optionally filtered by *kind*.

        The most recent *limit* matching episodes are returned, newest first.
        """
        if not self._episodes_path.exists():
            return []
        items: list[Episode] = []
        with self._episodes_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _parse_episode_line(line)
                except (ValueError, KeyError):
                    continue
                if kind is not None and obj.kind != kind:
                    continue
                items.append(obj)
        # Most recent first; cap via deque maxlen on the tail.
        if limit <= 0:
            return []
        recent = list(deque(items, maxlen=limit))
        recent.reverse()
        return recent

    # ------------------------------------------------------------------
    # L3 — Profile
    # ------------------------------------------------------------------
    def get_user_profile(self) -> dict[str, Any]:
        """Return the user profile (delegated to the configured loader)."""
        if self._profile_loader is not None:
            return self._profile_loader()
        from hermes.profile import load_profile
        return load_profile()

    def save_user_profile(self, profile: dict[str, Any]) -> None:
        """Persist *profile* (delegated to the configured saver)."""
        if self._profile_saver is not None:
            self._profile_saver(profile)
            return
        from hermes.profile import save_profile
        save_profile(profile)


def _parse_episode_line(line: str) -> Episode:
    """Parse a single JSONL line into an Episode."""
    import json
    obj = json.loads(line)
    if not isinstance(obj, dict):
        raise TypeError("episode line is not an object")
    details = obj.get("details", {})
    if not isinstance(details, dict):
        details = {"value": details}
    return Episode(
        id=str(obj["id"]),
        kind=str(obj["kind"]),
        summary=str(obj.get("summary", "")),
        details=details,
        created_at=float(obj.get("created_at", 0.0)),
    )
