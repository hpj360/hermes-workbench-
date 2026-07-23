"""Loop execution runner for Hermes.

Bridges the Orchestrator (sub-agent scheduling) with the Loop engine
(state management, stop rules, budget control). Supports:

- run_loop(): Execute one round of a loop
- run_loop_continuous(): Execute rounds until a stop rule triggers
- resume_loop(): Resume from the last recorded state
- Guidance mode fallback when the Gateway is unavailable
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes.loop import (
    LoopRound,
    LoopStage,
    LoopStatus,
    check_budget,
    check_stop_rules,
    get_loop,
    knowledge_hygiene_scan,
    loops_dir,
    record_round,
)
from hermes.orchestrator import Orchestrator, RoundResult

logger = logging.getLogger("hermes.runner")


def _guidance_mode(loop_name: str, pattern: str) -> dict[str, Any]:
    """Return guidance-only result when Gateway is unavailable."""
    return {
        "success": True,
        "mode": "guidance",
        "loop": loop_name,
        "pattern": pattern,
        "message": (
            "Gateway unavailable — running in guidance mode. "
            "Execute the loop manually using the agent definition files."
        ),
    }


def _terminal_status_to_stop(
    name: str, status: LoopStatus, entry: str
) -> dict[str, Any]:
    """Map a terminal LoopStatus to a STOP_RULES-compliant final_stop dict.

    Used by all three entry paths in run_loop_continuous (precheck, rejected,
    post-round) so they agree on BOTH rule_id AND description for the same
    loop state — previously these paths had divergent inline implementations
    that produced different descriptions for identical loop states.

    - COMPLETED → all_green (stop_success)
    - BUDGET_EXCEEDED → budget_exceeded (stop_escalate)
    - NEEDS_HUMAN → re-derive via check_stop_rules; if a rule fires, return
      its result VERBATIM (preserving the specific diagnosis such as
      "修复导致新失败: c。之前修好的: b"); else fall back to rounds_exhausted
      with a state-drift description
    - ERROR → rounds_exhausted with an explicit "error state" description
      (ERROR has no derivable rule; rounds_exhausted is the catch-all
      escalation, but the description makes clear it's an error, not
      genuinely exhausted rounds)
    - unknown future terminal status → log a warning and fall back to
      rounds_exhausted (fail loud, don't silently misclassify)

    `entry` is a short caller-supplied label (e.g. "precheck", "rejected",
    "post-round") embedded in fallback descriptions for traceability.
    """
    if status == LoopStatus.COMPLETED:
        return {
            "should_stop": True,
            "rule_id": "all_green",
            "rule_name": "ALL GREEN",
            "description": "All checks passed (loop status: completed)",
            "action": "stop_success",
        }
    if status == LoopStatus.BUDGET_EXCEEDED:
        return {
            "should_stop": True,
            "rule_id": "budget_exceeded",
            "rule_name": "预算耗尽",
            "description": f"Budget exhausted (loop status: {status.value})",
            "action": "stop_escalate",
        }
    if status == LoopStatus.NEEDS_HUMAN:
        loop = get_loop(name)
        if loop:
            derived = check_stop_rules(
                name, loop.current_round, loop.max_rounds, loop.rounds
            )
            if derived.get("should_stop"):
                # Preserve check_stop_rules' specific diagnosis VERBATIM — do
                # NOT overwrite with a generic message. The original
                # description (e.g. "修复导致新失败: c。之前修好的: b") is exactly
                # what the user needs to see to understand why the loop
                # stopped. Overwriting it was a regression that lost the
                # diagnosis while keeping only the rule_id.
                return derived
        # Fallback: NEEDS_HUMAN but no specific rule currently matches (state
        # drift — e.g. rounds cleared but status not reset, or max_rounds
        # raised after the loop stopped). Use a descriptive format consistent
        # across all entry paths.
        return {
            "should_stop": True,
            "rule_id": "rounds_exhausted",
            "rule_name": "轮次用尽",
            "description": (
                f"State-machine guard: status={status.value}, "
                f"no specific rule matched ({entry})"
            ),
            "action": "stop_escalate",
        }
    if status == LoopStatus.ERROR:
        # ERROR has no derivable stop rule (record_round never sets ERROR;
        # it's only set by external intervention or unexpected exceptions).
        # Map to rounds_exhausted (the catch-all escalation) but make the
        # description explicit so users don't mistake it for genuinely
        # exhausted rounds.
        return {
            "should_stop": True,
            "rule_id": "rounds_exhausted",
            "rule_name": "轮次用尽",
            "description": (
                f"Loop in error state ({entry}); requires human intervention"
            ),
            "action": "stop_escalate",
        }
    # Unknown future terminal status — fail loud, don't silently misclassify.
    logger.warning(
        "Unknown terminal status %s for loop %s; mapping to rounds_exhausted",
        status,
        name,
    )
    return {
        "should_stop": True,
        "rule_id": "rounds_exhausted",
        "rule_name": "轮次用尽",
        "description": (
            f"State-machine guard: status={status.value}, "
            f"no specific rule matched ({entry})"
        ),
        "action": "stop_escalate",
    }


def run_loop(name: str) -> dict[str, Any]:
    """Execute one round of a loop.

    Behavior depends on the loop's pattern and stage:
    - knowledge-hygiene L1: Runs the local file scan (no Gateway needed)
    - builder-checker L2+: Uses the Orchestrator to spawn builder/checker agents
    - Other patterns: Guidance mode if Gateway unavailable

    Returns a dict with round results, including stop rule evaluation.
    """
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    if loop.status == LoopStatus.COMPLETED:
        return {
            "success": False,
            "error": "Loop already completed. Use `hermes loop resume` to restart.",
        }
    if loop.status == LoopStatus.BUDGET_EXCEEDED:
        return {"success": False, "error": "Budget exceeded. Increase budget or reset the loop."}
    if loop.status == LoopStatus.NEEDS_HUMAN:
        return {
            "success": False,
            "error": "Loop stopped for human review. Use `hermes loop resume` to restart after fixing.",
        }
    if loop.status == LoopStatus.ERROR:
        return {"success": False, "error": "Loop in error state. Use `hermes loop resume` to restart."}

    # Check budget before starting
    budget = check_budget(name)
    if not budget.get("success"):
        return budget
    if budget["action"] == "hard_stop":
        return {"success": False, "error": f"Budget exceeded: {budget['used']}/{budget['limit']} tokens"}

    round_num = loop.current_round + 1
    loop_dir = loops_dir() / name
    now = datetime.now(timezone.utc).isoformat()

    # Pattern-specific execution
    if loop.pattern == "knowledge-hygiene" and loop.stage == LoopStage.L1_REPORT:
        return _run_knowledge_hygiene(name, round_num, now, loop_dir)

    if loop.pattern == "builder-checker":
        return _run_builder_checker(name, loop, round_num, now, loop_dir)

    if loop.pattern == "multi-perspective":
        return _run_multi_perspective(name, loop, round_num, now, loop_dir)

    # Default: try orchestrator, fall back to guidance
    orchestrator = Orchestrator()
    if not orchestrator.is_available():
        return _guidance_mode(name, loop.pattern)

    # For other patterns with Gateway available, run a generic round
    return _run_generic_with_gateway(name, loop, round_num, now, loop_dir, orchestrator)


def _run_knowledge_hygiene(
    name: str,
    round_num: int,
    now: str,
    loop_dir: Path,
) -> dict[str, Any]:
    """Execute knowledge-hygiene L1 scan (local, no Gateway needed)."""
    scan_result = knowledge_hygiene_scan()

    hp = scan_result["high_priority"]
    wl = scan_result["watch_list"]
    noise = scan_result["noise"]

    failure_items = hp + wl
    passed = len(hp) == 0

    round_data = LoopRound(
        round_num=round_num,
        timestamp=now,
        action="L1 knowledge hygiene scan",
        result_summary=f"High: {len(hp)}, Watch: {len(wl)}, Noise: {len(noise)}",
        verifier_result=scan_result["summary"].__str__(),
        passed=passed,
        failure_count=len(failure_items),
        failure_items=failure_items,
        tokens_used=0,
    )

    record_result = record_round(name, round_data, tokens_used=0)

    # Check stop rules
    loop = get_loop(name)
    if loop:
        stop = check_stop_rules(name, loop.current_round, loop.max_rounds, loop.rounds)
    else:
        stop = {"should_stop": False, "action": "continue"}

    return {
        "success": True,
        "mode": "local",
        "loop": name,
        "round": round_num,
        "scan_result": scan_result,
        "passed": passed,
        "stop_check": stop,
        "record": record_result,
    }


def _run_builder_checker(
    name: str,
    loop: Any,
    round_num: int,
    now: str,
    loop_dir: Path,
) -> dict[str, Any]:
    """Execute a builder-checker round via the Orchestrator."""
    orchestrator = Orchestrator()

    if not orchestrator.is_available():
        # Guidance mode: print execution instructions
        return _guidance_builder_checker(name, loop, round_num, loop_dir)

    # Get previous checker report for builder context (don't filter!)
    previous_report = ""
    if loop.rounds:
        last_round = loop.rounds[-1]
        if last_round.agent_reports:
            previous_report = last_round.agent_reports.get("checker", "")

    # Determine if parallel checks are enabled (based on sub_agents config)
    parallel_checks = True  # Default: parallel checker execution

    # Generate builder task based on round number
    if round_num == 1:
        builder_task = (
            f"Cycle {round_num}/{loop.max_rounds}. "
            "Read the project structure and LOOP.md, then implement the task described in LOOP.md. "
            "Follow the builder.md instructions."
        )
    else:
        builder_task = (
            f"Cycle {round_num}/{loop.max_rounds}. "
            "The checker found the following failures in the previous round. "
            "Fix them:\n\n"
            f"{previous_report}"
        )

    # Execute the round via orchestrator
    result: RoundResult = orchestrator.run_builder_checker_round(
        loop_dir=loop_dir,
        round_num=round_num,
        builder_task=builder_task,
        checker_context=previous_report,
        parallel_checks=parallel_checks,
    )

    # Build LoopRound from result
    agent_reports: dict[str, str] = {}
    for task in result.tasks:
        if task.result:
            agent_reports[task.role] = task.result

    round_data = LoopRound(
        round_num=round_num,
        timestamp=now,
        action=f"builder-checker round (parallel={parallel_checks})",
        result_summary=result.summary,
        verifier_result=result.checker_report,
        passed=result.all_passed,
        failure_count=len(result.failure_items),
        failure_items=result.failure_items,
        tokens_used=result.total_tokens,
        agent_reports=agent_reports,
    )

    record_result = record_round(name, round_data, tokens_used=result.total_tokens)

    # Check stop rules
    updated_loop = get_loop(name)
    if updated_loop:
        stop = check_stop_rules(
            name, updated_loop.current_round, updated_loop.max_rounds, updated_loop.rounds
        )
    else:
        stop = {"should_stop": False, "action": "continue"}

    return {
        "success": True,
        "mode": "orchestrated",
        "loop": name,
        "round": round_num,
        "result": result.to_dict(),
        "passed": result.all_passed,
        "stop_check": stop,
        "record": record_result,
    }


def _run_multi_perspective(
    name: str,
    loop: Any,
    round_num: int,
    now: str,
    loop_dir: Path,
) -> dict[str, Any]:
    """借鉴 ai-berkshire：执行多视角并行分析轮次。

    Gateway 可用时调用 orchestrator.run_parallel_perspectives，
    不可用时降级到 guidance 模式。
    """
    orchestrator = Orchestrator()

    if not orchestrator.is_available():
        return _guidance_multi_perspective(name, loop, round_num, loop_dir)

    # 从 LOOP.md 解析分析标的（默认用 loop name）
    subject = name
    if loop.config_path.exists():
        content = loop.config_path.read_text(encoding="utf-8")
        # LOOP.md 中 "## 分析标的" 段落
        if "## 分析标的" in content:
            after = content.split("## 分析标的", 1)[1]
            subject = after.split("##", 1)[0].strip() or name

    # 默认 3 个视角（用户可改 LOOP.md 中的视角列表）
    perspectives = [
        {"role": "perspective_1", "lens": "正面视角：发现标的的优势和机会"},
        {"role": "perspective_2", "lens": "风险视角：发现标的的风险和隐患"},
        {"role": "perspective_3", "lens": "中立视角：客观分析标的的现状"},
    ]

    result: RoundResult = orchestrator.run_parallel_perspectives(
        loop_dir=loop_dir,
        round_num=round_num,
        subject=subject,
        perspectives=perspectives,
    )

    # 构建 LoopRound
    agent_reports: dict[str, str] = {}
    for task in result.tasks:
        if task.result:
            agent_reports[task.role] = task.result

    # multi-perspective 的 deliverable 是 summary.md
    summary_path = loop_dir / "summary.md"
    deliverables = [str(summary_path)] if summary_path.exists() else []

    round_data = LoopRound(
        round_num=round_num,
        timestamp=now,
        action=f"multi-perspective round ({len(perspectives)} perspectives)",
        result_summary=result.summary,
        verifier_result=result.checker_report,
        passed=result.all_passed,
        failure_count=len(result.failure_items),
        failure_items=result.failure_items,
        tokens_used=result.total_tokens,
        agent_reports=agent_reports,
    )

    # 设置 deliverables 供 record_round 校验
    if deliverables:
        loop.deliverables = deliverables

    record_result = record_round(name, round_data, tokens_used=result.total_tokens)

    # Check stop rules
    updated_loop = get_loop(name)
    if updated_loop:
        stop = check_stop_rules(
            name, updated_loop.current_round, updated_loop.max_rounds, updated_loop.rounds
        )
    else:
        stop = {"should_stop": False, "action": "continue"}

    return {
        "success": True,
        "mode": "orchestrated",
        "loop": name,
        "round": round_num,
        "result": result.to_dict(),
        "passed": result.all_passed,
        "stop_check": stop,
        "record": record_result,
    }


def _guidance_multi_perspective(
    name: str,
    loop: Any,
    round_num: int,
    loop_dir: Path,
) -> dict[str, Any]:
    """Print guidance for manual multi-perspective execution."""
    perspective_path = loop_dir / "perspective.md"
    summary_path = loop_dir / "summary.md"

    guidance = _guidance_mode(name, "multi-perspective")
    guidance.update({
        "round": round_num,
        "max_rounds": loop.max_rounds,
        "agent_files": {
            "perspective": str(perspective_path),
            "summary": str(summary_path),
        },
        "instructions": [
            f"1. Cycle {round_num}/{loop.max_rounds}",
            f"2. 并行启动 3 个 perspective agent（用 {perspective_path}）",
            "3. 每个 agent 从不同视角分析标的（正面/风险/中立）",
            "4. 收集所有 perspective 结果",
            f"5. 启动 synthesizer agent（用 {summary_path}），汇总结果写入 summary.md",
            "6. summary.md 必须含 <!-- conclusion: --> 标记（反端水硬约束）",
            f"7. 重复直到报告完成或停止规则触发（max {loop.max_rounds} rounds）",
            f"8. 记录轮次结果: hermes loop record {name} --passed/--failed --summary '...'",
        ],
        "principles": [
            "多视角并行：N 个 agent 同消息并行分析，避免串行偏见",
            "反端水：synthesizer 必须给明确结论，禁止'一方面...另一方面...'",
            "声明性标记：perspective 产出含 <!-- claim: -->，summary 含 <!-- conclusion: -->",
        ],
    })
    return guidance


def _guidance_builder_checker(
    name: str,
    loop: Any,
    round_num: int,
    loop_dir: Path,
) -> dict[str, Any]:
    """Print guidance for manual builder-checker execution."""
    builder_path = loop_dir / "builder.md"
    checker_path = loop_dir / "checker.md"
    stop_rules_path = loop_dir / "stop-rules.md"

    guidance = _guidance_mode(name, "builder-checker")
    guidance.update({
        "round": round_num,
        "max_rounds": loop.max_rounds,
        "agent_files": {
            "builder": str(builder_path),
            "checker": str(checker_path),
            "stop_rules": str(stop_rules_path),
        },
        "instructions": [
            f"1. Cycle {round_num}/{loop.max_rounds}",
            f"2. Send task to builder agent: {builder_path}",
            "3. Send checker agent to run all checks",
            "4. If ALL GREEN -> stop",
            "5. If FAILED -> forward checker's RAW report to builder (do NOT interpret)",
            f"6. Repeat until ALL GREEN or stop rule triggers (max {loop.max_rounds} rounds)",
            "7. Record round result: hermes loop record <name> --passed/--failed --summary '...'",
        ],
        "principles": [
            "Tool-level hard isolation: checker physically cannot modify files",
            "Don't filter: pass checker's raw failure report to builder verbatim",
            "7 stop rules: ALL GREEN / rounds exhausted / budget exceeded /",
            "  beyond capability / regression / same failure twice / no progress",
        ],
    })
    return guidance


def _run_generic_with_gateway(
    name: str,
    loop: Any,
    round_num: int,
    now: str,
    loop_dir: Path,
    orchestrator: Orchestrator,
) -> dict[str, Any]:
    """Run a generic loop round using the orchestrator."""
    # For now, generic patterns use guidance mode
    # Future: implement pattern-specific orchestration
    return _guidance_mode(name, loop.pattern)


def run_loop_continuous(
    name: str, max_rounds: int | None = None, gated: bool = False
) -> dict[str, Any]:
    """Execute loop rounds continuously until a stop rule triggers.

    Args:
        name: Loop name
        max_rounds: Override max rounds (default: use loop's max_rounds)
        gated: 经验H——若为 True，每轮执行后若未触发停止规则（loop 仍为 RUNNING），
            则暂停循环并置 loop 为 NEEDS_HUMAN，等待人工确认后再继续（人工关卡）。
            适用于高风险任务的人工监督场景。

    Returns:
        Summary of all rounds executed and final stop reason.
    """
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    effective_max = max_rounds or loop.max_rounds
    rounds_executed: list[dict[str, Any]] = []
    final_stop: dict[str, Any] = {"should_stop": False, "action": "continue"}

    # Pre-check: if the loop is already in a terminal state, do not enter the
    # round loop. Without this, run_loop() returns success=False (rejected by
    # its own status guard) and we would break with the default final_stop
    # ({should_stop: False, action: continue}) and overall success=True —
    # misleading callers into thinking a round ran and the loop should
    # continue. Map the terminal status via _terminal_status_to_stop so the
    # diagnosis matches the other entry paths (all three agree on rule_id AND
    # description for the same loop state).
    if loop.status in (
        LoopStatus.COMPLETED,
        LoopStatus.BUDGET_EXCEEDED,
        LoopStatus.NEEDS_HUMAN,
        LoopStatus.ERROR,
    ):
        final_stop = _terminal_status_to_stop(name, loop.status, "precheck")
        return {
            "success": True,
            "loop": name,
            "rounds_executed": 0,
            "rounds": [],
            "final_stop": final_stop,
        }

    while True:
        # Check budget
        budget = check_budget(name)
        if not budget.get("success"):
            break
        if budget["action"] == "hard_stop":
            final_stop = {
                "should_stop": True,
                "rule_id": "budget_exceeded",
                "rule_name": "预算耗尽",
                "description": f"Budget exhausted: {budget['used']}/{budget['limit']} tokens",
                "action": "stop_escalate",
            }
            break
        if budget["action"] == "alert":
            logger.warning(
                "Budget warning: %s/%s tokens (%.1f%%)",
                budget["used"],
                budget["limit"],
                budget["percentage"],
            )

        # Execute one round
        result = run_loop(name)
        rounds_executed.append(result)

        if not result.get("success"):
            # run_loop rejected the round (e.g. status guard, budget). Derive a
            # meaningful final_stop from the current loop status instead of
            # leaving the default "continue" — otherwise callers see a
            # misleading "should_stop: False, success: True" for a no-op run.
            rejected_loop = get_loop(name)
            if rejected_loop and rejected_loop.status in (
                LoopStatus.COMPLETED,
                LoopStatus.BUDGET_EXCEEDED,
                LoopStatus.NEEDS_HUMAN,
                LoopStatus.ERROR,
            ):
                final_stop = _terminal_status_to_stop(
                    name, rejected_loop.status, "rejected"
                )
            else:
                final_stop = {
                    "should_stop": True,
                    "rule_id": "beyond_capability",
                    "rule_name": "超出能力边界",
                    "description": f"run_loop failed: {result.get('error', 'unknown')}",
                    "action": "stop_escalate",
                }
            break

        # Check if guidance mode was used
        if result.get("mode") == "guidance":
            break

        # Check stop rules
        stop = result.get("stop_check", {})
        if stop.get("should_stop"):
            final_stop = stop
            break

        # Check round limit
        updated_loop = get_loop(name)
        if not updated_loop or updated_loop.current_round >= effective_max:
            final_stop = {
                "should_stop": True,
                "rule_id": "rounds_exhausted",
                "rule_name": "轮次用尽",
                "description": f"Reached {effective_max} rounds",
                "action": "stop_escalate",
            }
            break

        if updated_loop.status in (
            LoopStatus.COMPLETED,
            LoopStatus.NEEDS_HUMAN,
            LoopStatus.BUDGET_EXCEEDED,
            LoopStatus.ERROR,
        ):
            # Map terminal loop status back to a real stop rule id/action via
            # the shared helper — never fabricate 'status_change'/'stop'.
            # Using the helper (instead of an inline mapping) ensures all
            # three entry paths (precheck / rejected / post-round) agree on
            # BOTH rule_id AND description for the same loop state, and
            # avoids the three-way logic drift that previously existed.
            # ERROR is included here so an externally-set error state is
            # caught immediately after the round rather than wasting another
            # round (previously ERROR only triggered on the next run_loop
            # call's status guard).
            final_stop = _terminal_status_to_stop(
                name, updated_loop.status, "post-round"
            )
            break

        # 经验H：gated 模式——每轮结束且仍在 RUNNING（未触发停止规则）时暂停，
        # 置 loop 为 NEEDS_HUMAN，等待人工确认后再继续。
        if gated and updated_loop.status == LoopStatus.RUNNING:
            updated_loop.status = LoopStatus.NEEDS_HUMAN
            from hermes.loop import _save_loop_meta
            _save_loop_meta(updated_loop)
            final_stop = {
                "should_stop": True,
                "rule_id": "human_gate",
                "rule_name": "人工关卡",
                "description": "Gated mode: waiting for human confirmation to continue",
                "action": "stop_escalate",
            }
            break

    return {
        "success": True,
        "loop": name,
        "rounds_executed": len(rounds_executed),
        "rounds": rounds_executed,
        "final_stop": final_stop,
    }


def resume_loop(name: str, gated: bool = False) -> dict[str, Any]:
    """Resume a loop from its last recorded state.

    Resets the loop status to IDLE if it was NEEDS_HUMAN, ERROR, COMPLETED, or
    BUDGET_EXCEEDED. For COMPLETED and BUDGET_EXCEEDED loops, the round history
    and budget are also reset so the loop starts a fresh cycle (a completed or
    budget-exhausted loop has nothing to "continue"; keeping stale rounds would
    make stop rules re-fire immediately, and keeping a stale budget would keep
    the loop locked). Then continues execution from the next round.

    Args:
        name: Loop name
        gated: 若为 True，传递给 run_loop_continuous 保持 gated 模式（每轮后暂停
            等待人工确认）。默认 False（向后兼容）。修复对抗审查 Critical 1：
            之前 resume_loop 调用 run_loop_continuous(name) 不传 gated，导致
            gated 模式 resume 后静默切回全自动。
    """
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    if loop.status in (LoopStatus.NEEDS_HUMAN, LoopStatus.ERROR):
        loop.status = LoopStatus.IDLE
        from hermes.loop import _save_loop_meta
        _save_loop_meta(loop)
        logger.info("Loop '%s' status reset to IDLE for resume", name)
    elif loop.status in (LoopStatus.COMPLETED, LoopStatus.BUDGET_EXCEEDED):
        loop.status = LoopStatus.IDLE
        loop.rounds = []
        loop.current_round = 0
        loop.budget_used_tokens = 0
        from hermes.loop import _save_loop_meta
        _save_loop_meta(loop)
        logger.info("Loop '%s' reset to IDLE for fresh resume (history cleared)", name)

    return run_loop_continuous(name, gated=gated)
