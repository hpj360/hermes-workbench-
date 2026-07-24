"""触发器系统：支持 GitHub Issue / 定时 / Webhook 三种触发方式。

触发器绑定到工作流，当条件满足时自动执行对应工作流。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from hermes.workbench.persistence import atomic_write_json, safe_read_json


@dataclass
class Trigger:
    """触发器定义。"""

    id: str
    workflow_id: str
    type: str  # github / cron / webhook
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_fired: float = 0.0
    fire_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "type": self.type,
            "config": self.config,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_fired": self.last_fired,
            "fire_count": self.fire_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Trigger:
        """从字典反序列化。"""
        return cls(
            id=d["id"],
            workflow_id=d["workflow_id"],
            type=d["type"],
            config=d.get("config", {}),
            enabled=d.get("enabled", True),
            created_at=d.get("created_at", time.time()),
            last_fired=d.get("last_fired", 0.0),
            fire_count=d.get("fire_count", 0),
        )


class TriggerStore:
    """触发器持久化存储。"""

    VALID_TYPES: ClassVar[set[str]] = {"github", "cron", "webhook"}

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "triggers.json"
        state_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        return safe_read_json(self._path, {})

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        atomic_write_json(self._path, data)

    def create(
        self, workflow_id: str, trigger_type: str, config: dict[str, Any]
    ) -> Trigger:
        """创建触发器。

        Args:
            workflow_id: 关联的工作流 ID
            trigger_type: 触发类型 (github/cron/webhook)
            config: 触发配置
                - github: {"repo": "owner/repo", "label": "workbench"}
                - cron: {"schedule": "0 9 * * 1-5"}
                - webhook: {"secret": "xxx"}

        Returns:
            创建的 Trigger 对象
        """
        if trigger_type not in self.VALID_TYPES:
            raise ValueError(f"无效的触发器类型: {trigger_type}, 支持: {self.VALID_TYPES}")

        trigger_id = f"tr-{uuid.uuid4().hex[:8]}"
        trigger = Trigger(
            id=trigger_id,
            workflow_id=workflow_id,
            type=trigger_type,
            config=config,
        )
        data = self._load()
        data[trigger_id] = trigger.to_dict()
        self._save(data)
        return trigger

    def get(self, trigger_id: str) -> Trigger | None:
        """获取单个触发器。"""
        data = self._load()
        d = data.get(trigger_id)
        return Trigger.from_dict(d) if d else None

    def list(self, workflow_id: str | None = None) -> list[Trigger]:
        """列出触发器，可按工作流过滤。"""
        data = self._load()
        triggers = [Trigger.from_dict(d) for d in data.values()]
        if workflow_id:
            triggers = [t for t in triggers if t.workflow_id == workflow_id]
        return triggers

    def delete(self, trigger_id: str) -> bool:
        """删除触发器。"""
        data = self._load()
        if trigger_id in data:
            del data[trigger_id]
            self._save(data)
            return True
        return False

    def toggle(self, trigger_id: str, enabled: bool) -> Trigger | None:
        """启用/禁用触发器。"""
        data = self._load()
        d = data.get(trigger_id)
        if not d:
            return None
        d["enabled"] = enabled
        data[trigger_id] = d
        self._save(data)
        return Trigger.from_dict(d)

    def mark_fired(self, trigger_id: str) -> None:
        """标记触发器已触发。"""
        data = self._load()
        d = data.get(trigger_id)
        if d:
            d["last_fired"] = time.time()
            d["fire_count"] = d.get("fire_count", 0) + 1
            data[trigger_id] = d
            self._save(data)
