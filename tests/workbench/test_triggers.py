"""Tests for workbench.triggers module.

Covers Trigger dataclass serialization and TriggerStore CRUD operations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes.workbench.triggers import Trigger, TriggerStore


# ---------------------------------------------------------------------------
# Trigger dataclass
# ---------------------------------------------------------------------------


def test_trigger_defaults():
    t = Trigger(id="tr-1", workflow_id="wf-1", type="cron")
    assert t.config == {}
    assert t.enabled is True
    assert t.last_fired == 0.0
    assert t.fire_count == 0


def test_trigger_to_dict_roundtrip():
    t = Trigger(
        id="tr-1",
        workflow_id="wf-1",
        type="github",
        config={"repo": "owner/repo"},
        enabled=False,
    )
    d = t.to_dict()
    assert d["id"] == "tr-1"
    assert d["type"] == "github"
    assert d["enabled"] is False
    assert d["config"] == {"repo": "owner/repo"}

    restored = Trigger.from_dict(d)
    assert restored.id == "tr-1"
    assert restored.type == "github"
    assert restored.enabled is False
    assert restored.config == {"repo": "owner/repo"}


def test_trigger_from_dict_tolerates_missing_optional_fields():
    t = Trigger.from_dict({"id": "tr-x", "workflow_id": "wf-x", "type": "cron"})
    assert t.config == {}
    assert t.enabled is True
    assert t.fire_count == 0


# ---------------------------------------------------------------------------
# TriggerStore CRUD
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> TriggerStore:
    return TriggerStore(state_dir=tmp_path)


def test_store_create_github_trigger(store: TriggerStore):
    t = store.create(
        workflow_id="wf-1",
        trigger_type="github",
        config={"repo": "owner/repo", "label": "workbench"},
    )
    assert t.id.startswith("tr-")
    assert t.type == "github"
    assert t.workflow_id == "wf-1"


def test_store_create_cron_trigger(store: TriggerStore):
    t = store.create(
        workflow_id="wf-1",
        trigger_type="cron",
        config={"schedule": "0 9 * * 1-5"},
    )
    assert t.type == "cron"
    assert t.config["schedule"] == "0 9 * * 1-5"


def test_store_create_webhook_trigger(store: TriggerStore):
    t = store.create(
        workflow_id="wf-1",
        trigger_type="webhook",
        config={"secret": "xxx"},
    )
    assert t.type == "webhook"


def test_store_create_invalid_type_raises(store: TriggerStore):
    with pytest.raises(ValueError, match="无效的触发器类型"):
        store.create(
            workflow_id="wf-1",
            trigger_type="invalid",
            config={},
        )


def test_store_get_returns_created(store: TriggerStore):
    t = store.create("wf-1", "cron", {"schedule": "* * * * *"})
    fetched = store.get(t.id)
    assert fetched is not None
    assert fetched.type == "cron"


def test_store_get_missing_returns_none(store: TriggerStore):
    assert store.get("tr-nonexistent") is None


def test_store_list_all(store: TriggerStore):
    store.create("wf-1", "cron", {})
    store.create("wf-2", "github", {})
    assert len(store.list()) == 2


def test_store_list_filtered_by_workflow(store: TriggerStore):
    store.create("wf-1", "cron", {})
    store.create("wf-1", "github", {})
    store.create("wf-2", "cron", {})
    only_wf1 = store.list(workflow_id="wf-1")
    assert len(only_wf1) == 2
    assert all(t.workflow_id == "wf-1" for t in only_wf1)


def test_store_list_filtered_with_nonexistent_workflow(store: TriggerStore):
    store.create("wf-1", "cron", {})
    assert store.list(workflow_id="wf-nonexistent") == []


def test_store_delete(store: TriggerStore):
    t = store.create("wf-1", "cron", {})
    assert store.delete(t.id) is True
    assert store.get(t.id) is None


def test_store_delete_missing_returns_false(store: TriggerStore):
    assert store.delete("tr-nonexistent") is False


def test_store_toggle_enable_disable(store: TriggerStore):
    t = store.create("wf-1", "cron", {})
    disabled = store.toggle(t.id, enabled=False)
    assert disabled is not None
    assert disabled.enabled is False
    # Persisted
    assert store.get(t.id).enabled is False

    enabled = store.toggle(t.id, enabled=True)
    assert enabled.enabled is True


def test_store_toggle_missing_returns_none(store: TriggerStore):
    assert store.toggle("tr-nonexistent", enabled=False) is None


def test_store_mark_fired_increments_count(store: TriggerStore):
    t = store.create("wf-1", "cron", {})
    store.mark_fired(t.id)
    store.mark_fired(t.id)
    fetched = store.get(t.id)
    assert fetched.fire_count == 2
    assert fetched.last_fired > 0


def test_store_mark_fired_missing_is_noop(store: TriggerStore):
    """Marking a non-existent trigger should not raise."""
    store.mark_fired("tr-nonexistent")  # should not raise


def test_store_persists_across_instances(tmp_path: Path):
    s1 = TriggerStore(state_dir=tmp_path)
    t = s1.create("wf-1", "cron", {"schedule": "* * * * *"})
    s2 = TriggerStore(state_dir=tmp_path)
    fetched = s2.get(t.id)
    assert fetched is not None
    assert fetched.config["schedule"] == "* * * * *"
