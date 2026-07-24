"""统一注册中心：跨本地与 GitHub 多源管理 skill/agent/user/knowledge。

聚合本地源（./skills/、./knowledge/、./data/、~/.codex/skills 等）与多个
GitHub 仓库源（hpj360 账号下各仓库），提供统一的查询入口。

设计原则：
- 零额外依赖（urllib 调用 GitHub API）
- GitHub 结果缓存到 .cache/registry/，避免频繁调用
- 本地源优先，GitHub 源补充
- 可注入 github_fetcher 用于测试
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class SourceKind(str, Enum):
    LOCAL = "local"
    GITHUB = "github"


@dataclass
class RegistrySource:
    """一个注册源（本地目录或 GitHub 仓库）。"""

    name: str
    kind: SourceKind
    location: str  # local: 目录路径; github: "owner/repo"
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass
class SkillEntry:
    """跨源统一的 skill 条目。"""

    name: str
    source: str  # 源名称
    kind: SourceKind
    path: str  # local: 目录路径; github: "owner/repo/skills/name"
    description: str = ""
    has_skill_md: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass
class AgentEntry:
    """跨源统一的 agent 条目。"""

    name: str
    source: str
    kind: SourceKind
    config_path: str  # AGENT.md 或配置文件路径
    workspace: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass
class KnowledgeEntry:
    """跨源统一的知识文档条目。"""

    name: str
    source: str
    kind: SourceKind
    path: str
    size: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass
class UserProfile:
    """跨源统一的用户画像。"""

    source: str
    kind: SourceKind
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


# ---------------------------------------------------------------------------
# 默认源配置
# ---------------------------------------------------------------------------

# hpj360 账号下需要纳入统一管理的 GitHub 仓库
DEFAULT_GITHUB_REPOS: list[tuple[str, str]] = [
    ("hermes", "hpj360/Hermes"),
    ("workbench", "hpj360/hermes-workbench-"),
    ("knowledge-base", "hpj360/Hermes-knowledge-base"),
    ("ai-project", "hpj360/AI-project"),
    ("pm-team", "hpj360/pm-team"),
]

# 本地 agent 目录约定（复用 skills.py 的 KNOWN_AGENT_DIRS）
KNOWN_AGENT_DIRS: list[tuple[str, str]] = [
    ("codex", "~/.codex/skills"),
    ("claude-code", "~/.claude/skills"),
    ("cursor", "~/.cursor/skills"),
    ("trae", "~/.trae/skills"),
    ("openclaw", "~/.openclaw/skills"),
]

CACHE_TTL_SECONDS = 3600  # GitHub 缓存 1 小时


# ---------------------------------------------------------------------------
# GitHub API 客户端
# ---------------------------------------------------------------------------

GitHubFetcher = Callable[[str, str], bytes]
"""GitHub 内容获取函数：(repo, path) -> raw bytes。可注入用于测试。"""


def _default_github_fetcher(repo: str, path: str) -> bytes:
    """通过 GitHub API 获取仓库目录内容列表（零依赖 urllib）。"""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    api_url = f"https://api.github.com/repos/{repo}/contents/{quote(path, safe='/')}"
    req = Request(api_url, headers={"Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=15) as resp:
        return resp.read()


def _parse_github_listing(raw: bytes) -> list[dict[str, Any]]:
    """解析 GitHub contents API 返回的目录列表。"""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [
        {
            "name": item.get("name", ""),
            "type": item.get("type", ""),
            "size": item.get("size", 0),
            "path": item.get("path", ""),
        }
        for item in data
        if isinstance(item, dict)
    ]


# ---------------------------------------------------------------------------
# 本地源
# ---------------------------------------------------------------------------


class LocalSource:
    """本地文件系统源：读取 skills/、knowledge/、data/、agent 目录。"""

    def __init__(self, name: str, base_dir: Path, agent_dirs: list[tuple[str, str]] | None = None) -> None:
        self.source = RegistrySource(
            name=name,
            kind=SourceKind.LOCAL,
            location=str(base_dir),
            description=f"本地目录 {base_dir}",
        )
        self.base_dir = Path(base_dir)
        self._agent_dirs = agent_dirs or KNOWN_AGENT_DIRS

    def list_skills(self) -> list[SkillEntry]:
        skills_root = self.base_dir / "skills"
        if not skills_root.exists():
            return []
        result: list[SkillEntry] = []
        for entry in sorted(skills_root.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            desc = ""
            if skill_md.exists():
                desc = _extract_description(skill_md.read_text(encoding="utf-8"))
            result.append(
                SkillEntry(
                    name=entry.name,
                    source=self.source.name,
                    kind=SourceKind.LOCAL,
                    path=str(entry),
                    description=desc,
                    has_skill_md=skill_md.exists(),
                )
            )
        return result

    def list_agents(self) -> list[AgentEntry]:
        result: list[AgentEntry] = []
        for agent_name, path_str in self._agent_dirs:
            agent_path = Path(path_str).expanduser()
            if not agent_path.exists():
                continue
            config = agent_path / "AGENT.md"
            result.append(
                AgentEntry(
                    name=agent_name,
                    source=self.source.name,
                    kind=SourceKind.LOCAL,
                    config_path=str(config) if config.exists() else str(agent_path),
                    workspace=str(agent_path),
                    description=f"本地 agent 目录 ({path_str})",
                )
            )
        # 也检查项目内 agents/ 目录（pm-team 风格）
        local_agents = self.base_dir / "agents"
        if local_agents.exists():
            for entry in sorted(local_agents.iterdir()):
                if not entry.is_dir():
                    continue
                agent_md = entry / "AGENT.md"
                desc = ""
                if agent_md.exists():
                    desc = _extract_description(agent_md.read_text(encoding="utf-8"))
                result.append(
                    AgentEntry(
                        name=entry.name,
                        source=self.source.name,
                        kind=SourceKind.LOCAL,
                        config_path=str(agent_md) if agent_md.exists() else str(entry),
                        workspace=str(entry),
                        description=desc,
                    )
                )
        return result

    def list_knowledge(self) -> list[KnowledgeEntry]:
        knowledge_root = self.base_dir / "knowledge"
        if not knowledge_root.exists():
            return []
        result: list[KnowledgeEntry] = []
        for entry in sorted(knowledge_root.glob("*.md")):
            if entry.is_file():
                result.append(
                    KnowledgeEntry(
                        name=entry.name,
                        source=self.source.name,
                        kind=SourceKind.LOCAL,
                        path=str(entry),
                        size=entry.stat().st_size,
                    )
                )
        return result

    def get_user_profile(self) -> UserProfile | None:
        profile_path = self.base_dir / "data" / "profile.json"
        if not profile_path.exists():
            return None
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            return UserProfile(source=self.source.name, kind=SourceKind.LOCAL, data=data)
        except (json.JSONDecodeError, OSError):
            return None


# ---------------------------------------------------------------------------
# GitHub 源
# ---------------------------------------------------------------------------


class GitHubSource:
    """单个 GitHub 仓库源：通过 API 读取 skills/agents/knowledge/data。"""

    def __init__(
        self,
        name: str,
        repo: str,
        fetcher: GitHubFetcher | None = None,
        cache_dir: Path | None = None,
        cache_ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self.source = RegistrySource(
            name=name,
            kind=SourceKind.GITHUB,
            location=repo,
            description=f"GitHub 仓库 {repo}",
        )
        self.repo = repo
        self._fetcher = fetcher or _default_github_fetcher
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._cache_ttl = cache_ttl

    def _cache_path(self, key: str) -> Path | None:
        if not self._cache_dir:
            return None
        safe = key.replace("/", "_").replace(":", "_")
        return self._cache_dir / f"{self.repo.replace('/', '_')}_{safe}.json"

    def _fetch_with_cache(self, path: str) -> list[dict[str, Any]]:
        cache_file = self._cache_path(path)
        if cache_file and cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < self._cache_ttl:
                try:
                    return json.loads(cache_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
        try:
            raw = self._fetcher(self.repo, path)
            listing = _parse_github_listing(raw)
        except Exception:  # noqa: BLE001
            return []
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(listing, ensure_ascii=False), encoding="utf-8")
        return listing

    def list_skills(self) -> list[SkillEntry]:
        listing = self._fetch_with_cache("skills")
        return [
            SkillEntry(
                name=item["name"],
                source=self.source.name,
                kind=SourceKind.GITHUB,
                path=f"{self.repo}/skills/{item['name']}",
                has_skill_md=True,  # GitHub 目录级无法确认，假设有
            )
            for item in listing
            if item["type"] == "dir"
        ]

    def list_agents(self) -> list[AgentEntry]:
        listing = self._fetch_with_cache("agents")
        return [
            AgentEntry(
                name=item["name"],
                source=self.source.name,
                kind=SourceKind.GITHUB,
                config_path=f"{self.repo}/agents/{item['name']}/AGENT.md",
                workspace=f"{self.repo}/agents/{item['name']}",
                description=f"GitHub agent ({self.repo})",
            )
            for item in listing
            if item["type"] == "dir"
        ]

    def list_knowledge(self) -> list[KnowledgeEntry]:
        listing = self._fetch_with_cache("knowledge")
        return [
            KnowledgeEntry(
                name=item["name"],
                source=self.source.name,
                kind=SourceKind.GITHUB,
                path=f"{self.repo}/knowledge/{item['name']}",
                size=item.get("size", 0),
            )
            for item in listing
            if item["type"] == "file" and item["name"].endswith(".md")
        ]

    def get_user_profile(self) -> UserProfile | None:
        # GitHub 源仅读取 profile.example.json 作为模板参考
        listing = self._fetch_with_cache("data")
        for item in listing:
            if item["name"] == "profile.json" or item["name"] == "profile.example.json":
                return UserProfile(
                    source=self.source.name,
                    kind=SourceKind.GITHUB,
                    data={"_note": f"profile from {self.repo}", "file": item["name"]},
                )
        return None


# ---------------------------------------------------------------------------
# 统一注册中心
# ---------------------------------------------------------------------------


class Registry:
    """聚合多源的统一注册中心。"""

    def __init__(
        self,
        local_source: LocalSource | None = None,
        github_sources: list[GitHubSource] | None = None,
        github_fetcher: GitHubFetcher | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self._local = local_source
        self._github_sources = github_sources or []
        self._fetcher = github_fetcher
        self._cache_dir = cache_dir

    @classmethod
    def from_env(
        cls,
        base_dir: Path | None = None,
        github_repos: list[tuple[str, str]] | None = None,
        github_fetcher: GitHubFetcher | None = None,
        cache_dir: Path | None = None,
    ) -> Registry:
        """从环境构造 Registry，包含本地源 + 默认 GitHub 仓库。"""
        from hermes.config import get_settings

        if base_dir is None:
            base_dir = get_settings().hermes_project_root
        if cache_dir is None:
            cache_dir = get_settings().hermes_cache_dir / "registry"
        if github_repos is None:
            github_repos = DEFAULT_GITHUB_REPOS

        local = LocalSource(name="local", base_dir=base_dir)
        sources = [
            GitHubSource(
                name=name,
                repo=repo,
                fetcher=github_fetcher,
                cache_dir=cache_dir,
            )
            for name, repo in github_repos
        ]
        return cls(
            local_source=local,
            github_sources=sources,
            github_fetcher=github_fetcher,
            cache_dir=cache_dir,
        )

    def list_sources(self) -> list[RegistrySource]:
        sources: list[RegistrySource] = []
        if self._local:
            sources.append(self._local.source)
        for gs in self._github_sources:
            sources.append(gs.source)
        return sources

    def list_skills(self, source: str | None = None) -> list[SkillEntry]:
        result: list[SkillEntry] = []
        if self._local and (source is None or source == self._local.source.name):
            result.extend(self._local.list_skills())
        for gs in self._github_sources:
            if source is None or source == gs.source.name:
                result.extend(gs.list_skills())
        return result

    def list_agents(self, source: str | None = None) -> list[AgentEntry]:
        result: list[AgentEntry] = []
        if self._local and (source is None or source == self._local.source.name):
            result.extend(self._local.list_agents())
        for gs in self._github_sources:
            if source is None or source == gs.source.name:
                result.extend(gs.list_agents())
        return result

    def list_knowledge(self, source: str | None = None) -> list[KnowledgeEntry]:
        result: list[KnowledgeEntry] = []
        if self._local and (source is None or source == self._local.source.name):
            result.extend(self._local.list_knowledge())
        for gs in self._github_sources:
            if source is None or source == gs.source.name:
                result.extend(gs.list_knowledge())
        return result

    def get_user_profile(self) -> dict[str, Any]:
        """合并多源 user 画像，本地优先。"""
        profiles: list[UserProfile] = []
        if self._local:
            p = self._local.get_user_profile()
            if p:
                profiles.append(p)
        for gs in self._github_sources:
            p = gs.get_user_profile()
            if p:
                profiles.append(p)
        if not profiles:
            return {"_note": "no user profile found in any source"}
        # 本地 profile 作为主体，GitHub 源作为补充元数据
        primary = profiles[0]
        merged = dict(primary.data)
        if len(profiles) > 1:
            merged["_additional_sources"] = [
                {"source": p.source, "kind": p.kind.value} for p in profiles[1:]
            ]
        merged["_primary_source"] = primary.source
        return merged

    def refresh(self) -> dict[str, Any]:
        """清除 GitHub 缓存，强制下次查询重新拉取。"""
        cleared = 0
        if self._cache_dir and self._cache_dir.exists():
            for f in self._cache_dir.glob("*.json"):
                f.unlink()
                cleared += 1
        return {"cleared_cache_files": cleared, "cache_dir": str(self._cache_dir) if self._cache_dir else None}

    def summary(self) -> dict[str, Any]:
        """返回注册中心摘要统计。"""
        return {
            "sources": len(self.list_sources()),
            "skills": len(self.list_skills()),
            "agents": len(self.list_agents()),
            "knowledge": len(self.list_knowledge()),
            "has_user_profile": bool(self._local and self._local.get_user_profile()),
        }


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _extract_description(content: str) -> str:
    """从 SKILL.md / AGENT.md 的 YAML front-matter 提取 description。"""
    if not content.startswith("---"):
        # 取第一段非空文本作为描述
        for line in content.strip().splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped[:120]
        return ""
    lines = content.splitlines()
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            if key.strip().lower() == "description":
                return val.strip().strip("\"'")[:120]
    return ""


__all__ = [
    "DEFAULT_GITHUB_REPOS",
    "AgentEntry",
    "GitHubSource",
    "KnowledgeEntry",
    "LocalSource",
    "Registry",
    "RegistrySource",
    "SkillEntry",
    "SourceKind",
    "UserProfile",
]
