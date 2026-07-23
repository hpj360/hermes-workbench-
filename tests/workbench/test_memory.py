"""Tests for hermes.workbench.memory.MemoryService (L1/L2/L3)."""

from __future__ import annotations

from pathlib import Path

from hermes.workbench.memory import (
    Episode,
    MemoryService,
    make_episode,
)


def _make_service(tmp_path: Path) -> MemoryService:
    return MemoryService(state_dir=tmp_path / "state")


# ---------------------------------------------------------------------------
# Episode factory
# ---------------------------------------------------------------------------


def test_make_episode_generates_id_and_timestamp() -> None:
    ep = make_episode("loop", "ran a plan", {"steps": 2})
    assert isinstance(ep, Episode)
    assert ep.kind == "loop"
    assert ep.summary == "ran a plan"
    assert ep.details == {"steps": 2}
    assert isinstance(ep.id, str) and len(ep.id) > 0
    assert ep.created_at > 0


def test_make_episode_default_details_empty() -> None:
    ep = make_episode("note", "hi")
    assert ep.details == {}


def test_make_episode_ids_unique() -> None:
    a = make_episode("k", "a")
    b = make_episode("k", "b")
    assert a.id != b.id


# ---------------------------------------------------------------------------
# L1 facts
# ---------------------------------------------------------------------------


def test_remember_and_get_fact(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.remember_fact("color", "blue")
    fact = svc.get_fact("color")
    assert fact == {"key": "color", "value": "blue"}


def test_get_fact_missing_returns_none(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    assert svc.get_fact("nope") is None


def test_remember_fact_overwrites(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.remember_fact("k", 1)
    svc.remember_fact("k", 2)
    assert svc.get_fact("k") == {"key": "k", "value": 2}


def test_list_facts_empty(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    assert svc.list_facts() == []


def test_list_facts_returns_all(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.remember_fact("a", 1)
    svc.remember_fact("b", 2)
    facts = {f["key"]: f["value"] for f in svc.list_facts()}
    assert facts == {"a": 1, "b": 2}


def test_forget_fact_returns_true_when_present(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.remember_fact("k", "v")
    assert svc.forget_fact("k") is True
    assert svc.get_fact("k") is None


def test_forget_fact_returns_false_when_missing(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    assert svc.forget_fact("k") is False


def test_facts_persist_across_instances(tmp_path: Path) -> None:
    svc1 = _make_service(tmp_path)
    svc1.remember_fact("persisted", True)
    svc2 = _make_service(tmp_path)
    assert svc2.get_fact("persisted") == {"key": "persisted", "value": True}


def test_facts_survive_corrupt_file(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "facts.json").write_text("{ broken", encoding="utf-8")
    svc = MemoryService(state_dir=state)
    # Corrupt facts.json should be treated as empty
    assert svc.list_facts() == []


# ---------------------------------------------------------------------------
# L2 episodes
# ---------------------------------------------------------------------------


def test_record_and_list_episode(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    ep = make_episode("loop", "ran plan")
    svc.record_episode(ep)
    items = svc.list_episodes()
    assert len(items) == 1
    assert items[0].id == ep.id
    assert items[0].kind == "loop"
    assert items[0].summary == "ran plan"


def test_list_episodes_empty(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    assert svc.list_episodes() == []


def test_list_episodes_filter_by_kind(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.record_episode(make_episode("loop", "a"))
    svc.record_episode(make_episode("note", "b"))
    svc.record_episode(make_episode("loop", "c"))
    loops = svc.list_episodes(kind="loop")
    assert len(loops) == 2
    assert all(e.kind == "loop" for e in loops)


def test_list_episodes_returns_newest_first(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.record_episode(make_episode("k", "first"))
    svc.record_episode(make_episode("k", "second"))
    svc.record_episode(make_episode("k", "third"))
    items = svc.list_episodes()
    assert [e.summary for e in items] == ["third", "second", "first"]


def test_list_episodes_limit(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    for i in range(10):
        svc.record_episode(make_episode("k", f"ep{i}"))
    items = svc.list_episodes(limit=3)
    assert len(items) == 3
    # Newest first → last three recorded
    assert [e.summary for e in items] == ["ep9", "ep8", "ep7"]


def test_list_episodes_limit_zero_returns_empty(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.record_episode(make_episode("k", "x"))
    assert svc.list_episodes(limit=0) == []


# ---------------------------------------------------------------------------
# L3 profile
# ---------------------------------------------------------------------------


def test_get_user_profile_uses_injected_loader(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def loader() -> dict[str, object]:
        captured["called"] = True
        return {"version": 4, "basic_info": {"name": "Zoe"}}

    svc = MemoryService(state_dir=tmp_path / "state", profile_loader=loader)
    profile = svc.get_user_profile()
    assert profile == {"version": 4, "basic_info": {"name": "Zoe"}}
    assert captured.get("called") is True


def test_save_user_profile_uses_injected_saver(tmp_path: Path) -> None:
    saved: list[dict[str, object]] = []

    def saver(profile: dict[str, object]) -> None:
        saved.append(profile)

    svc = MemoryService(state_dir=tmp_path / "state", profile_saver=saver)
    svc.save_user_profile({"version": 4})
    assert saved == [{"version": 4}]


def test_get_user_profile_falls_back_to_hermes_profile(tmp_path: Path, tmp_state_dir: Path) -> None:
    svc = _make_service(tmp_state_dir)
    profile = svc.get_user_profile()
    assert isinstance(profile, dict)
    assert "basic_info" in profile
