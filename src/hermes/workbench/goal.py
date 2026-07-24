"""Goal-based loop engineering for the Workbench agent runtime.

A Goal defines a machine-verifiable success criteria, boundary conditions
(time/rounds/failures), and a degradation fallback. SubAgent roles
(Planner, Generator, Evaluator) separate concerns within a loop cycle:

    Planner   → generates plan from goal (LLM-driven when available)
    Generator → executes plan via AgentLoop
    Evaluator → verifies result against goal (LLM-soft + machine-verifiable)

When an :class:`~hermes.workbench.llm.LlmClient` is injected, the Planner
asks the LLM to map a goal description to a JSON plan of skills, and the
Evaluator asks the LLM for a soft judgement that is combined with the
machine-verifiable criteria. When no LLM is injected, behavior is
unchanged (rule-based fallback) so existing tests keep passing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from hermes.workbench.agent_loop import AgentLoop, LoopResult, LoopStep
from hermes.workbench.llm import (
    LlmApiError,
    LlmClient,
    LlmConfigError,
    LlmMessage,
)
from hermes.workbench.memory import Episode, MemoryService, make_episode
from hermes.workbench.skill_runner import SkillRunner
from hermes.workbench.tracing import Tracer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Goal types
# ---------------------------------------------------------------------------


@dataclass
class GoalBoundary:
    """Boundary conditions that stop a loop early."""

    max_rounds: int = 10
    max_time: float = 3600.0  # seconds
    max_failures: int = 3  # consecutive failures before giving up


@dataclass
class GoalVerification:
    """Result of checking whether a goal was achieved."""

    achieved: bool
    evidence: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Goal:
    """A machine-verifiable goal for a loop task.

    ``success_criteria`` is a list of checks, each being a dict::

        {"skill": "skill-name", "args": [...], "expect_exit": 0}

    The goal is achieved when ALL checks pass.
    """

    description: str
    success_criteria: list[dict[str, Any]] = field(default_factory=list)
    boundary: GoalBoundary = field(default_factory=GoalBoundary)
    degradation: str | None = None  # fallback action description

    def verify(self, runner: SkillRunner) -> GoalVerification:
        """Run success criteria skills and check results."""
        if not self.success_criteria:
            return GoalVerification(achieved=True, evidence="no criteria defined")
        checks: list[dict[str, Any]] = []
        all_passed = True
        for criterion in self.success_criteria:
            skill = str(criterion.get("skill", ""))
            if not skill:
                continue
            args = list(criterion.get("args", []))
            expect_exit = int(criterion.get("expect_exit", 0))
            timeout = criterion.get("timeout")
            result = runner.run(skill, args=args, timeout=timeout)
            passed = result.ok and result.exit_code == expect_exit
            checks.append(
                {
                    "skill": skill,
                    "passed": passed,
                    "exit_code": result.exit_code,
                    "expected_exit": expect_exit,
                    "error": result.error,
                }
            )
            if not passed:
                all_passed = False
        evidence = "; ".join(
            f"{c['skill']}: {'PASS' if c['passed'] else 'FAIL'}" for c in checks
        )
        return GoalVerification(
            achieved=all_passed, evidence=evidence, checks=checks
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Goal:
        """Build a Goal from a plain dict (for deserialization)."""
        boundary_data = data.get("boundary") or {}
        return cls(
            description=str(data.get("description", "")),
            success_criteria=list(data.get("success_criteria", [])),
            boundary=GoalBoundary(
                max_rounds=int(boundary_data.get("max_rounds", 10)),
                max_time=float(boundary_data.get("max_time", 3600.0)),
                max_failures=int(boundary_data.get("max_failures", 3)),
            ),
            degradation=data.get("degradation"),
        )


# ---------------------------------------------------------------------------
# SubAgent roles
# ---------------------------------------------------------------------------


class SubAgent:
    """Base class for loop sub-agents."""

    role: str = "base"

    def __init__(
        self,
        runner: SkillRunner,
        memory: MemoryService,
        llm: LlmClient | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.runner = runner
        self.memory = memory
        self.llm = llm
        self.tracer = tracer

    def _record(self, episode: Episode) -> None:
        """Record an episode via the tracer (when available) or memory directly.

        When a tracer with an active span is set, the episode is stamped
        with the current trace_id so the Planner→Generator→Evaluator chain
        can be reconstructed. Without a tracer, falls back to plain
        memory recording (backward compatible).
        """
        if self.tracer is not None:
            self.tracer.record(episode)
        else:
            self.memory.record_episode(episode)


class PlannerAgent(SubAgent):
    """Generates a plan of skills to achieve a goal.

    When an LLM is available, the planner asks the model to translate the
    goal description into a JSON array of plan steps (each with ``skill``,
    ``args``, optional ``timeout`` / ``abort_on_error``). When no LLM is
    available, planning falls back to the goal's success-criteria skills
    or the task's fallback plan.
    """

    role = "planner"

    def plan(
        self,
        goal: Goal | None,
        fallback_plan: list[LoopStep] | None = None,
    ) -> list[LoopStep]:
        """Generate a plan for the goal."""
        llm_used = False
        plan: list[LoopStep] = []
        if self.llm is not None and goal and goal.description:
            plan = self._plan_via_llm(goal, fallback_plan)
            llm_used = bool(plan)
        if not plan:
            plan = self._plan_fallback(goal, fallback_plan)
        self._record(
            make_episode(
                "planner",
                f"planning for: {goal.description if goal else 'no goal'}",
                {"fallback": fallback_plan is not None, "llm_used": llm_used,
                 "steps": len(plan)},
            )
        )
        return plan

    def _plan_fallback(
        self,
        goal: Goal | None,
        fallback_plan: list[LoopStep] | None,
    ) -> list[LoopStep]:
        if fallback_plan:
            return fallback_plan
        if goal and goal.success_criteria:
            return [
                LoopStep(
                    skill=str(c.get("skill", "")),
                    args=list(c.get("args", [])),
                    timeout=c.get("timeout"),
                )
                for c in goal.success_criteria
                if c.get("skill")
            ]
        return []

    def _plan_via_llm(
        self, goal: Goal, fallback_plan: list[LoopStep] | None
    ) -> list[LoopStep]:
        """Ask the LLM for a JSON plan. Returns [] on any failure."""
        available = [s.name for s in self.runner.discover()]
        sys_prompt = (
            "You are a planning agent. Given a goal and a list of available "
            "skills, produce a JSON array of plan steps. Each step MUST be an "
            "object with: \"skill\" (string, one of the available skills), "
            "\"args\" (array of strings, may be empty), and optionally "
            "\"timeout\" (number, seconds) and \"abort_on_error\" (boolean)."
        )
        user_prompt = (
            f"Goal: {goal.description}\n"
            f"Available skills: {', '.join(available) or '(none)'}\n"
            f"Success criteria: {json.dumps(goal.success_criteria, ensure_ascii=False)}\n"
            f"Respond with a JSON array only."
        )
        try:
            data = self.llm.chat_json(  # type: ignore[union-attr]
                [
                    LlmMessage(role="system", content=sys_prompt),
                    LlmMessage(role="user", content=user_prompt),
                ]
            )
        except (LlmApiError, LlmConfigError) as e:
            logger.warning("PlannerAgent LLM call failed: %s", e)
            return []
        return _parse_llm_plan(data)

    # preserved for backward compatibility with tests that introspect the
    # rule-based path directly.
    def _plan_rule_based(
        self, goal: Goal | None, fallback_plan: list[LoopStep] | None
    ) -> list[LoopStep]:
        return self._plan_fallback(goal, fallback_plan)


class GeneratorAgent(SubAgent):
    """Executes a plan and produces output."""

    role = "generator"

    def __init__(
        self,
        runner: SkillRunner,
        memory: MemoryService,
        llm: LlmClient | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        super().__init__(runner, memory, llm=llm, tracer=tracer)
        self._loop = AgentLoop(runner=runner, memory=memory)

    def generate(self, plan: list[LoopStep]) -> LoopResult:
        """Execute the plan and return the result."""
        result = self._loop.execute(plan)
        self._record(
            make_episode(
                "generator",
                f"executed plan: {len(plan)} steps, ok={result.ok}",
                {
                    "steps": len(plan),
                    "ok": result.ok,
                    "error": result.error,
                    "step_results": [
                        {
                            "skill": s.skill,
                            "ok": s.ok,
                            "error": s.error,
                            "duration": s.duration,
                        }
                        for s in result.steps
                    ],
                },
            )
        )
        return result


class EvaluatorAgent(SubAgent):
    """Evaluates whether the output meets the goal.

    Combines a machine-verifiable check (via :meth:`Goal.verify`) with an
    optional LLM "soft judgement" that reads the loop's step outputs and
    decides whether the goal description was satisfied. The LLM judgement
    cannot override a hard machine failure: if ``result.ok`` is False the
    evaluation is always ``achieved=False``.
    """

    role = "evaluator"

    def evaluate(
        self, result: LoopResult, goal: Goal | None
    ) -> GoalVerification:
        """Evaluate if the result achieves the goal."""
        if goal is None:
            verification = GoalVerification(
                achieved=result.ok,
                evidence=f"no goal; loop ok={result.ok}",
            )
        elif not result.ok:
            verification = GoalVerification(
                achieved=False,
                evidence=f"loop failed: {result.error or 'steps failed'}",
            )
        else:
            verification = goal.verify(self.runner)
            # Soft LLM judgement (cannot flip a hard failure to success).
            if self.llm is not None and goal.description:
                soft = self._soft_judge(result, goal, verification)
                if soft:
                    verification.evidence = (
                        verification.evidence + " | LLM: " + soft
                    )
        self._record(
            make_episode(
                "evaluator",
                f"evaluation: {'achieved' if verification.achieved else 'not achieved'}",
                {
                    "achieved": verification.achieved,
                    "evidence": verification.evidence,
                    "checks": verification.checks,
                    "loop_ok": result.ok,
                },
            )
        )
        return verification

    def _soft_judge(
        self, result: LoopResult, goal: Goal, machine: GoalVerification
    ) -> str:
        """Ask the LLM for a one-line judgement. Returns "" on failure."""
        sys_prompt = (
            "You are an evaluation agent. Given a goal, the machine-verifiable "
            "check result, and the executed steps, give a one-sentence judgement "
            "of whether the goal was achieved. Be concise."
        )
        step_summary = "; ".join(
            f"{s.skill}({'OK' if s.ok else 'FAIL'})" for s in result.steps
        ) or "(no steps)"
        user_prompt = (
            f"Goal: {goal.description}\n"
            f"Machine check: achieved={machine.achieved}, "
            f"evidence={machine.evidence}\n"
            f"Steps: {step_summary}\n"
            f"Error: {result.error or 'none'}\n"
            f"One-sentence judgement:"
        )
        try:
            resp = self.llm.chat(  # type: ignore[union-attr]
                [
                    LlmMessage(role="system", content=sys_prompt),
                    LlmMessage(role="user", content=user_prompt),
                ]
            )
        except (LlmApiError, LlmConfigError) as e:
            logger.warning("EvaluatorAgent LLM call failed: %s", e)
            return ""
        return resp.content.strip()


def _parse_llm_plan(data: Any) -> list[LoopStep]:
    """Parse an LLM-produced plan (list of dicts) into LoopSteps.

    Accepts either a bare JSON array or ``{"plan": [...]}``. Tolerates
    missing ``args`` and skips steps without a ``skill`` field.
    """
    if isinstance(data, dict):
        items = data.get("plan") or data.get("steps") or []
    elif isinstance(data, list):
        items = data
    else:
        return []
    steps: list[LoopStep] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill", "")).strip()
        if not skill:
            continue
        args = item.get("args") or []
        if not isinstance(args, list):
            args = [str(args)]
        steps.append(
            LoopStep(
                skill=skill,
                args=[str(a) for a in args],
                timeout=item.get("timeout"),
                abort_on_error=bool(item.get("abort_on_error", False)),
            )
        )
    return steps
