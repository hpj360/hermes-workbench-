"""工作流模型与 DAG 执行引擎。

支持以有向无环图 (DAG) 组织技能步骤，按拓扑序执行，
独立步骤可并行。执行结果持久化到 .state/workflow_executions.jsonl。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hermes.workbench.persistence import atomic_append_jsonl, atomic_write_json, safe_read_json
from hermes.workbench.skill_runner import RunResult, SkillRunner


@dataclass
class WorkflowStep:
    """工作流中的单个步骤节点。"""

    id: str
    skill: str
    args: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    timeout: float | None = None


@dataclass
class Workflow:
    """一个完整的工作流定义。"""

    id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [
                {
                    "id": s.id,
                    "skill": s.skill,
                    "args": s.args,
                    "depends_on": s.depends_on,
                    "timeout": s.timeout,
                }
                for s in self.steps
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Workflow:
        """从字典反序列化。"""
        steps = [
            WorkflowStep(
                id=s["id"],
                skill=s["skill"],
                args=s.get("args", []),
                depends_on=s.get("depends_on", []),
                timeout=s.get("timeout"),
            )
            for s in d.get("steps", [])
        ]
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            steps=steps,
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )


@dataclass
class StepResult:
    """单个步骤的执行结果。"""

    step_id: str
    skill: str
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration: float = 0.0
    error: str | None = None


@dataclass
class Execution:
    """一次工作流执行的完整记录。"""

    id: str
    workflow_id: str
    workflow_name: str
    status: str = "RUNNING"  # RUNNING / COMPLETED / FAILED / CANCELLED
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    step_results: list[StepResult] = field(default_factory=list)
    error: str | None = None

    @property
    def duration(self) -> float:
        """执行耗时。"""
        return self.ended_at - self.started_at if self.ended_at else 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration": self.duration,
            "step_results": [
                {
                    "step_id": r.step_id,
                    "skill": r.skill,
                    "ok": r.ok,
                    "stdout": r.stdout,
                    "stderr": r.stderr,
                    "exit_code": r.exit_code,
                    "duration": r.duration,
                    "error": r.error,
                }
                for r in self.step_results
            ],
            "error": self.error,
        }


class WorkflowStore:
    """工作流持久化存储。"""

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "workflows.json"
        state_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        return safe_read_json(self._path, {})

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        atomic_write_json(self._path, data)

    def create(self, name: str, description: str, steps: list[dict[str, Any]]) -> Workflow:
        """创建工作流。"""
        wf_id = f"wf-{uuid.uuid4().hex[:8]}"
        wf_steps = [
            WorkflowStep(
                id=s["id"],
                skill=s["skill"],
                args=s.get("args", []),
                depends_on=s.get("depends_on", []),
                timeout=s.get("timeout"),
            )
            for s in steps
        ]
        wf = Workflow(id=wf_id, name=name, description=description, steps=wf_steps)
        data = self._load()
        data[wf_id] = wf.to_dict()
        self._save(data)
        return wf

    def get(self, wf_id: str) -> Workflow | None:
        """获取单个工作流。"""
        data = self._load()
        d = data.get(wf_id)
        return Workflow.from_dict(d) if d else None

    def list(self) -> list[Workflow]:
        """列出所有工作流。"""
        data = self._load()
        return [Workflow.from_dict(d) for d in data.values()]

    def delete(self, wf_id: str) -> bool:
        """删除工作流。"""
        data = self._load()
        if wf_id in data:
            del data[wf_id]
            self._save(data)
            return True
        return False

    def update(self, wf_id: str, name: str | None = None, description: str | None = None,
               steps: list[dict[str, Any]] | None = None) -> Workflow | None:
        """更新工作流。"""
        data = self._load()
        d = data.get(wf_id)
        if not d:
            return None
        if name is not None:
            d["name"] = name
        if description is not None:
            d["description"] = description
        if steps is not None:
            d["steps"] = steps
        d["updated_at"] = time.time()
        data[wf_id] = d
        self._save(data)
        return Workflow.from_dict(d)


class WorkflowRunner:
    """DAG 执行引擎，按拓扑序执行工作流步骤。"""

    def __init__(self, runner: SkillRunner, state_dir: Path) -> None:
        self._runner = runner
        self._exec_log = state_dir / "workflow_executions.jsonl"
        state_dir.mkdir(parents=True, exist_ok=True)

    def _topo_sort(self, steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
        """拓扑排序，返回分层列表（同层可并行）。"""
        step_map = {s.id: s for s in steps}
        in_degree = {s.id: len(s.depends_on) for s in steps}
        dependents: dict[str, list[str]] = {s.id: [] for s in steps}
        for s in steps:
            for dep in s.depends_on:
                if dep in dependents:
                    dependents[dep].append(s.id)

        layers: list[list[WorkflowStep]] = []
        remaining = set(step_map.keys())

        while remaining:
            ready = [sid for sid in remaining if in_degree[sid] == 0]
            if not ready:
                # 环检测：强制打破
                ready = list(remaining)
            layer = [step_map[sid] for sid in ready]
            layers.append(layer)
            for sid in ready:
                remaining.discard(sid)
                for dep in dependents[sid]:
                    in_degree[dep] -= 1

        return layers

    def execute(self, wf: Workflow, timeout: float | None = None) -> Execution:
        """执行工作流，返回执行记录。"""
        from hermes.workbench.events import get_event_broker

        broker = get_event_broker()
        exec_id = f"ex-{uuid.uuid4().hex[:8]}"
        execution = Execution(
            id=exec_id,
            workflow_id=wf.id,
            workflow_name=wf.name,
        )

        # 发布工作流启动事件
        broker.publish("workflow.started", {
            "execution_id": exec_id,
            "workflow_id": wf.id,
            "workflow_name": wf.name,
            "total_steps": len(wf.steps),
        })

        layers = self._topo_sort(wf.steps)

        for layer in layers:
            for step in layer:
                result = self._run_step(step, timeout)
                execution.step_results.append(result)
                # 发布步骤完成事件
                broker.publish("workflow.step.completed", {
                    "execution_id": exec_id,
                    "workflow_id": wf.id,
                    "step_id": step.id,
                    "skill": step.skill,
                    "ok": result.ok,
                    "duration": result.duration,
                    "error": result.error,
                })
                if not result.ok:
                    execution.status = "FAILED"
                    execution.error = f"步骤 {step.id} ({step.skill}) 执行失败"
                    execution.ended_at = time.time()
                    self._log_execution(execution)
                    broker.publish("workflow.completed", {
                        "execution_id": exec_id,
                        "workflow_id": wf.id,
                        "status": "FAILED",
                        "error": execution.error,
                        "duration": execution.duration,
                    })
                    return execution

        execution.status = "COMPLETED"
        execution.ended_at = time.time()
        self._log_execution(execution)
        broker.publish("workflow.completed", {
            "execution_id": exec_id,
            "workflow_id": wf.id,
            "status": "COMPLETED",
            "duration": execution.duration,
            "steps_completed": len(execution.step_results),
        })
        return execution

    def _run_step(self, step: WorkflowStep, default_timeout: float | None = None) -> StepResult:
        """执行单个步骤。"""
        t = step.timeout or default_timeout
        try:
            r: RunResult = self._runner.run(step.skill, args=step.args, timeout=t)
            return StepResult(
                step_id=step.id,
                skill=step.skill,
                ok=r.ok,
                stdout=r.stdout,
                stderr=r.stderr,
                exit_code=r.exit_code,
                duration=r.duration,
                error=r.error,
            )
        except Exception as e:  # noqa: BLE001
            return StepResult(
                step_id=step.id,
                skill=step.skill,
                ok=False,
                error=str(e),
                duration=0.0,
            )

    def _log_execution(self, execution: Execution) -> None:
        """持久化执行记录。"""
        atomic_append_jsonl(self._exec_log, execution.to_dict())

    def list_executions(self, workflow_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """查询执行记录。"""
        if not self._exec_log.exists():
            return []
        results: list[dict[str, Any]] = []
        with open(self._exec_log, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if workflow_id is None or d.get("workflow_id") == workflow_id:
                        results.append(d)
                except json.JSONDecodeError:
                    continue
        return results[-limit:]
