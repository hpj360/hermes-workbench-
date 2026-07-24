"""Skill discovery and execution for the Workbench runtime.

Reads YAML front-matter from each skill's SKILL.md, detects an entrypoint
(run.py/main.py → python, run.sh → shell, run.js/index.js → node, otherwise
"prompt"), and runs the skill in a sanitized subprocess with sensitive
environment variables stripped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENSITIVE_SUBSTRINGS = ("token", "secret", "credential", "password", "passwd", "pwd")
_SENSITIVE_SUFFIXES = ("_api_key", "_apikey")


def _looks_sensitive(key: str) -> bool:
    """Return True if *key* looks like a secret-bearing env var name."""
    lower = key.lower()
    for sub in _SENSITIVE_SUBSTRINGS:
        if sub in lower:
            return True
    for suffix in _SENSITIVE_SUFFIXES:
        if lower.endswith(suffix):
            return True
    return False


def _parse_front_matter(path: Path) -> dict[str, Any]:
    """Parse YAML front-matter from a SKILL.md file.

    The ``metadata`` field is a JSON STRING (not nested YAML) and is parsed
    with ``json.loads``. Returns a dict of front-matter fields (empty if the
    file is missing or has no front-matter).
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}
    fm_lines = lines[1:end_idx]
    raw: dict[str, Any] = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip() or ":" not in line:
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            items: list[Any] = []
            j = i + 1
            while j < len(fm_lines) and fm_lines[j].lstrip().startswith("- "):
                items.append(fm_lines[j].lstrip()[2:].strip())
                j += 1
            raw[key] = items
            i = j
        else:
            raw[key] = value
            i += 1
    md = raw.get("metadata")
    if isinstance(md, str) and md:
        try:
            parsed = json.loads(md)
            if isinstance(parsed, dict):
                raw["metadata"] = parsed
            else:
                raw["metadata"] = {"value": parsed}
        except json.JSONDecodeError:
            pass
    return raw


def _detect_entrypoint(skill_dir: Path) -> tuple[str | None, str]:
    """Return (entrypoint_filename, runtime) for *skill_dir*."""
    candidates: list[tuple[str, str]] = [
        ("run.py", "python"),
        ("main.py", "python"),
        ("run.sh", "shell"),
        ("run.js", "node"),
        ("index.js", "node"),
    ]
    for fname, runtime in candidates:
        p = skill_dir / fname
        if p.exists() and p.is_file():
            return fname, runtime
    return None, "prompt"


def _coerce_stream(val: str | bytes | None) -> str:
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SkillSpec:
    """Resolved metadata for a single skill, ready to run."""

    name: str
    path: Path
    description: str
    runtime: str  # "prompt" | "python" | "shell" | "node"
    requires_bins: list[str]
    requires_env: list[str]
    entrypoint: str | None
    raw_metadata: dict[str, Any]


@dataclass
class RunResult:
    """Outcome of a single skill invocation."""

    skill: str
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    duration: float
    error: str | None


# ---------------------------------------------------------------------------
# SkillRunner
# ---------------------------------------------------------------------------


