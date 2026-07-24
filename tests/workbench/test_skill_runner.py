"""Tests for hermes.workbench.skill_runner."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest

from hermes.workbench.skill_runner import (
    RunResult,
    SkillRunner,
    SkillSpec,
    _detect_entrypoint,
    _looks_sensitive,
    _parse_front_matter,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _write_skill_md(skill_dir: Path, body: str) -> Path:
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(body, encoding="utf-8")
    return skill_md


PROMPT_SKILL_MD = """---
name: alpha
description: alpha prompt skill
metadata: {"clawdbot":{"requires":{"bins":["node"]}}}
---

# Alpha

Body content here.
"""


# ---------------------------------------------------------------------------
# _looks_sensitive
# ---------------------------------------------------------------------------


def test_looks_sensitive_matches_token_substring() -> None:
    assert _looks_sensitive("MY_TOKEN") is True
    assert _looks_sensitive("SLACK_BOT_TOKEN") is True


def test_looks_sensitive_matches_secret_substring() -> None:
    assert _looks_sensitive("CLIENT_SECRET") is True


def test_looks_sensitive_matches_password_substring() -> None:
    assert _looks_sensitive("DB_PASSWORD") is True
    assert _looks_sensitive("USER_PASSWD") is True
    assert _looks_sensitive("USER_PWD") is True


def test_looks_sensitive_matches_credential_substring() -> None:
    assert _looks_sensitive("AWS_CREDENTIALS") is True


def test_looks_sensitive_matches_api_key_suffix() -> None:
    assert _looks_sensitive("OPENAI_API_KEY") is True
    assert _looks_sensitive("GOOGLE_APIKEY") is True  # _apikey suffix matches
    assert _looks_sensitive("STRIPE_APIKEY") is True
    assert _looks_sensitive("STRIPE_API_KEY") is True


def test_looks_sensitive_safe_keys_are_not_flagged() -> None:
    assert _looks_sensitive("PATH") is False
    assert _looks_sensitive("HOME") is False
    assert _looks_sensitive("LANG") is False
    assert _looks_sensitive("HERMES_STATE_DIR") is False


# ---------------------------------------------------------------------------
# _parse_front_matter
# ---------------------------------------------------------------------------


def test_parse_front_matter_parses_json_metadata_string(tmp_path: Path) -> None:
    p = _write_skill_md(tmp_path / "alpha", PROMPT_SKILL_MD)
    fm = _parse_front_matter(p)
    assert fm["name"] == "alpha"
    assert fm["description"] == "alpha prompt skill"
    assert isinstance(fm["metadata"], dict)
    assert fm["metadata"]["clawdbot"]["requires"]["bins"] == ["node"]


def test_parse_front_matter_returns_empty_when_no_front_matter(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("# just a doc\n", encoding="utf-8")
    assert _parse_front_matter(p) == {}


def test_parse_front_matter_returns_empty_when_missing(tmp_path: Path) -> None:
    assert _parse_front_matter(tmp_path / "nope.md") == {}


def test_parse_front_matter_parses_list_values(tmp_path: Path) -> None:
    body = "---\nname: x\nread_when:\n  - one\n  - two\n---\n\nbody\n"
    p = _write_skill_md(tmp_path / "x", body)
    fm = _parse_front_matter(p)
    assert fm["read_when"] == ["one", "two"]


# ---------------------------------------------------------------------------
# _detect_entrypoint
# ---------------------------------------------------------------------------


def test_detect_entrypoint_python_run_py(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    (d / "run.py").write_text("#", encoding="utf-8")
    assert _detect_entrypoint(d) == ("run.py", "python")


def test_detect_entrypoint_python_main_py(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    (d / "main.py").write_text("#", encoding="utf-8")
    assert _detect_entrypoint(d) == ("main.py", "python")


def test_detect_entrypoint_shell(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    (d / "run.sh").write_text("#", encoding="utf-8")
    assert _detect_entrypoint(d) == ("run.sh", "shell")


def test_detect_entrypoint_node_run_js(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    (d / "run.js").write_text("#", encoding="utf-8")
    assert _detect_entrypoint(d) == ("run.js", "node")


def test_detect_entrypoint_node_index_js(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    (d / "index.js").write_text("#", encoding="utf-8")
    assert _detect_entrypoint(d) == ("index.js", "node")


def test_detect_entrypoint_prompt_when_none(tmp_path: Path) -> None:
    d = tmp_path / "s"
    d.mkdir()
    assert _detect_entrypoint(d) == (None, "prompt")


# ---------------------------------------------------------------------------
# SkillRunner.discover / get
# ---------------------------------------------------------------------------


def _make_runner_with_alpha(tmp_path: Path) -> SkillRunner:
    base = tmp_path / "skills"
    _write_skill_md(base / "alpha", PROMPT_SKILL_MD)
    return SkillRunner(base_dir=base)


def test_discover_returns_specs(tmp_path: Path) -> None:
    runner = _make_runner_with_alpha(tmp_path)
    specs = runner.discover()
    assert len(specs) == 1
    s = specs[0]
    assert isinstance(s, SkillSpec)
    assert s.name == "alpha"
    assert s.runtime == "prompt"
    assert s.entrypoint is None
    assert s.requires_bins == ["node"]
    assert s.description == "alpha prompt skill"
    assert s.raw_metadata["clawdbot"]["requires"]["bins"] == ["node"]


def test_discover_empty_when_base_missing(tmp_path: Path) -> None:
    runner = SkillRunner(base_dir=tmp_path / "nope")
    assert runner.discover() == []


def test_get_returns_spec_for_existing(tmp_path: Path) -> None:
    runner = _make_runner_with_alpha(tmp_path)
    spec = runner.get("alpha")
    assert spec is not None
    assert spec.name == "alpha"


def test_get_returns_none_for_missing(tmp_path: Path) -> None:
    runner = _make_runner_with_alpha(tmp_path)
    assert runner.get("does-not-exist") is None


# ---------------------------------------------------------------------------
# SkillRunner.run
# ---------------------------------------------------------------------------


def test_run_prompt_skill_returns_content(tmp_path: Path) -> None:
    runner = _make_runner_with_alpha(tmp_path)
    result = runner.run("alpha")
    assert isinstance(result, RunResult)
    assert result.ok is True
    assert result.exit_code == 0
    assert "# Alpha" in result.stdout
    assert result.error is None


def test_run_missing_skill_returns_error(tmp_path: Path) -> None:
    runner = _make_runner_with_alpha(tmp_path)
    result = runner.run("nope")
    assert result.ok is False
    assert result.exit_code == -1
    assert "not found" in (result.error or "")


def test_run_python_skill_executes(tmp_path: Path) -> None:
    base = tmp_path / "skills"
    _write_skill_md(base / "py-skill", PROMPT_SKILL_MD)
    (base / "py-skill" / "run.py").write_text(
        'import sys\nprint("py-out", *sys.argv[1:])\n', encoding="utf-8"
    )
    runner = SkillRunner(base_dir=base)
    result = runner.run("py-skill", args=["x", "y"])
    assert result.ok is True
    assert "py-out x y" in result.stdout


def test_run_shell_skill_executes(tmp_path: Path) -> None:
    if SkillRunner._find_shell() is None:
        pytest.skip("No POSIX shell (sh/bash) available on this platform")
    base = tmp_path / "skills"
    _write_skill_md(base / "sh-skill", PROMPT_SKILL_MD)
    (base / "sh-skill" / "run.sh").write_text(
        '#!/bin/sh\necho "sh-out $1"\n', encoding="utf-8"
    )
    runner = SkillRunner(base_dir=base)
    result = runner.run("sh-skill", args=["hello"])
    assert result.ok is True
    assert "sh-out hello" in result.stdout


def test_run_node_skill_executes(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node binary not on PATH")
    base = tmp_path / "skills"
    _write_skill_md(base / "js-skill", PROMPT_SKILL_MD)
    (base / "js-skill" / "run.js").write_text(
        'console.log("js-out " + process.argv[2])\n', encoding="utf-8"
    )
    runner = SkillRunner(base_dir=base)
    result = runner.run("js-skill", args=["hi"])
    assert result.ok is True
    assert "js-out hi" in result.stdout


def test_run_timeout_returns_timeout_error(tmp_path: Path) -> None:
    if SkillRunner._find_shell() is None:
        pytest.skip("No POSIX shell (sh/bash) available on this platform")
    base = tmp_path / "skills"
    _write_skill_md(base / "slow", PROMPT_SKILL_MD)
    (base / "slow" / "run.sh").write_text(
        '#!/bin/sh\nsleep 5\necho done\n', encoding="utf-8"
    )
    runner = SkillRunner(base_dir=base)
    result = runner.run("slow", timeout=0.5)
    assert result.ok is False
    assert result.exit_code == -1
    assert (result.error or "").startswith("timeout")


def test_run_missing_required_bin_fails(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "skills"
    _write_skill_md(
        base / "needs-bin",
        '---\nname: needs-bin\ndescription: x\nmetadata: {"clawdbot":{"requires":{"bins":["nonexistent-bin-xyz"]}}}\n---\n\nbody\n',
    )
    (base / "needs-bin" / "run.sh").write_text(
        '#!/bin/sh\necho hi\n', encoding="utf-8"
    )
    runner = SkillRunner(base_dir=base)
    monkeypatch.setattr(
        "hermes.workbench.skill_runner.shutil.which",
        lambda b: None if b == "nonexistent-bin-xyz" else "/usr/bin/" + b,
    )
    result = runner.run("needs-bin")
    assert result.ok is False
    assert "nonexistent-bin-xyz" in (result.stderr or "")


# ---------------------------------------------------------------------------
# Env sanitization
# ---------------------------------------------------------------------------


def test_sanitized_env_strips_sensitive_vars(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MY_API_TOKEN", "secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-xxx")
    monkeypatch.setenv("SAFE_VAR", "ok")
    runner = _make_runner_with_alpha(tmp_path)
    env = runner._sanitized_env()
    assert "MY_API_TOKEN" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["SAFE_VAR"] == "ok"


def test_sanitized_env_returns_dict(tmp_path: Path) -> None:
    runner = _make_runner_with_alpha(tmp_path)
    env = runner._sanitized_env()
    assert isinstance(env, dict)
    assert "PATH" in env  # sane default env var


# ---------------------------------------------------------------------------
# File-permission safety (run.sh stays executable-safe in subprocess)
# ---------------------------------------------------------------------------


def test_run_shell_skill_with_executable_bit(tmp_path: Path) -> None:
    base = tmp_path / "skills"
    _write_skill_md(base / "sh2", PROMPT_SKILL_MD)
    run_sh = base / "sh2" / "run.sh"
    run_sh.write_text('#!/bin/sh\necho exec-ok\n', encoding="utf-8")
    os.chmod(run_sh, os.stat(run_sh).st_mode | stat.S_IXUSR)
    runner = SkillRunner(base_dir=base)
    result = runner.run("sh2")
    assert result.ok is True
    assert "exec-ok" in result.stdout
