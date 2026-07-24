"""Tests for hermes.workbench.cli (commands, parsers, task runtime)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from hermes.workbench import cli as wb_cli
from hermes.workbench.agent_loop import LoopResult, LoopStep, LoopStepResult
from hermes.workbench.cli import (
    Task,
    TaskRegistry,
    TaskScheduler,
    TaskStore,
    add_workbench_subparser,
    cmd_workbench_loop,
    cmd_workbench_memory_episodes_list,
    cmd_workbench_memory_facts_forget,
    cmd_workbench_memory_facts_get,
    cmd_workbench_memory_facts_list,
    cmd_workbench_memory_facts_remember,
    cmd_workbench_memory_profile_show,
    cmd_workbench_run,
    cmd_workbench_serve,
    cmd_workbench_skills_list,
    cmd_workbench_skills_show,
    cmd_workbench_task_cancel,
    cmd_workbench_task_list,
    cmd_workbench_task_register,
    cmd_workbench_task_run,
    cmd_workbench_task_show,
    register_workbench_commands,
    workbench_main,
)
from hermes.workbench.memory import MemoryService
from hermes.workbench.skill_runner import RunResult, SkillSpec

# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


def _spec(name: str, runtime: str = "prompt", description: str = "d") -> SkillSpec:
    return SkillSpec(
        name=name,
        path=Path("/tmp") / name,
        description=description,
        runtime=runtime,
        requires_bins=[],
        requires_env=[],
        entrypoint=None,
        raw_metadata={},
    )


def _run_result_ok(skill: str, stdout: str = "out") -> RunResult:
    return RunResult(
        skill=skill, ok=True, stdout=stdout, stderr="", exit_code=0, duration=0.01, error=None
    )


def _run_result_fail(skill: str, err: str = "boom") -> RunResult:
    return RunResult(
        skill=skill, ok=False, stdout="", stderr=err, exit_code=1, duration=0.01, error=err
    )


def _loop_result_ok() -> LoopResult:
    return LoopResult(
        steps=[LoopStepResult(skill="alpha", ok=True, error=None, duration=0.01)],
        ok=True,
        started_at=1.0,
        ended_at=2.0,
        error=None,
    )


class FakeRunner:
    """Minimal SkillRunner-like fake returning scripted results."""

    def __init__(self, specs: list[SkillSpec], results: dict[str, RunResult]) -> None:
        self._specs = specs
        self._results = results
        self.calls: list[tuple[str, list[str], float | None]] = []

    def discover(self) -> list[SkillSpec]:
        return list(self._specs)

    def get(self, name: str) -> SkillSpec | None:
        for s in self._specs:
            if s.name == name:
                return s
        return None

    def run(
        self, name: str, args: list[str] | None = None, timeout: float | None = None
    ) -> RunResult:
        self.calls.append((name, list(args or []), timeout))
        return self._results.get(
            name,
            _run_result_fail(name, f"skill not found: {name}"),
        )


def _patch_factories(
    monkeypatch: pytest.MonkeyPatch,
    state_dir: Path,
    runner: FakeRunner | None = None,
    memory: MemoryService | None = None,
) -> tuple[FakeRunner, MemoryService]:
    """Patch the module-level CLI factories to use *state_dir* and *runner*."""
    runner = runner or FakeRunner([], {})
    memory = memory or MemoryService(state_dir=state_dir)
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    monkeypatch.setattr(wb_cli, "_make_memory", lambda: memory)
    monkeypatch.setattr(wb_cli, "_make_loop", lambda: _LoopFactory(runner, memory))
    monkeypatch.setattr(wb_cli, "_make_store", lambda: TaskStore(state_dir=state_dir))
    monkeypatch.setattr(wb_cli, "_make_registry", lambda: TaskRegistry())
    return runner, memory


class _LoopFactory:
    """Callable that builds an AgentLoop-like object returning a fixed result."""

    def __init__(self, runner: FakeRunner, memory: MemoryService) -> None:
        self.runner = runner
        self.memory = memory
        self.result: LoopResult = _loop_result_ok()

    def __call__(self) -> _LoopFactory:
        return self

    def execute(
        self, plan: list[LoopStep], record_episode: bool = True
    ) -> LoopResult:
        # Drive the runner so calls are observable but ignore the real loop logic.
        for step in plan:
            self.runner.run(step.skill, args=step.args, timeout=step.timeout)
        return self.result


def _ns(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------


def test_task_to_dict_contains_all_fields() -> None:
    task = Task(
        task_id="t1",
        plan=[{"skill": "alpha"}],
        mode="oneshot",
        max_rounds=3,
        max_runs=2,
        interval=5.0,
    )
    d = task.to_dict()
    assert d["task_id"] == "t1"
    assert d["plan"] == [{"skill": "alpha"}]
    assert d["mode"] == "oneshot"
    assert d["max_rounds"] == 3
    assert d["max_runs"] == 2
    assert d["interval"] == 5.0
    assert d["status"] == "PENDING"
    assert d["rounds"] == []
    assert "created_at" in d


def test_task_default_status_is_pending() -> None:
    task = Task(task_id="t", plan=[])
    assert task.status == "PENDING"
    assert task.rounds == []
    assert task.mode == "oneshot"
    assert task.max_rounds == 1
    assert task.max_runs == 1
    assert task.interval == 0.0


# ---------------------------------------------------------------------------
# TaskStore
# ---------------------------------------------------------------------------


def test_task_store_save_and_get(tmp_path: Path) -> None:
    store = TaskStore(state_dir=tmp_path)
    task = Task(task_id="t1", plan=[{"skill": "alpha"}])
    store.save(task)
    got = store.get("t1")
    assert got is not None
    assert got["task_id"] == "t1"
    assert got["plan"] == [{"skill": "alpha"}]


def test_task_store_get_returns_none_for_missing(tmp_path: Path) -> None:
    store = TaskStore(state_dir=tmp_path)
    assert store.get("nope") is None


def test_task_store_list_returns_all(tmp_path: Path) -> None:
    store = TaskStore(state_dir=tmp_path)
    store.save(Task(task_id="t1", plan=[]))
    store.save(Task(task_id="t2", plan=[]))
    ids = sorted(t["task_id"] for t in store.list())
    assert ids == ["t1", "t2"]


def test_task_store_update_status_existing(tmp_path: Path) -> None:
    store = TaskStore(state_dir=tmp_path)
    store.save(Task(task_id="t1", plan=[]))
    assert store.update_status("t1", "COMPLETED") is True
    assert store.get("t1")["status"] == "COMPLETED"


def test_task_store_update_status_missing_returns_false(tmp_path: Path) -> None:
    store = TaskStore(state_dir=tmp_path)
    assert store.update_status("nope", "COMPLETED") is False


def test_task_store_loads_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text(
        json.dumps({"t1": {"task_id": "t1", "plan": [], "status": "PENDING"}}),
        encoding="utf-8",
    )
    store = TaskStore(state_dir=tmp_path)
    got = store.get("t1")
    assert got is not None
    assert got["task_id"] == "t1"


def test_task_store_handles_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "tasks.json").write_text("not json", encoding="utf-8")
    store = TaskStore(state_dir=tmp_path)
    assert store.list() == []


def test_task_store_persists_to_disk(tmp_path: Path) -> None:
    store = TaskStore(state_dir=tmp_path)
    store.save(Task(task_id="t1", plan=[{"skill": "alpha"}]))
    # A fresh store reading the same file must see the saved task.
    store2 = TaskStore(state_dir=tmp_path)
    assert store2.get("t1") is not None


# ---------------------------------------------------------------------------
# TaskRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get() -> None:
    reg = TaskRegistry()
    task = Task(task_id="t1", plan=[])
    assert reg.register(task) is task
    assert reg.get("t1") is task


def test_registry_get_returns_none_for_missing() -> None:
    reg = TaskRegistry()
    assert reg.get("nope") is None


def test_registry_list_returns_all() -> None:
    reg = TaskRegistry()
    reg.register(Task(task_id="t1", plan=[]))
    reg.register(Task(task_id="t2", plan=[]))
    assert sorted(t.task_id for t in reg.list()) == ["t1", "t2"]


# ---------------------------------------------------------------------------
# TaskScheduler
# ---------------------------------------------------------------------------


def test_scheduler_run_existing_task(tmp_path: Path) -> None:
    runner = FakeRunner([], {"alpha": _run_result_ok("alpha", "hello")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(task_id="t1", plan=[{"skill": "alpha"}])
    reg.register(task)
    result = sched.run("t1")
    assert isinstance(result, LoopResult)
    assert task.status == "COMPLETED"
    assert len(task.rounds) == 1
    assert task.rounds[0]["ok"] is True


def test_scheduler_run_missing_task_returns_none(tmp_path: Path) -> None:
    runner = FakeRunner([], {})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    assert sched.run("nope") is None


def test_scheduler_run_failed_task_marks_failed(tmp_path: Path) -> None:
    runner = FakeRunner([], {"alpha": _run_result_fail("alpha", "err")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(task_id="t1", plan=[{"skill": "alpha"}])
    reg.register(task)
    sched.run("t1")
    assert task.status == "FAILED"
    assert task.rounds[0]["ok"] is False


def test_scheduler_cancel_existing(tmp_path: Path) -> None:
    runner = FakeRunner([], {})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(task_id="t1", plan=[])
    reg.register(task)
    store.save(task)
    assert sched.cancel("t1") is True
    assert task.status == "CANCELLED"
    assert store.get("t1")["status"] == "CANCELLED"


def test_scheduler_cancel_missing_returns_false(tmp_path: Path) -> None:
    runner = FakeRunner([], {})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    assert sched.cancel("nope") is False


def test_scheduler_list_rounds_existing(tmp_path: Path) -> None:
    runner = FakeRunner([], {"alpha": _run_result_ok("alpha")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(task_id="t1", plan=[{"skill": "alpha"}])
    reg.register(task)
    sched.run("t1")
    rounds = sched.list_rounds("t1")
    assert len(rounds) == 1
    assert rounds[0]["ok"] is True


def test_scheduler_list_rounds_missing_returns_empty(tmp_path: Path) -> None:
    runner = FakeRunner([], {})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    assert sched.list_rounds("nope") == []


# ---------------------------------------------------------------------------
# TaskScheduler: recurring mode
# ---------------------------------------------------------------------------


def test_scheduler_recurring_runs_multiple_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FakeRunner([], {"alpha": _run_result_ok("alpha")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(
        task_id="t1",
        plan=[{"skill": "alpha"}],
        mode="recurring",
        max_runs=3,
        interval=1.5,
    )
    reg.register(task)
    sleeps: list[float] = []
    monkeypatch.setattr(wb_cli.time, "sleep", lambda s: sleeps.append(s))
    result = sched.run("t1")
    assert task.status == "COMPLETED"
    assert len(task.rounds) == 3
    assert all(r["ok"] is True for r in task.rounds)
    # sleep happens between runs, never after the last one
    assert sleeps == [1.5, 1.5]
    # the single-step plan runs once per round
    assert len(runner.calls) == 3
    assert isinstance(result, LoopResult)


def test_scheduler_recurring_respects_max_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FakeRunner([], {"alpha": _run_result_ok("alpha")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(
        task_id="t1",
        plan=[{"skill": "alpha"}],
        mode="recurring",
        max_runs=5,
        interval=2.0,
    )
    reg.register(task)
    monkeypatch.setattr(wb_cli.time, "sleep", lambda s: None)
    sched.run("t1")
    assert task.status == "COMPLETED"
    assert len(task.rounds) == 5
    assert len(runner.calls) == 5


def test_scheduler_oneshot_runs_once_even_with_recurring_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FakeRunner([], {"alpha": _run_result_ok("alpha")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(
        task_id="t1",
        plan=[{"skill": "alpha"}],
        mode="oneshot",
        max_runs=5,
        interval=1.0,
    )
    reg.register(task)
    sleeps: list[float] = []
    monkeypatch.setattr(wb_cli.time, "sleep", lambda s: sleeps.append(s))
    sched.run("t1")
    assert task.status == "COMPLETED"
    assert len(task.rounds) == 1
    assert sleeps == []
    assert len(runner.calls) == 1


def test_scheduler_recurring_failure_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FakeRunner([], {"alpha": _run_result_fail("alpha", "boom")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    task = Task(
        task_id="t1",
        plan=[{"skill": "alpha"}],
        mode="recurring",
        max_runs=3,
        interval=0.5,
    )
    reg.register(task)
    monkeypatch.setattr(wb_cli.time, "sleep", lambda s: None)
    sched.run("t1")
    assert task.status == "FAILED"
    assert len(task.rounds) == 3
    assert all(r["ok"] is False for r in task.rounds)


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------


def test_make_runner_uses_skills_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Path] = {}

    class FakeSkillRunner:
        def __init__(self, base_dir: Path) -> None:
            captured["base_dir"] = base_dir

    monkeypatch.setattr(wb_cli, "SkillRunner", FakeSkillRunner)
    expected = Path("/some/skills")
    monkeypatch.setattr(wb_cli, "_hermes_skills_dir", lambda: expected)
    wb_cli._make_runner()
    assert captured["base_dir"] == expected


def test_make_memory_uses_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wb_cli, "_state_dir", lambda: tmp_path)
    mem = wb_cli._make_memory()
    assert isinstance(mem, MemoryService)
    assert mem.state_dir == tmp_path


def test_make_store_uses_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wb_cli, "_state_dir", lambda: tmp_path)
    store = wb_cli._make_store()
    assert isinstance(store, TaskStore)
    assert store.state_dir == tmp_path


def test_make_registry_returns_empty() -> None:
    reg = wb_cli._make_registry()
    assert isinstance(reg, TaskRegistry)
    assert reg.list() == []


def test_make_scheduler_wires_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wb_cli, "_state_dir", lambda: tmp_path)
    sched = wb_cli._make_scheduler()
    assert isinstance(sched, TaskScheduler)
    assert isinstance(sched.store, TaskStore)
    assert isinstance(sched.registry, TaskRegistry)


# ---------------------------------------------------------------------------
# Command handlers: skills
# ---------------------------------------------------------------------------


def test_cmd_skills_list_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner([], {})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = cmd_workbench_skills_list(_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "no skills" in out


def test_cmd_skills_list_with_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner([_spec("alpha", "prompt", "alpha desc")], {})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = cmd_workbench_skills_list(_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "alpha desc" in out


def test_cmd_skills_show_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([_spec("alpha", "python", "alpha desc")], {})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = cmd_workbench_skills_show(_ns(name="alpha"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "python" in out


def test_cmd_skills_show_missing_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = cmd_workbench_skills_show(_ns(name="nope"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


# ---------------------------------------------------------------------------
# Command handlers: run
# ---------------------------------------------------------------------------


def test_cmd_run_ok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {"alpha": _run_result_ok("alpha", "ran-ok")})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = cmd_workbench_run(_ns(name="alpha", args=[], timeout=None))
    assert rc == 0
    out = capsys.readouterr().out
    assert "ran-ok" in out


def test_cmd_run_fail_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {"alpha": _run_result_fail("alpha", "err-text")})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = cmd_workbench_run(_ns(name="alpha", args=[], timeout=None))
    assert rc == 1
    err = capsys.readouterr().err
    assert "err-text" in err


# ---------------------------------------------------------------------------
# Command handlers: loop
# ---------------------------------------------------------------------------


def test_cmd_loop_with_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner, _ = _patch_factories(monkeypatch, tmp_path / "state")
    plan = json.dumps([{"skill": "alpha", "args": ["x"]}])
    rc = cmd_workbench_loop(_ns(plan=plan, plan_file=None))
    assert rc == 0
    out = capsys.readouterr().out
    assert "ok=True" in out
    assert runner.calls == [("alpha", ["x"], None)]


def test_cmd_loop_with_plan_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner, _ = _patch_factories(monkeypatch, tmp_path / "state")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps([{"skill": "alpha"}]), encoding="utf-8")
    rc = cmd_workbench_loop(_ns(plan=None, plan_file=str(plan_file)))
    assert rc == 0
    assert runner.calls == [("alpha", [], None)]


def test_cmd_loop_no_plan_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_loop(_ns(plan=None, plan_file=None))
    assert rc == 1
    err = capsys.readouterr().err
    assert "plan" in err


def test_cmd_loop_invalid_plan_step_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    plan = json.dumps([{"not_skill": "x"}])
    rc = cmd_workbench_loop(_ns(plan=plan, plan_file=None))
    assert rc == 1
    err = capsys.readouterr().err
    assert "skill" in err


def test_cmd_loop_failed_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    loop_factory = _LoopFactory(FakeRunner([], {}), MemoryService(state_dir=tmp_path))
    loop_factory.result = LoopResult(
        steps=[], ok=False, started_at=1.0, ended_at=2.0, error="bad"
    )
    monkeypatch.setattr(wb_cli, "_make_loop", lambda: loop_factory)
    plan = json.dumps([{"skill": "alpha"}])
    rc = cmd_workbench_loop(_ns(plan=plan, plan_file=None))
    assert rc == 1


# ---------------------------------------------------------------------------
# Command handlers: memory facts
# ---------------------------------------------------------------------------


def test_cmd_memory_facts_list_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_memory_facts_list(_ns())
    assert rc == 0
    assert "no facts" in capsys.readouterr().out


def test_cmd_memory_facts_list_with_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, mem = _patch_factories(monkeypatch, tmp_path / "state")
    mem.remember_fact("k1", "v1")
    rc = cmd_workbench_memory_facts_list(_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "k1" in out
    assert "v1" in out


def test_cmd_memory_facts_remember(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, mem = _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_memory_facts_remember(_ns(key="k1", value='"json-value"'))
    assert rc == 0
    assert mem.get_fact("k1") is not None
    assert mem.get_fact("k1")["value"] == "json-value"
    assert "remembered" in capsys.readouterr().out


def test_cmd_memory_facts_remember_plain_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    _, mem = _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_memory_facts_remember(_ns(key="k1", value="plain-text"))
    assert rc == 0
    assert mem.get_fact("k1")["value"] == "plain-text"


def test_cmd_memory_facts_get_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, mem = _patch_factories(monkeypatch, tmp_path / "state")
    mem.remember_fact("k1", {"a": 1})
    rc = cmd_workbench_memory_facts_get(_ns(key="k1"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "k1" in out


def test_cmd_memory_facts_get_missing_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_memory_facts_get(_ns(key="nope"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "no fact" in err


def test_cmd_memory_facts_forget_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, mem = _patch_factories(monkeypatch, tmp_path / "state")
    mem.remember_fact("k1", "v1")
    rc = cmd_workbench_memory_facts_forget(_ns(key="k1"))
    assert rc == 0
    assert mem.get_fact("k1") is None
    assert "forgot" in capsys.readouterr().out


def test_cmd_memory_facts_forget_missing_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_memory_facts_forget(_ns(key="nope"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "no fact" in err


# ---------------------------------------------------------------------------
# Command handlers: memory episodes
# ---------------------------------------------------------------------------


def test_cmd_memory_episodes_list_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_memory_episodes_list(_ns(kind=None, limit=1000))
    assert rc == 0
    assert "no episodes" in capsys.readouterr().out


def test_cmd_memory_episodes_list_with_episodes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hermes.workbench.memory import make_episode

    _, mem = _patch_factories(monkeypatch, tmp_path / "state")
    mem.record_episode(make_episode("loop", "did a thing", {"x": 1}))
    rc = cmd_workbench_memory_episodes_list(_ns(kind=None, limit=1000))
    assert rc == 0
    out = capsys.readouterr().out
    assert "did a thing" in out


def test_cmd_memory_episodes_list_filtered_by_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hermes.workbench.memory import make_episode

    _, mem = _patch_factories(monkeypatch, tmp_path / "state")
    mem.record_episode(make_episode("loop", "loop-ep", {}))
    mem.record_episode(make_episode("task", "task-ep", {}))
    rc = cmd_workbench_memory_episodes_list(_ns(kind="loop", limit=1000))
    assert rc == 0
    out = capsys.readouterr().out
    assert "loop-ep" in out
    assert "task-ep" not in out


# ---------------------------------------------------------------------------
# Command handlers: memory profile
# ---------------------------------------------------------------------------


def test_cmd_memory_profile_show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = {"name": "tester", "timezone": "UTC"}
    monkeypatch.setattr(
        "hermes.profile.load_profile", lambda: profile
    )
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_memory_profile_show(_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "tester" in out


# ---------------------------------------------------------------------------
# Command handlers: task
# ---------------------------------------------------------------------------


def test_cmd_task_register(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    plan = json.dumps([{"skill": "alpha"}])
    rc = cmd_workbench_task_register(
        _ns(
            task_id="t1",
            plan=plan,
            plan_file=None,
            mode="oneshot",
            max_rounds=1,
            max_runs=1,
            interval=0.0,
        )
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "registered" in out and "t1" in out


def test_cmd_task_register_generates_id_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = TaskStore(state_dir=tmp_path / "state")
    monkeypatch.setattr(wb_cli, "_make_store", lambda: store)
    monkeypatch.setattr(wb_cli, "_make_registry", lambda: TaskRegistry())
    plan = json.dumps([{"skill": "alpha"}])
    rc = cmd_workbench_task_register(
        _ns(
            task_id=None,
            plan=plan,
            plan_file=None,
            mode="oneshot",
            max_rounds=1,
            max_runs=1,
            interval=0.0,
        )
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "registered" in out
    assert store.list() != []


def test_cmd_task_register_no_plan_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_task_register(
        _ns(
            task_id="t1",
            plan=None,
            plan_file=None,
            mode="oneshot",
            max_rounds=1,
            max_runs=1,
            interval=0.0,
        )
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "plan" in err


def test_cmd_task_list_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_factories(monkeypatch, tmp_path / "state")
    rc = cmd_workbench_task_list(_ns())
    assert rc == 0
    assert "no tasks" in capsys.readouterr().out


def test_cmd_task_list_with_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = TaskStore(state_dir=tmp_path / "state")
    monkeypatch.setattr(wb_cli, "_make_store", lambda: store)
    store.save(Task(task_id="t1", plan=[{"skill": "alpha"}]))
    rc = cmd_workbench_task_list(_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "t1" in out


def test_cmd_task_run_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {"alpha": _run_result_ok("alpha", "ok")})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    reg.register(Task(task_id="t1", plan=[{"skill": "alpha"}]))
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    monkeypatch.setattr(wb_cli, "_make_scheduler", lambda: sched)
    rc = cmd_workbench_task_run(_ns(task_id="t1"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "ok=True" in out


def test_cmd_task_run_missing_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    monkeypatch.setattr(wb_cli, "_make_scheduler", lambda: sched)
    rc = cmd_workbench_task_run(_ns(task_id="nope"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


def test_cmd_task_show_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = TaskStore(state_dir=tmp_path / "state")
    monkeypatch.setattr(wb_cli, "_make_store", lambda: store)
    store.save(Task(task_id="t1", plan=[{"skill": "alpha"}]))
    rc = cmd_workbench_task_show(_ns(task_id="t1"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "t1" in out


def test_cmd_task_show_missing_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = TaskStore(state_dir=tmp_path / "state")
    monkeypatch.setattr(wb_cli, "_make_store", lambda: store)
    rc = cmd_workbench_task_show(_ns(task_id="nope"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


def test_cmd_task_cancel_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    task = Task(task_id="t1", plan=[])
    reg.register(task)
    store.save(task)
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    monkeypatch.setattr(wb_cli, "_make_scheduler", lambda: sched)
    rc = cmd_workbench_task_cancel(_ns(task_id="t1"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "cancelled" in out


def test_cmd_task_cancel_missing_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {})
    mem = MemoryService(state_dir=tmp_path / "m")
    store = TaskStore(state_dir=tmp_path / "s")
    reg = TaskRegistry()
    sched = TaskScheduler(store=store, registry=reg, runner=runner, memory=mem)
    monkeypatch.setattr(wb_cli, "_make_scheduler", lambda: sched)
    rc = cmd_workbench_task_cancel(_ns(task_id="nope"))
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


# ---------------------------------------------------------------------------
# Command handlers: serve
# ---------------------------------------------------------------------------


def test_cmd_serve_invokes_run_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # server module now exists (P3); the command must call run_server with
    # the parsed host/port and return 0. We patch run_server so it does not
    # actually block on serve_forever().
    import hermes.workbench.server as server_mod

    captured: list[tuple[str, int]] = []

    def _fake_run_server(host: str, port: int) -> None:
        captured.append((host, port))

    monkeypatch.setattr(server_mod, "run_server", _fake_run_server)
    rc = cmd_workbench_serve(_ns(host="127.0.0.1", port=8123))
    assert rc == 0
    assert captured == [("127.0.0.1", 8123)]


# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def _new_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test")
    sub = parser.add_subparsers(dest="command", required=False)
    add_workbench_subparser(sub)
    return parser


def test_add_workbench_subparser_registers_all() -> None:
    parser = _new_parser()
    # Each nested command group parses without error.
    parser.parse_args(["workbench", "skills", "list"])
    parser.parse_args(["workbench", "skills", "show", "alpha"])
    parser.parse_args(["workbench", "run", "alpha"])
    parser.parse_args(["workbench", "loop", "--plan", "[]"])
    parser.parse_args(["workbench", "memory", "facts", "list"])
    parser.parse_args(["workbench", "memory", "facts", "remember", "k", "v"])
    parser.parse_args(["workbench", "memory", "facts", "get", "k"])
    parser.parse_args(["workbench", "memory", "facts", "forget", "k"])
    parser.parse_args(["workbench", "memory", "episodes"])
    parser.parse_args(["workbench", "memory", "episodes", "--kind", "loop"])
    parser.parse_args(["workbench", "memory", "profile", "show"])
    parser.parse_args(["workbench", "task", "register", "--plan", "[]"])
    parser.parse_args(["workbench", "task", "list"])
    parser.parse_args(["workbench", "task", "run", "t1"])
    parser.parse_args(["workbench", "task", "show", "t1"])
    parser.parse_args(["workbench", "task", "cancel", "t1"])
    parser.parse_args(["workbench", "serve"])


def test_register_workbench_commands_standalone() -> None:
    parser = argparse.ArgumentParser(prog="standalone")
    register_workbench_commands(parser)
    args = parser.parse_args(["workbench", "skills", "list"])
    assert args.command == "workbench"


def test_workbench_main_no_args_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = workbench_main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "hermes-workbench" in out


def test_workbench_main_runs_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([_spec("alpha", "prompt", "alpha desc")], {})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = workbench_main(["workbench", "skills", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha" in out


def test_workbench_main_skills_list_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = workbench_main(["workbench", "skills", "list"])
    assert rc == 0
    assert "no skills" in capsys.readouterr().out


def test_workbench_main_skills_show_missing_returns_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = FakeRunner([], {})
    monkeypatch.setattr(wb_cli, "_make_runner", lambda: runner)
    rc = workbench_main(["workbench", "skills", "show", "nope"])
    assert rc == 1


def test_workbench_subparser_required_nested_groups() -> None:
    parser = _new_parser()
    # Missing the nested subcommand must error (required=True).
    with pytest.raises(SystemExit):
        parser.parse_args(["workbench", "skills"])


# ---------------------------------------------------------------------------
# _resolve_plan
# ---------------------------------------------------------------------------


def test_resolve_plan_from_string() -> None:
    plan = wb_cli._resolve_plan(_ns(plan='[{"skill": "alpha"}]', plan_file=None))
    assert plan == [{"skill": "alpha"}]


def test_resolve_plan_from_file(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text('[{"skill": "alpha"}]', encoding="utf-8")
    plan = wb_cli._resolve_plan(_ns(plan=None, plan_file=str(plan_file)))
    assert plan == [{"skill": "alpha"}]


def test_resolve_plan_none_returns_none() -> None:
    assert wb_cli._resolve_plan(_ns(plan=None, plan_file=None)) is None


def test_resolve_plan_non_list_returns_none() -> None:
    assert wb_cli._resolve_plan(_ns(plan='{"k": "v"}', plan_file=None)) is None
