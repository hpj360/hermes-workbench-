"""Sequential agent loop that orchestrates a plan of skill steps.

Each ``LoopStep`` invokes a single skill via the SkillRunner; results are
collected into a ``LoopResult``. By default the loop continues on failure
(unless ``abort_on_error=True``) and records both L1 facts (per-skill last
output) and an L2 episode summarizing the whole plan.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hermes.workbench.memory import MemoryService, make_episode
from hermes.workbench.skill_runner import RunResult, SkillRunner


@dataclass
class LoopStep:
    """A single step in an agent loop plan."""

    skill: str
    args: list[str] = field(default_factory=list)
    timeout: float | None = None
    abort_on_error: bool = False


@dataclass
class LoopStepResult:
    """Outcome of a single LoopStep invocation."""

    skill: str
    ok: bool
    error: str | None
    duration: float
    stdout_preview: str = ""


@dataclass
class LoopResult:
    """Aggregate outcome of an AgentLoop.execute call."""

    steps: list[LoopStepResult] = field(default_factory=list)
    ok: bool = False
    started_at: float = 0.0
    ended_at: float = 0.0
    error: str | None = None

    @property
    def duration(self) -> float:
        """Wall-clock duration of the loop."""
        return self.ended_at - self.started_at


class AgentLoop:
    """Run a plan of LoopSteps sequentially, recording memory along the way."""

    def __init__(self, runner: SkillRunner, memory: MemoryService) -> None:
        self.runner = runner
        self.memory = memory

    def execute(
        self, plan: list[LoopStep], record_episode: bool = True
    ) -> LoopResult:
        """Execute *plan* sequentially and return a LoopResult."""
        started_at = time.time()
        step_results: list[LoopStepResult] = []
        loop_error: str | None = None
        aborted = False

        for step in plan:
            run_result: RunResult = self.runner.run(
                step.skill, args=step.args, timeout=step.timeout
            )
            sr = LoopStepResult(
                skill=step.skill,
                ok=run_result.ok,
                error=run_result.error,
                duration=run_result.duration,
                stdout_preview=_preview(run_result.stdout),
            )
            step_results.append(sr)
            if not run_result.ok:
                if step.abort_on_error:
                    loop_error = run_result.error or f"step {step.skill} failed"
                    aborted = True
                    break
        ended_at = time.time()

        all_ok = bool(step_results) and all(s.ok for s in step_results)
        result = LoopResult(
            steps=step_results,
            ok=all_ok and not aborted,
            started_at=started_at,
            ended_at=ended_at,
            error=loop_error,
        )

        if record_episode:
            self._record_memory(plan, result)

        return result

    # ------------------------------------------------------------------
    def _record_memory(self, plan: list[LoopStep], result: LoopResult) -> None:
        # L1 facts: per-skill last_output preview
        for sr in result.steps:
            self.memory.remember_fact(
                f"skill:{sr.skill}:last_output", sr.stdout_preview
            )
        # L2 episode: whole plan summary
        summary = (
            f"loop executed {len(result.steps)} step(s); ok={result.ok}"
        )
        details: dict[str, Any] = {
            "plan": [
                {"skill": s.skill, "args": list(s.args), "abort_on_error": s.abort_on_error}
                for s in plan
            ],
            "steps": [
                {
                    "skill": s.skill,
                    "ok": s.ok,
                    "error": s.error,
                    "duration": s.duration,
                }
                for s in result.steps
            ],
            "ok": result.ok,
            "duration": result.duration,
            "error": result.error,
        }
        self.memory.record_episode(make_episode("loop", summary, details))


def _preview(text: str, max_len: int = 500) -> str:
    """Return a short preview of *text* (first max_len chars, trimmed)."""
    if len(text) <= max_len:
        return text
    return text[:max_len]
