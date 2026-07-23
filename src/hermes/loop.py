"""Loop Engineering support for Hermes.

Implements the Loop Engineering pattern from cobusgreyling/loop-engineering:
- Loop scaffolding (STATE.md, loop-budget.md, LOOP.md, builder.md, checker.md, stop-rules.md)
- Loop state tracking across runs
- L1/L2/L3 staged autonomy
- Loop readiness audit
- Maker/Checker separation with tool-level hard isolation
- Seven stop rules (ALL GREEN, rounds exhausted, budget exceeded, beyond capability, regression, same failure twice, no progress)
- "Don't interpret or filter" principle for failure report forwarding
- Built-in patterns (builder-checker, daily-triage, knowledge-hygiene, ci-sweeper, pr-babysitter)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("hermes.loop")


class LoopStage(str, Enum):
    L1_REPORT = "l1_report"
    L2_ASSIST = "l2_assist"
    L3_AUTONOMOUS = "l3_autonomous"


class LoopStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    NEEDS_HUMAN = "needs_human"
    COMPLETED = "completed"
    BUDGET_EXCEEDED = "budget_exceeded"
    ERROR = "error"


LOOP_PATTERNS: dict[str, dict[str, Any]] = {
    "daily-triage": {
        "name": "Daily Triage",
        "description": "每天扫描问题、分类优先级、报告High Priority/Watch List/Noise",
        "execution_status": "scaffolding_only",  # 生成脚手架，运行走 guidance 模式
        "default_stage": LoopStage.L1_REPORT,
        "l1_capability": "只报告，不修改",
        "l2_capability": "小步自动修复，Verifier独立验证",
        "l3_capability": "无人值守修复+PR（需要denylist）",
        "denylist": ["auth/", "payment/", "security/"],
        "max_rounds": 3,
        "sub_agents": [
            {"role": "scanner", "agent_file": None, "parallel": False},
        ],
    },
    "knowledge-hygiene": {
        "name": "Knowledge Hygiene",
        "description": "定期清理知识库：过期文档、重复skill、intent debt检测、偿还三笔债",
        "execution_status": "implemented",  # runner._run_knowledge_hygiene 实际执行
        "default_stage": LoopStage.L1_REPORT,
        "l1_capability": "只报告：过期文档、重复skill、缺失的项目约定",
        "l2_capability": "更新时间戳、标记重复、整理索引",
        "l3_capability": "（不建议自动删除）提示用户确认后清理",
        "denylist": [],
        "max_rounds": 2,
        "sub_agents": [
            {"role": "manifest_scanner", "agent_file": None, "parallel": True},
            {"role": "skill_scanner", "agent_file": None, "parallel": True},
            {"role": "knowledge_scanner", "agent_file": None, "parallel": True},
        ],
    },
    "ci-sweeper": {
        "name": "CI Sweeper",
        "description": "监控CI失败，尝试分类和修复flaky test",
        "execution_status": "scaffolding_only",  # 生成脚手架，运行走 guidance 模式
        "default_stage": LoopStage.L1_REPORT,
        "l1_capability": "报告CI失败列表",
        "l2_capability": "尝试修复明显问题，跑测试验证",
        "l3_capability": "自动提交修复PR",
        "denylist": ["auth/", "payment/"],
        "max_rounds": 3,
        "sub_agents": [
            {"role": "ci_monitor", "agent_file": None, "parallel": False},
            {"role": "builder", "agent_file": "builder.md", "parallel": False},
            {"role": "checker", "agent_file": "checker.md", "parallel": False},
        ],
    },
    "pr-babysitter": {
        "name": "PR Babysitter",
        "description": "盯PR状态，检查CI，提醒reviewer，处理反馈",
        "execution_status": "scaffolding_only",  # 生成脚手架，运行走 guidance 模式
        "default_stage": LoopStage.L1_REPORT,
        "l1_capability": "报告PR状态和CI结果",
        "l2_capability": "回应review评论，修复小问题",
        "l3_capability": "自动merge（需严格条件）",
        "denylist": [],
        "max_rounds": 5,
        "sub_agents": [
            {"role": "pr_monitor", "agent_file": None, "parallel": False},
        ],
    },
    "issue-triage": {
        # 对应 Cobus Greyling loop-engineering 7 套工作流中的 "Issue Triage"。
        # 设计目标：把"积压 Issue 太乱"这类持续但低风险任务系统化。
        # 默认 L1：只分类/打标，不修改代码；升级到 L2 可关闭明显重复/无效 issue。
        "name": "Issue Triage",
        "description": "扫描未分配/无标签的 issue，按优先级分类，建议标签/负责人，关闭明显无效项",
        "execution_status": "scaffolding_only",
        "default_stage": LoopStage.L1_REPORT,
        "l1_capability": "报告未分类 issue 列表 + 推荐标签/优先级 + 疑似重复项",
        "l2_capability": "为 issue 打标签/分配人，关闭明显重复或已超时的 stale issue",
        "l3_capability": "无人值守自动分诊 + 周报（需denylist保护安全敏感issue）",
        "denylist": ["label:security", "label:auth-bypass", "*P0*"],
        "max_rounds": 3,
        "sub_agents": [
            {"role": "issue_scanner", "agent_file": None, "parallel": False},
            {"role": "duplicate_detector", "agent_file": None, "parallel": True},
            {"role": "label_suggester", "agent_file": None, "parallel": True},
        ],
    },
    "changelog-draft": {
        # 对应 Cobus Greyling loop-engineering 7 套工作流中的 "Changelog Drafter"。
        # 设计目标：把"发布前翻几十条 commit 写 changelog"自动化。
        # 默认 L1：基于 git log 自动生成 changelog 草稿；L2 可自动追加到 CHANGELOG.md。
        "name": "Changelog Drafter",
        "description": "扫描自上次 release 以来的 commits/PRs，按 conventional commits 分类生成 CHANGELOG 草稿",
        "execution_status": "scaffolding_only",
        "default_stage": LoopStage.L1_REPORT,
        "l1_capability": "生成草稿写入 STATE.md 的 Changelog Draft 段（不修改 CHANGELOG.md）",
        "l2_capability": "将草稿自动追加到 CHANGELOG.md 的 [Unreleased] 段（人类review后commit）",
        "l3_capability": "无人值守：自动 bump version + commit CHANGELOG.md（需严格tag/分支保护）",
        "denylist": ["CHANGELOG.md"],  # L2 默认追加到段内；L3 须人工触发 tag
        "max_rounds": 2,
        "sub_agents": [
            {"role": "commit_classifier", "agent_file": None, "parallel": False},
            {"role": "pr_summarizer", "agent_file": None, "parallel": True},
        ],
    },
    "multi-perspective": {
        # 借鉴 ai-berkshire 的多视角并行框架：N 个 Agent 从不同视角并行分析
        # 同一标的，Team Lead（synthesizer）汇总成报告。适合分析类任务（非修复类）。
        "name": "Multi-Perspective Analysis",
        "description": "N 个 Agent 从不同视角并行分析同一标的，synthesizer 汇总成报告。适合分析类任务",
        "execution_status": "implemented",  # runner._run_multi_perspective 实际执行
        "default_stage": LoopStage.L2_ASSIST,
        "l1_capability": "各视角只读分析，汇总报告（不修改代码）",
        "l2_capability": "各视角并行分析 + synthesizer 综合结论（含明确评级）",
        "l3_capability": "无人值守并行分析 + 自动归档（需 denylist 保护敏感路径）",
        "denylist": ["auth/", "payment/", "security/", ".env", "*.key"],
        "max_rounds": 2,  # 分析类任务通常 1 轮即出报告，2 轮兜底
        "generates_agents": True,  # 生成 perspective.md + summary.md 模板
        "sub_agents": [
            {"role": "perspective_1", "agent_file": "perspective.md", "parallel": True},
            {"role": "perspective_2", "agent_file": "perspective.md", "parallel": True},
            {"role": "perspective_3", "agent_file": "perspective.md", "parallel": True},
            {"role": "synthesizer", "agent_file": "summary.md", "parallel": False},
        ],
    },
    "builder-checker": {
        "name": "Builder/Checker Loop",
        "description": "写代码和查代码拆成两个Agent，编排器循环调度，查到全绿为止。三文件模式：builder.md + checker.md + loop编排器",
        "execution_status": "implemented",  # runner._run_builder_checker 实际执行
        "default_stage": LoopStage.L2_ASSIST,
        "l1_capability": "builder只读分析，checker只报告（不修改）",
        "l2_capability": "builder写代码，checker跑检查，循环到ALL GREEN或停止条件触发",
        "l3_capability": "无人值守循环+自动提PR（需denylist和严格停止规则）",
        "denylist": ["auth/", "payment/", "security/", ".env", "*.key"],
        "max_rounds": 5,
        "generates_agents": True,
        "sub_agents": [
            {"role": "builder", "agent_file": "builder.md", "parallel": False},
            {"role": "checker_lint", "agent_file": "checker.md", "parallel": True, "check_type": "lint"},
            {"role": "checker_type", "agent_file": "checker.md", "parallel": True, "check_type": "typecheck"},
            {"role": "checker_test", "agent_file": "checker.md", "parallel": True, "check_type": "test"},
        ],
    },
}

# ── Stop rules (七条停止条件) ─────────────────────────────────────────
#
# 设计原则（第一性原理）：
# - 规则应互斥：每个停止场景只归一类，避免遮蔽。
# - 评估顺序 = STOP_RULES 列表顺序 = 诊断优先级（最具体诊断优先）。
# - ALL GREEN 实为成功条件（非停止），列为首条便于统一查阅，action=stop_success。
# - budget_exceeded 与 rounds_exhausted 同属"资源耗尽"，列入规则保证可发现性
#   （实际由 record_round 状态机处理，check_stop_rules 不重复检查）。
#
# 互斥条件（regression / same_failure_twice / no_progress 三者不重叠）：
#   regression        : new ≠ ∅ AND overlap ≠ ∅      （改相关代码引入新失败）
#   same_failure_twice: new = ∅ AND overlap ≠ ∅ AND count未减 （纯重复）
#   no_progress       : new ≠ ∅ AND overlap = ∅ AND fixed ≠ ∅ AND count未减 （全换）

STOP_RULES: list[dict[str, Any]] = [
    {
        "id": "all_green",
        "name": "ALL GREEN",
        "description": "所有检查通过（成功条件，非停止）。停止，附上每项检查的通过证明。",
        "action": "stop_success",
        # 经验D：成功条件，硬性
        "hard_gate": True,
    },
    {
        "id": "rounds_exhausted",
        "name": "轮次用尽",
        "description": "达到轮次上限。停止，报告仍失败的项、每轮尝试了什么、为什么没成功。",
        "action": "stop_escalate",
        # 经验D：资源耗尽必须停
        "hard_gate": True,
    },
    {
        "id": "budget_exceeded",
        "name": "预算耗尽",
        "description": "token 预算用尽。停止，报告已消耗预算与剩余失败项（由 record_round 状态机处理）。",
        "action": "stop_escalate",
        "hard_gate": True,
    },
    {
        "id": "beyond_capability",
        "name": "疑似超出能力边界",
        "description": "builder反复尝试但失败原因涉及它无法访问的外部依赖或环境问题。停止，报告阻塞点。",
        "action": "stop_escalate",
        # 经验D：外部问题无法继续
        "hard_gate": True,
    },
    {
        "id": "regression",
        "name": "回归",
        "description": "修复导致之前通过的检查失败（引入新失败且有重复失败）。停止，说明改了什么导致了回归。",
        "action": "stop_escalate",
        # 经验D：改坏了必须停
        "hard_gate": True,
    },
    {
        "id": "same_failure_twice",
        "name": "同一失败连续两轮",
        "description": "builder在猜，不是在修（纯重复，无新失败引入）。停止，升级给人。",
        "action": "stop_escalate",
        # 经验D：在猜必须停
        "hard_gate": True,
    },
    {
        "id": "no_progress",
        "name": "无实质进展",
        "description": "连续2轮失败项数量没有减少且失败集合完全更换。停止，可能任务范围过大，需要拆分成更小的子任务。",
        "action": "stop_escalate",
        # 经验D：可能只是任务大，拆分后可继续（软门禁）
        "hard_gate": False,
    },
]

# ── Report format standards (报告格式标准) ─────────────────────────────

BUILDER_REPORT_FORMAT = """## Builder 汇报格式
修改完成后，先本地跑一遍 checker 会执行的命令，确认通过再汇报。

