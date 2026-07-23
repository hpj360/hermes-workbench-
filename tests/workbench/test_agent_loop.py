"""Tests for hermes.workbench.agent_loop.AgentLoop."""

from __future__ import annotations

from pathlib import Path

from hermes.workbench.agent_loop import (
    AgentLoop,
    LoopResult,
    LoopStep,
    LoopStepResult,
)
from hermes.workbench.memory import MemoryService
from hermes.workbench.skill_runner import RunResult, SkillRunner


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeRunner(SkillRunner):
    """A SkillRunner subclass that returns scripted RunResults."""

    def __init__(self, results: dict[str, RunResult]) -> None:
        super().__init__(base_dir=Path("/nonexistent"))
        self._results = results
        self.calls: list[tuple[str, list[str], float | None]] = []

    def run(
        self,
        name: str,
        args: list[str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        self.calls.append((name, list(args or []), timeout))
        if name in self._results:
            return self._results[name]
        return RunResult(
            skill=name,
            ok=False,
            stdout="",
            stderr="",
            exit_code=-1,
            duration=0.0,
            error=f"skill not found: {name}",
        )


def _make_memory(tmp_path: Path) -> MemoryService:
    return MemoryService(state_dir=tmp_path / "state")


def _ok(skill: str, stdout: str = "out") -> RunResult:
    return RunResult(
        skill=skill, ok=True, stdout=stdout, stderr="", exit_code=0, duration=0.01, error=None
    )


def _fail(skill: str, err: str = "boom") -> RunResult:
    return RunResult(
        skill=skill, ok=False, stdout="", stderr=err, exit_code=1, duration=0.01, error=err
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_single_step_success(tmp_path: Path) -> None:
    runner = FakeRunner({"alpha": _ok("alpha", "hello")})
    loop = AgentLoop(runner=runner, memory=_make_memory(tmp_path))
    result = loop.execute([LoopStep(skill="alpha")])
    assert isinstance(result, LoopResult)
    assert result.ok is True
    assert len(result.steps) == 1
    assert result.steps[0].ok is True


def test_multi_step_success(tmp_path: Path) -> None:
    runner = FakeRunner({"alpha": _ok("alpha"), "beta": _ok("beta")})
    loop = AgentLoop(runner=runner, memory=_make_memory(tmp_path))
    result = loop.execute([LoopStep(skill="alpha"), LoopStep(skill="beta")])
    assert result.ok is True
    assert [s.skill for s in result.steps] == ["alpha", "beta"]


def test_failure_continues_by_default(tmp_path: Path) -> None:
    runner = FakeRunner({"alpha": _fail("alpha"), "beta": _ok("beta")})
    loop = AgentLoop(runner=runner, memory=_make_memory(tmp_path))
    result = loop.execute([LoopStep(skill="alpha"), LoopStep(skill="beta")])
    assert result.ok is False
    assert len(result.steps) == 2
    assert result.steps[1].skill == "beta"


def test_abort_on_error_stops_loop(tmp_path: Path) -> None:
    runner = FakeRunner({"alpha": _fail("alpha"), "beta": _ok("beta")})
    loop = AgentLoop(runner=runner, memory=_make_memory(tmp_path))
    result = loop.execute(
        [LoopStep(skill="alpha", abort_on_error=True), LoopStep(skill="beta")]
    )
    assert result.ok is False
    assert len(result.steps) == 1
    assert result.error is not None


def test_failed_step_records_error(tmp_path: Path) -> None:
    runner = FakeRunner({"alpha": _fail("alpha", "explicit-err")})
    loop = AgentLoop(runner=runner, memory=_make_memory(tmp_path))
    result = loop.execute([LoopStep(skill="alpha")])
    assert result.steps[0].ok is False
    assert result.steps[0].error == "explicit-err"


def test_l1_facts_recorded(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    runner = FakeRunner({"alpha": _ok("alpha", "stdout-text")})
    loop = AgentLoop(runner=runner, memory=mem)
    loop.execute([LoopStep(skill="alpha")])
    fact = mem.get_fact("skill:alpha:last_output")
    assert fact is not None
    assert fact["value"] == "stdout-text"


def test_l2_episode_recorded(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    runner = FakeRunner({"alpha": _ok("alpha")})
    loop = AgentLoop(runner=runner, memory=mem)
    loop.execute([LoopStep(skill="alpha")])
    episodes = mem.list_episodes(kind="loop")
    assert len(episodes) == 1
    assert "loop executed 1 step" in episodes[0].summary


def test_empty_plan_returns_not_ok(tmp_path: Path) -> None:
    runner = FakeRunner({})
    loop = AgentLoop(runner=runner, memory=_make_memory(tmp_path))
    result = loop.execute([])
    assert result.ok is False
    assert result.steps == []
    assert result.error is None


def test_duration_property(tmp_path: Path) -> None:
    runner = FakeRunner({"alpha": _ok("alpha")})
    loop = AgentLoop(runner=runner, memory=_make_memory(tmp_path))
    result = loop.execute([LoopStep(skill="alpha")])
    assert result.duration >= 0.0
    assert result.ended_at >= result.started_at


def test_record_episode_false_skips_memory(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    runner = FakeRunner({"alpha": _ok("alpha", "out")})
    loop = AgentLoop(runner=runner, memory=mem)
    loop.execute([LoopStep(skill="alpha")], record_episode=False)
    assert mem.list_episodes() == []
    assert mem.list_facts() == []


def test_loop_step_result_default_stdout_preview(tmp_path: Path) -> None:
    sr = LoopStepResult(skill="x", ok=True, error=None, duration=0.0)
    assert sr.stdout_preview == ""


def test_loop_step_defaults(tmp_path: Path) -> None:
    step = LoopStep(skill="x")
    assert step.args == []
    assert step.timeout is None
    assert step.abort_on_error is False
