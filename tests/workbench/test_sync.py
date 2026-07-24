"""Tests for workbench.sync module.

Covers SyncResult dataclass and AssetSync engine (skills/memory/profile/all).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes.workbench.memory import MemoryService
from hermes.workbench.projects import ProjectRegistry
from hermes.workbench.skill_runner import SkillRunner
from hermes.workbench.sync import AssetSync, SyncResult


# ---------------------------------------------------------------------------
# SyncResult dataclass
# ---------------------------------------------------------------------------


def test_sync_result_defaults():
    r = SyncResult(source="a", target="b", asset_type="skills")
    assert r.synced == 0
    assert r.skipped == 0
    assert r.errors == []
    assert r.ok is True
    assert r.ended_at == 0.0
    # duration is computed in to_dict() only
    assert r.to_dict()["duration"] == 0.0


def test_sync_result_with_errors_not_ok():
    r = SyncResult(source="a", target="b", asset_type="skills")
    r.errors.append("boom")
    assert r.ok is False


def test_sync_result_to_dict():
    r = SyncResult(
        source="a",
        target="b",
        asset_type="memory",
        synced=3,
        skipped=1,
        errors=["e"],
        started_at=10.0,
        ended_at=15.0,
    )
    d = r.to_dict()
    assert d["synced"] == 3
    assert d["skipped"] == 1
    assert d["ok"] is False
    assert d["duration"] == 5.0


def test_sync_result_duration_zero_when_not_ended():
    r = SyncResult(source="a", target="b", asset_type="skills")
    assert r.to_dict()["duration"] == 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory(tmp_path: Path) -> MemoryService:
    """Memory service with an isolated in-memory profile (no writes to data/profile.json)."""
    state = tmp_path / "state"
    state.mkdir()
    profile_store: dict = {}

    def _load_profile() -> dict:
        return dict(profile_store)

    def _save_profile(profile: dict) -> None:
        profile_store.clear()
        profile_store.update(profile)

    return MemoryService(
        state_dir=state,
        profile_loader=_load_profile,
        profile_saver=_save_profile,
    )


@pytest.fixture
def registry(tmp_path: Path) -> ProjectRegistry:
    return ProjectRegistry(state_dir=tmp_path)


@pytest.fixture
def runner(skills_dir: Path) -> SkillRunner:
    return SkillRunner(base_dir=skills_dir)


@pytest.fixture
def sync_engine(
    registry: ProjectRegistry,
    runner: SkillRunner,
    memory: MemoryService,
) -> AssetSync:
    return AssetSync(registry=registry, runner=runner, memory=memory)


# ---------------------------------------------------------------------------
# sync_skills
# ---------------------------------------------------------------------------


def test_sync_skills_missing_source_returns_error(sync_engine: AssetSync):
    result = sync_engine.sync_skills("prj-nonexistent", "local")
    assert result.ok is False
    assert any("不存在" in e for e in result.errors)


def test_sync_skills_to_local(sync_engine: AssetSync, registry: ProjectRegistry):
    """Sync to 'local' target syncs local skill count without requiring target project."""
    src = registry.add(name="src", project_type="local", url="/tmp")
    result = sync_engine.sync_skills(src.id, "local")
    assert result.ok is True
    assert result.synced >= 1  # alpha + beta skills
    assert result.ended_at > 0


def test_sync_skills_to_registered_target_updates_count(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
):
    src = registry.add(name="src", project_type="local", url="/tmp")
    target = registry.add(name="target", project_type="local", url="/tmp")
    result = sync_engine.sync_skills(src.id, target.id)
    assert result.ok is True
    assert result.synced >= 1
    # Target project should have its skills_count updated
    fetched = registry.get(target.id)
    assert fetched.skills_count >= 1


# ---------------------------------------------------------------------------
# sync_memory
# ---------------------------------------------------------------------------


def test_sync_memory_missing_source_returns_error(sync_engine: AssetSync):
    result = sync_engine.sync_memory("prj-nonexistent", "local")
    assert result.ok is False
    assert any("不存在" in e for e in result.errors)


def test_sync_memory_copies_facts_with_prefix(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
    memory: MemoryService,
):
    """Facts are copied with a 'synced:<source_id>:' prefix."""
    src = registry.add(name="src", project_type="local", url="/tmp")
    memory.remember_fact("city", "Shanghai")
    memory.remember_fact("lang", "zh")

    result = sync_engine.sync_memory(src.id, "local")
    assert result.ok is True
    assert result.synced == 2

    # Each fact should be present with the prefix
    assert memory.get_fact(f"synced:{src.id}:city") is not None
    assert memory.get_fact(f"synced:{src.id}:lang") is not None


def test_sync_memory_no_facts(sync_engine: AssetSync, registry: ProjectRegistry):
    src = registry.add(name="src", project_type="local", url="/tmp")
    result = sync_engine.sync_memory(src.id, "local")
    assert result.ok is True
    assert result.synced == 0


def test_sync_memory_skips_facts_without_key(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
    memory: MemoryService,
):
    """Facts with empty key are skipped (defensive — list_facts never yields them)."""
    src = registry.add(name="src", project_type="local", url="/tmp")
    memory.remember_fact("valid", "v")
    result = sync_engine.sync_memory(src.id, "local")
    assert result.synced == 1


# ---------------------------------------------------------------------------
# sync_profile
# ---------------------------------------------------------------------------


def test_sync_profile_missing_source_skipped(
    sync_engine: AssetSync,
    memory: MemoryService,
):
    """Missing source projects are skipped, not erroring."""
    result = sync_engine.sync_profile(["prj-nonexistent"])
    assert result.ok is True
    assert result.skipped == 1
    assert result.synced == 0


def test_sync_profile_merges_project_config(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
    memory: MemoryService,
):
    """Profile fields in project.config are merged into the user profile."""
    src = registry.add(
        name="src",
        project_type="local",
        url="/tmp",
        config={"profile": {"name": "alice", "tz": "Asia/Shanghai"}},
    )
    result = sync_engine.sync_profile([src.id])
    assert result.ok is True
    profile = memory.get_user_profile()
    assert profile.get("name") == "alice"
    assert profile.get("tz") == "Asia/Shanghai"


def test_sync_profile_later_overrides_earlier(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
    memory: MemoryService,
):
    """When multiple projects set the same field, the later one wins."""
    a = registry.add(
        name="a",
        project_type="local",
        url="/tmp",
        config={"profile": {"name": "alice"}},
    )
    b = registry.add(
        name="b",
        project_type="local",
        url="/tmp",
        config={"profile": {"name": "bob"}},
    )
    sync_engine.sync_profile([a.id, b.id])
    profile = memory.get_user_profile()
    assert profile.get("name") == "bob"


def test_sync_profile_synced_count_increments_only_on_change(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
    memory: MemoryService,
):
    """A field that overrides an existing different value counts as 'synced'."""
    src = registry.add(
        name="src",
        project_type="local",
        url="/tmp",
        config={"profile": {"name": "alice"}},
    )
    # Pre-populate the user profile with a different value
    memory.save_user_profile({"name": "old-name"})
    result = sync_engine.sync_profile([src.id])
    assert result.synced == 1  # one field overridden


# ---------------------------------------------------------------------------
# sync_all
# ---------------------------------------------------------------------------


def test_sync_all_returns_three_results(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
):
    src = registry.add(name="src", project_type="local", url="/tmp")
    results = sync_engine.sync_all(src.id, "local")
    assert len(results) == 3
    asset_types = [r.asset_type for r in results]
    assert asset_types == ["skills", "memory", "profile"]


def test_sync_all_with_missing_source(
    sync_engine: AssetSync,
    registry: ProjectRegistry,
):
    """sync_all still returns 3 results even when source is missing."""
    results = sync_engine.sync_all("prj-nonexistent", "local")
    assert len(results) == 3
    assert all(not r.ok for r in results[:2])  # skills + memory error
