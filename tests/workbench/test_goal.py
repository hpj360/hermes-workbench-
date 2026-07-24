"""Tests for hermes.workbench.goal (Goal types and SubAgent roles)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hermes.workbench.agent_loop import LoopResult, LoopStep, LoopStepResult
from hermes.workbench.goal import (
    EvaluatorAgent,
    GeneratorAgent,
    Goal,
    GoalBoundary,
    GoalVerification,
    PlannerAgent,
    SubAgent,
)
from hermes.workbench.memory import MemoryService
from hermes.workbench.skill_runner import RunResult, SkillSpec


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _spec(name: str) -> SkillSpec:
    return SkillSpec(
        name=name,
        path=Path("/tmp") / name,
        description="",
        runtime="prompt",
        requires_bins=[],
        requires_env=[],
        entrypoint=None,
        raw_metadata={},
    )


def _ok(skill: str) -> RunResult:
    return RunResult(
        skill=skill, ok=True, stdout="ok", stderr="", exit_code=0,
        duration=0.01, error=None,
    )


def _fail(skill: str) -> RunResult:
    return RunResult(
        skill=skill, ok=False, stdout="", stderr="err", exit_code=1,
        duration=0.01, error="err",
    )


class FakeRunner:
    """Minimal SkillRunner-like fake."""

    def __init__(self, results: dict[str, RunResult]) -> None:
        self._results = results
        self.calls: list[tuple[str, list[str], float | None]] = []

    def discover(self) -> list[SkillSpec]:
        return []

    def get(self, name: str) -> SkillSpec | None:
        return _spec(name)

    def run(
        self, name: str, args: list[str] | None = None, timeout: float | None = None
    ) -> RunResult:
        self.calls.append((name, list(args or []), timeout))
        return self._results.get(name, _fail(name))


def _loop_result_ok() -> LoopResult:
    return LoopResult(
        steps=[LoopStepResult(skill="alpha", ok=True, error=None, duration=0.01)],
        ok=True,
        started_at=1.0,
        ended_at=2.0,
        error=None,
    )


# ---------------------------------------------------------------------------
# Goal tests
# ---------------------------------------------------------------------------


def test_goal_from_dict() -> None:
    data = {
        "description": "deploy service",
        "success_criteria": [
            {"skill": "check-deploy", "args": [], "expect_exit": 0},
        ],
        "boundary": {"max_rounds": 5, "max_time": 600, "max_failures": 2},
        "degradation": "rollback to previous version",
    }
    goal = Goal.from_dict(data)
    assert goal.description == "deploy service"
    assert len(goal.success_criteria) == 1
    assert goal.boundary.max_rounds == 5
    assert goal.boundary.max_time == 600
    assert goal.boundary.max_failures == 2
    assert goal.degradation == "rollback to previous version"


def test_goal_from_dict_defaults() -> None:
    goal = Goal.from_dict({"description": "test"})
    assert goal.success_criteria == []
    assert goal.boundary.max_rounds == 10
    assert goal.boundary.max_time == 3600.0
    assert goal.boundary.max_failures == 3
    assert goal.degradation is None


def test_goal_verify_no_criteria_returns_achieved() -> None:
    goal = Goal(description="no criteria")
    runner = FakeRunner({})
    verification = goal.verify(runner)
    assert verification.achieved is True
    assert "no criteria" in verification.evidence


def test_goal_verify_all_pass() -> None:
    goal = Goal(
        description="test",
        success_criteria=[
            {"skill": "check-a", "expect_exit": 0},
            {"skill": "check-b", "expect_exit": 0},
        ],
    )
    runner = FakeRunner({"check-a": _ok("check-a"), "check-b": _ok("check-b")})
    verification = goal.verify(runner)
    assert verification.achieved is True
    assert len(verification.checks) == 2
    assert all(c["passed"] for c in verification.checks)


def test_goal_verify_some_fail() -> None:
    goal = Goal(
        description="test",
        success_criteria=[
            {"skill": "check-a", "expect_exit": 0},
            {"skill": "check-b", "expect_exit": 0},
        ],
    )
    runner = FakeRunner({"check-a": _ok("check-a"), "check-b": _fail("check-b")})
    verification = goal.verify(runner)
    assert verification.achieved is False
    assert len(verification.checks) == 2
    assert verification.checks[0]["passed"] is True
    assert verification.checks[1]["passed"] is False


def test_goal_boundary_defaults() -> None:
    b = GoalBoundary()
    assert b.max_rounds == 10
    assert b.max_time == 3600.0
    assert b.max_failures == 3


# ---------------------------------------------------------------------------
# SubAgent tests
# ---------------------------------------------------------------------------


def test_planner_uses_fallback_plan(tmp_path: Path) -> None:
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    planner = PlannerAgent(runner, memory)
    fallback = [LoopStep(skill="deploy", args=["--env", "prod"])]
    plan = planner.plan(goal=None, fallback_plan=fallback)
    assert plan == fallback
    # Should have recorded a planning episode
    episodes = memory.list_episodes(kind="planner")
    assert len(episodes) == 1


def test_planner_uses_goal_criteria_when_no_fallback(tmp_path: Path) -> None:
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    planner = PlannerAgent(runner, memory)
    goal = Goal(
        description="test",
        success_criteria=[{"skill": "check-deploy", "args": ["--env"]}],
    )
    plan = planner.plan(goal=goal, fallback_plan=None)
    assert len(plan) == 1
    assert plan[0].skill == "check-deploy"
    assert plan[0].args == ["--env"]


def test_planner_empty_plan_when_nothing_available(tmp_path: Path) -> None:
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    planner = PlannerAgent(runner, memory)
    plan = planner.plan(goal=None, fallback_plan=None)
    assert plan == []


def test_generator_executes_plan(tmp_path: Path) -> None:
    runner = FakeRunner({"alpha": _ok("alpha")})
    memory = MemoryService(state_dir=tmp_path / "state")
    generator = GeneratorAgent(runner, memory)
    plan = [LoopStep(skill="alpha")]
    result = generator.generate(plan)
    assert isinstance(result, LoopResult)
    assert result.ok is True


def test_evaluator_achieved_when_goal_met(tmp_path: Path) -> None:
    runner = FakeRunner({"check": _ok("check")})
    memory = MemoryService(state_dir=tmp_path / "state")
    evaluator = EvaluatorAgent(runner, memory)
    goal = Goal(
        description="test",
        success_criteria=[{"skill": "check", "expect_exit": 0}],
    )
    result = _loop_result_ok()
    verification = evaluator.evaluate(result, goal)
    assert verification.achieved is True
    episodes = memory.list_episodes(kind="evaluator")
    assert len(episodes) == 1


def test_evaluator_not_achieved_when_loop_fails(tmp_path: Path) -> None:
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    evaluator = EvaluatorAgent(runner, memory)
    goal = Goal(description="test")
    result = LoopResult(
        steps=[], ok=False, started_at=1.0, ended_at=2.0, error="crashed",
    )
    verification = evaluator.evaluate(result, goal)
    assert verification.achieved is False
    assert "loop failed" in verification.evidence


def test_evaluator_no_goal_uses_loop_ok(tmp_path: Path) -> None:
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    evaluator = EvaluatorAgent(runner, memory)
    result = _loop_result_ok()
    verification = evaluator.evaluate(result, goal=None)
    assert verification.achieved is True


def test_sub_agent_base_attributes(tmp_path: Path) -> None:
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    agent = SubAgent(runner, memory)
    assert agent.role == "base"
    assert agent.runner is runner
    assert agent.memory is memory


# ---------------------------------------------------------------------------
# SubAgent tests — LLM integration
# ---------------------------------------------------------------------------


class FakeRunnerWithSkills(FakeRunner):
    """FakeRunner variant that reports a fixed list of skills."""

    def __init__(self, results: dict[str, RunResult], skills: list[str]) -> None:
        super().__init__(results)
        self._skills = skills

    def discover(self) -> list[SkillSpec]:
        return [_spec(name) for name in self._skills]


class FakeLlmClient:
    """Minimal LlmClient-like fake that returns canned responses."""

    def __init__(
        self,
        chat_response: str = "",
        chat_json_response: dict[str, Any] | None = None,
        chat_raises: Exception | None = None,
        json_raises: Exception | None = None,
    ) -> None:
        self._chat_response = chat_response
        self._chat_json_response = chat_json_response or {}
        self._chat_raises = chat_raises
        self._json_raises = json_raises
        self.chat_calls: list[Any] = []
        self.json_calls: list[Any] = []

    def chat(self, messages: list[Any], **kwargs: Any) -> Any:
        from hermes.workbench.llm import LlmResponse
        self.chat_calls.append(messages)
        if self._chat_raises:
            raise self._chat_raises
        return LlmResponse(content=self._chat_response)

    def chat_json(self, messages: list[Any], **kwargs: Any) -> dict[str, Any]:
        self.json_calls.append(messages)
        if self._json_raises:
            raise self._json_raises
        return self._chat_json_response


def test_planner_uses_llm_when_available(tmp_path: Path) -> None:
    """PlannerAgent with LLM should ask the LLM for a JSON plan."""
    runner = FakeRunnerWithSkills({}, skills=["deploy", "test"])
    memory = MemoryService(state_dir=tmp_path / "state")
    llm = FakeLlmClient(
        chat_json_response={"plan": [{"skill": "deploy", "args": ["--env", "prod"]}]}
    )
    planner = PlannerAgent(runner, memory, llm=llm)  # type: ignore[arg-type]
    goal = Goal(description="deploy the service")
    plan = planner.plan(goal=goal, fallback_plan=None)
    assert len(plan) == 1
    assert plan[0].skill == "deploy"
    assert plan[0].args == ["--env", "prod"]
    # LLM should have been called once
    assert len(llm.json_calls) == 1


def test_planner_falls_back_when_llm_returns_empty(tmp_path: Path) -> None:
    """PlannerAgent should fall back to goal criteria when LLM returns no plan."""
    runner = FakeRunnerWithSkills({}, skills=["check"])
    memory = MemoryService(state_dir=tmp_path / "state")
    llm = FakeLlmClient(chat_json_response={"plan": []})
    planner = PlannerAgent(runner, memory, llm=llm)  # type: ignore[arg-type]
    goal = Goal(
        description="test",
        success_criteria=[{"skill": "check", "args": []}],
    )
    plan = planner.plan(goal=goal, fallback_plan=None)
    assert len(plan) == 1
    assert plan[0].skill == "check"


def test_planner_falls_back_when_llm_raises(tmp_path: Path) -> None:
    """PlannerAgent should fall back when the LLM call raises LlmApiError."""
    from hermes.workbench.llm import LlmApiError
    runner = FakeRunnerWithSkills({}, skills=["check"])
    memory = MemoryService(state_dir=tmp_path / "state")
    llm = FakeLlmClient(json_raises=LlmApiError("boom"))
    planner = PlannerAgent(runner, memory, llm=llm)  # type: ignore[arg-type]
    goal = Goal(
        description="test",
        success_criteria=[{"skill": "check"}],
    )
    plan = planner.plan(goal=goal, fallback_plan=None)
    assert len(plan) == 1
    assert plan[0].skill == "check"


def test_planner_no_llm_keeps_rule_based_behavior(tmp_path: Path) -> None:
    """PlannerAgent without LLM should behave exactly as before (backward compat)."""
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    planner = PlannerAgent(runner, memory)
    fallback = [LoopStep(skill="deploy")]
    plan = planner.plan(goal=None, fallback_plan=fallback)
    assert plan == fallback


def test_planner_llm_episode_records_llm_used_flag(tmp_path: Path) -> None:
    """planner episode should record llm_used=True when LLM produced a plan."""
    runner = FakeRunnerWithSkills({}, skills=["deploy"])
    memory = MemoryService(state_dir=tmp_path / "state")
    llm = FakeLlmClient(chat_json_response={"plan": [{"skill": "deploy"}]})
    planner = PlannerAgent(runner, memory, llm=llm)  # type: ignore[arg-type]
    goal = Goal(description="deploy")
    planner.plan(goal=goal, fallback_plan=None)
    episodes = memory.list_episodes(kind="planner")
    assert len(episodes) == 1
    assert episodes[0].details["llm_used"] is True


def test_evaluator_llm_adds_soft_judgement(tmp_path: Path) -> None:
    """EvaluatorAgent with LLM should append a soft judgement to evidence."""
    runner = FakeRunner({"check": _ok("check")})
    memory = MemoryService(state_dir=tmp_path / "state")
    llm = FakeLlmClient(chat_response="Goal achieved successfully.")
    evaluator = EvaluatorAgent(runner, memory, llm=llm)  # type: ignore[arg-type]
    goal = Goal(
        description="test",
        success_criteria=[{"skill": "check", "expect_exit": 0}],
    )
    result = _loop_result_ok()
    verification = evaluator.evaluate(result, goal)
    assert verification.achieved is True
    assert "LLM:" in verification.evidence
    assert "Goal achieved" in verification.evidence


def test_evaluator_llm_cannot_override_hard_failure(tmp_path: Path) -> None:
    """LLM soft judgement must not flip a failed loop to achieved=True."""
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    llm = FakeLlmClient(chat_response="Looks good to me!")
    evaluator = EvaluatorAgent(runner, memory, llm=llm)  # type: ignore[arg-type]
    goal = Goal(description="test")
    result = LoopResult(
        steps=[], ok=False, started_at=1.0, ended_at=2.0, error="crashed",
    )
    verification = evaluator.evaluate(result, goal)
    assert verification.achieved is False


def test_evaluator_llm_failure_does_not_break_evaluation(tmp_path: Path) -> None:
    """EvaluatorAgent should still produce a verdict when the LLM call fails."""
    from hermes.workbench.llm import LlmApiError
    runner = FakeRunner({"check": _ok("check")})
    memory = MemoryService(state_dir=tmp_path / "state")
    llm = FakeLlmClient(chat_raises=LlmApiError("network down"))
    evaluator = EvaluatorAgent(runner, memory, llm=llm)  # type: ignore[arg-type]
    goal = Goal(
        description="test",
        success_criteria=[{"skill": "check", "expect_exit": 0}],
    )
    result = _loop_result_ok()
    verification = evaluator.evaluate(result, goal)
    assert verification.achieved is True
    # evidence should NOT contain the LLM judgement (call failed)
    assert "LLM:" not in verification.evidence


def test_evaluator_no_llm_keeps_original_behavior(tmp_path: Path) -> None:
    """EvaluatorAgent without LLM should behave exactly as before."""
    runner = FakeRunner({"check": _ok("check")})
    memory = MemoryService(state_dir=tmp_path / "state")
    evaluator = EvaluatorAgent(runner, memory)
    goal = Goal(
        description="test",
        success_criteria=[{"skill": "check", "expect_exit": 0}],
    )
    result = _loop_result_ok()
    verification = evaluator.evaluate(result, goal)
    assert verification.achieved is True
    assert "LLM:" not in verification.evidence


# ---------------------------------------------------------------------------
# _parse_llm_plan helper
# ---------------------------------------------------------------------------


def test_parse_llm_plan_bare_array() -> None:
    from hermes.workbench.goal import _parse_llm_plan
    data = [{"skill": "a", "args": ["1"]}, {"skill": "b"}]
    steps = _parse_llm_plan(data)
    assert len(steps) == 2
    assert steps[0].skill == "a"
    assert steps[0].args == ["1"]
    assert steps[1].skill == "b"
    assert steps[1].args == []


def test_parse_llm_plan_wrapped_in_plan_key() -> None:
    from hermes.workbench.goal import _parse_llm_plan
    data = {"plan": [{"skill": "deploy", "timeout": 30, "abort_on_error": True}]}
    steps = _parse_llm_plan(data)
    assert len(steps) == 1
    assert steps[0].skill == "deploy"
    assert steps[0].timeout == 30
    assert steps[0].abort_on_error is True


def test_parse_llm_plan_skips_steps_without_skill() -> None:
    from hermes.workbench.goal import _parse_llm_plan
    data = [{"skill": "ok"}, {"args": ["x"]}, {"skill": "", "args": []}, "junk"]
    steps = _parse_llm_plan(data)
    assert len(steps) == 1
    assert steps[0].skill == "ok"


# ---------------------------------------------------------------------------
# Tracer integration
# ---------------------------------------------------------------------------


def test_planner_with_tracer_stamps_episode(tmp_path: Path) -> None:
    """When a Tracer with an active span is set, planner episodes get trace_id."""
    from hermes.workbench.tracing import Tracer

    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    tracer = Tracer(memory)
    planner = PlannerAgent(runner, memory, tracer=tracer)
    with tracer.span() as trace_id:
        planner.plan(goal=None, fallback_plan=[LoopStep(skill="x")])
    episodes = memory.list_episodes(kind="planner")
    assert len(episodes) == 1
    assert episodes[0].details.get("trace_id") == trace_id


def test_generator_with_tracer_stamps_episode(tmp_path: Path) -> None:
    """GeneratorAgent respects the tracer and stamps trace_id on its episode."""
    from hermes.workbench.tracing import Tracer

    runner = FakeRunner({"alpha": _ok("alpha")})
    memory = MemoryService(state_dir=tmp_path / "state")
    tracer = Tracer(memory)
    generator = GeneratorAgent(runner, memory, tracer=tracer)
    with tracer.span() as trace_id:
        generator.generate([LoopStep(skill="alpha")])
    episodes = memory.list_episodes(kind="generator")
    assert len(episodes) == 1
    assert episodes[0].details.get("trace_id") == trace_id


def test_evaluator_with_tracer_stamps_episode(tmp_path: Path) -> None:
    """EvaluatorAgent respects the tracer and stamps trace_id on its episode."""
    from hermes.workbench.tracing import Tracer

    runner = FakeRunner({"check": _ok("check")})
    memory = MemoryService(state_dir=tmp_path / "state")
    tracer = Tracer(memory)
    evaluator = EvaluatorAgent(runner, memory, tracer=tracer)
    goal = Goal(description="t", success_criteria=[{"skill": "check", "expect_exit": 0}])
    with tracer.span() as trace_id:
        evaluator.evaluate(_loop_result_ok(), goal)
    episodes = memory.list_episodes(kind="evaluator")
    assert len(episodes) == 1
    assert episodes[0].details.get("trace_id") == trace_id


def test_subagent_without_tracer_falls_back_to_memory(tmp_path: Path) -> None:
    """Without a tracer, episodes are recorded directly (backward compat)."""
    runner = FakeRunner({})
    memory = MemoryService(state_dir=tmp_path / "state")
    planner = PlannerAgent(runner, memory)  # no tracer
    planner.plan(goal=None, fallback_plan=[LoopStep(skill="x")])
    episodes = memory.list_episodes(kind="planner")
    assert len(episodes) == 1
    assert "trace_id" not in (episodes[0].details or {})


def test_generator_episode_records_step_results(tmp_path: Path) -> None:
    """GeneratorAgent's episode should include per-step result details."""
    runner = FakeRunner({"alpha": _ok("alpha")})
    memory = MemoryService(state_dir=tmp_path / "state")
    generator = GeneratorAgent(runner, memory)
    generator.generate([LoopStep(skill="alpha")])
    episodes = memory.list_episodes(kind="generator")
    assert len(episodes) == 1
    step_results = episodes[0].details.get("step_results", [])
    assert len(step_results) == 1
    assert step_results[0]["skill"] == "alpha"
    assert step_results[0]["ok"] is True
    assert "duration" in step_results[0]
    # exit_code should NOT be present (LoopStepResult has no exit_code attr)
    assert "exit_code" not in step_results[0]
