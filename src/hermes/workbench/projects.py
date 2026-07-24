"""项目接入管理：多项目连接、状态监控、技能发现。

支持接入本地文件系统项目、GitHub 仓库项目、远程 API 项目，
统一管理跨项目技能路由和资产同步。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from hermes.workbench.persistence import atomic_write_json, safe_read_json


@dataclass
class ProjectConnection:
    """项目连接定义。"""

    id: str
    name: str
    type: str  # local / github / api
    url: str = ""
    status: str = "disconnected"  # connected / disconnected / error
    token: str = ""
    skills_count: int = 0
    agents_count: int = 0
    knowledge_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_sync: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（隐藏 token）。"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "url": self.url,
            "status": self.status,
            "has_token": bool(self.token),
            "skills_count": self.skills_count,
            "agents_count": self.agents_count,
            "knowledge_count": self.knowledge_count,
            "created_at": self.created_at,
            "last_sync": self.last_sync,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProjectConnection:
        """从字典反序列化。"""
        return cls(
            id=d["id"],
            name=d["name"],
            type=d["type"],
            url=d.get("url", ""),
            status=d.get("status", "disconnected"),
            token=d.get("token", ""),
            skills_count=d.get("skills_count", 0),
            agents_count=d.get("agents_count", 0),
            knowledge_count=d.get("knowledge_count", 0),
            created_at=d.get("created_at", time.time()),
            last_sync=d.get("last_sync", 0.0),
            config=d.get("config", {}),
        )


class ProjectRegistry:
    """项目注册中心，管理所有已接入项目。"""

    VALID_TYPES: ClassVar[set[str]] = {"local", "github", "api"}

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / "projects.json"
        state_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        return safe_read_json(self._path, {})

    def _save(self, data: dict[str, dict[str, Any]]) -> None:
        atomic_write_json(self._path, data)

    def add(
        self,
        name: str,
        project_type: str,
        url: str = "",
        token: str = "",
        config: dict[str, Any] | None = None,
    ) -> ProjectConnection:
        """接入新项目。"""
        if project_type not in self.VALID_TYPES:
            raise ValueError(f"无效的项目类型: {project_type}, 支持: {self.VALID_TYPES}")

        project_id = f"prj-{uuid.uuid4().hex[:8]}"
        project = ProjectConnection(
            id=project_id,
            name=name,
            type=project_type,
            url=url,
            token=token,
            config=config or {},
        )
        data = self._load()
        data[project_id] = project.to_dict() | {"token": token}
        self._save(data)
        return project

    def get(self, project_id: str) -> ProjectConnection | None:
        """获取单个项目。"""
        data = self._load()
        d = data.get(project_id)
        if not d:
            return None
        return ProjectConnection.from_dict(d)

    def list(self) -> list[ProjectConnection]:
        """列出所有项目。"""
        data = self._load()
        return [ProjectConnection.from_dict(d) for d in data.values()]

    def remove(self, project_id: str) -> bool:
        """断开并移除项目。"""
        data = self._load()
        if project_id in data:
            del data[project_id]
            self._save(data)
            return True
        return False

    def update_status(
        self,
        project_id: str,
        status: str,
        skills_count: int | None = None,
        agents_count: int | None = None,
        knowledge_count: int | None = None,
    ) -> ProjectConnection | None:
        """更新项目状态。"""
        data = self._load()
        d = data.get(project_id)
        if not d:
            return None
        d["status"] = status
        if skills_count is not None:
            d["skills_count"] = skills_count
        if agents_count is not None:
            d["agents_count"] = agents_count
        if knowledge_count is not None:
            d["knowledge_count"] = knowledge_count
        if status == "connected":
            d["last_sync"] = time.time()
        data[project_id] = d
        self._save(data)
        return ProjectConnection.from_dict(d)

    def summary(self) -> dict[str, Any]:
        """汇总统计。"""
        projects = self.list()
        connected = [p for p in projects if p.status == "connected"]
        return {
            "total": len(projects),
            "connected": len(connected),
            "disconnected": len(projects) - len(connected),
            "total_skills": sum(p.skills_count for p in projects),
            "total_agents": sum(p.agents_count for p in projects),
            "total_knowledge": sum(p.knowledge_count for p in projects),
        }