汇报格式：
  改了什么：<一句话>
  修改文件：<file1>, <file2>, ...
  本地检查结果：<通过/失败>
"""

CHECKER_REPORT_FORMAT = """## Checker 报告格式

全部通过时：
  ALL GREEN
  然后逐项列出每项检查的名称和通过证明（如 "test: 848 passed, 0 failed"）。
  不要只说全过了。

任何失败时：
  FAILED
  然后逐条列出：
    file:line - 什么坏了 - 哪个检查抓到的

  如果同一文件有多个失败，合并列出。如果多个失败可能是同一根因，标注疑似同源。

  报告末尾必须附上结构化失败协议块（供编排器解析，便于跨轮次比对同一失败）：
    <!-- failures:json -->
    {"passed": false, "failures": [{"file": "src/auth.py", "line": 42, "type": "ImportError"}]}
    <!-- /failures -->

  说明：file 是失败文件路径（不含行号以免行号漂移误判），type 是错误类型/检查名。
  全部通过时输出 {"passed": true, "failures": []}。
"""

# ── Red lines (红线) ───────────────────────────────────────────────────

BUILDER_RED_LINES = [
    "绝不弱化测试来让它通过。修代码，不是修测试。",
    "绝不通过删除、注释、跳过失败的检查来达到通过。",
    "绝不在没有跑过检查的情况下声称已修复。",
    "不要顺手重构不相关的代码。每一行多余改动都可能引入新问题。",
]

CHECKER_RED_LINES = [
    "绝不意译失败信息。复制真实错误输出的关键行。",
    "绝不因为看起来是小问题而省略失败项。",
    "绝不自己尝试修复。你只负责报告，修复是builder的事。",
    "绝不修改自己的工具白名单来获得Write/Edit权限。",
]

ORCHESTRATOR_RULES = [
    "把checker的完整失败报告原样转发给builder，不要自己解读或过滤。",
    "builder需要原始错误信息（行号、堆栈轨迹、中间输出）来定位根因。",
    "每轮开始时公开声明 'Cycle N/最大轮次'。",
    "如果同一失败连续出现两次，停止循环。",
    "如果修复导致之前通过的检查失败，停止循环。",
]


@dataclass
class LoopRound:
    round_num: int
    timestamp: str
    action: str
    result_summary: str
    verifier_result: str
    passed: bool
    next_action: str = ""
    failure_count: int = 0
    failure_items: list[str] = field(default_factory=list)
    tokens_used: int = 0
    agent_reports: dict[str, str] = field(default_factory=dict)
    # 经验A：该轮对应的基线失败项快照（历史已知失败，用于 regression 判定时排除）
    baseline_failures: list[str] = field(default_factory=list)
    # P0-1：停止规则触发时的诊断信息（matched_signals / blocker / new_failures 等）。
    # 由 record_round 在 check_stop_rules 返回后回填，随 meta 持久化，供 CLI 展示与跨会话追溯。
    escalation_info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "action": self.action,
            "result_summary": self.result_summary,
            "verifier_result": self.verifier_result,
            "passed": self.passed,
            "next_action": self.next_action,
            "failure_count": self.failure_count,
            "failure_items": self.failure_items,
            "tokens_used": self.tokens_used,
            "agent_reports": self.agent_reports,
            "baseline_failures": self.baseline_failures,
            "escalation_info": self.escalation_info,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopRound:
        # Normalize explicit None to field defaults. `.get(key, default)` returns
        # None (not the default) when the key exists with a None value, which
        # would crash downstream `set(failure_items)` / `dict(agent_reports)`.
        failure_items = data.get("failure_items") or []
        agent_reports = data.get("agent_reports") or {}
        baseline_failures = data.get("baseline_failures") or []
        escalation_info = data.get("escalation_info") or {}
        return cls(
            round_num=data.get("round_num", 0),
            timestamp=data.get("timestamp", ""),
            action=data.get("action", ""),
            result_summary=data.get("result_summary", ""),
            verifier_result=data.get("verifier_result", ""),
            passed=data.get("passed", False),
            next_action=data.get("next_action", ""),
            failure_count=data.get("failure_count", 0),
            failure_items=failure_items if isinstance(failure_items, list) else [],
            tokens_used=data.get("tokens_used", 0),
            agent_reports=agent_reports if isinstance(agent_reports, dict) else {},
            baseline_failures=baseline_failures if isinstance(baseline_failures, list) else [],
            escalation_info=escalation_info if isinstance(escalation_info, dict) else {},
        )


@dataclass
class LoopState:
    name: str
    pattern: str
    stage: LoopStage
    status: LoopStatus
    config_path: Path
    state_path: Path
    budget_path: Path
    created_at: str
    last_run: str | None = None
    current_round: int = 0
    max_rounds: int = 5
    rounds: list[LoopRound] = field(default_factory=list)
    budget_used_tokens: int = 0
    budget_limit_tokens: int = 500000
    high_priority_items: list[str] = field(default_factory=list)
    watch_list: list[str] = field(default_factory=list)
    noise_items: list[str] = field(default_factory=list)
    # 经验A：基线失败项（历史已知失败），regression 判定时排除，只计新增失败
    baseline_failures: list[str] = field(default_factory=list)
    # 经验B：审计软门禁留疤（未通过的检查项名称列表，软门禁失败留痕但不阻断）
    audit_warnings: list[str] = field(default_factory=list)
    # 经验F：产物清单（期望产出的文件路径列表，每轮校验存在性）
    deliverables: list[str] = field(default_factory=list)


# meta.json schema version. Bump when the persisted shape changes; add a
# migration branch in _load_loop_meta. Old files without this key are v0.
META_SCHEMA_VERSION = 1


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def loops_dir() -> Path:
    return _project_root() / ".loops"


def _loop_config_path(name: str) -> Path:
    return loops_dir() / name / "LOOP.md"


def _loop_state_path(name: str) -> Path:
    return loops_dir() / name / "STATE.md"


def _loop_budget_path(name: str) -> Path:
    return loops_dir() / name / "loop-budget.md"


def _loop_meta_path(name: str) -> Path:
    return loops_dir() / name / "meta.json"


def _ensure_loops_dir() -> None:
    loops_dir().mkdir(parents=True, exist_ok=True)


def list_loops() -> list[LoopState]:
    _ensure_loops_dir()
    result: list[LoopState] = []
    if not loops_dir().exists():
        return result
    for entry in sorted(loops_dir().iterdir()):
        if entry.is_dir() and (entry / "meta.json").exists():
            try:
                meta = json.loads((entry / "meta.json").read_text(encoding="utf-8"))
                state = _load_loop_meta(meta, entry.name)
                if state:
                    result.append(state)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                # ValueError covers enum members that no longer exist after a
                # schema change (previously swallowed silently, hiding loops).
                logger.warning("Skipping loop '%s' with unreadable meta: %s", entry.name, exc)
                continue
    return result


def _load_loop_meta(meta: dict[str, Any], name: str) -> LoopState | None:
    loop_dir = loops_dir() / name
    # Schema version check + migration. v0 = files written before versioning
    # existed (0.2.0 era); they lack agent_reports/tokens_used on rounds but
    # LoopRound.from_dict already defaults those. Surface a warning instead of
    # silently swallowing enum ValueErrors (which previously made loops
    # disappear from `list` with no log).
    version = meta.get("schema_version", 0)
    if version > META_SCHEMA_VERSION:
        logger.warning(
            "Loop '%s' meta.json schema_version=%s is newer than supported %s; "
            "loading with best-effort defaults.",
            name,
            version,
            META_SCHEMA_VERSION,
        )
    rounds_data = meta.get("rounds", [])
    rounds = [LoopRound.from_dict(r) for r in rounds_data]
    # 经验A/B/F：新字段读取，缺省为空列表（向后兼容旧 meta.json）
    baseline_failures = meta.get("baseline_failures") or []
    audit_warnings = meta.get("audit_warnings") or []
    deliverables = meta.get("deliverables") or []
    return LoopState(
        name=name,
        pattern=meta.get("pattern", "custom"),
        stage=LoopStage(meta.get("stage", LoopStage.L1_REPORT.value)),
        status=LoopStatus(meta.get("status", LoopStatus.IDLE.value)),
        config_path=loop_dir / "LOOP.md",
        state_path=loop_dir / "STATE.md",
        budget_path=loop_dir / "loop-budget.md",
        created_at=meta.get("created_at", ""),
        last_run=meta.get("last_run"),
        current_round=meta.get("current_round", 0),
        max_rounds=meta.get("max_rounds", 5),
        rounds=rounds,
        budget_used_tokens=meta.get("budget_used_tokens", 0),
        budget_limit_tokens=meta.get("budget_limit_tokens", 500000),
        high_priority_items=meta.get("high_priority_items", []),
        watch_list=meta.get("watch_list", []),
        noise_items=meta.get("noise_items", []),
        baseline_failures=baseline_failures if isinstance(baseline_failures, list) else [],
        audit_warnings=audit_warnings if isinstance(audit_warnings, list) else [],
        deliverables=deliverables if isinstance(deliverables, list) else [],
    )


def _save_loop_meta(state: LoopState) -> None:
    _ensure_loops_dir()
    loop_dir = loops_dir() / state.name
    loop_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema_version": META_SCHEMA_VERSION,
        "pattern": state.pattern,
        "stage": state.stage.value,
        "status": state.status.value,
        "created_at": state.created_at,
        "last_run": state.last_run,
        "current_round": state.current_round,
        "max_rounds": state.max_rounds,
        "rounds": [r.to_dict() for r in state.rounds],
        "budget_used_tokens": state.budget_used_tokens,
        "budget_limit_tokens": state.budget_limit_tokens,
        "high_priority_items": state.high_priority_items,
        "watch_list": state.watch_list,
        "noise_items": state.noise_items,
        # 经验A/B/F：新字段序列化（list[str] 在 JSON 中原生可序列化）
        "baseline_failures": state.baseline_failures,
        "audit_warnings": state.audit_warnings,
        "deliverables": state.deliverables,
    }
    (loop_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def init_loop(name: str, pattern: str = "custom") -> dict[str, Any]:
    _ensure_loops_dir()
    loop_dir = loops_dir() / name

    if loop_dir.exists():
        return {"success": False, "error": f"Loop '{name}' already exists"}

    pattern_info = LOOP_PATTERNS.get(pattern, {})
    now = datetime.now(timezone.utc).isoformat()
    default_stage = pattern_info.get("default_stage", LoopStage.L1_REPORT)
    max_rounds = pattern_info.get("max_rounds", 5)
    budget_limit = pattern_info.get("budget_limit_tokens", 500000)

    loop_dir.mkdir(parents=True, exist_ok=True)

    loop_md = f"""# Loop: {name}

