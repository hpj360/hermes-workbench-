"""Tests for ui-design-system Skill (validate / generate_css / generate_tailwind / generate_swift / generate_android / audit)"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "ui-design-system"
SCRIPTS = SKILL_DIR / "scripts"
TOKENS_BASE = SKILL_DIR / "tokens" / "tokens.base.json"


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True, text=True, timeout=30,
    )


class TestValidate:
    def test_validate_passes_for_base_tokens(self):
        result = run_script("validate.py", "--tokens", str(TOKENS_BASE))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "✅ 校验通过" in result.stdout

    def test_validate_detects_bad_color(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"color": {"primary": "not-a-color"}}))
        result = run_script("validate.py", "--tokens", str(bad))
        assert result.returncode == 1
        assert "颜色格式错误" in result.stdout

    def test_validate_detects_missing_required_field(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"color": {"primary": "#FFF"}}))
        result = run_script("validate.py", "--tokens", str(bad))
        assert result.returncode == 1
        assert "缺少必填字段" in result.stdout


class TestGenerateCss:
    def test_generates_css_variables(self, tmp_path):
        out = tmp_path / "tokens.css"
        result = run_script("generate_css.py", "--tokens", str(TOKENS_BASE), "--output", str(out))
        assert result.returncode == 0
        assert out.exists()
        content = out.read_text()
        assert ":root {" in content
        assert "--color-blue-500" in content
        assert "#3B82F6" in content


class TestGenerateTailwind:
    def test_generates_tailwind_config(self, tmp_path):
        out = tmp_path / "tailwind.config.js"
        result = run_script("generate_tailwind.py", "--tokens", str(TOKENS_BASE), "--output", str(out))
        assert result.returncode == 0
        content = out.read_text()
        assert "module.exports" in content
        assert "colors:" in content
        assert "spacing:" in content


class TestGenerateSwift:
    def test_generates_swift_tokens(self, tmp_path):
        out = tmp_path / "Tokens.swift"
        result = run_script("generate_swift.py", "--tokens", str(TOKENS_BASE), "--output", str(out))
        assert result.returncode == 0
        content = out.read_text()
        assert "import SwiftUI" in content
        assert "public enum Tokens" in content
        assert "Color(red:" in content


class TestGenerateAndroid:
    def test_generates_colors_and_dimens(self, tmp_path):
        result = run_script("generate_android.py", "--tokens", str(TOKENS_BASE), "--output-dir", str(tmp_path))
        assert result.returncode == 0
        assert (tmp_path / "colors.xml").exists()
        assert (tmp_path / "dimens.xml").exists()
        assert "<color" in (tmp_path / "colors.xml").read_text()


class TestAudit:
    def test_audit_runs_on_base_tokens(self):
        result = run_script("audit.py", "--tokens", str(TOKENS_BASE))
        # audit 不一定退出 0（可能 warning），但要能跑
        assert "Token 审计" in result.stdout

    def test_audit_strict_mode(self):
        result = run_script("audit.py", "--tokens", str(TOKENS_BASE), "--strict")
        # base tokens 缺 color.primary 等警告；strict 模式下会退出非零
        # 但要确保不是 crash
        assert "Token 审计" in result.stdout
