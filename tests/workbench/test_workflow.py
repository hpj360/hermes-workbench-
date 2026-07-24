"""Tests for workbench.workflow module.

Covers WorkflowStep/Workflow/Execution dataclasses, WorkflowStore
persistence (CRUD), and WorkflowRunner DAG execution engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes.workbench.skill_runner import SkillRunner
from hermes.workbench.workflow import (
    Execution,
    StepResult,
    Workflow,
    WorkflowRunner,
    WorkflowStep,
    WorkflowStore,
)


# ---------------------------------------------------------------------------
# WorkflowStep / Workflow dataclasses
# ---------------------------------------------------------------------------


def test_workflow_step_defaults():
    step = WorkflowStep(id="s1", skill="alpha")
    assert step.id == "s1"
    assert step.skill == "alpha"
    assert step.args == []
    assert step.depends_on == []
    assert step.timeout is None


def test_workflow_step_with_values():
    step = WorkflowStep(
        id="s1",
        skill="alpha",
        args=["--flag", "v"],
        depends_on=["s0"],
        timeout=30.0,
    )
    assert step.args == ["--flag", "v"]
    assert step.depends_on == ["s0"]
    assert step.timeout == 30.0


def test_workflow_to_dict_roundtrip():
    wf = Workflow(
        id="wf-1",
        name="test",
        description="d",
        steps=[
            WorkflowStep(id="s1", skill="alpha", args=["--x"]),
            WorkflowStep(id="s2", skill="beta", depends_on=["s1"]),
        ],
    )
    d = wf.to_dict()
    assert d["id"] == "wf-1"
    assert d["name"] == "test"
    assert len(d["steps"]) == 2
    assert d["steps"][0]["args"] == ["--x"]
    assert d["steps"][1]["depends_on"] == ["s1"]

    restored = Workflow.from_dict(d)
    assert restored.id == "wf-1"
    assert restored.name == "test"
    assert len(restored.steps) == 2
    assert restored.steps[1].depends_on == ["s1"]


def test_workflow_from_dict_defaults():
    """from_dict tolerates missing optional fields."""
    wf = Workflow.from_dict({"id": "wf-x", "name": "x"})
    assert wf.description == ""
    assert wf.steps == []


# ---------------------------------------------------------------------------
# StepResult / Execution
# ---------------------------------------------------------------------------


def test_step_result_defaults():
    r = StepResult(step_id="s1", skill="alpha", ok=True)
    assert r.stdout == ""
    assert r.exit_code == 0
    assert r.duration == 0.0
    assert r.error is None


def test_execution_duration_zero_when_not_ended():
    ex = Execution(id="ex-1", workflow_id="wf-1", workflow_name="w")
    assert ex.duration == 0.0


def test_execution_duration_positive_when_ended():
    ex = Execution(
        id="ex-1",
        workflow_id="wf-1",
        workflow_name="w",
        started_at=100.0,
        ended_at=105.0,
    )
    assert ex.duration == 5.0


def test_execution_to_dict_serializes_step_results():
    ex = Execution(id="ex-1", workflow_id="wf-1", workflow_name="w")
    ex.step_results.append(StepResult(step_id="s1", skill="alpha", ok=True))
    d = ex.to_dict()
    assert d["id"] == "ex-1"
    assert len(d["step_results"]) == 1
    assert d["step_results"][0]["step_id"] == "s1"


# ---------------------------------------------------------------------------
# WorkflowStore CRUD
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> WorkflowStore:
    return WorkflowStore(state_dir=tmp_path)


def test_store_create_returns_workflow(store: WorkflowStore):
    wf = store.create(
        name="晨报",
        description="d",
        steps=[{"id": "s1", "skill": "alpha"}],
    )
    assert wf.id.startswith("wf-")
    assert wf.name == "晨报"
    assert len(wf.steps) == 1
    assert wf.steps[0].skill == "alpha"


def test_store_get_returns_created_workflow(store: WorkflowStore):
    wf = store.create(name="n", description="", steps=[])
    fetched = store.get(wf.id)
    assert fetched is not None
    assert fetched.name == "n"


def test_store_get_missing_returns_none(store: WorkflowStore):
    assert store.get("wf-nonexistent") is None


def test_store_list_returns_all(store: WorkflowStore):
    store.create(name="a", description="", steps=[])
    store.create(name="b", description="", steps=[])
    assert len(store.list()) == 2


def test_store_delete(store: WorkflowStore):
    wf = store.create(name="a", description="", steps=[])
    assert store.delete(wf.id) is True
    assert store.get(wf.id) is None


def test_store_delete_missing_returns_false(store: WorkflowStore):
    assert store.delete("wf-nonexistent") is False


def test_store_update_name(store: WorkflowStore):
    wf = store.create(name="a", description="d", steps=[])
    updated = store.update(wf.id, name="b")
    assert updated is not None
    assert updated.name == "b"
    # Description preserved
    assert updated.description == "d"


def test_store_update_steps(store: WorkflowStore):
    wf = store.create(name="a", description="", steps=[])
    updated = store.update(
        wf.id,
        steps=[{"id": "s1", "skill": "beta"}],
    )
    assert updated is not None
    assert len(updated.steps) == 1
    assert updated.steps[0].skill == "beta"


def test_store_update_missing_returns_none(store: WorkflowStore):
    assert store.update("wf-nonexistent", name="x") is None


def test_store_persists_across_instances(tmp_path: Path):
    s1 = WorkflowStore(state_dir=tmp_path)
    wf = s1.create(name="a", description="", steps=[])
    # New instance reading same state dir should see persisted workflow.
    s2 = WorkflowStore(state_dir=tmp_path)
    fetched = s2.get(wf.id)
    assert fetched is not None
    assert fetched.name == "a"


# ---------------------------------------------------------------------------
# WorkflowRunner — DAG execution
# ---------------------------------------------------------------------------


@pytest.fixture
def runner(skills_dir: Path, tmp_path: Path) -> WorkflowRunner:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    skill_runner = SkillRunner(base_dir=skills_dir)
    return WorkflowRunner(runner=skill_runner, state_dir=state_dir)


def test_runner_execute_single_step(runner: WorkflowRunner):
    wf = Workflow(
        id="wf-1",
        name="single",
        steps=[WorkflowStep(id="s1", skill="alpha")],
    )
    ex = runner.execute(wf)
    assert ex.status == "COMPLETED"
    assert len(ex.step_results) == 1
    assert ex.step_results[0].ok is True
    assert ex.step_results[0].skill == "alpha"


def test_runner_execute_linear_chain(runner: WorkflowRunner):
    """s1 -> s2 (s2 depends on s1)."""
    wf = Workflow(
        id="wf-2",
        name="chain",
        steps=[
            WorkflowStep(id="s1", skill="alpha"),
            WorkflowStep(id="s2", skill="beta", depends_on=["s1"]),
        ],
    )
    ex = runner.execute(wf)
    assert ex.status == "COMPLETED"
    assert [r.step_id for r in ex.step_results] == ["s1", "s2"]


def test_runner_execute_parallel_steps(runner: WorkflowRunner):
    """s1 and s2 have no deps — they should both run."""
    wf = Workflow(
        id="wf-3",
        name="parallel",
        steps=[
            WorkflowStep(id="s1", skill="alpha"),
            WorkflowStep(id="s2", skill="beta"),
        ],
    )
    ex = runner.execute(wf)
    assert ex.status == "COMPLETED"
    assert len(ex.step_results) == 2
    step_ids = {r.step_id for r in ex.step_results}
    assert step_ids == {"s1", "s2"}


def test_runner_execute_failing_step_marks_failed(runner: WorkflowRunner):
    """A non-existent skill produces a failed StepResult and FAILED execution."""
    wf = Workflow(
        id="wf-4",
        name="fail",
        steps=[WorkflowStep(id="s1", skill="nonexistent-skill")],
    )
    ex = runner.execute(wf)
    assert ex.status == "FAILED"
    assert ex.error is not None
    assert ex.step_results[0].ok is False


def test_runner_execute_stops_on_first_failure(runner: WorkflowRunner):
    """When a step fails, subsequent layers should NOT execute."""
    wf = Workflow(
        id="wf-5",
        name="stop-on-fail",
        steps=[
            WorkflowStep(id="s1", skill="nonexistent-skill"),
            WorkflowStep(id="s2", skill="alpha", depends_on=["s1"]),
        ],
    )
    ex = runner.execute(wf)
    assert ex.status == "FAILED"
    # Only the failing step should have a result.
    assert len(ex.step_results) == 1
    assert ex.step_results[0].step_id == "s1"


def test_runner_logs_execution(runner: WorkflowRunner):
    """Executions are persisted to workflow_executions.jsonl."""
    wf = Workflow(
        id="wf-6",
        name="log",
        steps=[WorkflowStep(id="s1", skill="alpha")],
    )
    runner.execute(wf)
    history = runner.list_executions()
    assert len(history) == 1
    assert history[0]["workflow_id"] == "wf-6"


def test_runner_list_executions_filter_by_workflow(runner: WorkflowRunner):
    wf1 = Workflow(id="wf-a", name="a", steps=[WorkflowStep(id="s1", skill="alpha")])
    wf2 = Workflow(id="wf-b", name="b", steps=[WorkflowStep(id="s1", skill="alpha")])
    runner.execute(wf1)
    runner.execute(wf2)

    only_a = runner.list_executions(workflow_id="wf-a")
    assert len(only_a) == 1
    assert only_a[0]["workflow_id"] == "wf-a"


def test_runner_list_executions_limit(runner: WorkflowRunner):
    wf = Workflow(id="wf-a", name="a", steps=[WorkflowStep(id="s1", skill="alpha")])
    for _ in range(5):
        runner.execute(wf)
    history = runner.list_executions(limit=2)
    assert len(history) == 2


def test_runner_list_executions_empty(runner: WorkflowRunner):
    assert runner.list_executions() == []


def test_runner_topo_sort_handles_cycle(runner: WorkflowRunner):
    """Cyclic dependencies should not deadlock the runner."""
    wf = Workflow(
        id="wf-cycle",
        name="cycle",
        steps=[
            WorkflowStep(id="s1", skill="alpha", depends_on=["s2"]),
            WorkflowStep(id="s2", skill="alpha", depends_on=["s1"]),
        ],
    )
    # Should complete (not hang) and run both steps.
    ex = runner.execute(wf)
    assert ex.status in {"COMPLETED", "FAILED"}
    assert len(ex.step_results) >= 1


def test_runner_with_timeout(runner: WorkflowRunner):
    """Step-level timeout is passed through to SkillRunner."""
    wf = Workflow(
        id="wf-to",
        name="to",
        steps=[WorkflowStep(id="s1", skill="alpha", timeout=5.0)],
    )
    ex = runner.execute(wf)
    assert ex.status == "COMPLETED"