## Pattern
{pattern_info.get('name', pattern.replace('-', ' ').title())}
{pattern_info.get('description', 'Custom loop')}

## Stage (分阶段上线)
**当前阶段: {default_stage.value}**

| 阶段 | 能力 | 状态 |
|------|------|------|
| L1 只报告 | {pattern_info.get('l1_capability', '只生成报告，不做任何修改')} | {'✓ 当前' if default_stage == LoopStage.L1_REPORT else ''} |
| L2 辅助修复 | {pattern_info.get('l2_capability', '小步修复 + 独立Verifier验证')} | {'✓ 当前' if default_stage == LoopStage.L2_ASSIST else ''} |
| L3 无人值守 | {pattern_info.get('l3_capability', '自动执行（需严格denylist）')} | {'✓ 当前' if default_stage == LoopStage.L3_AUTONOMOUS else ''} |

## 目标定义（四步框架）
1. **完成标准（可机器验证）**:
   - TODO: 定义什么叫"做完了"

2. **边界条件（Harness约束，不能怎么做）**:
   - 禁止删除文件
   - 禁止修改denylist中的路径: {', '.join(pattern_info.get('denylist', []))}
   - TODO: 补充其他约束

3. **降级方案（失败怎么办）**:
   - {max_rounds}轮后仍未完成 → 列出未解决项，交给用户决策

4. **目标分层**:
   - 全局约束: 不破坏现有功能，所有测试通过
   - 当前任务: TODO

## Maker/Checker 分离
- **Planner**: 分析状态，生成本轮执行计划
- **Generator (builder)**: 执行具体任务（有Write/Edit工具）
- **Evaluator (checker)（独立）**: 验证结果（无Write/Edit工具，工具级硬隔离）

### 关键原则：不过滤
编排器必须把checker的完整失败报告**原样转发**给builder，不要自己解读或过滤。
builder需要原始错误信息（行号、堆栈轨迹、中间输出）来定位根因。
总结会丢失关键细节，浪费整整一轮循环。

