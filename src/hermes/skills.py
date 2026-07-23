"""Skill discovery and management for Hermes.

Loads skills from the central repository under ./skills/ and provides
utilities for listing, syncing, and managing skills across multiple agents.

Implements the Nacos Skill Sync pattern:
- Single source of truth (central repository in ./skills/)
- Local mode with symlink/copy sync to external agent directories
- State tracking and conflict detection
- Automatic discovery of common agent skill directories
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SkillStatus(str, Enum):
    UNMANAGED = "unmanaged"
    LINKED = "linked"
    SYNCED = "synced"
    LOCAL_CHANGES = "local_changes"
    EXTERNAL_CHANGES = "external_changes"
    CONFLICT = "conflict"
    MISSING = "missing"


@dataclass
class SkillInfo:
    name: str
    path: Path
    has_skill_md: bool
    has_meta: bool
    meta: dict[str, Any] | None = None
    status: SkillStatus = SkillStatus.UNMANAGED
    synced_agents: list[str] = field(default_factory=list)
    source_agent: str | None = None
    next_action: str = ""


@dataclass
class AgentTarget:
    name: str
    path: Path
    exists: bool
    skill_count: int = 0
    is_symlink: bool = False


KNOWN_AGENT_DIRS = [
    ("codex", "~/.codex/skills"),
    ("claude-code", "~/.claude/skills"),
    ("cursor", "~/.cursor/skills"),
    ("qoder", "~/.qoder/skills"),
    ("qoder-work", "~/.qoder-work/skills"),
    ("kiro", "~/.kiro/skills"),
    ("lingma", "~/.lingma/skills"),
    ("copaw", "~/.copaw/skills"),
    ("openclaw", "~/.openclaw/skills"),
    ("agents-global", "~/.agents/skills"),
    ("skills-global", "~/.skills"),
    ("trae", "~/.trae/skills"),
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def skills_dir() -> Path:
    return _project_root() / "skills"


def knowledge_dir() -> Path:
    return _project_root() / "knowledge"


def state_dir() -> Path:
    return _project_root() / ".state"


def _sync_state_path() -> Path:
    return state_dir() / "skill_sync.json"


def _file_hash(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _dir_hash(directory: Path) -> str:
    if not directory.exists() or not directory.is_dir():
        return ""
    hasher = hashlib.sha256()
    for f in sorted(directory.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            rel = f.relative_to(directory)
            hasher.update(str(rel).encode())
            hasher.update(f.read_bytes())
    return hasher.hexdigest()


def _load_sync_state() -> dict[str, Any]:
    state_path = _sync_state_path()
    if not state_path.exists():
        return {
            "version": 1,
            "mode": "local",
            "profile": "default",
            "managed_skills": {},
            "custom_agents": [],
        }
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "version": 1,
            "mode": "local",
            "profile": "default",
            "managed_skills": {},
            "custom_agents": [],
        }


def _save_sync_state(state: dict[str, Any]) -> None:
    state_dir().mkdir(parents=True, exist_ok=True)
    _sync_state_path().write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def discover_agents() -> list[AgentTarget]:
    targets: list[AgentTarget] = []
    state = _load_sync_state()
    all_agents = KNOWN_AGENT_DIRS + [(a["name"], a["path"]) for a in state.get("custom_agents", [])]
    seen_names: set[str] = set()

    for name, path_str in all_agents:
        if name in seen_names:
            continue
        seen_names.add(name)
        path = Path(path_str).expanduser().resolve()
        exists = path.exists()
        is_symlink = path.is_symlink() if exists else False
        skill_count = 0
        if exists and path.is_dir():
            skill_count = sum(1 for d in path.iterdir() if d.is_dir())
        targets.append(
            AgentTarget(
                name=name,
                path=path,
                exists=exists,
                skill_count=skill_count,
                is_symlink=is_symlink,
            )
        )
    return targets


def add_agent_target(name: str, path_str: str) -> AgentTarget:
    state = _load_sync_state()
    custom = state.get("custom_agents", [])
    for a in custom:
        if a["name"] == name:
            a["path"] = path_str
            break
    else:
        custom.append({"name": name, "path": path_str})
    state["custom_agents"] = custom
    _save_sync_state(state)
    path = Path(path_str).expanduser().resolve()
    return AgentTarget(name=name, path=path, exists=path.exists())


def discover_skills() -> list[SkillInfo]:
    root = skills_dir()
    if not root.exists():
        return []

    state = _load_sync_state()
    managed = state.get("managed_skills", {})
    agents = discover_agents()
    agent_map = {a.name: a.path for a in agents if a.exists}

    result: list[SkillInfo] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        meta_json = entry / "_meta.json"
        meta: dict[str, Any] | None = None
        if meta_json.exists():
            try:
                meta = json.loads(meta_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = None

        info = SkillInfo(
            name=entry.name,
            path=entry,
            has_skill_md=skill_md.exists(),
            has_meta=meta_json.exists(),
            meta=meta,
        )

        if entry.name in managed:
            m = managed[entry.name]
            info.status = SkillStatus(m.get("status", "synced"))
            info.synced_agents = m.get("agents", [])
            info.source_agent = m.get("source_agent")
            info.next_action = _compute_next_action(info, agent_map, m)
        else:
            info.status = SkillStatus.UNMANAGED
            info.next_action = "skill-sync add to manage"

        result.append(info)
    return result


def _compute_next_action(
    info: SkillInfo,
    agent_map: dict[str, Path],
    managed_entry: dict[str, Any],
) -> str:
    if info.status == SkillStatus.SYNCED or info.status == SkillStatus.LINKED:
        return ""
    if info.status == SkillStatus.CONFLICT:
        return f"skill-sync resolve {info.name}"
    if info.status == SkillStatus.LOCAL_CHANGES:
        return "skill-sync sync to push changes"
    if info.status == SkillStatus.EXTERNAL_CHANGES:
        return "skill-sync resolve to choose version"
    if info.status == SkillStatus.MISSING:
        return "skill-sync sync to restore"
    return ""


def _detect_skill_status(skill_name: str) -> SkillStatus:
    central = skills_dir() / skill_name
    if not central.exists():
        return SkillStatus.MISSING

    state = _load_sync_state()
    managed = state.get("managed_skills", {})
    if skill_name not in managed:
        return SkillStatus.UNMANAGED

    m = managed[skill_name]
    central_hash = _dir_hash(central)
    recorded_hash = m.get("central_hash", "")

    agents = discover_agents()
    external_hashes: dict[str, str] = {}
    for agent_name in m.get("agents", []):
        for a in agents:
            if a.name == agent_name and a.exists:
                ext_path = a.path / skill_name
                if ext_path.exists():
                    external_hashes[agent_name] = _dir_hash(ext_path)
                break

    all_synced = True
    has_external_diff = False
    for agent_name, agent_hash in external_hashes.items():
        if agent_hash != central_hash:
            all_synced = False
            has_external_diff = True

    central_changed = central_hash != recorded_hash and recorded_hash != ""

    if central_changed and has_external_diff:
        return SkillStatus.CONFLICT
    if central_changed:
        return SkillStatus.LOCAL_CHANGES
    if has_external_diff:
        return SkillStatus.EXTERNAL_CHANGES
    if all_synced and recorded_hash == central_hash:
        if all((a.path / skill_name).is_symlink() for a in agents if a.name in m.get("agents", [])):
            return SkillStatus.LINKED
        return SkillStatus.SYNCED
    return SkillStatus.SYNCED


def list_knowledge_docs() -> list[Path]:
    root = knowledge_dir()
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.md") if p.is_file())


def get_skill_path(name: str) -> Path | None:
    candidate = skills_dir() / name
    return candidate if candidate.exists() and candidate.is_dir() else None


def _copy_directory(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink():
            dst.unlink()
        else:
            shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _create_symlink(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink():
            dst.unlink()
        else:
            shutil.rmtree(dst)
    os.symlink(src, dst, target_is_directory=True)


def _find_existing_skill(skill_name: str) -> tuple[str | None, Path | None]:
    for agent in discover_agents():
        if agent.exists:
            candidate = agent.path / skill_name
            if candidate.exists() and candidate.is_dir():
                return agent.name, candidate
    return None, None


def add_skill(
    skill_name: str,
    source: str | None = None,
    use_symlink: bool = True,
) -> dict[str, Any]:
    root = skills_dir()
    root.mkdir(parents=True, exist_ok=True)
    central = root / skill_name

    if central.exists() and not central.is_dir():
        return {"success": False, "error": f"{skill_name} exists but is not a directory"}

    state = _load_sync_state()
    managed = state.setdefault("managed_skills", {})

    agents = discover_agents()
    agent_map = {a.name: a.path for a in agents if a.exists}

    if not central.exists():
        if source and source in agent_map:
            src_path = agent_map[source] / skill_name
            if not src_path.exists():
                return {"success": False, "error": f"Skill not found in {source}"}
            _copy_directory(src_path, central)
        else:
            found_agent, found_path = _find_existing_skill(skill_name)
            if found_agent and found_path:
                if source is None:
                    return {
                        "success": False,
                        "error": f"Skill exists in agent '{found_agent}'. Specify --source {found_agent} or 'central' to confirm.",
                        "found_in": found_agent,
                    }
                _copy_directory(found_path, central)
            else:
                central.mkdir(parents=True)
                (central / "SKILL.md").write_text(
                    f"---\nname: {skill_name}\ndescription: TODO: describe when to use this skill\n---\n\n# {skill_name}\n\nTODO: document this skill\n",
                    encoding="utf-8",
                )

    target_agents: list[str] = []
    for agent in agents:
        if not agent.exists:
            continue
        target = agent.path / skill_name
        if use_symlink:
            _create_symlink(central, target)
        else:
            _copy_directory(central, target)
        target_agents.append(agent.name)

    managed[skill_name] = {
        "source_agent": source or "central",
        "agents": target_agents,
        "central_hash": _dir_hash(central),
        "mode": "symlink" if use_symlink else "copy",
        "status": SkillStatus.LINKED.value if use_symlink else SkillStatus.SYNCED.value,
    }
    _save_sync_state(state)

    return {
        "success": True,
        "skill": skill_name,
        "mode": "symlink" if use_symlink else "copy",
        "agents": target_agents,
    }


def add_all_skills(use_symlink: bool = True) -> list[dict[str, Any]]:
    root = skills_dir()
    results: list[dict[str, Any]] = []
    state = _load_sync_state()
    managed = state.get("managed_skills", {})

    for entry in sorted(root.iterdir()):
        if entry.is_dir() and entry.name not in managed:
            res = add_skill(entry.name, use_symlink=use_symlink)
            results.append(res)
    return results


def remove_skill(skill_name: str) -> dict[str, Any]:
    state = _load_sync_state()
    managed = state.get("managed_skills", {})

    if skill_name not in managed:
        return {"success": False, "error": f"Skill {skill_name} is not managed"}

    m = managed[skill_name]
    central = skills_dir() / skill_name
    use_symlink = m.get("mode", "copy") == "symlink"

    agents = discover_agents()
    for agent in agents:
        if not agent.exists:
            continue
        target = agent.path / skill_name
        if target.is_symlink():
            if central.exists() and use_symlink:
                target.unlink()
                _copy_directory(central, target)
            else:
                target.unlink()
        elif target.exists() and not use_symlink:
            pass
        elif target.exists() and use_symlink:
            _copy_directory(central, target)

    del managed[skill_name]
    _save_sync_state(state)

    return {"success": True, "skill": skill_name}


def sync_skills(skill_name: str | None = None) -> list[dict[str, Any]]:
    state = _load_sync_state()
    managed = state.get("managed_skills", {})
    results: list[dict[str, Any]] = []

    targets = [skill_name] if skill_name else list(managed.keys())

    for name in targets:
        if name not in managed:
            results.append({"skill": name, "success": False, "error": "not managed"})
            continue

        m = managed[name]
        central = skills_dir() / name
        if not central.exists():
            results.append({"skill": name, "success": False, "error": "central copy missing"})
            continue

        use_symlink = m.get("mode", "copy") == "symlink"
        agents = discover_agents()
        synced: list[str] = []
        known_agents = set(m.get("agents", []))

        for agent in agents:
            if not agent.exists:
                continue
            target = agent.path / name
            if use_symlink:
                if not target.is_symlink() or target.resolve() != central.resolve():
                    _create_symlink(central, target)
            else:
                _copy_directory(central, target)
            synced.append(agent.name)
            known_agents.add(agent.name)

        m["agents"] = sorted(known_agents)
        m["central_hash"] = _dir_hash(central)
        m["status"] = SkillStatus.LINKED.value if use_symlink else SkillStatus.SYNCED.value
        results.append({"skill": name, "success": True, "agents": synced})

    _save_sync_state(state)
    return results


def resolve_conflict(
    skill_name: str,
    source: str,
) -> dict[str, Any]:
    state = _load_sync_state()
    managed = state.get("managed_skills", {})

    if skill_name not in managed:
        return {"success": False, "error": f"Skill {skill_name} is not managed"}

    m = managed[skill_name]
    central = skills_dir() / skill_name
    agents = discover_agents()
    agent_map = {a.name: a.path for a in agents if a.exists}

    if source == "central":
        source_path = central
    elif source in agent_map:
        source_path = agent_map[source] / skill_name
    else:
        return {"success": False, "error": f"Unknown source: {source}"}

    if not source_path.exists():
        return {"success": False, "error": f"Source not found at {source_path}"}

    if source != "central":
        _copy_directory(source_path, central)

    use_symlink = m.get("mode", "copy") == "symlink"
    synced: list[str] = []
    known_agents = set(m.get("agents", []))
    for agent_name in agent_map:
        target = agent_map[agent_name] / skill_name
        if use_symlink:
            _create_symlink(central, target)
        else:
            _copy_directory(central, target)
        synced.append(agent_name)
        known_agents.add(agent_name)

    m["agents"] = sorted(known_agents)
    m["central_hash"] = _dir_hash(central)
    m["source_agent"] = source
    m["status"] = SkillStatus.LINKED.value if use_symlink else SkillStatus.SYNCED.value
    _save_sync_state(state)

    return {"success": True, "skill": skill_name, "resolved_from": source, "agents": synced}


def refresh_status() -> dict[str, Any]:
    state = _load_sync_state()
    managed = state.get("managed_skills", {})
    summary: dict[str, int] = {s.value: 0 for s in SkillStatus}

    for name in list(managed.keys()):
        status = _detect_skill_status(name)
        managed[name]["status"] = status.value
        summary[status.value] += 1

    _save_sync_state(state)
    return {"summary": summary, "total": len(managed)}