class SkillRunner:
    """Discover and execute skills under *base_dir*."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def discover(self) -> list[SkillSpec]:
        """Scan *base_dir* subdirectories and return one SkillSpec per skill."""
        if not self.base_dir.exists():
            return []
        specs: list[SkillSpec] = []
        for entry in sorted(self.base_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue
            specs.append(self._build_spec(entry, skill_md))
        return specs

    def get(self, name: str) -> SkillSpec | None:
        """Return the SkillSpec for *name*, or None if not installed."""
        for spec in self.discover():
            if spec.name == name:
                return spec
        return None

    def run(
        self,
        name: str,
        args: list[str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        """Run skill *name*. Returns a RunResult (never raises)."""
        spec = self.get(name)
        if spec is None:
            return RunResult(
                skill=name,
                ok=False,
                stdout="",
                stderr="",
                exit_code=-1,
                duration=0.0,
                error=f"skill not found: {name}",
            )
        if spec.entrypoint is None:
            return self._run_prompt(spec)
        return self._run_exec(spec, args or [], timeout)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _build_spec(self, skill_dir: Path, skill_md: Path) -> SkillSpec:
        fm = _parse_front_matter(skill_md)
        description = str(fm.get("description", "")) or ""
        raw_metadata = fm.get("metadata")
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}
        requires_bins: list[str] = []
        requires_env: list[str] = []
        clawdbot = raw_metadata.get("clawdbot")
        if isinstance(clawdbot, dict):
            req = clawdbot.get("requires")
            if isinstance(req, dict):
                bins = req.get("bins")
                if isinstance(bins, list):
                    requires_bins = [str(b) for b in bins]
                env = req.get("env")
                if isinstance(env, list):
                    requires_env = [str(e) for e in env]
        entrypoint, runtime = _detect_entrypoint(skill_dir)
        return SkillSpec(
            name=skill_dir.name,
            path=skill_dir,
            description=description,
            runtime=runtime,
            requires_bins=requires_bins,
            requires_env=requires_env,
            entrypoint=entrypoint,
            raw_metadata=raw_metadata,
        )

    def _run_prompt(self, spec: SkillSpec) -> RunResult:
        skill_md = spec.path / "SKILL.md"
        try:
            content = skill_md.read_text(encoding="utf-8")
        except OSError as exc:
            return RunResult(
                skill=spec.name,
                ok=False,
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                duration=0.0,
                error=str(exc),
            )
        return RunResult(
            skill=spec.name,
            ok=True,
            stdout=content,
            stderr="",
            exit_code=0,
            duration=0.0,
            error=None,
        )

    def _run_exec(
        self, spec: SkillSpec, args: list[str], timeout: float | None
    ) -> RunResult:
        missing = [b for b in spec.requires_bins if shutil.which(b) is None]
        if missing:
            return RunResult(
                skill=spec.name,
                ok=False,
                stdout="",
                stderr=f"missing required binaries: {', '.join(missing)}",
                exit_code=-1,
                duration=0.0,
                error=f"missing bins: {missing}",
            )
        cmd = self._build_command(spec, args)
        env = self._sanitized_env()
        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(spec.path),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                start_new_session=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                skill=spec.name,
                ok=False,
                stdout=_coerce_stream(exc.stdout),
                stderr=_coerce_stream(exc.stderr),
                exit_code=-1,
                duration=time.time() - start,
                error=f"timeout after {timeout}s",
            )
        except OSError as exc:
            return RunResult(
                skill=spec.name,
                ok=False,
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                duration=time.time() - start,
                error=str(exc),
            )
        duration = time.time() - start
        ok = proc.returncode == 0
        return RunResult(
            skill=spec.name,
            ok=ok,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration=duration,
            error=None if ok else f"exit {proc.returncode}",
        )

    @staticmethod
    def _find_shell() -> str | None:
        """Find an available POSIX shell (sh, bash) or Windows fallback."""
        for candidate in ("sh", "bash"):
            path = shutil.which(candidate)
            if path:
                return path
        if sys.platform == "win32":
            # Try Git Bash common install paths
            for p in (
                r"C:\Program Files\Git\bin\sh.exe",
                r"C:\Program Files\Git\usr\bin\sh.exe",
            ):
                if os.path.isfile(p):
                    return p
        return None

    def _build_command(self, spec: SkillSpec, args: list[str]) -> list[str]:
        if spec.entrypoint is None:
            return list(args)
        if spec.runtime == "python":
            return [sys.executable, spec.entrypoint, *args]
        if spec.runtime == "shell":
            shell = self._find_shell()
            if shell is None:
                raise OSError(
                    "No POSIX shell (sh/bash) found on PATH. "
                    "Install Git Bash or WSL on Windows."
                )
            return [shell, spec.entrypoint, *args]
        if spec.runtime == "node":
            return ["node", spec.entrypoint, *args]
        return [spec.entrypoint, *args]

    def _sanitized_env(self) -> dict[str, str]:
        """Return os.environ with sensitive keys stripped."""
        return {k: v for k, v in os.environ.items() if not _looks_sensitive(k)}