### 报告格式
- builder汇报: 改了什么 / 修改文件 / 本地检查结果
- checker报告: ALL GREEN + 逐项通过证明 / FAILED + file:line - 什么坏了 - 哪个检查抓到的

## Denylist（高风险路径，L3也不能碰）
{chr(10).join('- ' + d for d in pattern_info.get('denylist', [])) or '- （暂无）'}

## 停止规则（七条刹车条件）
1. ALL GREEN：所有检查通过 → 停止
2. 轮次用尽：达到{max_rounds}轮上限 → 停止，升级
3. 预算耗尽：token 预算用尽 → 停止，升级（由 record_round 状态机处理）
4. 超出能力边界：外部依赖问题 → 停止，报告阻塞点（前置于回归）
5. 回归：修复导致新失败且有持续失败 → 停止，升级
6. 同一失败连续两轮：builder在猜 → 停止，升级
7. 无实质进展：连续2轮失败数未减且失败集合完全更换 → 停止，拆分任务

详见 stop-rules.md
"""

    state_md = f"""# Loop State: {name}

Last updated: {now}

## Configuration
- Pattern: {pattern}
- Stage: {default_stage.value}
- Max rounds: {max_rounds}
- Budget limit: {budget_limit} tokens

## High Priority
（需要立即处理的项）

## Watch List
（需要关注但不紧急）

## Recent Noise (ignored)
（可忽略的噪音）

## Execution History
（每轮执行结果记录在此）
"""

    budget_md = f"""# Loop Budget: {name}

