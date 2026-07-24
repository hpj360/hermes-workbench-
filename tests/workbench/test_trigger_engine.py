"""Tests for workbench.trigger_engine module.

Covers CronScheduler (cron expression matching), TriggerEngine
(manual fire / webhook fire), and global singleton helpers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from hermes.workbench.skill_runner import SkillRunner
from hermes.workbench.trigger_engine import (
    CronScheduler,
    TriggerEngine,
    get_trigger_engine,
    init_trigger_engine,
    stop_trigger_engine,
)
from hermes.workbench.triggers import TriggerStore
from hermes.workbench.workflow import Workflow, WorkflowRunner, WorkflowStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trigger_store(tmp_path: Path) -> TriggerStore:
    return TriggerStore(state_dir=tmp_path)


@pytest.fixture
def workflow_store(tmp_path: Path) -> WorkflowStore:
    return WorkflowStore(state_dir=tmp_path)


@pytest.fixture
def workflow_runner(skills_dir: Path, tmp_path: Path) -> WorkflowRunner:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    runner = SkillRunner(base_dir=skills_dir)
    return WorkflowRunner(runner=runner, state_dir=state_dir)


@pytest.fixture
def engine(
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
    workflow_runner: WorkflowRunner,
) -> TriggerEngine:
    return TriggerEngine(
        trigger_store=trigger_store,
        workflow_store=workflow_store,
        workflow_runner=workflow_runner,
    )


def _make_workflow(store: WorkflowStore, name: str = "w") -> Workflow:
    return store.create(
        name=name,
        description="",
        steps=[{"id": "s1", "skill": "alpha"}],
    )


# ---------------------------------------------------------------------------
# CronScheduler._matches_cron
# ---------------------------------------------------------------------------


def test_matches_cron_star_matches_anything():
    """``* * * * *`` matches every datetime."""
    dt = datetime(2026, 7, 25, 9, 30)  # Saturday
    assert CronScheduler._matches_cron("* * * * *", dt)


def test_matches_cron_specific_minute_hour():
    dt = datetime(2026, 7, 25, 9, 30)  # Saturday
    assert CronScheduler._matches_cron("30 9 * * *", dt)
    assert not CronScheduler._matches_cron("31 9 * * *", dt)
    assert not CronScheduler._matches_cron("30 10 * * *", dt)


def test_matches_cron_specific_day_of_month():
    dt = datetime(2026, 7, 25, 9, 30)
    assert CronScheduler._matches_cron("30 9 25 * *", dt)
    assert not CronScheduler._matches_cron("30 9 26 * *", dt)


def test_matches_cron_specific_month():
    dt = datetime(2026, 7, 25, 9, 30)
    assert CronScheduler._matches_cron("30 9 25 7 *", dt)
    assert not CronScheduler._matches_cron("30 9 25 8 *", dt)


def test_matches_cron_weekday_sunday_is_zero():
    """2026-07-05 is a Sunday — weekday field 0 should match."""
    dt = datetime(2026, 7, 5, 9, 30)  # Sunday
    assert CronScheduler._matches_cron("30 9 * * 0", dt)
    assert not CronScheduler._matches_cron("30 9 * * 1", dt)


def test_matches_cron_invalid_field_count_returns_false():
    assert not CronScheduler._matches_cron("* * *", datetime.now())
    assert not CronScheduler._matches_cron("* * * * * *", datetime.now())


def test_matches_cron_non_numeric_field_returns_false():
    assert not CronScheduler._matches_cron("abc * * * *", datetime.now())


# ---------------------------------------------------------------------------
# CronScheduler lifecycle
# ---------------------------------------------------------------------------


def test_cron_scheduler_start_stop(trigger_store: TriggerStore):
    """start/stop should not raise and should leave no lingering thread."""
    sched = CronScheduler(trigger_store, fire_callback=lambda _: None, check_interval=0.05)
    sched.start()
    sched.stop()  # should not block


def test_cron_scheduler_start_idempotent(trigger_store: TriggerStore):
    sched = CronScheduler(trigger_store, fire_callback=lambda _: None, check_interval=0.05)
    sched.start()
    sched.start()  # second start should be a no-op
    sched.stop()


def test_cron_scheduler_fires_matching_trigger(
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    """A cron trigger whose schedule matches the current minute should fire."""
    fired: list = []
    workflow_store.create(name="w", description="", steps=[{"id": "s1", "skill": "alpha"}])
    wf = workflow_store.list()[0]
    now = datetime.now()
    trigger_store.create(
        workflow_id=wf.id,
        trigger_type="cron",
        config={"schedule": f"{now.minute} {now.hour} * * *"},
    )
    sched = CronScheduler(trigger_store, fire_callback=fired.append, check_interval=0.05)
    sched.start()
    # Wait briefly to allow one check cycle
    import time
    time.sleep(0.1)
    sched.stop()
    assert len(fired) >= 1


def test_cron_scheduler_skips_disabled_trigger(
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    fired: list = []
    workflow_store.create(name="w", description="", steps=[{"id": "s1", "skill": "alpha"}])
    wf = workflow_store.list()[0]
    now = datetime.now()
    t = trigger_store.create(
        workflow_id=wf.id,
        trigger_type="cron",
        config={"schedule": f"{now.minute} {now.hour} * * *"},
    )
    trigger_store.toggle(t.id, enabled=False)
    sched = CronScheduler(trigger_store, fire_callback=fired.append, check_interval=0.05)
    sched.start()
    import time
    time.sleep(0.1)
    sched.stop()
    assert fired == []


# ---------------------------------------------------------------------------
# TriggerEngine.fire (manual)
# ---------------------------------------------------------------------------


def test_engine_fire_missing_trigger_returns_none(engine: TriggerEngine):
    assert engine.fire("tr-nonexistent") is None


def test_engine_fire_executes_workflow(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "cron", {"schedule": "* * * * *"})

    result = engine.fire(t.id)
    assert result is not None
    assert result["trigger_id"] == t.id
    assert result["workflow_id"] == wf.id
    assert result["status"] in {"COMPLETED", "FAILED"}
    assert "execution_id" in result


def test_engine_fire_increments_fire_count(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "cron", {})
    engine.fire(t.id)
    engine.fire(t.id)
    fetched = trigger_store.get(t.id)
    assert fetched.fire_count == 2


def test_engine_fire_workflow_missing_returns_error(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
):
    t = trigger_store.create("wf-nonexistent", "cron", {})
    result = engine.fire(t.id)
    assert result is not None
    assert "error" in result
    assert result["error"] == "workflow not found"


# ---------------------------------------------------------------------------
# TriggerEngine.fire_by_webhook
# ---------------------------------------------------------------------------


def test_engine_webhook_missing_trigger_returns_none(engine: TriggerEngine):
    assert engine.fire_by_webhook("tr-nonexistent", payload={}) is None


def test_engine_webhook_disabled_trigger_returns_none(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "webhook", {"secret": "s"})
    trigger_store.toggle(t.id, enabled=False)
    assert engine.fire_by_webhook(t.id, payload={}, signature="s") is None


def test_engine_webhook_wrong_type_returns_none(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    """Cron triggers cannot be fired via webhook."""
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "cron", {})
    assert engine.fire_by_webhook(t.id, payload={}) is None


def test_engine_webhook_signature_mismatch_returns_error(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "webhook", {"secret": "expected"})
    result = engine.fire_by_webhook(t.id, payload={}, signature="wrong")
    assert result is not None
    assert "error" in result
    assert "signature" in result["error"]


def test_engine_webhook_no_secret_skips_signature_check(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    """When no secret is configured, webhook fires without signature."""
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "webhook", {})
    result = engine.fire_by_webhook(t.id, payload={})
    assert result is not None
    assert result["status"] in {"COMPLETED", "FAILED"}


def test_engine_webhook_valid_signature_fires(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "webhook", {"secret": "abc"})
    result = engine.fire_by_webhook(t.id, payload={}, signature="abc")
    assert result is not None
    assert result["trigger_id"] == t.id


def test_engine_github_trigger_can_fire_via_webhook(
    engine: TriggerEngine,
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
):
    """GitHub triggers reuse the webhook fire path."""
    wf = _make_workflow(workflow_store)
    t = trigger_store.create(wf.id, "github", {"repo": "owner/repo"})
    result = engine.fire_by_webhook(t.id, payload={"action": "opened"})
    assert result is not None
    assert result["status"] in {"COMPLETED", "FAILED"}


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------


def test_get_trigger_engine_returns_none_before_init():
    stop_trigger_engine()  # ensure clean state
    assert get_trigger_engine() is None


def test_init_and_stop_trigger_engine(
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
    workflow_runner: WorkflowRunner,
):
    stop_trigger_engine()
    engine = init_trigger_engine(
        trigger_store=trigger_store,
        workflow_store=workflow_store,
        workflow_runner=workflow_runner,
        auto_start=False,
    )
    assert get_trigger_engine() is engine
    stop_trigger_engine()
    assert get_trigger_engine() is None


def test_init_trigger_engine_replaces_existing(
    trigger_store: TriggerStore,
    workflow_store: WorkflowStore,
    workflow_runner: WorkflowRunner,
):
    stop_trigger_engine()
    e1 = init_trigger_engine(
        trigger_store=trigger_store,
        workflow_store=workflow_store,
        workflow_runner=workflow_runner,
        auto_start=False,
    )
    e2 = init_trigger_engine(
        trigger_store=trigger_store,
        workflow_store=workflow_store,
        workflow_runner=workflow_runner,
        auto_start=False,
    )
    assert e1 is not e2
    assert get_trigger_engine() is e2
    stop_trigger_engine()


# ---------------------------------------------------------------------------
# Engine start/stop
# ---------------------------------------------------------------------------


def test_engine_start_stop_is_safe(engine: TriggerEngine):
    """start/stop should not raise."""
    engine.start()
    engine.stop()


def test_engine_stop_without_start_is_safe(engine: TriggerEngine):
    engine.stop()  # no-op, should not raise
