"""资产同步引擎：跨项目同步技能、记忆和用户画像。

支持三种同步模式：
- skills: 同步技能定义（不含代码）
- memory: 同步 L1 facts 和 L2 episodes
- profile: 合并多项目用户画像
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hermes.workbench.memory import MemoryService
from hermes.workbench.projects import ProjectRegistry
from hermes.workbench.skill_runner import SkillRunner


@dataclass
class SyncResult:
    """同步操作结果。"""

    source: str
    target: str
    asset_type: str  # skills / memory / profile
    synced: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0

    @property
    def ok(self) -> bool:
        """是否成功。"""
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "source": self.source,
            "target": self.target,
            "asset_type": self.asset_type,
            "synced": self.synced,
            "skipped": self.skipped,
            "errors": self.errors,
            "ok": self.ok,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration": self.ended_at - self.started_at if self.ended_at else 0.0,
        }


class AssetSync:
    """跨项目资产同步引擎。"""

    def __init__(
        self,
        registry: ProjectRegistry,
        runner: SkillRunner,
        memory: MemoryService,
    ) -> None:
        self._registry = registry
        self._runner = runner
        self._memory = memory

    def sync_skills(self, source_id: str, target_id: str) -> SyncResult:
        """从源项目同步技能到目标项目。

        Phase 3 原型阶段：仅记录技能清单，不实际复制代码。
        ``target_id="local"`` 表示同步到本地工作台，无需在注册中心查找。
        """
        result = SyncResult(source=source_id, target=target_id, asset_type="skills")
        source = self._registry.get(source_id)
        if not source:
            result.errors.append("源项目不存在")
            result.ended_at = time.time()
            return result

        # "local" 代表本地工作台，不需要在注册中心查找
        target = self._registry.get(target_id) if target_id != "local" else None

        # 获取本地技能清单作为模拟
        local_specs = self._runner.discover()
        for _spec in local_specs:
            result.synced += 1

        # 更新目标项目技能计数（仅当目标是已注册项目时）
        if target is not None:
            self._registry.update_status(
                target_id, target.status, skills_count=len(local_specs)
            )
        result.ended_at = time.time()
        return result

    def sync_memory(self, source_id: str, target_id: str) -> SyncResult:
        """从源项目同步记忆到目标项目。

        同步 L1 facts 和 L2 episodes 到本地记忆库。
        """
        result = SyncResult(source=source_id, target=target_id, asset_type="memory")
        source = self._registry.get(source_id)

        if not source:
            result.errors.append("源项目不存在")
            result.ended_at = time.time()
            return result

        # 同步 L1 facts
        facts = self._memory.list_facts()
        for fact in facts:
            # 记录同步来源
            key = fact.get("key", "")
            value = fact.get("value")
            if not key:
                continue
            sync_key = f"synced:{source_id}:{key}"
            self._memory.remember_fact(sync_key, value)
            result.synced += 1

        result.ended_at = time.time()
        return result

    def sync_profile(self, source_ids: list[str]) -> SyncResult:
        """合并多个项目的用户画像到统一画像。

        策略：后合并的项目覆盖先前的同名字段。
        """
        result = SyncResult(source=",".join(source_ids), target="local", asset_type="profile")

        current_profile = self._memory.get_user_profile()
        merged = dict(current_profile)

        for sid in source_ids:
            project = self._registry.get(sid)
            if not project:
                result.skipped += 1
                continue
            # 模拟：从项目配置中提取画像字段
            project_profile = project.config.get("profile", {})
            for key, value in project_profile.items():
                if key in merged and merged[key] != value:
                    result.synced += 1
                else:
                    result.skipped += 1
                merged[key] = value

        # 保存合并后的画像
        self._memory.save_user_profile(merged)
        result.ended_at = time.time()
        return result

    def sync_all(self, source_id: str, target_id: str) -> list[SyncResult]:
        """同步全部资产（技能 + 记忆 + 画像）。"""
        return [
            self.sync_skills(source_id, target_id),
            self.sync_memory(source_id, target_id),
            self.sync_profile([source_id]),
        ]