## Token Budget
- Limit: {budget_limit} tokens per run
- Estimated per-round cost: ~50000 tokens
- Estimated max runs per budget: ~{budget_limit // 50000} rounds

## Cost Guardrails
- 达到预算80% → 警告，建议人工检查
- 达到预算100% → 自动停止，通知用户
- 同一问题自动修复超过3次 → 升级给人

## Run Log
| Date | Round | Tokens Used | Result | Notes |
|------|-------|-------------|--------|-------|
| {now[:10]} | 0 | 0 | initialized | Loop created |
"""

    (loop_dir / "LOOP.md").write_text(loop_md, encoding="utf-8")
    (loop_dir / "STATE.md").write_text(state_md, encoding="utf-8")
    (loop_dir / "loop-budget.md").write_text(budget_md, encoding="utf-8")

    files_created = ["LOOP.md", "STATE.md", "loop-budget.md"]

    # Generate builder/checker agent definitions for builder-checker pattern
    if pattern_info.get("generates_agents"):
        if pattern == "multi-perspective":
            # multi-perspective 生成 perspective.md + summary.md 模板
            perspective_md = _generate_perspective_md(name, pattern_info)
            summary_md = _generate_summary_md(name)
            (loop_dir / "perspective.md").write_text(perspective_md, encoding="utf-8")
            (loop_dir / "summary.md").write_text(summary_md, encoding="utf-8")
            files_created.extend(["perspective.md", "summary.md"])
        else:
            builder_md = _generate_builder_md(name, pattern_info)
            checker_md = _generate_checker_md(name)
            stop_rules_md = _generate_stop_rules_md(name, max_rounds)
            (loop_dir / "builder.md").write_text(builder_md, encoding="utf-8")
            (loop_dir / "checker.md").write_text(checker_md, encoding="utf-8")
            (loop_dir / "stop-rules.md").write_text(stop_rules_md, encoding="utf-8")
            files_created.extend(["builder.md", "checker.md", "stop-rules.md"])

    state = LoopState(
        name=name,
        pattern=pattern,
        stage=default_stage,
        status=LoopStatus.IDLE,
        config_path=loop_dir / "LOOP.md",
        state_path=loop_dir / "STATE.md",
        budget_path=loop_dir / "loop-budget.md",
        created_at=now,
        max_rounds=max_rounds,
        budget_limit_tokens=budget_limit,
    )
    _save_loop_meta(state)

    return {
        "success": True,
        "name": name,
        "pattern": pattern,
        "stage": default_stage.value,
        "path": str(loop_dir),
        "files": files_created,
    }


def get_loop(name: str) -> LoopState | None:
    loops = list_loops()
    for loop in loops:
        if loop.name == name:
            return loop
    return None


def audit_loop(name: str | None = None) -> dict[str, Any]:
    loops = [get_loop(name)] if name else list_loops()
    loops = [loop for loop in loops if loop is not None]

    if not loops:
        if name:
            return {"success": False, "error": f"Loop '{name}' not found"}
        return {"success": True, "total": 0, "score": 0, "checks": [], "warnings": [], "suggestions": ["No loops created yet. Run `hermes loop init <name>` to start."]}

    results: list[dict[str, Any]] = []
    total_score = 0

    for loop in loops:
        checks: list[dict[str, Any]] = []
        score = 0
        suggestions: list[str] = []

        checks.append({
            "name": "STATE.md exists",
            "passed": loop.state_path.exists(),
            "weight": 8,
            "hard_gate": False,
        })
        if loop.state_path.exists():
            score += 8
        else:
            suggestions.append("Create STATE.md for cross-session state tracking")

        checks.append({
            "name": "LOOP.md has completion criteria",
            "passed": False,
            "weight": 15,
            # 经验D：完成标准是硬门禁
            "hard_gate": True,
        })
        if loop.config_path.exists():
            content = loop.config_path.read_text(encoding="utf-8")
            has_criteria = "TODO" not in content.split("完成标准")[1].split("##")[0] if "完成标准" in content else False
            checks[-1]["passed"] = has_criteria
            if has_criteria:
                score += 15
            else:
                suggestions.append("Define machine-verifiable completion criteria in LOOP.md (avoid TODO)")
        else:
            suggestions.append("Create LOOP.md with goal definition")

        checks.append({
            "name": "Has Harness boundaries",
            "passed": loop.config_path.exists() and "边界条件" in loop.config_path.read_text(encoding="utf-8"),
            "weight": 10,
            "hard_gate": False,
        })
        if checks[-1]["passed"]:
            score += 10
        else:
            suggestions.append("Add boundary conditions (Harness constraints) to prevent Goodhart's Law")

        checks.append({
            "name": "Uses L1 stage (start conservative)",
            "passed": loop.stage == LoopStage.L1_REPORT,
            "weight": 8,
            "hard_gate": False,
        })
        if checks[-1]["passed"]:
            score += 8
        elif loop.stage == LoopStage.L2_ASSIST:
            score += 4
            suggestions.append("Consider running in L1 (report-only) first before enabling auto-fix")

        checks.append({
            "name": "Has fallback plan",
            "passed": loop.config_path.exists() and "降级" in loop.config_path.read_text(encoding="utf-8"),
            "weight": 8,
            "hard_gate": False,
        })
        if checks[-1]["passed"]:
            score += 8
        else:
            suggestions.append("Add a fallback plan (what to do when max rounds reached)")

        checks.append({
            "name": "Budget configured",
            "passed": loop.budget_path.exists(),
            "weight": 8,
            "hard_gate": False,
        })
        if checks[-1]["passed"]:
            score += 8
        else:
            suggestions.append("Configure token budget in loop-budget.md to prevent runaway costs")

        checks.append({
            "name": "Maker/Checker separation documented",
            "passed": loop.config_path.exists() and "Evaluator" in loop.config_path.read_text(encoding="utf-8"),
            "weight": 10,
            "hard_gate": False,
        })
        if checks[-1]["passed"]:
            score += 10
        else:
            suggestions.append("Document Planner/Generator/Evaluator separation (no self-evaluation!)")

        checks.append({
            "name": "Max rounds set",
            "passed": loop.max_rounds > 0 and loop.max_rounds <= 10,
            "weight": 8,
            "hard_gate": False,
        })
        if checks[-1]["passed"]:
            score += 8
        else:
            suggestions.append("Set reasonable max rounds (3-10) to prevent infinite loops")

        # New checks from "three files" article
        checks.append({
            "name": "Stop rules defined (7 conditions)",
            "passed": False,
            "weight": 12,
            # 经验D：停止规则是硬门禁
            "hard_gate": True,
        })
        loop_dir = loops_dir() / loop.name
        stop_rules_path = loop_dir / "stop-rules.md"
        if stop_rules_path.exists():
            content = stop_rules_path.read_text(encoding="utf-8")
            has_all_rules = all(
                rule["name"] in content
                for rule in STOP_RULES
            )
            checks[-1]["passed"] = has_all_rules
            if has_all_rules:
                score += 12
            else:
                suggestions.append("Define all 7 stop rules in stop-rules.md (budget exceeded, same failure twice, regression, no progress, etc.)")
        else:
            # Check if stop rules are in LOOP.md
            if loop.config_path.exists():
                content = loop.config_path.read_text(encoding="utf-8")
                if "停止规则" in content and "同一失败" in content:
                    checks[-1]["passed"] = True
                    score += 12
                else:
                    suggestions.append("Define stop rules: same failure twice, regression, no progress detection")
            else:
                suggestions.append("Create stop-rules.md with 7 stop conditions")

        checks.append({
            "name": "Tool-level isolation (checker has no Write/Edit)",
            "passed": False,
            "weight": 13,
            # 经验D：安全红线，硬门禁
            "hard_gate": True,
        })
        checker_path = loop_dir / "checker.md"
        if checker_path.exists():
            content = checker_path.read_text(encoding="utf-8")
            # Verify checker.md explicitly excludes Write and Edit from tools
            has_tools_line = "tools:" in content
            no_write = "Write" not in content.split("tools:")[1].split("\n")[0] if has_tools_line else False
            no_edit = "Edit" not in content.split("tools:")[1].split("\n")[0] if has_tools_line else False
            checks[-1]["passed"] = has_tools_line and no_write and no_edit
            if checks[-1]["passed"]:
                score += 13
            else:
                suggestions.append("Ensure checker.md tools field excludes Write and Edit (tool-level hard isolation)")
        else:
            # For non-builder-checker patterns, check if LOOP.md mentions tool isolation
            if loop.config_path.exists():
                content = loop.config_path.read_text(encoding="utf-8")
                if "工具级硬隔离" in content or "tool-level" in content.lower():
                    checks[-1]["passed"] = True
                    score += 13
                else:
                    suggestions.append("Document tool-level isolation: checker must not have Write/Edit tools")
            else:
                suggestions.append("Document tool-level isolation: checker must not have Write/Edit tools")

        # 借鉴 ai-berkshire：multi-perspective pattern 的 summary.md 必须含明确结论
        # （反端水硬约束）。仅约束 multi-perspective，不影响其他 pattern。
        if loop.pattern == "multi-perspective":
            loop_dir = loops_dir() / loop.name
            summary_path = loop_dir / "summary.md"
            has_conclusion = False
            if summary_path.exists():
                content = summary_path.read_text(encoding="utf-8")
                has_conclusion = "<!-- conclusion:" in content
            checks.append({
                "name": "Summary has explicit conclusion (anti-fence-sitter)",
                "passed": has_conclusion,
                "weight": 12,
                "hard_gate": True,
            })
            if has_conclusion:
                score += 12
            else:
                suggestions.append("summary.md must contain <!-- conclusion: --> marker (anti-fence-sitter)")

        total_score += score
        # 经验B：软门禁留疤——收集未通过检查的 name（不是 suggestions）
        loop_warnings = [c["name"] for c in checks if not c["passed"]]
        # 持久化 audit_warnings 到 meta.json，供 _update_state_md 在 STATE.md 留痕
        loop.audit_warnings = loop_warnings
        _save_loop_meta(loop)
        results.append({
            "loop": loop.name,
            "pattern": loop.pattern,
            "stage": loop.stage.value,
            "score": score,
            "checks": checks,
            "suggestions": suggestions,
            "warnings": loop_warnings,
        })

    avg_score = total_score // len(results) if results else 0
    readiness = "Not Ready"
    if avg_score >= 80:
        readiness = "Production Ready"
    elif avg_score >= 60:
        readiness = "L1 Ready (report-only)"
    elif avg_score >= 40:
        readiness = "Needs Work"

    # 经验B：顶层汇总所有未通过检查的 name（扁平列表）
    all_warnings = [w for r in results for w in r["warnings"]]
    return {
        "success": True,
        "total": len(results),
        "average_score": avg_score,
        "readiness": readiness,
        "loops": results,
        "warnings": all_warnings,
    }


# 声明性标记协议：与 <!-- failures:json --> 一脉相承，agent 在产物中写标记，
# Hermes 解析校验。校验"标记存在性"，不校验"内容真假"（后者需用户自验）。
_CLAIM_RE = re.compile(r"<!--\s*claim:\s*(.+?)\s*-->")
_CONCLUSION_RE = re.compile(r"<!--\s*conclusion:\s*(.+?)\s*-->")


def audit_deliverables(name: str) -> dict[str, Any]:
    """借鉴 ai-berkshire report_audit.py：抽检 loop 的 deliverables 产物。

    检查项：
    1. deliverables 中每个文件存在性（复用现有 missing_deliverables 逻辑）
    2. 每个文件中 <!-- claim: --> 标记数量（≥1 为合格，0 为 warning）
    3. multi-perspective pattern 的 summary.md 必须含 <!-- conclusion: --> 标记

    返回 {"missing": [...], "claim_warnings": [...], "conclusion_missing": bool}
    """
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    missing = [d for d in loop.deliverables if not Path(d).exists()] if loop.deliverables else []
    claim_warnings: list[str] = []
    conclusion_missing = False

    if loop.deliverables:
        for deliverable_path in loop.deliverables:
            p = Path(deliverable_path)
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8")
            claims = _CLAIM_RE.findall(content)
            if len(claims) == 0:
                claim_warnings.append(f"{p.name}: no <!-- claim: --> markers found")

    # multi-perspective 的 summary.md 必须含 conclusion 标记
    if loop.pattern == "multi-perspective":
        loop_dir = loops_dir() / loop.name
        summary_path = loop_dir / "summary.md"
        if summary_path.exists():
            content = summary_path.read_text(encoding="utf-8")
            if not _CONCLUSION_RE.search(content):
                conclusion_missing = True
        else:
            conclusion_missing = True

    return {
        "success": True,
        "missing": missing,
        "claim_warnings": claim_warnings,
        "conclusion_missing": conclusion_missing,
    }


def estimate_cost(name: str) -> dict[str, Any]:
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    # P0-2：用历史平均估算每轮 token，带护栏。
    # 护栏1：过滤 tokens_used=0 的轮次（未实际执行或记录缺失，会拉低均值）。
    # 护栏2：最小样本量——有效样本 < 3 时回退固定 50k。
    #   根因：若 loop 只跑了 1 轮就因 beyond_capability 停止，历史均值要么极低
    #  （import error 早停）要么极高（builder 读了很多文件），外推不如固定值稳定。
    FALLBACK = 50000
    MIN_SAMPLE = 3
    token_rounds = [r for r in loop.rounds if r.tokens_used > 0]
    if len(token_rounds) >= MIN_SAMPLE:
        per_round_tokens = sum(r.tokens_used for r in token_rounds) // len(token_rounds)
        estimate_source = "historical_avg"
    else:
        per_round_tokens = FALLBACK
        estimate_source = "fallback_default"

    max_rounds = loop.max_rounds
    total_estimate = per_round_tokens * max_rounds
    budget_remaining = loop.budget_limit_tokens - loop.budget_used_tokens
    rounds_remaining = budget_remaining // per_round_tokens if per_round_tokens > 0 else 0

    return {
        "success": True,
        "loop": name,
        "per_round_estimate_tokens": per_round_tokens,
        "estimate_source": estimate_source,
        "max_rounds": max_rounds,
        "total_estimate_tokens": total_estimate,
        "budget_limit_tokens": loop.budget_limit_tokens,
        "budget_used_tokens": loop.budget_used_tokens,
        "budget_remaining_tokens": budget_remaining,
        "estimated_rounds_remaining": rounds_remaining,
        "within_budget": total_estimate <= loop.budget_limit_tokens,
    }


def loop_metrics(name: str) -> dict[str, Any]:
    """Aggregate execution metrics from a loop's recorded rounds.

    P0-2：指标看板——从 LoopState.rounds 聚合轮次/令牌/通过率统计，
    供 `hermes loop metrics` 命令展示。空 rounds 不除零。
    """
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    rounds = loop.rounds
    total_rounds = len(rounds)
    # 过滤 tokens_used=0 的轮次再算均值（与 estimate_cost 护栏一致）
    token_rounds = [r for r in rounds if r.tokens_used > 0]
    total_tokens = sum(r.tokens_used for r in rounds)
    avg_tokens = total_tokens / len(token_rounds) if token_rounds else 0
    passed = sum(1 for r in rounds if r.passed)
    failed = total_rounds - passed
    pass_rate = (passed / total_rounds * 100) if total_rounds else 0
    budget_pct = (
        loop.budget_used_tokens / loop.budget_limit_tokens * 100
        if loop.budget_limit_tokens > 0
        else 0
    )

    return {
        "success": True,
        "loop": name,
        "pattern": loop.pattern,
        "status": loop.status.value,
        "current_round": loop.current_round,
        "max_rounds": loop.max_rounds,
        "total_rounds": total_rounds,
        "passed_rounds": passed,
        "failed_rounds": failed,
        "pass_rate": round(pass_rate, 1),
        "total_tokens": total_tokens,
        "avg_tokens_per_round": round(avg_tokens, 1),
        "budget_used_tokens": loop.budget_used_tokens,
        "budget_limit_tokens": loop.budget_limit_tokens,
        "budget_remaining_tokens": loop.budget_limit_tokens - loop.budget_used_tokens,
        "budget_percentage": round(budget_pct, 1),
    }


def advance_stage(name: str) -> dict[str, Any]:
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    stage_order = [LoopStage.L1_REPORT, LoopStage.L2_ASSIST, LoopStage.L3_AUTONOMOUS]
    current_idx = stage_order.index(loop.stage)
    if current_idx >= len(stage_order) - 1:
        return {"success": False, "error": "Already at highest stage (L3)"}

    audit_result = audit_loop(name)
    if not audit_result.get("success"):
        return audit_result

    loop_result = audit_result["loops"][0]
    if loop_result["score"] < 70 and current_idx == 0:
        return {
            "success": False,
            "error": "Cannot advance to L2: readiness score too low",
            "score": loop_result["score"],
            "required": 70,
            "suggestions": loop_result["suggestions"],
        }
    if loop_result["score"] < 85 and current_idx == 1:
        return {
            "success": False,
            "error": "Cannot advance to L3: readiness score too high",
            "score": loop_result["score"],
            "required": 85,
            "suggestions": loop_result["suggestions"],
        }

    new_stage = stage_order[current_idx + 1]
    loop.stage = new_stage
    _save_loop_meta(loop)

    return {
        "success": True,
        "loop": name,
        "previous_stage": stage_order[current_idx].value,
        "new_stage": new_stage.value,
    }


def check_stop_rules(
    name: str,
    current_round: int,
    max_rounds: int,
    rounds: list[LoopRound],
    baseline_failures: list[str] | None = None,
) -> dict[str, Any]:
    """Check if any of the seven stop rules are triggered.

    Returns a dict with 'should_stop', 'rule_id', 'rule_name', 'description', and 'escalation_info'.

    经验A：若提供 baseline_failures（历史已知失败项），则过滤掉 rounds 中每个 round
    的 failure_items 里属于 baseline 的项，只对"新增失败"做后续判定。不提供时行为不变
    （向后兼容）。
    """
    # 经验A：排除基线失败项，只对新增失败做判定（向后兼容：不传则不过滤）
    if baseline_failures:
        baseline_set = set(baseline_failures)
        rounds = [
            replace(
                r,
                failure_items=[f for f in r.failure_items if f not in baseline_set],
                failure_count=sum(1 for f in r.failure_items if f not in baseline_set),
            )
            for r in rounds
        ]

    # Rule 1: ALL GREEN — handled by caller (passed=True on latest round)
    if rounds and rounds[-1].passed:
        return {
            "should_stop": True,
            "rule_id": "all_green",
            "rule_name": "ALL GREEN",
            "description": "所有检查通过。",
            "action": "stop_success",
            "escalation_info": None,
        }

    # Rule 2: Rounds exhausted
    if current_round >= max_rounds:
        return {
            "should_stop": True,
            "rule_id": "rounds_exhausted",
            "rule_name": "轮次用尽",
            "description": f"达到轮次上限 ({max_rounds})。",
            "action": "stop_escalate",
            "escalation_info": {
                "current_round": current_round,
                "max_rounds": max_rounds,
                "failed_items": rounds[-1].failure_items if rounds else [],
                "attempts": [
                    {"round": r.round_num, "action": r.action, "result": r.result_summary}
                    for r in rounds
                ],
            },
        }

    # Rule 3: Beyond capability — external dependency / environment issues.
    # Evaluated BEFORE regression/same_failure_twice so that a repeated
    # environment error is diagnosed as "超出能力" (accurate) rather than
    # "在猜" (misleading). Previously this rule was last and got shadowed.
    if rounds and not rounds[-1].passed:
        last_round = rounds[-1]
        capability_signals = [
            "permission denied",
            "connection refused",
            "module not found",
            "modulenotfounderror",
            "command not found",
            "no such file or directory",
            "eacces",
            "econnrefused",
            "etimedout",
            "cannot find module",
            "unauthorized",
            "forbidden",
            "database connection",
            "external dependency",
            "environment variable",
            "not installed",
        ]
        combined_text = (
            last_round.result_summary + " " + last_round.verifier_result
        ).lower()
        matched_signals = [
            sig for sig in capability_signals if sig in combined_text
        ]
        if matched_signals:
            return {
                "should_stop": True,
                "rule_id": "beyond_capability",
                "rule_name": "疑似超出能力边界",
                "description": f"失败原因涉及外部依赖或环境问题: {', '.join(matched_signals)}。builder无法自行解决。",
                "action": "stop_escalate",
                "escalation_info": {
                    "current_round": current_round,
                    "matched_signals": matched_signals,
                    "last_result": last_round.result_summary,
                    "blocker": "外部依赖或环境问题，需要人工介入",
                },
            }

    # Rules 4-6 are mutually exclusive (互斥) based on set relationships:
    #   regression        : new ≠ ∅ AND overlap ≠ ∅
    #   same_failure_twice: new = ∅ AND overlap ≠ ∅ AND count未减
    #   no_progress       : new ≠ ∅ AND overlap = ∅ AND fixed ≠ ∅ AND count未减
    # This eliminates the shadowing where regression always preempted the others.
    if len(rounds) >= 2:
        prev_failures = set(rounds[-2].failure_items)
        curr_failures = set(rounds[-1].failure_items)
        new_failures = curr_failures - prev_failures
        previously_fixed = prev_failures - curr_failures
        persistent = prev_failures & curr_failures
        prev_count = rounds[-2].failure_count
        curr_count = rounds[-1].failure_count
        count_not_decreased = curr_count >= prev_count

        # Rule 4: Regression — introduced new failures AND some old failures persist
        # (builder edited related code and broke something new).
        if new_failures and persistent:
            return {
                "should_stop": True,
                "rule_id": "regression",
                "rule_name": "回归",
                "description": f"修复导致新失败: {', '.join(sorted(new_failures))}。之前修好的: {', '.join(sorted(previously_fixed))}",
                "action": "stop_escalate",
                "escalation_info": {
                    "current_round": current_round,
                    "new_failures": sorted(new_failures),
                    "previously_fixed": sorted(previously_fixed),
                    "persistent": sorted(persistent),
                },
            }

        # Rule 5: Same failure twice — no new failures, old ones persist, count not down.
        # (builder is guessing, not fixing).
        if not new_failures and persistent and count_not_decreased:
            return {
                "should_stop": True,
                "rule_id": "same_failure_twice",
                "rule_name": "同一失败连续两轮",
                "description": f"builder在猜，不是在修。共同失败项: {', '.join(sorted(persistent))}",
                "action": "stop_escalate",
                "escalation_info": {
                    "current_round": current_round,
                    "repeated_failures": sorted(persistent),
                    "last_two_rounds": [
                        {"round": r.round_num, "failures": r.failure_items}
                        for r in rounds[-2:]
                    ],
                },
            }

        # Rule 6: No progress — completely different failure set, count not down.
        # (task scope too large; each fix surfaces an unrelated new failure).
        if new_failures and not persistent and previously_fixed and count_not_decreased:
            return {
                "should_stop": True,
                "rule_id": "no_progress",
                "rule_name": "无实质进展",
                "description": f"连续2轮失败项数量未减少 ({prev_count} → {curr_count}) 且失败集合完全更换。可能任务范围过大。",
                "action": "stop_escalate",
                "escalation_info": {
                    "current_round": current_round,
                    "failure_counts": [prev_count, curr_count],
                    "new_failures": sorted(new_failures),
                    "previously_fixed": sorted(previously_fixed),
                    "suggestion": "拆分成更小的子任务",
                },
            }

    return {
        "should_stop": False,
        "rule_id": None,
        "rule_name": None,
        "description": None,
        "action": "continue",
        "escalation_info": None,
    }


def _generate_builder_md(name: str, pattern_info: dict[str, Any]) -> str:
    """Generate builder.md agent definition template."""
    denylist = pattern_info.get("denylist", [])
    denylist_str = "\n".join(f"  - {d}" for d in denylist) if denylist else "  - （暂无）"
    return f"""---
name: builder-{name}
description: 负责编写和修复代码。用于实现任务或修复 checker 发现的失败。
tools: Read, Write, Edit, Glob, Grep, Bash
---

你只负责构建和修复，不做其他任何事情。

## 接到任务时

1. 先读项目的 AGENTS.md、README、package.json（或等效配置文件），
   理解架构分层和编码约定。不了解项目约定就动手，白跑的循环比读文档
   花的时间多得多。
2. 确认任务涉及的文件范围。如果需要跨层修改，先想清楚依赖方向是否允许。
3. 写一行任务简报：目标、涉及文件、完成标准。然后开始实现。

## 接到修复请求时

1. 逐条阅读 checker 报告的失败项，每条失败都要读到 file:line。
2. 定位根因。区分症状和病因：测试失败是症状，代码逻辑错误是病因。
   修病因，不要修症状。
3. 一次只修一个根因。如果 checker 报了 3 个失败，但它们可能是同一个
   标根因引起的，先修最可能的那个，跑一遍检查看是否连带解决其他的。
4. 不要顺手重构不相关的代码。循环验证的场景下，每一行多余改动都可能
   引入新问题，让下一轮 checker 报出意料之外的失败。

## 红线
""" + "\n".join(f"- {line}" for line in BUILDER_RED_LINES) + f"""

## 汇报格式

修改完成后，先本地跑一遍 checker 会执行的命令，确认通过再汇报。

    改了什么：<一句话>
    修改文件：<file1>, <file2>, ...
    本地检查结果：<通过/失败>

## Denylist（禁止修改的路径）
{denylist_str}
"""


def _generate_checker_md(name: str) -> str:
    """Generate checker.md agent definition template."""
    return f"""---
name: checker-{name}
description: 运行所有检查并报告失败项。在 builder 之后调用。绝不修改代码。
tools: Read, Grep, Glob, Bash
---

你只检查，绝不修复。

## 发现检查命令

不要假设检查命令。先读 package.json 的 scripts 字段（或等效配置），
找出项目实际使用的检查命令。常见模式：

- test: `npm test` / `pnpm test` / `vitest run` / `pytest`
- lint: `eslint .` / `oxlint .` / `ruff check` / `biome check`
- 类型: `tsc --noEmit` / `vue-tsc --noEmit` / `mypy`
- 格式: `prettier --check` / `ruff format --check` / `format:check`

如果项目有聚合检查命令（如 `pnpm check` = test + lint + tsc + format），
优先跑聚合命令，它能一次性覆盖所有检查项。

如果项目有额外检查（依赖守卫、deadcode 检测、安全扫描等），也要跑。
这些检查往往能抓到测试和 lint 抓不到的问题。

## 执行

按顺序运行所有检查命令。每项检查的完整输出都要保留，不要只保留最后
一行的 pass/fail。失败的检查往往需要看中间输出才能定位根因。

## 报告格式

- 全部通过：输出 "ALL GREEN"，然后逐项列出每项检查的名称和通过证明
  （如 "test: 848 passed, 0 failed"）。不要只说全过了。

- 任何失败：输出 "FAILED"，然后逐条列出：
  `file:line - 什么坏了 - 哪个检查抓到的`

  如果同一文件有多个失败，合并列出。如果多个失败可能是同一根因，
  标注疑似同源。

## 红线
""" + "\n".join(f"- {line}" for line in CHECKER_RED_LINES) + """

## 关键：工具级硬隔离

你的 tools 字段没有 Write 和 Edit。这不是提示词约束，是工具可见性的硬隔离。
即使你"想"修复某个问题，你物理上无法修改任何文件。这是设计意图：
**写代码的不验代码，验代码的不写代码。**
"""


def _generate_perspective_md(name: str, pattern_info: dict[str, Any]) -> str:
    """Generate perspective.md agent definition template for multi-perspective pattern."""
    denylist = pattern_info.get("denylist", [])
    denylist_str = "\n".join(f"  - {d}" for d in denylist) if denylist else "  - （暂无）"
    return f"""---
name: perspective-{name}
description: 从特定视角分析标的，只读不修改。与其他 perspective agent 并行执行。
tools: Read, Grep, Glob, Bash
---

你是一个视角分析 agent，只负责从你的视角分析标的，不修改任何代码。

## 接到任务时

1. 阅读任务描述中的 **分析标的** 和 **你的视角**。
2. 从你的视角出发，分析标的的关键特征。
3. 列出你的视角下的 **正面发现（Bull）** 和 **风险点（Bear）**，各 3-5 条。
4. 用 `<!-- claim: <可验证的断言> -->` 标记你做出的关键事实断言（至少 2 条），
   供 synthesizer 抽检验证。

## 汇报格式

```
## 视角：<你的视角>

### Bull（正面发现）
- ...

### Bear（风险点）
- ...

### 关键断言
<!-- claim: 断言1文本 -->
<!-- claim: 断言2文本 -->
```

## 红线

- 只读分析，绝不修改代码或文件
- 不要"端水"——如果你的视角倾向负面，就明确说负面，不要为了平衡而硬凑正面
- 断言必须可验证（有具体数字/文件/事实依据），不要写"可能""也许"

## Denylist（禁止访问的路径）
{denylist_str}
"""


def _generate_summary_md(name: str) -> str:
    """Generate summary.md (synthesizer) agent definition template for multi-perspective pattern."""
    return f"""---
name: synthesizer-{name}
description: 汇总各 perspective agent 的分析结果，输出含明确结论的综合报告。
tools: Read, Write, Grep, Glob
---

你是 synthesizer（汇总者），负责把多个视角的分析结果综合成一份报告。

## 接到任务时

1. 阅读任务描述中附带的各 perspective agent 分析结果。
2. 识别各视角的共识与分歧。
3. 综合判断，给出 **明确结论**——禁止"一方面...另一方面..."的端水表述。
4. 把报告写入 `summary.md` 文件。

## 汇报格式（写入 summary.md）

```
# 综合分析报告

## 分析标的
<标的描述>

## 各视角共识
- ...

## 各视角分歧
- ...

## 综合结论
<!-- conclusion: <明确结论，如"建议采纳"/"建议观望"/"建议回避"> -->

结论依据：
1. ...
2. ...
3. ...
```

## 红线

- **必须给出明确结论**：`<!-- conclusion: -->` 标记不可省略
- 禁止模糊表述："有一定风险""需要进一步观察""视情况而定"
- 如果信息不足以给结论，写 `<!-- conclusion: 信息不足，建议补充以下数据后再判断 -->` 并列出缺失数据
- 不要简单堆砌各视角内容，必须做综合判断
"""


def _generate_stop_rules_md(name: str, max_rounds: int) -> str:
    """Generate stop-rules.md with the seven stop conditions."""
    rules_text = "\n".join(
        f"{i+1}. **{r['name']}**：{r['description']}"
        for i, r in enumerate(STOP_RULES)
    )
    return f"""# Loop Stop Rules: {name}

循环能替你推进流程，但不能替你担责任。一个没人盯着的loop，也会没人盯着地犯错。
所以循环必须有刹车。

## 停止条件

循环在以下任一条件成立时停止：

{rules_text}

## 红线

- 永远不在没有 checker 输出的情况下报告成功。
- 永远不弱化、删除、跳过检查来达到 ALL GREEN。
- 永远不修改 checker 的工具白名单。

## 升级协议

停止并升级给人时，必须携带以下信息：
- 当前轮次（Cycle N/{max_rounds}）
- 仍失败的项列表
- 每项已尝试过的修复方法
- 你的判断：为什么继续循环不会解决问题

## 编排器规则
""" + "\n".join(f"- {rule}" for rule in ORCHESTRATOR_RULES)


def knowledge_hygiene_scan() -> dict[str, Any]:
    """Execute L1 report for knowledge-hygiene pattern: scan for issues."""
    root = _project_root()
    knowledge_dir = root / "knowledge"
    skills_dir = root / "skills"

    issues: dict[str, list[str]] = {
        "high_priority": [],
        "watch_list": [],
        "noise": [],
    }

    existing_knowledge = list(knowledge_dir.glob("*.md")) if knowledge_dir.exists() else []
    existing_skills = [d for d in skills_dir.iterdir() if d.is_dir()] if skills_dir.exists() else []

    skill_names = {s.name for s in existing_skills}
    knowledge_names = {k.name for k in existing_knowledge}

    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            listed_skills = set(manifest.get("skills", []))
            listed_knowledge = set(manifest.get("knowledge", []))

            for s in existing_skills:
                if s.name not in listed_skills:
                    issues["watch_list"].append(f"Skill '{s.name}' exists but not in manifest.json")
            for s_name in listed_skills:
                if s_name not in skill_names:
                    issues["high_priority"].append(f"manifest.json lists '{s_name}' but directory missing")

            for k in existing_knowledge:
                if k.name not in listed_knowledge:
                    issues["watch_list"].append(f"Knowledge '{k.name}' exists but not in manifest.json")
            for k_name in listed_knowledge:
                if k_name not in knowledge_names:
                    issues["high_priority"].append(f"manifest.json lists knowledge '{k_name}' but file missing")
        except (json.JSONDecodeError, OSError):
            issues["high_priority"].append("manifest.json parse error")

    for skill_dir in existing_skills:
        skill_md = skill_dir / "SKILL.md"
        meta_json = skill_dir / "_meta.json"
        if not skill_md.exists():
            issues["high_priority"].append(f"Skill '{skill_dir.name}' missing SKILL.md")
        else:
            content = skill_md.read_text(encoding="utf-8")
            if len(content.strip()) < 50:
                issues["watch_list"].append(f"Skill '{skill_dir.name}' SKILL.md is nearly empty")
            if "TODO" in content:
                issues["watch_list"].append(f"Skill '{skill_dir.name}' has TODO in SKILL.md")
        if not meta_json.exists():
            issues["noise"].append(f"Skill '{skill_dir.name}' has no _meta.json (optional)")

    if (root / "README.md").exists():
        readme = (root / "README.md").read_text(encoding="utf-8")
        if "Skill Sync" not in readme and "skill-sync" not in readme:
            issues["watch_list"].append("README.md doesn't mention Skill Sync feature yet")

    intent_debt_notes = []
    if not (root / "AGENTS.md").exists():
        intent_debt_notes.append("AGENTS.md missing - project conventions not documented (Intent Debt)")
    if intent_debt_notes:
        issues["high_priority"].extend(intent_debt_notes)

    return {
        "success": True,
        "pattern": "knowledge-hygiene",
        "stage": LoopStage.L1_REPORT.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "high_priority": issues["high_priority"],
        "watch_list": issues["watch_list"],
        "noise": issues["noise"],
        "summary": {
            "high_priority_count": len(issues["high_priority"]),
            "watch_list_count": len(issues["watch_list"]),
            "noise_count": len(issues["noise"]),
        },
    }


# ── State management helpers ──────────────────────────────────────────


def record_round(
    name: str,
    round_data: LoopRound,
    tokens_used: int = 0,
) -> dict[str, Any]:
    """Record a completed round and persist state.

    Updates the loop's rounds list, current_round counter, budget, last_run
    timestamp, and status. Also writes a human-readable summary to STATE.md.
    """
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    # 经验A：记录该轮的基线失败项快照（便于跨轮次追溯当时的基线）
    if not round_data.baseline_failures:
        round_data.baseline_failures = list(loop.baseline_failures)
    loop.rounds.append(round_data)
    loop.current_round = round_data.round_num
    loop.last_run = datetime.now(timezone.utc).isoformat()
    loop.budget_used_tokens += tokens_used

    if loop.budget_limit_tokens > 0 and loop.budget_used_tokens >= loop.budget_limit_tokens:
        loop.status = LoopStatus.BUDGET_EXCEEDED
    elif round_data.passed:
        loop.status = LoopStatus.COMPLETED
    else:
        # 经验A：传入 baseline_failures，regression 判定时排除历史已知失败
        stop = check_stop_rules(
            name,
            loop.current_round,
            loop.max_rounds,
            loop.rounds,
            baseline_failures=loop.baseline_failures,
        )
        if stop["should_stop"]:
            loop.status = LoopStatus.NEEDS_HUMAN
        else:
            loop.status = LoopStatus.RUNNING
        # P0-1：回填诊断信息到当前轮次，随 _save_loop_meta 持久化。
        # 修复时序矛盾：此前 round_data 已 append 到 loop.rounds 但 escalation_info 未回填，
        # 导致 root_cause / matched_signals / blocker 永远无法持久化。
        round_data.escalation_info = stop.get("escalation_info") or {}

    _save_loop_meta(loop)
    _update_state_md(loop)

    # 经验F：校验产物清单存在性，缺失项写入返回结果（不阻断，仅留痕）
    missing_deliverables = (
        [d for d in loop.deliverables if not Path(d).exists()]
        if loop.deliverables
        else []
    )

    return {
        "success": True,
        "loop": name,
        "round": round_data.round_num,
        "status": loop.status.value,
        "tokens_used": tokens_used,
        "budget_used": loop.budget_used_tokens,
        "budget_remaining": loop.budget_limit_tokens - loop.budget_used_tokens,
        "missing_deliverables": missing_deliverables,
    }


def _update_state_md(loop: LoopState) -> None:
    """Write human-readable state summary to STATE.md."""
    lines = [f"# Loop State: {loop.name}", ""]
    lines.append(f"Last updated: {loop.last_run or 'never'}")
    lines.append("")
    lines.append("## Configuration")
    lines.append(f"- Pattern: {loop.pattern}")
    lines.append(f"- Stage: {loop.stage.value}")
    lines.append(f"- Status: {loop.status.value}")
    lines.append(f"- Current round: {loop.current_round}/{loop.max_rounds}")
    lines.append(f"- Budget: {loop.budget_used_tokens:,}/{loop.budget_limit_tokens:,} tokens")
    lines.append("")

    if loop.high_priority_items:
        lines.append("## High Priority")
        for item in loop.high_priority_items:
            lines.append(f"- {item}")
        lines.append("")

    if loop.watch_list:
        lines.append("## Watch List")
        for item in loop.watch_list:
            lines.append(f"- {item}")
        lines.append("")

    if loop.rounds:
        lines.append("## Execution History")
        for r in loop.rounds:
            marker = "✓" if r.passed else "✗"
            lines.append(f"### Round {r.round_num} {marker}")
            lines.append(f"- Action: {r.action}")
            lines.append(f"- Result: {r.result_summary}")
            lines.append(f"- Verifier: {r.verifier_result}")
            if r.failure_items:
                lines.append(f"- Failures ({r.failure_count}): {', '.join(r.failure_items[:5])}")
            if r.tokens_used:
                lines.append(f"- Tokens: {r.tokens_used:,}")
            lines.append("")

    # 经验B：软门禁留疤——展示审计未通过的检查项（留痕但不阻断执行）
    if loop.audit_warnings:
        lines.append("## Audit Warnings")
        lines.append("（软门禁未通过项，留痕但不阻断执行）")
        for w in loop.audit_warnings:
            lines.append(f"- {w}")
        lines.append("")

    # 经验F：产物清单及存在性检查状态
    if loop.deliverables:
        lines.append("## Deliverables")
        for d in loop.deliverables:
            exists = Path(d).exists()
            marker = "✓" if exists else "✗"
            lines.append(f"- {marker} {d}")
        lines.append("")

    loop.state_path.write_text("\n".join(lines), encoding="utf-8")


def get_loop_history(name: str) -> dict[str, Any]:
    """Return execution history for a loop."""
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    return {
        "success": True,
        "loop": name,
        "status": loop.status.value,
        "current_round": loop.current_round,
        "max_rounds": loop.max_rounds,
        "budget_used": loop.budget_used_tokens,
        "budget_limit": loop.budget_limit_tokens,
        "rounds": [r.to_dict() for r in loop.rounds],
    }


def check_budget(name: str) -> dict[str, Any]:
    """Check budget status and return alert level."""
    loop = get_loop(name)
    if not loop:
        return {"success": False, "error": f"Loop '{name}' not found"}

    used = loop.budget_used_tokens
    limit = loop.budget_limit_tokens
    pct = (used / limit * 100) if limit > 0 else 0

    if pct >= 100:
        level = "exceeded"
        action = "hard_stop"
    elif pct >= 80:
        level = "warning"
        action = "alert"
    else:
        level = "ok"
        action = "continue"

    return {
        "success": True,
        "loop": name,
        "used": used,
        "limit": limit,
        "percentage": round(pct, 1),
        "level": level,
        "action": action,
        "remaining": limit - used,
    }
